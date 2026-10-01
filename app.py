#!/usr/bin/env python3
"""A small, local now-playing appliance for the Apple Monitor III."""
from __future__ import annotations

import argparse
import io
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from PIL import Image, ImageOps

from display import ART_SIZE, local_art, prepare_art, render_frame
from spotify import Authorization, Spotify, SpotifyError
from systemd_notify import Watchdog

ROOT = Path(__file__).resolve().parent
DEFAULT_SETTINGS = {"peak": 204, "contrast": 1.15, "gamma": 1.0, "overscan": 5, "idle_seconds": 300}


def validate_settings(value):
    # Accept saved settings and open clients from before the activity-meter removal.
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if key != "motion"}
    if not isinstance(value, dict) or set(value) - set(DEFAULT_SETTINGS):
        raise ValueError("Unknown display setting")
    result = {}
    for key, item in value.items():
        low, high = {"peak": (68, 255), "contrast": (.5, 2), "gamma": (.5, 2),
                     "overscan": (0, 15), "idle_seconds": (30, 3600)}[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or not low <= item <= high:
            raise ValueError(f"Invalid {key} setting")
        item = int(item) if key in ("peak", "overscan", "idle_seconds") else float(item)
        result[key] = item
    return result


class Demo:
    name, interval = "Demo", 1
    tracks = [("Night Drive", "The Night Shift", "After Hours", 242000),
              ("Blue Hour", "Slow Radio", "Open Water", 216000),
              ("Quiet Signals", "The Night Shift", "After Hours", 284000)]

    def __init__(self):
        self.index, self.position, self.playing, self.updated = 0, 84000, True, time.monotonic()
        self.lock = threading.RLock()

    def poll(self):
        with self.lock:
            now = time.monotonic()
            if self.playing:
                self.position += (now - self.updated) * 1000
            self.updated = now
            if self.position >= self.tracks[self.index][3]:
                self.index = (self.index + 1) % len(self.tracks)
                self.position = 0
            title, artist, album, duration = self.tracks[self.index]
            return dict(source="DEMO", title=title, artist=artist, album=album, duration_ms=duration,
                        progress_ms=int(self.position), is_playing=self.playing, art_seed=self.index, controls=True)

    def control(self, action, state):
        with self.lock:
            self.poll()
            if action == "toggle":
                self.playing = not self.playing
            else:
                self.index = (self.index + (1 if action == "next" else -1)) % len(self.tracks)
                self.position = 0


class JsonFeed:
    name, interval = "JSON feed", 1

    def __init__(self, path):
        self.path = path.resolve()

    def poll(self):
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict):
            raise ValueError("Feed must be a JSON object")
        state = {key: str(data.get(key, ""))[:500] for key in ("title", "artist", "album")}
        state.update(source="LOCAL", is_playing=data.get("is_playing") is True, controls=False)
        for key in ("duration_ms", "progress_ms"):
            item = data.get(key, 0)
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError(f"Invalid {key} in feed")
            state[key] = max(0, int(item))
        if data.get("cover"):
            state["cover_path"] = str((self.path.parent / str(data["cover"])).resolve())
        return state


class Player:
    def __init__(self, args):
        self.args, self.lock = args, threading.RLock()
        self.settings = DEFAULT_SETTINGS.copy()
        self.settings_path = args.data / "display.json"
        try:
            self.settings.update(validate_settings(json.loads(self.settings_path.read_text())))
        except (OSError, ValueError):
            pass
        self.auth = Authorization(args.data / "spotify.json", args.port)
        source = args.source
        if source == "auto":
            import os
            source = "spotify" if self.auth.path.exists() or os.environ.get("SPOTIFY_REFRESH_TOKEN") else "demo"
        self.provider = JsonFeed(args.feed) if source == "json" else Spotify(self.auth.path) if source == "spotify" else Demo()
        self.state = {"source": self.provider.name.upper(), "title": "", "is_playing": False, "controls": False}
        self.updated = self.last_active = time.monotonic()
        self.art, self.art_key, self.art_error = None, None, None
        self.wake, self.stop = threading.Event(), threading.Event()

    def start(self):
        self.thread = threading.Thread(target=self.poll_loop, daemon=True)
        self.thread.start()

    def poll_loop(self):
        while not self.stop.is_set():
            self.wake.clear()
            with self.lock:
                provider = self.provider
            wait = provider.interval
            try:
                state = provider.poll()
                with self.lock:
                    if provider is self.provider:
                        self.state, self.updated = state, time.monotonic()
                # Metadata appears immediately; artwork downloads happen off the UI thread.
                self.load_art(state, provider)
            except (SpotifyError, OSError, ValueError, KeyError) as error:
                message = str(error) if isinstance(error, SpotifyError) else "Cannot read player data; retrying"
                with self.lock:
                    if provider is self.provider:
                        self.state = {**self.snapshot(), "is_playing": False, "error": message}
                        self.updated = time.monotonic()
                wait = getattr(error, "retry_after", 5)
            self.wake.wait(wait)

    def load_art(self, state, provider):
        key = state.get("cover_url") or state.get("cover_path") or None
        if state.get("cover_path"):
            try:
                key = (state["cover_path"], Path(state["cover_path"]).stat().st_mtime_ns)
            except OSError:
                with self.lock:
                    if provider is self.provider:
                        self.art, self.art_key, self.art_error = None, key, "Artwork unavailable"
                return
        with self.lock:
            if self.art_key == key and not self.art_error:
                return
            if provider is self.provider and self.art_key != key:
                self.art = None
        art, error = None, None
        try:
            if state.get("cover_path"):
                art = local_art(*key)
            elif state.get("cover_url"):
                url = urlparse(state["cover_url"])
                if url.scheme != "https" or url.hostname != "i.scdn.co":
                    raise ValueError("Unsupported artwork address")
                with urlopen(state["cover_url"], timeout=8) as response:
                    payload = response.read(5 * 1024 * 1024 + 1)
                if len(payload) > 5 * 1024 * 1024:
                    raise ValueError("Artwork is too large")
                with Image.open(io.BytesIO(payload)) as original:
                    art = prepare_art(original)
        except (OSError, ValueError):
            error = "Artwork unavailable"
        with self.lock:
            if provider is self.provider:
                self.art, self.art_key, self.art_error = art, key, error

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            state = self.state.copy()
            if state.get("is_playing"):
                self.last_active = now
                state["progress_ms"] = min(state.get("duration_ms", 0),
                    state.get("progress_ms", 0) + int((now - self.updated) * 1000))
            state["dimmed"] = now - self.last_active > self.settings["idle_seconds"]
            state["blanked"] = now - self.last_active > max(1800, self.settings["idle_seconds"] * 2)
            state.update(provider=self.provider.name, connected=isinstance(self.provider, Spotify) and bool(self.provider.tokens.get("refresh_token")),
                         artwork_error=self.art_error, settings=self.settings.copy())
            return state

    def frame(self, calibration=False):
        with self.lock:
            return render_frame(self.snapshot(), self.settings, time.monotonic(), self.art, calibration)

    def switch(self, source):
        if source not in ("demo", "spotify", "json") or source == "json" and not self.args.feed:
            raise ValueError("Choose a configured source")
        provider = {"demo": lambda: Demo(), "spotify": lambda: Spotify(self.auth.path),
                    "json": lambda: JsonFeed(self.args.feed)}[source]()
        with self.lock:
            self.provider, self.art, self.art_key, self.art_error = provider, None, None, None
            self.state = dict(title="", source=provider.name.upper(), is_playing=False, controls=False)
            self.last_active = self.updated = time.monotonic()
        self.wake.set()

    def control(self, action):
        if action not in ("toggle", "next", "previous"):
            raise ValueError("Unknown playback action")
        with self.lock:
            provider, state = self.provider, self.snapshot()
        if not state.get("controls") or isinstance(provider, JsonFeed):
            raise ValueError("Playback controls are unavailable for this source or device")
        restriction = {"next": "skipping_next", "previous": "skipping_prev",
                       "toggle": "pausing" if state.get("is_playing") else "resuming"}[action]
        if state.get("disallows", {}).get(restriction):
            raise ValueError("Spotify does not allow this action on the current device")
        provider.control(action, state)
        self.wake.set()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # OAuth codes never enter request logs.
        pass

    @property
    def player(self):
        return self.server.player

    def respond(self, status, payload, content_type="application/json"):
        if content_type == "application/json":
            payload = json.dumps(payload).encode()
        elif isinstance(payload, str):
            payload = payload.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self.respond(200, self.player.snapshot())
        elif parsed.path == "/api/frame.png":
            frame = self.player.frame(parse_qs(parsed.query).get("calibrate") == ["1"])
            buffer = io.BytesIO()
            frame.save(buffer, format="PNG")
            self.respond(200, buffer.getvalue(), "image/png")
        elif parsed.path == "/callback":
            try:
                self.player.auth.finish(parse_qs(parsed.query))
                self.player.switch("spotify")
                self.send_response(303)
                self.send_header("Location", "/?connected=1")
                self.end_headers()
            except (ValueError, SpotifyError, OSError) as error:
                import html
                self.respond(400, f"<h1>Sign-in could not finish</h1><p>{html.escape(str(error))}</p><a href='/'>Return to player</a>", "text/html; charset=utf-8")
        else:
            files = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            filename = files.get(parsed.path)
            if not filename:
                self.respond(404, {"error": "Not found"})
                return
            types = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8"}
            self.respond(200, (ROOT / "web" / filename).read_bytes(), types[filename.split(".")[-1]])

    def do_POST(self):
        # A local appliance, bound to loopback by default. Reject cross-origin writes.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            self.respond(403, {"error": "Cross-origin request rejected"})
            return
        if self.headers.get_content_type() != "application/json":
            self.respond(415, {"error": "Use application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            path = urlparse(self.path).path
            if path == "/api/control":
                self.player.control(data.get("action"))
            elif path == "/api/settings":
                updates = validate_settings(data)
                with self.player.lock:
                    settings = {**self.player.settings, **updates}
                    self.player.args.data.mkdir(parents=True, exist_ok=True)
                    temporary = self.player.settings_path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(settings))
                    temporary.replace(self.player.settings_path)
                    self.player.settings = settings
            elif path == "/api/source":
                self.player.switch(data.get("source"))
            elif path == "/api/spotify/connect":
                # Redirect is a loopback URI; sign in locally or through an SSH tunnel.
                client_id = data.get("client_id", "")
                self.respond(200, {"url": self.player.auth.begin(client_id)})
                return
            else:
                self.respond(404, {"error": "Not found"})
                return
            self.respond(200, {"ok": True, "state": self.player.snapshot()})
        except (ValueError, KeyError, TypeError, SpotifyError) as error:
            self.respond(400, {"error": str(error)})
        except OSError:
            self.respond(500, {"error": "Cannot save settings; check the data folder"})


class PlayerServer(ThreadingHTTPServer):
    def service_actions(self):
        self.watchdog.tick()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source", choices=("auto", "demo", "spotify", "json"), default="auto")
    parser.add_argument("--feed", type=Path)
    parser.add_argument("--data", type=Path, default=ROOT / ".data")
    args = parser.parse_args()
    if args.source == "json" and not args.feed:
        parser.error("--source json requires --feed /path/to/now-playing.json")
    player = Player(args)
    server = PlayerServer((args.host, args.port), Handler)
    server.watchdog = Watchdog()
    server.daemon_threads = True
    server.player = player
    player.start()
    print(f"Spcrtify: http://127.0.0.1:{args.port}", flush=True)
    print(f"Pi display: http://127.0.0.1:{args.port}/?kiosk=1", flush=True)
    try:
        server.watchdog.ready()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        player.stop.set()
        player.wake.set()
        server.server_close()


if __name__ == "__main__":
    main()
