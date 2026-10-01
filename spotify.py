"""Spotify Web API and loopback PKCE sign-in. Tokens stay on the server."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from onboarding import local_url

SCOPES = "user-read-playback-state user-read-currently-playing user-modify-playback-state"


class SpotifyError(Exception):
    def __init__(self, message, retry_after=5):
        super().__init__(message)
        self.retry_after = retry_after


class SpotifyReauthorization(SpotifyError):
    """A rejected refresh token needs a new login, not another refresh attempt."""


def request_json(url, method="GET", data=None, headers=None):
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            body = response.read(2 * 1024 * 1024)
            return json.loads(body) if body else None
    except HTTPError as error:
        if error.code == 400:
            try:
                body = json.loads(error.read(4096))
            except (ValueError, OSError):
                body = {}
            if isinstance(body, dict) and body.get("error") == "invalid_grant":
                raise SpotifyReauthorization("Reconnect Spotify to continue", 10) from None
        if error.code == 429:
            raise SpotifyError("Spotify rate limit; waiting to retry", max(5, int(error.headers.get("Retry-After", 30))))
        messages = {401: "Spotify sign-in expired", 403: "Spotify access denied; check account and app access",
                    404: "Open Spotify and start playback on a device"}
        raise SpotifyError(messages.get(error.code, f"Spotify request failed ({error.code})")) from None
    except (OSError, ValueError):
        raise SpotifyError("Cannot reach Spotify; retrying") from None


def save_tokens(path: Path, tokens: dict):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    # Never create a world-readable token file, including the temporary write.
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(temporary, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(tokens, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class Authorization:
    def __init__(self, path: Path, port=8765, relay_redirect=None):
        self.path = path
        self.redirect = f"http://127.0.0.1:{port}/callback"
        self.pending = None
        self.lock = threading.RLock()
        if relay_redirect:
            parsed = urlparse(relay_redirect)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment):
                raise ValueError("The Spotify callback must be an HTTPS URL")
        self.relay_redirect = relay_redirect

    def begin(self, client_id: str, return_to=None) -> str:
        if not isinstance(client_id, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", client_id):
            raise ValueError("Enter the 32-character Client ID from your Spotify app")
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        redirect = self.redirect
        if return_to:
            if not self.relay_redirect:
                raise ValueError("Configure an HTTPS Spotify callback before phone sign-in")
            return_to = local_url(return_to, "/callback")
            state = base64.urlsafe_b64encode(json.dumps({"v": 1, "return_to": return_to, "nonce": state},
                                                       separators=(",", ":")).encode()).rstrip(b"=").decode()
            redirect = self.relay_redirect
        with self.lock:
            # Reusing a live session makes double taps harmless. Another phone
            # cannot replace the proof while someone is approving on Spotify.
            if self.pending and time.monotonic() - self.pending[3] < 600:
                if self.pending[0] != client_id or self.pending[4] != redirect or self.pending[5] != return_to:
                    raise ValueError("A Spotify sign-in is already in progress. Finish it or wait ten minutes.")
                client_id, verifier, state, _, redirect, _ = self.pending
            else:
                self.pending = (client_id, verifier, state, time.monotonic(), redirect, return_to)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return "https://accounts.spotify.com/authorize?" + urlencode({
            "client_id": client_id, "response_type": "code", "redirect_uri": redirect,
            "scope": SCOPES, "state": state, "code_challenge_method": "S256", "code_challenge": challenge})

    def finish(self, query: dict) -> dict:
        with self.lock:
            pending = self.pending
            if not pending or time.monotonic() - pending[3] >= 600:
                self.pending = None
                raise ValueError("Sign-in timed out. Scan the display again.")
            client_id, verifier, state, _, redirect, _ = pending
            received = query.get("state", [])
            if (len(received) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", received[0])
                    or not secrets.compare_digest(received[0], state)):
                # An unrelated callback must not cancel a valid sign-in.
                raise ValueError("Sign-in state did not match. Please try again.")
            self.pending = None
            if "error" in query or len(query.get("code", [])) != 1 or not query["code"][0]:
                raise ValueError("Spotify sign-in was cancelled. Scan the display to try again.")
            tokens = request_json("https://accounts.spotify.com/api/token", "POST", urlencode({
                "grant_type": "authorization_code", "client_id": client_id,
                "code": query["code"][0], "redirect_uri": redirect, "code_verifier": verifier}).encode(),
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
        self.retired = False
        try:
            self.tokens = json.loads(path.read_text())
        except (OSError, ValueError):
            self.tokens = {}
        self.tokens.setdefault("client_id", os.environ.get("SPOTIFY_CLIENT_ID", ""))
        self.tokens.setdefault("refresh_token", os.environ.get("SPOTIFY_REFRESH_TOKEN", ""))

    def api(self, route: str, method="GET"):
        with self.lock:
            if self.retired:
                raise SpotifyError("Spotify connection changed")
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
        try:
            fresh = request_json("https://accounts.spotify.com/api/token", "POST", urlencode({
                "grant_type": "refresh_token", "refresh_token": self.tokens["refresh_token"],
                "client_id": self.tokens["client_id"]}).encode(),
                {"Content-Type": "application/x-www-form-urlencoded"})
        except SpotifyReauthorization:
            client_id = self.tokens.get("client_id", "")
            self.tokens.clear()
            # Keep the public app ID so reconnecting still uses the same app,
            # including after a reboot. Expired access/refresh tokens are gone.
            if client_id:
                self.tokens["client_id"] = client_id
            save_tokens(self.path, self.tokens)
            raise
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
