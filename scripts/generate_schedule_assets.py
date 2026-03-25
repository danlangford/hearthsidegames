#!/usr/bin/env python3

import json
import shutil
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "pages" / "schedule" / "generated"
FONT_PATH = ROOT / "pages" / "HearthLexendExaVF.ttf"
LOGO_PATH = ROOT / "pages" / "favicon.png"
DENVER = ZoneInfo("America/Denver")

W = 1080

CALENDARS = {
    "league": "https://calendar.google.com/calendar/ical/"
    "da80818db985c7def75a3f684726983ff5361d88ebe99a1800a16230d7348b0f%40group.calendar.google.com/public/basic.ics",
    "spotlight": "https://calendar.google.com/calendar/ical/"
    "c5990df85ec2c327d239e1ad43a117f68cb3cd715aca633e833de1c0f80b6e3a%40group.calendar.google.com/public/basic.ics",
}

DAY_ABBR = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def load_font(size):
    return ImageFont.truetype(str(FONT_PATH), size=size)


FONT_TITLE = load_font(52)
FONT_SUBTITLE = load_font(30)
FONT_DAY = load_font(30)
FONT_DATE = load_font(20)
FONT_TIME = load_font(22)
FONT_EVENT = load_font(24)
FONT_META = load_font(18)
FONT_NO_EVENTS = load_font(22)
FONT_BRAND = load_font(20)


def fetch_calendar(url):
    with urlopen(url, timeout=30) as response:
        body = response.read().decode("utf-8")
    if "BEGIN:VCALENDAR" not in body:
        raise RuntimeError(f"Unexpected response for {url}")
    return body


def unfold_lines(lines):
    unfolded = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def parse_ics(text):
    events = []
    current = None
    for line in unfold_lines(text.splitlines()):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        base = key.split(";", 1)[0]
        if base == "SUMMARY":
            current["summary"] = value
        elif base == "DTSTART":
            current["dtstart"] = value
            current["dtstart_key"] = key
        elif base == "DTEND":
            current["dtend"] = value
            current["dtend_key"] = key
        elif base == "RRULE":
            current["rrule"] = value
        elif base == "STATUS":
            current["status"] = value
        elif base == "RECURRENCE-ID":
            current["recurrence_id"] = value
    return events


def parse_dt(value, key=""):
    if "VALUE=DATE" in key:
        return {
            "dt": datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=DENVER),
            "all_day": True,
        }

    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).astimezone(DENVER)
        return {"dt": dt, "all_day": False}

    if "TZID=" in key:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M")
        return {"dt": dt.replace(tzinfo=DENVER), "all_day": False}

    if "T" in value:
        fmt = "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M"
        dt = datetime.strptime(value, fmt)
        return {"dt": dt.replace(tzinfo=DENVER), "all_day": False}

    dt = datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=DENVER)
    return {"dt": dt, "all_day": True}


def parse_rrule(rule):
    parsed = {}
    for part in rule.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key] = value
    return parsed


def get_week_range(reference_date, offset_weeks=0):
    monday = reference_date - timedelta(days=reference_date.weekday()) + timedelta(weeks=offset_weeks)
    sunday = monday + timedelta(days=6)
    start_dt = datetime.combine(monday, time.min, DENVER)
    end_dt = datetime.combine(sunday, time.max, DENVER)
    return {"start": start_dt, "end": end_dt}


def expand_event(event, week):
    if event.get("status") == "CANCELLED" or "dtstart" not in event:
        return []

    start_info = parse_dt(event["dtstart"], event.get("dtstart_key", ""))
    start_dt = start_info["dt"]
    all_day = start_info["all_day"]

    if event.get("recurrence_id"):
        if week["start"] <= start_dt <= week["end"]:
            return [{"summary": event.get("summary", ""), "dt": start_dt, "all_day": all_day}]
        return []

    if not event.get("rrule"):
        if week["start"] <= start_dt <= week["end"]:
            return [{"summary": event.get("summary", ""), "dt": start_dt, "all_day": all_day}]
        return []

    rule = parse_rrule(event["rrule"])
    if rule.get("FREQ") != "WEEKLY":
        if week["start"] <= start_dt <= week["end"]:
            return [{"summary": event.get("summary", ""), "dt": start_dt, "all_day": all_day}]
        return []

    until = parse_dt(rule["UNTIL"])["dt"] if "UNTIL" in rule else None
    interval = int(rule.get("INTERVAL", "1"))
    by_days = rule.get("BYDAY", "").split(",") if rule.get("BYDAY") else []
    if not by_days:
        by_days = [list(DAY_CODES.keys())[start_dt.weekday()]]

    occurrences = []
    base_week_start = start_dt.date() - timedelta(days=start_dt.weekday())

    for day_code in by_days:
        weekday = DAY_CODES.get(day_code)
        if weekday is None:
            continue

        occurrence_date = week["start"].date() + timedelta(days=weekday)
        occurrence_dt = datetime.combine(
            occurrence_date,
            start_dt.timetz().replace(tzinfo=None),
            DENVER,
        )

        if occurrence_dt < start_dt:
            continue
        if until and occurrence_dt > until:
            continue

        week_delta = (occurrence_date - base_week_start).days // 7
        if week_delta % interval != 0:
            continue

        if "COUNT" in rule:
            occurrence_number = week_delta // interval + 1
            if occurrence_number > int(rule["COUNT"]):
                continue

        if week["start"] <= occurrence_dt <= week["end"]:
            occurrences.append(
                {"summary": event.get("summary", ""), "dt": occurrence_dt, "all_day": all_day}
            )

    return occurrences


def collect_events():
    merged = []
    for event_type, url in CALENDARS.items():
        for event in parse_ics(fetch_calendar(url)):
            event["type"] = event_type
            merged.append(event)
    return merged


def build_week_data(source_events, week):
    occurrences = []
    for event in source_events:
        for item in expand_event(event, week):
            item["type"] = event["type"]
            occurrences.append(item)

    deduped = {}
    for item in occurrences:
        key = (item["summary"], item["dt"].date().isoformat(), item["type"])
        deduped[key] = item

    ordered = sorted(deduped.values(), key=lambda item: item["dt"])
    by_day = [[] for _ in range(7)]
    for item in ordered:
        by_day[item["dt"].weekday()].append(item)
    return ordered, by_day


def fit_text(draw, text, font, max_width):
    value = text
    while value and draw.textlength(value, font=font) > max_width:
        value = value[:-2].rstrip() + "…"
    return value or text


def format_range(start_date, end_date):
    if start_date.month == end_date.month:
        return f"{MONTH_ABBR[start_date.month - 1]} {start_date.day} – {end_date.day}"
    return f"{MONTH_ABBR[start_date.month - 1]} {start_date.day} – {MONTH_ABBR[end_date.month - 1]} {end_date.day}"


def format_time(dt):
    hour = dt.hour % 12 or 12
    suffix = "AM" if dt.hour < 12 else "PM"
    if dt.minute == 0:
        return f"{hour} {suffix}"
    return f"{hour}:{dt.minute:02d} {suffix}"


def make_background(height):
    img = Image.new("RGBA", (W, height), "#F4F0EC")
    draw = ImageDraw.Draw(img)
    top = (244, 240, 236)
    bottom = (235, 228, 220)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line((0, y, W, y), fill=color)
    return img


def draw_schedule_image(output_path, label, week, by_day, event_count):
    row_heights = [max(120, 30 + max(1, len(day_events)) * 42) for day_events in by_day]
    height = 360 + sum(row_heights) + 140
    image = make_background(height)
    draw = ImageDraw.Draw(image)

    if LOGO_PATH.exists():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((72, 72))
        image.alpha_composite(logo, ((W - 72) // 2, 54))

    draw.text((W / 2, 144), "HEARTHSIDE GAMES", fill=(108, 96, 88), font=FONT_META, anchor="ma")
    draw.text((W / 2, 190), label.upper(), fill=(191, 87, 0), font=FONT_TITLE, anchor="ma")
    draw.text(
        (W / 2, 242),
        f"{format_range(week['start'].date(), week['end'].date())}, {week['start'].year}",
        fill=(77, 71, 64),
        font=FONT_SUBTITLE,
        anchor="ma",
    )
    draw.text((W / 2, 286), f"{event_count} events", fill=(103, 99, 92), font=FONT_META, anchor="ma")

    legend_y = 320
    draw.ellipse((380, legend_y, 392, legend_y + 12), fill=(191, 87, 0))
    draw.text((408, legend_y - 4), "Weekly", fill=(77, 71, 64), font=FONT_META)
    draw.ellipse((560, legend_y, 572, legend_y + 12), fill=(74, 93, 104))
    draw.text((588, legend_y - 4), "Special", fill=(77, 71, 64), font=FONT_META)

    y = 360
    for index, day_events in enumerate(by_day):
        day_date = week["start"].date() + timedelta(days=index)
        if index > 0:
            draw.line((65, y, W - 65, y), fill=(210, 205, 198), width=1)

        draw.text((70, y + 18), DAY_ABBR[index], fill=(191, 87, 0), font=FONT_DAY)
        draw.text(
            (70, y + 52),
            f"{MONTH_ABBR[day_date.month - 1]} {day_date.day}",
            fill=(122, 114, 104),
            font=FONT_DATE,
        )

        if not day_events:
            draw.text((220, y + 32), "No events", fill=(156, 150, 142), font=FONT_NO_EVENTS)
        else:
            for row, event in enumerate(day_events):
                ey = y + 18 + row * 42
                is_special = event["type"] == "spotlight"
                dot_color = (74, 93, 104) if is_special else (191, 87, 0)
                name_color = (74, 93, 104) if is_special else (27, 27, 27)
                time_color = (116, 108, 100) if not is_special else (96, 108, 118)
                draw.ellipse((198, ey + 10, 208, ey + 20), fill=dot_color)
                draw.text(
                    (220, ey),
                    "ALL DAY" if event["all_day"] else format_time(event["dt"]),
                    fill=time_color,
                    font=FONT_TIME,
                )
                title = fit_text(draw, event["summary"], FONT_EVENT, W - 430 - 65)
                draw.text((430, ey), title, fill=name_color, font=FONT_EVENT)

        y += max(120, 30 + max(1, len(day_events)) * 42)

    draw.text((W / 2, y + 40), "hearthside.games", fill=(90, 84, 78), font=FONT_BRAND, anchor="ma")
    draw.text((W / 2, y + 68), "6802 S Redwood Rd · West Jordan, UT", fill=(130, 122, 114), font=FONT_META, anchor="ma")

    image.convert("RGB").save(output_path)


def build_manifest_entry(label, week, filename, alias=None):
    return {
        "label": label,
        "start": week["start"].date().isoformat(),
        "end": week["end"].date().isoformat(),
        "filename": filename,
        "alias": alias,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.glob("schedule*.png"):
        path.unlink()
    manifest_path = OUTPUT_DIR / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()

    source_events = collect_events()
    today = datetime.now(DENVER).date()

    current_week = get_week_range(today, 0)
    next_week = get_week_range(today, 1)

    current_events, current_by_day = build_week_data(source_events, current_week)
    next_events, next_by_day = build_week_data(source_events, next_week)

    current_name = f"schedule-{current_week['start'].date().isoformat()}-to-{current_week['end'].date().isoformat()}.png"
    next_name = f"schedule-{next_week['start'].date().isoformat()}-to-{next_week['end'].date().isoformat()}.png"

    draw_schedule_image(OUTPUT_DIR / current_name, "This Week", current_week, current_by_day, len(current_events))
    draw_schedule_image(OUTPUT_DIR / next_name, "Next Week", next_week, next_by_day, len(next_events))

    shutil.copyfile(OUTPUT_DIR / next_name, OUTPUT_DIR / "schedule.png")

    manifest = {
        "current_week": build_manifest_entry("This Week", current_week, current_name),
        "next_week": build_manifest_entry("Next Week", next_week, next_name, alias="schedule.png"),
    }

    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Generated schedule assets")


if __name__ == "__main__":
    main()
