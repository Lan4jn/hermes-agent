"""Google Gemini CLI OAuth provider authentication helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_CLOUDCODE_BASE_URL = "cloudcode-pa://google"
GEMINI_OAUTH_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60


def _mark_google_gemini_cli_active(creds: Dict[str, Any]) -> None:
    from hermes_cli.auth import _auth_store_lock, _load_auth_store, _save_auth_store, _save_provider_state

    with _auth_store_lock():
        auth_store = _load_auth_store()
        state: Dict[str, Any] = {}
        if creds.get("email"):
            state["email"] = str(creds["email"])
        _save_provider_state(auth_store, "google-gemini-cli", state)
        _save_auth_store(auth_store)


def resolve_gemini_oauth_runtime_credentials(
    *,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    from hermes_cli.auth import AuthError

    try:
        from agent.google_oauth import (
            GoogleOAuthError,
            _credentials_path,
            get_valid_access_token,
            load_credentials,
        )
    except ImportError as exc:
        raise AuthError(
            f"agent.google_oauth is not importable: {exc}",
            provider="google-gemini-cli",
            code="google_oauth_module_missing",
        ) from exc

    try:
        access_token = get_valid_access_token(force_refresh=force_refresh)
    except GoogleOAuthError as exc:
        raise AuthError(
            str(exc),
            provider="google-gemini-cli",
            code=exc.code,
        ) from exc

    from agent.gemini_endpoints import resolve_gemini_oauth_endpoints

    creds = load_credentials()
    base_url = resolve_gemini_oauth_endpoints().code_assist_base_url
    return {
        "provider": "google-gemini-cli",
        "base_url": base_url,
        "api_key": access_token,
        "source": "google-oauth",
        "expires_at_ms": (creds.expires_ms if creds else None),
        "auth_file": str(_credentials_path()),
        "email": (creds.email if creds else "") or "",
        "project_id": (creds.project_id if creds else "") or "",
    }


def get_gemini_oauth_auth_status() -> Dict[str, Any]:
    try:
        from agent.google_oauth import _credentials_path, load_credentials
    except ImportError:
        return {"logged_in": False, "error": "agent.google_oauth unavailable"}

    auth_path = _credentials_path()
    creds = load_credentials()
    if creds is None or not creds.access_token:
        return {
            "logged_in": False,
            "auth_file": str(auth_path),
            "error": "not logged in",
        }
    return {
        "logged_in": True,
        "auth_file": str(auth_path),
        "source": "google-oauth",
        "api_key": creds.access_token,
        "expires_at_ms": creds.expires_ms,
        "email": creds.email,
        "project_id": creds.project_id,
    }


def _login_gemini_oauth() -> None:
    from agent.google_oauth import resolve_project_id_from_env, start_oauth_flow
    from hermes_cli.auth import _update_config_for_provider
    from hermes_constants import display_hermes_home

    print()
    print("Signing in to Google Gemini via OAuth (PKCE)...")
    print("(Hermes creates its own local OAuth session via Google Code Assist)")
    print()

    env_project = resolve_project_id_from_env()
    creds = start_oauth_flow(
        project_id=env_project,
        force_relogin=True,
    )

    _mark_google_gemini_cli_active({
        "email": creds.email,
        "project_id": creds.project_id,
    })

    from agent.gemini_endpoints import resolve_gemini_oauth_endpoints

    endpoints = resolve_gemini_oauth_endpoints()
    config_path = _update_config_for_provider(
        "google-gemini-cli", endpoints.code_assist_base_url
    )
    print()
    print("Login successful!")
    print(f"  Account: {creds.email}")
    if creds.project_id:
        print(f"  GCP Project: {creds.project_id}")
    else:
        print("  GCP Project: (auto / free tier)")
    print(f"  Auth state: {display_hermes_home()}/auth/google_oauth.json")
    print(f"  Config updated: {config_path} (model.provider=google-gemini-cli)")
