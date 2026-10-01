#!/usr/bin/env bash
# Build a PERSONAL image locally, never through GitHub Actions.
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$#" -lt 2 ]; then
  echo 'Usage: bash image/make-private.sh BASE.img.xz OUTPUT_DIRECTORY --ssh-key KEY.pub --wifi-ssid SSID [--spotify-from spotify.json] [other personalize.py options]' >&2
  exit 1
fi
base=$(python3 -c 'import pathlib,sys;print(pathlib.Path(sys.argv[1]).resolve())' "$1")
output=$2
shift 2
mkdir -p "$output"
output=$(CDPATH='' cd -- "$output" && pwd)
if [ -e "$output/spcrtify-personal.img.xz" ] || [ -e "$output/spcrtify-personal.img" ]; then
  echo 'Choose an empty output directory; existing images are never overwritten.' >&2
  exit 1
fi
seed=$(mktemp -d "${TMPDIR:-/tmp}/spcrtify-private.XXXXXX")
trap 'rm -rf "$seed"' EXIT
touch "$seed/config.txt" "$seed/cmdline.txt"
python3 "$project/image/personalize.py" --boot "$seed" "$@"
echo 'Creating personal image locally. Do not upload or share this image.'
docker build -t spcrtify-personalizer -f "$project/image/Personalizer.Dockerfile" "$project/image"
docker run --rm --privileged \
  --mount "type=bind,source=$base,target=/base.img.xz,readonly" \
  --mount "type=bind,source=$seed,target=/seed,readonly" \
  --mount "type=bind,source=$output,target=/output" \
  spcrtify-personalizer
echo "Personal image: $output/spcrtify-personal.img.xz"
