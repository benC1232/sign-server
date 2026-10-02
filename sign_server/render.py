"""What goes on the sign. Each scene returns a WIDTHxHEIGHT RGB image."""

import colorsys
import math
import time

from PIL import Image, ImageDraw, ImageFont

from . import HEIGHT, WIDTH

_font = ImageFont.load_default()


def clock() -> Image.Image:
    """Demo frame: a rainbow strip and the current time."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    for x in range(WIDTH):
        hue = x / WIDTH
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        draw.line([(x, HEIGHT - 4), (x, HEIGHT - 1)], fill=(int(r * 255), int(g * 255), int(b * 255)))

    draw.text((2, 2), time.strftime("%H:%M"), font=_font, fill=(255, 255, 255))
    draw.text((2, 14), "sign-server", font=_font, fill=(0, 160, 255))
    return img


FLAG_BLUE = (0, 56, 184)


def israel_flag() -> Image.Image:
    """Flag of Israel stretched across the panel; the star keeps its shape.

    Stripes follow the official 160-unit height (15 white, 25 blue, 80 white,
    25 blue, 15 white), which is 3/5/16/5/3 px at 32 px. Drawn at 8x and
    scaled down so the thin star edges come out smooth.
    """
    k = 8
    w, h = WIDTH * k, HEIGHT * k
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 3 * k, w - 1, 8 * k - 1], fill=FLAG_BLUE)
    draw.rectangle([0, 24 * k, w - 1, 29 * k - 1], fill=FLAG_BLUE)

    cx, cy, r = w / 2, h / 2, 6.5 * k
    for start in (-90, 90):  # point-up and point-down triangles
        pts = [
            (cx + r * math.cos(math.radians(start + 120 * i)), cy + r * math.sin(math.radians(start + 120 * i)))
            for i in range(3)
        ]
        draw.polygon(pts, outline=FLAG_BLUE, width=int(1.2 * k))
    return img.resize((WIDTH, HEIGHT), Image.Resampling.BOX)


SCENES = {"clock": clock, "israel": israel_flag}
render = clock
