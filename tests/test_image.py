import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'image'))
from boot_config import configure
from personalize import personalize
from systemd_notify import Watchdog

spec = importlib.util.spec_from_file_location('first_boot', ROOT / 'image/stage-spcrtify/00-install/files/first_boot.py')
first_boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(first_boot)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.boot = self.root / 'boot'
        self.boot.mkdir()
        (self.boot / 'config.txt').write_text('arm_64bit=1\ndtoverlay=vc4-kms-v3d\n[pi5]\ndtoverlay=nospi10\n[all]\n')
        (self.boot / 'cmdline.txt').write_text('console=tty1 root=PARTUUID=1234 rootwait\n')

    def tearDown(self):
        self.temp.cleanup()

    def test_video_switch_is_idempotent_and_retains_boot_identity(self):
        configure(self.boot, shutdown_button=True)
        first = (self.boot / 'config.txt').read_text()
        configure(self.boot, shutdown_button=True)
        self.assertEqual(first, (self.boot / 'config.txt').read_text())
        self.assertEqual(first.count('dtoverlay=vc4-kms-v3d'), 1)
        self.assertIn('gpio-shutdown', first)
        configure(self.boot, 'hdmi')
        self.assertNotIn('gpio-shutdown', (self.boot / 'config.txt').read_text())
        self.assertIn('enable_tvout=0', (self.boot / 'config.txt').read_text())
        cmdline = (self.boot / 'cmdline.txt').read_text()
        self.assertIn('root=PARTUUID=1234', cmdline)
        self.assertNotIn('vc4.tv_norm', cmdline)
        self.assertEqual(len(cmdline.splitlines()), 1)

    def test_personalization_quotes_wifi_and_imports_tokens_privately(self):
        tokens = {'client_id': 'fake-client', 'refresh_token': 'fake-refresh'}
        personalize(self.boot, 'operator', 'spcrtify', 'ssh-ed25519 fake-public-key', 'Wifi: "Home"', 'secret: "wifi"', spotify=tokens)
        network = json.loads((self.boot / 'network-config').read_text())
        self.assertEqual(network['wifis']['wlan0']['access-points']['Wifi: "Home"']['password'], 'secret: "wifi"')
        data = self.root / 'data'
        data.mkdir()
        first_boot.import_spotify(self.boot, data, os.getuid(), os.getgid())
        self.assertEqual(json.loads((data / 'spotify.json').read_text()), tokens)
        self.assertEqual((data / 'spotify.json').stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.boot / 'spcrtify-spotify.json').exists())
        first_boot.import_spotify(self.boot, data, os.getuid(), os.getgid())
        self.assertEqual(json.loads((data / 'spotify.json').read_text()), tokens)

    def test_invalid_token_seed_is_retained_without_overwriting_saved_connection(self):
        data = self.root / 'data'
        data.mkdir()
        (data / 'spotify.json').write_text('{"refresh_token":"existing"}')
        (self.boot / 'spcrtify-spotify.json').write_text('{"invalid":true}')
        with self.assertRaises(ValueError):
            first_boot.import_spotify(self.boot, data, os.getuid(), os.getgid())
        self.assertEqual(json.loads((data / 'spotify.json').read_text())['refresh_token'], 'existing')
        self.assertTrue((self.boot / 'spcrtify-spotify.json').exists())

    def test_watchdog_notifies_from_loop_and_throttles_heartbeats(self):
        address = str(self.root / 'notify.sock')
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as listener:
            listener.bind(address)
            listener.settimeout(.2)
            with patch.dict(os.environ, {'NOTIFY_SOCKET': address}):
                watchdog = Watchdog()
            with patch('systemd_notify.time.monotonic', return_value=10):
                watchdog.ready()
                self.assertEqual(listener.recv(100), b'READY=1')
                self.assertEqual(listener.recv(100), b'WATCHDOG=1')
                watchdog.tick()
                with self.assertRaises(socket.timeout):
                    listener.recv(100)
            with patch('systemd_notify.time.monotonic', return_value=13):
                watchdog.tick()
                self.assertEqual(listener.recv(100), b'WATCHDOG=1')


if __name__ == '__main__':
    unittest.main()
