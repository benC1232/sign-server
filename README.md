# sign-server

Holds the screen for a 128×32 LED sign (I run it on DIY TransitTracker
hardware) and serves it over HTTP. The sign runs
[sign-code](https://github.com/benC1232/sign-code), which fetches a frame every
30 s and shows it as-is.

Providers draw the content and post it here, either as a full frame or as a
rectangle they own (so several providers can share the screen). When nothing
has been posted yet, the server draws a demo scene instead.

| Endpoint            | Does                                                          |
|---------------------|---------------------------------------------------------------|
| `GET /frame`        | 8192 bytes: 128×32 RGB565, little-endian, row-major           |
| `GET /frame.png`    | Same frame, scaled 8×, for checking in a browser              |
| `POST /frame`       | Body is 8192 bytes of RGB565; served as-is until replaced     |
| `POST /frame?x=&y=&w=&h=` | Body is w×h×2 bytes; replaces just that rectangle         |
| `DELETE /frame`     | Forget everything posted and go back to drawing the scene     |

Pushing a frame from anywhere on the network:

```sh
curl -X POST --data-binary @frame.rgb565 http://<pi>:5001/frame
```

Providers that only own part of the screen post a rectangle instead, e.g.
weather-provider posts a 40×32 panel at `?x=88&y=0&w=40&h=32`. The first
rectangle posted starts from a black screen, not the scene.

A wrong-sized body or out-of-bounds rectangle gets `400` and changes nothing.
Posted frames live in memory only, so a restart goes back to the scene.
There's no auth: anyone who can reach the server can post, so keep it on your
LAN.

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m sign_server   # --host, --port (default 5001), --scene clock|israel, -v
```

## Fallback scenes

Until something is posted, the scene picked with `--scene` is drawn fresh on
every request. Scenes live in `sign_server/render.py` (`SCENES`), each a
function returning a 128×32 PIL image: `clock` (a demo clock) and `israel` (the
flag).

## Run on boot (Pi)

Edit paths/user in `sign-server.service` if needed, then:

```sh
sudo cp sign-server.service /etc/systemd/system/
sudo systemctl enable --now sign-server
```

## Tests

```sh
.venv/bin/pip install pytest
.venv/bin/pytest
```

## License

MIT, see [LICENSE](LICENSE).
