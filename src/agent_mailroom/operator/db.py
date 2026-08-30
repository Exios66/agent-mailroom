from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Optional

from agent_mailroom.config.loader import base_dir

log = logging.getLogger(__name__)

ROLES = frozenset({"admin", "reviewer", "viewer"})


def db_path() -> Path:
    explicit = os.environ.get("MAILROOM_OPERATOR_DB", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return base_dir() / "operator.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    try:
        import bcrypt

        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    except ImportError:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), 200_000
        ).hex()
        return f"pbkdf2${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("$2"):
        try:
            import bcrypt
        except ImportError:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("ascii"))
        except ValueError:
            return False
    if stored.startswith("pbkdf2$"):
        parts = stored.split("$", 2)
        if len(parts) != 3:
            return False
        _, salt, digest = parts
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), 200_000
        ).hex()
        return hmac.compare_digest(check, digest)
    return False


def migrate() -> Path:
    path = db_path()
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ui_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT CHECK(role IN ('admin', 'reviewer', 'viewer')) DEFAULT 'viewer',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ui_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES ui_users(id),
                action TEXT NOT NULL,
                target_doc_id TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        row = conn.execute("SELECT COUNT(*) AS n FROM ui_users").fetchone()
        if int(row["n"]) == 0:
            username = os.environ.get("MAILROOM_OPERATOR_USER", "operator").strip() or "operator"
            password = os.environ.get("MAILROOM_OPERATOR_PASSWORD", "mailroom").strip() or "mailroom"
            role = os.environ.get("MAILROOM_OPERATOR_ROLE", "admin").strip() or "admin"
            if role not in ROLES:
                role = "admin"
            conn.execute(
                "INSERT INTO ui_users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
            log.info("seeded default operator user %s", username)
        conn.commit()
    finally:
        conn.close()
    return path


def lookup_user(username: str) -> Optional[dict[str, Any]]:
    migrate()
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM ui_users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def write_audit(*, action: str, user_id: int | None = None, metadata: dict[str, Any] | None = None) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO ui_audit (user_id, action, metadata) VALUES (?, ?, ?)",
            (user_id, action, json.dumps(metadata or {})),
        )
        conn.commit()
    finally:
        conn.close()
