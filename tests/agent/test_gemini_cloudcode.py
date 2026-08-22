"""Tests for the google-gemini-cli OAuth + Code Assist inference provider.

Covers:
- agent/google_oauth.py — PKCE, credential I/O with packed refresh format,
  token refresh dedup, invalid_grant handling, headless paste fallback
- agent/google_code_assist.py — project discovery, VPC-SC fallback, onboarding
  with LRO polling, quota retrieval
- agent/gemini_cloudcode_adapter.py — OpenAI↔Gemini translation, request
  envelope wrapping, response unwrapping, tool calls bidirectional, streaming
- Provider registration — registry entry, aliases, runtime dispatch, auth
  status, _OAUTH_CAPABLE_PROVIDERS regression guard
"""
from __future__ import annotations

import base64
import concurrent.futures
import contextlib
import hashlib
import http.server
import io
import json
import logging
import stat
import threading
import time
import traceback
import urllib.error
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


@contextlib.contextmanager
def _code_assist_server(response_body: bytes):
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            requests.append({
                "path": self.path,
                "body": self.rfile.read(length),
                "authorization": self.headers.get("Authorization"),
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests, thread
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _custom_oauth_endpoints():
    from agent.gemini_endpoints import GeminiOAuthEndpoints

    return GeminiOAuthEndpoints(
        oauth_authorize_url="https://login.example.test/custom/authorize",
        oauth_token_url="https://login.example.test/custom/token",
        oauth_userinfo_url="https://profile.example.test/custom/userinfo",
        code_assist_base_url="https://code.example.test",
        custom_code_assist=True,
    )


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    for key in (
        "HERMES_GEMINI_CLIENT_ID",
        "HERMES_GEMINI_CLIENT_SECRET",
        "HERMES_GEMINI_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT_ID",
        "SSH_CONNECTION",
        "SSH_CLIENT",
        "SSH_TTY",
        "HERMES_HEADLESS",
    ):
        monkeypatch.delenv(key, raising=False)
    return home


# =============================================================================
# google_oauth.py — PKCE + packed refresh format
# =============================================================================

class TestPkce:
    def test_verifier_and_challenge_s256_roundtrip(self):
        from agent.google_oauth import _generate_pkce_pair

        verifier, challenge = _generate_pkce_pair()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        assert challenge == expected
        assert 43 <= len(verifier) <= 128


class TestRefreshParts:
    def test_parse_bare_token(self):
        from agent.google_oauth import RefreshParts

        p = RefreshParts.parse("abc-token")
        assert p.refresh_token == "abc-token"
        assert p.project_id == ""
        assert p.managed_project_id == ""

    def test_parse_packed(self):
        from agent.google_oauth import RefreshParts

        p = RefreshParts.parse("rt|proj-123|mgr-456")
        assert p.refresh_token == "rt"
        assert p.project_id == "proj-123"
        assert p.managed_project_id == "mgr-456"

    def test_format_bare_token(self):
        from agent.google_oauth import RefreshParts

        assert RefreshParts(refresh_token="rt").format() == "rt"

    def test_format_with_project(self):
        from agent.google_oauth import RefreshParts

        packed = RefreshParts(
            refresh_token="rt", project_id="p1", managed_project_id="m1",
        ).format()
        assert packed == "rt|p1|m1"
        # Roundtrip
        parsed = RefreshParts.parse(packed)
        assert parsed.refresh_token == "rt"
        assert parsed.project_id == "p1"
        assert parsed.managed_project_id == "m1"

    def test_format_empty_refresh_token_returns_empty(self):
        from agent.google_oauth import RefreshParts

        assert RefreshParts(refresh_token="").format() == ""


class TestClientCredResolution:
    def test_env_override(self, monkeypatch):
        from agent.google_oauth import _get_client_id

        monkeypatch.setenv("HERMES_GEMINI_CLIENT_ID", "custom-id.apps.googleusercontent.com")
        assert _get_client_id() == "custom-id.apps.googleusercontent.com"

    def test_shipped_default_used_when_no_env(self):
        """Out of the box, the public gemini-cli desktop client is used."""
        from agent.google_oauth import _get_client_id, _DEFAULT_CLIENT_ID

        # Confirmed PUBLIC: baked into Google's open-source gemini-cli
        assert _DEFAULT_CLIENT_ID.endswith(".apps.googleusercontent.com")
        assert _DEFAULT_CLIENT_ID.startswith("681255809395-")
        assert _get_client_id() == _DEFAULT_CLIENT_ID

    def test_shipped_default_secret_present(self):
        from agent.google_oauth import _DEFAULT_CLIENT_SECRET, _get_client_secret

        assert _DEFAULT_CLIENT_SECRET.startswith("GOCSPX-")
        assert len(_DEFAULT_CLIENT_SECRET) >= 20
        assert _get_client_secret() == _DEFAULT_CLIENT_SECRET

    def test_falls_back_to_scrape_when_defaults_wiped(self, tmp_path, monkeypatch):
        """Forks that wipe the shipped defaults should still work with gemini-cli."""
        from agent import google_oauth

        monkeypatch.setattr(google_oauth, "_DEFAULT_CLIENT_ID", "")
        monkeypatch.setattr(google_oauth, "_DEFAULT_CLIENT_SECRET", "")

        fake_bin = tmp_path / "bin" / "gemini"
        fake_bin.parent.mkdir(parents=True)
        fake_bin.write_text("#!/bin/sh\n")
        oauth_dir = tmp_path / "node_modules" / "@google" / "gemini-cli-core" / "dist" / "src" / "code_assist"
        oauth_dir.mkdir(parents=True)
        (oauth_dir / "oauth2.js").write_text(
            'const OAUTH_CLIENT_ID = "99999-fakescrapedxyz.apps.googleusercontent.com";\n'
            'const OAUTH_CLIENT_SECRET = "GOCSPX-scraped-test-value-placeholder";\n'
        )

        monkeypatch.setattr("shutil.which", lambda _: str(fake_bin))
        google_oauth._scraped_creds_cache.clear()

        assert google_oauth._get_client_id().startswith("99999-")

    def test_missing_everything_raises_with_install_hint(self, monkeypatch):
        """When env + defaults + scrape all fail, raise with install instructions."""
        from agent import google_oauth

        monkeypatch.setattr(google_oauth, "_DEFAULT_CLIENT_ID", "")
        monkeypatch.setattr(google_oauth, "_DEFAULT_CLIENT_SECRET", "")
        google_oauth._scraped_creds_cache.clear()
        monkeypatch.setattr("shutil.which", lambda _: None)

        with pytest.raises(google_oauth.GoogleOAuthError) as exc_info:
            google_oauth._require_client_id()
        assert exc_info.value.code == "google_oauth_client_id_missing"

    def test_locate_gemini_cli_oauth_js_when_absent(self, monkeypatch):
        from agent import google_oauth

        monkeypatch.setattr("shutil.which", lambda _: None)
        assert google_oauth._locate_gemini_cli_oauth_js() is None

    def test_scrape_client_credentials_parses_id_and_secret(self, tmp_path, monkeypatch):
        from agent import google_oauth

        # Create a fake gemini binary and oauth2.js
        fake_gemini_bin = tmp_path / "bin" / "gemini"
        fake_gemini_bin.parent.mkdir(parents=True)
        fake_gemini_bin.write_text("#!/bin/sh\necho gemini\n")

        oauth_js_dir = tmp_path / "node_modules" / "@google" / "gemini-cli-core" / "dist" / "src" / "code_assist"
        oauth_js_dir.mkdir(parents=True)
        oauth_js = oauth_js_dir / "oauth2.js"
        # Synthesize a harmless test fingerprint (valid shape, obvious test values)
        oauth_js.write_text(
            'const OAUTH_CLIENT_ID = "12345678-testfakenotrealxyz.apps.googleusercontent.com";\n'
            'const OAUTH_CLIENT_SECRET = "GOCSPX-aaaaaaaaaaaaaaaaaaaaaaaa";\n'
        )

        monkeypatch.setattr("shutil.which", lambda _: str(fake_gemini_bin))
        google_oauth._scraped_creds_cache.clear()

        cid, cs = google_oauth._scrape_client_credentials()
        assert cid == "12345678-testfakenotrealxyz.apps.googleusercontent.com"
        assert cs.startswith("GOCSPX-")


class TestCredentialIo:
    def _make(self):
        from agent.google_oauth import GoogleCredentials

        return GoogleCredentials(
            access_token="at-1",
            refresh_token="rt-1",
            expires_ms=int((time.time() + 3600) * 1000),
            email="user@example.com",
            project_id="proj-abc",
        )

    def test_save_and_load_packed_refresh(self):
        from agent.google_oauth import load_credentials, save_credentials

        creds = self._make()
        save_credentials(creds)
        loaded = load_credentials()
        assert loaded is not None
        assert loaded.refresh_token == "rt-1"
        assert loaded.project_id == "proj-abc"

    def test_save_uses_0600_permissions(self):
        import sys
        if sys.platform == "win32":
            pytest.skip("POSIX permissions not supported on Windows")
        from agent.google_oauth import _credentials_path, save_credentials

        save_credentials(self._make())
        mode = stat.S_IMODE(_credentials_path().stat().st_mode)
        assert mode == 0o600

    def test_disk_format_is_packed(self):
        from agent.google_oauth import _credentials_path, save_credentials

        save_credentials(self._make())
        data = json.loads(_credentials_path().read_text())
        # The refresh field on disk is the packed string, not a dict
        assert data["refresh"] == "rt-1|proj-abc|"

    def test_update_project_ids(self):
        from agent.google_oauth import (
            load_credentials, save_credentials, update_project_ids,
        )
        from agent.google_oauth import GoogleCredentials

        save_credentials(GoogleCredentials(
            access_token="at", refresh_token="rt",
            expires_ms=int((time.time() + 3600) * 1000),
        ))
        update_project_ids(project_id="new-proj", managed_project_id="mgr-xyz")

        loaded = load_credentials()
        assert loaded.project_id == "new-proj"
        assert loaded.managed_project_id == "mgr-xyz"


class TestAccessTokenExpired:
    def test_fresh_token_not_expired(self):
        from agent.google_oauth import GoogleCredentials

        creds = GoogleCredentials(
            access_token="at", refresh_token="rt",
            expires_ms=int((time.time() + 3600) * 1000),
        )
        assert creds.access_token_expired() is False

    def test_near_expiry_considered_expired(self):
        """60s skew — a token with 30s left is considered expired."""
        from agent.google_oauth import GoogleCredentials

        creds = GoogleCredentials(
            access_token="at", refresh_token="rt",
            expires_ms=int((time.time() + 30) * 1000),
        )
        assert creds.access_token_expired() is True

    def test_no_token_is_expired(self):
        from agent.google_oauth import GoogleCredentials

        creds = GoogleCredentials(
            access_token="", refresh_token="rt", expires_ms=999999999,
        )
        assert creds.access_token_expired() is True


class TestOAuthEndpointRouting:
    def test_official_aliases_and_legacy_calls_use_official_urls(self, monkeypatch):
        from agent import google_oauth
        from agent.gemini_endpoints import resolve_gemini_oauth_endpoints

        official = resolve_gemini_oauth_endpoints({})
        assert google_oauth.AUTH_ENDPOINT == official.oauth_authorize_url
        assert google_oauth.TOKEN_ENDPOINT == official.oauth_token_url
        assert google_oauth.USERINFO_ENDPOINT == official.oauth_userinfo_url

        urls = []
        monkeypatch.setattr(
            google_oauth,
            "_post_form",
            lambda url, data, timeout: urls.append(url) or {},
        )
        google_oauth.exchange_code("legacy-code", "verifier", "http://localhost")
        google_oauth.refresh_access_token("legacy-refresh")

        assert urls == [official.oauth_token_url, official.oauth_token_url]

    def test_exchange_and_refresh_use_custom_token_url(self, monkeypatch):
        from agent import google_oauth

        endpoints = _custom_oauth_endpoints()
        requests = []
        monkeypatch.setattr(
            google_oauth,
            "_post_form",
            lambda url, data, timeout: requests.append((url, data)) or {},
        )

        google_oauth.exchange_code(
            "authorization-code",
            "verifier",
            "http://127.0.0.1/callback",
            endpoints=endpoints,
        )
        google_oauth.refresh_access_token("refresh-secret", endpoints=endpoints)

        assert [url for url, _ in requests] == [
            endpoints.oauth_token_url,
            endpoints.oauth_token_url,
        ]
        assert requests[0][1]["code"] == "authorization-code"
        assert requests[1][1]["refresh_token"] == "refresh-secret"

    def test_userinfo_request_uses_custom_url_with_only_alt_json(self, monkeypatch):
        from agent import google_oauth

        endpoints = _custom_oauth_endpoints()
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"email":"user@example.test"}'

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers["Authorization"]
            return Response()

        monkeypatch.setattr(google_oauth.urllib.request, "urlopen", fake_urlopen)

        email = google_oauth._fetch_user_email("access-secret", endpoints=endpoints)

        assert email == "user@example.test"
        assert captured == {
            "url": endpoints.oauth_userinfo_url + "?alt=json",
            "authorization": "Bearer access-secret",
        }

    def test_userinfo_http_error_logs_only_fixed_category(self, monkeypatch, caplog):
        from agent import google_oauth

        endpoints = _custom_oauth_endpoints()
        access_token = "access-token-value"
        refresh_token = "refresh-token-value"
        client_secret = "client-secret-value"
        response_body = (
            f"<html>{access_token} {refresh_token} {client_secret} "
            f"{endpoints.oauth_userinfo_url}</html>"
        )

        def reject(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                response_body,
                {},
                io.BytesIO(response_body.encode()),
            )

        monkeypatch.setattr(google_oauth.urllib.request, "urlopen", reject)
        caplog.set_level(logging.DEBUG, logger=google_oauth.__name__)

        assert google_oauth._fetch_user_email(
            access_token, endpoints=endpoints
        ) == ""

        assert "Google userinfo lookup failed" in caplog.text
        for unsafe in (
            access_token,
            refresh_token,
            client_secret,
            endpoints.oauth_userinfo_url,
            response_body,
            "HTTPError",
            "Traceback",
            "HTTP Error",
        ):
            assert unsafe not in caplog.text

    def test_invalid_profile_endpoint_fails_before_exchange_network(self, monkeypatch):
        from agent import google_oauth
        from agent.gemini_endpoints import GeminiEndpointConfigError

        config_path = Path.home() / ".hermes" / "config.yaml"
        config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "google-gemini-cli": {
                            "oauth_token_url": (
                                "https://alice:token-secret@example.test/token"
                            )
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            google_oauth,
            "_post_form",
            lambda *args, **kwargs: pytest.fail("network request must not run"),
        )

        with pytest.raises(GeminiEndpointConfigError) as caught:
            google_oauth.exchange_code(
                "authorization-secret", "verifier-secret", "http://localhost"
            )

        message = str(caught.value)
        for secret in ("token-secret", "authorization-secret", "verifier-secret"):
            assert secret not in message

    @pytest.mark.parametrize(
        ("status", "request_kind", "custom_endpoint"),
        [
            (400, "exchange", True),
            (500, "refresh", True),
            (400, "exchange", False),
            (500, "refresh", False),
        ],
    )
    def test_token_http_errors_redact_response_and_endpoint_url(
        self, monkeypatch, caplog, status, request_kind, custom_endpoint
    ):
        from agent import google_oauth
        from agent.gemini_endpoints import resolve_gemini_oauth_endpoints

        endpoints = (
            _custom_oauth_endpoints()
            if custom_endpoint
            else resolve_gemini_oauth_endpoints({})
        )
        authorization_code = "authorization-code-value"
        refresh_token = "refresh-token-value"
        access_token = "access-token-value"
        client_secret = "client-secret-value"
        response_body = (
            f"<html>upstream exploded</html> {authorization_code} {refresh_token} "
            f"{access_token} {client_secret}"
        )

        def reject(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                status,
                "unsafe upstream reason",
                {},
                io.BytesIO(response_body.encode()),
            )

        monkeypatch.setattr(google_oauth.urllib.request, "urlopen", reject)

        with pytest.raises(google_oauth.GoogleOAuthError) as caught:
            if request_kind == "exchange":
                google_oauth.exchange_code(
                    authorization_code,
                    "verifier",
                    "http://127.0.0.1/callback",
                    client_secret=client_secret,
                    endpoints=endpoints,
                )
            else:
                google_oauth.refresh_access_token(
                    refresh_token,
                    client_secret=client_secret,
                    endpoints=endpoints,
                )

        assert caught.value.code == "google_oauth_token_http_error"
        assert f"HTTP {status}" in str(caught.value)
        assert caught.value.__cause__ is None
        rendered = str(caught.value) + caplog.text
        for secret in (
            response_body,
            "<html>upstream exploded</html>",
            authorization_code,
            refresh_token,
            access_token,
            client_secret,
            endpoints.oauth_token_url,
        ):
            assert secret not in rendered

    @pytest.mark.parametrize("failure_kind", ["timeout", "read"])
    def test_token_request_failures_are_sanitized(
        self, monkeypatch, failure_kind
    ):
        from agent import google_oauth

        endpoint_url = "http://127.0.0.1:9/private/token"
        unsafe_detail = f"access-secret refresh-secret {endpoint_url}"

        class BrokenResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                raise OSError(unsafe_detail)

        def fail(request, timeout):
            if failure_kind == "timeout":
                raise TimeoutError(unsafe_detail)
            return BrokenResponse()

        monkeypatch.setattr(google_oauth.urllib.request, "urlopen", fail)

        with pytest.raises(google_oauth.GoogleOAuthError) as caught:
            google_oauth._post_form(
                endpoint_url, {"client_secret": "client-secret"}, 0.01
            )

        assert caught.value.code == "google_oauth_token_network_error"
        assert str(caught.value) == "Google OAuth token request failed."
        assert caught.value.__cause__ is None
        for unsafe in (unsafe_detail, endpoint_url, "access-secret", "refresh-secret"):
            assert unsafe not in str(caught.value)

    @pytest.mark.parametrize(
        "raw_response",
        [
            b"not-json access-secret refresh-secret",
            b'["access-secret", "refresh-secret"]',
        ],
        ids=["invalid-json", "non-dict-json"],
    )
    def test_token_invalid_responses_are_sanitized(
        self, monkeypatch, raw_response
    ):
        from agent import google_oauth

        endpoint_url = "http://127.0.0.1:9/private/token"

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return raw_response

        monkeypatch.setattr(
            google_oauth.urllib.request, "urlopen", lambda request, timeout: Response()
        )

        with pytest.raises(google_oauth.GoogleOAuthError) as caught:
            google_oauth._post_form(
                endpoint_url, {"client_secret": "client-secret"}, 0.01
            )

        assert caught.value.code == "google_oauth_token_invalid_response"
        assert str(caught.value) == "Google OAuth token response was invalid."
        assert caught.value.__cause__ is None
        rendered = str(caught.value)
        for unsafe in (endpoint_url, "access-secret", "refresh-secret", "client-secret"):
            assert unsafe not in rendered


class TestOAuthLoopbackE2E:
    def test_custom_token_and_userinfo_requests_use_loopback_server(self):
        from agent import google_oauth
        from agent.gemini_endpoints import resolve_gemini_oauth_endpoints

        observed = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                form = urllib.parse.parse_qs(self.rfile.read(length).decode())
                observed["post_path"] = self.path
                observed["grant_type"] = form.get("grant_type", [None])[0]
                payload = json.dumps(
                    {
                        "access_token": "loopback-access",
                        "refresh_token": "loopback-refresh",
                        "expires_in": 3600,
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                observed["userinfo_path"] = parsed.path
                observed["userinfo_query"] = urllib.parse.parse_qs(parsed.query)
                observed["authorization_present"] = bool(
                    self.headers.get("Authorization")
                )
                payload = b'{"email":"loopback@example.test"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            endpoints = resolve_gemini_oauth_endpoints(
                {
                    "providers": {
                        "google-gemini-cli": {
                            "oauth_authorize_url": (
                                f"http://127.0.0.1:{port}/authorize"
                            ),
                            "oauth_token_url": (
                                f"http://127.0.0.1:{port}/oauth/token"
                            ),
                            "oauth_userinfo_url": (
                                f"http://127.0.0.1:{port}/oauth/userinfo"
                            ),
                        }
                    }
                }
            )
            token_response = google_oauth.exchange_code(
                "loopback-code",
                "loopback-verifier",
                "http://127.0.0.1/callback",
                client_id="loopback-client",
                client_secret="loopback-client-secret",
                timeout=2,
                endpoints=endpoints,
            )
            email = google_oauth._fetch_user_email(
                token_response["access_token"], timeout=2, endpoints=endpoints
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        assert thread.is_alive() is False
        assert observed["post_path"] == "/oauth/token"
        assert observed["grant_type"] == "authorization_code"
        assert observed["userinfo_path"] == "/oauth/userinfo"
        assert observed["userinfo_query"] == {"alt": ["json"]}
        assert observed["authorization_present"] is True
        assert email == "loopback@example.test"


class TestOAuthFlowEndpointRouting:
    def test_existing_credentials_skip_endpoint_resolution(self, monkeypatch):
        from agent import google_oauth

        existing = google_oauth.GoogleCredentials(
            access_token="cached-access",
            refresh_token="cached-refresh",
            expires_ms=int((time.time() + 3600) * 1000),
        )
        google_oauth.save_credentials(existing)
        monkeypatch.setattr(
            google_oauth,
            "resolve_gemini_oauth_endpoints",
            lambda: pytest.fail("existing credentials must skip endpoint resolution"),
        )

        result = google_oauth.start_oauth_flow(force_relogin=False)

        assert result == existing

    def test_force_relogin_resolves_endpoints_before_network(self, monkeypatch):
        from agent import google_oauth
        from agent.gemini_endpoints import GeminiEndpointConfigError

        existing = google_oauth.GoogleCredentials(
            access_token="cached-access",
            refresh_token="cached-refresh",
            expires_ms=int((time.time() + 3600) * 1000),
        )
        google_oauth.save_credentials(existing)
        monkeypatch.setattr(
            google_oauth,
            "resolve_gemini_oauth_endpoints",
            lambda: (_ for _ in ()).throw(GeminiEndpointConfigError("invalid endpoint")),
        )
        monkeypatch.setattr(
            google_oauth,
            "_require_client_id",
            lambda: pytest.fail("network setup must not continue"),
        )

        with pytest.raises(GeminiEndpointConfigError, match="invalid endpoint"):
            google_oauth.start_oauth_flow(force_relogin=True)

    def test_start_flow_resolves_once_and_threads_same_endpoints(
        self, monkeypatch, capsys
    ):
        from agent import google_oauth

        endpoints = _custom_oauth_endpoints()
        resolved = []
        received = {}

        class Server:
            server_address = (google_oauth.REDIRECT_HOST, 43123)

            def serve_forever(self):
                google_oauth._OAuthCallbackHandler.captured_code = "callback-code"
                google_oauth._OAuthCallbackHandler.ready.set()

            def shutdown(self):
                pass

            def server_close(self):
                pass

        def fake_resolve():
            resolved.append(True)
            return endpoints

        def fake_exchange(code, verifier, redirect_uri, **kwargs):
            received["exchange"] = (code, redirect_uri, kwargs["endpoints"])
            return {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "expires_in": 3600,
            }

        def fake_persist(token_resp, **kwargs):
            received["persist"] = kwargs["endpoints"]
            return google_oauth.GoogleCredentials(
                access_token=token_resp["access_token"],
                refresh_token=token_resp["refresh_token"],
                expires_ms=int((time.time() + 3600) * 1000),
            )

        monkeypatch.setattr(google_oauth, "resolve_gemini_oauth_endpoints", fake_resolve)
        monkeypatch.setattr(google_oauth, "_bind_callback_server", lambda port: (Server(), 43123))
        monkeypatch.setattr(google_oauth, "exchange_code", fake_exchange)
        monkeypatch.setattr(google_oauth, "_persist_token_response", fake_persist)

        google_oauth.start_oauth_flow(force_relogin=True, open_browser=False)

        output = capsys.readouterr().out
        authorize_url = next(
            line.strip() for line in output.splitlines() if line.strip().startswith("https://")
        )
        parsed = google_oauth.urllib.parse.urlparse(authorize_url)
        assert (parsed.netloc, parsed.path) == (
            "login.example.test",
            "/custom/authorize",
        )
        assert len(resolved) == 1
        assert received["exchange"] == (
            "callback-code",
            "http://127.0.0.1:43123/oauth2callback",
            endpoints,
        )
        assert received["persist"] is endpoints

    def test_headless_start_passes_resolved_endpoints_to_paste_mode(self, monkeypatch):
        from agent import google_oauth

        endpoints = _custom_oauth_endpoints()
        received = []
        monkeypatch.setenv("HERMES_HEADLESS", "1")
        monkeypatch.setattr(
            google_oauth, "resolve_gemini_oauth_endpoints", lambda: endpoints
        )

        def fake_paste(*args, **kwargs):
            received.append(kwargs["endpoints"])
            return google_oauth.GoogleCredentials(
                access_token="access",
                refresh_token="refresh",
                expires_ms=int((time.time() + 3600) * 1000),
            )

        monkeypatch.setattr(google_oauth, "_paste_mode_login", fake_paste)

        google_oauth.start_oauth_flow(force_relogin=True)

        assert received == [endpoints]

    def test_paste_mode_uses_custom_authorize_and_threads_endpoints(
        self, monkeypatch, capsys
    ):
        from agent import google_oauth

        endpoints = _custom_oauth_endpoints()
        received = {}
        monkeypatch.setattr(google_oauth, "_prompt_paste_fallback", lambda: "pasted-code")

        def fake_exchange(code, verifier, redirect_uri, **kwargs):
            received["exchange"] = kwargs["endpoints"]
            return {"access_token": "access", "refresh_token": "refresh"}

        def fake_persist(token_resp, **kwargs):
            received["persist"] = kwargs["endpoints"]
            return google_oauth.GoogleCredentials(
                access_token="access",
                refresh_token="refresh",
                expires_ms=int((time.time() + 3600) * 1000),
            )

        monkeypatch.setattr(google_oauth, "exchange_code", fake_exchange)
        monkeypatch.setattr(google_oauth, "_persist_token_response", fake_persist)

        google_oauth._paste_mode_login(
            "verifier", "challenge", "state", "client", "secret", "project",
            endpoints=endpoints,
        )

        output = capsys.readouterr().out
        authorize_url = next(
            line.strip() for line in output.splitlines() if line.strip().startswith("https://")
        )
        parsed = google_oauth.urllib.parse.urlparse(authorize_url)
        assert (parsed.netloc, parsed.path) == (
            "login.example.test",
            "/custom/authorize",
        )
        assert received == {"exchange": endpoints, "persist": endpoints}

class TestGetValidAccessToken:
    def _save(self, **over):
        from agent.google_oauth import GoogleCredentials, save_credentials

        defaults = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_ms": int((time.time() + 3600) * 1000),
        }
        defaults.update(over)
        save_credentials(GoogleCredentials(**defaults))

    def test_returns_cached_when_fresh(self, monkeypatch):
        from agent import google_oauth

        self._save(access_token="cached-token")
        monkeypatch.setattr(
            google_oauth,
            "resolve_gemini_oauth_endpoints",
            lambda: pytest.fail("fresh tokens must not resolve endpoint config"),
        )
        assert google_oauth.get_valid_access_token() == "cached-token"

    @pytest.mark.parametrize(
        ("expires_delta", "force_refresh"),
        [(30, False), (3600, True)],
        ids=["expired", "forced"],
    )
    def test_refresh_uses_current_profile_custom_endpoint(
        self, monkeypatch, expires_delta, force_refresh
    ):
        from agent import google_oauth

        endpoints = _custom_oauth_endpoints()
        config_path = Path.home() / ".hermes" / "config.yaml"
        config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "google-gemini-cli": {
                            "oauth_token_url": endpoints.oauth_token_url,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        self._save(expires_ms=int((time.time() + expires_delta) * 1000))
        urls = []
        monkeypatch.setattr(
            google_oauth,
            "_post_form",
            lambda url, data, timeout: urls.append(url)
            or {"access_token": "refreshed", "expires_in": 3600},
        )

        token = google_oauth.get_valid_access_token(force_refresh=force_refresh)

        assert token == "refreshed"
        assert urls == [endpoints.oauth_token_url]

    def test_refreshes_when_near_expiry(self, monkeypatch):
        from agent import google_oauth

        self._save(expires_ms=int((time.time() + 30) * 1000))
        monkeypatch.setattr(
            google_oauth, "_post_form",
            lambda *a, **kw: {"access_token": "refreshed", "expires_in": 3600},
        )
        assert google_oauth.get_valid_access_token() == "refreshed"

    def test_invalid_grant_clears_credentials(self, monkeypatch):
        from agent import google_oauth

        self._save(expires_ms=int((time.time() - 10) * 1000))

        def boom(*a, **kw):
            raise google_oauth.GoogleOAuthError(
                "invalid_grant", code="google_oauth_invalid_grant",
            )

        monkeypatch.setattr(google_oauth, "_post_form", boom)

        with pytest.raises(google_oauth.GoogleOAuthError) as exc_info:
            google_oauth.get_valid_access_token()
        assert exc_info.value.code == "google_oauth_invalid_grant"
        # Credentials should be wiped
        assert google_oauth.load_credentials() is None

    def test_preserves_refresh_when_google_omits(self, monkeypatch):
        from agent import google_oauth

        self._save(expires_ms=int((time.time() + 30) * 1000), refresh_token="original-rt")
        monkeypatch.setattr(
            google_oauth, "_post_form",
            lambda *a, **kw: {"access_token": "new", "expires_in": 3600},
        )
        google_oauth.get_valid_access_token()
        assert google_oauth.load_credentials().refresh_token == "original-rt"


class TestProjectIdResolution:
    @pytest.mark.parametrize("env_var", [
        "HERMES_GEMINI_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT_ID",
    ])
    def test_env_vars_checked(self, monkeypatch, env_var):
        from agent.google_oauth import resolve_project_id_from_env

        monkeypatch.setenv(env_var, "test-proj")
        assert resolve_project_id_from_env() == "test-proj"

    def test_priority_order(self, monkeypatch):
        from agent.google_oauth import resolve_project_id_from_env

        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "lower-priority")
        monkeypatch.setenv("HERMES_GEMINI_PROJECT_ID", "higher-priority")
        assert resolve_project_id_from_env() == "higher-priority"

    def test_no_env_returns_empty(self):
        from agent.google_oauth import resolve_project_id_from_env

        assert resolve_project_id_from_env() == ""


class TestHeadlessDetection:
    def test_detects_ssh(self, monkeypatch):
        from agent.google_oauth import _is_headless

        monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 22 5.6.7.8 9876")
        assert _is_headless() is True

    def test_detects_hermes_headless(self, monkeypatch):
        from agent.google_oauth import _is_headless

        monkeypatch.setenv("HERMES_HEADLESS", "1")
        assert _is_headless() is True

    def test_default_not_headless(self):
        from agent.google_oauth import _is_headless

        assert _is_headless() is False


# =============================================================================
# google_code_assist.py — project discovery, onboarding, quota, VPC-SC
# =============================================================================

class TestCodeAssistVpcScDetection:
    def test_detects_vpc_sc_in_json(self):
        from agent.google_code_assist import _is_vpc_sc_violation

        body = json.dumps({
            "error": {
                "details": [{"reason": "SECURITY_POLICY_VIOLATED"}],
                "message": "blocked by policy",
            }
        })
        assert _is_vpc_sc_violation(body) is True

    def test_detects_vpc_sc_in_message(self):
        from agent.google_code_assist import _is_vpc_sc_violation

        body = '{"error": {"message": "SECURITY_POLICY_VIOLATED"}}'
        assert _is_vpc_sc_violation(body) is True

    def test_non_vpc_sc_returns_false(self):
        from agent.google_code_assist import _is_vpc_sc_violation

        assert _is_vpc_sc_violation('{"error": {"message": "not found"}}') is False
        assert _is_vpc_sc_violation("") is False


class TestLoadCodeAssist:
    def test_code_assist_endpoint_remains_official_compatibility_alias(self):
        from agent import google_code_assist
        from agent.gemini_endpoints import OFFICIAL_CODE_ASSIST_BASE_URL

        assert google_code_assist.CODE_ASSIST_ENDPOINT == OFFICIAL_CODE_ASSIST_BASE_URL

    def test_parses_response(self, monkeypatch):
        from agent import google_code_assist

        fake = {
            "currentTier": {"id": "free-tier"},
            "cloudaicompanionProject": "proj-123",
            "allowedTiers": [{"id": "free-tier"}, {"id": "standard-tier"}],
        }
        monkeypatch.setattr(google_code_assist, "_post_json", lambda *a, **kw: fake)

        info = google_code_assist.load_code_assist("access-token")
        assert info.current_tier_id == "free-tier"
        assert info.cloudaicompanion_project == "proj-123"
        assert "free-tier" in info.allowed_tiers
        assert "standard-tier" in info.allowed_tiers

    def test_vpc_sc_forces_standard_tier(self, monkeypatch):
        from agent import google_code_assist

        def boom(*a, **kw):
            raise google_code_assist.CodeAssistError(
                "VPC-SC policy violation", code="code_assist_vpc_sc",
            )

        monkeypatch.setattr(google_code_assist, "_post_json", boom)

        info = google_code_assist.load_code_assist("access-token", project_id="corp-proj")
        assert info.current_tier_id == "standard-tier"
        assert info.cloudaicompanion_project == "corp-proj"

    def test_custom_endpoint_is_used_once_without_fallback(self, monkeypatch):
        from agent import google_code_assist

        calls = []

        def boom(url, *args, **kwargs):
            calls.append(url)
            raise google_code_assist.CodeAssistError("proxy unavailable")

        monkeypatch.setattr(google_code_assist, "_post_json", boom)

        with pytest.raises(google_code_assist.CodeAssistError):
            google_code_assist.load_code_assist(
                "access-token", base_url="https://proxy.example.test/root/",
            )

        assert calls == [
            "https://proxy.example.test/root/v1internal:loadCodeAssist",
        ]

    def test_official_endpoint_keeps_sandbox_fallbacks(self, monkeypatch):
        from agent import google_code_assist

        calls = []

        def fake_post(url, *args, **kwargs):
            calls.append(url)
            if len(calls) < 3:
                raise google_code_assist.CodeAssistError("unavailable")
            return {"currentTier": {"id": "free-tier"}}

        monkeypatch.setattr(google_code_assist, "_post_json", fake_post)

        info = google_code_assist.load_code_assist("access-token")

        assert info.current_tier_id == "free-tier"
        assert calls == [
            f"{google_code_assist.CODE_ASSIST_ENDPOINT}/v1internal:loadCodeAssist",
            *[
                f"{endpoint}/v1internal:loadCodeAssist"
                for endpoint in google_code_assist.FALLBACK_ENDPOINTS
            ],
        ]

    def test_custom_vpc_sc_error_does_not_reach_or_log_endpoint(
        self, monkeypatch, caplog,
    ):
        from agent import google_code_assist

        calls = []
        custom_base_url = "https://proxy.test/private/root"
        caplog.set_level(logging.INFO, logger=google_code_assist.__name__)

        def boom(url, *args, **kwargs):
            calls.append(url)
            raise google_code_assist.CodeAssistError(
                "VPC-SC policy violation", code="code_assist_vpc_sc",
            )

        monkeypatch.setattr(google_code_assist, "_post_json", boom)

        info = google_code_assist.load_code_assist(
            "access-token", project_id="corp-proj", base_url=custom_base_url,
        )

        assert info.current_tier_id == "standard-tier"
        assert calls == [f"{custom_base_url}/v1internal:loadCodeAssist"]
        assert custom_base_url not in caplog.text
        assert calls[0] not in caplog.text

    def test_http_error_does_not_expose_access_token(self, monkeypatch, caplog):
        from agent import google_code_assist

        access_token = "secret-access-token"
        error = urllib.error.HTTPError(
            "https://proxy.example.test/root/v1internal:loadCodeAssist",
            500,
            "failed",
            {},
            io.BytesIO(f"backend echoed {access_token}".encode()),
        )
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: (_ for _ in ()).throw(error),
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.load_code_assist(
                access_token, base_url="https://proxy.example.test/root",
            )

        assert access_token not in str(exc_info.value)
        assert access_token not in caplog.text

    def test_custom_http_error_redacts_fullbase_and_path_fragments(
        self, monkeypatch, caplog,
    ):
        from agent import google_code_assist

        access_token = "secret-access-token"
        custom_base_url = "https://proxy.example.test/private/customer-path"
        private_path = "/private/customer-path"
        error = urllib.error.HTTPError(
            f"{custom_base_url}/v1internal:loadCodeAssist",
            500,
            "failed",
            {},
            io.BytesIO(
                f"backend path={private_path} token={access_token}".encode()
            ),
        )
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: (_ for _ in ()).throw(error),
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.load_code_assist(
                access_token, base_url=custom_base_url,
            )

        rendered = f"{exc_info.value!r}\n{caplog.text}"
        for sensitive in (
            access_token, custom_base_url, private_path, private_path.lstrip("/"),
        ):
            assert sensitive not in rendered

    def test_custom_http_error_redacts_canonical_encoded_paths(
        self, monkeypatch, caplog,
    ):
        from agent import google_code_assist

        access_token = "canonical-secret-token"
        custom_base_url = "https://proxy.example.test/private/%2522customer"
        private_variants = (
            custom_base_url,
            "https://proxy.example.test/private/%22customer",
            "https://proxy.example.test/private/\"customer",
            "/private/%2522customer", "private/%2522customer",
            "/private/%22customer", "private/%22customer",
            "/private/\"customer", "private/\"customer",
        )
        error = urllib.error.HTTPError(
            f"{custom_base_url}/v1internal:loadCodeAssist",
            500,
            "failed",
            {},
            io.BytesIO(" | ".join((*private_variants, access_token)).encode()),
        )
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: (_ for _ in ()).throw(error),
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.load_code_assist(
                access_token, base_url=custom_base_url,
            )

        rendered = f"{exc_info.value!r}\n{caplog.text}"
        for sensitive in (*private_variants, access_token):
            assert sensitive not in rendered

    def test_empty_http_error_redacts_reason_and_drops_sensitive_cause(
        self, monkeypatch, caplog,
    ):
        from agent import google_code_assist

        access_token = "secret-access-token"
        custom_base_url = "https://proxy.example.test/private-root"
        client_secret = "secret-client-credential"
        reason = f"token={access_token} url={custom_base_url} secret={client_secret}"
        error = urllib.error.HTTPError(
            f"{custom_base_url}/v1internal:loadCodeAssist",
            500,
            reason,
            {},
            io.BytesIO(b""),
        )
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: (_ for _ in ()).throw(error),
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.load_code_assist(
                access_token, base_url=custom_base_url,
            )

        exposed = (
            str(exc_info.value),
            repr(exc_info.value),
            repr(exc_info.value.__cause__),
            caplog.text,
        )
        for sensitive in (access_token, custom_base_url, client_secret):
            assert all(sensitive not in value for value in exposed)
        assert exc_info.value.__cause__ is None


class TestCodeAssistHttpPrimitive:
    class FakeResponse:
        def __init__(self, body):
            self.body = body
            self.read_sizes = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            self.read_sizes.append(size)
            return self.body[:size]

    def test_success_response_read_is_bounded(self, monkeypatch):
        from agent import google_code_assist

        response = self.FakeResponse(b"{}")
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: response,
        )

        assert google_code_assist._post_json("https://example.test", {}, "at") == {}
        assert response.read_sizes == [google_code_assist.MAX_RESPONSE_BYTES + 1]

    def test_success_response_over_limit_is_rejected(self, monkeypatch):
        from agent import google_code_assist

        response = self.FakeResponse(b"x" * (google_code_assist.MAX_RESPONSE_BYTES + 1))
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: response,
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist._post_json("https://example.test", {}, "at")

        assert exc_info.value.code == "code_assist_response_too_large"

    def test_http_error_response_read_is_bounded(self, monkeypatch):
        from agent import google_code_assist

        body = self.FakeResponse(b"x" * (google_code_assist.MAX_RESPONSE_BYTES + 1))
        error = urllib.error.HTTPError(
            "https://example.test", 500, "failed", {}, body,
        )
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: (_ for _ in ()).throw(error),
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist._post_json("https://example.test", {}, "at")

        assert exc_info.value.code == "code_assist_response_too_large"
        assert body.read_sizes == [google_code_assist.MAX_RESPONSE_BYTES + 1]

    def test_invalid_json_is_a_safe_structured_error(self, monkeypatch):
        from agent import google_code_assist

        secret = "secret-access-token"
        response = self.FakeResponse(
            f"not-json {secret} https://proxy.example.test/private".encode()
        )
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: response,
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist._post_json("https://example.test", {}, secret)

        assert exc_info.value.code == "code_assist_invalid_response"
        assert exc_info.value.__cause__ is None
        assert secret not in repr(exc_info.value)
        assert "https://proxy.example.test/private" not in repr(exc_info.value)

    @pytest.mark.parametrize("response_body", [b"[]", b'"ok"', b"123", b"null"])
    def test_mock_non_object_json_is_a_safe_structured_error(
        self, monkeypatch, caplog, response_body,
    ):
        from agent import google_code_assist

        custom_base_url = "https://proxy.example.test/private-root"
        response = self.FakeResponse(response_body)
        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: response,
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.load_code_assist(
                "access-token", base_url=custom_base_url,
            )

        exposed = f"{exc_info.value!r}\n{exc_info.value.__cause__!r}\n{caplog.text}"
        assert exc_info.value.code == "code_assist_invalid_response"
        assert exc_info.value.__cause__ is None
        assert response_body.decode() not in exposed
        assert custom_base_url not in exposed

    @pytest.mark.parametrize(
        "transport_error",
        [
            urllib.error.URLError(
                "secret-access-token https://proxy.example.test/private"
            ),
            TimeoutError("secret-access-token https://proxy.example.test/private"),
        ],
    )
    def test_transport_errors_are_safe(self, monkeypatch, caplog, transport_error):
        from agent import google_code_assist

        monkeypatch.setattr(
            google_code_assist.urllib.request,
            "urlopen",
            lambda *args, **kwargs: (_ for _ in ()).throw(transport_error),
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.load_code_assist(
                "secret-access-token",
                base_url="https://proxy.example.test/private",
            )

        exposed = f"{exc_info.value!r}\n{exc_info.value.__cause__!r}\n{caplog.text}"
        assert exc_info.value.code == "code_assist_network_error"
        assert exc_info.value.__cause__ is None
        assert "secret-access-token" not in exposed
        assert "https://proxy.example.test/private" not in exposed

    def test_loopback_custom_request_uses_real_path_body_and_header(self):
        from agent import google_code_assist

        response = json.dumps({"currentTier": {"id": "free-tier"}}).encode()
        with _code_assist_server(response) as (base_url, requests, thread):
            info = google_code_assist.load_code_assist(
                "loopback-token",
                project_id="project-123",
                base_url=f"{base_url}/custom/",
            )

        assert not thread.is_alive()
        assert info.current_tier_id == "free-tier"
        assert requests[0]["path"] == "/custom/v1internal:loadCodeAssist"
        assert requests[0]["authorization"] == "Bearer loopback-token"
        assert json.loads(requests[0]["body"])["cloudaicompanionProject"] == "project-123"

    def test_loopback_oversized_response_is_rejected_and_server_stops(self):
        from agent import google_code_assist

        response = b"x" * (google_code_assist.MAX_RESPONSE_BYTES + 1)
        with _code_assist_server(response) as (base_url, _, thread):
            with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
                google_code_assist.load_code_assist("at", base_url=base_url)

        assert exc_info.value.code == "code_assist_response_too_large"
        assert not thread.is_alive()

    @pytest.mark.parametrize("response_body", [b"[]", b'"ok"', b"123", b"null"])
    def test_loopback_non_object_json_is_rejected_and_server_stops(
        self, caplog, response_body,
    ):
        from agent import google_code_assist

        with _code_assist_server(response_body) as (base_url, _, thread):
            custom_base_url = f"{base_url}/private-root"
            with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
                google_code_assist.load_code_assist(
                    "access-token", base_url=custom_base_url,
                )

        exposed = f"{exc_info.value!r}\n{exc_info.value.__cause__!r}\n{caplog.text}"
        assert exc_info.value.code == "code_assist_invalid_response"
        assert exc_info.value.__cause__ is None
        assert response_body.decode() not in exposed
        assert custom_base_url not in exposed
        assert not thread.is_alive()


class TestOnboardUser:
    def test_paid_tier_requires_project_id(self):
        from agent import google_code_assist

        with pytest.raises(google_code_assist.ProjectIdRequiredError):
            google_code_assist.onboard_user(
                "at", tier_id="standard-tier", project_id="",
            )

    def test_free_tier_no_project_required(self, monkeypatch):
        from agent import google_code_assist

        monkeypatch.setattr(
            google_code_assist, "_post_json",
            lambda *a, **kw: {"done": True, "response": {"cloudaicompanionProject": "gen-123"}},
        )
        resp = google_code_assist.onboard_user("at", tier_id="free-tier")
        assert resp["done"] is True

    def test_lro_polling(self, monkeypatch):
        """Simulate a long-running operation that completes on the second poll."""
        from agent import google_code_assist

        call_count = {"n": 0}

        def fake_post(url, body, token, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"name": "operations/op-abc", "done": False}
            return {"name": "operations/op-abc", "done": True, "response": {}}

        monkeypatch.setattr(google_code_assist, "_post_json", fake_post)
        monkeypatch.setattr(google_code_assist.time, "sleep", lambda *_: None)

        resp = google_code_assist.onboard_user(
            "at", tier_id="free-tier",
        )
        assert resp["done"] is True
        assert call_count["n"] >= 2

    def test_custom_endpoint_is_used_for_onboard_and_all_polls(self, monkeypatch):
        from agent import google_code_assist

        calls = []
        responses = [
            {"name": "operations/op-abc", "done": False},
            {"name": "operations/op-abc", "done": False},
            {"name": "operations/op-abc", "done": True, "response": {}},
        ]

        def fake_post(url, *args, **kwargs):
            calls.append(url)
            return responses.pop(0)

        monkeypatch.setattr(google_code_assist, "_post_json", fake_post)
        monkeypatch.setattr(google_code_assist.time, "sleep", lambda *_: None)

        resp = google_code_assist.onboard_user(
            "access-token",
            tier_id="free-tier",
            base_url="https://proxy.example.test/code-assist/",
        )

        assert resp["done"] is True
        assert calls == [
            "https://proxy.example.test/code-assist/v1internal:onboardUser",
            "https://proxy.example.test/code-assist/v1internal/operations/op-abc",
            "https://proxy.example.test/code-assist/v1internal/operations/op-abc",
        ]

    @pytest.mark.parametrize(
        "responses",
        [
            [{"done": True, "error": {"code": 13, "message": "failed"}}],
            [
                {"name": "operations/op-abc", "done": False},
                {"name": "operations/op-abc", "done": True, "error": {"code": 13}},
            ],
        ],
        ids=["initial", "poll"],
    )
    def test_done_lro_with_error_is_failure(self, monkeypatch, responses):
        from agent import google_code_assist

        monkeypatch.setattr(
            google_code_assist,
            "_post_json",
            lambda *args, **kwargs: responses.pop(0),
        )
        monkeypatch.setattr(google_code_assist.time, "sleep", lambda *_: None)

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.onboard_user("at", tier_id="free-tier")

        assert exc_info.value.code == "code_assist_onboarding_failed"

    def test_lro_poll_exhaustion_is_timeout(self, monkeypatch):
        from agent import google_code_assist

        monkeypatch.setattr(
            google_code_assist,
            "_post_json",
            lambda *args, **kwargs: {
                "name": "operations/op-abc",
                "done": False,
            },
        )
        monkeypatch.setattr(google_code_assist, "_ONBOARDING_POLL_ATTEMPTS", 2)
        monkeypatch.setattr(google_code_assist.time, "sleep", lambda *_: None)

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.onboard_user("at", tier_id="free-tier")

        assert exc_info.value.code == "code_assist_onboarding_timeout"

    def test_pending_lro_without_operation_name_is_rejected(self, monkeypatch):
        from agent import google_code_assist

        monkeypatch.setattr(
            google_code_assist,
            "_post_json",
            lambda *args, **kwargs: {"done": False},
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.onboard_user("at", tier_id="free-tier")

        assert exc_info.value.code == "code_assist_invalid_operation"

    @pytest.mark.parametrize(
        "operation_name",
        [
            "operations/.",
            "operations/..",
            "operations/op%2Fsecret",
            "operations\\op",
            "operations/op name",
            "https://evil.test/operations/op",
            "//evil.test/operations/op",
            "//[",
            "/operations/op",
            "operations/op?token=secret",
            "operations/op#secret",
            "operations/../secret-token",
            "operations/op/extra",
            "tasks/op",
            "operations/op\nsecret-token",
            123,
        ],
    )
    def test_rejects_unsafe_operation_name_without_polling_or_leaking_secrets(
        self, monkeypatch, caplog, operation_name,
    ):
        from agent import google_code_assist

        calls = []

        def fake_post(url, *args, **kwargs):
            calls.append(url)
            return {"name": operation_name, "done": False}

        monkeypatch.setattr(google_code_assist, "_post_json", fake_post)
        monkeypatch.setattr(google_code_assist.time, "sleep", lambda *_: None)

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.onboard_user(
                "secret-token",
                tier_id="free-tier",
                base_url="https://proxy.example.test/private-root",
            )

        assert len(calls) == 1
        combined = f"{exc_info.value}\n{caplog.text}"
        assert str(operation_name) not in combined
        assert "secret-token" not in combined
        assert "https://proxy.example.test/private-root" not in combined


class TestRetrieveUserQuota:
    def test_parses_buckets(self, monkeypatch):
        from agent import google_code_assist

        fake = {
            "buckets": [
                {
                    "modelId": "gemini-2.5-pro",
                    "tokenType": "input",
                    "remainingFraction": 0.75,
                    "resetTime": "2026-04-17T00:00:00Z",
                },
                {
                    "modelId": "gemini-2.5-flash",
                    "remainingFraction": 0.9,
                },
            ]
        }
        monkeypatch.setattr(google_code_assist, "_post_json", lambda *a, **kw: fake)

        buckets = google_code_assist.retrieve_user_quota("at", project_id="p1")
        assert len(buckets) == 2
        assert buckets[0].model_id == "gemini-2.5-pro"
        assert buckets[0].remaining_fraction == 0.75
        assert buckets[1].remaining_fraction == 0.9

    def test_custom_endpoint_is_used(self, monkeypatch):
        from agent import google_code_assist

        calls = []
        monkeypatch.setattr(
            google_code_assist,
            "_post_json",
            lambda url, *args, **kwargs: calls.append(url) or {"buckets": []},
        )

        google_code_assist.retrieve_user_quota(
            "at", base_url="https://proxy.example.test/root/",
        )

        assert calls == [
            "https://proxy.example.test/root/v1internal:retrieveUserQuota",
        ]


class TestResolveProjectContext:
    def test_configured_shortcircuits(self, monkeypatch):
        from agent.google_code_assist import resolve_project_context

        # Should NOT call loadCodeAssist when configured_project_id is set
        def should_not_be_called(*a, **kw):
            raise AssertionError("should short-circuit")

        monkeypatch.setattr(
            "agent.google_code_assist._post_json", should_not_be_called,
        )
        ctx = resolve_project_context("at", configured_project_id="proj-abc")
        assert ctx.project_id == "proj-abc"
        assert ctx.source == "config"

    def test_env_shortcircuits(self, monkeypatch):
        from agent.google_code_assist import resolve_project_context

        monkeypatch.setattr(
            "agent.google_code_assist._post_json",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("nope")),
        )
        ctx = resolve_project_context("at", env_project_id="env-proj")
        assert ctx.project_id == "env-proj"
        assert ctx.source == "env"

    def test_discovers_via_load_code_assist(self, monkeypatch):
        from agent import google_code_assist

        monkeypatch.setattr(
            google_code_assist, "_post_json",
            lambda *a, **kw: {
                "currentTier": {"id": "free-tier"},
                "cloudaicompanionProject": "discovered-proj",
            },
        )
        ctx = google_code_assist.resolve_project_context("at")
        assert ctx.project_id == "discovered-proj"
        assert ctx.tier_id == "free-tier"
        assert ctx.source == "discovered"

    def test_discovery_uses_custom_code_assist_endpoint(self, monkeypatch):
        from agent import google_code_assist

        calls = []
        monkeypatch.setattr(
            google_code_assist,
            "_post_json",
            lambda url, *args, **kwargs: calls.append(url) or {
                "currentTier": {"id": "free-tier"},
                "cloudaicompanionProject": "discovered-proj",
            },
        )

        ctx = google_code_assist.resolve_project_context(
            "at", code_assist_base_url="https://proxy.example.test/root/",
        )

        assert ctx.source == "discovered"
        assert calls == [
            "https://proxy.example.test/root/v1internal:loadCodeAssist",
        ]

    def test_onboarding_uses_same_custom_code_assist_endpoint(self, monkeypatch):
        from agent import google_code_assist

        calls = []

        def fake_post(url, *args, **kwargs):
            calls.append(url)
            if url.endswith("v1internal:loadCodeAssist"):
                return {}
            return {
                "done": True,
                "response": {"cloudaicompanionProject": "onboarded-proj"},
            }

        monkeypatch.setattr(google_code_assist, "_post_json", fake_post)

        ctx = google_code_assist.resolve_project_context(
            "at", code_assist_base_url="https://proxy.example.test/root/",
        )

        assert ctx.source == "onboarded"
        assert calls == [
            "https://proxy.example.test/root/v1internal:loadCodeAssist",
            "https://proxy.example.test/root/v1internal:onboardUser",
        ]

    def test_failed_onboarding_is_not_marked_onboarded(self, monkeypatch):
        from agent import google_code_assist

        responses = [
            {},
            {"done": True, "error": {"code": 13, "message": "failed"}},
        ]
        monkeypatch.setattr(
            google_code_assist,
            "_post_json",
            lambda *args, **kwargs: responses.pop(0),
        )

        with pytest.raises(google_code_assist.CodeAssistError) as exc_info:
            google_code_assist.resolve_project_context("at")

        assert exc_info.value.code == "code_assist_onboarding_failed"

    def test_configured_fast_path_accepts_custom_endpoint_without_request(self, monkeypatch):
        from agent import google_code_assist

        monkeypatch.setattr(
            google_code_assist,
            "_post_json",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no request")),
        )

        ctx = google_code_assist.resolve_project_context(
            "at",
            configured_project_id="configured-proj",
            code_assist_base_url="https://proxy.example.test/root/",
        )

        assert ctx.project_id == "configured-proj"
        assert ctx.source == "config"


# =============================================================================
# gemini_cloudcode_adapter.py — request/response translation
# =============================================================================

class TestBuildGeminiRequest:
    def test_user_assistant_messages(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ])
        assert req["contents"][0] == {
            "role": "user", "parts": [{"text": "hi"}],
        }
        assert req["contents"][1] == {
            "role": "model", "parts": [{"text": "hello"}],
        }

    def test_system_instruction_separated(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(messages=[
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hi"},
        ])
        assert req["systemInstruction"]["parts"][0]["text"] == "You are helpful"
        # System should NOT appear in contents
        assert all(c["role"] != "system" for c in req["contents"])

    def test_multiple_system_messages_joined(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(messages=[
            {"role": "system", "content": "A"},
            {"role": "system", "content": "B"},
            {"role": "user", "content": "hi"},
        ])
        assert "A\nB" in req["systemInstruction"]["parts"][0]["text"]

    def test_tool_call_translation(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(messages=[
            {"role": "user", "content": "what's the weather?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "SF"}'},
                }],
            },
        ])
        # Assistant turn should have a functionCall part
        model_turn = req["contents"][1]
        assert model_turn["role"] == "model"
        fc_part = next(p for p in model_turn["parts"] if "functionCall" in p)
        assert fc_part["functionCall"]["name"] == "get_weather"
        assert fc_part["functionCall"]["args"] == {"city": "SF"}
        assert fc_part["functionCall"]["id"] == "call_1"

    def test_tool_result_translation(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(messages=[
            {"role": "user", "content": "q"},
            {"role": "assistant", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "get_weather", "arguments": "{}"},
            }]},
            {
                "role": "tool",
                "name": "get_weather",
                "tool_call_id": "c1",
                "content": '{"temp": 72}',
            },
        ])
        # Last content turn should carry functionResponse
        last = req["contents"][-1]
        fr_part = next(p for p in last["parts"] if "functionResponse" in p)
        assert fr_part["functionResponse"]["name"] == "get_weather"
        assert fr_part["functionResponse"]["response"] == {"temp": 72}
        assert fr_part["functionResponse"]["id"] == "c1"

    def test_tools_translated_to_function_declarations(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(
            messages=[{"role": "user", "content": "hi"}],
            tools=[
                {"type": "function", "function": {
                    "name": "fn1", "description": "foo",
                    "parameters": {"type": "object"},
                }},
            ],
        )
        decls = req["tools"][0]["functionDeclarations"]
        assert decls[0]["name"] == "fn1"
        assert decls[0]["description"] == "foo"
        assert decls[0]["parameters"] == {"type": "object"}

    def test_tools_strip_json_schema_only_fields_from_parameters(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(
            messages=[{"role": "user", "content": "hi"}],
            tools=[
                {"type": "function", "function": {
                    "name": "fn1",
                    "description": "foo",
                    "parameters": {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "city": {
                                "type": "string",
                                "$schema": "ignored",
                                "description": "City name",
                                "additionalProperties": False,
                            }
                        },
                        "required": ["city"],
                    },
                }},
            ],
        )
        params = req["tools"][0]["functionDeclarations"][0]["parameters"]
        assert "$schema" not in params
        assert "additionalProperties" not in params
        assert params["type"] == "object"
        assert params["required"] == ["city"]
        assert params["properties"]["city"] == {
            "type": "string",
            "description": "City name",
        }

    def test_tool_choice_auto(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(
            messages=[{"role": "user", "content": "hi"}],
            tool_choice="auto",
        )
        assert req["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"

    def test_tool_choice_required(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(
            messages=[{"role": "user", "content": "hi"}],
            tool_choice="required",
        )
        assert req["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"

    def test_tool_choice_specific_function(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(
            messages=[{"role": "user", "content": "hi"}],
            tool_choice={"type": "function", "function": {"name": "my_fn"}},
        )
        cfg = req["toolConfig"]["functionCallingConfig"]
        assert cfg["mode"] == "ANY"
        assert cfg["allowedFunctionNames"] == ["my_fn"]

    def test_generation_config_params(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=512,
            top_p=0.9,
            stop=["###", "END"],
        )
        gc = req["generationConfig"]
        assert gc["temperature"] == 0.7
        assert gc["maxOutputTokens"] == 512
        assert gc["topP"] == 0.9
        assert gc["stopSequences"] == ["###", "END"]

    def test_thinking_config_normalization(self):
        from agent.gemini_cloudcode_adapter import build_gemini_request

        req = build_gemini_request(
            messages=[{"role": "user", "content": "hi"}],
            thinking_config={"thinking_budget": 1024, "include_thoughts": True},
        )
        tc = req["generationConfig"]["thinkingConfig"]
        assert tc["thinkingBudget"] == 1024
        assert tc["includeThoughts"] is True


class TestWrapCodeAssistRequest:
    def test_envelope_shape(self):
        from agent.gemini_cloudcode_adapter import wrap_code_assist_request

        inner = {"contents": [], "generationConfig": {}}
        wrapped = wrap_code_assist_request(
            project_id="p1", model="gemini-2.5-pro", inner_request=inner,
        )
        assert wrapped["project"] == "p1"
        assert wrapped["model"] == "gemini-2.5-pro"
        assert wrapped["request"] is inner
        assert "user_prompt_id" in wrapped
        assert len(wrapped["user_prompt_id"]) > 10


class TestTranslateGeminiResponse:
    def test_text_response(self):
        from agent.gemini_cloudcode_adapter import _translate_gemini_response

        resp = {
            "response": {
                "candidates": [{
                    "content": {"parts": [{"text": "hello world"}]},
                    "finishReason": "STOP",
                }],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5,
                    "totalTokenCount": 15,
                },
            }
        }
        result = _translate_gemini_response(resp, model="gemini-2.5-flash")
        assert result.choices[0].message.content == "hello world"
        assert result.choices[0].message.tool_calls is None
        assert result.choices[0].finish_reason == "stop"
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.usage.total_tokens == 15

    def test_function_call_response(self):
        from agent.gemini_cloudcode_adapter import _translate_gemini_response

        resp = {
            "response": {
                "candidates": [{
                    "content": {"parts": [{
                        "functionCall": {"name": "lookup", "args": {"q": "weather"}, "id": "provider-call-1"},
                    }]},
                    "finishReason": "STOP",
                }],
            }
        }
        result = _translate_gemini_response(resp, model="gemini-2.5-flash")
        tc = result.choices[0].message.tool_calls[0]
        assert tc.id == "provider-call-1"
        assert tc.function.name == "lookup"
        assert json.loads(tc.function.arguments) == {"q": "weather"}
        assert result.choices[0].finish_reason == "tool_calls"

    def test_thought_parts_go_to_reasoning(self):
        from agent.gemini_cloudcode_adapter import _translate_gemini_response

        resp = {
            "response": {
                "candidates": [{
                    "content": {"parts": [
                        {"thought": True, "text": "let me think"},
                        {"text": "final answer"},
                    ]},
                }],
            }
        }
        result = _translate_gemini_response(resp, model="gemini-2.5-flash")
        assert result.choices[0].message.content == "final answer"
        assert result.choices[0].message.reasoning == "let me think"

    def test_unwraps_direct_format(self):
        """If response is already at top level (no 'response' wrapper), still parse."""
        from agent.gemini_cloudcode_adapter import _translate_gemini_response

        resp = {
            "candidates": [{
                "content": {"parts": [{"text": "hi"}]},
                "finishReason": "STOP",
            }],
        }
        result = _translate_gemini_response(resp, model="gemini-2.5-flash")
        assert result.choices[0].message.content == "hi"

    def test_empty_candidates(self):
        from agent.gemini_cloudcode_adapter import _translate_gemini_response

        result = _translate_gemini_response({"response": {"candidates": []}}, model="gemini-2.5-flash")
        assert result.choices[0].message.content == ""
        assert result.choices[0].finish_reason == "stop"

    def test_finish_reason_mapping(self):
        from agent.gemini_cloudcode_adapter import _map_gemini_finish_reason

        assert _map_gemini_finish_reason("STOP") == "stop"
        assert _map_gemini_finish_reason("MAX_TOKENS") == "length"
        assert _map_gemini_finish_reason("SAFETY") == "content_filter"
        assert _map_gemini_finish_reason("RECITATION") == "content_filter"


class TestTranslateStreamEvent:
    def test_parallel_calls_to_same_tool_get_unique_indices(self):
        """Gemini may emit several functionCall parts with the same name in a
        single turn (e.g. parallel file reads). Each must get its own OpenAI
        ``index`` — otherwise downstream aggregators collapse them into one.
        """
        from agent.gemini_cloudcode_adapter import _translate_stream_event

        event = {
            "response": {
                "candidates": [{
                    "content": {"parts": [
                        {"functionCall": {"name": "read_file", "args": {"path": "a"}}},
                        {"functionCall": {"name": "read_file", "args": {"path": "b"}}},
                        {"functionCall": {"name": "read_file", "args": {"path": "c"}}},
                    ]},
                }],
            }
        }
        counter = [0]
        chunks = _translate_stream_event(event, model="gemini-2.5-flash",
                                         tool_call_counter=counter)
        indices = [c.choices[0].delta.tool_calls[0].index for c in chunks]
        assert indices == [0, 1, 2]
        assert counter[0] == 3

    def test_counter_persists_across_events(self):
        """Index assignment must continue across SSE events in the same stream."""
        from agent.gemini_cloudcode_adapter import _translate_stream_event

        def _event(name):
            return {"response": {"candidates": [{
                "content": {"parts": [{"functionCall": {"name": name, "args": {}}}]},
            }]}}

        counter = [0]
        chunks_a = _translate_stream_event(_event("foo"), model="m", tool_call_counter=counter)
        chunks_b = _translate_stream_event(_event("bar"), model="m", tool_call_counter=counter)
        chunks_c = _translate_stream_event(_event("foo"), model="m", tool_call_counter=counter)

        assert chunks_a[0].choices[0].delta.tool_calls[0].index == 0
        assert chunks_b[0].choices[0].delta.tool_calls[0].index == 1
        assert chunks_c[0].choices[0].delta.tool_calls[0].index == 2

    def test_finish_reason_switches_to_tool_calls_when_any_seen(self):
        from agent.gemini_cloudcode_adapter import _translate_stream_event

        counter = [0]
        # First event emits one tool call.
        _translate_stream_event(
            {"response": {"candidates": [{
                "content": {"parts": [{"functionCall": {"name": "x", "args": {}}}]},
            }]}},
            model="m", tool_call_counter=counter,
        )
        # Second event carries only the terminal finishReason.
        chunks = _translate_stream_event(
            {"response": {"candidates": [{"finishReason": "STOP"}]}},
            model="m", tool_call_counter=counter,
        )
        assert chunks[-1].choices[0].finish_reason == "tool_calls"


class TestMakeStreamChunk:
    def test_reasoning_only_chunk_has_content_none(self):
        from agent.gemini_cloudcode_adapter import _make_stream_chunk

        chunk = _make_stream_chunk(model="m", reasoning="think")
        delta = chunk.choices[0].delta
        assert delta.content is None
        assert delta.reasoning == "think"

    def test_content_only_chunk_has_reasoning_none(self):
        from agent.gemini_cloudcode_adapter import _make_stream_chunk

        chunk = _make_stream_chunk(model="m", content="hello")
        delta = chunk.choices[0].delta
        assert delta.content == "hello"
        assert delta.reasoning is None
        assert delta.tool_calls is None

    def test_finish_only_chunk_has_all_fields_none(self):
        from agent.gemini_cloudcode_adapter import _make_stream_chunk

        chunk = _make_stream_chunk(model="m", finish_reason="stop")
        delta = chunk.choices[0].delta
        assert delta.content is None
        assert delta.reasoning is None
        assert delta.tool_calls is None
        assert chunk.choices[0].finish_reason == "stop"


class TestGeminiCloudCodeClient:
    def test_client_exposes_openai_interface(self):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient

        client = GeminiCloudCodeClient(api_key="dummy")
        try:
            assert hasattr(client, "chat")
            assert hasattr(client.chat, "completions")
            assert callable(client.chat.completions.create)
        finally:
            client.close()

    def test_resolves_marker_to_configured_code_assist_base(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.gemini_endpoints import GeminiOAuthEndpoints

        monkeypatch.setattr(
            "agent.gemini_cloudcode_adapter.resolve_gemini_oauth_endpoints",
            lambda: GeminiOAuthEndpoints(
                oauth_authorize_url="https://auth.example.test/authorize",
                oauth_token_url="https://auth.example.test/token",
                oauth_userinfo_url="https://auth.example.test/userinfo",
                code_assist_base_url="https://proxy.example.test/private/code",
                custom_code_assist=True,
            ),
        )
        client = GeminiCloudCodeClient(base_url="cloudcode-pa://google")
        try:
            assert client.base_url == "https://proxy.example.test/private/code"
        finally:
            client.close()

    def test_resolves_marker_with_trailing_slash(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.gemini_endpoints import GeminiOAuthEndpoints

        monkeypatch.setattr(
            "agent.gemini_cloudcode_adapter.resolve_gemini_oauth_endpoints",
            lambda: GeminiOAuthEndpoints(
                oauth_authorize_url="https://auth.example.test/authorize",
                oauth_token_url="https://auth.example.test/token",
                oauth_userinfo_url="https://auth.example.test/userinfo",
                code_assist_base_url="https://proxy.example.test/private/code",
                custom_code_assist=True,
            ),
        )
        client = GeminiCloudCodeClient(base_url="cloudcode-pa://google/")
        try:
            assert client.base_url == "https://proxy.example.test/private/code"
        finally:
            client.close()

    @pytest.mark.parametrize(
        "base_url",
        [
            "ftp://proxy.example.test/private/code",
            "https://user:secret@proxy.example.test/private/code",
            "https://proxy.example.test/private/code?token=secret",
            "https://proxy.example.test/private/code#secret",
            "http://proxy.example.test/private/code",
            "https://proxy.example.test/private/\x00code",
            0,
        ],
    )
    def test_explicit_base_rejects_unsafe_urls(self, base_url):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.gemini_endpoints import GeminiEndpointConfigError

        with pytest.raises(GeminiEndpointConfigError):
            GeminiCloudCodeClient(base_url=base_url)

    def test_explicit_network_base_is_normalized(self):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient

        client = GeminiCloudCodeClient(base_url="https://proxy.example.test/code/")
        try:
            assert client.base_url == "https://proxy.example.test/code"
        finally:
            client.close()

    def test_runtime_helper_uses_cloudcode_client_for_custom_https_base(self):
        from agent.agent_runtime_helpers import create_openai_client
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient

        agent = SimpleNamespace(
            provider="google-gemini-cli",
            _client_log_context=lambda: "test",
        )
        client = create_openai_client(
            agent,
            {
                "api_key": "oauth-token",
                "base_url": "https://proxy.example.test/private/code",
                "project_id": "project-1",
            },
            reason="test",
            shared=False,
        )
        try:
            assert isinstance(client, GeminiCloudCodeClient)
            assert client.base_url == "https://proxy.example.test/private/code"
            assert client._configured_project_id == "project-1"
        finally:
            client.close()

    def test_project_discovery_and_generation_use_custom_base(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import ProjectContext

        project_calls = []
        requests = []
        monkeypatch.setattr("agent.google_oauth.get_valid_access_token", lambda **_: "token")
        monkeypatch.setattr("agent.google_oauth.resolve_project_id_from_env", lambda: "")
        monkeypatch.setattr("agent.google_oauth.load_credentials", lambda: None)

        def resolve_project(*args, **kwargs):
            project_calls.append(kwargs)
            return ProjectContext(project_id="project-1")

        monkeypatch.setattr("agent.gemini_cloudcode_adapter.resolve_project_context", resolve_project)

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(
                200,
                json={"response": {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}},
            )

        client = GeminiCloudCodeClient(base_url="https://proxy.example.test/private/code/")
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            result = client.chat.completions.create(
                model="gemini-test", messages=[{"role": "user", "content": "hi"}],
            )
            assert result.choices[0].message.content == "ok"
            assert project_calls[0]["code_assist_base_url"] == client.base_url
            assert requests == [
                "https://proxy.example.test/private/code/v1internal:generateContent"
            ]
        finally:
            client.close()

    def test_project_context_resolution_is_single_flight(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import ProjectContext

        calls = []
        calls_lock = threading.Lock()
        start = threading.Barrier(2)
        monkeypatch.setattr("agent.google_oauth.resolve_project_id_from_env", lambda: "")
        monkeypatch.setattr("agent.google_oauth.load_credentials", lambda: None)
        monkeypatch.setattr("agent.google_oauth.update_project_ids", lambda **_: None)

        def resolve_project(*args, **kwargs):
            with calls_lock:
                calls.append(kwargs["code_assist_base_url"])
            time.sleep(0.1)
            return ProjectContext(project_id="project-1")

        monkeypatch.setattr(
            "agent.gemini_cloudcode_adapter.resolve_project_context", resolve_project,
        )
        client = GeminiCloudCodeClient(base_url="https://proxy.example.test/code")

        def resolve():
            start.wait()
            return client._ensure_project_context("token", "gemini-test")

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                contexts = list(executor.map(lambda _: resolve(), range(2)))
            assert [ctx.project_id for ctx in contexts] == ["project-1", "project-1"]
            assert calls == ["https://proxy.example.test/code"]
        finally:
            client.close()

    def test_project_context_lock_releases_after_resolution_error(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError, ProjectContext

        calls = []
        monkeypatch.setattr("agent.google_oauth.resolve_project_id_from_env", lambda: "")
        monkeypatch.setattr("agent.google_oauth.load_credentials", lambda: None)
        monkeypatch.setattr("agent.google_oauth.update_project_ids", lambda **_: None)

        def resolve_project(*args, **kwargs):
            calls.append(kwargs["code_assist_base_url"])
            if len(calls) == 1:
                raise CodeAssistError("temporary failure")
            return ProjectContext(project_id="project-1")

        monkeypatch.setattr(
            "agent.gemini_cloudcode_adapter.resolve_project_context", resolve_project,
        )
        client = GeminiCloudCodeClient(base_url="https://proxy.example.test/code")
        try:
            with pytest.raises(CodeAssistError):
                client._ensure_project_context("token", "gemini-test")
            assert client._ensure_project_context(
                "token", "gemini-test"
            ).project_id == "project-1"
            assert len(calls) == 2
        finally:
            client.close()

    def test_nonstream_401_refreshes_once_on_same_custom_url(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient

        token_calls = []
        requests = []

        def token(*, force_refresh=False):
            token_calls.append(force_refresh)
            return "fresh-token" if force_refresh else "stale-token"

        monkeypatch.setattr("agent.google_oauth.get_valid_access_token", token)

        def handler(request):
            requests.append((str(request.url), request.headers["Authorization"]))
            if len(requests) == 1:
                return httpx.Response(401, json={"error": {"message": "expired"}})
            return httpx.Response(
                200,
                json={"response": {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}},
            )

        client = GeminiCloudCodeClient(
            base_url="https://proxy.example.test/private/code", project_id="project-1",
        )
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            result = client.chat.completions.create(model="gemini-test", messages=[])
            assert result.choices[0].message.content == "ok"
            assert token_calls == [False, True]
            assert requests == [
                ("https://proxy.example.test/private/code/v1internal:generateContent", "Bearer stale-token"),
                ("https://proxy.example.test/private/code/v1internal:generateContent", "Bearer fresh-token"),
            ]
        finally:
            client.close()

    def test_stream_401_refreshes_before_first_chunk_on_same_custom_url(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient

        token_calls = []
        requests = []

        def token(*, force_refresh=False):
            token_calls.append(force_refresh)
            return "fresh-token" if force_refresh else "stale-token"

        monkeypatch.setattr("agent.google_oauth.get_valid_access_token", token)

        def handler(request):
            requests.append((str(request.url), request.headers["Authorization"]))
            if len(requests) == 1:
                return httpx.Response(401, json={"error": {"message": "expired"}})
            event = {"response": {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}}
            return httpx.Response(200, text=f"data: {json.dumps(event)}\n\n")

        client = GeminiCloudCodeClient(
            base_url="https://proxy.example.test/private/code", project_id="project-1",
        )
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            chunks = list(client.chat.completions.create(model="gemini-test", messages=[], stream=True))
            assert chunks[0].choices[0].delta.content == "ok"
            assert token_calls == [False, True]
            assert requests == [
                ("https://proxy.example.test/private/code/v1internal:streamGenerateContent?alt=sse", "Bearer stale-token"),
                ("https://proxy.example.test/private/code/v1internal:streamGenerateContent?alt=sse", "Bearer fresh-token"),
            ]
        finally:
            client.close()

    def test_non_401_does_not_refresh(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        token_calls = []
        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token",
            lambda *, force_refresh=False: token_calls.append(force_refresh) or "token",
        )
        client = GeminiCloudCodeClient(
            base_url="https://proxy.example.test/code", project_id="project-1",
        )
        client._http.close()
        client._http = httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(403, text="denied"))
        )
        try:
            with pytest.raises(CodeAssistError):
                client.chat.completions.create(model="gemini-test", messages=[])
            assert token_calls == [False]
        finally:
            client.close()

    @pytest.mark.parametrize("stream", [False, True])
    def test_second_401_is_raised_after_single_refresh(self, monkeypatch, stream):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        token_calls = []
        requests = []
        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token",
            lambda *, force_refresh=False: (
                token_calls.append(force_refresh) or
                ("fresh-token" if force_refresh else "stale-token")
            ),
        )

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(401, json={"error": {"message": "expired"}})

        client = GeminiCloudCodeClient(
            base_url="https://proxy.example.test/private/code", project_id="project-1",
        )
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(CodeAssistError) as exc_info:
                result = client.chat.completions.create(
                    model="gemini-test", messages=[], stream=stream,
                )
                if stream:
                    list(result)
            assert exc_info.value.status_code == 401
            assert token_calls == [False, True]
            assert len(requests) == 2
            assert len(set(requests)) == 1
        finally:
            client.close()

    def test_http_error_redacts_echoed_custom_path_and_token(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        private_base = "https://proxy.example.test/private/customer-path"
        access_token = "secret-access-token"
        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token", lambda **_: access_token,
        )

        def handler(request):
            return httpx.Response(500, json={
                "error": {
                    "message": f"upstream={private_base} token={access_token}",
                    "status": "INTERNAL",
                }
            })

        client = GeminiCloudCodeClient(base_url=private_base, project_id="project-1")
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(CodeAssistError) as exc_info:
                client.chat.completions.create(model="gemini-test", messages=[])
            rendered = str(exc_info.value)
            assert private_base not in rendered
            assert access_token not in rendered
        finally:
            client.close()

    def test_custom_rate_limit_error_uses_synthetic_safe_response(
        self, monkeypatch, caplog,
    ):
        from agent.error_classifier import FailoverReason, classify_api_error
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        private_base = "https://proxy.example.test/private/customer-path"
        private_path = "/private/customer-path"
        access_token = "secret-access-token"
        original_responses = []
        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token", lambda **_: access_token,
        )

        def handler(request):
            response = httpx.Response(
                429,
                headers={"Retry-After": "17", "Content-Type": "application/json"},
                json={"error": {
                    "message": f"rate limit at {private_path} token={access_token}",
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [{
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": private_path,
                    }],
                }},
            )
            original_responses.append(response)
            return response

        client = GeminiCloudCodeClient(base_url=private_base, project_id="project-1")
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(CodeAssistError) as exc_info:
                client.chat.completions.create(model="gemini-test", messages=[])
            error = exc_info.value
            classified = classify_api_error(
                error, provider="google-gemini-cli", model="gemini-test",
            )
            assert error.response is not None
            assert error.response is not original_responses[0]
            assert error.response.status_code == 429
            assert str(error.response.request.url) == "https://redacted.invalid"
            assert error.response.headers["Retry-After"] == "17"
            assert classified.status_code == 429
            assert classified.reason == FailoverReason.rate_limit
            rendered = "\n".join((
                str(error), repr(error.details), error.response.text,
                repr(classified), classified.message, caplog.text,
            ))
            for sensitive in (private_base, private_path, private_path.lstrip("/"), access_token):
                assert sensitive not in rendered
        finally:
            client.close()

    @pytest.mark.parametrize(
        ("private_base", "private_variants"),
        [
            (
                "https://proxy.example.test/private/%22customer",
                (
                    "https://proxy.example.test/private/%22customer",
                    "https://proxy.example.test/private/\"customer",
                    "/private/%22customer", "private/%22customer",
                    "/private/\"customer", "private/\"customer",
                ),
            ),
            (
                "https://proxy.example.test/private/%2522customer",
                (
                    "https://proxy.example.test/private/%2522customer",
                    "https://proxy.example.test/private/%22customer",
                    "https://proxy.example.test/private/\"customer",
                    "/private/%2522customer", "private/%2522customer",
                    "/private/%22customer", "private/%22customer",
                    "/private/\"customer", "private/\"customer",
                ),
            ),
            (
                "https://proxy.example.test/private/%5csecret",
                (
                    "https://proxy.example.test/private/%5csecret",
                    "https://proxy.example.test/private/%5Csecret",
                    "https://proxy.example.test/private/\\secret",
                    "/private/%5csecret", "private/%5csecret",
                    "/private/%5Csecret", "private/%5Csecret",
                    "/private/\\secret", "private/\\secret",
                ),
            ),
        ],
    )
    def test_canonical_proxy_paths_are_redacted_everywhere(
        self, monkeypatch, caplog, private_base, private_variants,
    ):
        from agent.error_classifier import FailoverReason, classify_api_error
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        access_token = "canonical-secret-token"
        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token", lambda **_: access_token,
        )

        def handler(request):
            return httpx.Response(
                429,
                json={"error": {
                    "message": " | ".join((*private_variants, access_token)),
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [{
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": " | ".join(private_variants),
                    }],
                }},
            )

        client = GeminiCloudCodeClient(base_url=private_base, project_id="project-1")
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(CodeAssistError) as exc_info:
                client.chat.completions.create(model="gemini-test", messages=[])
            error = exc_info.value
            classified = classify_api_error(
                error, provider="google-gemini-cli", model="gemini-test",
            )
            assert classified.reason == FailoverReason.rate_limit
            rendered = "\n".join((
                str(error), repr(error.details), error.response.text,
                "".join(traceback.format_exception(error)),
                repr(classified), classified.message, caplog.text,
            ))
            for sensitive in (*private_variants, access_token):
                assert sensitive not in rendered
        finally:
            client.close()

    def test_sensitive_json_keys_are_redacted_without_collision_data_loss(
        self, monkeypatch, caplog,
    ):
        from agent.error_classifier import FailoverReason, classify_api_error
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        private_base = "https://proxy.example.test/private/%2522customer"
        sensitive_keys = (
            private_base,
            "https://proxy.example.test/private/%22customer",
            "https://proxy.example.test/private/\"customer",
            "/private/%22customer",
            "json-key-secret-token",
        )
        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token",
            lambda **_: sensitive_keys[-1],
        )
        metadata = {
            sensitive_keys[0]: "raw-value",
            sensitive_keys[1]: "decoded-once-value",
            sensitive_keys[2]: "decoded-stable-value",
            sensitive_keys[3]: [{sensitive_keys[4]: "nested-list-value"}],
            sensitive_keys[4]: "token-key-value",
        }

        def handler(request):
            return httpx.Response(429, json={"error": {
                "message": "rate limit",
                "status": "RESOURCE_EXHAUSTED",
                "details": [{
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "RATE_LIMIT",
                    "metadata": metadata,
                }],
            }})

        client = GeminiCloudCodeClient(base_url=private_base, project_id="project-1")
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(CodeAssistError) as exc_info:
                client.chat.completions.create(model="gemini-test", messages=[])
            error = exc_info.value
            classified = classify_api_error(
                error, provider="google-gemini-cli", model="gemini-test",
            )
            assert classified.reason == FailoverReason.rate_limit
            safe_metadata = error.details["metadata"]
            assert len(safe_metadata) == len(metadata)
            assert len(set(safe_metadata)) == len(metadata)
            assert {
                value for value in safe_metadata.values()
                if isinstance(value, str)
            } >= {
                "raw-value", "decoded-once-value", "decoded-stable-value",
                "token-key-value",
            }
            rendered = "\n".join((
                str(error), repr(error.details),
                json.dumps(error.response.json(), sort_keys=True),
                repr(classified), classified.message, caplog.text,
            ))
            for sensitive in sensitive_keys:
                assert sensitive not in rendered
        finally:
            client.close()

    def test_custom_404_names_configured_endpoint(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token", lambda **_: "token",
        )
        client = GeminiCloudCodeClient(
            base_url="https://proxy.example.test/private/code", project_id="project-1",
        )
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={
                "error": {"message": "model missing", "status": "NOT_FOUND"}
            })
        ))
        try:
            with pytest.raises(CodeAssistError) as exc_info:
                client.chat.completions.create(model="gemini-test", messages=[])
            message = str(exc_info.value)
            assert "configured Code Assist endpoint" in message
            assert "cloudcode-pa.googleapis.com" not in message
            assert "/private/code" not in message
        finally:
            client.close()

    @pytest.mark.parametrize(
        "echoed_path", ["/private/customer-path", "private/customer-path"],
    )
    def test_http_error_redacts_proxy_path_fragments(
        self, monkeypatch, caplog, echoed_path,
    ):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        private_base = "https://proxy.example.test/private/customer-path"
        access_token = "secret-access-token"
        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token", lambda **_: access_token,
        )

        def handler(request):
            return httpx.Response(500, json={
                "error": {
                    "message": f"upstream path={echoed_path} token={access_token}",
                    "status": "INTERNAL",
                    "details": [{
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": echoed_path,
                    }],
                }
            })

        client = GeminiCloudCodeClient(base_url=private_base, project_id="project-1")
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(CodeAssistError) as exc_info:
                client.chat.completions.create(model="gemini-test", messages=[])
            rendered = "\n".join((
                str(exc_info.value),
                repr(exc_info.value.details),
                "".join(traceback.format_exception(exc_info.value)),
                caplog.text,
            ))
            for sensitive in (
                private_base,
                "/private/customer-path",
                "private/customer-path",
                access_token,
            ):
                assert sensitive not in rendered
        finally:
            client.close()

    @pytest.mark.parametrize("late_error_kind", ["http", "code_assist_401"])
    def test_stream_error_after_first_chunk_never_refreshes_or_replays(
        self, monkeypatch, late_error_kind,
    ):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        refresh_calls = []
        stream_calls = []

        def token(*, force_refresh=False):
            if force_refresh:
                refresh_calls.append(True)
            return "access-token"

        monkeypatch.setattr("agent.google_oauth.get_valid_access_token", token)

        def handler(request):
            stream_calls.append(str(request.url))
            return httpx.Response(200, text="unused")

        def events(response):
            yield {
                "response": {
                    "candidates": [{"content": {"parts": [{"text": "first"}]}}]
                }
            }
            if late_error_kind == "http":
                raise httpx.ReadError("late stream failure", request=response.request)
            raise CodeAssistError(
                "late unauthorized", code="code_assist_unauthorized", status_code=401,
            )

        monkeypatch.setattr(
            "agent.gemini_cloudcode_adapter._iter_sse_events", events,
        )
        client = GeminiCloudCodeClient(
            base_url="https://proxy.example.test/private/code", project_id="project-1",
        )
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            stream = client.chat.completions.create(
                model="gemini-test", messages=[], stream=True,
            )
            assert next(stream).choices[0].delta.content == "first"
            with pytest.raises(CodeAssistError):
                next(stream)
            assert refresh_calls == []
            assert stream_calls == [
                "https://proxy.example.test/private/code/v1internal:streamGenerateContent?alt=sse"
            ]
        finally:
            client.close()

    def test_network_error_redacts_custom_path_and_token(self, monkeypatch):
        from agent.gemini_cloudcode_adapter import GeminiCloudCodeClient
        from agent.google_code_assist import CodeAssistError

        private_base = "https://proxy.example.test/private/customer-path"
        access_token = "secret-access-token"
        monkeypatch.setattr(
            "agent.google_oauth.get_valid_access_token", lambda **_: access_token,
        )

        def handler(request):
            raise httpx.ConnectError(
                f"failed url={request.url} token={request.headers['Authorization']}",
                request=request,
            )

        client = GeminiCloudCodeClient(base_url=private_base, project_id="project-1")
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(CodeAssistError) as exc_info:
                client.chat.completions.create(model="gemini-test", messages=[])
            rendered = str(exc_info.value)
            assert private_base not in rendered
            assert access_token not in rendered
            assert exc_info.value.__cause__ is None
        finally:
            client.close()


class TestGeminiHttpErrorParsing:
    """Regression coverage for _gemini_http_error Google-envelope parsing.

    These are the paths that users actually hit during Google-side throttling
    (April 2026: gemini-2.5-pro MODEL_CAPACITY_EXHAUSTED, gemma-4-26b-it
    returning 404).  The error needs to carry status_code + response so the
    main loop's error_classifier and Retry-After logic work.
    """

    @staticmethod
    def _fake_response(status: int, body: dict | str = "", headers=None):
        """Minimal httpx.Response stand-in (duck-typed for _gemini_http_error)."""
        class _FakeResponse:
            def __init__(self):
                self.status_code = status
                if isinstance(body, dict):
                    self.text = json.dumps(body)
                else:
                    self.text = body
                self.headers = headers or {}
        return _FakeResponse()

    def test_model_capacity_exhausted_produces_friendly_message(self):
        from agent.gemini_cloudcode_adapter import _gemini_http_error

        body = {
            "error": {
                "code": 429,
                "message": "Resource has been exhausted (e.g. check quota).",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "MODEL_CAPACITY_EXHAUSTED",
                        "domain": "googleapis.com",
                        "metadata": {"model": "gemini-2.5-pro"},
                    },
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "30s",
                    },
                ],
            }
        }
        err = _gemini_http_error(self._fake_response(429, body))
        assert err.status_code == 429
        assert err.code == "code_assist_capacity_exhausted"
        assert err.retry_after == 30.0
        assert err.details["reason"] == "MODEL_CAPACITY_EXHAUSTED"
        # Message must be user-friendly, not a raw JSON dump.
        message = str(err)
        assert "gemini-2.5-pro" in message
        assert "capacity exhausted" in message.lower()
        assert "30s" in message
        # response attr is preserved for run_agent's Retry-After header path.
        assert err.response is not None

    def test_resource_exhausted_without_reason(self):
        from agent.gemini_cloudcode_adapter import _gemini_http_error

        body = {
            "error": {
                "code": 429,
                "message": "Quota exceeded for requests per minute.",
                "status": "RESOURCE_EXHAUSTED",
            }
        }
        err = _gemini_http_error(self._fake_response(429, body))
        assert err.status_code == 429
        assert err.code == "code_assist_rate_limited"
        message = str(err)
        assert "quota" in message.lower()

    def test_404_model_not_found_produces_model_retired_message(self):
        from agent.gemini_cloudcode_adapter import _gemini_http_error

        body = {
            "error": {
                "code": 404,
                "message": "models/gemma-4-26b-it is not found for API version v1internal",
                "status": "NOT_FOUND",
            }
        }
        err = _gemini_http_error(self._fake_response(404, body))
        assert err.status_code == 404
        message = str(err)
        assert "not available" in message.lower() or "retired" in message.lower()
        # Error message should reference the actual model text from Google.
        assert "gemma-4-26b-it" in message

    def test_unauthorized_preserves_status_code(self):
        from agent.gemini_cloudcode_adapter import _gemini_http_error

        err = _gemini_http_error(self._fake_response(
            401, {"error": {"code": 401, "message": "Invalid token", "status": "UNAUTHENTICATED"}},
        ))
        assert err.status_code == 401
        assert err.code == "code_assist_unauthorized"

    def test_retry_after_header_fallback(self):
        """If the body has no RetryInfo detail, fall back to Retry-After header."""
        from agent.gemini_cloudcode_adapter import _gemini_http_error

        resp = self._fake_response(
            429,
            {"error": {"code": 429, "message": "Rate limited", "status": "RESOURCE_EXHAUSTED"}},
            headers={"Retry-After": "45"},
        )
        err = _gemini_http_error(resp)
        assert err.retry_after == 45.0

    def test_malformed_body_still_produces_structured_error(self):
        """Non-JSON body must not swallow status_code — we still want the classifier path."""
        from agent.gemini_cloudcode_adapter import _gemini_http_error

        err = _gemini_http_error(self._fake_response(500, "<html>internal error</html>"))
        assert err.status_code == 500
        # Raw body snippet must still be there for debugging.
        assert "500" in str(err)

    def test_status_code_flows_through_error_classifier(self):
        """End-to-end: CodeAssistError from a 429 must classify as rate_limit.

        This is the whole point of adding status_code to CodeAssistError —
        _extract_status_code must see it and FailoverReason.rate_limit must
        fire, so the main loop triggers fallback_providers.
        """
        from agent.gemini_cloudcode_adapter import _gemini_http_error
        from agent.error_classifier import classify_api_error, FailoverReason

        body = {
            "error": {
                "code": 429,
                "message": "Resource has been exhausted",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "MODEL_CAPACITY_EXHAUSTED",
                        "metadata": {"model": "gemini-2.5-pro"},
                    }
                ],
            }
        }
        err = _gemini_http_error(self._fake_response(429, body))

        classified = classify_api_error(
            err, provider="google-gemini-cli", model="gemini-2.5-pro",
        )
        assert classified.status_code == 429
        assert classified.reason == FailoverReason.rate_limit


# =============================================================================
# Provider registration
# =============================================================================

class TestProviderRegistration:
    def test_registry_entry(self):
        from hermes_cli.auth import PROVIDER_REGISTRY

        assert "google-gemini-cli" in PROVIDER_REGISTRY
        assert PROVIDER_REGISTRY["google-gemini-cli"].auth_type == "oauth_external"

    def test_google_gemini_alias_still_goes_to_api_key_gemini(self):
        """Regression guard: don't shadow the existing google-gemini → gemini alias."""
        from hermes_cli.auth import resolve_provider

        assert resolve_provider("google-gemini") == "gemini"

    def test_runtime_provider_raises_when_not_logged_in(self):
        from hermes_cli.auth import AuthError
        from hermes_cli.runtime_provider import resolve_runtime_provider

        with pytest.raises(AuthError) as exc_info:
            resolve_runtime_provider(requested="google-gemini-cli")
        assert exc_info.value.code == "google_oauth_not_logged_in"

    def test_runtime_provider_returns_correct_shape_when_logged_in(self):
        from agent.google_oauth import GoogleCredentials, save_credentials
        from hermes_cli.runtime_provider import resolve_runtime_provider

        save_credentials(GoogleCredentials(
            access_token="live-tok",
            refresh_token="rt",
            expires_ms=int((time.time() + 3600) * 1000),
            project_id="my-proj",
            email="t@e.com",
        ))

        result = resolve_runtime_provider(requested="google-gemini-cli")
        assert result["provider"] == "google-gemini-cli"
        assert result["api_mode"] == "chat_completions"
        assert result["api_key"] == "live-tok"
        assert result["base_url"] == "https://cloudcode-pa.googleapis.com"
        assert result["project_id"] == "my-proj"
        assert result["email"] == "t@e.com"

    def test_runtime_provider_returns_configured_code_assist_base(self, tmp_path, monkeypatch):
        from agent.google_oauth import GoogleCredentials, save_credentials
        from agent.agent_runtime_helpers import create_openai_client
        from agent.google_code_assist import ProjectContext
        from hermes_cli.runtime_provider import resolve_runtime_provider

        hermes_home = tmp_path / "hermes"
        hermes_home.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))
        (hermes_home / "config.yaml").write_text(
            "providers:\n"
            "  google-gemini-cli:\n"
            "    oauth_authorize_url: https://proxy.example.test/oauth/authorize\n"
            "    oauth_token_url: https://proxy.example.test/oauth/token\n"
            "    oauth_userinfo_url: https://proxy.example.test/oauth/userinfo\n"
            "    code_assist_base_url: https://proxy.example.test/private/code/\n"
        )
        save_credentials(GoogleCredentials(
            access_token="live-token", refresh_token="refresh-token",
            expires_ms=int((time.time() + 3600) * 1000),
        ))

        result = resolve_runtime_provider(requested="google-gemini-cli")
        assert result["base_url"] == "https://proxy.example.test/private/code"

        project_bases = []
        requests = []

        def resolve_project(*args, **kwargs):
            project_bases.append(kwargs["code_assist_base_url"])
            return ProjectContext(project_id="project-1")

        monkeypatch.setattr(
            "agent.gemini_cloudcode_adapter.resolve_project_context", resolve_project,
        )

        def handler(request):
            requests.append(str(request.url))
            if "streamGenerateContent" in request.url.path:
                event = {
                    "response": {
                        "candidates": [{"content": {"parts": [{"text": "stream"}]}}]
                    }
                }
                return httpx.Response(200, text=f"data: {json.dumps(event)}\n\n")
            return httpx.Response(
                200,
                json={
                    "response": {
                        "candidates": [{"content": {"parts": [{"text": "generate"}]}}]
                    }
                },
            )

        agent = SimpleNamespace(
            provider="google-gemini-cli", _client_log_context=lambda: "test",
        )
        client = create_openai_client(agent, result, reason="test", shared=False)
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            generated = client.chat.completions.create(model="gemini-test", messages=[])
            streamed = list(client.chat.completions.create(
                model="gemini-test", messages=[], stream=True,
            ))
            assert generated.choices[0].message.content == "generate"
            assert streamed[0].choices[0].delta.content == "stream"
            assert project_bases == ["https://proxy.example.test/private/code"]
            assert requests == [
                "https://proxy.example.test/private/code/v1internal:generateContent",
                "https://proxy.example.test/private/code/v1internal:streamGenerateContent?alt=sse",
            ]
            assert all("googleapis.com" not in url for url in requests)
        finally:
            client.close()

    def test_determine_api_mode(self):
        from hermes_cli.providers import determine_api_mode

        assert determine_api_mode("google-gemini-cli", "cloudcode-pa://google") == "chat_completions"

    def test_oauth_capable_set_preserves_existing(self):
        from hermes_cli.auth_commands import _OAUTH_CAPABLE_PROVIDERS

        for required in ("anthropic", "nous", "openai-codex", "qwen-oauth", "google-gemini-cli"):
            assert required in _OAUTH_CAPABLE_PROVIDERS

    def test_config_env_vars_registered(self):
        from hermes_cli.config import OPTIONAL_ENV_VARS

        for key in (
            "HERMES_GEMINI_CLIENT_ID",
            "HERMES_GEMINI_CLIENT_SECRET",
            "HERMES_GEMINI_PROJECT_ID",
        ):
            assert key in OPTIONAL_ENV_VARS


class TestAuthStatus:
    def test_not_logged_in(self):
        from hermes_cli.auth import get_auth_status

        s = get_auth_status("google-gemini-cli")
        assert s["logged_in"] is False

    def test_logged_in_reports_email_and_project(self):
        from agent.google_oauth import GoogleCredentials, save_credentials
        from hermes_cli.auth import get_auth_status

        save_credentials(GoogleCredentials(
            access_token="tok", refresh_token="rt",
            expires_ms=int((time.time() + 3600) * 1000),
            email="tek@nous.ai",
            project_id="tek-proj",
        ))

        s = get_auth_status("google-gemini-cli")
        assert s["logged_in"] is True
        assert s["email"] == "tek@nous.ai"
        assert s["project_id"] == "tek-proj"


class TestGquotaCommand:
    def test_gquota_registered(self):
        from hermes_cli.commands import COMMANDS

        assert "/gquota" in COMMANDS


class TestRunGeminiOauthLoginPure:
    def test_returns_pool_compatible_dict(self, monkeypatch):
        from agent import google_oauth

        def fake_start(**kw):
            return google_oauth.GoogleCredentials(
                access_token="at", refresh_token="rt",
                expires_ms=int((time.time() + 3600) * 1000),
                email="u@e.com", project_id="p",
            )

        monkeypatch.setattr(google_oauth, "start_oauth_flow", fake_start)

        result = google_oauth.run_gemini_oauth_login_pure()
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"
        assert result["email"] == "u@e.com"
        assert result["project_id"] == "p"
        assert isinstance(result["expires_at_ms"], int)
