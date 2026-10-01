const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const {spotifyAppUrl} = require('../web/setup.js');

const authorization = 'https://accounts.spotify.com/authorize?' + new URLSearchParams({
  client_id: 'a'.repeat(32), response_type: 'code',
  redirect_uri: 'https://yorhodes.github.io/spcrtify/callback.html',
  scope: 'user-read-playback-state user-modify-playback-state',
  state: 'Pi-issued-state', code_challenge_method: 'S256', code_challenge: 'Pi-issued-challenge',
}).toString();

test('app link preserves the exact callback, state, scopes and PKCE query', () => {
  const app = spotifyAppUrl(authorization);
  assert.equal(app, 'spotify-action://authorize' + new URL(authorization).search);
  assert.equal(new URL(app).search, new URL(authorization).search);
});

test('only Spotify authorization addresses can become app links', () => {
  for (const url of ['javascript:alert(1)', 'http://accounts.spotify.com/authorize?a=1',
    'https://evil.example/authorize?a=1', 'https://accounts.spotify.com@evil.example/authorize?a=1',
    'https://user@accounts.spotify.com/authorize?a=1', 'https://accounts.spotify.com:8765/authorize?a=1',
    'https://accounts.spotify.com/other?a=1', authorization + '#fragment',
    'https://accounts.spotify.com/authorize']) assert.throws(() => spotifyAppUrl(url));
});

async function page(navigator, url = authorization) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      hidden: id !== 'setup-continue', disabled: true, value: '', listeners: {},
      addEventListener(name, fn) {this.listeners[name] = fn;},
      removeAttribute(name) {delete this[name];}, focus() {this.focused = true;},
    });
    return elements.get(id);
  };
  const navigations = [], requests = [];
  vm.runInNewContext(fs.readFileSync(require.resolve('../web/setup.js'), 'utf8'), {
    URL, URLSearchParams, navigator, document: {getElementById: element},
    location: {hash: '#pairing-nonce', pathname: '/setup', search: '', assign: (url) => navigations.push(url)},
    history: {replaceState() {}}, sessionStorage: {setItem() {}, getItem() {}, removeItem() {}},
    fetch: async (path, options) => {
      requests.push({path, body: JSON.parse(options.body)});
      return {ok: true, json: async () => path === '/api/spotify/setup'
        ? {client_id: 'a'.repeat(32), callback_uri: 'https://yorhodes.github.io/spcrtify/callback.html'}
        : {url}};
    },
  });
  await new Promise(setImmediate);
  await element('setup-form').listeners.submit({preventDefault() {}});
  return {element, navigations, requests};
}

test('iPhone and iPad offer user-tapped app and browser links without automatic navigation', async () => {
  for (const navigator of [{userAgent: 'iPhone', platform: 'iPhone', maxTouchPoints: 5},
    {userAgent: 'Macintosh', platform: 'MacIntel', maxTouchPoints: 5}]) {
    const {element, navigations, requests} = await page(navigator);
    assert.deepEqual(navigations, []);
    assert.equal(element('setup-open-app').href, spotifyAppUrl(authorization));
    assert.equal(element('setup-open-browser').href, authorization);
    assert.equal(element('setup-options').hidden, false);
    assert.equal(element('setup-continue').hidden, true);
    assert.equal(requests[1].body.pairing_token, 'pairing-nonce');
    element('setup-client-id').listeners.input();
    assert.equal(element('setup-options').hidden, true);
    assert.equal(element('setup-open-app').href, undefined);
    assert.equal(element('setup-open-browser').href, undefined);
  }
});

test('other platforms retain normal browser sign-in', async () => {
  const {navigations} = await page({userAgent: 'Android', platform: 'Linux', maxTouchPoints: 5});
  assert.deepEqual(navigations, [authorization]);
});

test('failed preparation keeps sign-in available and shows an error', async () => {
  const {element, navigations} = await page({userAgent: 'iPhone'}, 'https://evil.example/authorize?a=1');
  assert.deepEqual(navigations, []);
  assert.equal(element('setup-error').hidden, false);
  assert.equal(element('setup-continue').disabled, false);
});
