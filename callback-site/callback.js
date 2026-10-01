"use strict";
// Pure validation is also exercised by the Node tests. No requests or storage.
function buildReturnUrl(search) {
  if (search.length > 4096) throw new Error("This sign-in link is invalid. Scan your display again.");
  const params = new URLSearchParams(search);
  const states = params.getAll("state");
  if (states.length !== 1 || !/^[A-Za-z0-9_-]{1,1024}$/.test(states[0])) throw new Error("This sign-in link is incomplete. Scan your display again.");
  const state = JSON.parse(atob(states[0].replace(/-/g, "+").replace(/_/g, "/")));
  if (state.v !== 1 || !/^[A-Za-z0-9_-]{43}$/.test(state.nonce) || typeof state.return_to !== "string") throw new Error("This sign-in link is invalid. Scan your display again.");
  const target = new URL(state.return_to);
  const parts = target.hostname.split(".").map(Number);
  const privateAddress = parts.length === 4 && parts.every((part) => Number.isInteger(part) && part >= 0 && part <= 255) &&
    (parts[0] === 10 || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
     (parts[0] === 192 && parts[1] === 168) || target.hostname === "127.0.0.1");
  if (target.protocol !== "http:" || !privateAddress || !target.port || Number(target.port) < 1024 ||
      target.username || target.password || target.pathname !== "/callback" || target.search || target.hash ||
      target.origin + "/callback" !== state.return_to) throw new Error("This link does not point to a local display. Scan your display again.");
  const codes = params.getAll("code"), errors = params.getAll("error");
  if ((codes.length === 1 && errors.length === 0 && codes[0] && codes[0].length <= 2048)) target.searchParams.set("code", codes[0]);
  else if (errors.length === 1 && codes.length === 0 && /^[a-z_]{1,80}$/.test(errors[0])) target.searchParams.set("error", errors[0]);
  else throw new Error("Spotify did not return a valid sign-in code. Scan your display again.");
  target.searchParams.set("state", states[0]);
  return target.href;
}
if (typeof module !== "undefined") module.exports = {buildReturnUrl};
if (typeof document !== "undefined") {
  const search = location.search;
  history.replaceState({}, "", location.pathname);
  try {
    const url = buildReturnUrl(search);
    document.getElementById("return-link").href = url;
    document.getElementById("return-link").hidden = false;
    document.getElementById("wifi-note").hidden = false;
    if (new URLSearchParams(search).has("error")) {
      document.getElementById("heading").textContent = "Sign-in cancelled.";
      document.getElementById("message").textContent = "Return to your display to try again when you are ready.";
    }
  } catch (error) {
    document.getElementById("heading").textContent = "Let’s try that again.";
    document.getElementById("message").textContent = "This sign-in link is incomplete or invalid. Scan the QR on your display again.";
  }
}
