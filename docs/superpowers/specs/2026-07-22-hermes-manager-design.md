# Hermes Node Messaging Parity and Fleet Manager Design

Date: 2026-07-22
Status: Approved design

## 1. Objective

Deliver two coordinated capabilities:

1. Bring Hermes node messaging to functional parity with PicoClaw's `/message`
   workflow, excluding PicoClaw's WebUI proxy.
2. Build a standalone Hermes Manager that can remotely operate multiple Hermes
   hosts from one browser-based console.

The manager must support both directly reachable nodes and nodes that can only
make outbound connections. The first release uses one administrator account and
provides status, chat, command execution, sessions, logs, configuration, and
Gateway start/stop/restart controls.

## 2. Scope

### 2.1 Included

- `/message` request and response compatibility with PicoClaw.
- A model-visible node messaging tool that supports configured peers and
  arbitrary HTTP(S) targets.
- Message, command, API key, and short-lived exec-token workflows.
- Optional shared node-message memory notes.
- A standalone FastAPI + React + SQLite manager application.
- A node-side Manager Connector that runs independently of the Gateway.
- Direct HTTPS management and outbound WSS management through one logical
  transport interface.
- Single-administrator authentication, per-node credentials, capability-scoped
  authorization, encrypted secret storage, and immutable audit events.
- Windows background-service and Linux systemd operation.

### 2.2 Not included

- PicoClaw's `/api/message/proxy` WebUI helper.
- Multi-user RBAC in the first release.
- A general remote file browser or unrestricted file-management API.
- Automatic Hermes software upgrades or fleet-wide rolling deployments.
- Replacing the existing single-node Hermes Dashboard.
- Making management features part of the permanent core model-tool schema.

## 3. Design Principles

- Preserve Hermes prompt caching. Node-message notes never rebuild or mutate the
  system prompt of an active conversation.
- Keep the core narrow. The Connector is a CLI-managed service, not a model
  tool. The node-message tool is service-gated and appears only when node
  messaging is configured.
- Keep nodes authoritative for sessions, logs, configuration, and runtime
  state. The manager caches only summaries and recent status.
- Separate chat credentials from host-control credentials.
- Reuse existing Hermes service-manager, configuration, logging, session, and
  API-server logic through shared service functions rather than duplicating
  shell behavior.
- Use capability discovery and protocol version negotiation so old nodes remain
  partially manageable.

## 4. High-Level Architecture

### 4.1 Hermes Manager

The manager is a standalone program in the Hermes monorepo with its own deploy
artifact. It contains:

- React administration console.
- FastAPI control API and authentication layer.
- Node registry and transport router.
- Direct HTTPS client.
- Outbound WebSocket connection hub.
- Operation scheduler and event stream.
- SQLite persistence for nodes, encrypted credentials, operation metadata,
  administrator state, and audit records.

The built frontend is embedded into the backend package so the application can
be started with one command on Windows or Linux. A container image may be
provided, but the native cross-platform command is the primary deployment.

### 4.2 Manager Connector

Each managed host runs an optional `Hermes Manager Connector` as a separate,
lightweight process. It does not run an LLM. It remains available while the
Gateway is stopped or restarting.

The Connector:

- Exposes the versioned direct-management HTTPS API when direct mode is enabled.
- Maintains a WSS connection to the manager when outbound mode is enabled.
- Reports host, Connector, Gateway, platform, version, and capability status.
- Proxies manager chat requests to the local Gateway `/message` endpoint.
- Calls shared Hermes service-manager functions for start/stop/restart.
- Reads logs through bounded, redacted log services.
- Reads and writes configuration through validated, revision-aware services.
- Executes authorized structured command operations through the existing Hermes
  terminal runtime.

CLI lifecycle commands:

```text
hermes manager-connector install
hermes manager-connector start
hermes manager-connector stop
hermes manager-connector restart
hermes manager-connector status
hermes manager-connector enroll <manager-url> <one-time-token>
```

`install` registers a Windows background service or a systemd user/system
service according to the existing Hermes service-management conventions.

### 4.3 Connection Modes

Both modes implement the same logical `NodeTransport` contract.

- Direct mode: Manager sends HTTPS requests to a reachable Connector endpoint.
- Outbound mode: Connector opens a WSS connection to the Manager and receives
  allowlisted request envelopes over that connection.
- Hybrid mode: A node may configure both. The Manager selects the healthiest
  route and fails over without changing the feature-layer code.

Gateway shutdown does not close the management channel. The Manager can still
read Connector status and logs, then start the Gateway again.

## 5. `/message` Functional Parity

### 5.1 Wire Contract

Hermes keeps the existing endpoint:

```text
POST /message
```

Accepted JSON fields remain exactly:

```json
{
  "session_id": "remote",
  "sender_id": "node-a",
  "sender_display_name": "Node A",
  "message": "Hello",
  "command": "pwd",
  "api_key": "optional-key",
  "exec_token": "optional-token"
}
```

The response remains compatible with PicoClaw:

```json
{
  "session_id": "remote",
  "reply": "Hello",
  "exec_token": "optional-issued-token",
  "exec_token_expires_at": "2026-07-22T12:00:00Z",
  "command": {
    "requested": true,
    "authorized": true,
    "executed": true,
    "is_error": false,
    "output": "..."
  },
  "error": "optional-error"
}
```

Cross-project clients should use body `api_key` and `exec_token`, which are the
common denominator. Hermes may additionally accept Hermes-specific API-key and
exec-token headers, while preserving the existing bearer API-server key path.

### 5.2 Command Authorization

Hermes intentionally retains an additional safety gate:

```yaml
platforms:
  api_server:
    extra:
      message_api:
        allow_command_execution: false
```

A command executes only when both conditions hold:

1. `allow_command_execution` is enabled.
2. The request contains a valid API-server bearer key, message API key, or
   unexpired exec token.

A valid message API key may issue a short-lived exec token. Tokens remain
process-local and expire according to `token_ttl_seconds`.

### 5.3 Node Messaging Tool

The existing local work-in-progress `send_hermes_message` capability will be
reworked into one service-gated node-messaging tool rather than adding duplicate
tools. Its schema supports:

- `base_url`: arbitrary target base URL; `/message` is appended safely.
- `peer`: optional configured peer alias instead of a URL.
- `session_id`, `sender_id`, and `sender_display_name`.
- `message`, `command`, `api_key`, and `exec_token`.
- A bounded timeout.

Exactly one of `base_url` or `peer` is required. The implementation validates
HTTP(S), strips query/fragment data, caps response bodies, pretty-prints JSON,
and returns HTTP status and structured remote errors. The system prompt lists
configured peers and instructs the model to use the tool instead of handwritten
HTTP.

### 5.4 Shared Node-Message Notes

Add:

```yaml
platforms:
  api_server:
    extra:
      message_api:
        shared_memory_notes_enabled: true
```

When enabled, a completed `/message` turn writes a sanitized, bounded note with
timestamp, session, sender, request summary, and response summary through the
Hermes memory-provider integration. The built-in implementation stores daily
node-message notes separately from the small `MEMORY.md` fact store. A bounded
recent-note context source is loaded only when a new agent context is created.
It never mutates an active conversation's cached prompt. Provider plugins are
notified through the existing memory-manager write hook.

## 6. Manager Protocol

### 6.1 Direct API

The Connector exposes a versioned, allowlisted surface under:

```text
/manager/v1
```

Initial resources:

- `GET /health`
- `GET /capabilities`
- `GET /status`
- `POST /message`
- `GET /sessions`
- `GET /sessions/{id}`
- `GET /logs`
- `GET /config`
- `PUT /config`
- `POST /service/start`
- `POST /service/stop`
- `POST /service/restart`
- `POST /operations/command`
- `GET /operations/{id}`
- `POST /operations/{id}/cancel`
- `GET /events` using SSE where direct streaming is available

The management surface does not expose arbitrary local paths or forward unknown
HTTP routes.

### 6.2 Outbound WebSocket

The outbound channel carries the same logical operations in envelopes:

```json
{
  "type": "request",
  "id": "request-uuid",
  "method": "POST",
  "path": "/manager/v1/service/restart",
  "body": {},
  "deadline": "2026-07-22T12:00:30Z"
}
```

Responses correlate by `id` and include `status`, `body`, and a structured
`error`. Separate `heartbeat`, `event`, and `operation_progress` envelopes carry
status and streaming updates. Unknown paths and unsupported capabilities are
rejected at the Connector.

### 6.3 Capabilities

Capabilities include protocol version and flags for:

- message API and command execution.
- sessions and session history.
- logs and log streaming.
- configuration read/write.
- service start/stop/restart.
- command operations and cancellation.
- direct transport and outbound transport.
- Windows or Linux service backend.

The Manager renders only supported controls.

## 7. Authentication and Authorization

### 7.1 Manager Administrator

- The first-run flow creates one administrator account.
- Passwords are hashed with Argon2id.
- Browser authentication uses secure, HTTP-only, same-site cookies.
- State-changing browser requests use CSRF protection.
- Non-loopback production deployments require HTTPS directly or through a
  trusted reverse proxy.

### 7.2 Node Enrollment

- The Manager creates a short-lived, single-use enrollment token.
- The Connector generates a stable node identity key pair locally.
- Enrollment binds the node public identity, returns manager trust material,
  and provisions independent direct/outbound credentials as needed.
- Revoking one node invalidates only that node.
- Credentials are never shared between nodes.

### 7.3 Permission Scopes

Initial scopes:

```text
status:read
message:send
sessions:read
logs:read
config:read
config:write
command:execute
service:start
service:stop
service:restart
```

The Connector validates scopes again before execution. `/message` credentials
cannot implicitly authorize configuration or service operations.

### 7.4 Secret Storage and Audit

- Manager-held node credentials are encrypted at rest with a generated master
  key protected by OS file permissions or an OS credential store where
  available.
- Connector private identity material never leaves the node.
- Logs and audit payloads pass through existing Hermes secret redaction.
- Audit events record administrator, node, operation, timestamp, request ID,
  result, and error category without recording secret values.

## 8. Configuration and Service Operations

### 8.1 Configuration Updates

The update sequence is:

1. Read current configuration and revision.
2. Submit the proposed document with the expected revision.
3. Validate YAML and the Hermes configuration schema.
4. Reject stale revisions with `409 conflict`.
5. Write a timestamped backup.
6. Write the new file atomically.
7. Optionally restart the Gateway.
8. Wait for health recovery.
9. If requested and health recovery fails, restore the backup and start the
   Gateway with the previous configuration.

The response includes old revision, new revision, backup identifier, restart
operation ID, and rollback result.

### 8.2 Long-Running Operations

Commands, service transitions, and configuration-triggered restarts create an
`operation_id`. Operation state is durable in the Manager and includes:

```text
queued -> dispatched -> running -> succeeded | failed | cancelled | timed_out
```

Every request also has an idempotency key. Replayed write requests return the
existing operation instead of executing twice.

## 9. Manager Data Model

SQLite tables are conceptually grouped as:

- `admins`: administrator identity and password hash metadata.
- `nodes`: stable identity, display name, connection preference, endpoint,
  platform, version, capabilities, and last-seen state.
- `node_credentials`: encrypted direct and outbound credentials.
- `node_connections`: current route, connection instance, latency, and health.
- `operations`: requested action, state, timestamps, result summary, and error.
- `audit_events`: append-only security and operation records.
- `manager_settings`: manager-level configuration.
- `message_sessions`: manager-initiated node-message session mappings and exec
  token metadata; tokens are encrypted.

Remote sessions, complete logs, and full node configuration are fetched on
demand and remain authoritative on each node.

## 10. User Interface

The approved layout uses:

- A persistent left node sidebar with health indicators and fast switching.
- A central single-node workspace.
- A right live-event and operation panel.

Node workspace tabs:

- Overview: Connector, Gateway, platforms, version, active agents, latency.
- Chat: `/message` conversations and exec-token state.
- Sessions: remote session list and transcript detail.
- Logs: bounded tail, filters, follow mode, download of an explicitly selected
  redacted range.
- Config: structured editor plus raw YAML, revision warning, validation,
  backup, restart, and rollback controls.
- Terminal: structured command operations, streaming output, cancellation.
- Service: start, stop, restart, status, and recent service-operation history.

High-risk operations require an explicit confirmation dialog that names the
target node and action.

## 11. Failure Handling

- Node health states are `online`, `degraded`,
  `connector_online_gateway_down`, and `offline`.
- Outbound connections reconnect with exponential backoff and jitter.
- Direct requests have explicit connect, response, and operation deadlines.
- Read-only calls may retry automatically. Write operations use idempotency
  keys and are not blindly replayed.
- Command and log streams have size, duration, and line-rate limits.
- A disconnected operation becomes `unknown` until the Connector reconnects
  and reports its final state; it is not automatically marked failed.
- Configuration conflicts return `409` and preserve both local and proposed
  revisions.
- Unsupported protocol versions or capabilities produce structured errors and
  leave unrelated features available.
- Gateway-down status does not mark the Connector or host offline.

## 12. Verification Strategy

### 12.1 Unit Tests

- `/message` parsing, response shape, key/token authorization, URL
  normalization, body limits, and memory-note gating.
- Enrollment, authentication, permission scopes, idempotency, and audit
  redaction.
- Config revision checks, schema validation, backup, atomic write, rollback.
- Operation state transitions and capability filtering.

### 12.2 Integration Tests

Use a temporary `HERMES_HOME` and real imports/services instead of only mocked
helpers. Cover:

- Manager to directly connected Connector.
- Manager to outbound WSS Connector.
- Route failover for a hybrid node.
- Connector proxy to a real local API-server adapter.
- Gateway stopped while Connector remains reachable, followed by remote start.
- Session and log reads against real temporary state.
- Configuration update followed by real reload/restart behavior.

### 12.3 Cross-Project Compatibility

Run protocol tests against both the Hermes implementation and PicoClaw's
`/message` handler/tool contract. Verify normal messages, key-to-token issuance,
token reuse, authorized commands, unauthorized commands, mixed message+command
responses, and error bodies.

### 12.4 Platform E2E

- Windows: hidden background service, no command window popups, automatic
  startup, Gateway restart, reconnect after reboot.
- Linux: systemd installation, service start/stop/restart, reconnect, and
  Gateway recovery.
- Browser: login, node switching, chat, logs, config conflict, rollback,
  command cancellation, and service controls.

## 13. Implementation Boundaries

Implementation should proceed in dependency order:

1. Finalize `/message` parity and tests.
2. Extract reusable config/log/service/session management services.
3. Implement the Connector and its direct API.
4. Implement outbound WSS transport and enrollment.
5. Implement Manager backend, persistence, operations, and audit.
6. Implement the approved React management console.
7. Add Windows/Linux service packaging and full E2E verification.

The Message API remains independently usable without the Manager. The Manager
depends on the Connector contract, not on private Dashboard endpoints.
