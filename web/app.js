"use strict";
const $ = (id) => document.getElementById(id);
const query = new URLSearchParams(location.search);
const kiosk = query.get("kiosk") === "1";
const canvas = $("screen");
const context = canvas.getContext("2d", {alpha: false});
const tintCanvas = document.createElement("canvas");
tintCanvas.width = 280; tintCanvas.height = 192;
const tint = tintCanvas.getContext("2d", {willReadFrequently: true});
let state = null, signal = kiosk, calibration = false, busy = false;
let settingsEditing = false, lastAnnounced = "", toastTimer, settingsTimer, settingsDirty = false;
document.body.classList.toggle("kiosk", kiosk);
document.body.classList.toggle("signal-mode", signal);
context.imageSmoothingEnabled = false;
const defaults = {peak: 204, contrast: 1.15, gamma: 1, overscan: 5, idle_seconds: 300};
let settings = {...defaults};

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").hidden = true, 5000);
}
async function api(path, body) {
  const response = await fetch(path, {method: body ? "POST" : "GET", cache: "no-store",
    headers: body ? {"Content-Type": "application/json"} : {}, body: body ? JSON.stringify(body) : undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The player could not finish that request");
  return result;
}
function updateSettingLabels() {
  for (const key of ["peak", "contrast", "gamma", "overscan"]) {
    $(key).value = settings[key];
    $(key + "-value").textContent = key === "peak" ? Math.round(settings[key] / 255 * 100) + "%" :
      key === "overscan" ? settings[key] + "%" : Number(settings[key]).toFixed(2);
  }
  document.documentElement.style.setProperty("--signal-scale", 1 - 2 * settings.overscan / 100);
}
function updateState(next) {
  state = next;
  if (!settingsEditing && !settingsDirty) {settings = {...next.settings}; updateSettingLabels();}
  const demo = next.provider === "Demo";
  $("source-status").textContent = demo ? (next.is_playing ? "Demo is playing" : "Demo is paused") : next.error ? "Player reconnecting" :
    next.connected ? "Spotify connected" : next.provider;
  $("connect").textContent = next.connected ? "Reconnect Spotify ↗" : "Connect Spotify ↗";
  $("demo").hidden = demo;
  $("footer-status").textContent = next.error || next.artwork_error ||
    (demo ? "Original demo artwork & music metadata" : "Music plays on your Spotify device");
  $("track-description").textContent = next.title ? next.title + " — " + next.artist : "Waiting for your next record.";
  $("play-status").textContent = next.error ? "RECONNECTING" : next.dimmed ? "TAKING A BREATHER" : next.is_playing ? "NOW PLAYING" : "PAUSED";
  $("play-pause").textContent = next.is_playing ? "Ⅱ" : "▶";
  $("play-pause").setAttribute("aria-label", next.is_playing ? "Pause" : "Play");
  const disallows = next.disallows || {};
  for (const button of document.querySelectorAll("[data-action]")) {
    const key = {previous: "skipping_prev", next: "skipping_next", toggle: next.is_playing ? "pausing" : "resuming"}[button.dataset.action];
    button.disabled = busy || !next.controls || !!disallows[key];
  }
  const description = next.title ? `${next.title}, ${next.artist}, ${next.album}. ${next.is_playing ? "Playing" : "Paused"}.` : "Waiting for music";
  if (description !== lastAnnounced) {canvas.setAttribute("aria-label", description); lastAnnounced = description;}
}
async function refreshState() {
  try { updateState(await api("/api/state")); }
  catch (_) { $("source-status").textContent = "Player offline"; $("footer-status").textContent = "Reconnecting to the player…"; }
}
async function refreshFrame() {
  try {
    const response = await fetch(`/api/frame.png?calibrate=${calibration ? 1 : 0}`, {cache: "no-store"});
    if (!response.ok) throw new Error("No frame");
    const bitmap = await createImageBitmap(await response.blob());
    tint.drawImage(bitmap, 0, 0); bitmap.close();
    if (!signal) {
      const pixels = tint.getImageData(0, 0, 280, 192);
      for (let i = 0; i < pixels.data.length; i += 4) {
        const gray = pixels.data[i];
        pixels.data[i] = Math.round(gray * .43);
        pixels.data[i + 1] = gray;
        pixels.data[i + 2] = Math.round(gray * .32);
      }
      tint.putImageData(pixels, 0, 0);
    }
    context.drawImage(tintCanvas, 0, 0);
  } catch (_) { /* Hold the last good frame across a brief reconnect. */ }
}
// Poll serially: no overlapping frame downloads on a Pi Zero.
async function loop() {
  await Promise.all([refreshState(), refreshFrame()]);
  setTimeout(loop, document.hidden ? 2000 : 500);
}
async function control(action) {
  if (busy || !state?.controls) return;
  busy = true; updateState(state);
  try {await api("/api/control", {action}); await new Promise(resolve => setTimeout(resolve, 150)); await refreshState(); await refreshFrame();}
  catch (error) {toast(error.message);}
  finally {busy = false; if (state) updateState(state);}
}
for (const button of document.querySelectorAll("[data-action]")) button.addEventListener("click", () => control(button.dataset.action));
canvas.addEventListener("click", (event) => {
  if (calibration) return;
  const rect = canvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width * 280;
  const y = (event.clientY - rect.top) / rect.height * 192;
  if (y >= 153 && y <= 175 && x >= 183) control(x < 211 ? "previous" : x < 245 ? "toggle" : "next");
});
function changeMode(output) {
  signal = output; document.body.classList.toggle("signal-mode", signal);
  for (const [id, selected] of [["preview-mode", !output], ["signal-mode", output]]) {
    $(id).classList.toggle("selected", selected); $(id).setAttribute("aria-pressed", String(selected));
  }
  refreshFrame();
}
$("preview-mode").addEventListener("click", () => changeMode(false));
$("signal-mode").addEventListener("click", () => changeMode(true));
function showSettings(open, focus) {
  $("settings-panel").hidden = !open; $("tune").setAttribute("aria-expanded", String(open));
  if (open && focus) $(focus).focus({preventScroll: true});
  if (open) $("settings-panel").scrollIntoView({behavior: "smooth", block: "nearest"});
}
$("tune").addEventListener("click", () => showSettings($("settings-panel").hidden));
$("close-settings").addEventListener("click", () => {showSettings(false); $("tune").focus();});
$("brightness-knob").addEventListener("click", () => showSettings(true, "peak"));
$("contrast-knob").addEventListener("click", () => showSettings(true, "contrast"));
async function saveSettings() {
  try {await api("/api/settings", settings); settingsDirty = false; await refreshFrame();}
  catch (error) {toast(error.message);}
}
for (const key of ["peak", "contrast", "gamma", "overscan"]) {
  $(key).addEventListener("input", () => {
    settingsEditing = true; settingsDirty = true;
    settings[key] = Number($(key).value);
    updateSettingLabels(); clearTimeout(settingsTimer); settingsTimer = setTimeout(saveSettings, 200);
  });
  $(key).addEventListener("change", () => {settingsEditing = false;});
}
$("reset-settings").addEventListener("click", () => {settings = {...defaults}; settingsDirty = true; updateSettingLabels(); saveSettings();});
function toggleCalibration() {
  calibration = !calibration;
  $("calibrate").textContent = calibration ? "Return to now playing" : "Show calibration pattern";
  refreshFrame();
}
$("calibrate").addEventListener("click", toggleCalibration);
$("fullscreen").addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else {await document.documentElement.requestFullscreen(); document.body.classList.add("kiosk"); changeMode(true);}
  } catch (_) {toast("Fullscreen is unavailable in this browser. Use ?kiosk=1 for the Pi display.");}
});
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && !kiosk) {document.body.classList.remove("kiosk"); changeMode(false);}
});
document.addEventListener("keydown", (event) => {
  if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(document.activeElement?.tagName) || $("connect-dialog").open) return;
  if (event.key === " ") {event.preventDefault(); control("toggle");}
  else if (event.key === "ArrowRight") {event.preventDefault(); control("next");}
  else if (event.key === "ArrowLeft") {event.preventDefault(); control("previous");}
  else if (event.key.toLowerCase() === "c") toggleCalibration();
});
$("connect").addEventListener("click", () => {
  $("connect-error").hidden = true; $("connect-dialog").showModal();
  $("redirect-uri").textContent = `http://127.0.0.1:${location.port || 8765}/callback`;
  if (!["127.0.0.1", "localhost"].includes(location.hostname)) $("local-note").textContent = "You are viewing the Pi remotely. Open this app through an SSH tunnel at 127.0.0.1 before signing in (see README).";
});
$("close-dialog").addEventListener("click", () => $("connect-dialog").close());
$("spotify-form").addEventListener("submit", async (event) => {
  event.preventDefault(); $("authorize").disabled = true;
  try {
    if (!["127.0.0.1", "localhost"].includes(location.hostname)) throw new Error("Sign in at 127.0.0.1 on this computer or through an SSH tunnel to the Pi.");
    const result = await api("/api/spotify/connect", {client_id: $("client-id").value.trim()});
    location.assign(result.url);
  } catch (error) {$("connect-error").textContent = error.message; $("connect-error").hidden = false; $("authorize").disabled = false;}
});
$("demo").addEventListener("click", async () => {
  try {await api("/api/source", {source: "demo"}); await refreshState();}
  catch (error) {toast(error.message);}
});
if (query.has("connected")) {toast("Spotify connected. Start a record on your favorite speaker."); history.replaceState({}, "", "/");}
updateSettingLabels();
loop();
