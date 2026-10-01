# Phone sign-in

The Pi image discovers the IPv4 address of `wlan0` and displays a setup QR when
Spotify is disconnected. The QR opens a local page with a ten-minute setup link.
The phone must stay on the same Wi-Fi and the network must permit devices to
communicate; guest Wi-Fi/client isolation can prevent access.

1. Scan the display’s QR and tap **Continue to Spotify**.
   On iPhone or iPad, choose **Open Spotify app** to try approval using the
   account already signed in to Spotify, or **Sign in through browser**.
2. Approve access on Spotify.
3. On the HTTPS callback page, tap **Return to Spcrtify**.
4. The phone opens the local Pi callback. The Pi verifies the pending request,
   exchanges the temporary code using its private PKCE verifier, and saves the
   connection with owner-only permissions. The display switches to now playing.

No token is sent to the callback page. Its JavaScript makes no network requests,
uses no browser storage, loads no third-party scripts, and removes OAuth values
from the address bar. Only a private IPv4 address, an unprivileged port, and the
fixed `/callback` path can be used as the return destination. The Pi separately
checks the exact random state, times out pending requests, and consumes valid
callbacks once. Setup writes retain the app’s same-origin checks. The Wi-Fi is a
trusted network: other people on it can view/control the player and start setup.

Restarting reuses the saved connection. Network errors keep it and retry. An
`invalid_grant` refresh response clears the rejected tokens, retaining only the
public Client ID, and brings back setup. Spotify currently gives developer-app
refresh tokens a six-month lifetime; successful refresh does not extend it.
[Spotify token lifecycle](https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens)

The iOS app option is experimental. It uses the `spotify-action://authorize`
link constructed by [Spotify's iOS authentication SDK](https://github.com/spotify/ios-auth/blob/main/Sources/SessionManager.swift),
preserving the Pi's original callback, state and PKCE challenge. A webpage
launch with our HTTPS callback is not a documented Spotify integration and
still needs testing on an actual iPhone. Browser sign-in remains available;
there is no timer that could interrupt approval in the Spotify app.

## One-time Spotify app configuration

In the [Spotify developer dashboard](https://developer.spotify.com/dashboard),
add this exact redirect URI to the app identified by `spotify-config.json`:

```text
https://yorhodes.github.io/spcrtify/callback.html
```

Keep `http://127.0.0.1:8765/callback` registered too for local development or
SSH-tunnel sign-in. Spotify requires HTTPS for non-loopback callbacks and an
exact match with the registered URI.
[Redirect rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)

`spotify-config.json` contains only public app configuration. A user can select
their own Client ID under **Use your own Spotify app** on the setup page; that
app must register the same callback and allow the signing-in account. The
selected ID is remembered alongside its connection.

## Move away from GitHub Pages

Copy the four files in `callback-site/` to any static HTTPS host. Register the new
`https://your-host/callback.html` URI in Spotify, then set `callback_uri` in a
public JSON configuration and launch with `--spotify-config /path/to/config.json`.
`--spotify-callback` or `SPOTIFY_CALLBACK_URI` overrides only the callback address;
`SPOTIFY_CLIENT_ID` overrides the public app ID. Neither setting is a client secret.

On the image, put overrides in `/var/lib/spcrtify/spotify.env`:

```ini
SPOTIFY_CALLBACK_URI=https://your-host/callback.html
SPOTIFY_CLIENT_ID=your-public-client-id
```

Then restart `spcrtify-player.service`. The included service reads this optional
file. The callback host is needed only for sign-in; existing authorized playback
and token refresh contact Spotify directly even if Pages is unavailable.

To avoid a public callback host entirely, serve the Pi through trusted HTTPS and
register its HTTPS `/callback` URI. The phone must resolve and reach that address
on Wi-Fi, and the certificate must be trusted. A reverse proxy can forward to the
local application. Self-signed certificates introduce manual phone trust setup.

## Check before using the CRT

Run on a Wi-Fi-connected development machine, keeping its normal server separate:

```sh
uv run app.py --host 0.0.0.0 --port 8766 --appliance --data /tmp/spcrtify-qr-test
```

The alternate data directory protects your existing connection. If automatic
Wi-Fi discovery is unavailable, pass `--setup-url http://<Wi-Fi-IPv4>:8766`.
The Pi always discovers `wlan0`; the macOS development fallback uses `en0`.
Open `/api/frame.png` to view the exact QR render and scan it with your phone.
Do not forward this port through your router. The OS image’s firewall restricts
its management port to Wi-Fi and loopback; a manual launch does not install that
firewall. Check Safari and Chrome on your actual phone, then test the Pi/CRT.

A cancelled or failed sign-in preserves an existing connection. Scan again to
retry. If the Pi restarts during approval, its one-time proof is lost and you
must start again. If a link expires or the Wi-Fi address changes, scan the latest
QR. Browsers may ask before opening the local HTTP address; the return button
uses full-page navigation rather than a cross-origin background request.
