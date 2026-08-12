"""
Thermal image quality validation.

Generates the actual 384×N 1-bit output for the seven required test image
types through the new preset pipeline AND the legacy pipeline, then reports
thermal-relevant metrics:

  * black coverage %           — too high = muddy/blackish prints
  * transition density         — too high = noisy, "over-sharpened" texture
  * raster row width           — must stay 48 bytes (384 dots) per protocol
  * thin-line preservation     — 1 px lines must survive line-art/manga modes

Run:  python tools/validate_image_quality.py
"""

import os
import sys
import random

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image, ImageDraw
from backend.services.image_processor import ImageProcessor as P


def make_photo():
    """Portrait-like: gradient skin tones + soft noise."""
    rnd = random.Random(1)
    img = Image.new("L", (400, 500))
    px = img.load()
    for y in range(500):
        for x in range(400):
            base = 70 + int((x / 400) * 120) + int((y / 500) * 60)
            px[x, y] = max(0, min(255, base + rnd.randint(-14, 14)))
    return img


def make_manga():
    """Manga panel: solid blacks, white gutters, gray shading, thin lines."""
    img = Image.new("L", (400, 500), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 30, 380, 240], fill=230)          # gray panel
    d.rectangle([40, 60, 180, 200], fill=0)            # solid black block
    for i in range(12):                                 # thin horizontal lines
        d.line([(30, 120 + i * 5), (370, 120 + i * 5)], fill=0, width=1)
    d.line([(200, 40), (380, 210)], fill=0, width=2)    # diagonal
    d.rectangle([210, 260, 380, 470], fill=200)         # darker panel
    d.text((230, 300), "M A N G A", fill=0)             # text block
    return img


def make_dark():
    """Dark image: night scene, shadows dominant."""
    rnd = random.Random(2)
    img = Image.new("L", (400, 300))
    px = img.load()
    for y in range(300):
        for x in range(400):
            base = 25 + int((x / 400) * 50) + int((y / 300) * 30)
            px[x, y] = max(0, min(255, base + rnd.randint(-8, 8)))
    return img


def make_light():
    """Light image: bright scene, mostly whites."""
    rnd = random.Random(3)
    img = Image.new("L", (400, 300))
    px = img.load()
    for y in range(300):
        for x in range(400):
            base = 175 + int((x / 400) * 60) + int((y / 300) * 20)
            px[x, y] = max(0, min(255, base + rnd.randint(-10, 10)))
    return img


def make_gradient():
    """Full-range smooth gradient."""
    img = Image.new("L", (384, 256))
    px = img.load()
    for y in range(256):
        for x in range(384):
            px[x, y] = int((x / 383) * 255)
    return img


def make_line_art():
    """Fine line art: 1 px lines, curves, dots."""
    img = Image.new("L", (400, 400), 255)
    d = ImageDraw.Draw(img)
    for x in range(0, 400, 12):                          # vertical grid 1px
        d.line([(x, 0), (x, 399)], fill=0, width=1)
    for y in range(0, 400, 12):
        d.line([(0, y), (399, y)], fill=0, width=1)
    d.ellipse([150, 150, 250, 250], outline=0, width=1)  # 1px circle
    for i in range(20):
        d.point((30 + i * 5, 300), fill=0)               # isolated dots
    return img


def make_text():
    """Small text: 8-14 px glyphs."""
    img = Image.new("L", (384, 120), 255)
    d = ImageDraw.Draw(img)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    d.text((8, 10), "Mini Print Studio", fill=0, font=font)
    d.text((8, 34), "The quick brown fox", fill=0, font=font)
    d.text((8, 58), "0123456789", fill=0, font=font)
    return img


def metrics(img_1bit):
    """Black coverage + black/white transition density."""
    img_1bit = img_1bit.convert("1")
    d = img_1bit.load()
    w, h = img_1bit.size
    black = 0
    transitions = 0
    for y in range(h):
        prev = None
        for x in range(w):
            v = 0 if d[x, y] == 0 else 1
            if v == 0:
                black += 1
            if prev is not None and v != prev:
                transitions += 1
            prev = v
    return {
        "black_pct": round(100 * black / (w * h), 1),
        "transitions": transitions,
    }


def thin_line_check(img_1bit, region_top=0, region_bottom=None, min_run=0.8):
    """Does a 1px source line survive? Reports the longest continuous black
    run in the best column across the region (resize aliasing shifts the
    exact column, so we search columns rather than assuming one)."""
    img_1bit = img_1bit.convert("1")
    d = img_1bit.load()
    w, h = img_1bit.size
    if region_bottom is None:
        region_bottom = h
    best = 0
    best_x = -1
    for x in range(w):
        run = 0
        cur = 0
        for y in range(region_top, region_bottom):
            if d[x, y] == 0:
                cur += 1
                run = max(run, cur)
            else:
                cur = 0
        if run > best:
            best, best_x = run, x
    threshold = min_run * (region_bottom - region_top)
    return best >= threshold, best, best_x


def make_thin_cross():
    """Dedicated thin-line test: one 1px vertical + one 1px horizontal line."""
    img = Image.new("L", (400, 200), 255)
    d = ImageDraw.Draw(img)
    d.line([(200, 10), (200, 190)], fill=0, width=1)
    d.line([(20, 100), (380, 100)], fill=0, width=1)
    return img


CASES = [
    ("portrait_photo", make_photo, "photo"),
    ("manga_panel", make_manga, "manga"),
    ("dark_image", make_dark, "photo"),
    ("light_image", make_light, "photo"),
    ("gradient", make_gradient, "photo"),
    ("fine_line_art", make_line_art, "line_art"),
    ("small_text", make_text, "text"),
]


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "quality_report")
    os.makedirs(out_dir, exist_ok=True)
    print(f"{'case':<18}{'preset':<11}{'black%':>8}{'trans':>9}{'rows':>6}{'48B/row':>9}  note")
    print("-" * 80)
    ok = True
    for name, builder, preset in CASES:
        src = builder().convert("RGB")

        new_img = P.process_image(src, target_width_px=384,
                                  processing_preset=preset)
        legacy_img = P.process_image(src, target_width_px=384,
                                     processing_preset=None)

        for label, img in (("new", new_img), ("legacy", legacy_img)):
            img = img.convert("1")
            raster = P.to_raster_bytes(img)
            row_len = len(raster) // img.height
            m = metrics(img)
            row_ok = row_len == 48 and img.width == 384
            if not row_ok:
                ok = False
            print(f"{name:<18}{label + '/' + preset:<11}{m['black_pct']:>7}%{m['transitions']:>9}{img.height:>6}{row_len:>7}B  {'OK' if row_ok else 'BAD ROW!'}")
            P.to_base64_png(img.convert("L").point(lambda p: 255 - p))  # keep warm
            img.convert("L").save(os.path.join(out_dir, f"{name}_{label}.png"))

        # Thin-line preservation in manga + line_art presets, tested on a
        # dedicated 1px cross so resize aliasing can't mask the result.
        if preset in ("manga", "line_art"):
            cross = make_thin_cross().convert("RGB")
            cross_out = P.process_image(cross, target_width_px=384,
                                        processing_preset=preset)
            # Vertical line: longest black run in the best column must span
            # the middle band of the image (0.8 of the height).
            kept_v, run_v, x_v = thin_line_check(cross_out, region_top=20, region_bottom=180)
            # Horizontal line: longest black run in the best row.
            d = cross_out.convert("1").load()
            best_h = 0
            for y in range(20, 180):
                cur = 0
                for x in range(cross_out.width):
                    if d[x, y] == 0:
                        cur += 1
                        best_h = max(best_h, cur)
                    else:
                        cur = 0
            preserved = kept_v and best_h >= 0.5 * cross_out.width
            print(f"{'':<18}{'thin-line':<11}{'':>8}{'':>9}{'':>6}{'':>9}  {'KEPT' if preserved else 'LOST!'} (v-run={run_v}px h-run={best_h}px)")
            if not preserved:
                ok = False

    print("-" * 80)
    print(f"Report images written to: {out_dir}")
    print("ALL CHECKS PASSED" if ok else "CHECKS FAILED")


if __name__ == "__main__":
    main()
