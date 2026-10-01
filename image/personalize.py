"""Personalize a flashed card's boot partition; secrets never enter GitHub."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import uuid

from boot_config import configure


def private_write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value)


def personalize(boot, username, hostname, key, ssid, password, country="US", timezone="UTC", spotify=None, video="composite", shutdown_button=False):
    if not (boot / "config.txt").is_file() or not (boot / "cmdline.txt").is_file():
        raise ValueError("Choose the card's bootfs partition, containing config.txt and cmdline.txt")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", username) or username in {"root", "spcrtify"}:
        raise ValueError("Choose an administrator username other than root or spcrtify")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", hostname):
        raise ValueError("Use a hostname containing lowercase letters, numbers, and hyphens")
    if not key.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")) or "\n" in key.strip():
        raise ValueError("Supply a single SSH public key, never a private key")
    if not re.fullmatch(r"[A-Z]{2}", country) or not ssid or not 8 <= len(password) <= 63:
        raise ValueError("Provide a two-letter Wi-Fi country, SSID, and 8–63 character Wi-Fi password")
    if spotify and not all(isinstance(spotify.get(field), str) and spotify[field] for field in ("client_id", "refresh_token")):
        raise ValueError("Spotify credentials need an existing Client ID and refresh token")
    user_data = {
        "hostname": hostname, "manage_etc_hosts": True, "timezone": timezone,
        "ssh_pwauth": False, "disable_root": True,
        "users": [{"name": username, "shell": "/bin/bash", "lock_passwd": True,
                   "groups": ["adm", "sudo"], "sudo": "ALL=(ALL) NOPASSWD:ALL",
                   "ssh_authorized_keys": [key.strip()]}],
        "package_update": False, "package_upgrade": False,
    }
    network = {"version": 2, "renderer": "NetworkManager", "wifis": {"wlan0": {
        "dhcp4": True, "optional": True, "regulatory-domain": country,
        "access-points": {ssid: {"password": password}},
    }}}
    # JSON is valid YAML; quoting safely handles punctuation in SSIDs/passwords.
    private_write(boot / "user-data", "#cloud-config\n" + json.dumps(user_data, indent=2) + "\n")
    private_write(boot / "network-config", json.dumps(network, indent=2) + "\n")
    private_write(boot / "meta-data", json.dumps({"instance-id": "spcrtify-" + str(uuid.uuid4()), "local-hostname": hostname, "dsmode": "local"}) + "\n")
    if spotify:
        private_write(boot / "spcrtify-spotify.json", json.dumps(spotify) + "\n")
    configure(boot, video, shutdown_button)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot", type=Path, required=True)
    parser.add_argument("--username", default="operator")
    parser.add_argument("--hostname", default="spcrtify")
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--wifi-ssid", required=True)
    parser.add_argument("--country", default="US")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--spotify-from", type=Path, help="existing local spotify.json; skips another login")
    parser.add_argument("--video", choices=("composite", "hdmi"), default="composite")
    parser.add_argument("--shutdown-button", action="store_true", help="momentary switch between GPIO3 and GND")
    args = parser.parse_args()
    try:
        spotify = json.loads(args.spotify_from.read_text()) if args.spotify_from else None
        personalize(args.boot, args.username, args.hostname, args.ssh_key.read_text().strip(),
                    args.wifi_ssid, getpass.getpass("Wi-Fi password: "), args.country, args.timezone,
                    spotify, args.video, args.shutdown_button)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print("Card configured. Eject it before powering up the Pi.")


if __name__ == "__main__":
    main()
