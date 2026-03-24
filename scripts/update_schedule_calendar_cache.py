#!/usr/bin/env python3

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "pages" / "schedule" / "data"

CALENDARS = {
    "leagues": "https://calendar.google.com/calendar/ical/"
    "da80818db985c7def75a3f684726983ff5361d88ebe99a1800a16230d7348b0f%40group.calendar.google.com/public/basic.ics",
    "spotlight": "https://calendar.google.com/calendar/ical/"
    "c5990df85ec2c327d239e1ad43a117f68cb3cd715aca633e833de1c0f80b6e3a%40group.calendar.google.com/public/basic.ics",
}


def fetch_text(url):
    with urlopen(url, timeout=30) as response:
        body = response.read().decode("utf-8")
        if "BEGIN:VCALENDAR" not in body:
            raise ValueError(f"Unexpected response from {url}")
        return normalize_ics(body)


def normalize_ics(text):
    lines = text.splitlines()
    stable_lines = [line for line in lines if not line.startswith("DTSTAMP:")]
    return "\n".join(stable_lines).strip() + "\n"


def write_text(path, text):
    path.write_text(text, encoding="utf-8")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for slug, url in CALENDARS.items():
        try:
            body = fetch_text(url)
        except (HTTPError, URLError, TimeoutError, ValueError) as err:
            raise SystemExit(f"Failed to fetch {slug} calendar: {err}") from err

        target = DATA_DIR / f"{slug}.ics"
        write_text(target, body)
    print("Updated schedule calendar cache")


if __name__ == "__main__":
    main()
