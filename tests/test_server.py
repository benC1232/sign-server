import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from sign_server import __main__ as server
from sign_server.encode import from_rgb565, to_rgb565
from sign_server.render import israel_flag


@pytest.fixture
def base_url():
    server.posted = None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/frame"
    httpd.shutdown()
    server.posted = None


def call(url, method="GET", body=None):
    req = urllib.request.Request(url, data=body, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read()


def test_post_then_get_returns_posted_bytes(base_url):
    frame = bytes(range(256)) * 32
    assert call(base_url, "POST", frame)[0] == 204
    assert call(base_url) == (200, frame)
    assert call(base_url + ".png")[0] == 200


def test_delete_goes_back_to_scene(base_url):
    call(base_url, "POST", bytes(8192))
    assert call(base_url, "DELETE")[0] == 204
    assert call(base_url)[1] != bytes(8192)


def test_wrong_size_rejected(base_url):
    with pytest.raises(urllib.error.HTTPError) as e:
        call(base_url, "POST", bytes(100))
    assert e.value.code == 400
    assert server.posted is None


def test_rgb565_round_trip():
    data = to_rgb565(israel_flag())
    assert to_rgb565(from_rgb565(data)) == data


def test_region_post_only_touches_its_rectangle(base_url):
    call(base_url, "POST", bytes([0x11]) * 8192)
    assert call(base_url + "?x=88&y=0&w=40&h=32", "POST", bytes([0xFF]) * (40 * 32 * 2))[0] == 204
    frame = call(base_url)[1]
    row = frame[: 128 * 2]
    assert row[: 88 * 2] == bytes([0x11]) * (88 * 2)
    assert row[88 * 2 :] == bytes([0xFF]) * (40 * 2)
    assert frame[-2:] == b"\xff\xff"  # bottom-right pixel


def test_region_on_empty_canvas_starts_black(base_url):
    call(base_url + "?x=0&y=0&w=1&h=1", "POST", b"\xff\xff")
    frame = call(base_url)[1]
    assert frame[:2] == b"\xff\xff" and frame[2:] == bytes(8190)


@pytest.mark.parametrize("query, size", [
    ("?x=100&y=0&w=40&h=32", 40 * 32 * 2),  # off the right edge
    ("?x=0&y=0&w=10", 10 * 2),              # missing h
    ("?x=0&y=0&w=10&h=10", 7),              # wrong body size
])
def test_bad_region_rejected(base_url, query, size):
    with pytest.raises(urllib.error.HTTPError) as e:
        call(base_url + query, "POST", bytes(size))
    assert e.value.code == 400
    assert server.posted is None
