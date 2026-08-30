"use strict";

/** Shared Electron hardening contract. pytest and main.js both read this. */

const ALLOWED_EXTERNAL_HOSTS = Object.freeze([
  "limezu.itch.io",
  "github.com",
]);

const LOOPBACK_HOSTS = Object.freeze(["127.0.0.1", "localhost", "::1"]);

function webPreferences() {
  return {
    preload: null,
    nodeIntegration: false,
    contextIsolation: true,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false,
    enableRemoteModule: false,
    navigateOnDragDrop: false,
    safeDialogs: true,
    disableBlinkFeatures: "Auxclick",
  };
}

function isLoopbackUrl(urlString) {
  try {
    const url = new URL(urlString);
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    return LOOPBACK_HOSTS.includes(url.hostname);
  } catch {
    return false;
  }
}

function isAllowedExternal(urlString) {
  try {
    const url = new URL(urlString);
    if (url.protocol !== "https:") return false;
    return ALLOWED_EXTERNAL_HOSTS.includes(url.hostname);
  } catch {
    return false;
  }
}

function isAllowedNavigation(urlString, serverOrigin) {
  if (serverOrigin && urlString.startsWith(serverOrigin)) return true;
  return isLoopbackUrl(urlString);
}

const OFFICE_CSP =
  "default-src 'self'; " +
  "script-src 'self'; " +
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
  "font-src 'self' https://fonts.gstatic.com data:; " +
  "img-src 'self' data:; " +
  "connect-src 'self' ws: wss:; " +
  "worker-src 'none'; " +
  "object-src 'none'; " +
  "base-uri 'self'; " +
  "form-action 'self'; " +
  "frame-ancestors 'none'";

module.exports = {
  ALLOWED_EXTERNAL_HOSTS,
  LOOPBACK_HOSTS,
  OFFICE_CSP,
  webPreferences,
  isLoopbackUrl,
  isAllowedExternal,
  isAllowedNavigation,
};
