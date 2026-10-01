"""Wi-Fi discovery and short-lived setup links for the local appliance."""
from __future__ import annotations

import ipaddress
import secrets
import socket
import struct
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

LOCAL_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                       ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.1/32"))


def local_url(value: str, path="") -> str:
    """Accept an explicit private IPv4 origin, never an arbitrary redirect."""
    parsed = urlparse(value)
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError:
        raise ValueError("Use a local IPv4 address for the setup URL") from None
    if (parsed.scheme != "http" or not any(address in network for network in LOCAL_NETWORKS)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/", path) or port is None or not 1024 <= port <= 65535):
        raise ValueError("Use http://<Wi-Fi IPv4 address>:<port> for setup")
    return f"http://{address}:{port}{path}"


def wifi_address() -> str | None:
    # On the Pi, deliberately inspect Wi-Fi rather than a default/Ethernet route.
    try:
        if sys.platform.startswith("linux"):
            import fcntl
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                result = fcntl.ioctl(connection.fileno(), 0x8915, struct.pack("256s", b"wlan0"))
            address = socket.inet_ntoa(result[20:24])
        elif sys.platform == "darwin":
            address = subprocess.check_output(["/usr/sbin/ipconfig", "getifaddr", "en0"],
                                              stderr=subprocess.DEVNULL, timeout=2).decode().strip()
        else:
            return None
        local_url(f"http://{address}:8765")
        return address
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class Pairing:
    lifetime = 600

    def __init__(self, port=8765, origin=None):
        self.port = port
        self.override = local_url(origin) if origin else None
        self.lock = threading.RLock()
        self.origin = self.token = None
        self.updated = self.checked = float("-inf")

    def refresh(self):
        now = time.monotonic()
        with self.lock:
            if now - self.checked >= 5:
                address = wifi_address() if not self.override else None
                origin = self.override or (f"http://{address}:{self.port}" if address else None)
                if origin != self.origin:
                    self.origin, self.token = origin, None
                self.checked = now
            if self.origin and (not self.token or now - self.updated >= self.lifetime):
                self.token, self.updated = secrets.token_urlsafe(24), now
            return self.origin

    def url(self):
        with self.lock:
            return f"{self.origin}/setup#{self.token}" if self.refresh() else None

    def validate(self, token):
        with self.lock:
            if (not self.refresh() or not isinstance(token, str)
                    or not secrets.compare_digest(token, self.token)):
                raise ValueError("This setup link expired. Scan the QR on the display again.")
            return local_url(self.origin, "/callback")

    def complete(self):
        with self.lock:
            self.token = None
