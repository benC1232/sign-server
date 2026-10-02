import struct

import pytest
from PIL import Image

from sign_server import HEIGHT, WIDTH
from sign_server.encode import to_rgb565
from sign_server.render import SCENES


def solid(color):
    return Image.new("RGB", (WIDTH, HEIGHT), color)


def test_size():
    assert len(to_rgb565(solid((0, 0, 0)))) == WIDTH * HEIGHT * 2 == 8192


def test_channels_little_endian():
    img = solid((0, 0, 0))
    img.putpixel((0, 0), (255, 0, 0))
    img.putpixel((1, 0), (0, 255, 0))
    img.putpixel((2, 0), (0, 0, 255))
    img.putpixel((0, 1), (255, 255, 255))
    px = to_rgb565(img)
    assert px[:6] == bytes([0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00])
    assert struct.unpack_from("<H", px, WIDTH * 2)[0] == 0xFFFF  # row-major


def test_wrong_size_rejected():
    with pytest.raises(ValueError):
        to_rgb565(Image.new("RGB", (64, 32)))


@pytest.mark.parametrize("scene", SCENES)
def test_scenes_are_encodable(scene):
    assert len(to_rgb565(SCENES[scene]())) == 8192
