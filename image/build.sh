#!/usr/bin/env bash
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
workspace=${SPCRTIFY_BUILD_DIR:-"$project/.image-build"}
case "$workspace" in *' '*) echo 'Image build paths must not contain spaces.' >&2; exit 1;; esac
command -v docker >/dev/null
docker info >/dev/null
mkdir -p "$workspace"
ref=$(cat "$project/image/pi-gen.ref")
if [ ! -d "$workspace/pi-gen/.git" ]; then
  git clone --no-checkout https://github.com/RPi-Distro/pi-gen.git "$workspace/pi-gen"
fi
git -C "$workspace/pi-gen" checkout --detach "$ref"
builder="$workspace/pi-gen"
cp "$project/image/config" "$builder/config"
# Pin the Astral binary in the builder and copy it into the ARM rootfs.
if ! grep -q 'ghcr.io/astral-sh/uv:' "$builder/Dockerfile"; then
  printf '\nCOPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv\n' >> "$builder/Dockerfile"
fi
mkdir -p "$builder/stage-spcrtify"
cp -R "$project/image/stage-spcrtify/." "$builder/stage-spcrtify/"
mkdir -p "$builder/stage-spcrtify/00-install/files/app"
# Explicit source allowlist: credentials, local settings, and generated files
# can never enter the image, even if they are present in the working directory.
git -C "$project" archive HEAD app.py display.py kiosk.py render.py spotify.py \
  systemd_notify.py web tests LICENSE pyproject.toml uv.lock .python-version now-playing.example.json \
  | tar -xf - -C "$builder/stage-spcrtify/00-install/files/app"
cp "$project/image/boot_config.py" "$builder/stage-spcrtify/00-install/files/boot_config.py"
git -C "$project" rev-parse HEAD > "$builder/stage-spcrtify/00-install/files/app/version.txt"
touch "$builder/stage2/SKIP_IMAGES"
chmod +x "$builder/stage-spcrtify/prerun.sh" "$builder/stage-spcrtify/00-install/00-run.sh"
cd "$builder"
./build-docker.sh
mkdir -p "$project/dist/image"
python3 "$project/image/collect.py" "$builder/deploy" "$project/dist/image" "$ref" "$(git -C "$project" rev-parse HEAD)"
echo "Image and checksum: $project/dist/image"
