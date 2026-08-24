from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
import psutil

from agent.backends import AntigravityConfig, BackendTurnRequest
from agent.backends.antigravity import AntigravitySession


FAKE_AGY = Path(__file__).parents[2] / "fixtures" / "fake_agy.py"


def fake_command() -> str:
    return subprocess.list2cmdline([sys.executable, str(FAKE_AGY)])


def config(
    permission_mode="strict",
    proxy_url="",
    *,
    model="gemini-test",
    effort="medium",
) -> AntigravityConfig:
    return AntigravityConfig(
        enabled=True,
        command=fake_command(),
        model=model,
        effort=effort,
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


@pytest.fixture
def official_document_events():
    return [
        {
            "event": "init",
            "conversation_id": "doc-conversation",
            "init": {
                "cwd": "/home/user/project",
                "tools": ["ask_permission", "run_command"],
                "permission_mode": "request-review",
            },
        },
        {
            "event": "step_update",
            "step_update": {
                "conversation_id": "doc-conversation",
                "step_index": 2,
                "state": "ACTIVE",
                "step_type": "agent_response",
                "text_delta": "apple",
            },
        },
        {
            "event": "step_update",
            "step_update": {
                "conversation_id": "doc-conversation",
                "step_index": 2,
                "state": "DONE",
                "step_type": "agent_response",
                "text_delta": "\n",
                "usage": {"output_tokens": 4},
            },
        },
        {
            "event": "step_update",
            "step_update": {
                "conversation_id": "doc-conversation",
                "step_index": 3,
                "state": "DONE",
                "step_type": "tool",
                "tool_name": "run_command",
                "tool_info": {
                    "name": "run_command",
                    "parameters": {"CommandLine": "echo hello"},
                    "output": "hello\r\n",
                },
            },
        },
        {
            "event": "result",
            "result": {
                "conversation_id": "doc-conversation",
                "status": "SUCCESS",
                "response": "apple\n",
                "duration_seconds": 1.4,
                "num_turns": 1,
                "usage": {"input_tokens": 10, "output_tokens": 4},
            },
        },
    ]


def test_official_document_event_shapes_parse_directly(official_document_events):
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    session._record_init(official_document_events[0])
    for payload in official_document_events[1:]:
        session._stdout_events.put(("line", json.dumps(payload)))
    emitted = []

    result = session._read_turn(emitted.append, time.monotonic() + 1)

    assert session.conversation_id == "doc-conversation"
    assert session.effective_metadata["permission_mode"] == "request-review"
    assert [event.text for event in emitted if event.kind == "message_delta"] == [
        "apple",
        "\n",
    ]
    tool = next(event for event in emitted if event.kind == "tool")
    assert tool.tool_name == "run_command"
    assert "CommandLine" in tool.text and "hello" in tool.text
    assert result.response == "apple\n"
    assert result.usage == {"input_tokens": 10, "output_tokens": 4}


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


def test_exited_process_is_not_respawned_between_turns(monkeypatch):
    import agent.backends.antigravity as module

    real_popen = module.subprocess.Popen
    spawns = []

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        spawns.append(process.pid)
        return process

    monkeypatch.setattr(module.subprocess, "Popen", recording_popen)
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    first = session.run_turn(request("EXIT_AFTER_RESULT"), lambda _event: None)
    deadline = time.monotonic() + 2
    while session.pid is not None and time.monotonic() < deadline:
        time.sleep(0.01)

    with pytest.raises(RuntimeError, match="cannot be reused"):
        session.run_turn(request("second"), lambda _event: None)

    assert first.response == "reply:EXIT_AFTER_RESULT"
    assert len(spawns) == 1
    session.close()


def test_every_official_text_delta_is_emitted_verbatim():
    events = []
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    try:
        result = session.run_turn(request("DELTA_SEMANTICS"), events.append)
    finally:
        session.close()

    assert result.response == "aab\nnext!"
    assert [event.text for event in events if event.kind == "message_delta"] == [
        "a",
        "ab",
        "\n",
        "next",
        "!",
    ]


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


def test_child_env_allowlists_runtime_and_drops_host_secrets(monkeypatch):
    monkeypatch.setenv("PATH", os.environ["PATH"])
    monkeypatch.setenv("HOME", str(Path.home()))
    monkeypatch.setenv("OPENAI_API_KEY", "OPENAI_SECRET_MARKER")
    monkeypatch.setenv("QQBOT_TOKEN", "QQBOT_SECRET_MARKER")
    monkeypatch.setenv("CUSTOM_SECRET", "CUSTOM_SECRET_MARKER")
    monkeypatch.setenv("AGY_TEST_HOST_ONLY", "not-allowlisted")
    monkeypatch.setenv("AGY_TEST_PRINCIPAL", "host-value")
    monkeypatch.setenv("AGY_TEST_TEXT", "host-value")
    proxy = "http://proxy.example:8080/path"
    session = AntigravitySession(config(proxy_url=proxy), cwd=str(Path.cwd()))
    try:
        session.run_turn(request("request-secret"), lambda _event: None)
        env = session.effective_metadata["env"]
        present = session.effective_metadata["env_present"]
    finally:
        session.close()
    assert {env[key] for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")} == {proxy}
    assert present["PATH"] is True and env["PATH"]
    assert present["HOME"] is True and env["HOME"]
    assert present["OPENAI_API_KEY"] is False
    assert present["QQBOT_TOKEN"] is False
    assert present["CUSTOM_SECRET"] is False
    assert env["AGY_TEST_HOST_ONLY"] == ""
    assert env["AGY_TEST_PRINCIPAL"] == ""
    assert env["AGY_TEST_TEXT"] == ""


@pytest.mark.parametrize(
    ("model", "effort", "absent_flags"),
    [
        ("", "medium", {"--model"}),
        ("gemini-test", "", {"--effort"}),
        ("", "", {"--model", "--effort"}),
    ],
)
def test_empty_model_and_effort_flags_are_omitted(model, effort, absent_flags):
    session = AntigravitySession(
        config(model=model, effort=effort), cwd=str(Path.cwd())
    )
    try:
        session.run_turn(request(), lambda _event: None)
        argv = session.effective_metadata["argv"]
    finally:
        session.close()
    assert absent_flags.isdisjoint(argv)


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


@pytest.mark.parametrize(
    "prompt",
    ["STATUS:" + "x" * 8000, "STATUS_SECRET"],
)
def test_unknown_status_is_bounded_and_does_not_leak(prompt):
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    with pytest.raises(RuntimeError) as exc_info:
        session.run_turn(request(prompt), lambda _event: None)
    message = str(exc_info.value)
    assert "invalid terminal status" in message
    assert len(message) < 5000
    assert "STATUS_SECRET_MARKER" not in message


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


def test_stderr_tail_never_retains_raw_secrets():
    session = AntigravitySession(config(), cwd=str(Path.cwd()), timeout_seconds=1)
    with pytest.raises(RuntimeError):
        session.run_turn(request("SECRET_EXIT"), lambda _event: None)
    tail = "\n".join(session._stderr_tail)
    assert "PROXY_SECRET_MARKER" not in tail
    assert "OAUTH_SECRET_MARKER" not in tail
    assert "sk-" + "a" * 32 not in tail


def test_close_is_idempotent_and_reaps_process():
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    session.run_turn(request(), lambda _event: None)
    pid = session.pid
    session.close()
    session.close()
    assert session.pid is None
    assert all(not thread.is_alive() for thread in session._reader_threads)
    if os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_health_properties_distinguish_alive_closed_and_fatal():
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    assert session.alive is False
    assert session.fatal is False

    session.run_turn(request(), lambda _event: None)
    assert session.alive is True
    assert session.fatal is False
    session.close()
    assert session.alive is False
    assert session.fatal is False

    failed = AntigravitySession(config(), cwd=str(Path.cwd()))
    with pytest.raises(RuntimeError):
        failed.run_turn(request("MALFORMED"), lambda _event: None)
    assert failed.alive is False
    assert failed.fatal is True


def test_close_wins_race_before_spawn_and_no_child_survives(monkeypatch):
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    original_ensure = session._ensure_process
    entered = threading.Event()
    release = threading.Event()
    errors = []

    def blocked_ensure(deadline):
        entered.set()
        release.wait(2)
        return original_ensure(deadline)

    monkeypatch.setattr(session, "_ensure_process", blocked_ensure)
    worker = threading.Thread(
        target=lambda: _capture_run_error(session, errors), daemon=True
    )
    worker.start()
    assert entered.wait(2)
    session.close()
    release.set()
    worker.join(3)

    try:
        assert not worker.is_alive()
        assert errors and "cannot be reused" in str(errors[0])
        assert session.alive is False
    finally:
        session.interrupt()


def _capture_run_error(session, errors):
    try:
        session.run_turn(request("race"), lambda _event: None)
    except Exception as exc:
        errors.append(exc)


class _FailingProcess:
    pid = 42
    stdin = None

    def __init__(self):
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return None

    def wait(self, timeout):
        raise subprocess.TimeoutExpired("agy", timeout)

    def terminate(self):
        self.terminate_calls += 1
        raise OSError("terminate failed")

    def kill(self):
        self.kill_calls += 1
        raise OSError("kill failed api_key=KILL_SECRET_MARKER_1234567890")


def test_close_retains_live_process_and_raises_when_kill_fails(monkeypatch):
    import agent.backends.antigravity as module

    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    process = _FailingProcess()
    session._process = process
    tree_kill_calls = []
    monkeypatch.setattr(
        module,
        "kill_process_tree",
        lambda pid, **kwargs: tree_kill_calls.append((pid, kwargs)) or False,
        raising=False,
    )

    with pytest.raises(RuntimeError) as exc_info:
        session.close()

    assert session._process is process
    assert session._closed is True
    assert session.pid == process.pid
    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert len(tree_kill_calls) == 2
    assert "KILL_SECRET_MARKER" not in str(exc_info.value)


def test_close_terminates_real_parent_and_child_process_tree():
    session = AntigravitySession(config(), cwd=str(Path.cwd()))
    result = session.run_turn(request("SPAWN_CHILD"), lambda _event: None)
    parent_pid = session.pid
    child_pid = int(result.response)
    assert parent_pid and _pid_alive(parent_pid) and _pid_alive(child_pid)

    try:
        session.close()
        deadline = time.monotonic() + 3
        while (
            _pid_alive(parent_pid) or _pid_alive(child_pid)
        ) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not _pid_alive(parent_pid)
        assert not _pid_alive(child_pid)
        assert all(not thread.is_alive() for thread in session._reader_threads)
    finally:
        for pid in (child_pid, parent_pid):
            try:
                psutil.Process(pid).kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass


def _pid_alive(pid):
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


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
        seen.append(kwargs)
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
    if os.name == "nt":
        assert seen[0]["creationflags"] & 0x00000200
        assert seen[0]["creationflags"] & real_flags == real_flags
        assert "start_new_session" not in seen[0]
    else:
        assert seen[0]["start_new_session"] is True
        assert "creationflags" not in seen[0]
