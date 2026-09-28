from __future__ import annotations

import os
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Keep this in lockstep with office/index.html (whose <meta> copy omits
# frame-ancestors: browsers ignore it there and log an error) and
# electron/security.js.
OFFICE_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data:; "
    "connect-src 'self' ws: wss:; "
    "worker-src 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}


def cors_origins() -> list[str]:
    raw = os.environ.get("MAILROOM_CORS_ORIGINS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    port = os.environ.get("MAILROOM_PORT", "8000")
    host = os.environ.get("MAILROOM_HOST", "127.0.0.1")
    origins = [
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    ]
    if host not in {"127.0.0.1", "localhost", "0.0.0.0", "::", "::1"}:
        origins.append(f"http://{host}:{port}")
    return origins


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_public_bind() -> bool:
    """A non-loopback ``MAILROOM_HOST`` (0.0.0.0, a LAN IP, a hostname)."""
    host = os.environ.get("MAILROOM_HOST", "127.0.0.1").strip().strip("[]").lower()
    return host not in LOOPBACK_HOSTS


def open_mode_allowed() -> bool:
    """``MAILROOM_ALLOW_OPEN=1`` acknowledges a tokenless public bind (e.g. the
    compose file, which publishes the port on host loopback only)."""
    return os.environ.get("MAILROOM_ALLOW_OPEN", "").strip().lower() in {"1", "true", "yes", "on"}


def origin_allowed(origin: str | None, host: str | None) -> bool:
    """Browser WebSocket / write Origin check. A missing Origin is a non-browser
    client (TUI, curl) and is governed by the token alone."""
    if not origin:
        return True
    if origin in set(cors_origins()):
        return True
    try:
        netloc = urlsplit(origin).netloc.lower()
    except ValueError:
        return False
    return bool(host) and netloc == str(host).lower()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Browser-testing hardened headers. Office pages also get a strict CSP."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        path = request.url.path
        if path == "/" or path.startswith("/office"):
            response.headers["Content-Security-Policy"] = OFFICE_CSP
        return response
