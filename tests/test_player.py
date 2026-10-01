import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from PIL import Image

from app import DEFAULT_SETTINGS, Demo, Handler, JsonFeed, Player, ThreadingHTTPServer, validate_settings
from display import ART_SIZE, PIXEL_ASPECT, prepare_art, quantize_art, render_frame, title_lines
from kiosk import target_rect
from spotify import Authorization, Spotify, SpotifyError, request_json, save_tokens


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.args = argparse.Namespace(source="demo", port=8765, data=self.path, feed=None)
        self.player = Player(self.args)

    def tearDown(self):
        self.player.stop.set()
        self.player.wake.set()
        self.temp.cleanup()

    def test_signal_geometry_and_palette_in_all_modes(self):
        for peak in (68, 204, 255):
            for state, calibration in ((Demo().poll(), False), ({}, False), ({}, True),
                                       ({**Demo().poll(), "dimmed": True}, False)):
                frame = render_frame(state, {**DEFAULT_SETTINGS, "peak": peak}, 1, calibration=calibration)
                ceiling = round(peak * .3) if state.get("dimmed") else peak
                self.assertEqual(frame.size, (280, 192))
                self.assertEqual(frame.mode, "L")
                self.assertLessEqual(len(set(frame.tobytes())), 16)
                self.assertLessEqual(max(frame.tobytes()), ceiling)
        self.assertAlmostEqual(ART_SIZE[0] * PIXEL_ASPECT, ART_SIZE[1], delta=1)

    def test_playing_picture_has_no_header_or_footer(self):
        frame = render_frame(Demo().poll(), DEFAULT_SETTINGS, 0)
        self.assertEqual(frame.crop((0, 0, 280, 23)).getbbox(), None)
        self.assertEqual(frame.crop((0, 174, 280, 192)).getbbox(), None)

    def test_artwork_has_no_added_dither(self):
        art = Image.new("L", ART_SIZE, 127)
        result = quantize_art(art, 1, 1)
        self.assertEqual(len(set(result.tobytes())), 1)
        gradient = Image.linear_gradient("L").resize(ART_SIZE)
        result = quantize_art(gradient, 1.5, 1.2)
        self.assertTrue(set(result.tobytes()).issubset(set(range(16))))

    def test_full_cover_edges_survive_aspect_correction(self):
        from PIL import ImageDraw
        original = Image.new("L", (300, 300), 80)
        draw = ImageDraw.Draw(original)
        draw.rectangle((0, 0, 299, 19), fill=230)
        draw.rectangle((0, 280, 299, 299), fill=170)
        result = prepare_art(original)
        self.assertEqual(result.size, ART_SIZE)
        self.assertGreater(result.getpixel((80, 2)), 200)
        self.assertGreater(result.getpixel((80, ART_SIZE[1] - 3)), 150)
        # A landscape source is letterboxed, not cropped horizontally.
        landscape = Image.new("L", (300, 100), 200)
        result = prepare_art(landscape)
        self.assertEqual(result.getpixel((80, 0)), 0)
        self.assertEqual(result.getpixel((80, ART_SIZE[1] // 2)), 200)

    def test_long_titles_fit_and_indicate_truncation(self):
        value = "A LONGER PODCAST EPISODE TITLE THAT FITS"
        rows = title_lines(value)
        self.assertGreater(len(rows), 2)
        self.assertEqual(" ".join(rows), value)
        rows = title_lines("An extremely long episode title " * 10)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(len(row) <= 13 for row in rows))
        self.assertTrue(rows[-1].endswith(".."))

    def test_demo_pause_next_previous(self):
        provider = Demo()
        original = provider.poll()["title"]
        provider.control("toggle", {})
        paused = provider.poll()
        self.assertFalse(paused["is_playing"])
        provider.updated -= 10
        self.assertEqual(provider.poll()["progress_ms"], paused["progress_ms"])
        provider.control("next", {})
        self.assertNotEqual(provider.poll()["title"], original)
        provider.control("previous", {})
        self.assertEqual(provider.poll()["title"], original)

    def test_progress_clamps_at_duration(self):
        self.player.state = {"title": "Test", "is_playing": True, "progress_ms": 900, "duration_ms": 1000}
        self.player.updated -= 100
        self.assertEqual(self.player.snapshot()["progress_ms"], 1000)

    def test_idle_dims_blanks_and_playback_wakes(self):
        self.player.last_active -= 301
        self.assertTrue(self.player.snapshot()["dimmed"])
        self.player.last_active -= 1500
        self.assertTrue(self.player.snapshot()["blanked"])
        self.assertIsNone(self.player.frame().getbbox())
        self.assertIsNotNone(self.player.frame(calibration=True).getbbox())
        self.player.state = Demo().poll()
        self.assertFalse(self.player.snapshot()["blanked"])
        self.assertFalse(self.player.snapshot()["dimmed"])

    def test_settings_validate_ranges_and_nonfinite_numbers(self):
        self.assertEqual(validate_settings({"peak": 200, "motion": False}), {"peak": 200})
        self.player.settings_path.write_text(json.dumps({"peak": 170, "gamma": 1.4, "motion": True}))
        restored = Player(self.args)
        self.assertEqual((restored.settings["peak"], restored.settings["gamma"]), (170, 1.4))
        self.assertNotIn("motion", restored.settings)
        for value in ({"peak": 1000}, {"peak": True}, {"gamma": float("nan")}, {"other": 1}, []):
            with self.assertRaises(ValueError):
                validate_settings(value)

    def test_missing_cover_does_not_break_track_state(self):
        self.player.state = Demo().poll()
        self.player.load_art({"cover_path": str(self.path / "missing.png")}, self.player.provider)
        self.assertTrue(self.player.snapshot()["is_playing"])
        self.assertEqual(self.player.art_error, "Artwork unavailable")

    def test_json_feed_reads_relative_cover_and_rejects_bad_time(self):
        feed = self.path / "feed.json"
        feed.write_text(json.dumps({"title": "Track", "cover": "art.png", "is_playing": True}))
        state = JsonFeed(feed).poll()
        self.assertEqual(state["cover_path"], str((self.path / "art.png").resolve()))
        self.assertFalse(state["controls"])
        feed.write_text('{"progress_ms": "invalid"}')
        with self.assertRaises(ValueError):
            JsonFeed(feed).poll()

    def test_composite_scaling_accounts_for_nonsquare_framebuffer(self):
        self.assertEqual(target_rect(720, 480, 5), (648, 432))
        self.assertEqual(target_rect(1920, 1080, 0, True), (1440, 1080))

    def test_pkce_url_and_state_validation(self):
        auth = Authorization(self.path / "spotify.json")
        query = parse_qs(urlparse(auth.begin("a" * 32)).query)
        verifier = auth.pending[1]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge"], [challenge])
        self.assertEqual(query["redirect_uri"], ["http://127.0.0.1:8765/callback"])
        with self.assertRaises(ValueError):
            auth.finish({"state": ["wrong"], "code": ["test"]})
        self.assertFalse(auth.path.exists())

    def test_pkce_callback_saves_private_tokens(self):
        auth = Authorization(self.path / "spotify.json")
        query = parse_qs(urlparse(auth.begin("a" * 32)).query)
        with patch("spotify.request_json", return_value={"access_token": "fake-access", "refresh_token": "fake-refresh", "expires_in": 3600}):
            auth.finish({"state": query["state"], "code": ["fake-code"]})
        self.assertEqual(os.stat(auth.path).st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(auth.path.read_text())["client_id"], "a" * 32)

    def test_refresh_preserves_then_rotates_refresh_token(self):
        provider = Spotify(self.path / "spotify.json")
        provider.tokens = {"client_id": "a" * 32, "refresh_token": "original"}
        with patch("spotify.request_json", return_value={"access_token": "fake", "expires_in": 3600}):
            provider.refresh()
        self.assertEqual(provider.tokens["refresh_token"], "original")
        with patch("spotify.request_json", return_value={"access_token": "fake", "expires_in": 3600, "refresh_token": "rotated"}):
            provider.refresh()
        self.assertEqual(json.loads(provider.path.read_text())["refresh_token"], "rotated")

    def test_spotify_track_episode_and_no_playback(self):
        provider = Spotify(self.path / "spotify.json")
        item = {"name": "Track", "duration_ms": 200000, "artists": [{"name": "Artist"}],
                "album": {"name": "Album", "images": [{"url": "https://i.scdn.co/image/test", "width": 300}]}}
        with patch.object(provider, "api", return_value={"item": item, "is_playing": True, "progress_ms": 5000}):
            state = provider.poll()
        self.assertEqual((state["artist"], state["album"], state["progress_ms"]), ("Artist", "Album", 5000))
        episode = {"name": "Episode", "show": {"name": "Show", "publisher": "Host"}}
        with patch.object(provider, "api", return_value={"item": episode}):
            self.assertEqual(provider.poll()["artist"], "Host")
        with patch.object(provider, "api", return_value=None):
            self.assertEqual(provider.poll()["title"], "")

    def test_rate_limit_respects_retry_after(self):
        error = HTTPError("https://api.spotify.com", 429, "rate limited", {"Retry-After": "42"}, io.BytesIO())
        with patch("spotify.urlopen", side_effect=error):
            with self.assertRaises(SpotifyError) as result:
                request_json("https://api.spotify.com")
        self.assertEqual(result.exception.retry_after, 42)

    def test_restricted_device_control_is_rejected(self):
        self.player.state = {**Demo().poll(), "disallows": {"skipping_next": True}}
        with self.assertRaises(ValueError):
            self.player.control("next")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.player = Player(argparse.Namespace(source="demo", data=Path(self.temp.name), feed=None, port=8765))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.player = self.player
        self.player.start()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.player.stop.set()
        self.player.wake.set()
        self.player.thread.join(timeout=2)
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def post(self, path, value, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        return urlopen(Request(self.url + path, data=json.dumps(value).encode(), headers=headers), timeout=2)

    def test_http_frame_and_state_are_constrained(self):
        with urlopen(self.url + "/api/frame.png") as response:
            frame = Image.open(io.BytesIO(response.read()))
            self.assertEqual(frame.size, (280, 192))
            self.assertLessEqual(len(set(frame.tobytes())), 16)
        with urlopen(self.url + "/api/state") as response:
            state = json.load(response)
            self.assertNotIn("tokens", state)
        with urlopen(self.url + "/") as response:
            self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
            self.assertIn(b"Now, just listen", response.read())

    def test_http_settings_persist_and_bad_requests_are_rejected(self):
        with self.post("/api/settings", {"peak": 170}):
            pass
        restored = Player(self.player.args)
        self.assertEqual(restored.settings["peak"], 170)
        for path, data, origin, status in (("/api/settings", {"peak": 999}, None, 400),
                                         ("/api/settings", {"peak": 170}, "http://evil.example", 403),
                                         ("/api/control", {"action": "invalid"}, None, 400)):
            with self.assertRaises(HTTPError) as error:
                self.post(path, data, origin)
            self.assertEqual(error.exception.code, status)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/.data/spotify.json")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
