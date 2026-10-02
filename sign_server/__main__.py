"""HTTP server that hands out the current sign frame.

GET    /frame      -> 128x32 raw RGB565, little-endian, row-major (8192 bytes)
GET    /frame.png  -> the same frame as a PNG, for checking from a browser
POST   /frame      -> body is 8192 bytes of RGB565; served until replaced
POST   /frame?x=&y=&w=&h=
                   -> body is w*h*2 bytes of RGB565; replaces just that rectangle,
                      so several providers can each own part of the screen
DELETE /frame      -> drop everything posted, go back to drawing the scene
"""

import argparse
import io
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from . import HEIGHT, WIDTH, render
from .encode import from_rgb565, to_rgb565

log = logging.getLogger("sign_server")

FRAME_BYTES = WIDTH * HEIGHT * 2

# Canvas built from POSTs; when None, the scene is drawn on each request.
posted = None
lock = threading.Lock()


def current_frame() -> bytes:
    with lock:
        if posted is not None:
            return bytes(posted)
    return to_rgb565(render.render())


def parse_region(query: str):
    """(x, y, w, h) from the query string, or None for a full frame."""
    q = parse_qs(query)
    keys = ("x", "y", "w", "h")
    if not any(k in q for k in keys):
        return None
    try:
        x, y, w, h = (int(q[k][0]) for k in keys)
    except (KeyError, ValueError):
        raise ValueError("region needs integer x, y, w and h")
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > WIDTH or y + h > HEIGHT:
        raise ValueError(f"region {w}x{h} at ({x},{y}) is outside the {WIDTH}x{HEIGHT} screen")
    return x, y, w, h


def paste(region, data: bytes):
    """Write a region's pixels into the canvas, starting from black if empty."""
    global posted
    x, y, w, h = region
    with lock:
        if posted is None:
            posted = bytearray(FRAME_BYTES)
        for row in range(h):
            dst = ((y + row) * WIDTH + x) * 2
            posted[dst : dst + w * 2] = data[row * w * 2 : (row + 1) * w * 2]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/frame":
            self._send(current_frame(), "application/octet-stream")
        elif path == "/frame.png":
            buf = io.BytesIO()
            from_rgb565(current_frame()).resize((WIDTH * 8, HEIGHT * 8), 0).save(buf, "PNG")
            self._send(buf.getvalue(), "image/png")
        else:
            self.send_error(404)

    def do_POST(self):
        global posted
        path, _, query = self.path.partition("?")
        if path != "/frame":
            self.send_error(404)
            return
        try:
            region = parse_region(query)
        except ValueError as e:
            self.send_error(400, str(e))
            return
        expected = FRAME_BYTES if region is None else region[2] * region[3] * 2
        length = int(self.headers.get("Content-Length") or 0)
        if length != expected:
            self.send_error(400, f"body must be {expected} bytes of RGB565, got {length}")
            return
        data = self.rfile.read(length)
        if region is None:
            with lock:
                posted = bytearray(data)
            log.info("frame posted by %s", self.address_string())
        else:
            paste(region, data)
            log.info("region %s posted by %s", region, self.address_string())
        self._send(b"", "text/plain", 204)

    def do_DELETE(self):
        global posted
        if self.path.split("?", 1)[0] != "/frame":
            self.send_error(404)
            return
        with lock:
            posted = None
        log.info("posted frame cleared by %s", self.address_string())
        self._send(b"", "text/plain", 204)

    def _send(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.debug("%s %s", self.address_string(), format % args)


def main():
    p = argparse.ArgumentParser(prog="sign_server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5001)
    p.add_argument("--scene", choices=render.SCENES, default="clock")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    render.render = render.SCENES[args.scene]
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("serving %s on http://%s:%d/frame", args.scene, args.host, args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
