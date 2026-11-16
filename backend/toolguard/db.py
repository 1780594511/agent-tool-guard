"""SQLite is the atomic boundary for simulated effects, approval consumption and audit."""

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 revision INTEGER NOT NULL DEFAULT 1, privileges TEXT NOT NULL, approval_scopes TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 csrf_hash TEXT NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, classification TEXT NOT NULL,
 body TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS grants (
 user_id TEXT NOT NULL REFERENCES users(id), document_id TEXT NOT NULL REFERENCES documents(id),
 PRIMARY KEY(user_id, document_id)
);
CREATE TABLE IF NOT EXISTS policies (
 version TEXT PRIMARY KEY, body TEXT NOT NULL, created_at REAL NOT NULL,
 author TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_policy ON policies(active) WHERE active=1;
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), request_key TEXT NOT NULL,
 request_hash TEXT NOT NULL, prompt_preview TEXT NOT NULL, provider TEXT NOT NULL,
 status TEXT NOT NULL, steps INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
 deadline_at REAL NOT NULL, ended_at REAL, error TEXT,
 UNIQUE(user_id, request_key)
);
CREATE TABLE IF NOT EXISTS calls (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), user_id TEXT NOT NULL REFERENCES users(id),
 idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL, tool TEXT NOT NULL,
 arguments TEXT NOT NULL, arguments_preview TEXT NOT NULL, resources TEXT NOT NULL,
 policy_version TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
 approval_id TEXT, result TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL, duration_ms REAL NOT NULL DEFAULT 0,
 UNIQUE(user_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS approvals (
 id TEXT PRIMARY KEY, call_id TEXT NOT NULL UNIQUE REFERENCES calls(id),
 user_id TEXT NOT NULL REFERENCES users(id), tool TEXT NOT NULL, arguments TEXT NOT NULL,
 resources TEXT NOT NULL, destination TEXT NOT NULL, policy_version TEXT NOT NULL,
 subject_revision INTEGER NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL,
 created_at REAL NOT NULL, expires_at REAL NOT NULL, approver_id TEXT REFERENCES users(id),
 decided_at REAL, consumed_at REAL
);
CREATE TABLE IF NOT EXISTS tickets (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), call_id TEXT UNIQUE NOT NULL,
 title TEXT NOT NULL, body TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS inbox (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), call_id TEXT UNIQUE NOT NULL,
 destination TEXT NOT NULL, document_ids TEXT NOT NULL, payload TEXT NOT NULL,
 approval_id TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS read_receipts (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), call_id TEXT UNIQUE NOT NULL,
 document_id TEXT NOT NULL, version INTEGER NOT NULL, content_hash TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, event TEXT NOT NULL,
 task_id TEXT, call_id TEXT, user_id TEXT, tool TEXT, resource_ids TEXT NOT NULL,
 policy_version TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL,
 approval_id TEXT, execution_status TEXT NOT NULL, duration_ms REAL NOT NULL,
 metadata TEXT NOT NULL, previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'append only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'append only'); END;
CREATE TABLE IF NOT EXISTS evaluations (
 id TEXT PRIMARY KEY, created_at REAL NOT NULL, user_id TEXT NOT NULL,
 status TEXT NOT NULL, config TEXT NOT NULL, result TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS login_attempts (name_hash TEXT PRIMARY KEY, attempts INTEGER NOT NULL, until REAL NOT NULL);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = self.connect()
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
        finally:
            con.close()

    @contextmanager
    def transaction(self):
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()


def audit(
    con,
    *,
    event,
    user_id=None,
    task_id=None,
    call_id=None,
    tool=None,
    resources=(),
    policy_version="unknown",
    decision="info",
    reason="",
    approval_id=None,
    status="none",
    duration_ms=0,
    metadata=None,
):
    previous = con.execute("SELECT entry_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    entry = dict(
        timestamp=time.time(),
        event=event,
        task_id=task_id,
        call_id=call_id,
        user_id=user_id,
        tool=tool,
        resource_ids=canonical(list(resources)),
        policy_version=policy_version,
        decision=decision,
        reason=reason,
        approval_id=approval_id,
        execution_status=status,
        duration_ms=round(float(duration_ms), 3),
        metadata=canonical(metadata or {}),
        previous_hash=previous[0] if previous else "0" * 64,
    )
    entry["entry_hash"] = digest(entry)
    con.execute(
        f"INSERT INTO audit ({','.join(entry)}) VALUES ({','.join('?' for _ in entry)})",
        tuple(entry.values()),
    )


def verify_audit(con) -> dict:
    previous = "0" * 64
    count = 0
    for row in con.execute("SELECT * FROM audit ORDER BY seq"):
        record = dict(row)
        record.pop("seq")
        claimed = record.pop("entry_hash")
        if record["previous_hash"] != previous or digest(record) != claimed:
            return {"valid": False, "checked": count, "broken_at": row["seq"]}
        previous = claimed
        count += 1
    return {"valid": True, "checked": count, "head": previous}
