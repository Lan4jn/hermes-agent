"""Tests for editable install metadata verification and root module discovery.

Ensures that:
1. Changes to root-level Python modules (like hermes_state_ids.py) invalidate
   the editable install cache so that setuptools/uv regenerates the static finder mapping.
2. `_verify_editable_install_metadata` detects missing root modules from outside
   the repository tree and triggers self-healing `--no-deps -e .` reinstall.
3. Newly added root modules (hermes_state_ids) and standalone helpers (gateway.cgroup_cleanup)
   can be imported from a non-source working directory without PYTHONPATH.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from hermes_cli.update_cmd_deps import (
    _editable_install_is_current,
    _UPDATE_CRITICAL_MODULES,
    _INSTALL_DEFINING_FILES,
)
from hermes_cli.main_install_repair import _verify_editable_install_metadata


class TestEditableInstallMetadataVerification:
    """Validate invalidation rules and self-healing for editable install metadata."""

    def test_critical_modules_includes_hermes_state_ids(self):
        """hermes_state_ids must be tracked as a critical module for update probes."""
        assert "hermes_state_ids" in _UPDATE_CRITICAL_MODULES

    def test_editable_install_invalidated_by_root_module_change(self):
        """A pull that touches a root-level .py file must invalidate the editable install."""
        fake_diff = "hermes_state_ids.py\n"
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=fake_diff)
            is_current = _editable_install_is_current(["git"], Path("."), "old_sha")
            assert is_current is False

    def test_editable_install_invalidated_by_defining_files(self):
        """A pull that touches pyproject.toml or setup.py must invalidate editable install."""
        fake_diff = "pyproject.toml\n"
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=fake_diff)
            is_current = _editable_install_is_current(["git"], Path("."), "old_sha")
            assert is_current is False

    def test_editable_install_remains_current_for_doc_only_changes(self):
        """A pull that touches only docs/ or subpackages without new root modules remains current."""
        fake_diff = "docs/user-guide/index.md\nwebsite/docusaurus.config.js\n"
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=fake_diff)
            is_current = _editable_install_is_current(["git"], Path("."), "old_sha")
            assert is_current is True

    def test_verify_editable_install_metadata_repairs_when_missing(self):
        """When probe discovers missing root modules, it triggers repair and secondary probe confirms success."""
        with (
            mock.patch("hermes_cli.main_install_repair._resolve_install_target_python", return_value="/venv/bin/python"),
            mock.patch("hermes_cli.main_install_repair._venv_probe") as mock_probe,
            mock.patch("hermes_cli.main_install_repair._run_repair_step", return_value=True) as mock_repair,
        ):
            mock_probe.side_effect = [
                mock.MagicMock(returncode=1, stdout="hermes_state_ids\n"),
                mock.MagicMock(returncode=0, stdout=""),
            ]
            ok = _verify_editable_install_metadata(["uv", "pip"])
            assert ok is True
            assert mock_repair.called
            repair_cmd = mock_repair.call_args[0][1]
            assert "install" in repair_cmd
            assert "--no-deps" in repair_cmd
            assert "-e" in repair_cmd

    def test_verify_editable_install_metadata_warns_when_repair_incomplete(self):
        """When secondary probe still finds missing modules after repair, returns False."""
        with (
            mock.patch("hermes_cli.main_install_repair._resolve_install_target_python", return_value="/venv/bin/python"),
            mock.patch("hermes_cli.main_install_repair._venv_probe") as mock_probe,
            mock.patch("hermes_cli.main_install_repair._run_repair_step", return_value=True) as mock_repair,
        ):
            mock_probe.side_effect = [
                mock.MagicMock(returncode=1, stdout="hermes_state_ids\n"),
                mock.MagicMock(returncode=1, stdout="hermes_state_ids\n"),
            ]
            ok = _verify_editable_install_metadata(["uv", "pip"])
            assert ok is False
            assert mock_repair.called

    def test_verify_editable_install_metadata_no_op_when_healthy(self):
        """When all root modules are importable, no repair reinstall is triggered."""
        with (
            mock.patch("hermes_cli.main_install_repair._resolve_install_target_python", return_value="/venv/bin/python"),
            mock.patch("hermes_cli.main_install_repair._venv_probe") as mock_probe,
            mock.patch("hermes_cli.main_install_repair._run_repair_step") as mock_repair,
        ):
            mock_probe.return_value = mock.MagicMock(returncode=0, stdout="")
            _verify_editable_install_metadata(["uv", "pip"])
            assert not mock_repair.called

    def test_discover_root_py_modules_discovers_state_ids_without_importing_setup(self):
        """_discover_root_py_modules must list hermes_state_ids and never import setup.py."""
        from hermes_cli.main_install_repair import _discover_root_py_modules
        from hermes_cli.main import PROJECT_ROOT

        modules = _discover_root_py_modules(PROJECT_ROOT)
        assert "hermes_state_ids" in modules
        assert "run_agent" in modules
        assert "setup" not in modules

    def test_sync_python_dependencies_invokes_editable_verifier(self):
        """Production update path must invoke editable metadata verification even when deps_current=True."""
        from hermes_cli.update_cmd_deps import _sync_python_dependencies_after_pull

        with (
            mock.patch("hermes_cli.update_cmd_deps._editable_install_is_current", return_value=True),
            mock.patch("hermes_cli.update_cmd._m") as mock_m,
            mock.patch("hermes_cli.update_cmd._pip_install_prefix", return_value=(["uv", "pip"], None)),
            mock.patch("hermes_cli.update_cmd._validate_critical_modules_import", return_value=(True, "", "")),
            mock.patch("hermes_cli.update_cmd._sweep_bytecode_after_update"),
            mock.patch("hermes_cli.update_cmd._write_lazy_refresh_incomplete_marker"),
            mock.patch("hermes_cli.update_cmd._write_update_incomplete_marker"),
        ):
            mock_main = mock.MagicMock()
            mock_main.PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
            mock_main._refresh_active_lazy_features.return_value = True
            mock_m.return_value = mock_main
            _sync_python_dependencies_after_pull(
                ["git"], "main", "old_sha",
                active_lazy_features=(), active_tool_dependencies=(),
                _windows_gateway_resume=False,
            )
            assert mock_main._verify_editable_install_metadata.called


class TestRootModulesImportableFromNonSourceCwd:
    """Regression test ensuring root modules are importable outside the source tree without PYTHONPATH."""

    def test_import_hermes_state_ids_from_tempdir_without_pythonpath(self):
        """Ensure hermes_state_ids can be imported with cwd=tempfile.gettempdir() and no PYTHONPATH."""
        clean_env = dict(os.environ)
        clean_env.pop("PYTHONPATH", None)
        clean_env.pop("PYTHONHOME", None)

        code = (
            "import hermes_state_ids\n"
            "sid = hermes_state_ids.new_session_id()\n"
            "assert isinstance(sid, str) and len(sid) > 0\n"
            "print('HERMES_STATE_IDS_OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=tempfile.gettempdir(),
            env=clean_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        assert result.returncode == 0, f"Failed importing hermes_state_ids: stderr={result.stderr}"
        assert "HERMES_STATE_IDS_OK" in result.stdout

    def test_import_gateway_cgroup_cleanup_from_tempdir_without_pythonpath(self):
        """Ensure python -m gateway.cgroup_cleanup runs with exit 0 from external cwd without PYTHONPATH."""
        clean_env = dict(os.environ)
        clean_env.pop("PYTHONPATH", None)
        clean_env.pop("PYTHONHOME", None)

        result = subprocess.run(
            [sys.executable, "-m", "gateway.cgroup_cleanup"],
            cwd=tempfile.gettempdir(),
            env=clean_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        assert result.returncode == 0, f"gateway.cgroup_cleanup failed: stderr={result.stderr}"
