#!/bin/bash -e
install -d "${ROOTFS_DIR}/opt/spcrtify"
install -m 755 /usr/local/bin/uv "${ROOTFS_DIR}/usr/local/bin/uv"
cp -R files/app/. "${ROOTFS_DIR}/opt/spcrtify/"
install -D -m 644 files/spcrtify-player.service "${ROOTFS_DIR}/etc/systemd/system/spcrtify-player.service"
install -D -m 644 files/spcrtify-provision.service "${ROOTFS_DIR}/etc/systemd/system/spcrtify-provision.service"
install -D -m 755 files/first_boot.py "${ROOTFS_DIR}/usr/local/lib/spcrtify-first-boot.py"
install -D -m 644 files/lightdm.conf "${ROOTFS_DIR}/etc/lightdm/lightdm.conf.d/90-spcrtify.conf"
install -D -m 644 files/lightdm-restart.conf "${ROOTFS_DIR}/etc/systemd/system/lightdm.service.d/90-spcrtify.conf"
install -D -m 644 files/spcrtify.desktop "${ROOTFS_DIR}/usr/share/xsessions/spcrtify.desktop"
install -D -m 755 files/session.sh "${ROOTFS_DIR}/usr/local/bin/spcrtify-session"
install -D -m 644 files/watchdog.conf "${ROOTFS_DIR}/etc/systemd/system.conf.d/90-spcrtify.conf"
install -D -m 644 files/journal.conf "${ROOTFS_DIR}/etc/systemd/journald.conf.d/90-spcrtify.conf"
install -D -m 644 files/sshd.conf "${ROOTFS_DIR}/etc/ssh/sshd_config.d/90-spcrtify.conf"
install -D -m 644 files/nftables.conf "${ROOTFS_DIR}/etc/nftables.conf"
python3 files/boot_config.py "${ROOTFS_DIR}/boot/firmware"
on_chroot <<'CHROOT'
usermod -L pi
usermod -s /usr/sbin/nologin pi
if ! id spcrtify >/dev/null 2>&1; then
  useradd --create-home --user-group --home-dir /var/lib/spcrtify --shell /bin/bash --groups video,render,input spcrtify
fi
usermod -L spcrtify
install -d -m 700 -o spcrtify -g spcrtify /var/lib/spcrtify
install -d -m 755 -o spcrtify -g spcrtify /var/lib/spcrtify/.config/systemd/user
systemctl enable spcrtify-player.service lightdm.service ssh.service avahi-daemon.service nftables.service
systemctl set-default graphical.target
# Validate installed dependencies and server behavior inside the ARM rootfs.
cd /opt/spcrtify
export UV_PYTHON_DOWNLOADS=never UV_CACHE_DIR=/var/cache/spcrtify-uv
uv venv --python /usr/bin/python3 --system-site-packages .venv
uv sync --locked --no-dev --no-install-project
.venv/bin/python -c 'import pygame; from PIL import Image'
.venv/bin/python -m unittest discover -s tests -p test_player.py
rm -rf /var/cache/spcrtify-uv
systemd-analyze verify /etc/systemd/system/spcrtify-player.service
CHROOT
install -m 644 files/spcrtify-viewer.service "${ROOTFS_DIR}/var/lib/spcrtify/.config/systemd/user/"
on_chroot <<'CHROOT'
chown -R spcrtify:spcrtify /var/lib/spcrtify/.config
CHROOT
