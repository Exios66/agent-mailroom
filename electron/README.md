# The Mailroom desktop shell

Thin Electron wrapper around the same FastAPI `/office/` UI the browser uses.
The renderer has no Node integration. All pipeline traffic stays on loopback HTTP.

## Hardening

- `contextIsolation`, `sandbox`, `webSecurity` on; `nodeIntegration` off
- Preload exposes only `mailroomDesktop.getVersion` and `mailroomDesktop.openCredits`
- Navigation is limited to the loopback mailroom origin
- `shell.openExternal` is allowlisted to `limezu.itch.io` and `github.com`
- The office page is under the same CSP the browser server sends

The office does **not** require Electron. Playwright and a normal browser hit
`http://127.0.0.1:8000/office/` with the same JS.

## Run

From the repo root, with the Python app already up:

```bash
export MAILROOM_URL=http://127.0.0.1:8000
cd electron && npm install && npm run start:attached
```

Or let Python start both:

```bash
python -m agent_mailroom --desktop
```

`npm start` (no `MAILROOM_URL`) spawns `python3 -m agent_mailroom` and waits on `/v1/health`.
