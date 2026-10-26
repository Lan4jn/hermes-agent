"""Profile-scoped, independently revocable message API credentials."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
import os
import secrets
import sqlite3
import stat
import uuid

from hermes_constants import get_hermes_home


def _connect(*, create=False, write=False):
    path = get_hermes_home() / "message_api_keys.sqlite3"
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("message API key database must not be a symlink")
    if create:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
    if not path.exists():
        return None
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise OSError("message API key database must be a regular file")
    conn = sqlite3.connect(path.as_uri() + ("?mode=rw" if create or write else "?mode=ro"),
                           uri=True, timeout=5)
    try:
        if create or write:
            conn.execute("PRAGMA journal_mode=DELETE")
        if create:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS message_keys ("
                    "id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "key_hash BLOB NOT NULL UNIQUE)"
                )
    except BaseException:
        conn.close()
        raise
    return conn


def create_key(name):
    if (not isinstance(name, str) or not name.strip() or len(name) > 80
            or not name.isprintable()):
        raise ValueError("invalid message API key name")
    key = "hmmsg_" + secrets.token_urlsafe(32)
    record = {
        "id": uuid.uuid4().hex,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "key": key,
    }
    with closing(_connect(create=True)) as conn, conn:
        conn.execute(
            "INSERT INTO message_keys (id, name, created_at, key_hash) VALUES (?, ?, ?, ?)",
            (record["id"], name, record["created_at"], hashlib.sha256(key.encode()).digest()),
        )
    return record


def list_keys():
    conn = _connect()
    if conn is None:
        return []
    with closing(conn):
        return [
            {"id": row[0], "name": row[1], "created_at": row[2]}
            for row in conn.execute("SELECT id, name, created_at FROM message_keys ORDER BY created_at, id")
        ]


def revoke_key(id):
    conn = _connect(write=True)
    if conn is None:
        return False
    with closing(conn) as conn, conn:
        return conn.execute("DELETE FROM message_keys WHERE id = ?", (id,)).rowcount > 0


def validate_key(key):
    if not isinstance(key, str) or len(key) > 64 or not key.startswith("hmmsg_"):
        return False
    try:
        digest = hashlib.sha256(key.encode()).digest()
        conn = _connect()
        if conn is None:
            return False
        with closing(conn):
            row = conn.execute("SELECT key_hash FROM message_keys WHERE key_hash = ?", (digest,)).fetchone()
            return row is not None and hmac.compare_digest(row[0], digest)
    except (OSError, sqlite3.DatabaseError, UnicodeError):
        return False


def get_policy():
    conn = _connect()
    if conn is None:
        return {"require_chat_key": False}
    with closing(conn):
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'message_policy'"
        ).fetchone() is None:
            return {"require_chat_key": False}
        row = conn.execute("SELECT require_chat_key FROM message_policy WHERE id = 1").fetchone()
        return {"require_chat_key": bool(row[0]) if row else False}


def set_policy(require_chat_key):
    if not isinstance(require_chat_key, bool):
        raise ValueError("require_chat_key must be a boolean")
    with closing(_connect(create=True)) as conn, conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS message_policy ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), "
            "require_chat_key INTEGER NOT NULL CHECK (require_chat_key IN (0, 1)))"
        )
        conn.execute(
            "INSERT INTO message_policy (id, require_chat_key) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET require_chat_key = excluded.require_chat_key",
            (int(require_chat_key),),
        )
