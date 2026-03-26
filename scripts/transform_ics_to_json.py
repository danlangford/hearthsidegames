#!/usr/bin/env python3

import json
from datetime import UTC, datetime, time, timedelta
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from schedule_common import (
    OUTPUT_DIR,
    remove_stale_outputs,
    write_if_changed,
)

DENVER = ZoneInfo("America/Denver")

CALENDARS = {
    "league": "https://calendar.google.com/calendar/ical/"
    "da80818db985c7def75a3f684726983ff5361d88ebe99a1800a16230d7348b0f%40group.calendar.google.com/public/basic.ics",
    "spotlight": "https://calendar.google.com/calendar/ical/"
    "c5990df85ec2c327d239e1ad43a117f68cb3cd715aca633e833de1c0f80b6e3a%40group.calendar.google.com/public/basic.ics",
}

DAY_ABBR = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
DAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def fetch_calendar(url):
    with urlopen(url, timeout=30) as response:
        body = response.read().decode("utf-8")
    if "BEGIN:VCALENDAR" not in body:
        raise RuntimeError(f"Unexpected response for {url}")
    print(f"Fetched calendar: url={url} bytes={len(body.encode('utf-8'))}")
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
        elif base == "UID":
            current["uid"] = value
        elif base == "RECURRENCE-ID":
            current["recurrence_id"] = value
            current["recurrence_id_key"] = key
        elif base == "EXDATE":
            current.setdefault("exdates", []).append((value, key))
    return events


def parse_dt(value, key=""):
    if "VALUE=DATE" in key:
        return {
            "dt": datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=DENVER),
            "all_day": True,
        }

    if value.endswith("Z"):
        dt = (
            datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            .replace(tzinfo=UTC)
            .astimezone(DENVER)
        )
        return {"dt": dt, "all_day": False}

    if "TZID=" in key:
        dt = datetime.strptime(
            value, "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M"
        )
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
    monday = (
        reference_date
        - timedelta(days=reference_date.weekday())
        + timedelta(weeks=offset_weeks)
    )
    sunday = monday + timedelta(days=6)
    start_dt = datetime.combine(monday, time.min, DENVER)
    end_dt = datetime.combine(sunday, time.max, DENVER)
    return {"start": start_dt, "end": end_dt}


def build_override_keys(events):
    keys = set()
    for event in events:
        if not event.get("uid") or not event.get("recurrence_id"):
            continue
        recurrence_info = parse_dt(
            event["recurrence_id"], event.get("recurrence_id_key", "")
        )
        keys.add((event["uid"], recurrence_info["dt"].isoformat()))
    return keys


def build_exdate_keys(event):
    keys = set()
    for value, key in event.get("exdates", []):
        keys.add(parse_dt(value, key).get("dt").isoformat())
    return keys


def expand_event(event, week, override_keys):
    if event.get("status") == "CANCELLED" or "dtstart" not in event:
        return []

    start_info = parse_dt(event["dtstart"], event.get("dtstart_key", ""))
    start_dt = start_info["dt"]
    all_day = start_info["all_day"]
    uid = event.get("uid")

    if event.get("recurrence_id"):
        if week["start"] <= start_dt <= week["end"]:
            return [
                {
                    "summary": event.get("summary", ""),
                    "dt": start_dt,
                    "all_day": all_day,
                    "uid": uid,
                }
            ]
        return []

    if not event.get("rrule"):
        if week["start"] <= start_dt <= week["end"]:
            return [
                {
                    "summary": event.get("summary", ""),
                    "dt": start_dt,
                    "all_day": all_day,
                    "uid": uid,
                }
            ]
        return []

    rule = parse_rrule(event["rrule"])
    if rule.get("FREQ") != "WEEKLY":
        if week["start"] <= start_dt <= week["end"]:
            return [
                {
                    "summary": event.get("summary", ""),
                    "dt": start_dt,
                    "all_day": all_day,
                }
            ]
        return []

    until = parse_dt(rule["UNTIL"])["dt"] if "UNTIL" in rule else None
    interval = int(rule.get("INTERVAL", "1"))
    by_days = rule.get("BYDAY", "").split(",") if rule.get("BYDAY") else []
    if not by_days:
        by_days = [list(DAY_CODES.keys())[start_dt.weekday()]]

    occurrences = []
    base_week_start = start_dt.date() - timedelta(days=start_dt.weekday())
    exdate_keys = build_exdate_keys(event)

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
            occurrence_key = occurrence_dt.isoformat()
            if occurrence_key in exdate_keys:
                continue
            if uid and (uid, occurrence_key) in override_keys:
                continue
            occurrences.append(
                {
                    "summary": event.get("summary", ""),
                    "dt": occurrence_dt,
                    "all_day": all_day,
                    "uid": uid,
                }
            )

    return occurrences


def collect_events():
    merged = []
    for event_type, url in CALENDARS.items():
        parsed = parse_ics(fetch_calendar(url))
        print(f"Parsed source events: calendar={event_type} count={len(parsed)}")
        for event in parsed:
            event["type"] = event_type
            merged.append(event)
    print(f"Collected source events: total={len(merged)}")
    return merged


def format_time(dt):
    hour = dt.hour % 12 or 12
    suffix = "AM" if dt.hour < 12 else "PM"
    if dt.minute == 0:
        return f"{hour} {suffix}"
    return f"{hour}:{dt.minute:02d} {suffix}"


def occurrence_sort_key(item):
    return (
        item["dt"].date().isoformat(),
        item["all_day"],
        item["dt"].hour,
        item["dt"].minute,
        item["summary"].casefold(),
        item["type"],
    )


def dedupe_occurrences(items):
    deduped = {}
    for item in items:
        key = (
            item["summary"],
            item["type"],
            item["all_day"],
            item["dt"].isoformat(),
        )
        deduped[key] = item
    return sorted(deduped.values(), key=occurrence_sort_key)


def build_week_data(source_events, week, label):
    override_keys = build_override_keys(source_events)
    occurrences = []
    for event in source_events:
        for item in expand_event(event, week, override_keys):
            item["type"] = event["type"]
            occurrences.append(item)

    ordered = dedupe_occurrences(occurrences)
    days = []
    for index in range(7):
        day_date = week["start"].date() + timedelta(days=index)
        day_items = [item for item in ordered if item["dt"].date() == day_date]
        groups = []
        grouped = {}
        for item in day_items:
            group_key = (
                (
                    (0, 0, 0, "ALL_DAY"),
                    "ALL DAY",
                )
                if item["all_day"]
                else (
                    (
                        1,
                        item["dt"].hour,
                        item["dt"].minute,
                        f'{item["dt"].hour:02d}:{item["dt"].minute:02d}',
                    ),
                    format_time(item["dt"]),
                )
            )
            grouped.setdefault(group_key, []).append(item)

        for group_key in sorted(grouped.keys()):
            events = [
                {
                    "summary": event["summary"],
                    "type": event["type"],
                    "all_day": event["all_day"],
                    "starts_at": event["dt"].isoformat(),
                }
                for event in sorted(
                    grouped[group_key],
                    key=lambda event: (event["summary"].casefold(), event["type"]),
                )
            ]
            groups.append(
                {
                    "time_sort_key": group_key[0][3],
                    "time_label": group_key[1],
                    "all_day": group_key[0][3] == "ALL_DAY",
                    "events": events,
                }
            )

        days.append(
            {
                "date": day_date.isoformat(),
                "weekday": DAY_ABBR[index],
                "groups": groups,
            }
        )

    return {
        "label": label,
        "start": week["start"].date().isoformat(),
        "end": week["end"].date().isoformat(),
        "event_count": len(ordered),
        "days": days,
    }


def build_week_filename(week):
    return f'week-{week["start"].strftime("%y%m%d")}.json'


def build_image_filename(week):
    return (
        "schedule0.png"
        if week["start"].date() <= datetime.now(DENVER).date() <= week["end"].date()
        else "schedule1.png"
    )


def build_manifest_entry(
    label, week, filename, data_filename, alias=None, event_count=0
):
    return {
        "label": label,
        "start": week["start"].date().isoformat(),
        "end": week["end"].date().isoformat(),
        "filename": filename,
        "data_filename": data_filename,
        "alias": alias,
        "event_count": event_count,
    }


def build_manifest(current_week, next_week, current_data, next_data):
    alias_targets_next_week = datetime.now(DENVER).weekday() >= 5
    return {
        "current_week": build_manifest_entry(
            "This Week",
            current_week,
            build_image_filename(current_week),
            build_week_filename(current_week),
            alias=None if alias_targets_next_week else "schedule.png",
            event_count=current_data["event_count"],
        ),
        "next_week": build_manifest_entry(
            "Next Week",
            next_week,
            build_image_filename(next_week),
            build_week_filename(next_week),
            alias="schedule.png" if alias_targets_next_week else None,
            event_count=next_data["event_count"],
        ),
    }


def json_bytes(payload):
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    source_events = collect_events()
    today = datetime.now(DENVER).date()

    current_week = get_week_range(today, 0)
    next_week = get_week_range(today, 1)

    current_data = build_week_data(source_events, current_week, "This Week")
    next_data = build_week_data(source_events, next_week, "Next Week")

    current_data_path = OUTPUT_DIR / build_week_filename(current_week)
    next_data_path = OUTPUT_DIR / build_week_filename(next_week)
    manifest_path = OUTPUT_DIR / "manifest.json"

    print(
        "Prepared canonical schedule data: "
        f'current_week={current_data["start"]}..{current_data["end"]} current_events={current_data["event_count"]} '
        f'next_week={next_data["start"]}..{next_data["end"]} next_events={next_data["event_count"]}'
    )

    current_changed = write_if_changed(
        current_data_path,
        json_bytes(current_data),
        "This Week Data",
    )
    next_changed = write_if_changed(
        next_data_path,
        json_bytes(next_data),
        "Next Week Data",
    )

    remove_stale_outputs("week-*.json", [current_data_path, next_data_path])

    manifest = build_manifest(current_week, next_week, current_data, next_data)
    manifest_changed = write_if_changed(
        manifest_path,
        json_bytes(manifest),
        "Manifest",
    )

    print(
        "Data summary: "
        f"current_changed={current_changed} next_changed={next_changed} manifest_changed={manifest_changed}"
    )


if __name__ == "__main__":
    main()
