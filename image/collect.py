"""Collect only public image artifacts, and record their provenance."""
import hashlib
import json
from pathlib import Path
import shutil
import sys


def main():
    source, target = map(Path, sys.argv[1:3])
    images = list(source.glob("*spcrtify*.img.xz"))
    if not images:
        raise SystemExit("No Spcrtify image was exported")
    target.mkdir(parents=True, exist_ok=True)
    image = target / "spcrtify-zero2w-arm64.img.xz"
    shutil.copy2(max(images, key=lambda path: path.stat().st_mtime), image)
    with image.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (target / "SHA256SUMS").write_text(f"{digest}  {image.name}\n")
    for info in source.glob("*spcrtify*.info"):
        shutil.copy2(info, target / "packages.info")
    (target / "manifest.json").write_text(json.dumps({
        "image": image.name, "sha256": digest, "pi_gen_commit": sys.argv[3],
        "app_commit": sys.argv[4], "os": "Raspberry Pi OS Trixie arm64",
        "board": "Raspberry Pi Zero 2 W", "video": "composite NTSC",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
