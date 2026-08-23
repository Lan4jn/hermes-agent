"""Deterministic stdio NDJSON stand-in for the Antigravity CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
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
                )
            },
            "argv": sys.argv[1:],
        }
    )

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

        if text.startswith("STATUS:"):
            status = text.partition(":")[2]
            emit({"event": "result", "status": status, "response": "nope"})
            continue

        if text == "UNKNOWN_EVENT":
            emit({"event": "future_protocol_event", "payload": "ignored"})

        if text == "TOOL":
            emit(
                {
                    "event": "step_update",
                    "step": {
                        "type": "tool",
                        "status": "DONE",
                        "name": "terminal",
                        "input": {
                            "command": "echo ok",
                            "api_key": "sk-" + "b" * 32,
                            "padding": "i" * 3000,
                        },
                        "output": "oauth_token=OAUTH_TOOL_SECRET_1234567890 "
                        + "o" * 3000,
                    },
                }
            )

        response = f"reply:{text}"
        emit(
            {
                "event": "step_update",
                "step": {
                    "type": "agent_response",
                    "status": "ACTIVE",
                    "message": response[:6],
                },
            }
        )
        emit(
            {
                "event": "step_update",
                "step": {
                    "type": "agent_response",
                    "status": "DONE",
                    "message": response,
                },
            }
        )
        emit(
            {
                "event": "result",
                "status": "SUCCESS",
                "response": response,
                "usage": {"input_tokens": len(text), "output_tokens": len(response)},
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
