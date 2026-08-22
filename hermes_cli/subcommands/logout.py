"""``hermes logout`` subcommand parser.

Extracted verbatim from ``hermes_cli/main.py:main()`` (god-file Phase 2).
Handler injected to avoid importing ``main``.
"""

from __future__ import annotations

from typing import Callable


_PROVIDER_ALIASES = {
    "gemini-cli": "google-gemini-cli",
    "gemini-oauth": "google-gemini-cli",
}


def build_logout_parser(subparsers, *, cmd_logout: Callable) -> None:
    """Attach the ``logout`` subcommand to ``subparsers``."""
    # =========================================================================
    # logout command
    # =========================================================================
    logout_parser = subparsers.add_parser(
        "logout",
        help="Clear authentication for an inference provider",
        description="Remove stored credentials and reset provider config",
    )
    logout_parser.add_argument(
        "--provider",
        choices=[
            "nous",
            "openai-codex",
            "xai-oauth",
            "spotify",
            "google-gemini-cli",
            "gemini-cli",
            "gemini-oauth",
        ],
        default=None,
        help="Provider to log out from (default: active provider)",
    )

    def dispatch(args):
        provider = getattr(args, "provider", None)
        if provider in _PROVIDER_ALIASES:
            args.provider = _PROVIDER_ALIASES[provider]
        return cmd_logout(args)

    logout_parser.set_defaults(func=dispatch)
