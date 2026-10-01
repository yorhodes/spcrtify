#!/usr/bin/env python3
"""Render a small Spotify-inspired Apple III / Monitor /// player screen.

The source frame is exactly 280x192 pixels and is quantized to 16 gray
intensities. On a green-phosphor Monitor ///, those intensities appear as
different green luminance levels. The preview is aspect-corrected to 4:3 and
adds scanline/vignette effects; the native PNG remains the signal reference.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

W, H = 280, 192
LEVELS = 16
PALETTE = [round(i * 255 / (LEVELS - 1)) for i in range(LEVELS)]

# Tiny built-in 5x7 bitmap font keeps output deterministic and portable.
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ":": ("00000", "00100", "00100", "00000", "00100", "00100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    "'": ("00100", "00100", "00010", "00000", "00000", "00000", "00000"),
    " ": ("00000",) * 7,
    "/": ("00001", "00001", "00010", "00100", "01000", "10000", "10000"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "&": ("01100", "10010", "10100", "01000", "10101", "10010", "01101"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    ",": ("00000", "00000", "00000", "00000", "00100", "00100", "01000"),
}


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str,
         color: int, scale: int = 1) -> None:
    x, y = xy
    for char in value.upper():
        glyph = FONT.get(char, FONT[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    draw.rectangle((x + col * scale, y + row * scale,
                                    x + (col + 1) * scale - 1,
                                    y + (row + 1) * scale - 1), fill=color)
        x += 6 * scale


def album_art(source: Path) -> Image.Image:
    """Load supplied cover art, aspect-correct it, then dither to 16 indices."""
    gray = Image.open(source).convert("L")
    gray = ImageOps.fit(gray, (103, 94), method=Image.Resampling.LANCZOS)
    gray = ImageEnhance.Contrast(gray).enhance(1.25)

    # Adaptive grayscale palette retains the photograph's tonal structure;
    # Floyd–Steinberg distributes quantization error into a fine screen texture.
    indexed = gray.quantize(colors=16, method=Image.Quantize.MEDIANCUT,
                            dither=Image.Dither.FLOYDSTEINBERG)
    source_palette = indexed.getpalette()
    source_palette += [0] * (768 - len(source_palette))
    lut = [round(source_palette[index * 3] * 15 / 255) for index in range(256)]
    # Return 0–15 indices so the complete screen is expanded consistently.
    return indexed.point(lut, mode="L")


def draw_source(cover_path: Path) -> Image.Image:
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)

    # Header: compact Spotify mark and label.
    d.ellipse((8, 7, 18, 17), outline=12, width=1)
    d.arc((10, 9, 16, 13), 195, 340, fill=15, width=1)
    d.arc((11, 11, 16, 15), 195, 340, fill=12, width=1)
    text(d, (22, 9), "SPOTIFY", 13)
    d.line((8, 21, 271, 21), fill=4)

    # Album art: 94x94, dither-free 16-level pixel illustration.
    # Correct horizontal pixel aspect so the cover appears square on a 4:3 CRT.
    art = album_art(cover_path)
    im.paste(art, (8, 29))
    d.rectangle((7, 28, 111, 123), outline=8)

    # Now-playing information and progress.
    text(d, (119, 32), "COME", 15, scale=2)
    text(d, (119, 48), "TOGETHER", 15, scale=2)
    text(d, (119, 68), "THE BEATLES", 11)
    text(d, (119, 79), "ABBEY ROAD", 8)
    d.rectangle((119, 96, 270, 101), outline=9)
    d.rectangle((121, 98, 163, 99), fill=15)
    text(d, (119, 105), "1:24", 12)
    text(d, (239, 105), "4:20", 12)

    # Small level meter.
    bars = [4, 7, 10, 6, 12, 9, 5, 8, 13, 7, 10, 5, 8, 4]
    for i, height in enumerate(bars):
        x = 113 + i * 7
        for j in range(height):
            y = 145 - j * 3
            d.rectangle((x, y, x + 3, y + 1), fill=6 + (j % 8))

    # Playback controls.
    d.polygon([(145, 160), (145, 174), (135, 167)], fill=12)
    d.rectangle((130, 160, 132, 174), fill=12)
    d.rectangle((185, 159, 188, 175), fill=15)
    d.rectangle((192, 159, 195, 175), fill=15)
    d.rectangle((246, 160, 248, 174), fill=12)
    d.polygon([(250, 160), (250, 174), (260, 167)], fill=12)

    # Footer line and restrained status label.
    d.line((8, 182, 271, 182), fill=4)
    text(d, (8, 184), "NOW PLAYING", 8)

    # Quantize every pixel to one of 16 evenly spaced luminance values.
    # The drawing helpers above use shade indices 0–15, so expand each index
    # to its evenly spaced 8-bit luminance value rather than re-quantizing it.
    return im.point(lambda p: PALETTE[min(LEVELS - 1, int(p))])


def green_image(gray: Image.Image) -> Image.Image:
    """Map gray luminance to green phosphor while preserving 16 levels."""
    zero = Image.new("L", gray.size, 0)
    return Image.merge("RGB", (zero, gray, zero))


def crt_preview(gray: Image.Image) -> Image.Image:
    """Create an aspect-correct 4:3 phosphor preview, separate from source."""
    src = green_image(gray)
    # Pixel aspect correction: fit the 280x192 raster to a 4:3 display area.
    screen = src.resize((1024, 768), Image.Resampling.NEAREST)
    pixels = screen.load()
    for y in range(screen.height):
        factor = 0.78 if y % 4 == 3 else 1.0
        for x in range(screen.width):
            r, g, b = pixels[x, y]
            pixels[x, y] = (r, int(g * factor), b)

    # Gentle glass vignette; deliberately confined to the presentation image.
    mask = Image.new("L", screen.size, 255)
    md = ImageDraw.Draw(mask)
    for inset in range(0, 180, 3):
        level = max(120, 255 - inset // 2)
        md.rounded_rectangle((inset, inset * 3 // 4,
                              1023 - inset, 767 - inset * 3 // 4),
                             radius=80, outline=level, width=3)
    mask = mask.filter(ImageFilter.GaussianBlur(28))
    shade = Image.new("RGB", screen.size, (0, 0, 0))
    screen = Image.composite(screen, shade, mask)

    # Simple cabinet mockup around the screen; screen signal is unchanged.
    canvas = Image.new("RGB", (1200, 1000), (27, 19, 13))
    cd = ImageDraw.Draw(canvas)
    cd.rounded_rectangle((25, 20, 1175, 970), radius=54, fill=(109, 78, 50), outline=(46, 32, 21), width=8)
    cd.rounded_rectangle((70, 50, 1130, 850), radius=50, fill=(37, 27, 19), outline=(155, 116, 78), width=7)
    canvas.paste(screen, (88, 66))
    cd.rectangle((90, 888, 1110, 952), fill=(54, 38, 26), outline=(32, 23, 17), width=3)
    cd.text((125, 907), "monitor ///", fill=(196, 158, 116))
    cd.text((805, 907), "BRIGHTNESS     CONTRAST", fill=(176, 140, 102))
    for x in (860, 1045):
        cd.ellipse((x - 24, 923, x + 24, 971), fill=(18, 17, 15), outline=(10, 9, 8), width=4)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("dist"), help="output directory (default: dist)")
    parser.add_argument("--cover", type=Path, required=True,
                        help="local album-cover image to crop, dither, and display")
    args = parser.parse_args()
    if not args.cover.is_file():
        parser.error(f"cover image does not exist: {args.cover}")
    args.out.mkdir(parents=True, exist_ok=True)

    gray = draw_source(args.cover)
    gray_path = args.out / "player-280x192-16-gray.png"
    green_path = args.out / "player-280x192-green.png"
    preview_path = args.out / "monitor-iii-preview.png"
    gray.save(gray_path, optimize=False)
    green_image(gray).save(green_path, optimize=False)
    crt_preview(gray).save(preview_path, optimize=False)

    colors = len(set(gray.tobytes()))
    assert gray.size == (280, 192)
    assert set(gray.tobytes()).issubset(set(PALETTE)), "unexpected non-palette luminance value"
    assert colors <= 16, f"expected at most 16 luminance values; found {colors}"
    print(f"native: {gray_path} ({gray.width}x{gray.height}, {colors}/16 luminance values)")
    print(f"green:  {green_path}")
    print(f"preview:{preview_path} (4:3 CRT presentation; not the source raster)")


if __name__ == "__main__":
    main()
