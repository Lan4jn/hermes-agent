"""Setup and interactive configuration wizard for Antigravity backend."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
import urllib.request
from urllib.parse import urlsplit

from agent.backends.antigravity import _CHILD_ENV_ALLOWLIST
from agent.backends.config import AntigravityConfig, parse_antigravity_config
from hermes_cli._subprocess_compat import split_command_line, windows_hide_flags
from hermes_cli.config import (
    atomic_config_write,
    get_env_value,
    load_config,
    save_config,
    save_env_value,
)
from hermes_cli.cli_output import (
    line_input,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    prompt,
    prompt_yes_no,
)

logger = logging.getLogger(__name__)

OFFICIAL_INSTALLER_WINDOWS = "https://antigravity.google/cli/install.ps1"
OFFICIAL_INSTALLER_POSIX = "https://antigravity.google/cli/install.sh"
_MODEL_SLUG = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")


def parse_antigravity_models(stdout: str) -> list[str]:
    """Extract model slugs from `agy models` output, skipping display labels."""
    models: list[str] = []
    for raw in stdout.splitlines():
        trimmed = raw.strip()
        if not trimmed:
            continue
        first = trimmed.lstrip("-*• ").split(maxsplit=1)[0] if trimmed else ""
        if first and _MODEL_SLUG.fullmatch(first) and first not in models:
            models.append(first)
    return models


def build_setup_env(proxy_url: str = "") -> dict[str, str]:
    """Build a sanitized environment mapping containing only allowlisted variables."""
    env = {
        k: os.environ[k]
        for k in _CHILD_ENV_ALLOWLIST
        if k in os.environ
    }
    if proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[key] = proxy_url
    return env


def detect_antigravity_executable(hint: str = "") -> str | None:
    """Check standard PATH and common user install locations for ``agy``."""
    if hint:
        p = Path(hint)
        if p.is_file():
            return str(p)

    found = shutil.which("agy")
    if found:
        return found

    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    user_profile = os.environ.get("USERPROFILE", "")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "Antigravity" / "bin" / "agy.exe")
        candidates.append(Path(local_app_data) / "Google" / "Antigravity" / "agy.exe")
        candidates.append(Path(local_app_data) / "agy" / "bin" / "agy.exe")
    if user_profile:
        candidates.append(Path(user_profile) / ".antigravity" / "bin" / "agy.exe")

    try:
        home = Path.home()
        candidates.extend([
            home / ".local" / "bin" / "agy",
            home / ".antigravity" / "bin" / "agy",
            Path("/usr/local/bin/agy"),
            Path("/opt/antigravity/bin/agy"),
        ])
    except Exception:
        pass

    for cand in candidates:
        if cand.is_file():
            return str(cand)

    return None


def verify_antigravity_executable(executable_path: str, proxy_url: str = "") -> str | None:
    """Verify that ``executable_path --version`` runs cleanly and returns its version."""
    if not executable_path:
        return None
    argv = split_command_line(executable_path)
    argv.append("--version")

    env = build_setup_env(proxy_url)

    popen_kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": 10,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = windows_hide_flags()

    try:
        res = subprocess.run(argv, **popen_kwargs)
        if res.returncode == 0:
            version_str = res.stdout.strip()
            return version_str or "agy (verified)"
        return None
    except Exception:
        return None


def probe_antigravity_models(
    executable_path: str, proxy_url: str = ""
) -> tuple[list[str], str | None]:
    """Query ``agy models`` to verify official authentication and get catalog slugs."""
    argv = split_command_line(executable_path)
    argv.append("models")

    env = build_setup_env(proxy_url)

    popen_kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": 15,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = windows_hide_flags()

    try:
        res = subprocess.run(argv, **popen_kwargs)
        if res.returncode != 0:
            err = res.stderr.strip() or res.stdout.strip() or f"exit code {res.returncode}"
            return [], err

        models = parse_antigravity_models(res.stdout)
        if not models:
            return [], "no valid model slugs returned by `agy models`"
        return models, None
    except subprocess.TimeoutExpired:
        return [], "Timed out while probing models from `agy models`"
    except Exception as e:
        return [], str(e)


def is_running_elevated() -> bool:
    """Return True if running as root / administrator."""
    if os.name == "nt":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return getattr(os, "geteuid", lambda: -1)() == 0


def install_antigravity(proxy_url: str = "") -> str | None:
    """Download and run the official Google Antigravity installer."""
    if is_running_elevated():
        print_warning(
            "Installing as root/administrator is strongly discouraged.\n"
            "Please install as a regular user for correct user-level config."
        )

    installer_url = OFFICIAL_INSTALLER_WINDOWS if os.name == "nt" else OFFICIAL_INSTALLER_POSIX
    env = build_setup_env(proxy_url)

    try:
        req = urllib.request.Request(installer_url, headers={"User-Agent": "hermes-agent-setup"})
        if proxy_url:
            handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(handler)
            open_call = opener.open
        else:
            open_call = urllib.request.urlopen

        with tempfile.TemporaryDirectory() as tmpdir:
            if os.name == "nt":
                installer_file = Path(tmpdir) / "install.ps1"
                with open_call(req, timeout=30) as resp, open(installer_file, "wb") as f:
                    shutil.copyfileobj(resp, f)

                ps_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
                cmd = [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer_file)]
            else:
                installer_file = Path(tmpdir) / "install.sh"
                with open_call(req, timeout=30) as resp, open(installer_file, "wb") as f:
                    shutil.copyfileobj(resp, f)
                installer_file.chmod(0o755)
                cmd = ["/bin/sh", str(installer_file)]

            print_info(f"Executing installer...")
            res = subprocess.run(cmd, env=env, timeout=180)
            if res.returncode != 0:
                print_error(f"Installer failed with exit code {res.returncode}")
                return None
    except Exception as e:
        print_error(f"Failed to download or run installer: {e}")
        return None

    # Wait briefly for PATH or binary symlinks to settle
    time.sleep(1.0)
    return detect_antigravity_executable()


def run_antigravity_setup(interactive: bool = True, custom_config: dict | None = None) -> bool:
    """Interactive wizard to configure the Google Antigravity Headless backend."""
    print_header("Google Antigravity Backend Setup")
    print_info(
        "Antigravity connects Hermes to Google AI Pro via the official\n"
        "headless `agy` CLI protocol. Your native Hermes models and credentials\n"
        "are preserved and can be used interchangeably.\n"
    )

    # 1. Forward Proxy (Prompt early so download/probe can use it)
    proxy_input = ""
    if interactive:
        print_info("Forward Proxy (Optional):")
        print_info("If you access Google services via a local/remote proxy (e.g. Clash, v2ray), enter the URL.")
        proxy_input = prompt("Proxy URL (e.g. http://127.0.0.1:7890) [leave empty to skip]").strip()
    else:
        proxy_input = (custom_config or {}).get("proxy_url", "")

    proxy_url = ""
    proxy_has_secret = False
    if proxy_input:
        try:
            parsed_cfg = parse_antigravity_config(
                {"agent_backends": {"antigravity": {"proxy_url": proxy_input}}}
            )
            proxy_url = parsed_cfg.proxy_url
            if "@" in proxy_input:
                proxy_has_secret = True
        except ValueError as e:
            print_error(f"Invalid proxy URL: {e}")
            return False

    # 2. Detect or install executable
    exe = detect_antigravity_executable()
    if not exe:
        url = OFFICIAL_INSTALLER_WINDOWS if os.name == "nt" else OFFICIAL_INSTALLER_POSIX
        print_warning(f"`agy` executable was not found on PATH or in standard user directories.")
        print_info(f"Official installer: {url}")

        if not interactive or not prompt_yes_no("Download and run the official Google Antigravity installer?", True):
            print_info("Setup cancelled. No configuration was changed.")
            return False

        print_info("Downloading and running official installer...")
        exe = install_antigravity(proxy_url=proxy_url)
        if not exe:
            print_error("Installation did not produce a detectable `agy` executable.")
            return False

    version = verify_antigravity_executable(exe, proxy_url=proxy_url)
    if not version:
        print_error(f"Failed to execute `{exe} --version`.")
        return False
    print_success(f"Found Antigravity CLI: {version}")

    # 3. Model catalog & Login probe
    print_info("\nProbing Antigravity model catalog...")
    models, err = probe_antigravity_models(exe, proxy_url)
    if err or not models:
        print_warning(f"Could not retrieve model list: {err or 'no models returned'}")
        print_info("Launching `agy` to authenticate with Google...")
        if interactive:
            auth_cmd = split_command_line(exe)
            subprocess.run(auth_cmd, env=build_setup_env(proxy_url))
            models, err = probe_antigravity_models(exe, proxy_url)

    if not models:
        print_error(f"Failed to obtain model list from Antigravity: {err or 'no models returned'}.")
        print_info("Setup cancelled. No configuration was changed.")
        return False

    # 4. Model selection
    selected_model = models[0]
    if interactive:
        print_info("\nAvailable Antigravity Models:")
        for idx, m in enumerate(models, 1):
            print(f"  {idx}) {m}")
        pick = prompt(f"Select default model [1-{len(models)}] (default: 1)").strip()
        try:
            val = int(pick)
            if 1 <= val <= len(models):
                selected_model = models[val - 1]
        except ValueError:
            pass
    elif custom_config and "model" in custom_config:
        selected_model = custom_config["model"]

    # 5. Reasoning effort
    effort = "high"
    if interactive:
        print_info("\nDefault Reasoning Effort:")
        print("  1) high (default - maximum reasoning tokens)")
        print("  2) medium")
        print("  3) low")
        pick_e = prompt("Select reasoning effort [1-3] (default: 1)").strip()
        if pick_e == "2":
            effort = "medium"
        elif pick_e == "3":
            effort = "low"
    elif custom_config and "effort" in custom_config:
        effort = custom_config["effort"]

    # 6. Permission mode
    permission_mode = "strict"
    if interactive:
        print_info("\nExecution Permission Mode:")
        print("  1) strict   (standard approval prompts)")
        print("  2) sandbox  (--sandbox container isolation)")
        print("  3) trusted  (--dangerously-skip-permissions - caution)")
        pick_p = prompt("Select permission mode [1-3] (default: 1)").strip()
        if pick_p == "2":
            permission_mode = "sandbox"
        elif pick_p == "3":
            permission_mode = "trusted"
    elif custom_config and "permission_mode" in custom_config:
        permission_mode = custom_config["permission_mode"]

    # 7. Summary and confirmation
    if interactive:
        print()
        print_header("Configuration Summary")
        print(f"  Backend:         antigravity")
        print(f"  Executable:      {exe}")
        print(f"  Model:           {selected_model}")
        print(f"  Effort:          {effort}")
        print(f"  Permission Mode: {permission_mode}")
        if proxy_url:
            display_p = (
                f"{urlsplit(proxy_url).scheme}://***:***@{urlsplit(proxy_url).hostname}"
                if proxy_has_secret
                else f"{urlsplit(proxy_url).scheme}://{urlsplit(proxy_url).netloc}"
            )
            print(f"  Proxy:           {display_p}")
        print()
        if not prompt_yes_no("Save Antigravity configuration to config.yaml?", True):
            print_info("Configuration discarded.")
            return False

    # Persist proxy secret to .env if credentials are present
    persisted_proxy_yaml = proxy_url
    if proxy_has_secret:
        save_env_value("ANTIGRAVITY_PROXY_URL", proxy_url)
        persisted_proxy_yaml = "${ANTIGRAVITY_PROXY_URL}"

    # Write to config.yaml
    cfg = load_config()
    agent_backends = cfg.setdefault("agent_backends", {})
    agent_backends["default"] = "antigravity"

    antigravity_section = agent_backends.setdefault("antigravity", {})
    antigravity_section["enabled"] = True
    antigravity_section["command"] = exe
    antigravity_section["model"] = selected_model
    antigravity_section["effort"] = effort
    antigravity_section["permission_mode"] = permission_mode
    if persisted_proxy_yaml:
        antigravity_section["proxy_url"] = persisted_proxy_yaml

    save_config(cfg)
    print_success("Antigravity backend successfully configured and set as default backend!")
    return True


def show_antigravity_status() -> None:
    """Print current Antigravity configuration and diagnostic status."""
    cfg = load_config()
    antigravity_cfg = parse_antigravity_config(cfg)

    print_header("Google Antigravity Backend Status")
    print(f"  Enabled:         {antigravity_cfg.enabled}")
    print(f"  Command:         {antigravity_cfg.command}")
    print(f"  Model:           {antigravity_cfg.model or '(auto)'}")
    print(f"  Effort:          {antigravity_cfg.effort}")
    print(f"  Permission Mode: {antigravity_cfg.permission_mode}")

    exe = detect_antigravity_executable()
    version = verify_antigravity_executable(exe, antigravity_cfg.proxy_url) if exe else None
    if exe and version:
        print_success(f"  Executable:      {exe} ({version})")
    else:
        print_error(f"  Executable:      NOT FOUND or unusable (searched for `{antigravity_cfg.command}`)")

    if antigravity_cfg.proxy_display:
        print(f"  Proxy:           {antigravity_cfg.proxy_display}")

    if exe and version:
        print_info("\nProbing connection and model availability...")
        models, err = probe_antigravity_models(exe, antigravity_cfg.proxy_url)
        if models:
            print_success(f"  Authenticated! Found {len(models)} model(s): {', '.join(models[:3])}...")
        else:
            print_warning(f"  Authentication check failed: {err}")
            print_info("  Run `hermes setup --backend antigravity` or launch `agy` to authenticate.")


def run_backend_setup(backend_name: str = "antigravity", interactive: bool = True, custom_config: dict | None = None) -> bool:
    """Unified entry point for backend setup wizards."""
    if backend_name == "antigravity":
        return run_antigravity_setup(interactive=interactive, custom_config=custom_config)
    print_error(f"Unknown backend '{backend_name}'")
    return False


def run_backend_status(backend_name: str = "antigravity") -> None:
    """Unified entry point for backend status display."""
    if backend_name == "antigravity":
        show_antigravity_status()
    else:
        print_error(f"Unknown backend '{backend_name}'")
