# Discord Schedule Posting Setup Guide

This guide walks you through setting up the automatic Discord schedule posting feature. The system will automatically post schedule updates to your Discord #store-schedule channel whenever the weekly schedule changes.

## What You'll Be Setting Up

- A Discord bot that posts schedule images to your server
- GitHub secrets to authenticate the bot
- Automatic posting triggered by schedule updates (every 4 hours or on manual trigger)

## Step 1: Create Discord Bot Application

### 1.1 Create the Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"** button (top right)
3. Name it: `Hearthside Schedule Bot` (or your preference)
4. Click **"Create"**
5. Accept the terms if prompted

### 1.2 Set Up Bot User

1. In the left sidebar, click **"Bot"**
2. Click **"Add Bot"** button
3. Under **"TOKEN"** section, click **"Copy"** to copy your bot token
   - ⚠️ **IMPORTANT**: Save this token somewhere safe. You'll need it in Step 3.
   - Never share this token publicly

### 1.3 Enable Required Intents

1. On the Bot page, scroll down to **"Privileged Gateway Intents"**
2. Enable the **"Message Content Intent"** toggle
   - This allows the bot to read message content to search for existing posts
3. Click **"Save Changes"**

### 1.4 Set Bot Permissions

1. In the left sidebar, click **"OAuth2"** → **"URL Generator"**
2. Under **"SCOPES"**, check:
   - ✅ `bot`
3. Under **"PERMISSIONS"**, check:
   - ✅ `Send Messages`
   - ✅ `Attach Files`
   - ✅ `Read Messages/View Channels`
4. Copy the generated URL at the bottom (under "GENERATED URL")

## Step 2: Add Bot to Your Discord Server

### 2.1 Invite the Bot

1. Paste the URL from Step 1.4 into your browser
2. Select your Discord server from the dropdown
3. Click **"Authorize"**
4. Complete any CAPTCHA if prompted

### 2.2 Verify Bot Access

1. Go to your Discord server
2. Right-click the #store-schedule channel
3. Click "View Channel Details"
4. Go to "Permissions" tab
5. Verify that your bot user has:
   - ✅ View Channel
   - ✅ Send Messages
   - ✅ Attach Files
   - ✅ Read Message History

## Step 3: Get Discord Channel ID

1. In Discord, right-click the **#store-schedule** channel
2. Click **"Copy Channel ID"**
3. ⚠️ Save this ID somewhere safe. You'll need it in Step 4.

## Step 4: Configure GitHub Secrets

These secrets authenticate the bot and tell the workflow where to post.

### 4.1 Add DISCORD_BOT_TOKEN

1. Go to your GitHub repository
2. Click **Settings** (top navigation)
3. In left sidebar, click **"Secrets and variables"** → **"Actions"**
4. Click **"New repository secret"**
   - **Name**: `DISCORD_BOT_TOKEN`
   - **Value**: (paste the bot token from Step 1.2)
5. Click **"Add secret"**

### 4.2 Add DISCORD_CHANNEL_ID

1. Click **"New repository secret"** again
   - **Name**: `DISCORD_CHANNEL_ID`
   - **Value**: (paste the channel ID from Step 3)
2. Click **"Add secret"**

## Step 5: Test the Integration

### 5.1 Trigger Workflow Manually

1. Go to your GitHub repository
2. Click **"Actions"** (top navigation)
3. Select **"Generate Schedule Assets"** workflow (left sidebar)
4. Click **"Run workflow"** button (blue button, top right)
5. Click **"Run workflow"** in the dropdown

### 5.2 Check Discord

1. Go to your Discord server's #store-schedule channel
2. You should see a new message with:
   - 📅 Schedule Update header
   - This week and next week dates
   - Event counts
   - Two schedule images (schedule0.png and schedule1.png) attached

If the message appeared, **Setup is complete!** ✅

## Troubleshooting

### "Bot is in the server but not in the channel"

1. Verify the bot has access to #store-schedule:
   - Right-click channel → Permissions
   - Find your bot user
   - Ensure they have "Send Messages" and "Attach Files" permissions

**Solution**: Either grant the bot permissions on that specific channel, or ensure the bot has permissions in the server's @everyone role.

### "No Discord message appears after workflow runs"

1. Check the workflow logs:
   - Go to GitHub → Actions → Generate Schedule Assets
   - Click the most recent run
   - Look for the "Post schedule to Discord" step
   - Check the logs for error messages

2. Common causes:
   - **Invalid bot token**: Verify you copied the entire token correctly in Step 1.2
   - **Invalid channel ID**: Verify you copied the channel ID correctly in Step 3
   - **Missing intents**: Verify MESSAGE CONTENT INTENT is enabled in Step 1.3
   - **Missing permissions**: Verify bot has required permissions in Step 2.2

3. If you see "401 Unauthorized":
   - Bot token is invalid or expired
   - Regenerate the bot token in Discord Developer Portal (Step 1.2)
   - Update the GitHub secret

4. If you see "403 Forbidden":
   - Bot lacks permissions (typically SEND_MESSAGES or ATTACH_FILES)
   - Verify bot permissions in your Discord server (Step 2.2)

5. If you see "404 Not Found":
   - Channel ID is invalid
   - Get a fresh channel ID from Step 3
   - Update the GitHub secret

### Workflow succeeds but Discord message doesn't update

The workflow intentionally doesn't fail if Discord posting fails. To verify what happened:

1. Go to GitHub Actions workflow run
2. Click "Post schedule to Discord" step
3. Check the logs for any error messages

This allows the main schedule generation to continue even if Discord is temporarily unavailable.

### "Rate limited" messages in logs

Discord has API rate limits. The bot automatically retries with backoff delays. This is normal and should resolve on its own.

If rate limiting persists:
- Check that only one GitHub Actions instance is running
- Avoid manually triggering the workflow excessively

## How It Works

### Automatic Updates

Once set up, the system automatically:

1. **Every 4 hours**: Checks Google Calendar for schedule changes
2. **If schedule changed**: Generates new PNG images
3. **Searches Discord**: Looks for existing message with current week's dates
4. **Updates or creates**:
   - If message found: Updates it with new images (no duplicate messages)
   - If not found: Creates new message (e.g., when week rolls over)

### Message Search Logic

The script searches for existing messages by looking for the current week's date range (e.g., "Mar 23-29"). This ensures:

- ✅ Only one message per week is posted
- ✅ Old week messages remain untouched
- ✅ No state files needed in the repository
- ✅ Handles week transitions naturally

## Resetting or Troubleshooting Setup

### To regenerate the bot token

If you suspect your token was exposed:

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click your application
3. Go to "Bot" page
4. Click **"Regenerate"** next to the token
5. Copy the new token
6. Update the `DISCORD_BOT_TOKEN` GitHub secret (Step 4.1)

### To change which channel receives posts

1. Get the new channel ID from Discord (Step 3)
2. Update the `DISCORD_CHANNEL_ID` GitHub secret (Step 4.2)

### To disable Discord posting temporarily

1. Go to GitHub → Settings → Secrets
2. Delete the `DISCORD_BOT_TOKEN` secret
3. Workflow will log a clear error and continue without posting

To re-enable: Add the secret back.

## Reference

**Files involved in this feature**:
- `scripts/post_schedule_to_discord.py` - Main Discord posting script
- `.github/workflows/generate_schedule_assets.yml` - GitHub Actions workflow
- `pages/schedule/generated/manifest.json` - Schedule metadata (dates, event counts)
- `pages/schedule/generated/schedule0.png` - This Week image
- `pages/schedule/generated/schedule1.png` - Next Week image

**Discord API Documentation**: [Discord.com/developers/docs](https://discord.com/developers/docs)

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review the GitHub Actions workflow logs for specific error messages
3. Verify all steps in this guide are completed
4. Check that your bot token and channel ID are current and correct
