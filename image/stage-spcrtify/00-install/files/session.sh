#!/bin/sh
set -eu
xset s off
xset -dpms
xsetroot -solid black
systemctl --user import-environment DISPLAY XAUTHORITY
trap 'systemctl --user stop spcrtify-viewer.service' EXIT
systemctl --user start --wait spcrtify-viewer.service
