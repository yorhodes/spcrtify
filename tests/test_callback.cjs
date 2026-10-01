const assert = require('node:assert/strict');
const {test} = require('node:test');
const {buildReturnUrl} = require('../callback-site/callback.js');
const state = (return_to = 'http://192.168.1.20:8765/callback') => Buffer.from(JSON.stringify({v: 1, return_to, nonce: 'x'.repeat(43)})).toString('base64url');
const query = (return_to) => new URLSearchParams({state: state(return_to), code: 'temporary-code'}).toString();
test('returns the code and unchanged state to the Pi, with no token exchange', () => {
  const url = new URL(buildReturnUrl('?' + query()));
  assert.equal(url.origin, 'http://192.168.1.20:8765');
  assert.equal(url.pathname, '/callback');
  assert.equal(url.searchParams.get('code'), 'temporary-code');
  assert.equal(url.searchParams.get('state'), state());
});
test('supports configured private addresses and returns cancellation to Pi', () => {
  for (const ip of ['10.0.0.2', '172.16.0.2', '172.31.255.2', '192.168.0.2', '127.0.0.1']) assert.ok(buildReturnUrl(query(`http://${ip}:8765/callback`)));
  const result = new URL(buildReturnUrl(new URLSearchParams({state: state(), error: 'access_denied'}).toString()));
  assert.equal(result.searchParams.get('error'), 'access_denied');
  assert.equal(result.searchParams.has('code'), false);
});
test('rejects public URLs, credentials, dangerous schemes, unrelated paths and ambiguous representations', () => {
  for (const value of ['https://evil.example/callback', 'http://8.8.8.8:8765/callback', 'http://172.32.0.1:8765/callback',
    'http://192.168.1.20:80/callback', 'http://user@192.168.1.20:8765/callback', 'javascript:alert(1)',
    'http://192.168.1.20:8765/other', 'http://192.168.1.20:8765/callback?next=evil',
    'http://192.168.1.20:8765/callback#fragment', 'http://0x7f000001:8765/callback', '//192.168.1.20:8765/callback']) {
    assert.throws(() => buildReturnUrl(query(value)), value);
  }
});
test('rejects missing, malformed and duplicate OAuth parameters', () => {
  for (const value of ['', '?state=oops&code=test', '?' + query() + '&state=other', '?' + query() + '&code=other',
    '?' + query() + '&error=access_denied', '?state=' + state(), '?' + 'x'.repeat(4097)]) assert.throws(() => buildReturnUrl(value));
});
