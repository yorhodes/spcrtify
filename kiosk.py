#!/usr/bin/env python3
"""Lightweight fullscreen Pi viewer. Requires pygame; no browser needed."""
from __future__ import annotations

import argparse
import io
import json
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def target_rect(width: int, height: int, overscan: float, square_pixels=False):
    """Composite mode fills a physical 4:3 display, even at 720x480/576."""
    if square_pixels:
        width = min(width, round(height * 4 / 3))
        height = min(height, round(width * 3 / 4))
    return round(width * (1 - 2 * overscan / 100)), round(height * (1 - 2 * overscan / 100))


class Feed:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.image, self.settings, self.calibrate, self.action = None, {"overscan": 5}, False, None
        self.updated = time.monotonic()

    def run(self):
        while not self.stop.is_set():
            start = time.monotonic()
            with self.lock:
                action, self.action = self.action, None
                calibrate = self.calibrate
            try:
                if action:
                    request = Request(self.url + "/api/control", data=json.dumps({"action": action}).encode(),
                                      headers={"Content-Type": "application/json"}, method="POST")
                    try:
                        with urlopen(request, timeout=2) as response:
                            response.read()
                    except URLError:
                        pass
                with urlopen(self.url + "/api/state", timeout=2) as response:
                    settings = json.load(response)["settings"]
                with urlopen(self.url + f"/api/frame.png?calibrate={int(calibrate)}", timeout=2) as response:
                    image = response.read()
                with self.lock:
                    self.image, self.settings, self.updated = image, settings, time.monotonic()
            except (URLError, ValueError, KeyError, OSError):
                pass
            self.stop.wait(max(.05, .5 - (time.monotonic() - start)))


def main():
    import pygame
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--windowed", action="store_true", help="desktop test window")
    parser.add_argument("--square-pixels", action="store_true", help="letterbox HDMI or desktop displays to 4:3")
    args = parser.parse_args()
    pygame.display.init()
    surface = pygame.display.set_mode((800, 600) if args.windowed else (0, 0), 0 if args.windowed else pygame.FULLSCREEN)
    pygame.display.set_caption("Monitor /// Player")
    pygame.mouse.set_visible(False)
    feed = Feed(args.url)
    thread = threading.Thread(target=feed.run, daemon=True)
    thread.start()
    clock = pygame.time.Clock()
    last_image, last_size, last_overscan, scaled = None, None, None, None
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    with feed.lock:
                        if event.key == pygame.K_c:
                            feed.calibrate = not feed.calibrate
                        elif event.key in (pygame.K_SPACE, pygame.K_LEFT, pygame.K_RIGHT):
                            feed.action = {pygame.K_SPACE: "toggle", pygame.K_LEFT: "previous", pygame.K_RIGHT: "next"}[event.key]
            with feed.lock:
                image, overscan, updated = feed.image, feed.settings["overscan"], feed.updated
            size = surface.get_size()
            if image and (image != last_image or size != last_size or overscan != last_overscan):
                native = pygame.image.load(io.BytesIO(image), "frame.png").convert()
                scaled = pygame.transform.scale(native, target_rect(*size, overscan, args.square_pixels))
                last_image, last_size, last_overscan = image, size, overscan
            surface.fill((0, 0, 0))
            # If the local server goes away, blank after 30 seconds instead of burning in a frozen frame.
            if scaled and time.monotonic() - updated < 30:
                surface.blit(scaled, scaled.get_rect(center=surface.get_rect().center))
            pygame.display.flip()
            clock.tick(10)
    finally:
        feed.stop.set()
        pygame.quit()


if __name__ == "__main__":
    main()
