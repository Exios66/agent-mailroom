from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app
from agent_mailroom.api.security import OFFICE_CSP
from agent_mailroom.llm.providers import resolve_harness

ROOT = Path(__file__).resolve().parents[1]


def test_office_pages_send_csp_and_hardening_headers():
    client = TestClient(create_app())
    page = client.get("/office/index.html")
    assert page.status_code == 200
    assert page.headers["content-security-policy"] == OFFICE_CSP
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["x-frame-options"] == "DENY"
    assert "unsafe-eval" not in page.headers["content-security-policy"]
    html = page.text
    assert "Content-Security-Policy" in html
    assert "/office/js/app.js" in html
    assert html.count("<script") == 1
    assert 'data-tab="inbox"' in html
    assert 'data-tab="archive"' in html
    assert 'data-tab="matters"' in html
    assert 'data-tab="failed"' in html
    assert 'data-testid="lookup-q"' in html
    js = client.get("/office/js/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers.get("content-type", "")


def test_health_reports_limezu_tilesets():
    client = TestClient(create_app())
    health = client.get("/v1/health").json()
    tiles = health["checks"]["tilesets"]
    assert tiles["present"] is True
    assert health["checks"]["desktop"] is False


def test_placeholder_openrouter_key_stays_on_mock(monkeypatch):
    monkeypatch.setenv("MAILROOM_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("MAILROOM_LLM_FALLBACK", "mock")
    monkeypatch.setenv("OPENROUTER_API_KEY", "changeme")
    _, _, info = resolve_harness()
    assert info["active"] == "mock"
    assert info["configured"] is False


def test_repo_has_no_openrouter_key_shapes():
    banned = "sk-or-" + "v1-"
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "node_modules", ".venv", "data", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".webp", ".db"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if banned in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_electron_security_contract():
    script = """
      const s = require('./electron/security.js');
      const p = s.webPreferences();
      console.log(JSON.stringify({
        nodeIntegration: p.nodeIntegration,
        sandbox: p.sandbox,
        contextIsolation: p.contextIsolation,
        webSecurity: p.webSecurity,
        navOk: s.isAllowedNavigation('http://127.0.0.1:8000/office/', 'http://127.0.0.1:8000'),
        navBad: s.isAllowedNavigation('https://evil.example/steal', 'http://127.0.0.1:8000'),
        extOk: s.isAllowedExternal('https://limezu.itch.io/moderninteriors'),
        extHttp: s.isAllowedExternal('http://limezu.itch.io/moderninteriors'),
        extBad: s.isAllowedExternal('https://evil.example/'),
        csp: s.OFFICE_CSP,
      }));
    """
    raw = subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True)
    data = json.loads(raw)
    assert data["nodeIntegration"] is False
    assert data["sandbox"] is True
    assert data["contextIsolation"] is True
    assert data["webSecurity"] is True
    assert data["navOk"] is True
    assert data["navBad"] is False
    assert data["extOk"] is True
    assert data["extHttp"] is False
    assert data["extBad"] is False
    assert data["csp"] == OFFICE_CSP
