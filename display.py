"""The signal renderer: 280x192, grayscale only, at most 16 luminance values."""
from __future__ import annotations

import math
import textwrap
import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from render import FONT, text

WIDTH, HEIGHT = 280, 192
PIXEL_ASPECT = (4 / 3) / (WIDTH / HEIGHT)
ART_SIZE = (160, 146)  # 160 * pixel aspect ~= 146; square on a 4:3 CRT.


def ascii_text(value: str) -> str:
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    return unicodedata.normalize("NFKD", value).encode("ascii", "replace").decode().upper()


def line(draw, xy, value, shade=14, limit=13, scale=1):
    value = ascii_text(str(value))
    if len(value) > limit:
        value = value[:limit - 2] + ".."
    text(draw, xy, value, shade, scale)


def title_lines(value: str) -> list[str]:
    rows = textwrap.wrap(ascii_text(value), 13, break_long_words=True, break_on_hyphens=False)
    if len(rows) > 5:
        rows[4] = rows[4][:11] + ".."
    return (rows or ["UNTITLED"])[:5]


def timecode(ms: int, *, hours: bool = False) -> str:
    seconds = max(0, int(ms) // 1000)
    if hours and seconds >= 3600:
        return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


@lru_cache(maxsize=12)
def demo_art(seed: int = 0) -> Image.Image:
    """Original, procedural landscape artwork. No external assets needed."""
    w, h = ART_SIZE
    art = Image.new("L", (w, h))
    p = art.load()
    # Original sky, striped moon, and ridgelines with smooth tonal regions.
    for y in range(h):
        for x in range(w):
            tone = 88 + 52 * y / h
            cx = round(w * .65) - seed * 15
            if (x - cx) ** 2 / 1.2 + (y - 43) ** 2 < 26 ** 2:
                tone = 212 if y % 6 < 4 else 164
            for ridge in range(4):
                edge = 73 + ridge * 18 + math.sin(x / (23 + ridge * 3) + ridge * 2 + seed) * 12
                if y > edge:
                    tone = 27 + ridge * 23 + (y - edge) / 3
            p[x, y] = max(0, min(255, round(tone)))
    return art


@lru_cache(maxsize=12)
def local_art(path: str, modified: int) -> Image.Image:
    with Image.open(path) as original:
        return prepare_art(original)


def prepare_art(original: Image.Image) -> Image.Image:
    """Preserve the whole cover, then compensate for the CRT's pixel aspect."""
    square_side = ART_SIZE[1]
    source = ImageOps.exif_transpose(original).convert("L")
    contained = ImageOps.contain(source, (square_side, square_side), method=Image.Resampling.LANCZOS)
    square = Image.new("L", (square_side, square_side), 0)
    square.paste(contained, ((square_side - contained.width) // 2, (square_side - contained.height) // 2))
    return square.resize(ART_SIZE, Image.Resampling.LANCZOS)


@lru_cache(maxsize=1)
def spotify_mark() -> Image.Image:
    """Supersampled curves, softened into the existing 16-shade signal palette."""
    scale = 16
    mark = Image.new("L", (24 * scale, 24 * scale), 0)
    draw = ImageDraw.Draw(mark)
    draw.ellipse((0, 0, 24 * scale - 1, 24 * scale - 1), fill=255)
    curves = (
        (((4.7, 8.0), (9.0, 6.0), (15.4, 6.6), (19.3, 9.0)), 2.0),
        (((5.5, 11.9), (9.6, 10.2), (14.9, 10.9), (18.2, 12.9)), 1.7),
        (((6.2, 15.5), (9.8, 14.1), (13.5, 14.6), (16.9, 16.5)), 1.5),
    )
    for control, thickness in curves:
        points = []
        for step in range(129):
            t = step / 128
            weights = ((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3)
            points.append(tuple(round(scale * sum(weights[i] * control[i][axis] for i in range(4)))
                                for axis in (0, 1)))
        width = round(thickness * scale)
        draw.line(points, fill=0, width=width, joint="curve")
        radius = width / 2
        for x, y in (points[0], points[-1]):
            draw.ellipse((round(x-radius), round(y-radius), round(x+radius), round(y+radius)), fill=0)
    # Wide signal pixels become a round 22x22 physical mark on the 4:3 CRT.
    mark = mark.resize((24, 22), Image.Resampling.LANCZOS)
    return mark.point(lambda value: max(0, min(15, round(value * 15 / 255))))


@lru_cache(maxsize=3)
def playback_icon(kind: str) -> Image.Image:
    """Antialias transport diagonals while retaining the signal's fixed shades."""
    scale = 8
    icon = Image.new("L", (17 * scale, 18 * scale), 0)
    draw = ImageDraw.Draw(icon)
    if kind == "play":
        vertices, peak = ((4, 2), (4, 16), (14, 9)), 15
    elif kind in ("previous", "next"):
        draw.rectangle((2 * scale, 3 * scale, 4 * scale, 15 * scale), fill=255)
        vertices, peak = ((12, 3), (12, 15), (5, 9)), 11
    else:
        raise ValueError("Unknown transport icon")
    draw.polygon([(x * scale, y * scale) for x, y in vertices], fill=255)
    icon = icon.resize((17, 18), Image.Resampling.LANCZOS)
    if kind == "next":
        icon = ImageOps.mirror(icon)
    return icon.point(lambda value: max(0, min(peak, round(value * peak / 255))))


@lru_cache(maxsize=1)
def wordmark() -> Image.Image:
    """Mixed-case Spcrtify, with a wider, brighter crt in the native raster."""
    glyphs = {
        "S": FONT["S"],
        "p": ("00000", "00000", "11110", "10001", "11110", "10000", "10000"),
        "c": ("00000", "00000", "01111", "10000", "10000", "10000", "01111"),
        "r": ("00000", "00000", "10110", "11001", "10000", "10000", "10000"),
        "t": ("00100", "00100", "11111", "00100", "00100", "00100", "00011"),
        "i": ("00100", "00000", "01100", "00100", "00100", "00100", "01110"),
        "f": ("00011", "00100", "00100", "01110", "00100", "00100", "00100"),
        "y": ("00000", "00000", "10001", "10001", "01111", "00001", "01110"),
    }
    result = Image.new("L", (51, 7))
    draw = ImageDraw.Draw(result)
    x = 0
    for char in "Spcrtify":
        bold = char in "crt"
        for y, row in enumerate(glyphs[char]):
            for column, bit in enumerate(row):
                if bit == "1":
                    draw.rectangle((x + column, y, x + column + int(bold), y), fill=15 if bold else 11)
        x += 7 if bold else 6
    return result


def quantize_art(art: Image.Image, contrast: float, gamma: float) -> Image.Image:
    # Fixed palette rather than adaptive colors, guaranteeing <=16 values.
    gray = ImageEnhance.Contrast(art).enhance(contrast)
    gray = gray.point(lambda p: round(255 * (p / 255) ** (1 / gamma)))
    # Sixteen smooth shades, with no added dithering or moving noise.
    return gray.point(lambda p: max(0, min(15, round(p * 15 / 255))))


def render_frame(state: dict, settings: dict, now: float, art: Image.Image | None = None,
                 calibration: bool = False) -> Image.Image:
    frame = Image.new("L", (WIDTH, HEIGHT), 0)
    if state.get("blanked") and not calibration:
        return frame
    d = ImageDraw.Draw(frame)
    if calibration:
        d.rectangle((8, 8, 271, 183), outline=12, width=2)
        line(d, (20, 20), "MONITOR /// CALIBRATION", 15, 40)
        line(d, (20, 36), "ALL 16 STEPS SHOULD BE VISIBLE", 10, 40)
        for i in range(16):
            d.rectangle((20 + 15 * i, 58, 33 + 15 * i, 97), fill=i)
        line(d, (20, 108), "BLACK", 8)
        line(d, (230, 108), "WHITE", 14)
        for i in range(8):
            d.rectangle((20 + i * 5, 133, 22 + i * 5, 163), fill=15)
            d.rectangle((74, 133 + i * 4, 114, 134 + i * 4), fill=15)
        line(d, (134, 132), "CHECK EDGES", 12, 20)
        line(d, (134, 147), "KEEP 4:3", 12, 20)
        line(d, (20, 172), "C TO RETURN", 8, 35)
    elif not state.get("title"):
        # Sparse idle picture, no brightly lit full-screen logo.
        line(d, (89, 88), "WAITING FOR MUSIC", 5, 30)
        if state.get("error"):
            line(d, (38, 128), state["error"], 7, 34)
    else:
        if state.get("source") == "SPOTIFY":
            frame.paste(spotify_mark(), (184, 19))
            frame.paste(wordmark(), (214, 27))
        cover = art if art is not None else demo_art(state.get("art_seed", 0)) if state.get("source") == "DEMO" else missing_art()
        frame.paste(quantize_art(cover, settings["contrast"], settings["gamma"]), (12, 23))
        rows = title_lines(state["title"])
        for index, row in enumerate(rows):
            line(d, (184, 50 + 10 * index), row, 15)
        artist_y = 50 + (len(rows) - 1) * 10 + 14
        album_y = artist_y + 13
        progress_y = album_y + 14
        time_y = progress_y + 12
        line(d, (184, artist_y), state.get("artist", ""), 11)
        line(d, (184, album_y), state.get("album", ""), 8)
        progress, duration = state.get("progress_ms", 0), state.get("duration_ms", 0)
        d.rectangle((184, progress_y, 265, progress_y + 5), outline=8, width=1)
        if duration > 0:
            fill = round(78 * max(0, min(1, progress / duration)))
            if fill > 0:
                d.rectangle((186, progress_y + 2, 185 + fill, progress_y + 3), fill=14)
        line(d, (184, time_y), timecode(progress), 10)
        total = timecode(duration, hours=True)
        line(d, (266 - len(total) * 6, time_y), total, 10)
        # Decorative motion, not audio analysis. Longer titles take this space.
        bar_height = min(24, 147 - (time_y + 15))
        if bar_height >= 8:
            for index in range(16):
                if state.get("is_playing"):
                    envelope = .25 + .75 * math.sin(math.pi * (index + 1) / 17)
                    motion = .55 + .25 * math.sin(now * 2.1 + index * .8) + .2 * math.sin(now * 3.4 - index * .5)
                    height = max(2, round(bar_height * envelope * motion))
                else:
                    height = 2
                x = 185 + index * 5
                for y in range(147, 147 - height, -2):
                    d.line((x, y, x + 2, y), fill=9 if state.get("is_playing") else 4)
        # Hit targets share exact source coordinates with the browser.
        frame.paste(playback_icon("previous"), (185, 155))
        frame.paste(playback_icon("next"), (250, 155))
        if state.get("is_playing"):
            d.rectangle((221, 157, 224, 170), fill=15)
            d.rectangle((228, 157, 231, 170), fill=15)
        else:
            frame.paste(playback_icon("play"), (217, 155))
    peak = settings["peak"]
    if state.get("dimmed") and not calibration:
        peak = round(peak * .3)
    palette = [round(i * peak / 15) for i in range(16)]
    return frame.point(lambda p: palette[min(15, p)])


@lru_cache(maxsize=1)
def missing_art() -> Image.Image:
    art = Image.new("L", ART_SIZE, 17)
    d = ImageDraw.Draw(art)
    cx, cy = ART_SIZE[0] // 2, ART_SIZE[1] // 2
    for radius in (53, 48, 42, 36, 30):
        d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=68, width=2)
    d.ellipse((cx - 13, cy - 13, cx + 13, cy + 13), fill=119)
    d.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=17)
    return art
