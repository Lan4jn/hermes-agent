# Google Gemini CLI OAuth Custom Endpoints Design

Date: 2026-08-22
Status: Approved design

## Objective

Allow the `google-gemini-cli` provider to route every Google OAuth and Code
Assist request through explicitly configured reverse-proxy endpoints while
preserving the current Google-hosted defaults.

## Configuration Contract

Behavioral endpoint settings live in `config.yaml`, not `.env`:

```yaml
providers:
  google-gemini-cli:
    oauth_authorize_url: https://proxy.example.com/oauth/authorize
    oauth_token_url: https://proxy.example.com/oauth/token
    oauth_userinfo_url: https://proxy.example.com/oauth/userinfo
    code_assist_base_url: https://proxy.example.com/codeassist
```

All fields are optional. Each omitted field uses its current official default:

- `https://accounts.google.com/o/oauth2/v2/auth`
- `https://oauth2.googleapis.com/token`
- `https://www.googleapis.com/oauth2/v1/userinfo`
- `https://cloudcode-pa.googleapis.com`

Client ID, client secret, and other credentials remain secret configuration and
continue to use the existing credential sources.

## Endpoint Resolution

A small immutable endpoint object is the single resolver output. It is resolved
from the active profile's config for each login/runtime construction boundary,
so multiplexed profiles cannot leak endpoint choices into one another.

Resolution rules:

1. Read `providers.google-gemini-cli` from the active profile.
2. Validate configured URL fields independently.
3. Use the official default for every omitted field.
4. Normalize only trailing slashes; do not invent paths for separately
   configured endpoints.
5. Reject URL userinfo, query strings, and fragments.
6. Require HTTPS, except HTTP on `localhost`, `127.0.0.1`, or `::1`.

Invalid custom configuration fails with a clear provider configuration error;
it never silently falls back to an official URL.

## Request Propagation

The resolved endpoints must reach every relevant request path:

- Browser authorization URL.
- Authorization-code exchange.
- Refresh-token exchange.
- Userinfo email lookup.
- Code Assist `loadCodeAssist` discovery.
- Code Assist onboarding and long-running-operation polling.
- User quota retrieval.
- Non-streaming `generateContent`.
- Streaming `streamGenerateContent`.

Code Assist helpers accept an explicit base URL rather than reading mutable
module globals. `GeminiCloudCodeClient` stores its resolved Code Assist base and
passes it into project discovery. A custom Code Assist base disables direct
Google fallback endpoints so a configured proxy is not bypassed.

The marker `cloudcode-pa://google` remains an internal provider-routing marker,
not a network endpoint. Runtime credential resolution returns the configured
Code Assist base separately to client construction.

## Authentication Lifecycle

`hermes auth add google-gemini-cli --type oauth` continues to force a new OAuth
login and overwrites the stored Google grant after a successful exchange.

`hermes auth logout google-gemini-cli` must clear both:

- Hermes provider/auth-pool state.
- The real profile-local `auth/google_oauth.json` credential file.

Logout remains idempotent. A failed OAuth login does not delete the previously
working credential until a replacement grant has been successfully persisted.

## Interactive Model Flow

The existing `hermes model` flow owns the interactive configuration entry. The
new prompts appear only after the user selects `google-gemini-cli`; every other
provider follows its existing branch byte-for-byte.

The flow is:

1. Ask whether to use `Google official endpoints` or `Custom reverse proxy`.
2. Official mode removes only these four keys from
   `providers.google-gemini-cli`:
   `oauth_authorize_url`, `oauth_token_url`, `oauth_userinfo_url`, and
   `code_assist_base_url`.
3. Custom mode asks for one HTTPS origin, for example
   `https://server.sjser.ccwu.cc`.
4. The origin must not contain userinfo, a path other than `/`, query, fragment,
   whitespace, or control characters. HTTP is accepted only for loopback.
5. Derive and display the four final endpoints:

   - `<origin>/o/oauth2/v2/auth`
   - `<origin>/token`
   - `<origin>/oauth2/v1/userinfo`
   - `<origin>` for Code Assist

6. Require confirmation, persist the endpoint selection, and only then start
   the existing OAuth login and model picker.

Custom mode is all-or-nothing: all four derived fields are written together, so
no OAuth or Code Assist request silently returns to an official Google host.
Choosing official mode restores resolver defaults by deleting the override keys
rather than copying official URLs into user configuration.

If the profile already contains the exact unified-origin pattern, the prompt
uses that origin as its editable default. If it contains four independently
configured endpoints that cannot be represented by the unified pattern, the
flow explains that confirming a new origin will replace only those four Google
Gemini endpoint fields. Cancellation leaves configuration and credentials
unchanged.

Configuration writes preserve all unrelated mappings and comments. In
particular, the flow must not modify:

- Any provider other than `providers.google-gemini-cli`.
- Other keys under `providers.google-gemini-cli`.
- `model.provider` or `model.model` before OAuth and model selection succeed.
- API keys, fallback providers, auxiliary models, tools, platforms, or secrets.

## Security Boundaries

Custom OAuth/token endpoints receive sensitive OAuth material. The CLI and
documentation must state this when custom endpoints are configured.

The implementation must:

- Never log authorization codes, access tokens, refresh tokens, client secrets,
  or proxy credentials.
- Reject plaintext non-loopback endpoints.
- Reject embedded URL credentials.
- Avoid process-global endpoint mutation.
- Preserve profile-aware credential and config paths.
- Keep timeout and error-body bounds on all HTTP requests.

## Error Handling

- Configuration errors identify the invalid field without echoing credentials.
- OAuth and Code Assist HTTP errors retain their existing structured error codes.
- A custom Code Assist proxy failure is reported as a proxy request failure and
  does not retry against Google directly.
- Token refresh continues to preserve a rotated refresh token.

## Verification

Tests must prove:

- Official defaults remain byte-for-byte unchanged when no custom fields exist.
- Each of the four custom endpoints is independently honored.
- Authorization, code exchange, refresh, userinfo, discovery, onboarding,
  quota, generation, and streaming use the configured destinations.
- A custom Code Assist base never falls back to an official Google host.
- HTTPS and loopback HTTP pass; non-loopback HTTP, userinfo, query, fragment,
  malformed, and non-HTTP URLs fail.
- Two profile scopes resolve independent endpoint sets.
- `auth add` forces re-login and `auth logout` deletes the actual Google OAuth
  credential file.
- Existing Gemini API-key/native/custom-proxy provider behavior is unchanged.
- `hermes model` official/custom selection is available only for
  `google-gemini-cli`.
- A unified origin derives exactly the four documented paths and persists them
  without changing unrelated provider/model configuration.
- Official mode removes only the four endpoint override keys.
- Existing unified configuration is prefilled; independent endpoint config is
  not silently overwritten; cancellation performs no write.
- Invalid origins fail before config persistence or OAuth startup.

Run focused OAuth, Cloud Code, provider-routing, auth-command, and model-setup
tests, followed by the relevant regression suites and static checks.
