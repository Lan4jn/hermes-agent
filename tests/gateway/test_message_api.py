"""Behavioral contracts for the optional /message gateway surface."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
import time
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms import message_api_keys
from gateway.platforms.api_server import APIServerAdapter


@pytest_asyncio.fixture
async def server():
    clients = []

    async def start(message_api=None, *, key="admin-secret"):
        adapter = APIServerAdapter(PlatformConfig(
            enabled=True, extra={"key": key, "message_api": message_api or {}}))
        app = web.Application()
        for method, path, handler in adapter._http_route_table():
            app.router.add_route(method, path, handler)
        client = TestClient(TestServer(app))
        await client.start_server()
        clients.append(client)
        return adapter, client

    yield start
    for client in clients:
        await client.close()


@pytest.mark.asyncio
async def test_chat_policy_is_live_and_chat_key_never_grants_execution(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server({"allow_command_execution": True, "api_keys": ["legacy-secret"]})
    adapter._run_agent = AsyncMock(return_value=({"final_response": "hello", "session_id": "s1"}, {}))
    adapter._execute_message_api_command = lambda *a, **k: {"output": "ok", "exit_code": 0}
    chat = message_api_keys.create_key("reader")["key"]

    response = await client.post("/message", json={"message": "hi", "session_id": "peer"})
    assert response.status == 200
    assert (await response.json())["reply"] == "hello"
    assert adapter._run_agent.await_count == 1

    message_api_keys.set_policy(True)
    response = await client.post("/message", json={"message": "hi"})
    assert response.status == 401
    assert adapter._run_agent.await_count == 1
    response = await client.post("/message", json={"message": "hi"},
                                 headers={"X-Hermes-Message-Key": chat})
    assert response.status == 200
    response = await client.post("/message", json={"message": "hi"},
                                 headers={"X-Hermes-Api-Key": chat})
    assert response.status == 200
    response = await client.post("/message", json={"message": "hi", "command": "echo secret",
                                                   "api_key": chat})
    assert response.status == 200
    payload = await response.json()
    assert payload["command"]["requested"] and not payload["command"]["executed"]
    assert "exec_token" not in payload and "secret" not in json.dumps(payload)
    response = await client.post("/message", json={"command": "echo ok", "api_key": chat})
    assert response.status == 401
    response = await client.post("/message", json={"command": "echo ok", "api_key": "legacy-secret"})
    assert response.status == 200
    assert (await response.json())["command"]["executed"]
    response = await client.post("/message", json={"message": "hi"},
                                 headers={"Authorization": "Bearer admin-secret"})
    assert response.status == 200
    response = await client.get("/v1/capabilities",
                                headers={"Authorization": "Bearer admin-secret"})
    capabilities = await response.json()
    assert capabilities["features"]["message_api"]
    assert capabilities["endpoints"]["message_api"]["path"] == "/message"
    assert capabilities["endpoints"]["message_session"]["path"].endswith("/{session_id}")

    message_api_keys.set_policy(False)
    response = await client.post("/message", json={"message": "hi"})
    assert response.status == 200


@pytest.mark.asyncio
async def test_command_token_and_disabled_modes(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server({"allow_command_execution": True, "api_keys": ["legacy"]})
    adapter._run_agent = AsyncMock(return_value=({"final_response": "ok"}, {}))
    adapter._execute_message_api_command = lambda *a, **k: {"output": "ok", "exit_code": 0}
    response = await client.post("/message", json={"api_key": "legacy"})
    assert response.status == 200
    token = (await response.json())["exec_token"]
    assert adapter._run_agent.await_count == 0
    response = await client.post("/message", json={"command": "echo ok", "exec_token": token})
    assert response.status == 200
    assert (await response.json())["command"]["authorized"]
    other_home = tmp_path / "other"
    other_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(other_home))
    assert (await client.post("/message", json={"command": "echo ok", "exec_token": token})).status == 401
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    response = await client.post("/message", json={"command": "echo ok"},
                                 headers={"Authorization": "Bearer admin-secret"})
    assert response.status == 200
    response = await client.post("/message", json={"command": "echo ok"})
    assert response.status == 401

    _, disabled = await server()
    response = await disabled.post("/message", json={"command": "echo no"})
    assert response.status == 403
    response = await disabled.post("/message", data="{broken", headers={"Content-Type": "application/json"})
    assert response.status == 400
    _, absent = await server({"enabled": False})
    assert (await absent.post("/message", json={"message": "hi"})).status == 404


@pytest.mark.asyncio
async def test_broken_policy_and_provider_errors_fail_closed(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server()
    adapter._run_agent = AsyncMock(side_effect=RuntimeError("provider-secret-raw"))
    message_api_keys.set_policy(True)
    (tmp_path / "message_api_keys.sqlite3").write_bytes(b"corrupted")
    response = await client.post("/message", json={"message": "hi"})
    assert response.status != 200
    assert adapter._run_agent.await_count == 0
    (tmp_path / "message_api_keys.sqlite3").unlink()
    response = await client.post("/message", json={"message": "hi"})
    assert response.status == 500
    assert "provider-secret-raw" not in await response.text()


@pytest.mark.asyncio
async def test_optional_note_failure_does_not_discard_chat_reply(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server({"shared_memory_notes_enabled": True})
    adapter._run_agent = AsyncMock(return_value=({"final_response": "completed"}, {}))
    adapter._record_message_note = lambda *args: (_ for _ in ()).throw(OSError("disk failed"))
    response = await client.post("/message", json={"message": "hi"})
    assert response.status == 200
    assert (await response.json())["reply"] == "completed"


@pytest.mark.asyncio
async def test_history_requires_admin_and_only_lists_message_sessions(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server({"webui_history_enabled": True})
    db = await adapter._ensure_session_db_async()
    # Real SessionDB integration: the row's declared conversation key is the
    # isolation marker; unrelated API sessions must never be visible.
    db.create_session("msg-row", source="api_server")
    db.record_gateway_session_peer("msg-row", source="api_server", session_key="message_api:peer")
    db.create_session("other-row", source="api_server")
    assert (await client.get("/api/message/sessions")).status == 401
    headers = {"Authorization": "Bearer admin-secret"}
    response = await client.get("/api/message/sessions", headers=headers)
    assert response.status == 200
    rows = await response.json()
    assert any(row["id"] == "msg-row" for row in rows)
    assert not any(row["id"] == "other-row" for row in rows)
    assert (await client.get("/api/message/sessions/other-row", headers=headers)).status == 404
    assert (await client.get("/api/message/sessions/msg-row", headers=headers)).status == 200


@pytest.mark.asyncio
async def test_session_continuity_and_profile_scoped_history(server, tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(a))
    adapter, client = await server({"webui_history_enabled": True})
    db_a = await adapter._ensure_session_db_async()
    observed = []

    async def run(**kwargs):
        observed.append(kwargs)
        if len(observed) == 1:
            db_a.create_session("transcript-a", source="api_server")
            adapter._bind_declared_conversation("transcript-a", kwargs["gateway_session_key"])
        return {"final_response": "ok", "session_id": "transcript-a"}, {}

    adapter._run_agent = run
    first = await client.post("/message", json={"message": "hello", "session_id": "peer"})
    assert (await first.json())["session_id"] == "transcript-a"
    second = await client.post("/message", json={"message": "again", "session_id": "transcript-a"})
    assert second.status == 200
    assert observed[0]["session_id"] is None
    assert observed[1]["session_id"] == "transcript-a"
    assert observed[1]["gateway_session_key"] == observed[0]["gateway_session_key"] == "message_api:peer"
    assert observed[1]["bind_declared_conversation"]
    assert observed[1]["turn_author"]["id"] == "message_api:remote-peer"
    headers = {"Authorization": "Bearer admin-secret"}
    assert (await client.get("/api/message/sessions/transcript-a", headers=headers)).status == 200

    monkeypatch.setenv("HERMES_HOME", str(b))
    response = await client.get("/api/message/sessions", headers=headers)
    assert response.status == 200 and await response.json() == []
    assert (await client.get("/api/message/sessions/transcript-a", headers=headers)).status == 404
    message_api_keys.set_policy(True)
    assert (await client.post("/message", json={"message": "from b"})).status == 401
    monkeypatch.setenv("HERMES_HOME", str(a))
    assert (await client.get("/api/message/sessions/transcript-a", headers=headers)).status == 200
    assert (await client.post("/message", json={"message": "from a"})).status == 200


@pytest.mark.asyncio
async def test_chat_key_cannot_be_promoted_by_legacy_config(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    chat = message_api_keys.create_key("chat")["key"]
    adapter, client = await server({"allow_command_execution": True, "api_keys": [chat]})
    adapter._execute_message_api_command = lambda *a, **k: pytest.fail("chat key executed command")
    response = await client.post("/message", json={"command": "echo no", "api_key": chat})
    assert response.status == 401
    assert "exec_token" not in await response.text()


@pytest.mark.asyncio
async def test_command_uses_original_peer_key_after_session_rotation(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server({"allow_command_execution": True})
    db = await adapter._ensure_session_db_async()
    db.create_session("transcript", source="api_server")
    db.record_gateway_session_peer("transcript", source="api_server", session_key="message_api:peer")
    task_ids = []
    adapter._execute_message_api_command = lambda cmd, task_id: (
        task_ids.append(task_id) or {"output": "ok", "exit_code": 0})
    response = await client.post("/message", json={"session_id": "transcript", "command": "echo ok"},
                                 headers={"Authorization": "Bearer admin-secret"})
    assert response.status == 200
    assert task_ids == ["message_api:peer"]


def test_terminal_command_uses_existing_runtime(monkeypatch):
    import tools.terminal_tool as terminal

    captured = {}

    def execute(**kwargs):
        captured.update(kwargs)
        return '{"output":"ok","exit_code":0}'

    monkeypatch.setattr(terminal, "terminal_tool", execute)
    result = APIServerAdapter._execute_message_api_command("echo ok", "message_api:peer")
    assert result == '{"output":"ok","exit_code":0}'
    assert captured == {"command": "echo ok", "task_id": "message_api:peer", "force": True}


@pytest.mark.asyncio
async def test_admission_counts_pending_work_and_rejects_drain_and_cap(server):
    adapter, client = await server()
    started, finish = asyncio.Event(), asyncio.Event()

    async def run(**kwargs):
        started.set()
        await finish.wait()
        return {"final_response": "ok"}, {}

    adapter._run_agent = run
    adapter._max_concurrent_runs = 1
    first = asyncio.create_task(client.post("/message", json={"message": "hi"}))
    await asyncio.wait_for(started.wait(), 15)
    try:
        assert adapter.active_agent_work_count() >= 1
        assert (await client.post("/message", json={"message": "again"})).status == 429
        adapter._gateway_is_draining = lambda: True
        assert (await client.post("/message", json={"message": "again"})).status == 503
    finally:
        finish.set()
        response = await first
        assert response.status == 200


@pytest.mark.asyncio
async def test_oversized_chat_key_is_rejected_without_hashing(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    message_api_keys.set_policy(True)
    adapter, client = await server()
    adapter._run_agent = AsyncMock()
    response = await client.post("/message", json={"message": "hi", "chat_key": "hmmsg_" + "x" * 100_000})
    assert response.status == 401
    assert adapter._run_agent.await_count == 0


def test_oversized_key_never_reaches_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    message_api_keys.create_key("normal")
    monkeypatch.setattr(message_api_keys.hashlib, "sha256",
                        lambda *_: pytest.fail("oversized credential was hashed"))
    assert not message_api_keys.validate_key("hmmsg_" + "x" * 100_000)


@pytest.mark.asyncio
async def test_pending_admission_precedes_body_read(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter = APIServerAdapter(PlatformConfig(enabled=True))
    reading, release = asyncio.Event(), asyncio.Event()

    class SlowRequest:
        headers = {}

        async def json(self):
            reading.set()
            await release.wait()
            return {"message": "hi"}

    adapter._run_agent = AsyncMock(return_value=({"final_response": "ok"}, {}))
    task = asyncio.create_task(adapter._handle_message_api(SlowRequest()))
    await reading.wait()
    try:
        assert adapter.active_agent_work_count() == 1
    finally:
        release.set()
        await task
    assert adapter.active_agent_work_count() == 0


@pytest.mark.asyncio
async def test_exec_token_does_not_authorize_chat(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    message_api_keys.set_policy(True)
    adapter, client = await server({"allow_command_execution": True, "api_keys": ["legacy"]})
    adapter._run_agent = AsyncMock(return_value=({"final_response": "ok"}, {}))
    adapter._execute_message_api_command = lambda *a, **k: {"output": "ok", "exit_code": 0}
    issued = await client.post("/message", json={"command": "echo ok", "api_key": "legacy"})
    token = (await issued.json())["exec_token"]
    blocked = await client.post("/message", json={"message": "private", "exec_token": token})
    assert blocked.status == 401
    assert adapter._run_agent.await_count == 0
    command = await client.post("/message", json={"command": "echo ok", "exec_token": token})
    assert command.status == 200 and (await command.json())["command"]["executed"]
    executed = []
    adapter._execute_message_api_command = lambda *args: executed.append(args)
    adapter._message_token_store._tokens[(str(tmp_path), token)] = 0
    expired = await client.post("/message", json={"command": "echo expired", "exec_token": token})
    assert expired.status == 401
    assert not executed


@pytest.mark.asyncio
async def test_chat_key_only_does_not_issue_token_and_null_command_is_chat(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    chat_key = message_api_keys.create_key("chat only")["key"]
    message_api_keys.set_policy(True)
    adapter, client = await server({"allow_command_execution": True, "api_keys": ["legacy"]})
    adapter._run_agent = AsyncMock(return_value=({"final_response": "hello"}, {}))
    executed = []
    adapter._execute_message_api_command = lambda *args: executed.append(args)

    key_only = await client.post("/message", json={"api_key": chat_key})
    assert key_only.status == 200
    assert "exec_token" not in await key_only.text()
    response = await client.post("/message", json={
        "message": "hi", "command": None, "chat_key": chat_key})
    assert response.status == 200
    payload = await response.json()
    assert payload["reply"] == "hello"
    assert payload["command"] == {"requested": False, "authorized": False, "executed": False}
    assert "exec_token" not in payload
    assert adapter._run_agent.await_count == 1 and not executed


@pytest.mark.asyncio
async def test_command_only_obeys_cap_and_drain(server):
    adapter, client = await server({"allow_command_execution": True})
    adapter._max_concurrent_runs = 1
    started, finish = threading.Event(), threading.Event()
    commands = []

    def execute(command, session_key):
        commands.append(command)
        started.set()
        assert finish.wait(30)
        return {"output": "ok", "exit_code": 0}

    adapter._execute_message_api_command = execute
    headers = {"Authorization": "Bearer admin-secret"}
    first = asyncio.create_task(client.post("/message", json={"command": "first"}, headers=headers))
    assert await asyncio.to_thread(started.wait, 15)
    try:
        assert adapter.active_agent_work_count() == 2
        blocked = await client.post("/message", json={"command": "second"}, headers=headers)
        assert blocked.status == 429
        assert commands == ["first"]
        adapter._gateway_is_draining = lambda: True
        draining = await client.post("/message", json={"command": "third"}, headers=headers)
        assert draining.status == 503
        assert commands == ["first"]
    finally:
        finish.set()
        assert (await first).status == 200


@pytest.mark.asyncio
async def test_cancelled_command_remains_counted_until_worker_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter = APIServerAdapter(PlatformConfig(
        enabled=True, extra={"key": "admin-secret", "message_api": {"allow_command_execution": True}}))
    adapter._max_concurrent_runs = 1
    started, release = threading.Event(), threading.Event()

    def execute(command, session_key):
        started.set()
        assert release.wait(30)
        return {"output": "ok", "exit_code": 0}

    adapter._execute_message_api_command = execute

    class Request:
        headers = {"Authorization": "Bearer admin-secret"}

        async def json(self):
            return {"command": "echo ok"}

    task = asyncio.create_task(adapter._handle_message_api(Request()))
    assert await asyncio.to_thread(started.wait, 15)
    try:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert adapter.active_agent_work_count() == 1
        blocked = await adapter._handle_message_api(Request())
        assert blocked.status == 429
    finally:
        release.set()
        for _ in range(100):
            if adapter.active_agent_work_count() == 0:
                break
            await asyncio.sleep(0.01)
    assert adapter.active_agent_work_count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_read", ["policy", "chat_key", "session"])
async def test_locked_sqlite_read_keeps_event_loop_responsive(
    server, tmp_path, monkeypatch, blocked_read,
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server()
    adapter._run_agent = AsyncMock(return_value=({"final_response": "ok"}, {}))
    body = {"message": "hi"}
    if blocked_read == "session":
        db = await adapter._ensure_session_db_async()
        db.create_session("existing", source="api_server")
        path = tmp_path / "state.db"
    else:
        chat = message_api_keys.create_key("chat")["key"]
        message_api_keys.set_policy(True)
        body["chat_key"] = chat
        path = tmp_path / "message_api_keys.sqlite3"
        if blocked_read == "chat_key":
            monkeypatch.setattr(message_api_keys, "get_policy", lambda: {"require_chat_key": True})

    locker = sqlite3.connect(path, check_same_thread=False)
    locker.execute("BEGIN EXCLUSIVE")
    timer = threading.Timer(1.0, locker.rollback)
    timer.start()
    try:
        start = time.monotonic()
        request = asyncio.create_task(client.post("/message", json=body))
        await asyncio.sleep(0.05)
        assert time.monotonic() - start < 0.7, "SQLite lock blocked the aiohttp event loop"
        response = await request
        assert response.status == 200
    finally:
        timer.join(2)
        locker.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [
    "message", "command", "session_id", "sender_id", "sender_display_name",
    "api_key", "chat_key", "exec_token",
])
@pytest.mark.parametrize("value", [{}, ["not", "text"]], ids=["object", "list"])
async def test_non_string_request_fields_are_rejected(server, field, value):
    adapter, client = await server({"allow_command_execution": True})
    adapter._run_agent = AsyncMock()
    commands = []
    adapter._execute_message_api_command = lambda *a: commands.append(a)
    response = await client.post("/message", json={"message": "hi", "command": "echo ok", field: value},
                                 headers={"Authorization": "Bearer admin-secret"})
    assert response.status == 400
    assert adapter._run_agent.await_count == 0 and not commands


@pytest.mark.asyncio
async def test_sender_fallback_and_optional_switches(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server()
    observed = []

    async def run(**kwargs):
        observed.append(kwargs)
        return {"final_response": "reply"}, {}

    adapter._run_agent = run
    response = await client.post("/message", json={"message": "hi", "sender_id": "alice",
                                                   "sender_display_name": "Alice"})
    assert response.status == 200
    assert (await response.json())["session_id"] == "alice"
    assert observed[-1]["gateway_session_key"] == "message_api:alice"
    assert observed[-1]["turn_author"]["id"] == "message_api:alice"
    assert observed[-1]["session_history_delivery"] == ""
    assert (await client.get("/api/message/sessions",
                             headers={"Authorization": "Bearer admin-secret"})).status == 404
    assert not (tmp_path / "memories" / "node_messages").exists()

    enabled, enabled_client = await server({
        "webui_history_enabled": True, "shared_memory_notes_enabled": True,
        "session_history_delivery": True,
    })
    enabled._run_agent = run
    response = await enabled_client.post("/message", json={"message": "hi", "sender_id": "alice"})
    assert response.status == 200
    assert observed[-1]["session_history_delivery"] == "1"
    assert list((tmp_path / "memories" / "node_messages").glob("*.md"))
    assert (await enabled_client.get("/api/message/sessions",
                                     headers={"Authorization": "Bearer admin-secret"})).status == 200


@pytest.mark.asyncio
async def test_message_routes_use_real_multiplex_profile_middleware(tmp_path, monkeypatch):
    from agent import secret_scope
    from gateway.config import GatewayConfig

    a, b = tmp_path / "default", tmp_path / "worker"
    a.mkdir()
    b.mkdir()
    default_cwd, worker_cwd = a / "workspace", b / "workspace"
    default_cwd.mkdir()
    worker_cwd.mkdir()
    (a / "config.yaml").write_text(
        f"terminal:\n  cwd: {default_cwd.as_posix()}\n", encoding="utf-8")
    (b / ".env").write_text("API_SERVER_KEY=worker-profile-secret-key-12345\n", encoding="utf-8")
    (b / "config.yaml").write_text(
        "platforms:\n  api_server:\n    message_api:\n      api_keys:\n        - worker-exec\n"
        f"terminal:\n  cwd: {worker_cwd.as_posix()}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(a))
    monkeypatch.setattr("hermes_cli.profiles.profiles_to_serve",
                        lambda multiplex: [("default", a), ("worker", b)])
    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir",
                        lambda name: a if name == "default" else b)
    adapter = APIServerAdapter(PlatformConfig(
        enabled=True, extra={"key": "admin-secret", "message_api": {
            "webui_history_enabled": True, "allow_command_execution": True,
            "api_keys": ["default-exec"],
        }}))
    adapter.gateway_runner = type("Runner", (), {"config": GatewayConfig(multiplex_profiles=True)})()
    secret_scope.set_multiplex_active(True)
    try:
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
        app = web.Application(middlewares=[adapter._make_profile_prefix_middleware()])
        for method, path, handler in adapter._http_route_table():
            app.router.add_route(method, path, handler)
            app.router.add_route(method, "/p/{profile}" + path, handler)
        async with TestClient(TestServer(app)) as client:
            with adapter._profile_scope("worker"):
                message_api_keys.set_policy(True)
                db = await adapter._ensure_session_db_async()
                db.create_session("worker-row", source="api_server")
                db.record_gateway_session_peer(
                    "worker-row", source="api_server", session_key="message_api:worker")
            adapter._run_agent = AsyncMock(return_value=({"final_response": "default"}, {}))
            default = await client.post("/message", json={"message": "hi"})
            assert default.status == 200
            assert (await client.post("/p/worker/message", json={"message": "hi"})).status == 401
            assert adapter._run_agent.await_count == 1
            worker_headers = {"Authorization": "Bearer worker-profile-secret-key-12345"}
            default_headers = {"Authorization": "Bearer admin-secret"}
            commands = []
            from gateway.session_context import get_session_env
            from hermes_constants import get_hermes_home
            from tools.terminal_scope import get_terminal_scope

            def inspect_terminal(**kwargs):
                commands.append({
                    "command": kwargs["command"],
                    "task_id": kwargs["task_id"],
                    "force": kwargs["force"],
                    "profile": get_session_env("HERMES_SESSION_PROFILE", ""),
                    "session_key": get_session_env("HERMES_SESSION_KEY", ""),
                    "home": str(get_hermes_home()),
                    "cwd": (get_terminal_scope() or {}).get("TERMINAL_CWD"),
                })
                return {"output": "ok", "exit_code": 0}

            monkeypatch.setattr("tools.terminal_tool.terminal_tool", inspect_terminal)
            wrong = await client.post("/p/worker/message", json={
                "command": "wrong", "api_key": "default-exec"})
            assert wrong.status == 401
            assert "exec_token" not in await wrong.text()
            assert commands == []
            own = await client.post("/p/worker/message", json={
                "command": "own", "api_key": "worker-exec"})
            assert own.status == 200
            assert (await own.json())["command"]["executed"]
            primary = await client.post("/message", json={
                "command": "primary", "api_key": "default-exec"})
            assert primary.status == 200
            assert len(commands) == 2
            assert commands[0]["command"] == "own"
            assert commands[0]["force"] is True
            assert commands[0]["profile"] == "worker"
            assert commands[0]["home"] == str(b)
            assert commands[0]["cwd"] == worker_cwd.as_posix()
            assert commands[0]["task_id"] == commands[0]["session_key"]
            assert commands[0]["task_id"].startswith("message_api:anon-")
            assert commands[0]["task_id"] != "message_api:remote"

            assert commands[1]["command"] == "primary"
            assert commands[1]["force"] is True
            assert commands[1]["profile"] == ""
            assert commands[1]["home"] == str(a)
            assert commands[1]["cwd"] == default_cwd.as_posix()
            assert commands[1]["task_id"] == commands[1]["session_key"]
            assert commands[1]["task_id"].startswith("message_api:anon-")
            assert commands[1]["task_id"] != "message_api:remote"
            assert commands[0]["task_id"] != commands[1]["task_id"]
            assert await asyncio.get_running_loop().run_in_executor(
                None, get_session_env, "HERMES_SESSION_KEY", "") == ""
            assert (await client.get("/p/worker/api/message/sessions/worker-row",
                                     headers=default_headers)).status == 401
            assert (await client.get("/api/message/sessions/worker-row",
                                     headers=default_headers)).status == 404
            assert (await client.get("/p/worker/api/message/sessions/worker-row",
                                     headers=worker_headers)).status == 200
    finally:
        secret_scope.set_multiplex_active(False)


@pytest.mark.asyncio
async def test_anonymous_requests_are_isolated_and_never_share_remote_session(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server({"allow_command_execution": True, "api_keys": ["test-key"]})
    db = await adapter._ensure_session_db_async()
    observed_runs = []

    async def run(**kwargs):
        observed_runs.append(kwargs)
        idx = len(observed_runs)
        session_id = kwargs.get("session_id") or f"transcript-{idx}"
        if db is not None and not db.get_session(session_id):
            db.create_session(session_id, source="api_server")
            adapter._bind_declared_conversation(session_id, kwargs["gateway_session_key"])
        return {"final_response": f"reply-{idx}", "session_id": session_id}, {}

    adapter._run_agent = run

    # 1. Two anonymous messages without session_id or sender_id
    first = await client.post("/message", json={"message": "hello from anon 1"})
    assert first.status == 200
    first_body = await first.json()
    first_session = first_body["session_id"]
    assert first_session != "remote"
    assert not first_session.startswith("remote")
    assert first_body["reply"] == "reply-1"

    second = await client.post("/message", json={"message": "hello from anon 2"})
    assert second.status == 200
    second_body = await second.json()
    second_session = second_body["session_id"]
    assert second_session != "remote"
    assert second_session != first_session

    # Verify second agent run history is empty and does not carry first session contents
    assert len(observed_runs) == 2
    assert observed_runs[0]["gateway_session_key"] != observed_runs[1]["gateway_session_key"]
    assert "remote" not in observed_runs[0]["gateway_session_key"]
    assert "remote" not in observed_runs[1]["gateway_session_key"]
    assert observed_runs[1]["conversation_history"] == []

    # 2. Deficient / empty inputs also generate distinct IDs
    third = await client.post("/message", json={"message": "empty sender", "sender_id": "", "session_id": None})
    assert third.status == 200
    third_session = (await third.json())["session_id"]
    assert third_session not in (first_session, second_session, "remote", "")

    fourth = await client.post("/message", json={"message": "whitespace sender", "sender_id": "   "})
    assert fourth.status == 200
    fourth_session = (await fourth.json())["session_id"]
    assert fourth_session not in (first_session, second_session, third_session, "remote", "")

    # 3. Explicit sender_id: "same-peer" continues same session
    peer_first = await client.post("/message", json={"message": "peer 1", "sender_id": "same-peer"})
    assert peer_first.status == 200
    peer_first_body = await peer_first.json()
    assert peer_first_body["session_id"] == "transcript-5"

    peer_second = await client.post("/message", json={"message": "peer 2", "sender_id": "same-peer"})
    assert peer_second.status == 200
    peer_second_body = await peer_second.json()
    assert peer_second_body["session_id"] == "transcript-5"
    assert observed_runs[-1]["gateway_session_key"] == observed_runs[-2]["gateway_session_key"] == "message_api:same-peer"

    # 4. Explicit session_id takes precedence over sender_id
    explicit_session = await client.post("/message", json={
        "message": "override", "session_id": "custom-session", "sender_id": "same-peer"
    })
    assert explicit_session.status == 200
    assert observed_runs[-1]["gateway_session_key"] == "message_api:custom-session"

    # 5. Pure command without identity fields must not fall back to shared remote task_id
    executed_commands = []
    adapter._execute_message_api_command = lambda cmd, task_id: (
        executed_commands.append({"command": cmd, "task_id": task_id}) or {"output": "ok", "exit_code": 0}
    )

    cmd_first = await client.post("/message", json={"command": "echo 1", "api_key": "test-key"})
    assert cmd_first.status == 200
    cmd_first_body = await cmd_first.json()
    assert cmd_first_body["session_id"] != "remote"

    cmd_second = await client.post("/message", json={"command": "echo 2", "api_key": "test-key"})
    assert cmd_second.status == 200
    cmd_second_body = await cmd_second.json()
    assert cmd_second_body["session_id"] != "remote"
    assert cmd_first_body["session_id"] != cmd_second_body["session_id"]

    assert len(executed_commands) == 2
    assert executed_commands[0]["task_id"] != "message_api:remote"
    assert executed_commands[1]["task_id"] != "message_api:remote"
    assert executed_commands[0]["task_id"] != executed_commands[1]["task_id"]


@pytest.mark.asyncio
async def test_message_direct_mode_passes_agent_mode_to_run_agent(server):
    adapter, client = await server()
    db = await adapter._ensure_session_db_async()
    db.create_session("arena-sess-1", source="api_server")
    adapter._bind_declared_conversation("arena-sess-1", "message_api:arena-sess-1")
    observed = []

    async def run(**kwargs):
        observed.append(kwargs)
        return {"final_response": "Direct move reply", "session_id": "arena-sess-1"}, {}

    adapter._run_agent = run
    resp = await client.post("/message", json={
        "message": "move",
        "session_id": "arena-sess-1",
        "agent_mode": "direct",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["reply"] == "Direct move reply"
    assert len(observed) == 1
    assert observed[0]["agent_mode"] == "direct"
    assert observed[0]["session_id"] == "arena-sess-1"


@pytest.mark.asyncio
async def test_message_invalid_agent_mode_returns_400(server):
    _, client = await server()
    resp = await client.post("/message", json={
        "message": "move",
        "agent_mode": "invalid_mode",
    })
    assert resp.status == 400
    data = await resp.json()
    assert "invalid agent_mode" in data["error"]


@pytest.mark.asyncio
async def test_message_direct_mode_skips_shared_notes(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter, client = await server({"shared_memory_notes_enabled": True})
    recorded = []
    adapter._record_message_note = lambda *args: recorded.append(args)
    adapter._run_agent = AsyncMock(return_value=({"final_response": "play reply"}, {}))

    resp = await client.post("/message", json={
        "message": "play",
        "agent_mode": "direct",
    })
    assert resp.status == 200
    assert recorded == []

    resp_default = await client.post("/message", json={
        "message": "play default",
        "agent_mode": "default",
    })
    assert resp_default.status == 200
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_run_agent_with_session_authority_passes_agent_mode(server, monkeypatch):
    """When session_authority is active, _run_agent must pass agent_mode to run_api_turn,
    and session_api_turn must record it in settings (_SETTING_KEYS) (#P1-1)."""
    from unittest.mock import MagicMock
    from gateway import session_api_turn
    adapter, _ = await server()

    mock_runner = MagicMock()
    mock_runner.session_authority = MagicMock()
    adapter.gateway_runner = mock_runner

    captured_kwargs = {}
    async def mock_run_api_turn(adap, **kwargs):
        captured_kwargs.update(kwargs)
        return ({"final_response": "ok"}, {})

    monkeypatch.setattr(session_api_turn, "run_api_turn", mock_run_api_turn)

    await adapter._run_agent(
        user_message="test",
        conversation_history=[],
        session_id="test-sess",
        agent_mode="direct"
    )

    assert "agent_mode" in session_api_turn._SETTING_KEYS, "_SETTING_KEYS must register agent_mode"
    assert captured_kwargs.get("agent_mode") == "direct", f"agent_mode was not passed to run_api_turn! captured: {captured_kwargs}"


def test_turn_runner_applies_direct_agent_mode():
    """TurnRunner must enforce direct agent_mode (max_iterations=1, enabled_toolsets=[]) from api_execution settings."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from gateway.config import Platform
    from gateway.run_turn_runner import TurnRunner
    from gateway.session_api_turn import api_execution

    mock_adapter = MagicMock()
    mock_adapter._model_routes = {}
    mock_adapter._select_agent_runtime = MagicMock(return_value=("test-model", None, None, None))
    token = api_execution.set({"adapter": mock_adapter, "settings": {"agent_mode": "direct"}})
    try:
        runner = MagicMock()
        runner.session_authority = None
        runner._resolve_session_agent_runtime = MagicMock(return_value=("test-model", {"provider": "test-provider"}))
        runner._resolve_turn_agent_config = MagicMock(return_value={"model": "test-model"})

        mock_agent = MagicMock()
        mock_agent.max_iterations = 500
        mock_agent.enabled_toolsets = ["web", "terminal"]
        mock_agent.skip_context_files = False
        mock_agent.skip_memory = False

        ctx = SimpleNamespace(
            source=SimpleNamespace(platform=Platform.API_SERVER),
            session_key="test-key",
            session_id="test-session-id",
            inbound_message_id="test-msg-id",
            user_config={},
            message="hello",
            mute_notification_reply=False,
            enabled_toolsets=["web", "terminal"],
            agent_holder=[mock_agent],
            tools_holder=[[]],
        )
        turn = TurnRunner(runner, ctx)
        turn._resolve_turn_agent = MagicMock(return_value=(mock_agent, False))
        turn._setup_stream_consumer = MagicMock(return_value=(None, None, None, False))
        turn._wire_turn_agent_callbacks = MagicMock()
        turn._load_turn_history = MagicMock(return_value=([], None, []))
        turn._prepare_turn_message = MagicMock(return_value=(None, None))
        turn._run_conversation_with_approval = MagicMock(return_value={"final_response": "done"})
        turn._finish_stream_consumer = MagicMock()
        turn._sync_session_after_run = MagicMock(return_value=(False, "test-sess", 0))
        turn._persisted_turn = MagicMock()

        turn.run_sync()

        assert mock_agent.max_iterations == 1, f"max_iterations is {mock_agent.max_iterations}"
        assert mock_agent.enabled_toolsets == [], f"enabled_toolsets is {mock_agent.enabled_toolsets}"
        assert mock_agent.skip_context_files is True
        assert mock_agent.skip_memory is True
    finally:
        api_execution.reset(token)
