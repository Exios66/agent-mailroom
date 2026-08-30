from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_mailroom.config.loader import base_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS matters (
    matter_id TEXT PRIMARY KEY,
    name TEXT,
    client_name TEXT,
    practice_area TEXT DEFAULT 'transactional',
    opened_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stage TEXT NOT NULL,
    graph_node TEXT,
    doc_type TEXT,
    contract_subtype TEXT,
    doc_subclass TEXT,
    classification_confidence REAL,
    extraction_confidence REAL,
    extracted_data TEXT,
    report TEXT,
    escalation_reason TEXT,
    review_decision TEXT,
    routing_path TEXT,
    trace_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    entry_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    matter_id TEXT NOT NULL,
    event TEXT NOT NULL,
    actor TEXT NOT NULL,
    detail TEXT,
    prev_hash TEXT DEFAULT '',
    entry_hash TEXT DEFAULT '',
    seq INTEGER DEFAULT 0,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_audit_doc ON audit_log(doc_id, seq);
CREATE INDEX IF NOT EXISTS idx_docs_stage ON documents(stage);
"""


def db_path() -> Path:
    return base_dir() / "mailroom.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
