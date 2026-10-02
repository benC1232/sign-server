"""HTTP server that hands out the current sign frame(s).

GET    /frame      -> 1-30 frames of 128x32 raw RGB565, little-endian, row-major
                      (8192 bytes each), back to back. Several frames are an
                      animation; the X-Frame-Ms header says how long to show each.
GET    /frame.png  -> the first frame as a PNG, for checking from a browser
GET    /frame.gif  -> all frames as an animated GIF
POST   /frame      -> body is 8192 bytes of RGB565; replaces everything posted
POST   /frame?x=&y=&w=&h=
                   -> body is w*h*2 bytes of RGB565; replaces just that rectangle,
                      so several providers can each own part of the screen
       ...&frames=N
                   -> N frames of that size back to back (1-30): an animated region
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
MAX_FRAMES = 30
FULL = (0, 0, WIDTH, HEIGHT)

# Posted regions in the order they were posted, each (x, y, w, h) -> list of
# frames (bytes). Later regions draw over earlier ones. None: nothing posted
# yet, so the scene is drawn on each request.
layers = None
lock = threading.Lock()
frame_ms = 500  # how long the sign shows each frame of an animation


def compose(snapshot):
    """Full frames from the layers. The screen animates as long as its longest
    region; a region with fewer frames holds its last one."""
    count = max(len(frames) for frames in snapshot.values())
    out = []
    for i in range(count):
        canvas = bytearray(FRAME_BYTES)  # black where nothing was posted
        for (x, y, w, h), frames in snapshot.items():
            data = frames[min(i, len(frames) - 1)]
            for row in range(h):
                dst = ((y + row) * WIDTH + x) * 2
                canvas[dst : dst + w * 2] = data[row * w * 2 : (row + 1) * w * 2]
        out.append(bytes(canvas))
    return out


def current_frames() -> list:
    with lock:
        snapshot = dict(layers) if layers is not None else None
    if snapshot is None:
        return [to_rgb565(render.render())]
    return compose(snapshot)


def parse_post(query: str):
    """(region, frame count) from the query string; region is FULL if not given."""
    q = parse_qs(query)
    try:
        count = int(q.get("frames", ["1"])[0])
    except ValueError:
        raise ValueError("frames must be an integer")
    if not 1 <= count <= MAX_FRAMES:
        raise ValueError(f"frames must be 1-{MAX_FRAMES}, got {count}")
    keys = ("x", "y", "w", "h")
    if not any(k in q for k in keys):
        return FULL, count
    try:
        x, y, w, h = (int(q[k][0]) for k in keys)
    except (KeyError, ValueError):
        raise ValueError("region needs integer x, y, w and h")
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > WIDTH or y + h > HEIGHT:
        raise ValueError(f"region {w}x{h} at ({x},{y}) is outside the {WIDTH}x{HEIGHT} screen")
    return (x, y, w, h), count


def store(region, frames):
    """Save a posted region. A full-screen post replaces everything."""
    global layers
    with lock:
        if region == FULL or layers is None:
            layers = {}
        layers.pop(region, None)  # re-posting a region moves it to the top
        layers[region] = frames


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/frame":
            frames = current_frames()
            headers = {"X-Frame-Ms": str(frame_ms)} if len(frames) > 1 else {}
            self._send(b"".join(frames), "application/octet-stream", headers=headers)
        elif path == "/frame.png":
            buf = io.BytesIO()
            from_rgb565(current_frames()[0]).resize((WIDTH * 8, HEIGHT * 8), 0).save(buf, "PNG")
            self._send(buf.getvalue(), "image/png")
        elif path == "/frame.gif":
            images = [from_rgb565(f).resize((WIDTH * 8, HEIGHT * 8), 0) for f in current_frames()]
            buf = io.BytesIO()
            images[0].save(buf, "GIF", save_all=True, append_images=images[1:], duration=frame_ms, loop=0)
            self._send(buf.getvalue(), "image/gif")
        else:
            self.send_error(404)

    def do_POST(self):
        path, _, query = self.path.partition("?")
        if path != "/frame":
            self.send_error(404)
            return
        try:
            region, count = parse_post(query)
        except ValueError as e:
            self.send_error(400, str(e))
            return
        size = region[2] * region[3] * 2
        length = int(self.headers.get("Content-Length") or 0)
        if length != size * count:
            self.send_error(400, f"body must be {count} x {size} bytes of RGB565, got {length}")
            return
        data = self.rfile.read(length)
        store(region, [data[i * size : (i + 1) * size] for i in range(count)])
        log.info("%s, %d frame(s), posted by %s", "frame" if region == FULL else f"region {region}",
                 count, self.address_string())
        self._send(b"", "text/plain", 204)

    def do_DELETE(self):
        global layers
        if self.path.split("?", 1)[0] != "/frame":
            self.send_error(404)
            return
        with lock:
            layers = None
        log.info("posted frame cleared by %s", self.address_string())
        self._send(b"", "text/plain", 204)

    def _send(self, body: bytes, content_type: str, status: int = 200, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
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
    p.add_argument("--frame-ms", type=int, default=500, help="how long the sign shows each animation frame")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    global frame_ms
    frame_ms = args.frame_ms
    render.render = render.SCENES[args.scene]
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("serving %s on http://%s:%d/frame", args.scene, args.host, args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
