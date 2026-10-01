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

On the Pi image, scan the display’s QR with a phone on the same Wi-Fi, approve
Spotify access, then tap **Return to Spcrtify**. The Pi remembers the connection
after restarting. Audio stays on your existing Spotify device.

For local development, register `http://127.0.0.1:8765/callback` in your
[Spotify app](https://developer.spotify.com/dashboard), click **Connect Spotify**,
and use its Client ID. The included public app ID works only for accounts
allowlisted by the app owner; the owner needs Spotify Premium.

Sign-in uses PKCE without a client secret. Tokens stay on the Pi. The small
HTTPS callback is hosted on GitHub Pages and can move to any static HTTPS host.
See [phone sign-in and callback setup](docs/login.md).

## Run on the Pi

Use the [ready-to-flash image](docs/image.md) for automatic startup, crash recovery, composite NTSC output, and graceful shutdown. Add Wi-Fi and SSH access locally before flashing, then use QR sign-in on first boot. You can also seed an existing Spotify connection to skip that sign-in.

The public image contains no credentials. A private image or personalized SD card contains your credentials and should stay private. The image build is tested separately from the physical Pi / CRT, which still needs verification on your hardware.

For an existing Raspberry Pi OS desktop installation, see the [manual Pi setup guide](docs/pi-setup.md).

[Development, tests, and alternate sources](docs/development.md) · [MIT license](LICENSE)
