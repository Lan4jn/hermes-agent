"""Tests for Antigravity gateway setup, detection, installer, and status."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.backends.setup import (
    OFFICIAL_INSTALLER_POSIX,
    OFFICIAL_INSTALLER_WINDOWS,
    detect_antigravity_executable,
    install_antigravity,
    parse_antigravity_models,
    probe_antigravity_models,
    run_antigravity_setup,
    run_backend_setup,
    run_backend_status,
    verify_antigravity_executable,
)
from hermes_cli.config import get_env_value, load_config, save_config

FAKE_AGY = str(Path(__file__).resolve().parents[1] / "fixtures" / "fake_agy.py")


@pytest.fixture
def hermes_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("ANTIGRAVITY_PROXY_URL", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("agent_backends:\n  default: hermes\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Executable detection
# ---------------------------------------------------------------------------


class TestExecutableDetection:
    def test_explicit_valid_command_hint_wins(self, tmp_path):
        fake_bin = tmp_path / "custom_agy"
        fake_bin.write_text("#!/bin/sh\necho 1", encoding="utf-8")
        fake_bin.chmod(0o755)

        detected = detect_antigravity_executable(str(fake_bin))
        assert detected == str(fake_bin)

    def test_detection_falls_back_to_path(self, monkeypatch):
        with patch("shutil.which", return_value="/usr/local/bin/agy"):
            detected = detect_antigravity_executable()
            assert detected == "/usr/local/bin/agy"

    def test_detection_checks_user_install_dir_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        agy_exe = tmp_path / "agy" / "bin" / "agy.exe"
        agy_exe.parent.mkdir(parents=True)
        agy_exe.write_text("fake binary", encoding="utf-8")

        detected = detect_antigravity_executable()
        assert detected == str(agy_exe)

    def test_detection_checks_user_install_dir_posix(self, monkeypatch, tmp_path):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("USERPROFILE", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        agy_bin = tmp_path / ".local" / "bin" / "agy"
        agy_bin.parent.mkdir(parents=True)
        agy_bin.write_text("#!/bin/sh\n", encoding="utf-8")

        detected = detect_antigravity_executable()
        assert detected == str(agy_bin)

    def test_detection_returns_none_when_not_found(self, monkeypatch, tmp_path):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("USERPROFILE", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert detect_antigravity_executable() is None


# ---------------------------------------------------------------------------
# Executable verification and model catalog probe
# ---------------------------------------------------------------------------


class TestVerificationAndProbe:
    def test_verify_executable_success(self):
        # Using python fake_agy as executable
        version = verify_antigravity_executable(f"{sys.executable} {FAKE_AGY}")
        assert version is not None

    def test_verify_executable_invalid_fails(self, tmp_path):
        nonexistent = str(tmp_path / "nonexistent_agy")
        assert verify_antigravity_executable(nonexistent) is None

    def test_probe_models_parses_catalog(self):
        # Mock subprocess to return model list
        fake_output = "gemini-3.7-flash-high\ngemini-2.5-pro\ngemini-2.5-flash\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=fake_output, stderr=""
            )
            models, err = probe_antigravity_models("agy")
            assert err is None
            assert "gemini-3.7-flash-high" in models
            assert "gemini-2.5-pro" in models

    def test_probe_models_handles_auth_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Error: authentication required. Run agy login."
            )
            models, err = probe_antigravity_models("agy")
            assert models == []
            assert err is not None

    def test_parse_models_uses_slug_not_display_label(self):
        stdout = "gemini-3.7-flash-high Gemini 3.7 Flash (High)\nclaude-sonnet-4-6 Claude Sonnet 4.6 (Thinking)\n"
        assert parse_antigravity_models(stdout) == [
            "gemini-3.7-flash-high",
            "claude-sonnet-4-6",
        ]

    def test_empty_catalog_after_login_performs_no_write(self, hermes_env, monkeypatch):
        config_path = hermes_env / "config.yaml"
        env_path = hermes_env / ".env"
        before = config_path.read_text(encoding="utf-8")
        env_before = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        monkeypatch.setattr("agent.backends.setup.detect_antigravity_executable", lambda *_: "agy")
        monkeypatch.setattr("agent.backends.setup.verify_antigravity_executable", lambda *_args, **_kw: "agy 1.0")
        monkeypatch.setattr("agent.backends.setup.probe_antigravity_models", lambda *_args, **_kw: ([], "authentication required"))
        assert run_antigravity_setup(interactive=False, custom_config={}) is False
        assert config_path.read_text(encoding="utf-8") == before
        if env_path.exists():
            assert env_path.read_text(encoding="utf-8") == env_before


# ---------------------------------------------------------------------------
# Installer
# ---------------------------------------------------------------------------


class TestInstaller:
    def test_official_installer_urls_are_antigravity_google(self):
        assert OFFICIAL_INSTALLER_WINDOWS == "https://antigravity.google/cli/install.ps1"
        assert OFFICIAL_INSTALLER_POSIX == "https://antigravity.google/cli/install.sh"

    def test_installer_downloads_and_runs_script_array(self, tmp_path, monkeypatch):
        downloaded = False
        executed_cmd = []

        def fake_urlopen(req, *args, **kwargs):
            nonlocal downloaded
            downloaded = True
            mock_resp = MagicMock()
            mock_resp.read.side_effect = [b"echo installed", b""]
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        def fake_run(cmd, *args, **kwargs):
            executed_cmd.append(cmd)
            return MagicMock(returncode=0)

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr(
            "agent.backends.setup.detect_antigravity_executable",
            lambda *a, **k: "/usr/local/bin/agy",
        )

        result = install_antigravity()
        assert downloaded is True
        assert len(executed_cmd) == 1
        assert isinstance(executed_cmd[0], list)
        assert result == "/usr/local/bin/agy"


# ---------------------------------------------------------------------------
# Setup Flow and Persistence
# ---------------------------------------------------------------------------


class TestSetupFlow:
    def test_setup_cancellation_writes_zero_config(self, hermes_env):
        from hermes_cli.config import read_raw_config

        with patch("agent.backends.setup.detect_antigravity_executable", return_value=None), \
             patch("agent.backends.setup.prompt", return_value=""), \
             patch("agent.backends.setup.prompt_yes_no", return_value=False):
            success = run_backend_setup("antigravity", interactive=True)
            assert success is False

        raw = read_raw_config()
        assert raw.get("agent_backends", {}).get("default") == "hermes"
        assert "antigravity" not in raw.get("agent_backends", {})

    def test_setup_authenticated_proxy_persists_env_secret(self, hermes_env):
        proxy_secret = "http://user:secretpass@192.168.31.130:7890"

        with patch("agent.backends.setup.detect_antigravity_executable", return_value=f"{sys.executable} {FAKE_AGY}"), \
             patch("agent.backends.setup.verify_antigravity_executable", return_value="agy 1.2.0"), \
             patch("agent.backends.setup.probe_antigravity_models", return_value=(["gemini-3.7-flash-high", "gemini-2.5-pro"], None)), \
             patch("agent.backends.setup.prompt", side_effect=[proxy_secret, "1", "1", "2"]), \
             patch("agent.backends.setup.prompt_yes_no", return_value=True):

            success = run_backend_setup("antigravity", interactive=True)
            assert success is True

        # Check .env has ANTIGRAVITY_PROXY_URL
        saved_env = get_env_value("ANTIGRAVITY_PROXY_URL")
        assert saved_env == proxy_secret

        # Check config.yaml has ${ANTIGRAVITY_PROXY_URL}
        loaded = load_config()
        assert loaded["agent_backends"]["default"] == "antigravity"
        assert loaded["agent_backends"]["antigravity"]["enabled"] is True
        assert loaded["agent_backends"]["antigravity"]["model"] == "gemini-3.7-flash-high"
        assert loaded["agent_backends"]["antigravity"]["permission_mode"] == "sandbox"

        # Check raw config text contains the placeholder, not literal secret
        raw_text = (hermes_env / "config.yaml").read_text(encoding="utf-8")
        assert "${ANTIGRAVITY_PROXY_URL}" in raw_text
        assert "secretpass" not in raw_text


# ---------------------------------------------------------------------------
# Gateway backend CLI routing
# ---------------------------------------------------------------------------


class TestGatewayBackendCLI:
    def test_gateway_backend_parser_and_dispatch(self, hermes_env):
        import argparse
        from hermes_cli.subcommands.gateway import build_gateway_parser
        from hermes_cli.gateway import gateway_command

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        build_gateway_parser(
            subparsers,
            cmd_gateway=gateway_command,
            cmd_proxy=lambda args: None,
            cmd_gateway_enroll=lambda args: None,
        )

        args = parser.parse_args(["gateway", "backend", "status", "antigravity"])
        assert args.command == "gateway"
        assert args.gateway_command == "backend"
        assert args.backend_command == "status"
        assert args.backend == "antigravity"

        with patch("agent.backends.setup.run_backend_status") as mock_status:
            gateway_command(args)
            mock_status.assert_called_once_with("antigravity")

        args = parser.parse_args(["gateway", "backend", "setup", "antigravity"])
        assert args.gateway_command == "backend"
        assert args.backend_command == "setup"
        assert args.backend == "antigravity"

        with patch("agent.backends.setup.run_backend_setup") as mock_setup:
            gateway_command(args)
            mock_setup.assert_called_once_with("antigravity")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_displays_antigravity_info(self, hermes_env, capsys):
        with patch("agent.backends.setup.detect_antigravity_executable", return_value="/usr/bin/agy"), \
             patch("agent.backends.setup.verify_antigravity_executable", return_value="agy 1.2.0"), \
             patch("agent.backends.setup.probe_antigravity_models", return_value=(["gemini-3.7-flash-high"], None)):

            run_backend_status("antigravity")

        captured = capsys.readouterr().out
        assert "Antigravity" in captured
        assert "agy 1.2.0" in captured
