from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from agent_mailroom.config.loader import base_dir

_DB_LOCK = threading.RLock()

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
    judge_verdict TEXT,
    judge_score REAL,
    judge_findings TEXT,
    arbiter_decision TEXT,
    arbiter_reasoning TEXT,
    arbiter_retry_count INTEGER DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS topics (
    topic_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT,
    route_to TEXT NOT NULL DEFAULT 'boss',
    status TEXT NOT NULL DEFAULT 'queued',
    doc_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topics_status ON topics(status);

CREATE TABLE IF NOT EXISTS pipeline_spans (
    span_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    name TEXT NOT NULL,
    observation_type TEXT DEFAULT 'span',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    latency_ms REAL,
    input_json TEXT,
    output_json TEXT,
    seq INTEGER NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_spans_doc ON pipeline_spans(doc_id, seq);

CREATE TABLE IF NOT EXISTS field_scores (
    doc_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    score REAL,
    method TEXT,
    detail TEXT,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (doc_id, field_name)
);
"""


def db_path() -> Path:
    return base_dir() / "mailroom.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            return conn
        except sqlite3.OperationalError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    raise last_error or sqlite3.OperationalError("database is locked")


def locked() -> threading.Lock:
    return _DB_LOCK


def init_db() -> None:
    with _DB_LOCK:
        with connect() as conn:
            conn.executescript(SCHEMA)
            _ensure_document_judgment_columns(conn)
            conn.commit()


def _ensure_document_judgment_columns(conn: sqlite3.Connection) -> None:
    """llm-mailroom v0.6.0: arbiter/judge fields persist on catalog rows."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    alters = [
        ("judge_verdict", "TEXT"),
        ("judge_score", "REAL"),
        ("judge_findings", "TEXT"),
        ("arbiter_decision", "TEXT"),
        ("arbiter_reasoning", "TEXT"),
        ("arbiter_retry_count", "INTEGER DEFAULT 0"),
    ]
    for name, decl in alters:
        if name not in existing:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {decl}")
