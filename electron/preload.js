"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const ALLOWED = new Set(["desktop:version", "desktop:credits"]);

function invoke(channel) {
  if (!ALLOWED.has(channel)) {
    return Promise.reject(new Error("blocked ipc channel"));
  }
  return ipcRenderer.invoke(channel);
}

contextBridge.exposeInMainWorld("mailroomDesktop", {
  isDesktop: true,
  getVersion: () => invoke("desktop:version"),
  openCredits: () => invoke("desktop:credits"),
});
