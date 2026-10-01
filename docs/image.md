# Spcrtify image

An appliance image for the Raspberry Pi Zero 2 W: Raspberry Pi OS Trixie arm64,
a minimal X11 display session, and Spcrtify. No browser or full desktop is needed.
Composite NTSC is configured by default. The Zero 2 W's TV pads still need a
physical cable to the Monitor III. Use a microSD card of at least 8 GB.

## Build or download

In GitHub, open **Actions → Build Pi image → Run workflow**. Download the
`spcrtify-zero2w-arm64` artifact when the build completes and unzip it. It contains
`spcrtify-zero2w-arm64.img.xz`, `SHA256SUMS`, a manifest identifying the source
commits, and the installed package list. Artifacts remain available for 14 days.

To build locally, use Docker on an ARM64 Mac or Linux machine:

```sh
bash image/build.sh
```

The build uses a pinned [official pi-gen revision](https://github.com/RPi-Distro/pi-gen),
Raspberry Pi OS Lite stages, and the custom `stage-spcrtify`. uv syncs the app's
locked dependencies into a virtual environment around the OS Python and pygame.
The build runs app tests inside the ARM root filesystem before exporting the
compressed image. Debian package repositories can change; the manifest and
package list record what was used, but the image is not byte-for-byte reproducible.

The builder uses a privileged Linux container for filesystem mounts. Output is in
`dist/image/`; build containers and working files are local and are not published.
If a build fails, inspect `.image-build/pi-gen/deploy/build-docker.log` or
`docker logs spcrtify-image-build`. Remove that stopped container before retrying:
`docker rm -v spcrtify-image-build`.

## Option A: personalize the card

1. Verify `SHA256SUMS` (`shasum -a 256 -c SHA256SUMS` on macOS).
2. In Raspberry Pi Imager, choose **Use custom** and select the `.img.xz`.
3. Flash the card. Configure it with the script below instead of Imager's OS customization.
4. Reinsert the card so its `bootfs` partition mounts. Personalize it **before first boot**.

```sh
uv run image/personalize.py \
  --boot /Volumes/bootfs \
  --username operator \
  --hostname spcrtify \
  --ssh-key ~/.ssh/id_ed25519.pub \
  --wifi-ssid 'Your Wi-Fi' \
  --country US \
  --timezone America/New_York \
  --spotify-from .data/spotify.json
```

The script prompts for the Wi-Fi password. Use a public SSH key; if you need one,
run `ssh-keygen -t ed25519`. Adjust the boot path on Linux. Omit `--spotify-from`
to connect Spotify later. Add `--video hdmi` for an HDMI test screen, or
`--shutdown-button` if you wire a momentary button between GPIO3 and GND.

Configuration uses Raspberry Pi OS cloud-init to create your administrator and
join Wi-Fi. The service account is separate and has no SSH access. There is no
shared default password. Eject the card, insert it in the Pi, and apply power.

## Option B: make your own private flashable image

To bake the same settings into an image locally, before flashing:

```sh
bash image/make-private.sh \
  dist/image/spcrtify-zero2w-arm64.img.xz \
  image/private \
  --ssh-key ~/.ssh/id_ed25519.pub \
  --wifi-ssid 'Your Wi-Fi' \
  --username operator \
  --country US \
  --timezone America/New_York \
  --spotify-from .data/spotify.json
```

This copies the base image, mounts its boot partition inside Docker, inserts the
configuration, and compresses the result. Flash `image/private/spcrtify-personal.img.xz`.
Existing images are never overwritten. Public GitHub builds exclude all tokens,
Wi-Fi passwords, private images, and local settings. Private images belong only
on your own storage; they contain credentials. The runtime import moves the
Spotify seed into `/var/lib/spcrtify/spotify.json` with owner-only permissions,
syncs it to storage, and removes the seed from the boot partition.

Baking a connection skips another sign-in, not OAuth itself: you need an existing
Spotify authorization. The Pi renews access tokens automatically. Spotify
[limits refresh tokens to six months](https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens),
after which you need to reconnect. You also need to reconnect if access is revoked.

## Power-up and recovery

Power → Linux boot → server and display session → fullscreen viewer → Spotify.
The server starts independently of the network. An authorized image retries
Spotify while Wi-Fi comes up; an unconnected image starts in demo mode.
Nothing automatically starts or transfers music playback.

The server and viewer restart after crashes. Their event loops send heartbeats;
if one stops responding for 20 seconds, systemd restarts it. The display session
also restarts if its display manager exits. A hardware watchdog can reboot the
Pi if systemd stops feeding it for 30 seconds. None of these mechanisms guarantees
recovery from every hardware fault; validate them on your Pi before leaving it unattended.

Playing wakes the image. Five minutes idle dims it; thirty minutes blanks it.
A disconnected viewer blanks after thirty seconds rather than retaining a frozen
picture. Journals live in RAM, limited to 16 MB. Spotify tokens and settings remain
on writable persistent storage; the root filesystem is not an overlay filesystem.

## Wi-Fi setup page and maintenance

Open `http://spcrtify.local:8765` from a device on the same Wi-Fi to view the
player and tune it. Port 8765 is filtered to Wi-Fi and loopback; it is unavailable
on other interfaces. Anyone on that Wi-Fi can view and control playback. Do not
forward it through your router.

When no Spotify connection is saved, the display shows a QR for phone sign-in.
Scan it on the same Wi-Fi, approve Spotify access, and tap **Return to Spcrtify**.
The public HTTPS callback carries only the temporary authorization code back to
your local Pi; the Pi exchanges it directly with Spotify. The QR stays readable
while disconnected; normal idle dimming resumes after connection. A temporary
network outage retains saved tokens and retries. An expired or revoked refresh
token brings the QR back.

The app owner must register `https://yorhodes.github.io/spcrtify/callback.html`
as a redirect URI. For another Spotify app or callback host, see
[login configuration](login.md). The image includes only the public Client ID and
callback address, never a client secret or account tokens.

An SSH tunnel remains available for local browser sign-in or maintenance:

```sh
ssh -N -L 8765:127.0.0.1:8765 operator@spcrtify.local
```

Open [127.0.0.1:8765](http://127.0.0.1:8765); local sign-in uses the loopback
callback. Stop your laptop’s local player first so port 8765 is free.

```sh
ssh operator@spcrtify.local
systemctl status spcrtify-player.service lightdm.service
sudo journalctl -u spcrtify-player -u lightdm -n 50
sudo systemctl restart spcrtify-player
sudo journalctl _SYSTEMD_USER_UNIT=spcrtify-viewer.service -n 50
```

For recovery testing, `sudo systemctl kill --signal=SIGSTOP spcrtify-player`
should trigger a watchdog restart; `sudo systemctl kill --signal=SIGKILL spcrtify-player`
should trigger crash recovery. Check for a new process ID and a working preview.
Test loss of Wi-Fi and reconnection separately. These checks are intended for your
Pi, not the computer used to build the image.

Leave the Pi powered and use the CRT's own switch for daily use. To remove Pi power:

```sh
ssh operator@spcrtify.local sudo poweroff
```

Wait until shutdown completes before unplugging. The optional GPIO3 button requests
the same graceful shutdown; it does not cut 5 V or operate the monitor's switch.
Restoring the supply boots the image automatically. A shared outlet that cuts Pi
power without shutdown can still corrupt the card.

The image uses `/opt/spcrtify` for code and `/var/lib/spcrtify` for credentials and
settings. Before reflashing, copy the latter securely over SSH if you want to keep
its connection. Keep backups private. The existing desktop installer continues to
use the `monitor3-player` and `monitor3-kiosk` user services; the image has separate
system/server and user/viewer service names.

## Hardware validation

A successful build validates the ARM dependencies, HTTP server, and exported
filesystem. It does not prove the first-boot Wi-Fi setup, X11 composite output,
GPIO button, hardware watchdog, or safe shutdown on your physical board. Verify
all of those on the Zero 2 W and Monitor III before considering the appliance finished.

References: [Pi composite output](https://www.raspberrypi.com/documentation/computers/config_txt.html#composite-video-mode),
[cloud-init networking](https://docs.cloud-init.io/en/latest/reference/network-config-format-v2.html),
[uv](https://docs.astral.sh/uv/).
