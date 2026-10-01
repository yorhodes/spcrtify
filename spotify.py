"""Spotify Web API and loopback PKCE sign-in. Tokens stay on the server."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCOPES = "user-read-playback-state user-read-currently-playing user-modify-playback-state"


class SpotifyError(Exception):
    def __init__(self, message, retry_after=5):
        super().__init__(message)
        self.retry_after = retry_after


def request_json(url, method="GET", data=None, headers=None):
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            body = response.read(2 * 1024 * 1024)
            return json.loads(body) if body else None
    except HTTPError as error:
        if error.code == 429:
            raise SpotifyError("Spotify rate limit; waiting to retry", max(5, int(error.headers.get("Retry-After", 30))))
        messages = {401: "Spotify sign-in expired", 403: "Spotify access denied; check account and app access",
                    404: "Open Spotify and start playback on a device"}
        raise SpotifyError(messages.get(error.code, f"Spotify request failed ({error.code})")) from None
    except (OSError, ValueError):
        raise SpotifyError("Cannot reach Spotify; retrying") from None


def save_tokens(path: Path, tokens: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    # Never create a world-readable token file, including the temporary write.
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(temporary, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(tokens, stream)
    temporary.replace(path)


class Authorization:
    def __init__(self, path: Path, port=8765):
        self.path = path
        self.redirect = f"http://127.0.0.1:{port}/callback"
        self.pending = None

    def begin(self, client_id: str) -> str:
        if len(client_id) != 32 or not all(c in "0123456789abcdef" for c in client_id.lower()):
            raise ValueError("Enter the 32-character Client ID from your Spotify app")
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        self.pending = (client_id, verifier, state, time.monotonic())
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return "https://accounts.spotify.com/authorize?" + urlencode({
            "client_id": client_id, "response_type": "code", "redirect_uri": self.redirect,
            "scope": SCOPES, "state": state, "code_challenge_method": "S256", "code_challenge": challenge})

    def finish(self, query: dict) -> dict:
        pending, self.pending = self.pending, None
        if not pending or time.monotonic() - pending[3] > 600:
            raise ValueError("Sign-in timed out. Please try again.")
        client_id, verifier, state, _ = pending
        if not secrets.compare_digest(query.get("state", [""])[0], state):
            raise ValueError("Sign-in state did not match. Please try again.")
        if "error" in query or not query.get("code"):
            raise ValueError("Spotify sign-in was cancelled.")
        tokens = request_json("https://accounts.spotify.com/api/token", "POST", urlencode({
            "grant_type": "authorization_code", "client_id": client_id,
            "code": query["code"][0], "redirect_uri": self.redirect, "code_verifier": verifier}).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"})
        tokens.update(client_id=client_id, expires_at=time.time() + tokens["expires_in"])
        save_tokens(self.path, tokens)
        return tokens


class Spotify:
    name = "Spotify"
    interval = 5

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        try:
            self.tokens = json.loads(path.read_text())
        except (OSError, ValueError):
            self.tokens = {}
        self.tokens.setdefault("client_id", os.environ.get("SPOTIFY_CLIENT_ID", ""))
        self.tokens.setdefault("refresh_token", os.environ.get("SPOTIFY_REFRESH_TOKEN", ""))

    def api(self, route: str, method="GET"):
        with self.lock:
            if not self.tokens.get("refresh_token") or not self.tokens.get("client_id"):
                raise SpotifyError("Connect Spotify to start", 10)
            if time.time() >= self.tokens.get("expires_at", 0) - 60:
                self.refresh()
            for attempt in range(2):
                try:
                    return request_json("https://api.spotify.com/v1/" + route, method,
                                        b"" if method != "GET" else None,
                                        {"Authorization": "Bearer " + self.tokens["access_token"]})
                except SpotifyError as error:
                    if str(error) == "Spotify sign-in expired" and attempt == 0:
                        self.refresh()
                    else:
                        raise

    def refresh(self):
        fresh = request_json("https://accounts.spotify.com/api/token", "POST", urlencode({
            "grant_type": "refresh_token", "refresh_token": self.tokens["refresh_token"],
            "client_id": self.tokens["client_id"]}).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"})
        self.tokens.update(fresh)
        self.tokens["expires_at"] = time.time() + fresh["expires_in"]
        save_tokens(self.path, self.tokens)

    def poll(self):
        data = self.api("me/player?additional_types=episode")
        if not data or not data.get("item"):
            return {"source": "SPOTIFY", "is_playing": False, "title": ""}
        item = data["item"]
        album = item.get("album") or item.get("show") or {}
        images = album.get("images") or item.get("images") or []
        image = min(images, key=lambda entry: abs((entry.get("width") or 300) - 300)) if images else {}
        artists = ", ".join(artist["name"] for artist in item.get("artists", [])) or album.get("publisher", "")
        return {"source": "SPOTIFY", "title": item.get("name", "Untitled"), "artist": artists,
                "album": album.get("name", ""), "duration_ms": item.get("duration_ms", 0),
                "progress_ms": data.get("progress_ms") or 0, "is_playing": data.get("is_playing", False),
                "cover_url": image.get("url", ""), "track_url": item.get("external_urls", {}).get("spotify", ""),
                "controls": not data.get("device", {}).get("is_restricted", False),
                "disallows": data.get("actions", {}).get("disallows", {})}

    def control(self, action: str, state: dict):
        route, method = {"toggle": ("pause" if state.get("is_playing") else "play", "PUT"),
                         "next": ("next", "POST"), "previous": ("previous", "POST")}[action]
        self.api("me/player/" + route, method)
