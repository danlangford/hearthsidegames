#!/usr/bin/env python3

import io
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from schedule_common import (
    OUTPUT_DIR,
    load_week_payload,
    remove_stale_outputs,
    write_if_changed,
)

ROOT = Path(__file__).resolve().parent.parent
MONTH_ABBR = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

FONT_PATH = ROOT / "pages" / "HearthLexendExaVF.ttf"
LOGO_PATH = ROOT / "pages" / "favicon.png"

W = 960
H = 1080


def load_font(size):
    return ImageFont.truetype(str(FONT_PATH), size=size)


FONT_TITLE = load_font(43)
FONT_SUBTITLE = load_font(26)
FONT_DAY = load_font(26)
FONT_DATE = load_font(18)
FONT_TIME = load_font(18)
FONT_EVENT = load_font(19)
FONT_META = load_font(16)
FONT_NO_EVENTS = load_font(19)
FONT_BRAND = load_font(19)


def make_background():
    img = Image.new("RGBA", (W, H), "#F4F0EC")
    draw = ImageDraw.Draw(img)
    top = (244, 240, 236)
    bottom = (235, 228, 220)
    for y in range(H):
        ratio = y / max(H - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line((0, y, W, y), fill=color)
    return img


def fit_text(draw, text, font, max_width):
    value = text
    while value and draw.textlength(value, font=font) > max_width:
        value = value[:-2].rstrip() + "…"
    return value or text


def format_range(start_date, end_date):
    if start_date.month == end_date.month:
        return f"{MONTH_ABBR[start_date.month - 1]} {start_date.day} – {end_date.day}"
    return f"{MONTH_ABBR[start_date.month - 1]} {start_date.day} – {MONTH_ABBR[end_date.month - 1]} {end_date.day}"


def flatten_day_events(day):
    flattened = []
    for group in day["groups"]:
        for event in group["events"]:
            flattened.append(
                {
                    "time_label": group["time_label"],
                    "all_day": group["all_day"],
                    "summary": event["summary"],
                    "type": event["type"],
                }
            )
    return flattened


def get_event_line_height(event_count):
    if event_count <= 1:
        return 24
    if event_count == 2:
        return 22
    if event_count == 3:
        return 19
    return 17


def draw_schedule_image(output_path, payload):
    by_day = [flatten_day_events(day) for day in payload["days"]]
    image = make_background()
    draw = ImageDraw.Draw(image)
    row_top = 258
    footer_top = H - 56
    row_height = (footer_top - row_top) // len(payload["days"])
    day_x = 44
    event_x = 194
    event_title_x = 344

    if LOGO_PATH.exists():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((60, 60))
        image.alpha_composite(logo, ((W - 60) // 2, 30))

    start_date = date.fromisoformat(payload["days"][0]["date"])
    end_date = date.fromisoformat(payload["days"][-1]["date"])
    draw.text(
        (W / 2, 110),
        "HEARTHSIDE GAMES",
        fill=(108, 96, 88),
        font=FONT_META,
        anchor="ma",
    )
    draw.text(
        (W / 2, 150),
        payload["label"].upper(),
        fill=(191, 87, 0),
        font=FONT_TITLE,
        anchor="ma",
    )
    draw.text(
        (W / 2, 194),
        f"{format_range(start_date, end_date)}, {start_date.year}",
        fill=(77, 71, 64),
        font=FONT_SUBTITLE,
        anchor="ma",
    )
    legend_y = 230
    draw.ellipse((W / 2 - 122, legend_y, W / 2 - 112, legend_y + 10), fill=(191, 87, 0))
    draw.text((W / 2 - 96, legend_y - 4), "Weekly", fill=(77, 71, 64), font=FONT_META)
    draw.ellipse((W / 2 + 10, legend_y, W / 2 + 20, legend_y + 10), fill=(74, 93, 104))
    draw.text((W / 2 + 36, legend_y - 4), "Special", fill=(77, 71, 64), font=FONT_META)

    y = row_top
    for index, day_events in enumerate(by_day):
        day = payload["days"][index]
        day_date = date.fromisoformat(day["date"])
        if index > 0:
            draw.line((40, y, W - 40, y), fill=(210, 205, 198), width=1)

        draw.text((day_x, y + 10), day["weekday"], fill=(191, 87, 0), font=FONT_DAY)
        draw.text(
            (day_x, y + 44),
            f"{MONTH_ABBR[day_date.month - 1]} {day_date.day}",
            fill=(122, 114, 104),
            font=FONT_DATE,
        )

        if not day_events:
            draw.text(
                (event_x, y + 26), "No events", fill=(156, 150, 142), font=FONT_NO_EVENTS
            )
        else:
            line_height = get_event_line_height(len(day_events))
            for row, event in enumerate(day_events):
                ey = y + 10 + row * line_height
                is_special = event["type"] == "spotlight"
                dot_color = (74, 93, 104) if is_special else (191, 87, 0)
                name_color = (74, 93, 104) if is_special else (27, 27, 27)
                time_color = (116, 108, 100) if not is_special else (96, 108, 118)
                draw.ellipse((event_x, ey + 7, event_x + 8, ey + 15), fill=dot_color)
                draw.text(
                    (event_x + 18, ey),
                    event["time_label"],
                    fill=time_color,
                    font=FONT_TIME,
                )
                title = fit_text(draw, event["summary"], FONT_EVENT, W - event_title_x - 40)
                draw.text((event_title_x, ey), title, fill=name_color, font=FONT_EVENT)

        y += row_height

    draw.text(
        (W / 2, footer_top - 18),
        "hearthside.games",
        fill=(90, 84, 78),
        font=FONT_BRAND,
        anchor="ma",
    )
    draw.text(
        (W / 2, footer_top + 6),
        "6802 S Redwood Rd · West Jordan, UT",
        fill=(130, 122, 114),
        font=FONT_META,
        anchor="ma",
    )

    save_kwargs = {"format": "PNG"} if isinstance(output_path, io.BytesIO) else {}
    image.convert("RGB").save(output_path, **save_kwargs)


def render_schedule_image(payload):
    buffer = io.BytesIO()
    draw_schedule_image(buffer, payload)
    return buffer.getvalue()


def main():
    manifest = load_week_payload(OUTPUT_DIR / "manifest.json")

    current_payload = load_week_payload(
        OUTPUT_DIR / manifest["current_week"]["data_filename"]
    )
    next_payload = load_week_payload(
        OUTPUT_DIR / manifest["next_week"]["data_filename"]
    )

    current_image_path = OUTPUT_DIR / manifest["current_week"]["filename"]
    next_image_path = OUTPUT_DIR / manifest["next_week"]["filename"]
    alias_path = OUTPUT_DIR / "schedule.png"
    alias_source_payload = (
        next_payload
        if manifest["next_week"].get("alias") == "schedule.png"
        else current_payload
    )

    current_changed = write_if_changed(
        current_image_path,
        render_schedule_image(current_payload),
        "This Week Image",
    )
    next_changed = write_if_changed(
        next_image_path,
        render_schedule_image(next_payload),
        "Next Week Image",
    )
    alias_changed = write_if_changed(
        alias_path,
        render_schedule_image(alias_source_payload),
        "Generic Alias",
    )

    remove_stale_outputs(
        "schedule*.png", [current_image_path, next_image_path, alias_path]
    )

    print(
        "Render summary: "
        f"current_changed={current_changed} next_changed={next_changed} alias_changed={alias_changed}"
    )


if __name__ == "__main__":
    main()
