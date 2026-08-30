from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _find_electron() -> str | None:
    env = os.environ.get("MAILROOM_ELECTRON", "").strip()
    if env:
        return env
    local = _repo_root() / "electron" / "node_modules" / ".bin" / "electron"
    if local.exists():
        return str(local)
    return shutil.which("electron")


def _wait_health(host: str, port: int, timeout: float = 20.0) -> None:
    url = f"http://{host}:{port}/v1/health"
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if 200 <= resp.status < 500:
                    return
                last = f"status {resp.status}"
        except urllib.error.URLError as exc:
            last = str(exc.reason if hasattr(exc, "reason") else exc)
        time.sleep(0.25)
    raise RuntimeError(f"mailroom did not become healthy at {url}: {last}")


def run_desktop(host: str | None = None, port: int | None = None) -> int:
    """Serve the mailroom and open the hardened Electron shell when available."""
    host = host or os.environ.get("MAILROOM_HOST", "127.0.0.1")
    port = int(port or os.environ.get("MAILROOM_PORT", "8000"))
    os.environ["MAILROOM_HOST"] = host
    os.environ["MAILROOM_PORT"] = str(port)
    os.environ["MAILROOM_DESKTOP"] = "1"

    import uvicorn

    def _serve() -> None:
        uvicorn.run(
            "agent_mailroom.api.app:create_app",
            factory=True,
            host=host,
            port=port,
            reload=False,
        )

    electron = _find_electron()
    origin = f"http://{host}:{port}"
    if not electron:
        print(
            "Electron is not installed. The office is the same in a browser:\n"
            f"  {origin}/office/\n"
            "To install the desktop shell: cd electron && npm install && npm start",
            flush=True,
        )
        uvicorn.run(
            "agent_mailroom.api.app:create_app",
            factory=True,
            host=host,
            port=port,
            reload=False,
        )
        return 0

    thread = threading.Thread(target=_serve, name="mailroom-uvicorn", daemon=True)
    thread.start()
    _wait_health(host, port)
    env = os.environ.copy()
    env["MAILROOM_URL"] = origin
    proc = subprocess.Popen([electron, str(_repo_root() / "electron")], cwd=_repo_root() / "electron", env=env)
    code = proc.wait()
    return code if code is not None else 0
