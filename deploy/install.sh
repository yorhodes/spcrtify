#!/bin/sh
# Run on the Pi, as the desktop user. Changes only this user's startup entries.
set -eu
project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
case "$project" in
  *[!a-zA-Z0-9_./-]*) echo "Use an install path containing only letters, numbers, slashes, dots, underscores, and hyphens." >&2; exit 1 ;;
esac
python3 -m venv --system-site-packages "$project/.venv"
"$project/.venv/bin/python" -m pip install -r "$project/requirements.txt"
"$project/.venv/bin/python" -c 'import pygame; from PIL import Image' >/dev/null
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/autostart"
for name in monitor3-player monitor3-kiosk; do
  sed "s|@PROJECT@|$project|g" "$project/deploy/$name.service" > "$HOME/.config/systemd/user/$name.service"
done
chmod +x "$project/deploy/start-kiosk.sh"
cat > "$HOME/.config/autostart/monitor3-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Monitor III Player
Exec=$project/deploy/start-kiosk.sh
Terminal=false
EOF
systemctl --user daemon-reload
systemctl --user enable --now monitor3-player.service
echo "Server installed. Sign into Spotify, then log out and back in to start the fullscreen display."
echo "Stop display: systemctl --user stop monitor3-kiosk.service"
