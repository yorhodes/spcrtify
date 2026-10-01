# SpCRTify

A live Spotify now-playing display for a Raspberry Pi Zero 2 W and an Apple
Monitor III. The CRT picture is deliberately small and quiet: a large square
album cover, track / artist / album, progress, and three playback controls.
No demo banner, display title, or footer appears in the playing picture.
Titles wrap up to five lines, with metadata moving down to fit. Decorative activity
bars animate during playback when space allows; they do not represent the audio
signal. Total durations of an hour or more use hours:minutes:seconds.

The Pi sends **grayscale**, not green. The Monitor III's phosphor gives the image
its color. A separate browser preview simulates the green screen and cabinet.

## Try it on your computer

```sh
git clone https://github.com/yorhodes/spcrtify.git
cd spcrtify
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open [the player](http://127.0.0.1:8765). Demo mode works immediately, with three
fictional tracks and original procedural artwork. Pause / previous / next work
in demo mode. Space and left / right arrows work too; C toggles calibration.

The **Monitor output** view shows the exact grayscale picture. **Tune display**
adjusts peak luminance, artwork contrast, shadow detail, and overscan margins.
Settings survive restarts. The picture focuses on artwork, track details, progress,
and playback controls.

## Connect Spotify

1. Create a Web API app in the [Spotify developer dashboard](https://developer.spotify.com/dashboard).
2. Add the exact redirect URI `http://127.0.0.1:8765/callback` to its settings.
3. In the player, click **Connect Spotify**, paste the Client ID, and sign in.
4. Start music on your Spotify speaker, phone, or computer. The Pi follows it.

This is a visual companion; it does not play audio or turn the Pi into a Spotify
Connect speaker. Playback controls target your currently active Spotify device.
Spotify development-mode apps require the app owner to have Premium; other
users must be on the app's allowlist. See [Spotify's current access rules](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).

Sign-in uses [PKCE](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)
and needs no client secret. Access and refresh tokens live only on the server in
`.data/spotify.json`, with owner-only permissions. Refresh is automatic, including
rotated refresh tokens. The app handles no active playback, account access errors,
network interruptions, and rate-limit backoff. Credentials are never sent to the
viewer. `.data/` is excluded from Git.

On later starts, the server automatically selects Spotify if a saved connection
exists. `--source spotify` selects it explicitly; `--source demo` always selects
the demo. Environment variables `SPOTIFY_CLIENT_ID` and `SPOTIFY_REFRESH_TOKEN`
are also supported for an existing PKCE connection.

## Pi Zero 2 W setup

Use Raspberry Pi OS with a desktop session, Wi-Fi, SSH, and desktop auto-login.
The Pi viewer uses **pygame / SDL**, keeping Chromium out of the 512 MB Pi's
normal display path. The browser remains useful on your laptop for sign-in and
display tuning. This setup has not yet been exercised on your physical Pi / CRT.

Clone the project on the Pi, then run:

```sh
sudo apt update
sudo apt install git python3-venv python3-pygame
git clone https://github.com/yorhodes/spcrtify.git ~/spcrtify
cd ~/spcrtify
sh deploy/install.sh
```

The installer creates a virtual environment that can use the OS pygame package,
installs Pillow, and installs two **user** services. The server starts at login;
the fullscreen viewer starts through a desktop autostart entry after the graphical
session is available. Both restart on failure. The installer does not edit boot
files or change the system's power settings. No root service is needed.

Enable **Desktop Autologin** in `sudo raspi-config`. Disable desktop screen
blanking there so that the app controls dimming / blanking and playback can wake
the picture without keyboard input. Reboot after setting up video and sign-in.

To sign into Spotify from your laptop while the server runs on the Pi, stop any
local server using port 8765 and open a tunnel (replace the user / hostname):

```sh
ssh -N -L 8765:127.0.0.1:8765 your-user@raspberrypi.local
```

Then open `http://127.0.0.1:8765` on your laptop and connect Spotify. The loopback
callback goes through the tunnel to the Pi. Tokens are saved on the Pi. Keep
that exact port on both ends; Spotify disallows `localhost` as a redirect URI.
[Spotify redirect rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)

Manual launch / service checks:

```sh
# The server normally runs as a user service after installation.
systemctl --user status monitor3-player.service monitor3-kiosk.service
journalctl --user -u monitor3-player -u monitor3-kiosk -n 50

# Manually test the native viewer in a graphical session.
.venv/bin/python kiosk.py
# For a modern desktop / HDMI display with square pixels:
.venv/bin/python kiosk.py --windowed --square-pixels

# Stop the kiosk before editing or signing in on the Pi itself.
systemctl --user stop monitor3-kiosk.service
systemctl --user start monitor3-kiosk.service
```

## Composite video and calibration

The Monitor III accepts a 1.0 V peak-to-peak composite signal through its video
input. It is an analog monochrome monitor, **not a fixed 280×192 pixel panel**.
The original Apple III computer's modes are separate from the monitor's limits.
The application uses **280×192 and at most 16 grayscale values** as an intentional
rendering budget. [Monitor III owner's manual](https://downloads.reactivemicro.com/Documentation/Manuals/Apple%20III%20Monitor%20III%20Owner%27s%20Manual.pdf)

On the Zero 2 W, composite video is available on the **TV test pads on the bottom
of the board**. Wire those to a suitable composite RCA connection and connect
the monitor's video input. HDMI alone cannot drive this input.
[Official Pi video documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html#composite-video-mode)

Use `sudo raspi-config` → Display Options → Composite if available. For current
KMS installations, the official configuration is to append `,composite` to the
existing overlay line in `/boot/firmware/config.txt`:

```ini
dtoverlay=vc4-kms-v3d,composite
```

The Zero family also needs `enable_tvout=1`. Keep the existing OS / board-specific
configuration and follow the official documentation for your installed version;
avoid adding a second duplicate overlay. Composite defaults to NTSC. For another
standard supported by your particular monitor, append `vc4.tv_norm=PAL` (or the
appropriate documented mode) to the **existing single line** in
`/boot/firmware/cmdline.txt`. Reboot after changing video configuration.

The native viewer maps the raster to the whole composite framebuffer, which is
physically displayed at 4:3 even if the framebuffer is 720×480. It uses nearest
neighbor scaling and equal RGB channels, so scaling adds no extra luminance
values. Album art compensates for the raster's non-square pixels and appears
square on the physical 4:3 screen. Full artwork is preserved before pixel-aspect
correction; non-square covers are letterboxed instead of cropped. The browser kiosk view is intended for modern
square-pixel previews; use the native viewer for actual composite output.

Start with the 5% safe-edge margin and 80% digital peak. The latter is a code
value ceiling (204 / 255), not a measured luminance or electrical voltage. Press C
for the 16-step calibration pattern. Adjust the monitor's brightness until black
stays black, then contrast so the upper steps remain separate. Use the app's
controls to recover artwork shadows or reduce bloom. The active picture has no
simulated scanlines, vignette, color tint, or added dithering.

## Startup and power

The simplest daily arrangement is to **leave the Pi powered and switch the CRT
with its own power switch**. The Pi stays connected and the screen follows the
current Spotify state when you turn the monitor on. Use a reliable 5 V / 2.5 A
micro-USB supply for the Zero 2 W.
[Official Pi power guidance](https://www.raspberrypi.com/documentation/computers/getting-started.html)

Startup sequence: power → Pi boot → desktop auto-login → server / viewer launch
→ Spotify token refresh → current track. Wi-Fi or Spotify may take longer than
the local display; it shows a waiting picture and retries. Startup follows your
existing playback; it does not automatically start music.

Idle behavior:

- Playing: normal luminance. Resuming playback wakes the picture.
- Paused / no playback for five minutes: 30% of the selected peak.
- Idle for thirty minutes: completely black signal.
- Local viewer loses the server for thirty seconds: black instead of a frozen image.

Blanking does **not** turn off the CRT or disconnect its power. Use its switch to
turn it off overnight. Neither the app nor composite video can operate that switch.

To remove Pi power, shut down first:

```sh
ssh your-user@raspberrypi.local sudo poweroff
```

Wait for shutdown to complete before unplugging its supply. A Zero 2 W does not
disconnect its own 5 V supply when Linux halts. If you want one button for both
devices, use an external power controller that requests Pi shutdown, confirms it
has halted, and then cuts power. On power restoration the startup services bring
the display back. A shared switched outlet by itself does not provide graceful
Pi shutdown. [Official shutdown guidance](https://www.raspberrypi.com/documentation/computers/getting-started.html)

For a later appliance build, a read-only root / overlay filesystem can reduce
writes, but `.data/spotify.json` and display settings still need durable writable
storage because Spotify refresh tokens can rotate. Configure and test that after
the normal setup works.

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

MIT. See [LICENSE](LICENSE).
