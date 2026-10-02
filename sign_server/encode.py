"""Turn a PIL image into the sign's wire format: raw little-endian RGB565."""

from array import array
import sys

from PIL import Image

from . import HEIGHT, WIDTH


def to_rgb565(img: Image.Image) -> bytes:
    if img.size != (WIDTH, HEIGHT):
        raise ValueError(f"frame must be {WIDTH}x{HEIGHT}, got {img.size[0]}x{img.size[1]}")
    rgb = img.convert("RGB").tobytes()
    out = array("H", bytes(WIDTH * HEIGHT * 2))
    for i in range(WIDTH * HEIGHT):
        r, g, b = rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]
        out[i] = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes()


def from_rgb565(data: bytes) -> Image.Image:
    """Inverse of to_rgb565, for previewing posted frames."""
    if len(data) != WIDTH * HEIGHT * 2:
        raise ValueError(f"frame must be {WIDTH * HEIGHT * 2} bytes, got {len(data)}")
    px = array("H", data)
    if sys.byteorder != "little":
        px.byteswap()
    rgb = bytearray(WIDTH * HEIGHT * 3)
    for i, v in enumerate(px):
        r, g, b = v >> 11, (v >> 5) & 0x3F, v & 0x1F
        rgb[3 * i] = (r << 3) | (r >> 2)
        rgb[3 * i + 1] = (g << 2) | (g >> 4)
        rgb[3 * i + 2] = (b << 3) | (b >> 2)
    return Image.frombytes("RGB", (WIDTH, HEIGHT), bytes(rgb))
