"""Optional systemd heartbeats from the application's actual event loop."""
import os
import socket
import time


class Watchdog:
    def __init__(self):
        self.address = os.environ.get("NOTIFY_SOCKET", "")
        if self.address.startswith("@"):
            self.address = "\0" + self.address[1:]
        self.last = 0.0

    def send(self, message):
        if not self.address:
            return
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as connection:
                connection.settimeout(.2)
                connection.connect(self.address)
                connection.sendall(message.encode())
        except OSError:
            # Desktop runs and unavailable notification sockets still work.
            pass

    def ready(self):
        self.send("READY=1")
        self.tick()

    def tick(self):
        now = time.monotonic()
        if now - self.last >= 2:
            self.send("WATCHDOG=1")
            self.last = now
