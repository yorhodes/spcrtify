"""Personalize a copy of the FAT boot partition, without touching the source."""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess

from boot_config import configure


def main():
    image = Path('/output/spcrtify-personal.img')
    descriptor = os.open(image, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        subprocess.run(['xz', '-dc', '/base.img.xz'], stdout=stream, check=True)
    with image.open('rb') as stream:
        mbr = stream.read(512)
    if mbr[510:512] != b'\x55\xaa' or mbr[450] not in (0x0b, 0x0c):
        raise ValueError('Expected a Raspberry Pi image with FAT32 as the first partition')
    offset = struct.unpack_from('<I', mbr, 454)[0] * 512
    # Docker Desktop exposes the Linux VM's loop driver, but device nodes may
    # not exist inside this container. Create nodes, never detach others' loops.
    for index in range(64):
        path = Path('/dev/loop' + str(index))
        if not path.exists():
            os.mknod(path, 0o60600, os.makedev(7, index))
    boot = Path('/mnt/boot')
    boot.mkdir(parents=True, exist_ok=True)
    subprocess.run(['mount', '-t', 'vfat', '-o', f'loop,offset={offset}', str(image), str(boot)], check=True)
    try:
        seed = Path('/seed')
        for name in ['user-data', 'network-config', 'meta-data', 'spcrtify-spotify.json']:
            if (seed / name).exists():
                shutil.copy2(seed / name, boot / name)
        config = (seed / 'config.txt').read_text()
        configure(boot, 'composite' if 'enable_tvout=1' in config else 'hdmi', 'gpio-shutdown' in config)
    finally:
        subprocess.run(['umount', str(boot)], check=True)
    subprocess.run(['xz', '-T0', '-3', str(image)], check=True)
    compressed = image.with_suffix('.img.xz')
    with compressed.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    Path('/output/SHA256SUMS').write_text(f'{digest}  {compressed.name}\n')
    for result in [compressed, Path('/output/SHA256SUMS')]:
        os.chmod(result, 0o600)
        os.chown(result, int(os.environ.get('LOCAL_UID', '0')), int(os.environ.get('LOCAL_GID', '0')))


if __name__ == '__main__':
    main()
