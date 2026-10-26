"""Windows gateway imports must not shadow a PM-selected Python with the legacy venv."""

import sys

import pytest


@pytest.mark.platforms("windows")
def test_gateway_keeps_selected_pm_site_ahead_of_legacy_venv(tmp_path, monkeypatch):
    from gateway import run
    from pm import environments

    root = tmp_path / "checkout"
    gateway_dir = root / "gateway"
    gateway_dir.mkdir(parents=True)
    legacy_site = root / "venv" / "Lib" / "site-packages"
    legacy_site.mkdir(parents=True)
    (root / "venv" / "pyvenv.cfg").write_text(f"version_info = {sys.version_info.major}.{sys.version_info.minor}.9\n", encoding="utf-8")
    selected_venv = tmp_path / "pm" / "venv"
    selected_site = selected_venv / "Lib" / "site-packages"
    selected_site.mkdir(parents=True)

    monkeypatch.setattr(run, "__file__", str(gateway_dir / "run.py"))
    monkeypatch.setattr(environments, "committed_venv", lambda project_root: selected_venv)
    monkeypatch.setattr(sys, "path", [str(root), str(selected_site), "stdlib"])
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    run._ensure_windows_gateway_venv_imports()

    assert str(selected_site) in sys.path
    assert str(legacy_site) not in sys.path


@pytest.mark.platforms("windows")
def test_gateway_uses_legacy_venv_only_when_no_pm_environment_exists(tmp_path, monkeypatch):
    from gateway import run
    from pm import environments

    root = tmp_path / "checkout"
    gateway_dir = root / "gateway"
    gateway_dir.mkdir(parents=True)
    legacy_site = root / "venv" / "Lib" / "site-packages"
    legacy_site.mkdir(parents=True)
    (root / "venv" / "pyvenv.cfg").write_text(
        f"version_info = {sys.version_info.major}.{sys.version_info.minor}.9\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(run, "__file__", str(gateway_dir / "run.py"))
    monkeypatch.setattr(environments, "committed_venv", lambda project_root: None)
    monkeypatch.setattr(sys, "path", [str(root), "stdlib"])
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    run._ensure_windows_gateway_venv_imports()

    assert str(legacy_site) in sys.path
