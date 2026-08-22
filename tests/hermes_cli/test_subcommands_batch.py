"""Smoke tests for the batch-extracted subcommand parser builders.

Each ``build_<group>_parser`` should attach its subcommand to a subparsers
group and wire ``func`` to the injected handler. These are intentionally
light — the byte-identical ``--help`` verification done at extraction time is
the real behavioral guarantee; this just guards against a module failing to
import or a builder raising.
"""

from __future__ import annotations

import argparse
from unittest.mock import Mock

import pytest

from hermes_cli.subcommands.auth import build_auth_parser
from hermes_cli.subcommands.backup import build_backup_parser
from hermes_cli.subcommands.config import build_config_parser
from hermes_cli.subcommands.dashboard import build_dashboard_parser
from hermes_cli.subcommands.debug import build_debug_parser
from hermes_cli.subcommands.doctor import build_doctor_parser
from hermes_cli.subcommands.dump import build_dump_parser
from hermes_cli.subcommands.gui import build_gui_parser
from hermes_cli.subcommands.hooks import build_hooks_parser
from hermes_cli.subcommands.import_cmd import build_import_cmd_parser
from hermes_cli.subcommands.login import build_login_parser
from hermes_cli.subcommands.logout import build_logout_parser
from hermes_cli.subcommands.logs import build_logs_parser
from hermes_cli.subcommands.model import build_model_parser

from hermes_cli.subcommands.prompt_size import build_prompt_size_parser
from hermes_cli.subcommands.security import build_security_parser
from hermes_cli.subcommands.setup import build_setup_parser
from hermes_cli.subcommands.slack import build_slack_parser
from hermes_cli.subcommands.status import build_status_parser
from hermes_cli.subcommands.uninstall import build_uninstall_parser
from hermes_cli.subcommands.update import build_update_parser
from hermes_cli.subcommands.webhook import build_webhook_parser
from hermes_cli.subcommands.whatsapp import build_whatsapp_parser


def _h(name):
    def handler(args):  # pragma: no cover - identity only
        return name
    handler.__name__ = f"cmd_{name}"
    return handler


def _logout_parser(handler):
    parser = argparse.ArgumentParser(prog="hermes")
    sub = parser.add_subparsers(dest="command")
    build_logout_parser(sub, cmd_logout=handler)
    return parser


@pytest.mark.parametrize(
    "provider", ["google-gemini-cli", "gemini-cli", "gemini-oauth"],
)
def test_logout_parser_clears_google_for_canonical_and_aliases(
    provider, tmp_path, monkeypatch,
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    from agent.google_oauth import GoogleCredentials, _credentials_path, save_credentials
    from hermes_cli.auth import logout_command

    save_credentials(GoogleCredentials(
        access_token="token", refresh_token="refresh", expires_ms=9999999999000,
    ))
    handler = Mock(side_effect=logout_command)
    args = _logout_parser(handler).parse_args(["logout", "--provider", provider])

    args.func(args)

    assert handler.call_args.args[0].provider == "google-gemini-cli"
    assert not _credentials_path().exists()


@pytest.mark.parametrize("provider", ["nous", "openai-codex", "xai-oauth", "spotify"])
def test_logout_parser_preserves_existing_providers(provider):
    handler = Mock()
    args = _logout_parser(handler).parse_args(["logout", "--provider", provider])

    args.func(args)

    assert handler.call_args.args[0].provider == provider


def test_logout_parser_rejects_unknown_provider_friendly(capsys):
    handler = Mock()

    with pytest.raises(SystemExit) as exc_info:
        _logout_parser(handler).parse_args(["logout", "--provider", "unknown-provider"])

    assert exc_info.value.code == 2
    error = capsys.readouterr().err
    assert "invalid choice" in error
    assert "unknown-provider" in error
    handler.assert_not_called()


def test_auth_logout_parser_clears_google_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    from agent.google_oauth import GoogleCredentials, _credentials_path, save_credentials
    from hermes_cli.auth_commands import auth_command

    save_credentials(GoogleCredentials(
        access_token="token", refresh_token="refresh", expires_ms=9999999999000,
    ))
    handler = Mock(side_effect=auth_command)
    parser = argparse.ArgumentParser(prog="hermes")
    sub = parser.add_subparsers(dest="command")
    build_auth_parser(sub, cmd_auth=handler)
    args = parser.parse_args(["auth", "logout", "google-gemini-cli"])

    args.func(args)

    assert handler.call_args.args[0].provider == "google-gemini-cli"
    assert not _credentials_path().exists()


# (subcommand_name, builder, handler_kwargs, sample_argv)
SINGLE_HANDLER_CASES = [
    ("model", build_model_parser, "cmd_model", ["model"]),
    ("setup", build_setup_parser, "cmd_setup", ["setup"]),

    ("whatsapp", build_whatsapp_parser, "cmd_whatsapp", ["whatsapp"]),
    ("slack", build_slack_parser, "cmd_slack", ["slack"]),
    ("login", build_login_parser, "cmd_login", ["login"]),
    ("logout", build_logout_parser, "cmd_logout", ["logout"]),
    ("auth", build_auth_parser, "cmd_auth", ["auth"]),
    ("status", build_status_parser, "cmd_status", ["status"]),
    ("webhook", build_webhook_parser, "cmd_webhook", ["webhook"]),
    ("hooks", build_hooks_parser, "cmd_hooks", ["hooks"]),
    ("doctor", build_doctor_parser, "cmd_doctor", ["doctor"]),
    ("security", build_security_parser, "cmd_security", ["security"]),
    ("dump", build_dump_parser, "cmd_dump", ["dump"]),
    ("debug", build_debug_parser, "cmd_debug", ["debug"]),
    ("backup", build_backup_parser, "cmd_backup", ["backup"]),
    ("import", build_import_cmd_parser, "cmd_import", ["import", "/tmp/x.zip"]),
    ("config", build_config_parser, "cmd_config", ["config"]),
    ("update", build_update_parser, "cmd_update", ["update"]),
    ("uninstall", build_uninstall_parser, "cmd_uninstall", ["uninstall"]),
    ("gui", build_gui_parser, "cmd_gui", ["gui"]),
    ("logs", build_logs_parser, "cmd_logs", ["logs"]),
    ("prompt-size", build_prompt_size_parser, "cmd_prompt_size", ["prompt-size"]),
]




def test_config_get_unset_subcommands_parse():
    """`hermes config get/unset` parse key args (and --json for get)."""
    parser = argparse.ArgumentParser(prog="hermes")
    sub = parser.add_subparsers(dest="command")
    handler = _h("config")
    build_config_parser(sub, cmd_config=handler)

    ns = parser.parse_args(["config", "get", "terminal.backend", "--json"])
    assert ns.func is handler
    assert ns.config_command == "get"
    assert ns.key == "terminal.backend"
    assert ns.json is True

    ns = parser.parse_args(["config", "unset", "terminal.backend"])
    assert ns.func is handler
    assert ns.config_command == "unset"
    assert ns.key == "terminal.backend"




# ── deprecated `hermes login` fails gracefully, not with argparse error ────
#
# `hermes login` is a removed command; its handler (`login_command` in
# `hermes_cli/auth.py`) prints a deprecation notice pointing at `hermes auth` /
# `hermes model` and exits 0.  Two behavior contracts guard the UX:
#   1. ANY `--provider <value>` (including ones the user actually wants, like
#      `anthropic`) must parse and reach the handler — never crash in argparse
#      with `invalid choice` before the friendly redirect is printed (#24756).
#   2. The subcommand must not advertise itself in the parser help row.


def _login_parser():
    parser = argparse.ArgumentParser(prog="hermes")
    sub = parser.add_subparsers(dest="command")
    build_login_parser(sub, cmd_login=_h("login"))
    return parser




def test_login_subparser_help_is_suppressed():
    """The deprecated `login` row must not appear in `hermes --help`.

    Must hold without leaking argparse's literal `==SUPPRESS==` placeholder,
    which `help=argparse.SUPPRESS` emits for a top-level subparser on 3.12+.
    The fix omits the `help=` kwarg entirely instead.
    """
    parser = argparse.ArgumentParser(prog="hermes")
    sub = parser.add_subparsers(dest="command")
    build_login_parser(sub, cmd_login=_h("login"))
    help_text = parser.format_help()
    # The misleading old help string must be gone from the top-level usage.
    assert "Authenticate with an inference provider" not in help_text
    # And no leaked SUPPRESS placeholder row.
    assert "==SUPPRESS==" not in help_text
