"use strict";
function spotifyAppUrl(authorizationUrl) {
  const url = new URL(authorizationUrl);
  if (url.origin !== "https://accounts.spotify.com" || url.pathname !== "/authorize"
      || url.username || url.password || url.hash || !url.search) {
    throw new Error("Unexpected Spotify sign-in address.");
  }
  // Match Spotify's iOS SDK actionScheme + authorizeEndpoint. Keep the exact
  // Pi-issued query: the callback, state and PKCE challenge must not change.
  return "spotify-action://authorize" + url.search;
}
if (typeof module !== "undefined") module.exports = {spotifyAppUrl};
if (typeof document !== "undefined") {
  const element = (id) => document.getElementById(id);
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const storageKey = "spcrtify-setup-link";
  let pairingToken = location.hash.slice(1);
  try {
    if (pairingToken) sessionStorage.setItem(storageKey, pairingToken);
    else pairingToken = sessionStorage.getItem(storageKey) || "";
  } catch (_) { /* The current scan still works with browser storage disabled. */ }
  history.replaceState({}, "", location.pathname + location.search);
  function showError(message) {
    element("setup-error").textContent = message;
    element("setup-error").hidden = false;
  }
  async function post(path, value) {
    const response = await fetch(path, {method: "POST", cache: "no-store",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(value)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not connect. Please try again.");
    return data;
  }
  async function initialize() {
    try {
      if (new URLSearchParams(location.search).get("connected") === "1") {
        const response = await fetch("/api/state", {cache: "no-store"});
        if (!response.ok || !(await response.json()).connected) throw new Error("Scan the display to connect Spotify.");
        element("sign-in").hidden = true;
        element("success").hidden = false;
        try {sessionStorage.removeItem(storageKey);} catch (_) {}
        history.replaceState({}, "", "/setup");
        return;
      }
      const info = await post("/api/spotify/setup", {pairing_token: pairingToken});
      if (!info.callback_uri) throw new Error("Phone sign-in needs an HTTPS callback. Ask the display owner to configure it.");
      element("setup-client-id").value = info.client_id;
      element("setup-callback").textContent = info.callback_uri;
      element("app-settings").hidden = false;
      element("app-settings").open = !info.client_id;
      element("setup-continue").disabled = false;
    } catch (error) {showError(error.message || "Cannot reach your display. Check that you are on the same Wi-Fi.");}
  }
  element("setup-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    element("setup-continue").disabled = true;
    element("setup-error").hidden = true;
    try {
      const result = await post("/api/spotify/connect", {pairing_token: pairingToken,
        client_id: element("setup-client-id").value.trim()});
      if (ios) {
        element("setup-open-app").href = spotifyAppUrl(result.url);
        element("setup-open-browser").href = result.url;
        element("setup-options").hidden = false;
        element("setup-continue").hidden = true;
        // A second tap on an actual link keeps native-app navigation tied to a
        // user gesture. Do not guess whether it opened or redirect on a timer.
        element("setup-open-app").focus();
      } else location.assign(result.url);
    } catch (error) {
      showError(error.message || "Cannot reach your display. Check your Wi-Fi and try again.");
      element("setup-continue").disabled = false;
    }
  });
  element("setup-client-id").addEventListener("input", () => {
    element("setup-options").hidden = true;
    element("setup-open-app").removeAttribute("href");
    element("setup-open-browser").removeAttribute("href");
    element("setup-continue").hidden = false;
    element("setup-continue").disabled = false;
  });
  initialize();
}
