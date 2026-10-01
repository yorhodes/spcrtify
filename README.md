# Spcrtify

A Spotify now-playing display for the Apple Monitor III, powered by a Raspberry Pi Zero 2 W.

![Spcrtify animated phosphor preview](docs/preview.gif)

*[Come Together — Remastered 2009, The Beatles](https://open.spotify.com/track/2EqlS6tkEnglzr7tkKAAYD). Rendered preview; the Pi outputs grayscale and the monitor supplies the green phosphor glow.*

Large album art, wrapping titles, playback controls, and decorative activity bars in a 280 × 192 picture with 16 luminance levels. The bars animate while playing; they do not analyze the audio. Music plays on your existing Spotify device.

## Try it locally

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/yorhodes/spcrtify.git
cd spcrtify
uv run app.py
```

Open [127.0.0.1:8765](http://127.0.0.1:8765). Demo mode works immediately. Use **Tune display** to adjust brightness, artwork, and safe edges. Space pauses; the arrow keys skip; C shows calibration.

## Connect Spotify

1. Create an app in the [Spotify developer dashboard](https://developer.spotify.com/dashboard).
2. Register `http://127.0.0.1:8765/callback` as its redirect URI.
3. Click **Connect Spotify**, enter the Client ID, and sign in.

The app owner needs Spotify Premium; additional users must be allowlisted. Sign-in uses PKCE with no client secret. Tokens stay in the ignored `.data/` directory and refresh automatically, including after restarts.

## Run on the Pi

Use the [ready-to-flash image](docs/image.md) for automatic startup, crash recovery, composite NTSC output, and graceful shutdown. You can add Wi-Fi, SSH access, and an existing Spotify connection locally before flashing, so first boot needs no Spotify login.

The public image contains no credentials. A private image or personalized SD card contains your credentials and should stay private. The image build is tested separately from the physical Pi / CRT, which still needs verification on your hardware.

For an existing Raspberry Pi OS desktop installation, see the [manual Pi setup guide](docs/pi-setup.md).

[Development, tests, and alternate sources](docs/development.md) · [MIT license](LICENSE)
