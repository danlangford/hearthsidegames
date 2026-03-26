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

SOCIAL_LAYOUT = {
    "name": "social",
    "width": 1080,
    "height": 1350,
    "show_logo": True,
    "show_brand": True,
    "show_address": True,
    "logo_size": 72,
    "header_meta_y": 126,
    "header_label_y": 174,
    "header_range_y": 228,
    "legend_y": 272,
    "row_top": 318,
    "footer_top": 1290,
    "left_pad": 48,
    "right_pad": 48,
    "day_x": 56,
    "event_x": 242,
    "event_title_x": 424,
    "divider_left": 48,
    "divider_right": 48,
    "fonts": {
        "title": 48,
        "subtitle": 30,
        "day": 28,
        "date": 20,
        "time": 20,
        "event": 22,
        "meta": 17,
        "no_events": 22,
        "brand": 21,
    },
}

TV_LAYOUT = {
    "name": "tv",
    "width": 960,
    "height": 1080,
    "show_logo": False,
    "show_brand": False,
    "show_address": False,
    "show_store_name": False,
    "header_label_y": 26,
    "header_range_y": 98,
    "legend_y": 144,
    "row_top": 188,
    "footer_top": 1048,
    "left_pad": 40,
    "right_pad": 40,
    "day_x": 44,
    "event_x": 196,
    "event_title_x": 328,
    "divider_left": 36,
    "divider_right": 36,
    "day_pad_top": 12,
    "day_pad_bottom": 18,
    "event_pad_top": 14,
    "event_gap": 24,
    "empty_day_height": 76,
    "tracking": {
        "title": -0.8,
        "subtitle": -0.3,
        "meta": -2.4,
        "day": -2.4,
        "date": -2.4,
        "time": -2.4,
        "event": -2.4,
    },
    "fonts": {
        "title": 60,
        "subtitle": 34,
        "day": 35,
        "date": 25,
        "time": 24,
        "event": 29,
        "meta": 18,
        "no_events": 28,
        "brand": 20,
    },
}


def load_font(size):
    return ImageFont.truetype(str(FONT_PATH), size=size)


def build_fonts(layout):
    return {name: load_font(size) for name, size in layout["fonts"].items()}


def make_background(width, height):
    img = Image.new("RGBA", (width, height), "#F4F0EC")
    draw = ImageDraw.Draw(img)
    top = (244, 240, 236)
    bottom = (235, 228, 220)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line((0, y, width, y), fill=color)
    return img


def fit_text(draw, text, font, max_width):
    value = text
    while value and draw.textlength(value, font=font) > max_width:
        value = value[:-2].rstrip() + "…"
    return value or text


def text_width(draw, text, font, tracking=0):
    if not text:
        return 0
    if not tracking:
        return draw.textlength(text, font=font)
    width = 0
    for index, char in enumerate(text):
        width += draw.textlength(char, font=font)
        if index < len(text) - 1:
            width += tracking
    return width


def fit_text_tracking(draw, text, font, max_width, tracking=0):
    value = text
    while value and text_width(draw, value, font, tracking) > max_width:
        value = value[:-2].rstrip() + "…"
    return value or text


def draw_text_tracking(draw, position, text, font, fill, tracking=0, anchor=None):
    if not tracking:
        draw.text(position, text, fill=fill, font=font, anchor=anchor)
        return

    x, y = position
    if anchor == "ma":
        x -= text_width(draw, text, font, tracking) / 2
    elif anchor == "ra":
        x -= text_width(draw, text, font, tracking)

    cursor = x
    for char in text:
        draw.text((cursor, y), char, fill=fill, font=font)
        cursor += draw.textlength(char, font=font) + tracking


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


def get_event_line_height(event_count, layout_name):
    if layout_name == "tv":
        if event_count <= 1:
            return 34
        if event_count == 2:
            return 32
        if event_count == 3:
            return 29
        return 27

    if event_count <= 1:
        return 27
    if event_count == 2:
        return 24
    if event_count == 3:
        return 22
    return 19


def draw_header(image, draw, payload, layout, fonts):
    width = layout["width"]
    start_date = date.fromisoformat(payload["days"][0]["date"])
    end_date = date.fromisoformat(payload["days"][-1]["date"])

    tracking = layout.get("tracking", {})

    if layout.get("show_logo") and LOGO_PATH.exists():
        logo_size = layout["logo_size"]
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((logo_size, logo_size))
        image.alpha_composite(logo, ((width - logo_size) // 2, 28))

    if layout.get("show_store_name", True):
        draw_text_tracking(
            draw,
            (width / 2, layout["header_meta_y"]),
            "HEARTHSIDE GAMES",
            fill=(108, 96, 88),
            font=fonts["meta"],
            anchor="ma",
            tracking=tracking.get("meta", 0),
        )
    draw_text_tracking(
        draw,
        (width / 2, layout["header_label_y"]),
        payload["label"].upper(),
        fill=(191, 87, 0),
        font=fonts["title"],
        anchor="ma",
        tracking=tracking.get("title", 0),
    )
    draw_text_tracking(
        draw,
        (width / 2, layout["header_range_y"]),
        f"{format_range(start_date, end_date)}, {start_date.year}",
        fill=(77, 71, 64),
        font=fonts["subtitle"],
        anchor="ma",
        tracking=tracking.get("subtitle", 0),
    )

    legend_y = layout["legend_y"]
    draw.ellipse((width / 2 - 122, legend_y, width / 2 - 112, legend_y + 10), fill=(191, 87, 0))
    draw_text_tracking(
        draw,
        (width / 2 - 96, legend_y - 4),
        "Leagues",
        fill=(77, 71, 64),
        font=fonts["meta"],
        tracking=tracking.get("meta", 0),
    )
    draw.rectangle((width / 2 + 10, legend_y, width / 2 + 20, legend_y + 10), fill=(74, 93, 104))
    draw_text_tracking(
        draw,
        (width / 2 + 36, legend_y - 4),
        "Spotlight",
        fill=(77, 71, 64),
        font=fonts["meta"],
        tracking=tracking.get("meta", 0),
    )


def draw_footer(draw, layout, fonts):
    if not layout.get("show_brand") and not layout.get("show_address"):
        return

    width = layout["width"]
    footer_top = layout["footer_top"]

    if layout.get("show_brand"):
        draw.text(
            (width / 2, footer_top - 18),
            "hearthside.games",
            fill=(90, 84, 78),
            font=fonts["brand"],
            anchor="ma",
        )

    if layout.get("show_address"):
        draw.text(
            (width / 2, footer_top + 6),
            "6802 S Redwood Rd · West Jordan, UT",
            fill=(130, 122, 114),
            font=fonts["meta"],
            anchor="ma",
        )


def draw_schedule_rows(draw, payload, layout, fonts):
    width = layout["width"]
    row_top = layout["row_top"]
    footer_top = layout["footer_top"]
    by_day = [flatten_day_events(day) for day in payload["days"]]
    if layout["name"] == "tv":
        tracking = layout.get("tracking", {})
        y = row_top
        for index, day_events in enumerate(by_day):
            day = payload["days"][index]
            day_date = date.fromisoformat(day["date"])
            line_height = get_event_line_height(len(day_events), layout["name"])
            text_block_height = (
                layout["empty_day_height"]
                if not day_events
                else layout["event_pad_top"] + len(day_events) * line_height
            )
            row_height = max(
                78,
                layout["day_pad_top"] + text_block_height + layout["day_pad_bottom"],
            )
            next_y = y + row_height
            if index > 0:
                draw.line(
                    (layout["divider_left"], y, width - layout["divider_right"], y),
                    fill=(210, 205, 198),
                    width=1,
                )

            draw_text_tracking(
                draw,
                (layout["day_x"], y + layout["day_pad_top"]),
                day["weekday"],
                fill=(160, 69, 0),
                font=fonts["day"],
                tracking=tracking.get("day", 0),
            )
            draw_text_tracking(
                draw,
                (layout["day_x"], y + layout["day_pad_top"] + 38),
                f"{MONTH_ABBR[day_date.month - 1]} {day_date.day}",
                fill=(92, 86, 79),
                font=fonts["date"],
                tracking=tracking.get("date", 0),
            )

            if not day_events:
                draw.text(
                    (layout["event_x"], y + 30),
                    "No events",
                    fill=(156, 150, 142),
                    font=fonts["no_events"],
                )
            else:
                previous_time_label = None
                for row, event in enumerate(day_events):
                    ey = y + layout["event_pad_top"] + row * line_height
                    is_special = event["type"] == "spotlight"
                    dot_color = (74, 93, 104) if is_special else (191, 87, 0)
                    name_color = (74, 93, 104) if is_special else (27, 27, 27)
                    time_color = (116, 108, 100) if not is_special else (96, 108, 118)
                    show_time = event["time_label"] != previous_time_label
                    if show_time:
                        draw_text_tracking(
                            draw,
                            (layout["event_x"], ey),
                            event["time_label"],
                            fill=time_color,
                            font=fonts["time"],
                            tracking=tracking.get("time", 0),
                        )
                    marker_x = layout["event_title_x"]
                    marker_top = ey + 10
                    marker_bottom = marker_top + 9
                    if is_special:
                        draw.rectangle((marker_x, marker_top, marker_x + 9, marker_bottom), fill=dot_color)
                    else:
                        draw.ellipse((marker_x, marker_top, marker_x + 9, marker_bottom), fill=dot_color)
                    title = fit_text_tracking(
                        draw,
                        event["summary"],
                        fonts["event"],
                        width - marker_x - layout["right_pad"] - 22,
                        tracking.get("event", 0),
                    )
                    draw_text_tracking(
                        draw,
                        (marker_x + 18, ey),
                        title,
                        fill=name_color,
                        font=fonts["event"],
                        tracking=tracking.get("event", 0),
                    )
                    previous_time_label = event["time_label"]

            y = next_y
        return

    row_height = (footer_top - row_top) // len(payload["days"])

    y = row_top
    for index, day_events in enumerate(by_day):
        day = payload["days"][index]
        day_date = date.fromisoformat(day["date"])
        if index > 0:
            draw.line(
                (layout["divider_left"], y, width - layout["divider_right"], y),
                fill=(210, 205, 198),
                width=1,
            )

        draw.text((layout["day_x"], y + 10), day["weekday"], fill=(191, 87, 0), font=fonts["day"])
        draw.text(
            (layout["day_x"], y + 46),
            f"{MONTH_ABBR[day_date.month - 1]} {day_date.day}",
            fill=(122, 114, 104),
            font=fonts["date"],
        )

        if not day_events:
            draw.text(
                (layout["event_x"], y + 28),
                "No events",
                fill=(156, 150, 142),
                font=fonts["no_events"],
            )
        else:
            line_height = get_event_line_height(len(day_events), layout["name"])
            for row, event in enumerate(day_events):
                ey = y + 10 + row * line_height
                is_special = event["type"] == "spotlight"
                dot_color = (74, 93, 104) if is_special else (191, 87, 0)
                name_color = (74, 93, 104) if is_special else (27, 27, 27)
                time_color = (116, 108, 100) if not is_special else (96, 108, 118)
                if is_special:
                    draw.rectangle((layout["event_x"], ey + 7, layout["event_x"] + 8, ey + 15), fill=dot_color)
                else:
                    draw.ellipse((layout["event_x"], ey + 7, layout["event_x"] + 8, ey + 15), fill=dot_color)
                draw.text(
                    (layout["event_x"] + 18, ey),
                    event["time_label"],
                    fill=time_color,
                    font=fonts["time"],
                )
                title = fit_text(
                    draw,
                    event["summary"],
                    fonts["event"],
                    width - layout["event_title_x"] - layout["right_pad"],
                )
                draw.text((layout["event_title_x"], ey), title, fill=name_color, font=fonts["event"])

        y += row_height


def draw_schedule_image(output_path, payload, layout):
    image = make_background(layout["width"], layout["height"])
    draw = ImageDraw.Draw(image)
    fonts = build_fonts(layout)

    draw_header(image, draw, payload, layout, fonts)
    draw_schedule_rows(draw, payload, layout, fonts)
    draw_footer(draw, layout, fonts)

    save_kwargs = {"format": "PNG"} if isinstance(output_path, io.BytesIO) else {}
    image.convert("RGB").save(output_path, **save_kwargs)


def render_schedule_image(payload, layout):
    buffer = io.BytesIO()
    draw_schedule_image(buffer, payload, layout)
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
    tv_path = OUTPUT_DIR / "scheduletv.png"
    alias_source_payload = (
        next_payload
        if manifest["next_week"].get("alias") == "schedule.png"
        else current_payload
    )

    current_changed = write_if_changed(
        current_image_path,
        render_schedule_image(current_payload, SOCIAL_LAYOUT),
        "This Week Image",
    )
    next_changed = write_if_changed(
        next_image_path,
        render_schedule_image(next_payload, SOCIAL_LAYOUT),
        "Next Week Image",
    )
    alias_changed = write_if_changed(
        alias_path,
        render_schedule_image(alias_source_payload, SOCIAL_LAYOUT),
        "Generic Alias",
    )
    tv_changed = write_if_changed(
        tv_path,
        render_schedule_image(alias_source_payload, TV_LAYOUT),
        "TV Schedule",
    )

    remove_stale_outputs(
        "schedule*.png", [current_image_path, next_image_path, alias_path, tv_path]
    )

    print(
        "Render summary: "
        f"current_changed={current_changed} next_changed={next_changed} "
        f"alias_changed={alias_changed} tv_changed={tv_changed}"
    )


if __name__ == "__main__":
    main()
