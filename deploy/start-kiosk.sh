#!/bin/sh
set -eu
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR
exec systemctl --user start monitor3-kiosk.service
