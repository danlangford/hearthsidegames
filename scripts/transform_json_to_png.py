#!/usr/bin/env python3

import io
import os
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

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
# Raster of pages/flame-deck-compat.svg (black on transparent) for the image header.
LOGO_PATH = ROOT / "pages" / "flame-deck-logo.png"

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
    # Each day row shows its own date, and spotlight titles are set in a heavier
    # weight instead of relying on a legend, so the TV header is just the title.
    "show_range": False,
    "show_legend": False,
    "header_label_y": 26,
    "row_top": 100,
    "footer_top": 1056,
    "left_pad": 40,
    "right_pad": 40,
    "day_x": 44,
    "event_x": 196,
    "event_title_x": 328,
    "divider_left": 36,
    "divider_right": 36,
    "day_pad_top": 10,
    "day_pad_bottom": 12,
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
        "event_spotlight": (29, 600),
        "meta": 18,
        "no_events": 28,
        "brand": 20,
    },
}


def load_font(size, weight=None):
    # Pin the basic layout engine so brand text renders the same whether or not
    # raqm is available (raqm is only needed for the emoji font).
    font = ImageFont.truetype(str(FONT_PATH), size=size, layout_engine=ImageFont.Layout.BASIC)
    if weight is not None:
        font.set_variation_by_axes([weight])  # variable font: single wght axis, 100-900
    return font


# --- Emoji support -----------------------------------------------------------
#
# The brand font has no emoji glyphs and Pillow does no font fallback, so text is
# split into plain runs and emoji clusters. Emoji are drawn from a color bitmap
# font (Noto Color Emoji on CI, Apple Color Emoji on macOS), scaled to the line,
# and pasted onto the image.

EMOJI_FONT_CANDIDATES = [
    os.environ.get("EMOJI_FONT_PATH", ""),
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
]
# Color bitmap fonts only load at the sizes of their embedded strikes.
EMOJI_FONT_SIZES = (109, 160, 96, 64)
EMOJI_SCALE = 1.0  # emoji box size relative to the font size
EMOJI_GAP_RATIO = 0.08  # extra breathing room on each side of an emoji

ZWJ = "‍"
VS16 = "️"
VS15 = "︎"
KEYCAP = "⃣"


def _is_regional_indicator(char):
    return 0x1F1E6 <= ord(char) <= 0x1F1FF


def _is_emoji_modifier(char):
    return 0x1F3FB <= ord(char) <= 0x1F3FF


def _is_tag(char):
    return 0xE0020 <= ord(char) <= 0xE007F


def _is_pictographic(char):
    cp = ord(char)
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x2300 <= cp <= 0x23FF
        or 0x2B00 <= cp <= 0x2BFF
        or 0x2190 <= cp <= 0x21FF
        or 0x25A0 <= cp <= 0x25FF
        or 0x2900 <= cp <= 0x297F
        or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299)
    )


def split_emoji_runs(text):
    """Split text into [(is_emoji, segment)] keeping emoji sequences intact."""
    runs = []
    plain = []
    i = 0
    n = len(text)

    def flush_plain():
        if plain:
            runs.append((False, "".join(plain)))
            plain.clear()

    while i < n:
        char = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        # Keycaps: 1️⃣ #️⃣ *️⃣
        if char in "0123456789#*" and (nxt == KEYCAP or (nxt == VS16 and text[i + 2 : i + 3] == KEYCAP)):
            end = i + (2 if nxt == KEYCAP else 3)
            flush_plain()
            runs.append((True, text[i:end]))
            i = end
            continue

        # Flags: pairs of regional indicators
        if _is_regional_indicator(char):
            end = i + 2 if nxt and _is_regional_indicator(nxt) else i + 1
            flush_plain()
            runs.append((True, text[i:end]))
            i = end
            continue

        is_text_symbol = nxt == VS15
        is_emoji_start = not is_text_symbol and (
            0x1F000 <= ord(char) <= 0x1FAFF or (_is_pictographic(char) and (nxt == VS16 or not _brand_has_glyph(char)))
        )
        if not is_emoji_start:
            plain.append(char)
            i += 1
            if is_text_symbol:
                i += 1  # drop VS15; the brand font draws the text form
            continue

        end = i + 1
        while end < n:
            c = text[end]
            if c == VS16 or _is_emoji_modifier(c) or _is_tag(c) or c == KEYCAP:
                end += 1
            elif c == ZWJ and end + 1 < n:
                end += 2
            else:
                break
        flush_plain()
        runs.append((True, text[i:end]))
        i = end

    flush_plain()
    return runs


def split_clusters(text):
    """Split text into user-visible units (characters, with emoji kept whole)."""
    clusters = []
    for is_emoji, segment in split_emoji_runs(text):
        if is_emoji:
            clusters.append(segment)
        else:
            clusters.extend(segment)
    return clusters


_glyph_cache = {}


def _render_probe(char):
    font = load_font(32)
    probe = Image.new("L", (64, 64), 0)
    ImageDraw.Draw(probe).text((8, 8), char, fill=255, font=font)
    return probe.tobytes()


def _brand_has_glyph(char):
    """True when the brand font draws something other than its missing-glyph box."""
    if char not in _glyph_cache:
        if "missing" not in _glyph_cache:
            _glyph_cache["missing"] = _render_probe("\U0010FFFD")
        _glyph_cache[char] = _render_probe(char) != _glyph_cache["missing"]
    return _glyph_cache[char]


_emoji_font = None
_emoji_font_loaded = False


def get_emoji_font():
    global _emoji_font, _emoji_font_loaded
    if _emoji_font_loaded:
        return _emoji_font
    _emoji_font_loaded = True
    # Raqm (complex text layout) is needed to compose flags, keycaps, skin tones
    # and ZWJ sequences into single glyphs. Pillow's wheels bundle it but need
    # the system fribidi library (apt: libfribidi0, brew: fribidi).
    if features.check("raqm"):
        layout_engine = ImageFont.Layout.RAQM
    else:
        layout_engine = ImageFont.Layout.BASIC
        print(
            "WARNING: Pillow raqm layout unavailable (install fribidi); "
            "flags and multi-part emoji will not render.",
            file=sys.stderr,
        )
    for path in EMOJI_FONT_CANDIDATES:
        if not path or not Path(path).exists():
            continue
        for size in EMOJI_FONT_SIZES:
            try:
                _emoji_font = ImageFont.truetype(path, size=size, layout_engine=layout_engine)
                print(f"Using emoji font: {path} @ {size}px")
                return _emoji_font
            except OSError:
                continue
    print("WARNING: no color emoji font found; emoji will be skipped in images.", file=sys.stderr)
    return None


_emoji_image_cache = {}


def render_emoji(sequence, box_size):
    key = (sequence, box_size)
    if key in _emoji_image_cache:
        return _emoji_image_cache[key]

    font = get_emoji_font()
    result = None
    if font is not None:
        strike = font.size
        canvas = Image.new("RGBA", (strike * 3, strike * 2), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text((strike // 2, strike // 2), sequence, font=font, embedded_color=True)
        bbox = canvas.getbbox()
        if bbox:
            glyph = canvas.crop(bbox)
            scale = box_size / max(glyph.width, glyph.height, strike * 0.9)
            size = (max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale)))
            result = glyph.resize(size, Image.LANCZOS)

    _emoji_image_cache[key] = result
    return result


def emoji_advance(font):
    box = round(font.size * EMOJI_SCALE)
    gap = round(font.size * EMOJI_GAP_RATIO)
    return box, gap, box + gap * 2


def draw_emoji(draw, x, y, sequence, font):
    """Draw an emoji whose layout box starts at (x, y) as a text top-left anchor."""
    box, gap, _advance = emoji_advance(font)
    glyph = render_emoji(sequence, box)
    if glyph is None:
        return
    # Center the emoji on the cap-height band of the brand font.
    ascent, _descent = font.getmetrics()
    cap_top = font.getbbox("H")[1]
    band_mid = (cap_top + ascent) / 2
    px = round(x + gap + (box - glyph.width) / 2)
    py = round(y + band_mid - glyph.height / 2)
    # ImageDraw keeps the target image here; paste the RGBA glyph with its alpha.
    draw._image.alpha_composite(glyph, (max(px, 0), max(py, 0)))


def build_fonts(layout):
    """Each font spec is a size or a (size, weight) pair."""
    fonts = {}
    for name, spec in layout["fonts"].items():
        size, weight = spec if isinstance(spec, tuple) else (spec, None)
        fonts[name] = load_font(size, weight)
    return fonts


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
    return fit_text_tracking(draw, text, font, max_width, 0)


def has_emoji(text):
    return any(is_emoji for is_emoji, _segment in split_emoji_runs(text))


def cluster_width(draw, cluster, font, is_emoji):
    if is_emoji:
        return emoji_advance(font)[2]
    return draw.textlength(cluster, font=font)


def text_width(draw, text, font, tracking=0):
    if not text:
        return 0
    if not has_emoji(text):
        if not tracking:
            return draw.textlength(text, font=font)
        return sum(draw.textlength(char, font=font) for char in text) + tracking * (len(text) - 1)

    runs = split_emoji_runs(text)
    if not tracking:
        return sum(cluster_width(draw, segment, font, is_emoji) for is_emoji, segment in runs)
    clusters = [(is_emoji, c) for is_emoji, segment in runs for c in ([segment] if is_emoji else segment)]
    return sum(cluster_width(draw, c, font, is_emoji) for is_emoji, c in clusters) + tracking * (len(clusters) - 1)


def fit_text_tracking(draw, text, font, max_width, tracking=0):
    clusters = split_clusters(text)
    if text_width(draw, text, font, tracking) <= max_width:
        return text
    while clusters:
        clusters = clusters[:-1]
        value = "".join(clusters).rstrip() + "…"
        if text_width(draw, value, font, tracking) <= max_width:
            return value
    return text


def draw_text_tracking(draw, position, text, font, fill, tracking=0, anchor=None):
    emoji = has_emoji(text)
    if not tracking and not emoji:
        draw.text(position, text, fill=fill, font=font, anchor=anchor)
        return

    x, y = position
    if anchor == "ma":
        x -= text_width(draw, text, font, tracking) / 2
    elif anchor == "ra":
        x -= text_width(draw, text, font, tracking)

    cursor = x
    for is_emoji, segment in split_emoji_runs(text):
        if is_emoji:
            draw_emoji(draw, cursor, y, segment, font)
            cursor += cluster_width(draw, segment, font, True) + tracking
        elif not tracking:
            draw.text((cursor, y), segment, fill=fill, font=font)
            cursor += draw.textlength(segment, font=font)
        else:
            for char in segment:
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


def copy_day_with_events(day, events):
    groups = []
    event_index = 0
    for group in day["groups"]:
        group_events = []
        for _event in group["events"]:
            if event_index >= len(events):
                break
            group_events.append(
                {
                    "summary": events[event_index]["summary"],
                    "type": events[event_index]["type"],
                    "all_day": events[event_index]["all_day"],
                }
            )
            event_index += 1
        if group_events:
            groups.append({**group, "events": group_events})
        if event_index >= len(events):
            break

    return {**day, "groups": groups}


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


def get_tv_row_height(event_count, layout):
    text_block_height = (
        layout["empty_day_height"]
        if event_count == 0
        else layout["event_pad_top"] + event_count * get_event_line_height(event_count, layout["name"])
    )
    return max(
        78,
        layout["day_pad_top"] + text_block_height + layout["day_pad_bottom"],
    )


def build_visible_tv_payload(payload, layout):
    visible_days = []
    y = layout["row_top"]
    footer_top = layout["footer_top"]
    min_event_row_height = get_tv_row_height(1, layout)

    for day in payload["days"]:
        day_events = flatten_day_events(day)
        row_height = get_tv_row_height(len(day_events), layout)
        if y + row_height <= footer_top:
            visible_days.append(day)
            y += row_height
            continue

        if not day_events or y + min_event_row_height > footer_top:
            break

        visible_events = []
        for event_count in range(1, len(day_events) + 1):
            next_height = get_tv_row_height(event_count, layout)
            if y + next_height > footer_top:
                break
            visible_events = day_events[:event_count]

        if visible_events:
            visible_days.append(copy_day_with_events(day, visible_events))
        break

    if not visible_days:
        return payload

    return {
        **payload,
        "end": visible_days[-1]["date"],
        "event_count": sum(len(flatten_day_events(day)) for day in visible_days),
        "days": visible_days,
    }


def draw_header(image, draw, payload, layout, fonts):
    width = layout["width"]
    start_date = date.fromisoformat(payload["days"][0]["date"])
    end_date = date.fromisoformat(payload["days"][-1]["date"])

    tracking = layout.get("tracking", {})

    if layout.get("show_logo") and LOGO_PATH.exists():
        logo_size = layout["logo_size"]
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
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
    if layout.get("show_range", True):
        draw_text_tracking(
            draw,
            (width / 2, layout["header_range_y"]),
            f"{format_range(start_date, end_date)}, {start_date.year}",
            fill=(77, 71, 64),
            font=fonts["subtitle"],
            anchor="ma",
            tracking=tracking.get("subtitle", 0),
        )

    if not layout.get("show_legend", True):
        return

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
                    title_font = fonts.get("event_spotlight", fonts["event"]) if is_special else fonts["event"]
                    title = fit_text_tracking(
                        draw,
                        event["summary"],
                        title_font,
                        width - marker_x - layout["right_pad"] - 22,
                        tracking.get("event", 0),
                    )
                    draw_text_tracking(
                        draw,
                        (marker_x + 18, ey),
                        title,
                        fill=name_color,
                        font=title_font,
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
                draw_text_tracking(draw, (layout["event_title_x"], ey), title, fill=name_color, font=fonts["event"])

        y += row_height


def draw_schedule_image(output_path, payload, layout):
    if layout["name"] == "tv":
        payload = build_visible_tv_payload(payload, layout)

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
    tv_only = "--tv-only" in sys.argv[1:]

    tv_path = OUTPUT_DIR / "scheduletv.png"
    tv_payload = load_week_payload(OUTPUT_DIR / "tv.json")

    if tv_only:
        tv_changed = write_if_changed(
            tv_path,
            render_schedule_image(tv_payload, TV_LAYOUT),
            "TV Schedule",
        )
        print(f"Render summary: tv_changed={tv_changed}")
        return

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
        render_schedule_image(tv_payload, TV_LAYOUT),
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
