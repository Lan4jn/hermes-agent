"""Tests that provider selection via `hermes model` always persists correctly.

Regression tests for the bug where _save_model_choice could save config.model
as a plain string, causing subsequent provider writes (which check
isinstance(model, dict)) to silently fail — leaving the provider unset and
falling back to auto-detection.
"""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """Isolated HERMES_HOME with a minimal string-format config."""
    home = tmp_path / "hermes"
    home.mkdir()
    config_yaml = home / "config.yaml"
    # Start with model as a plain string — the format that triggered the bug
    config_yaml.write_text("model: some-old-model\n")
    env_file = home / ".env"
    env_file.write_text("")
    monkeypatch.setenv("HERMES_HOME", str(home))
    # Clear env vars that could interfere
    monkeypatch.delenv("HERMES_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("HERMES_INFERENCE_PROVIDER", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("STEPFUN_API_KEY", raising=False)
    monkeypatch.delenv("STEPFUN_BASE_URL", raising=False)
    return home


class TestSaveModelChoiceAlwaysDict:
    def test_string_model_becomes_dict(self, config_home):
        """When config.model is a plain string, _save_model_choice must
        convert it to a dict so provider can be set afterwards."""
        from hermes_cli.auth import _save_model_choice

        _save_model_choice("kimi-k2.5")

        import yaml
        config = yaml.safe_load((config_home / "config.yaml").read_text(encoding="utf-8")) or {}
        model = config.get("model")
        assert isinstance(model, dict), (
            f"Expected model to be a dict after save, got {type(model)}: {model}"
        )
        assert model["default"] == "kimi-k2.5"


class TestProviderPersistsAfterModelSave:
    def test_update_config_for_provider_uses_atomic_yaml_write(self, config_home):
        """Provider switches should delegate config writes to atomic_yaml_write."""
        from hermes_cli.auth import _update_config_for_provider

        config_path = config_home / "config.yaml"
        original_text = config_path.read_text(encoding="utf-8")

        def _boom(path, data, **kwargs):
            assert path == config_path
            assert data["model"]["provider"] == "nous"
            assert data["model"]["base_url"] == "https://inference.example.com/v1"
            assert data["model"]["default"] == "some-old-model"
            assert kwargs["sort_keys"] is False
            raise OSError("simulated atomic write failure")

        with patch("hermes_cli.auth.atomic_yaml_write", side_effect=_boom) as mock_write:
            with pytest.raises(OSError, match="simulated atomic write failure"):
                _update_config_for_provider(
                    "nous",
                    "https://inference.example.com/v1/",
                    default_model="llama-3.3",
                )

        assert mock_write.call_count == 1
        assert config_path.read_text(encoding="utf-8") == original_text

    def test_api_key_provider_saved_when_model_was_string(self, config_home, monkeypatch):
        """_model_flow_api_key_provider must persist the provider even when
        config.model started as a plain string."""
        from hermes_cli.auth import PROVIDER_REGISTRY

        pconfig = PROVIDER_REGISTRY.get("kimi-coding")
        if not pconfig:
            pytest.skip("kimi-coding not in PROVIDER_REGISTRY")

        # Simulate: user has a Kimi API key, model was a string
        monkeypatch.setenv("KIMI_API_KEY", "sk-kimi-test-key")

        from hermes_cli.main import _model_flow_api_key_provider
        from hermes_cli.config import load_config

        # Mock the model selection prompt to return "kimi-k2.5"
        # Also mock input() for the base URL prompt and builtins.input
        with patch("hermes_cli.auth._prompt_model_selection", return_value="kimi-k2.5"), \
             patch("hermes_cli.auth.deactivate_provider"), \
             patch("builtins.input", return_value=""):
            _model_flow_api_key_provider(load_config(), "kimi-coding", "old-model")

        import yaml
        config = yaml.safe_load((config_home / "config.yaml").read_text(encoding="utf-8")) or {}
        model = config.get("model")
        assert isinstance(model, dict), f"model should be dict, got {type(model)}"
        assert model.get("provider") == "kimi-coding", (
            f"provider should be 'kimi-coding', got {model.get('provider')}"
        )
        assert model.get("default") == "kimi-k2.5"

    def test_google_gemini_cli_provider_saved_when_selected(self, config_home):
        """_model_flow_google_gemini_cli should persist provider/base_url/model together."""
        from hermes_cli.main import _model_flow_google_gemini_cli
        from hermes_cli.config import load_config

        with patch(
            "hermes_cli.auth.get_gemini_oauth_auth_status",
            return_value={"logged_in": True, "email": "user@example.com"},
        ), patch(
            "hermes_cli.auth.resolve_gemini_oauth_runtime_credentials",
            return_value={
                "provider": "google-gemini-cli",
                "api_key": "ya29.test",
                "base_url": "https://cloudcode-pa.googleapis.com",
                "project_id": "proj-123",
            },
        ), patch(
            "hermes_cli.auth._prompt_model_selection",
            return_value="gemini-3.1-pro-preview",
        ):
            _model_flow_google_gemini_cli(load_config(), "old-model")

        import yaml

        config = yaml.safe_load((config_home / "config.yaml").read_text()) or {}
        model = config.get("model")
        assert isinstance(model, dict), f"model should be dict, got {type(model)}"
        assert model.get("provider") == "google-gemini-cli"
        assert model.get("base_url") == "https://cloudcode-pa.googleapis.com"
        assert model.get("default") == "gemini-3.1-pro-preview"
        assert "api_mode" not in model

    def test_google_gemini_cli_preserves_custom_endpoint_config(self, config_home):
        from hermes_cli.config import load_config
        from hermes_cli.main import _model_flow_google_gemini_cli

        import yaml

        endpoint_config = {
            "oauth_authorize_url": "https://proxy.example.test/oauth/authorize",
            "oauth_token_url": "https://proxy.example.test/oauth/token",
            "oauth_userinfo_url": "https://proxy.example.test/oauth/userinfo",
            "code_assist_base_url": "https://proxy.example.test/private/code",
        }
        (config_home / "config.yaml").write_text(yaml.safe_dump({
            "model": "old-model",
            "providers": {"google-gemini-cli": endpoint_config},
        }))
        config = load_config()

        with patch(
            "hermes_cli.auth.get_gemini_oauth_auth_status", return_value={"logged_in": True},
        ), patch(
            "hermes_cli.auth.resolve_gemini_oauth_runtime_credentials",
            return_value={"project_id": "project-1"},
        ), patch(
            "hermes_cli.auth._prompt_model_selection", return_value="gemini-test",
        ) as prompt:
            _model_flow_google_gemini_cli(config, "old-model")

        saved = load_config()
        assert saved["providers"]["google-gemini-cli"] == endpoint_config
        assert saved["model"]["base_url"] == endpoint_config["code_assist_base_url"]
        assert prompt.call_args.kwargs["confirm_base_url"] == endpoint_config["code_assist_base_url"]







class TestGeminiUnifiedProxyOrigin:
    def test_derives_all_required_endpoints(self):
        from hermes_cli.model_setup_flows import _derive_gemini_proxy_endpoints

        assert _derive_gemini_proxy_endpoints("https://proxy.example.test/") == {
            "oauth_authorize_url": "https://proxy.example.test/o/oauth2/v2/auth",
            "oauth_token_url": "https://proxy.example.test/token",
            "oauth_userinfo_url": "https://proxy.example.test/oauth2/v1/userinfo",
            "code_assist_base_url": "https://proxy.example.test",
        }

    @pytest.mark.parametrize(
        "origin",
        [
            "http://remote.test",
            "https://user@proxy.test",
            "https://proxy.test/path",
            "https://proxy.test?x=1",
            "https://proxy.test#fragment",
            "ftp://proxy.test",
            " https://proxy.test",
        ],
    )
    def test_rejects_unsafe_or_non_origin_urls(self, origin):
        from agent.gemini_endpoints import GeminiEndpointConfigError
        from hermes_cli.model_setup_flows import _derive_gemini_proxy_endpoints

        with pytest.raises(GeminiEndpointConfigError):
            _derive_gemini_proxy_endpoints(origin)

    @pytest.mark.parametrize("origin", ["http://localhost:8080", "http://127.0.0.1"])
    def test_accepts_loopback_http(self, origin):
        from hermes_cli.model_setup_flows import _derive_gemini_proxy_endpoints

        assert _derive_gemini_proxy_endpoints(origin)["code_assist_base_url"] == origin

    def test_detects_only_exact_unified_endpoint_pattern(self):
        from hermes_cli.model_setup_flows import (
            _derive_gemini_proxy_endpoints,
            _gemini_unified_proxy_origin,
        )

        endpoints = _derive_gemini_proxy_endpoints("https://proxy.example.test")
        assert _gemini_unified_proxy_origin(endpoints) == "https://proxy.example.test"

        endpoints["oauth_token_url"] = "https://other.example.test/token"
        assert _gemini_unified_proxy_origin(endpoints) is None

    def test_incomplete_endpoint_config_is_not_unified(self):
        from hermes_cli.model_setup_flows import _gemini_unified_proxy_origin

        assert _gemini_unified_proxy_origin(
            {"code_assist_base_url": "https://proxy.example.test"}
        ) is None


class TestBaseUrlValidation:
    """Reject non-URL values in the base URL prompt (e.g. shell commands).

    Uses MiniMax instead of Z.AI because Z.AI now uses a curses-based
    endpoint picker (_select_zai_endpoint) rather than the plain text
    input() prompt. Z.AI picker behavior is covered in
    TestZaiEndpointPicker below.
    """


    def test_empty_base_url_keeps_default(self, config_home, monkeypatch):
        """Pressing Enter (empty) should not change the base URL."""
        from hermes_cli.auth import PROVIDER_REGISTRY

        pconfig = PROVIDER_REGISTRY.get("minimax")
        if not pconfig:
            pytest.skip("minimax not in PROVIDER_REGISTRY")

        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)

        from hermes_cli.main import _model_flow_api_key_provider
        from hermes_cli.config import load_config, get_env_value

        with patch("hermes_cli.auth._prompt_model_selection", return_value="MiniMax-M2"), \
             patch("hermes_cli.auth.deactivate_provider"), \
             patch("builtins.input", return_value=""):
            _model_flow_api_key_provider(load_config(), "minimax", "old-model")

        saved = get_env_value("MINIMAX_BASE_URL") or ""
        assert saved == "", "Empty input should not save a base URL"


class TestZaiEndpointPicker:
    """Z.AI setup should present a curses picker for endpoint selection."""



    def test_custom_proxy_rejects_invalid_url(self, config_home, monkeypatch, capsys):
        """Custom proxy must start with http:// or https://."""
        from hermes_cli.main import _model_flow_api_key_provider
        from hermes_cli.config import load_config

        monkeypatch.setenv("GLM_API_KEY", "test-key")
        monkeypatch.delenv("GLM_BASE_URL", raising=False)
        from hermes_cli.auth import ZAI_ENDPOINTS
        custom_idx = len(ZAI_ENDPOINTS)

        with patch("hermes_cli.main._prompt_provider_choice", return_value=custom_idx), \
             patch("hermes_cli.auth._prompt_model_selection", return_value="glm-5"), \
             patch("hermes_cli.auth.deactivate_provider"), \
             patch("builtins.input", return_value="not-a-url"):
            _model_flow_api_key_provider(load_config(), "zai", "old-model")

        # The invalid URL should not have been saved as base_url
        model = load_config()["model"]
        assert model["base_url"] != "not-a-url"
        captured = capsys.readouterr()
        assert "Invalid URL" in captured.out


    def test_current_endpoint_is_default_choice(self, config_home, monkeypatch):
        """When a known endpoint is already active, it should be the default."""
        from hermes_cli.auth import ZAI_ENDPOINTS
        from hermes_cli.model_setup_flows import _select_zai_endpoint

        coding_url = ZAI_ENDPOINTS[2][1]  # coding-global

        captured = {}

        def fake_choice(choices, *, default=0, title=""):
            captured["default"] = default
            captured["choices"] = choices
            return default

        with patch("hermes_cli.main._prompt_provider_choice", side_effect=fake_choice):
            result = _select_zai_endpoint(coding_url)

        # Default should point at index 2 (coding-global)
        assert captured["default"] == 2
        assert result == coding_url
