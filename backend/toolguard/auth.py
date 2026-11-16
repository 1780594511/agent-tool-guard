"""Opaque sessions, password verification and capabilities kept entirely on the server."""

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from .db import audit


class GuardError(Exception):
    def __init__(self, code: str, status: int = 403):
        self.code, self.status = code, status
        super().__init__(code)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    result = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"{salt.hex()}:{result.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt, expected = stored.split(":")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 210_000)
    return hmac.compare_digest(actual.hex(), expected)


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    name: str
    role: str
    revision: int
    privileges: tuple[str, ...]
    approval_scopes: tuple[str, ...]

    @classmethod
    def from_row(cls, row):
        return cls(
            row["id"],
            row["username"],
            row["name"],
            row["role"],
            row["revision"],
            tuple(json.loads(row["privileges"])),
            tuple(json.loads(row["approval_scopes"])),
        )

    def require(self, privilege: str):
        if privilege not in self.privileges:
            raise GuardError("PRIVILEGE_REQUIRED")


def authenticate(con, token: str | None, csrf: str | None = None) -> Principal:
    if not token or len(token) > 200:
        raise GuardError("SESSION_REQUIRED", 401)
    row = con.execute(
        "SELECT u.*,s.csrf_hash,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND u.active=1",
        (token_hash(token),),
    ).fetchone()
    if not row or row["expires_at"] <= time.time():
        raise GuardError("SESSION_EXPIRED", 401)
    if csrf is not None and not hmac.compare_digest(row["csrf_hash"], token_hash(csrf)):
        raise GuardError("CSRF_INVALID")
    return Principal.from_row(row)


def login(db, username: str, password: str) -> dict:
    error = None
    result = {}
    with db.transaction() as con:
        now = time.time()
        name_hash = token_hash(username)
        rate = con.execute("SELECT * FROM login_attempts WHERE name_hash=?", (name_hash,)).fetchone()
        if rate and rate["until"] > now and rate["attempts"] >= 10:
            error = GuardError("LOGIN_RATE_LIMIT", 429)
        else:
            row = con.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
            # Uniform expensive password work for unknown names as well.
            stored = row["password_hash"] if row else ("00" * 16 + ":" + "00" * 32)
            valid = check_password(password, stored)
            if not row or not valid:
                attempts = rate["attempts"] + 1 if rate and rate["until"] > now else 1
                con.execute(
                    "INSERT OR REPLACE INTO login_attempts VALUES (?,?,?)", (name_hash, attempts, now + 60)
                )
                audit(con, event="login", decision="deny", reason="INVALID_CREDENTIALS")
                error = GuardError("INVALID_CREDENTIALS", 401)
            else:
                token = secrets.token_urlsafe(32)
                csrf = token_hash("csrf:" + token)
                expiry = now + min(24, max(1, int(os.getenv("ATG_SESSION_HOURS", "8")))) * 3600
                con.execute("DELETE FROM login_attempts WHERE name_hash=?", (name_hash,))
                con.execute(
                    "INSERT INTO sessions VALUES (?,?,?,?)",
                    (token_hash(token), row["id"], token_hash(csrf), expiry),
                )
                audit(con, event="login", user_id=row["id"], decision="allow", reason="SESSION_CREATED")
                result = {"token": token, "csrf": csrf, "expires_at": expiry}
    if error:
        raise error
    return result
