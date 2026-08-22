from unittest.mock import MagicMock, patch


def test_gquota_uses_chat_console_when_tui_is_live():
    from agent.google_oauth import GoogleOAuthError
    from cli import HermesCLI

    cli = HermesCLI.__new__(HermesCLI)
    cli.console = MagicMock()
    cli._app = object()

    live_console = MagicMock()

    with patch("cli.ChatConsole", return_value=live_console), \
         patch("agent.google_oauth.get_valid_access_token", side_effect=GoogleOAuthError("No Google OAuth credentials found")), \
         patch("agent.google_oauth.load_credentials", return_value=None), \
         patch("agent.google_code_assist.retrieve_user_quota"):
        cli._handle_gquota_command("/gquota")

    assert live_console.print.call_count == 2
    cli.console.print.assert_not_called()


def test_gquota_uses_configured_code_assist_base():
    from cli import HermesCLI

    cli = HermesCLI.__new__(HermesCLI)
    cli.console = MagicMock()
    cli._app = None

    with patch(
        "hermes_cli.auth.resolve_gemini_oauth_runtime_credentials",
        return_value={
            "api_key": "access-token",
            "project_id": "project-1",
            "base_url": "https://proxy.example.test/private/code",
        },
    ), patch("agent.google_code_assist.retrieve_user_quota", return_value=[]) as quota:
        cli._handle_gquota_command("/gquota")

    quota.assert_called_once_with(
        "access-token",
        project_id="project-1",
        base_url="https://proxy.example.test/private/code",
    )
