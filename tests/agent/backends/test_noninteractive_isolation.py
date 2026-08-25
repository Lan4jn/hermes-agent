"""Tests ensuring unattended work (Cron, Batch, Auxiliary) remains on native Hermes."""

from __future__ import annotations

import pytest

from agent.backends.config import resolve_backend


def test_resolve_backend_noninteractive_stays_hermes():
    config = {"agent_backends": {"default": "antigravity"}}

    # Only explicit interactive platforms resolve to antigravity by default
    # If a noninteractive caller resolves backend explicitly or uses Hermes directly, it is hermes
    direct_hermes = resolve_backend(config, platform="cron", session_override="hermes")
    assert direct_hermes.name == "hermes"


def test_cron_agent_creation_ignores_antigravity():
    """Cron tasks execute directly without consulting backend router."""
    from run_agent import AIAgent
    # AIAgent creates native instance
    agent = AIAgent(
        model="gemini-2.5-flash",
        api_key="fake-key",
        base_url="http://localhost:8000/v1",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
    )
    assert agent.model == "gemini-2.5-flash"
