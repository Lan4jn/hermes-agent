"""Persistent message API keys and per-profile policy contracts."""

from contextlib import closing
import os
import sqlite3
import stat
import subprocess
import sys

import pytest

from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from gateway.platforms import message_api_keys as keys


def test_key_lifecycle_and_disk_secrecy(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    issued = keys.create_key("chat")
    db = tmp_path / "message_api_keys.sqlite3"
    assert issued["key"].startswith("hmmsg_")
    assert set(issued) == {"id", "name", "created_at", "key"}
    assert keys.list_keys() == [{k: issued[k] for k in ("id", "name", "created_at")}]
    assert issued["key"].encode() not in db.read_bytes()
    assert keys.validate_key(issued["key"])
    assert not keys.validate_key("hmmsg_invalid")
    assert keys.revoke_key(issued["id"])
    assert not keys.revoke_key(issued["id"])
    assert not keys.validate_key(issued["key"])
    assert keys.list_keys() == []


def test_keys_open_in_another_process_and_isolate_profiles(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(a))
    issued = keys.create_key("a")
    result = subprocess.run(
        [sys.executable, "-c",
         "from gateway.platforms.message_api_keys import validate_key; "
         "import sys; sys.exit(0 if validate_key(sys.argv[1]) else 1)",
         issued["key"]],
        env=os.environ.copy(), capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    token = set_hermes_home_override(b)
    try:
        assert not keys.validate_key(issued["key"])
        other = keys.create_key("b")
        assert keys.list_keys()[0]["id"] == other["id"]
    finally:
        reset_hermes_home_override(token)
    assert keys.list_keys()[0]["id"] == issued["id"]
    assert not keys.validate_key(other["key"])


@pytest.mark.parametrize("name", ["", " ", "x" * 81, "a\nb", "a\x00b", "a\u200bb"])
def test_invalid_names(tmp_path, monkeypatch, name):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        keys.create_key(name)


def test_reads_leave_wal_alone_and_writes_switch_to_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    issued = keys.create_key("wal")
    db = tmp_path / "message_api_keys.sqlite3"
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
    assert keys.validate_key(issued["key"])
    assert keys.list_keys()[0]["id"] == issued["id"]
    assert keys.get_policy() == {"require_chat_key": False}
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    keys.set_policy(True)
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    assert keys.validate_key(issued["key"])


def test_invalid_surrogate_key_returns_false(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    keys.create_key("valid")
    assert keys.validate_key("hmmsg_\ud800") is False


def test_corrupt_database_fails_closed_without_replacement(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = tmp_path / "message_api_keys.sqlite3"
    db.write_bytes(b"not a database")
    with pytest.raises(Exception):
        keys.create_key("safe")
    assert not keys.validate_key("hmmsg_any")
    assert db.read_bytes() == b"not a database"


def test_symlink_database_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    target = tmp_path / "target"
    target.write_text("unchanged")
    link = tmp_path / "message_api_keys.sqlite3"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(OSError):
        keys.create_key("safe")
    assert not keys.validate_key("hmmsg_any")
    assert target.read_text() == "unchanged"


@pytest.mark.platforms("posix")
def test_database_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    keys.create_key("safe")
    assert stat.S_IMODE((tmp_path / "message_api_keys.sqlite3").stat().st_mode) == 0o600


def test_policy_persists_without_touching_yaml_and_isolates_profiles(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(a))
    yaml = a / "config.yaml"
    original = b"\xff\x00opaque config bytes\n"
    yaml.write_bytes(original)
    assert keys.get_policy() == {"require_chat_key": False}
    assert not (a / "message_api_keys.sqlite3").exists()
    issued = keys.create_key("stays valid")
    assert keys.get_policy() == {"require_chat_key": False}
    keys.set_policy(True)
    assert keys.validate_key(issued["key"])
    with sqlite3.connect(a / "message_api_keys.sqlite3") as conn:
        assert conn.execute("SELECT id, require_chat_key FROM message_policy").fetchall() == [(1, 1)]
    assert yaml.read_bytes() == original
    child = subprocess.run(
        [sys.executable, "-c",
         "from gateway.platforms.message_api_keys import get_policy, validate_key; "
         "import sys; sys.exit(0 if get_policy()['require_chat_key'] "
         "and validate_key(sys.argv[1]) else 1)", issued["key"]],
        env=os.environ.copy(), capture_output=True, check=False,
    )
    assert child.returncode == 0, child.stderr.decode()
    token = set_hermes_home_override(b)
    try:
        assert keys.get_policy() == {"require_chat_key": False}
        assert not (b / "message_api_keys.sqlite3").exists()
        keys.set_policy(True)
        assert keys.get_policy() == {"require_chat_key": True}
    finally:
        reset_hermes_home_override(token)
    assert keys.get_policy() == {"require_chat_key": True}
    keys.set_policy(False)
    assert keys.get_policy() == {"require_chat_key": False}
    assert keys.validate_key(issued["key"])
    child = subprocess.run(
        [sys.executable, "-c",
         "from gateway.platforms.message_api_keys import get_policy, validate_key; "
         "import sys; sys.exit(0 if not get_policy()['require_chat_key'] "
         "and validate_key(sys.argv[1]) else 1)", issued["key"]],
        env=os.environ.copy(), capture_output=True, check=False,
    )
    assert child.returncode == 0, child.stderr.decode()
    assert yaml.read_bytes() == original
    with sqlite3.connect(a / "message_api_keys.sqlite3") as conn:
        assert conn.execute("SELECT id, require_chat_key FROM message_policy").fetchall() == [(1, 0)]


def test_policy_does_not_create_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    keys.set_policy(True)
    assert keys.get_policy() == {"require_chat_key": True}
    assert not (tmp_path / "config.yaml").exists()


def test_policy_concurrent_writes_follow_database_order(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    keys.set_policy(False)
    db = tmp_path / "message_api_keys.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            "CREATE TABLE policy_audit (sequence INTEGER PRIMARY KEY, value INTEGER NOT NULL);"
            "CREATE TRIGGER policy_updated AFTER UPDATE ON message_policy BEGIN "
            "INSERT INTO policy_audit(value) VALUES (NEW.require_chat_key); END;"
        )
    code = (
        "import sys; from gateway.platforms.message_api_keys import set_policy; "
        "sys.stdin.buffer.read(1); "
        "[(set_policy(sys.argv[1] == 'true')) for _ in range(12)]"
    )
    children = [
        subprocess.Popen([sys.executable, "-c", code, value], env=os.environ.copy(),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for value in ("true", "false")
    ]
    for child in children:
        child.stdin.write(b"x")
        child.stdin.flush()
    for child in children:
        output, error = child.communicate(timeout=30)
        assert child.returncode == 0, (output, error)
    with sqlite3.connect(db) as conn:
        latest = conn.execute("SELECT value FROM policy_audit ORDER BY sequence DESC LIMIT 1").fetchone()
        stored = conn.execute("SELECT id, require_chat_key FROM message_policy").fetchall()
        assert len(conn.execute("SELECT value FROM policy_audit").fetchall()) == 24
    assert stored == [(1, latest[0])]
    assert keys.get_policy() == {"require_chat_key": bool(latest[0])}


@pytest.mark.parametrize("kind", ["corrupt", "directory"])
def test_policy_existing_invalid_database_fails_closed(tmp_path, monkeypatch, kind):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = tmp_path / "message_api_keys.sqlite3"
    if kind == "corrupt":
        db.write_bytes(b"not sqlite")
    elif kind == "directory":
        db.mkdir()
    with pytest.raises((OSError, sqlite3.DatabaseError)):
        keys.get_policy()
    if kind == "corrupt":
        assert db.read_bytes() == b"not sqlite"


def test_policy_unreadable_database_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    keys.set_policy(True)
    real_connect = sqlite3.connect

    def denied(database, *args, **kwargs):
        if "message_api_keys.sqlite3" in str(database):
            raise PermissionError("database unavailable")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", denied)
    with pytest.raises(PermissionError):
        keys.get_policy()
