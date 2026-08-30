"use strict";

const { app, BrowserWindow, ipcMain, session, shell } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const security = require("./security");

const REPO_ROOT = path.resolve(__dirname, "..");
const DEFAULT_HOST = process.env.MAILROOM_HOST || "127.0.0.1";
const DEFAULT_PORT = String(process.env.MAILROOM_PORT || "8000");

let childServer = null;
let mainWindow = null;

function parseArgs(argv) {
  return {
    attached: argv.includes("--attached") || Boolean(process.env.MAILROOM_URL),
  };
}

function serverOrigin() {
  if (process.env.MAILROOM_URL) {
    return process.env.MAILROOM_URL.replace(/\/$/, "");
  }
  return `http://${DEFAULT_HOST}:${DEFAULT_PORT}`;
}

function waitForHealth(origin, timeoutMs = 20000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const ping = () => {
      const req = http.get(`${origin}/v1/health`, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) {
          resolve(origin);
          return;
        }
        retry();
      });
      req.on("error", retry);
      req.setTimeout(1500, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`mailroom health check timed out: ${origin}`));
        return;
      }
      setTimeout(ping, 250);
    };
    ping();
  });
}

function spawnMailroom(origin) {
  const url = new URL(origin);
  const python = process.env.MAILROOM_PYTHON || "python3";
  childServer = spawn(python, ["-m", "agent_mailroom"], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      MAILROOM_HOST: url.hostname,
      MAILROOM_PORT: url.port || "8000",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  childServer.stdout.on("data", (buf) => process.stdout.write(buf));
  childServer.stderr.on("data", (buf) => process.stderr.write(buf));
  childServer.on("exit", (code) => {
    if (code && code !== 0) {
      console.error(`agent_mailroom exited ${code}`);
    }
    childServer = null;
  });
}

function attachSessionGuards(origin) {
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    const headers = { ...details.responseHeaders };
    headers["Content-Security-Policy"] = [security.OFFICE_CSP];
    headers["X-Content-Type-Options"] = ["nosniff"];
    headers["X-Frame-Options"] = ["DENY"];
    callback({ responseHeaders: headers });
  });

  session.defaultSession.setPermissionRequestHandler((_wc, _perm, grant) => grant(false));

  app.on("web-contents-created", (_event, contents) => {
    contents.on("will-attach-webview", (event) => event.preventDefault());
    contents.on("will-navigate", (event, url) => {
      if (!security.isAllowedNavigation(url, origin)) {
        event.preventDefault();
        if (security.isAllowedExternal(url)) {
          shell.openExternal(url);
        }
      }
    });
    contents.setWindowOpenHandler(({ url }) => {
      if (security.isAllowedExternal(url) || security.isAllowedNavigation(url, origin)) {
        if (security.isAllowedExternal(url)) shell.openExternal(url);
        else contents.loadURL(url);
      }
      return { action: "deny" };
    });
  });
}

function createWindow(origin) {
  const prefs = security.webPreferences();
  prefs.preload = path.join(__dirname, "preload.js");
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 960,
    minHeight: 640,
    title: "The Mailroom",
    autoHideMenuBar: true,
    webPreferences: prefs,
  });
  mainWindow.loadURL(`${origin}/office/`);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function bindIpc() {
  ipcMain.handle("desktop:version", () => app.getVersion());
  ipcMain.handle("desktop:credits", async () => {
    await shell.openExternal("https://limezu.itch.io/moderninteriors");
    return true;
  });
}

app.enableSandbox();

async function boot() {
  const { attached } = parseArgs(process.argv);
  const origin = serverOrigin();
  if (!attached) {
    spawnMailroom(origin);
  }
  await waitForHealth(origin);
  attachSessionGuards(origin);
  bindIpc();
  createWindow(origin);
}

app.whenReady().then(boot).catch((err) => {
  console.error(err);
  app.quit();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (childServer && !childServer.killed) {
    childServer.kill("SIGTERM");
  }
});

app.on("activate", () => {
  if (!mainWindow && app.isReady()) {
    createWindow(serverOrigin());
  }
});
