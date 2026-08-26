"""Deterministic stdio NDJSON stand-in for the Antigravity CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if "--version" in sys.argv:
        sys.stdout.write("agy 1.2.0 (fake)\n")
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "models":
        sys.stdout.write("gemini-3.7-flash-high\ngemini-2.5-pro\ngemini-2.5-flash\n")
        return 0
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-format", required=True)
    parser.add_argument("--output-format", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--sandbox", action="store_true")
    parser.add_argument("--dangerously-skip-permissions", action="store_true")
    parser.add_argument("--conversation", default="")
    args = parser.parse_args()

    conversation_id = args.conversation or "fake-conversation-1"
    emit(
        {
            "event": "init",
            "conversation_id": conversation_id,
            "init": {
                "cwd": os.getcwd(),
                "model": args.model,
                "effort": args.effort,
                "pid": os.getpid(),
                "env": {
                    key: os.environ.get(key, "")
                    for key in (
                        "HTTP_PROXY",
                        "HTTPS_PROXY",
                        "http_proxy",
                        "https_proxy",
                        "AGY_TEST_HOST_ONLY",
                        "AGY_TEST_PRINCIPAL",
                        "AGY_TEST_TEXT",
                        "OPENAI_API_KEY",
                        "QQBOT_TOKEN",
                        "CUSTOM_SECRET",
                        "PATH",
                        "HOME",
                    )
                },
                "env_present": {
                    key: key in os.environ
                    for key in (
                        "OPENAI_API_KEY",
                        "QQBOT_TOKEN",
                        "CUSTOM_SECRET",
                        "PATH",
                        "HOME",
                    )
                },
                "argv": sys.argv[1:],
            },
        }
    )

    child = None
    for raw in sys.stdin:
        request = json.loads(raw)
        if (
            set(request) != {"event", "message"}
            or request["event"] != "user"
            or not isinstance(request["message"], dict)
            or set(request["message"]) != {"content"}
            or not isinstance(request["message"]["content"], str)
        ):
            sys.stderr.write("invalid user event shape\n")
            return 2
        text = request["message"]["content"]
        if text == "MALFORMED":
            sys.stdout.write("{not-json}\n")
            sys.stdout.flush()
            continue
        if text == "OVERSIZED_STDOUT":
            sys.stdout.write("x" * 20000 + "\n")
            sys.stdout.flush()
            continue
        if text == "OVERSIZED_STDERR":
            sys.stderr.write("x" * 20000 + "\n")
            sys.stderr.flush()
            time.sleep(10)
            continue
        if text == "OVERSIZED_EVENTS":
            for index in range(20):
                emit({
                    "event": "step_update",
                    "step_update": {
                        "step_type": "agent_response",
                        "text_delta": f"chunk {index} ",
                        "state": "RUNNING",
                    },
                })
            emit({
                "event": "result",
                "result": {
                    "conversation_id": conversation_id,
                    "status": "SUCCESS",
                    "response": "done",
                    "usage": {},
                },
            })
            continue
        if text == "STDERR_FLOOD":
            for index in range(200):
                sys.stderr.write(f"stderr line {index}\n")
            sys.stderr.flush()
        if text == "SECRET_EXIT":
            sys.stderr.write(
                "proxy_password=PROXY_SECRET_MARKER api_key=sk-"
                + "a" * 32
                + " oauth_token=OAUTH_SECRET_MARKER_1234567890\n"
            )
            sys.stderr.flush()
            return 17
        if text == "EXIT":
            return 9
        if text in {"TIMEOUT", "INTERRUPT"}:
            time.sleep(10)
            continue
        if text == "SPAWN_CHILD":
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            emit(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": conversation_id,
                        "status": "SUCCESS",
                        "response": str(child.pid),
                        "usage": {},
                    },
                }
            )
            continue

        if text.startswith("STATUS:"):
            status = text.partition(":")[2]
            emit(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": conversation_id,
                        "status": status,
                        "response": "nope",
                    },
                }
            )
            continue
        if text == "STATUS_SECRET":
            emit(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": conversation_id,
                        "status": "api_key=STATUS_SECRET_MARKER_1234567890",
                        "response": "nope",
                    },
                }
            )
            continue

        if text == "DELTA_SEMANTICS":
            for step_index, status, delta in (
                (0, "ACTIVE", "a"),
                (0, "ACTIVE", "ab"),
                (0, "DONE", "\n"),
                (1, "ACTIVE", "next"),
                (1, "DONE", "!"),
            ):
                emit(
                    {
                        "event": "step_update",
                        "step_update": {
                            "conversation_id": conversation_id,
                            "step_index": step_index,
                            "step_type": "agent_response",
                            "state": status,
                            "text_delta": delta,
                        },
                    }
                )
            emit(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": conversation_id,
                        "status": "SUCCESS",
                        "response": "aab\nnext!",
                        "usage": {},
                    },
                }
            )
            continue

        if text == "UNKNOWN_EVENT":
            emit({"event": "future_protocol_event", "payload": "ignored"})

        if text == "TOOL":
            emit(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": conversation_id,
                        "step_index": 1,
                        "step_type": "tool",
                        "state": "DONE",
                        "tool_name": "terminal",
                        "tool_info": {
                            "name": "terminal",
                            "parameters": {
                                "command": "echo ok",
                                "api_key": "sk-" + "b" * 32,
                                "padding": "i" * 3000,
                            },
                            "output": "oauth_token=OAUTH_TOOL_SECRET_1234567890 "
                            + "o" * 3000,
                        },
                    },
                }
            )

        response = f"reply:{text}"
        emit(
            {
                "event": "step_update",
                "step_update": {
                    "conversation_id": conversation_id,
                    "step_index": 0,
                    "step_type": "agent_response",
                    "state": "ACTIVE",
                    "text_delta": response[:6],
                },
            }
        )
        emit(
            {
                "event": "step_update",
                "step_update": {
                    "conversation_id": conversation_id,
                    "step_index": 0,
                    "step_type": "agent_response",
                    "state": "ACTIVE",
                    "text_delta": response[6:],
                },
            }
        )
        emit(
            {
                "event": "step_update",
                "step_update": {
                    "conversation_id": conversation_id,
                    "step_index": 0,
                    "step_type": "agent_response",
                    "state": "DONE",
                },
            }
        )
        emit(
            {
                "event": "result",
                "result": {
                    "conversation_id": conversation_id,
                    "status": "SUCCESS",
                    "response": response,
                    "duration_seconds": 0.01,
                    "num_turns": 1,
                    "usage": {
                        "input_tokens": len(text),
                        "output_tokens": len(response),
                    },
                },
            }
        )
        if text == "EXIT_AFTER_RESULT":
            return 0
    if child is not None:
        child.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
