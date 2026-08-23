from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from agent.backends import AntigravityConfig, BackendTurnRequest
from agent.backends.antigravity import AntigravitySession


FAKE_AGY = Path(__file__).parents[2] / "fixtures" / "fake_agy.py"


def fake_command() -> str:
    return subprocess.list2cmdline([sys.executable, str(FAKE_AGY)])


def config(permission_mode="strict", proxy_url="") -> AntigravityConfig:
    return AntigravityConfig(
        enabled=True,
        command=fake_command(),
        model="gemini-test",
        effort="medium",
        permission_mode=permission_mode,
        proxy_url=proxy_url,
    )


def request(text="hello", *, trusted=False) -> BackendTurnRequest:
    return BackendTurnRequest(
        session_id="session-1",
        profile="default",
        platform="cli",
        principal_id="principal-secret",
        text=text,
        cwd=None,
        trusted=trusted,
    )


def test_multi_turn_reuses_process_conversation_and_emits_only_new_deltas():
    events = []
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    try:
        first = session.run_turn(request("one"), events.append)
        pid = session.pid
        second = session.run_turn(request("two"), events.append)
    finally:
        session.close()

    assert pid and second.conversation_id == first.conversation_id == "fake-conversation-1"
    assert session.pid is None
    assert [event.text for event in events if event.kind == "message_delta"] == [
        "reply:",
        "one",
        "reply:",
        "two",
    ]
    assert first.response == "reply:one"
    assert first.status == "SUCCESS"
    assert first.usage == {"input_tokens": 3, "output_tokens": 9}
    with pytest.raises(TypeError):
        first.usage["input_tokens"] = 99


def test_stdin_is_utf8_text_only_and_unknown_events_are_ignored():
    unicode_text = chr(0x4F60) + chr(0x597D)
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    try:
        unicode_result = session.run_turn(request(unicode_text), lambda _event: None)
        unknown_result = session.run_turn(request("UNKNOWN_EVENT"), lambda _event: None)
    finally:
        session.close()
    assert unicode_result.response.startswith("reply:")
    assert [ord(char) for char in unicode_result.response[-2:]] == [0x4F60, 0x597D]
    assert unknown_result.response == "reply:UNKNOWN_EVENT"


@pytest.mark.parametrize(
    ("mode", "trusted", "extra"),
    [("strict", False, []), ("sandbox", False, ["--sandbox"]), ("trusted", True, ["--dangerously-skip-permissions"])],
)
def test_permission_mode_builds_exact_argv(mode, trusted, extra):
    session = AntigravitySession(config(mode), cwd=str(Path.cwd()))
    try:
        session.run_turn(request(trusted=trusted), lambda _event: None)
        assert session.effective_metadata["argv"] == [
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--model", "gemini-test",
            "--effort", "medium",
            *extra,
        ]
    finally:
        session.close()


def test_trusted_mode_requires_request_authorization_before_spawn():
    session = AntigravitySession(config("trusted"), cwd=str(Path.cwd()))
    with pytest.raises(PermissionError, match="trusted"):
        session.run_turn(request(trusted=False), lambda _event: None)
    assert session.pid is None


def test_resume_adds_conversation_argument():
    session = AntigravitySession(config(), cwd=str(Path.cwd()), conversation_id="resume-42")
    try:
        result = session.run_turn(request(), lambda _event: None)
        assert result.conversation_id == "resume-42"
        assert session.effective_metadata["argv"][-2:] == ["--conversation", "resume-42"]
    finally:
        session.close()


def test_child_env_keeps_host_runtime_and_overrides_all_proxy_spellings(monkeypatch):
    monkeypatch.setenv("AGY_TEST_HOST_ONLY", "kept")
    monkeypatch.setenv("AGY_TEST_PRINCIPAL", "host-value")
    monkeypatch.setenv("AGY_TEST_TEXT", "host-value")
    proxy = "http://proxy.example:8080/path"
    session = AntigravitySession(config(proxy_url=proxy), cwd=str(Path.cwd()))
    try:
        session.run_turn(request("request-secret"), lambda _event: None)
        env = session.effective_metadata["env"]
    finally:
        session.close()
    assert env["AGY_TEST_HOST_ONLY"] == "kept"
    assert {env[key] for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")} == {proxy}
    assert env["AGY_TEST_PRINCIPAL"] == "host-value"
    assert env["AGY_TEST_TEXT"] == "host-value"


def test_tool_event_is_bounded_factual_and_redacted():
    events = []
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    try:
        session.run_turn(request("TOOL"), events.append)
    finally:
        session.close()
    tool = next(event for event in events if event.kind == "tool")
    assert tool.tool_name == "terminal" and tool.status == "DONE"
    assert "command" in tool.text and len(tool.text) <= 2200
    assert "sk-" + "b" * 32 not in tool.text
    assert "OAUTH_TOOL_SECRET_1234567890" not in tool.text


@pytest.mark.parametrize("prompt", ["MALFORMED", "OVERSIZED_STDOUT", "OVERSIZED_STDERR"])
def test_invalid_or_oversized_protocol_terminates_session(prompt):
    session = AntigravitySession(config(), cwd=str(Path.cwd()), timeout_seconds=1)
    with pytest.raises(RuntimeError):
        session.run_turn(request(prompt), lambda _event: None)
    assert session.pid is None


def test_stderr_flood_does_not_deadlock():
    session = AntigravitySession(config(), cwd=str(Path.cwd()), timeout_seconds=2)
    try:
        result = session.run_turn(request("STDERR_FLOOD"), lambda _event: None)
    finally:
        session.close()
    assert result.response == "reply:STDERR_FLOOD"


@pytest.mark.parametrize("status", ["ERROR", "CANCELED", "INTERRUPTED", "INVALID", "WAITING", "RUNNING"])
def test_non_success_result_status_fails_and_closes(status):
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    with pytest.raises(RuntimeError, match=status):
        session.run_turn(request(f"STATUS:{status}"), lambda _event: None)
    assert session.pid is None


@pytest.mark.parametrize("prompt", ["EXIT", "SECRET_EXIT", "TIMEOUT"])
def test_exit_and_timeout_errors_have_bounded_redacted_stderr(prompt):
    session = AntigravitySession(config(), cwd=str(Path.cwd()), timeout_seconds=0.3)
    with pytest.raises(RuntimeError) as exc_info:
        session.run_turn(request(prompt), lambda _event: None)
    message = str(exc_info.value)
    assert len(message) < 5000
    assert "PROXY_SECRET_MARKER" not in message
    assert "OAUTH_SECRET_MARKER" not in message
    assert "sk-" + "a" * 32 not in message
    assert session.pid is None


def test_close_is_idempotent_and_reaps_process():
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    session.run_turn(request(), lambda _event: None)
    pid = session.pid
    session.close()
    session.close()
    assert session.pid is None
    if os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_interrupt_terminates_active_process_without_orphan():
    session = AntigravitySession(config(), cwd=str(Path.cwd()), timeout_seconds=5)
    errors = []
    worker = threading.Thread(
        target=lambda: _capture_error(session, errors), daemon=True
    )
    worker.start()
    deadline = time.monotonic() + 2
    while session.pid is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert session.interrupt() is True
    worker.join(2)
    assert not worker.is_alive() and errors and session.pid is None
    assert session.interrupt() is False
    with pytest.raises(RuntimeError, match="cannot be reused"):
        session.run_turn(request("after-interrupt"), lambda _event: None)
    assert session.pid is None


def _capture_error(session, errors):
    try:
        session.run_turn(request("INTERRUPT"), lambda _event: None)
    except Exception as exc:
        errors.append(exc)


def test_turns_are_serialized_on_one_session():
    session = AntigravitySession(config(), cwd=str(Path.cwd()), timeout_seconds=2)
    results = []
    threads = [
        threading.Thread(target=lambda text=text: results.append(session.run_turn(request(text), lambda _event: None)))
        for text in ("first", "second")
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
    finally:
        session.close()
    assert sorted(result.response for result in results) == ["reply:first", "reply:second"]


def test_windows_hide_flags_passed_at_spawn(monkeypatch):
    import agent.backends.antigravity as module

    real_popen = module.subprocess.Popen
    real_flags = module.windows_hide_flags()
    seen = []

    def recording_popen(*args, **kwargs):
        seen.append(kwargs.get("creationflags"))
        return real_popen(*args, **kwargs)

    calls = []

    def recording_flags():
        calls.append(True)
        return real_flags

    monkeypatch.setattr(module, "windows_hide_flags", recording_flags)
    monkeypatch.setattr(module.subprocess, "Popen", recording_popen)
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    try:
        session.run_turn(request(), lambda _event: None)
    finally:
        session.close()
    assert calls == [True]
    assert seen == [real_flags]
