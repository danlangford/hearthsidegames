#!/usr/bin/env python3
"""
Post schedule updates to Discord channel.

This script reads the generated schedule manifest and posts or updates
a message in a Discord channel with the current and next week's schedule images.
If a message with the current week's date already exists, it updates that message.
Otherwise, it creates a new message.

Environment Variables Required:
  DISCORD_BOT_TOKEN: Discord bot token with READ_MESSAGE_HISTORY, SEND_MESSAGES, ATTACH_FILES
  DISCORD_CHANNEL_ID: Numeric Discord channel ID where schedules should be posted

The script uses only Python standard library for maximum compatibility.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# Configuration
ROOT = Path(__file__).resolve().parent.parent
GENERATED_DIR = ROOT / "pages" / "schedule" / "generated"
MANIFEST_PATH = GENERATED_DIR / "manifest.json"
SCHEDULE0_PATH = GENERATED_DIR / "schedule0.png"
SCHEDULE1_PATH = GENERATED_DIR / "schedule1.png"

DISCORD_API_BASE = "https://discord.com/api/v10"
MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


def log(message, level="INFO"):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def load_env_vars():
    """Load and validate required environment variables."""
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    channel_id = os.getenv("DISCORD_CHANNEL_ID")

    if not bot_token or not channel_id:
        log("Missing required environment variables:", "ERROR")
        if not bot_token:
            log("  DISCORD_BOT_TOKEN not set", "ERROR")
        if not channel_id:
            log("  DISCORD_CHANNEL_ID not set", "ERROR")
        log("Setup instructions: https://github.com/danlangford/hearthsidegames/blob/main/docs/discord-setup.md", "ERROR")
        sys.exit(1)

    return bot_token, channel_id


def load_manifest():
    """Load manifest.json to get week date ranges and event counts."""
    try:
        manifest_data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return manifest_data
    except Exception as e:
        log(f"Failed to load manifest: {e}", "ERROR")
        raise


def format_date_range(start_str, end_str):
    """Format ISO dates to readable format like 'Mar 23-29'."""
    try:
        start_date = datetime.fromisoformat(start_str).date()
        end_date = datetime.fromisoformat(end_str).date()

        start_month = MONTH_ABBR[start_date.month - 1]
        end_month = MONTH_ABBR[end_date.month - 1]

        if start_date.month == end_date.month:
            return f"{start_month} {start_date.day}-{end_date.day}"
        else:
            return f"{start_month} {start_date.day}-{end_month} {end_date.day}"
    except Exception as e:
        log(f"Failed to format dates: {e}", "ERROR")
        raise


def build_message_content(manifest):
    """Build Discord message text with date ranges and event counts."""
    current = manifest["current_week"]
    next_week = manifest["next_week"]

    current_dates = format_date_range(current["start"], current["end"])
    next_dates = format_date_range(next_week["start"], next_week["end"])

    # Get year from current week (assuming it's the same for both weeks)
    current_year = datetime.fromisoformat(current["start"]).year

    content = (
        f"📅 **Schedule Update**\n"
        f"\n"
        f"Week of **{current_dates}** and **{next_dates}, {current_year}**\n"
        f"\n"
        f"This Week: {current['event_count']} events | Next Week: {next_week['event_count']} events\n"
        f"\n"
        f"📍 Hearthside Games - 6802 S Redwood Rd, West Jordan, UT\n"
        f"🌐 hearthside.games"
    )

    return content, current_dates


def make_api_request(url, method, headers, data=None, max_retries=3):
    """Make HTTP request to Discord API with retry logic for rate limits."""
    for attempt in range(max_retries):
        try:
            req = Request(url, data=data, headers=headers, method=method)
            response = urlopen(req)
            return response

        except HTTPError as e:
            if e.code == 429:  # Rate limited
                retry_after = float(e.headers.get("Retry-After", 5))
                log(f"Rate limited, waiting {retry_after}s before retry (attempt {attempt + 1}/{max_retries})", "WARN")
                time.sleep(retry_after)
                continue
            else:
                raise

        except (URLError, Exception) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                log(f"Request failed ({e}), retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})", "WARN")
                time.sleep(wait_time)
                continue
            else:
                raise

    raise Exception("Max retries exceeded")


def fetch_recent_messages(channel_id, bot_token, limit=50):
    """Fetch recent messages from channel to search for existing post."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages?limit={limit}"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "User-Agent": "HearthsideScheduleBot/1.0",
    }

    try:
        response = make_api_request(url, "GET", headers)
        response_data = response.read().decode("utf-8")
        messages = json.loads(response_data)
        return messages

    except HTTPError as e:
        if e.code == 403:
            log("Bot lacks permission to read messages (READ_MESSAGE_HISTORY)", "ERROR")
        elif e.code == 401:
            log("Invalid bot token (401 Unauthorized)", "ERROR")
        elif e.code == 404:
            log("Channel not found (check DISCORD_CHANNEL_ID)", "ERROR")
        raise


def search_existing_message(channel_id, bot_token, date_pattern):
    """Search recent messages for one containing the current week's date pattern."""
    try:
        messages = fetch_recent_messages(channel_id, bot_token)

        for msg in messages:
            content = msg.get("content", "")
            # Look for the exact date pattern in message content
            if date_pattern in content:
                msg_id = msg.get("id")
                created_at = msg.get("timestamp")
                log(f"Found existing message: id={msg_id} created={created_at}")
                return msg_id

        log(f"No existing message found with date pattern '{date_pattern}'")
        return None

    except Exception as e:
        log(f"Failed to search messages: {e}", "ERROR")
        raise


def create_multipart_payload(content, files_dict):
    """Create multipart/form-data body for file uploads.

    files_dict: dict of {filename: file_bytes}
    """
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
    parts = []

    # Add payload_json part
    parts.append(f"--{boundary}".encode("utf-8"))
    parts.append(b"Content-Disposition: form-data; name=\"payload_json\"")
    parts.append(b"Content-Type: application/json")
    parts.append(b"")
    payload = {"content": content}
    parts.append(json.dumps(payload).encode("utf-8"))

    # Add file parts
    for index, (filename, file_bytes) in enumerate(files_dict.items()):
        parts.append(f"--{boundary}".encode("utf-8"))
        parts.append(
            f"Content-Disposition: form-data; name=\"files[{index}]\"; filename=\"{filename}\"".encode("utf-8")
        )
        parts.append(b"Content-Type: image/png")
        parts.append(b"")
        parts.append(file_bytes)

    parts.append(f"--{boundary}--".encode("utf-8"))
    parts.append(b"")

    body = b"\r\n".join(parts)
    return boundary, body


def create_discord_message(channel_id, bot_token, content):
    """Create new Discord message with schedule images."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"

    # Read image files
    try:
        schedule0_data = SCHEDULE0_PATH.read_bytes()
        schedule1_data = SCHEDULE1_PATH.read_bytes()
    except FileNotFoundError as e:
        log(f"Missing schedule image file: {e}", "ERROR")
        raise

    files_dict = {
        "schedule0.png": schedule0_data,
        "schedule1.png": schedule1_data,
    }

    boundary, body = create_multipart_payload(content, files_dict)

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "HearthsideScheduleBot/1.0",
    }

    try:
        response = make_api_request(url, "POST", headers, data=body)
        response_data = response.read().decode("utf-8")
        msg = json.loads(response_data)
        msg_id = msg.get("id")
        log(f"Created new Discord message: id={msg_id}")
        return msg_id

    except HTTPError as e:
        if e.code == 403:
            log("Bot lacks permission to send messages (SEND_MESSAGES or ATTACH_FILES)", "ERROR")
        raise


def update_discord_message(channel_id, message_id, bot_token, content):
    """Update existing Discord message with new schedule images."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"

    # Read image files
    try:
        schedule0_data = SCHEDULE0_PATH.read_bytes()
        schedule1_data = SCHEDULE1_PATH.read_bytes()
    except FileNotFoundError as e:
        log(f"Missing schedule image file: {e}", "ERROR")
        raise

    files_dict = {
        "schedule0.png": schedule0_data,
        "schedule1.png": schedule1_data,
    }

    boundary, body = create_multipart_payload(content, files_dict)

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "HearthsideScheduleBot/1.0",
    }

    try:
        response = make_api_request(url, "PATCH", headers, data=body)
        response_data = response.read().decode("utf-8")
        msg = json.loads(response_data)
        log(f"Updated Discord message: id={message_id}")
        return message_id

    except HTTPError as e:
        if e.code == 403:
            log("Bot lacks permission to edit messages", "ERROR")
        raise


def post_to_discord():
    """Main orchestration: post or update schedule in Discord."""
    try:
        # Load configuration
        bot_token, channel_id = load_env_vars()
        log("Loaded environment variables")

        # Load manifest and build message
        manifest = load_manifest()
        log("Loaded manifest")

        content, current_date_pattern = build_message_content(manifest)
        log(f"Built message content (date pattern: {current_date_pattern})")

        # Search for existing message
        existing_msg_id = search_existing_message(channel_id, bot_token, current_date_pattern)

        # Create or update message
        if existing_msg_id:
            update_discord_message(channel_id, existing_msg_id, bot_token, content)
        else:
            create_discord_message(channel_id, bot_token, content)

        log("✅ Successfully posted schedule to Discord")
        return 0

    except Exception as e:
        log(f"❌ Failed to post to Discord: {e}", "ERROR")
        log("Workflow will continue despite Discord posting failure", "WARN")
        # Don't raise - let workflow succeed even if Discord posting fails
        return 1


if __name__ == "__main__":
    exit_code = post_to_discord()
    sys.exit(exit_code)
