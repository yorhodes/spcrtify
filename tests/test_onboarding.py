import argparse
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from app import Handler, Player, ThreadingHTTPServer
from display import render_frame
from app import DEFAULT_SETTINGS
from onboarding import Pairing, local_url
from spotify import Authorization, Spotify, SpotifyError, SpotifyReauthorization, request_json, save_tokens

CALLBACK = 'https://yorhodes.github.io/spcrtify/callback.html'
FAKE_TOKENS = {'access_token': 'test-access', 'refresh_token': 'test-refresh', 'expires_in': 3600}


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_local_origins_reject_public_hosts_credentials_paths_and_low_ports(self):
        for address in ('192.168.1.20', '10.0.0.3', '172.31.1.2', '127.0.0.1'):
            self.assertEqual(local_url(f'http://{address}:8765/', '/callback'), f'http://{address}:8765/callback')
        for value in ('http://example.com:8765', 'http://8.8.8.8:8765', 'http://172.32.0.1:8765',
                      'http://user@192.168.1.20:8765', 'http://192.168.1.20:8765/other',
                      'http://192.168.1.20:80', 'http://192.168.1.20:8765?x=1', 'https://192.168.1.20:8765'):
            with self.assertRaises(ValueError):
                local_url(value)

    def test_pairing_expiry_and_wifi_address_changes_invalidate_old_links(self):
        with patch('onboarding.wifi_address', return_value='192.168.1.20'), patch('onboarding.time.monotonic', return_value=1):
            pairing = Pairing()
            url = pairing.url()
            token = urlparse(url).fragment
            self.assertEqual(pairing.validate(token), 'http://192.168.1.20:8765/callback')
        with patch('onboarding.wifi_address', return_value='192.168.1.20'), patch('onboarding.time.monotonic', return_value=602):
            with self.assertRaises(ValueError):
                pairing.validate(token)
            renewed = urlparse(pairing.url()).fragment
        with patch('onboarding.wifi_address', return_value='192.168.1.21'), patch('onboarding.time.monotonic', return_value=610):
            with self.assertRaises(ValueError):
                pairing.validate(renewed)
            self.assertIn('192.168.1.21', pairing.url())
        with patch('onboarding.wifi_address', return_value=None), patch('onboarding.time.monotonic', return_value=620):
            self.assertIsNone(pairing.url())

    def test_relay_state_binds_local_callback_and_never_contains_private_proof(self):
        auth = Authorization(self.path / 'spotify.json', relay_redirect=CALLBACK)
        query = parse_qs(urlparse(auth.begin('a' * 32, 'http://192.168.1.20:8765/callback')).query)
        state = json.loads(base64.urlsafe_b64decode(query['state'][0] + '==='))
        self.assertEqual(state['return_to'], 'http://192.168.1.20:8765/callback')
        self.assertEqual(query['redirect_uri'], [CALLBACK])
        self.assertNotIn(auth.pending[1], json.dumps(state))
        self.assertEqual(auth.begin('a' * 32, state['return_to']), auth.begin('a' * 32, state['return_to']))
        with self.assertRaises(ValueError):
            auth.begin('b' * 32, state['return_to'])
        with self.assertRaises(ValueError):
            auth.finish({'state': ['wrong'], 'code': ['test']})
        self.assertIsNotNone(auth.pending)
        with patch('spotify.request_json', return_value=FAKE_TOKENS.copy()) as request:
            auth.finish({'state': query['state'], 'code': ['test']})
        sent = parse_qs(request.call_args.args[2].decode())
        self.assertEqual(sent['redirect_uri'], [CALLBACK])
        self.assertIn('code_verifier', sent)
        self.assertEqual(os.stat(auth.path).st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            auth.finish({'state': query['state'], 'code': ['test']})

    def test_cancelled_and_timed_out_sign_ins_preserve_saved_connection(self):
        path = self.path / 'spotify.json'
        save_tokens(path, {'refresh_token': 'original', 'client_id': 'a' * 32})
        auth = Authorization(path, relay_redirect=CALLBACK)
        query = parse_qs(urlparse(auth.begin('a' * 32, 'http://192.168.1.20:8765/callback')).query)
        with self.assertRaises(ValueError):
            auth.finish({'state': query['state'], 'error': ['access_denied']})
        auth.begin('a' * 32)
        pending = auth.pending
        auth.pending = (*pending[:3], pending[3] - 601, *pending[4:])
        with self.assertRaises(ValueError):
            auth.finish({'state': [pending[2]], 'code': ['test']})
        self.assertEqual(json.loads(path.read_text())['refresh_token'], 'original')

    def test_invalid_grant_requires_login_but_network_failure_keeps_tokens(self):
        path = self.path / 'spotify.json'
        original = {'refresh_token': 'original', 'client_id': 'a' * 32}
        save_tokens(path, original)
        provider = Spotify(path)
        with patch('spotify.request_json', side_effect=SpotifyError('Cannot reach Spotify; retrying')):
            with self.assertRaises(SpotifyError):
                provider.refresh()
        self.assertEqual(json.loads(path.read_text()), original)
        error = HTTPError('https://accounts.spotify.com/api/token', 400, 'Bad request', {}, io.BytesIO(b'{"error":"invalid_grant"}'))
        with patch('spotify.urlopen', side_effect=error):
            with self.assertRaises(SpotifyReauthorization):
                provider.refresh()
        self.assertEqual(json.loads(path.read_text()), {"client_id": 'a' * 32})
        self.assertNotIn('refresh_token', provider.tokens)

    def test_appliance_shows_constrained_setup_frame_and_restores_saved_account(self):
        args = argparse.Namespace(source='auto', port=8765, data=self.path, feed=None,
                                  appliance=True, setup_url='http://192.168.255.255:8765')
        player = Player(args)
        self.assertIsInstance(player.provider, Spotify)
        frame = player.frame()
        self.assertEqual(frame.size, (280, 192))
        self.assertTrue(set(frame.tobytes()).issubset({0, 136, 163, 190, 204}))
        save_tokens(player.auth.path, {**FAKE_TOKENS, 'client_id': 'a' * 32})
        restored = Player(args)
        self.assertTrue(restored.snapshot()['connected'])
        self.assertEqual(restored.frame().tobytes(), render_frame(restored.snapshot(), restored.settings, 0).tobytes())

    def test_replacing_provider_prevents_old_account_from_saving_tokens(self):
        args = argparse.Namespace(source='spotify', port=8765, data=self.path, feed=None)
        player = Player(args)
        original = player.provider
        player.switch('spotify')
        with patch('spotify.request_json') as request:
            with self.assertRaises(SpotifyError):
                original.api('me/player')
            request.assert_not_called()


class PhoneHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        args = argparse.Namespace(source='auto', data=self.path, feed=None, port=8765, appliance=True)
        self.player = Player(args)
        self.player.auth.relay_redirect = CALLBACK
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.player = self.player
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.player.pairing = Pairing(self.server.server_port, self.url)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def post(self, path, data):
        with urlopen(Request(self.url + path, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}), timeout=3) as response:
            return json.load(response)

    def test_phone_setup_through_callback_and_restart_without_secrets_in_state(self):
        pair = self.post('/api/spotify/pair', {})
        token = urlparse(pair['url']).fragment
        info = self.post('/api/spotify/setup', {'pairing_token': token})
        self.assertEqual(info['callback_uri'], CALLBACK)
        self.assertNotIn('refresh_token', info)
        url = self.post('/api/spotify/connect', {'pairing_token': token, 'client_id': 'a' * 32})['url']
        query = parse_qs(urlparse(url).query)
        verifier = self.player.auth.pending[1]
        with patch('spotify.request_json', return_value=FAKE_TOKENS.copy()):
            with urlopen(self.url + '/callback?' + urlencode({'state': query['state'][0], 'code': 'test-code'}), timeout=3) as response:
                self.assertEqual(urlparse(response.url).path, '/setup')
                self.assertIn('connected=1', response.url)
        with urlopen(self.url + '/api/state') as response:
            state = json.load(response)
        self.assertTrue(state['connected'])
        for secret in ('test-access', 'test-refresh', verifier):
            self.assertNotIn(secret, json.dumps(state))
        restored = Player(self.player.args)
        self.assertTrue(restored.snapshot()['connected'])
        with self.assertRaises(HTTPError) as error:
            self.post('/api/spotify/setup', {'pairing_token': token})
        self.assertEqual(error.exception.code, 400)

    def test_setup_rejects_invalid_pair_and_cross_origin_and_serves_private_headers(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url + '/api/state', headers={'Host': 'evil.example:8765'}))
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError):
            self.post('/api/spotify/connect', {'pairing_token': 'wrong', 'client_id': 'a' * 32})
        request = Request(self.url + '/api/spotify/pair', data=b'{}', headers={'Content-Type': 'application/json', 'Origin': 'https://evil.example'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)
        for path in ('/setup', '/setup.js', '/setup.css'):
            with urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
