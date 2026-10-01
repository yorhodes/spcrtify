# Development and alternate sources

## Local JSON source and static renderer

An alternate feed accepts title, artist, album, progress / duration in
milliseconds, and `is_playing`. `cover` may be a path relative to the feed file.
Update the feed atomically so the poller never reads a half-written file.

```sh
python app.py --source json --feed now-playing.example.json
```

This source only displays state; controls are unavailable. The original
deterministic static renderer still works:

```sh
python render.py --cover /path/to/cover.jpg --out dist
```

It preserves the original layout / dithering for backward compatibility. The live
app's artwork is larger and has no added dithering. Copyrighted album artwork is
not bundled. The demo artwork and metadata are original placeholders.

## Checks

```sh
python -m unittest discover -s tests -v
node --check web/app.js
sh -n deploy/install.sh
sh -n deploy/start-kiosk.sh
```

Tests cover the signal palette and geometry, clean margins, artwork tone handling,
demo playback, idle / wake behavior, missing artwork, JSON feeds, Spotify track /
episode mapping, authentication, token refresh, rate limits, and the HTTP API.
Live Spotify and the composite hardware still require your account and Pi for
end-to-end verification.

MIT. See [LICENSE](../LICENSE).
