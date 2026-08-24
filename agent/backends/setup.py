"""Setup, executable detection, installation, and status for Antigravity backend."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from agent.redact import redact_sensitive_text
from hermes_cli._subprocess_compat import split_command_line, windows_hide_flags
from hermes_cli.config import (
    get_env_value,
    load_config,
    save_config,
    save_env_value,
)
from hermes_cli.setup import (
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    prompt,
    prompt_choice,
    prompt_yes_no,
)

logger = logging.getLogger(__name__)

OFFICIAL_INSTALLER_WINDOWS = "https://antigravity.google/cli/install.ps1"
OFFICIAL_INSTALLER_POSIX = "https://antigravity.google/cli/install.sh"


def detect_antigravity_executable(command_hint: str = "") -> str | None:
    """Find the ``agy`` executable using explicit command, PATH, or standard per-user locations."""
    if command_hint and command_hint.strip():
        hint = command_hint.strip()
        which_hit = shutil.which(hint)
        if which_hit:
            return which_hit
        parts = split_command_line(hint)
        if parts:
            first_path = Path(parts[0])
            if first_path.is_file():
                return hint
            which_first = shutil.which(parts[0])
            if which_first:
                return hint

    # 2. PATH lookup
    which_agy = shutil.which("agy")
    if which_agy:
        return which_agy

    # 3. Official per-user paths
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            win_path = Path(local_app_data) / "agy" / "bin" / "agy.exe"
            if win_path.is_file():
                return str(win_path)
    else:
        posix_path = Path.home() / ".local" / "bin" / "agy"
        if posix_path.is_file():
            return str(posix_path)

    return None


def verify_antigravity_executable(executable_path: str, proxy_url: str = "") -> str | None:
    """Verify that ``executable_path --version`` runs cleanly and returns its version."""
    if not executable_path:
        return None
    argv = split_command_line(executable_path)
    argv.append("--version")

    env = dict(os.environ)
    if proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[key] = proxy_url

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

    env = dict(os.environ)
    if proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[key] = proxy_url

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
            raw_err = (res.stderr or res.stdout or "failed to query models").strip()
            return [], redact_sensitive_text(raw_err, force=True)

        stdout = res.stdout.strip()
        models: list[str] = []
        if stdout.startswith("[") or stdout.startswith("{"):
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str):
                            models.append(item)
                        elif isinstance(item, dict) and "id" in item:
                            models.append(item["id"])
                        elif isinstance(item, dict) and "name" in item:
                            models.append(item["name"])
                elif isinstance(parsed, dict) and "models" in parsed:
                    for item in parsed["models"]:
                        if isinstance(item, str):
                            models.append(item)
                        elif isinstance(item, dict) and "id" in item:
                            models.append(item["id"])
            except Exception:
                pass

        if not models:
            for line in stdout.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("MODEL") and not line.startswith("---"):
                    parts = line.split()
                    if parts:
                        models.append(parts[0])

        if models:
            return models, None
        return [], "no models returned by agy models"
    except Exception as e:
        return [], redact_sensitive_text(str(e), force=True)


def install_antigravity(proxy_url: str = "") -> str | None:
    """Download official Google installer script to a temp file and execute it."""
    url = OFFICIAL_INSTALLER_WINDOWS if os.name == "nt" else OFFICIAL_INSTALLER_POSIX
    suffix = ".ps1" if os.name == "nt" else ".sh"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        temp_path = Path(tmp.name)

    try:
        if proxy_url:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            )
            resp_ctx = opener.open(url, timeout=30)
        else:
            resp_ctx = urllib.request.urlopen(url, timeout=30)

        with resp_ctx as resp:
            temp_path.write_bytes(resp.read())

        if os.name == "nt":
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(temp_path)]
        else:
            temp_path.chmod(0o755)
            cmd = ["bash", str(temp_path)]

        popen_kwargs: dict[str, Any] = {"check": True}
        if os.name == "nt":
            popen_kwargs["creationflags"] = windows_hide_flags()

        subprocess.run(cmd, **popen_kwargs)
        return detect_antigravity_executable()
    except Exception as e:
        logger.error("Antigravity installer failed: %s", e)
        return None
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def _is_elevated() -> bool:
    if os.name == "nt":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return getattr(os, "geteuid", lambda: -1)() == 0


def run_antigravity_setup(interactive: bool = True, custom_config: dict | None = None) -> bool:
    """Interactive wizard to configure the Google Antigravity Headless backend."""
    print_header("Google Antigravity Backend Setup")
    print_info(
        "Antigravity connects Hermes to Google AI Pro via the official\n"
        "headless `agy` CLI protocol. Your native Hermes models and credentials\n"
        "are preserved and can be used interchangeably.\n"
    )

    # 1. Detect executable
    exe = detect_antigravity_executable()
    if not exe:
        url = OFFICIAL_INSTALLER_WINDOWS if os.name == "nt" else OFFICIAL_INSTALLER_POSIX
        print_warning(f"`agy` executable was not found on PATH or in standard user directories.")
        print_info(f"Official installer: {url}")

        if not interactive or not prompt_yes_no("Download and run the official Google Antigravity installer?", True):
            print_info("Setup cancelled. No configuration was changed.")
            return False

        print_info("Downloading and running official installer...")
        exe = install_antigravity()
        if not exe:
            print_error("Installation did not produce a detectable `agy` executable.")
            return False

    version = verify_antigravity_executable(exe)
    if not version:
        print_error(f"Failed to execute `{exe} --version`.")
        return False
    print_success(f"Found Antigravity CLI: {version}")

    # 2. Forward Proxy (optional)
    proxy_input = ""
    if interactive:
        print()
        print_info("Forward Proxy (Optional):")
        print_info("If you access Google services via a local/remote proxy (e.g. Clash, v2ray), enter the URL.")
        proxy_input = prompt("Proxy URL (e.g. http://127.0.0.1:7890) [leave empty to skip]").strip()
    else:
        proxy_input = (custom_config or {}).get("proxy_url", "")

    proxy_url = ""
    proxy_has_secret = False
    if proxy_input:
        from .config import parse_antigravity_config
        try:
            parsed_cfg = parse_antigravity_config(
                {"agent_backends": {"antigravity": {"proxy_url": proxy_input}}}
            )
            proxy_url = parsed_cfg.proxy_url
        except ValueError as e:
            # Check if it was rejected due to credentials
            parsed = urlsplit(proxy_input)
            if parsed.username or parsed.password:
                proxy_url = proxy_input
                proxy_has_secret = True
            else:
                print_error(f"Invalid proxy URL: {e}")
                return False

    # 3. Model catalog & Login probe
    print_info("\nProbing Antigravity model catalog...")
    models, err = probe_antigravity_models(exe, proxy_url)
    if err or not models:
        print_warning(f"Could not retrieve models: {err}")
        print_info(
            "Please ensure you are logged in to Antigravity by running:\n"
            "  agy login\n"
        )
        if interactive and prompt_yes_no("Did you complete `agy login` and wish to retry?", True):
            models, err = probe_antigravity_models(exe, proxy_url)

        if err or not models:
            print_error("Authentication probe failed. No configuration was changed.")
            return False

    # 4. Model Selection
    selected_model = models[0]
    if interactive and len(models) > 1:
        print()
        selected_model = prompt_choice("Select Antigravity model:", models, default=models[0])

    # 5. Permission mode & Effort
    permission_mode = "sandbox"
    effort = "high"
    if interactive:
        print()
        permission_mode = prompt_choice(
            "Select permission mode:",
            ["strict", "sandbox", "trusted"],
            default="sandbox",
        )
        if permission_mode == "trusted" and _is_elevated():
            print_warning(
                "WARNING: Running in trusted mode as root/administrator allows\n"
                "Antigravity to execute system-level commands without prompt!"
            )
        effort = prompt_choice(
            "Select reasoning effort:",
            ["low", "medium", "high"],
            default="high",
        )

    # 6. Default assignment
    set_as_default = True
    if interactive:
        print()
        set_as_default = prompt_yes_no("Set Antigravity as the default backend for all interactive chats?", True)

    # 7. Confirmation & Save
    if interactive:
        print("\nSummary of Changes:")
        print(f"  Backend:         Antigravity ({exe})")
        print(f"  Model:           {selected_model}")
        print(f"  Reasoning Effort:{effort}")
        print(f"  Permission Mode: {permission_mode}")
        if proxy_url:
            display_p = f"{urlsplit(proxy_url).scheme}://{urlsplit(proxy_url).netloc}" if not proxy_has_secret else "configured (credentials stored in .env)"
            print(f"  Proxy:           {display_p}")
        print(f"  Default Backend: {'antigravity' if set_as_default else 'hermes (native)'}")

        if not prompt_yes_no("\nSave this configuration?", True):
            print_info("Setup cancelled. No configuration was changed.")
            return False

    # Persist proxy secret to .env if credentials are present
    persisted_proxy_yaml = proxy_url
    if proxy_has_secret:
        save_env_value("ANTIGRAVITY_PROXY_URL", proxy_url)
        persisted_proxy_yaml = "${ANTIGRAVITY_PROXY_URL}"

    # Update config.yaml
    config = load_config()
    agent_backends = config.setdefault("agent_backends", {})
    if set_as_default:
        agent_backends["default"] = "antigravity"

    antigravity_section = agent_backends.setdefault("antigravity", {})
    antigravity_section["enabled"] = True
    antigravity_section["command"] = exe
    antigravity_section["model"] = selected_model
    antigravity_section["effort"] = effort
    antigravity_section["permission_mode"] = permission_mode
    if persisted_proxy_yaml:
        antigravity_section["proxy_url"] = persisted_proxy_yaml

    save_config(config, merge_existing=True)

    print_success("\nAntigravity backend successfully configured!")
    print_info("You can switch back to native Hermes anytime with `/backend hermes`.")
    return True


def run_backend_status(backend_name: str = "antigravity") -> None:
    """Print the current configuration and operational status of the backend."""
    if backend_name != "antigravity":
        print(f"Status for backend '{backend_name}' is not supported.")
        return

    config = load_config()
    from .config import parse_antigravity_config, resolve_backend
    antigravity_cfg = parse_antigravity_config(config)
    default_selection = resolve_backend(config, platform="cli")

    exe = detect_antigravity_executable(antigravity_cfg.command)
    version = verify_antigravity_executable(exe, antigravity_cfg.proxy_url) if exe else None

    print(f"Antigravity Interactive Agent Backend Status:")
    print(f"  Configured:      {'Yes' if antigravity_cfg.enabled else 'No'}")
    print(f"  Effective Default:{default_selection.name} (source: {default_selection.source})")
    print(f"  Executable:      {exe or 'NOT FOUND'}")
    print(f"  Version:         {version or 'UNAVAILABLE'}")
    print(f"  Configured Model:{antigravity_cfg.model or '(dynamic catalog)'}")
    print(f"  Reasoning Effort:{antigravity_cfg.effort}")
    print(f"  Permission Mode: {antigravity_cfg.permission_mode}")
    if antigravity_cfg.proxy_display:
        print(f"  Proxy:           {antigravity_cfg.proxy_display}")
    if antigravity_cfg.permission_mode == "trusted" and _is_elevated():
        print_warning("  Security Note:   Process is elevated / root with trusted permission mode.")

    if exe and version:
        models, err = probe_antigravity_models(exe, antigravity_cfg.proxy_url)
        if err:
            print_warning(f"  Catalog / Auth:  {err}")
        else:
            print(f"  Catalog Status:  Authenticated ({len(models)} model(s) available)")
    print()


def run_backend_setup(backend_name: str = "antigravity", interactive: bool = True, custom_config: dict | None = None) -> bool:
    """Dispatch setup for the given backend."""
    if backend_name == "antigravity":
        return run_antigravity_setup(interactive=interactive, custom_config=custom_config)
    print_error(f"Setup for backend '{backend_name}' is not supported.")
    return False

