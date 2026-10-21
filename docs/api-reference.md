# AgentOps — API Reference

**Base path:** `/api/v1` (configurable via `API_PREFIX`)
**Interactive docs:** `GET /docs` (OpenAPI), `GET /openapi.json`
**Status:** M0, M1 and M2 endpoints are live. Routes for workflows, approvals, evaluations,
knowledge, schedules and analytics are specified in `AGENTS.md` §25 and land with their milestones —
they are not stubs in the service today.

---

## 1. Conventions

### 1.1 Authentication

Every protected endpoint requires:

```http
Authorization: Bearer <access token>
```

- **Supabase mode (default):** the token is a Supabase Auth access token, verified against the
  project JWKS. Obtain it in the browser through `@supabase/supabase-js`.
- **Local mode (development only):** the token is issued by `POST /api/v1/auth/login` or
  `/register`. The API refuses to start with `AUTH_MODE=local` in staging/production.

There is no cookie session and no CSRF token. Identity comes only from the verified `sub` claim.

### 1.2 Response shape

Successful responses are JSON objects or arrays with the documented schema. Errors always use:

```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "You do not have permission to perform this action.",
    "retryable": false,
    "request_id": "b0b0c0de-..."
  }
}
```

`details` is optional and never contains secrets. `request_id` is echoed from
`X-Request-ID` when supplied (or generated) and is present in the server log line.

### 1.3 Status codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 202 | Accepted (asynchronous work; reserved) |
| 204 | No content |
| 400 / 422 | Request cannot be processed / validation failed |
| 401 | Missing or invalid credentials |
| 403 | Authenticated but not permitted (also `POLICY_VIOLATION`) |
| 404 | Not found, or not visible to this tenant |
| 409 | State or uniqueness conflict (`CONFLICT`, `RUN_CANCELLED`) |
| 429 | Rate limited or execution limit exceeded |
| 500 / 503 / 504 | Internal error / provider unavailable / provider timeout |

### 1.4 Pagination

List endpoints in M1 return bounded, unpaginated collections (a user's workspaces, a workspace's
members). Later resource collections adopt the cursor contract documented in `PLAN.md`; the API
does not silently truncate.

---

## 2. System

### `GET /health` — liveness

No authentication. Returns `200` while the process can serve requests. It does not touch the
database.

```json
{ "status": "ok", "name": "agentops", "environment": "development", "version": "0.1.0" }
```

### `GET /ready` — readiness

No authentication. Checks the database and the auth verifier.

```json
{ "status": "ready", "checks": { "database": "ok", "auth": "ok" } }
```

| Case | Status |
|---|---|
| All dependencies reachable | `200 ready` |
| Database or JWKS unavailable | `503 not_ready` (dependency named in `checks`) |

Readiness never reveals connection strings, hosts or credentials.

---

## 3. Authentication mode

### `GET /api/v1/auth/mode`

No authentication. Tells the browser how to sign in; this is the single source of truth (the
browser never infers the mode from a build flag).

```json
{
  "auth_mode": "supabase",
  "local_sign_in_enabled": false,
  "supabase_url": "https://<project-ref>.supabase.co"
}
```

`local_sign_in_enabled` is `true` only for the development issuer. When the response says
`supabase` and the bundle has no project configured, the UI shows a setup error rather than
falling back.

### `POST /api/v1/auth/register` — development only

Returns `404`/`403` when the local issuer is disabled. Creates a profile and a local credential,
returns a token.

```json
{ "email": "dev@example.com", "password": "at-least-10-chars", "display_name": "Dev User" }
```

`201` → `AuthResponse` (`access_token`, `token_type`, `expires_at`, `user`, `workspaces`).

### `POST /api/v1/auth/login` — development only

```json
{ "email": "dev@example.com", "password": "at-least-10-chars" }
```

`200` → `AuthResponse`. Unknown email and wrong password return the same message
(`AUTHENTICATION_REQUIRED`); the endpoint never reveals whether an account exists. Rate-limited by
`AUTH_RATE_LIMIT_PER_MINUTE`.

### `POST /api/v1/auth/logout`

Authenticated. Appends an audit event and returns `204`. Access tokens are stateless and remain
valid until expiry; in Supabase mode the client also calls `supabase.auth.signOut()` to revoke the
refresh token.

---

## 4. Identity

### `GET /api/v1/me`

Authenticated. Returns the caller's profile (provisioned on first use from the verified token) and
their workspace memberships.

```json
{
  "user": {
    "id": "7d32…",
    "email": "user@example.com",
    "display_name": "User Name",
    "status": "active",
    "created_at": "2026-10-21T09:45:05Z"
  },
  "workspaces": [
    { "id": "336d…", "name": "Acme", "slug": "acme", "role": "owner", "member_count": 1 }
  ]
}
```

`user.id` always equals the verified token subject.

---

## 5. Workspaces

All workspace routes are tenant-scoped. A non-member receives `404`/`403`; the API never returns
another tenant's content.

### `GET /api/v1/workspaces`

Authenticated. Lists workspaces in which the caller has an **active** membership, with the caller's
role and the member count.

### `POST /api/v1/workspaces`

Authenticated. Creates a workspace owned by the caller and the matching `owner` membership in one
transaction, then writes an audit event.

```json
{ "name": "Acme Operations" }
```

`201` → `WorkspaceRead`. Slug is derived from the name and made unique.

### `GET /api/v1/workspaces/{workspace_id}`

Member-only. `200` → `WorkspaceRead`; `404` when the workspace does not exist or the caller is not
a member.

### `PATCH /api/v1/workspaces/{workspace_id}`

Requires `workspace.update` (owner or admin).

```json
{ "name": "Acme Ops", "settings": { "timezone": "Asia/Kolkata" } }
```

Ownership cannot be changed here; a dedicated audited transfer operation is planned. `settings` is
replaced, not deep-merged.

### `GET /api/v1/workspaces/{workspace_id}/members`

Member-only. Returns members with their profile fields.

```json
[
  {
    "id": "member-row-uuid",
    "user_id": "profile-uuid",
    "email": "user@example.com",
    "display_name": "User Name",
    "role": "owner",
    "status": "active",
    "created_at": "2026-10-21T09:45:07Z"
  }
]
```

### `POST /api/v1/workspaces/{workspace_id}/members`

Requires `workspace.manage_members` (owner or admin). Adds an **existing** user by email; there is
no email delivery in M1.

```json
{ "email": "colleague@example.com", "role": "developer" }
```

`201` → `MemberRead`. `404 RESOURCE_NOT_FOUND` when no profile has that email (this avoids leaking
account existence across tenants); `409 CONFLICT` when already a member.

### `PATCH /api/v1/workspaces/{workspace_id}/members/{member_id}`

Requires `workspace.manage_members`.

```json
{ "role": "reviewer" }
```

The owner's role cannot be demoted through this endpoint; ownership transfer is a separate audited
operation. `204`-style success returns the updated `MemberRead`.

### `DELETE /api/v1/workspaces/{workspace_id}/members/{member_id}`

Requires `workspace.manage_members`. `204`. The owner cannot be removed; the workspace must be
deleted or ownership transferred first.

---

## 6. Permission matrix (enforced by these routes)

| Endpoint | Required permission | Roles |
|---|---|---|
| `GET /workspaces` | authenticated | any |
| `POST /workspaces` | `workspace.create` | any authenticated |
| `GET /workspaces/{id}` | active membership | viewer+ |
| `PATCH /workspaces/{id}` | `workspace.update` | owner, admin |
| `GET …/members` | active membership | viewer+ |
| `POST/PATCH/DELETE …/members` | `workspace.manage_members` | owner, admin |

The full role/permission catalogue is `backend/app/core/permissions.py`; the same data is
documented in [`security.md`](security.md#32-roles).

---

## 7. Agents, providers, tools and runs (M2)

All routes below take `workspace_id` as a query parameter and are tenant-scoped. A caller without an
active membership receives `404`; another tenant's identifiers are never revealed.

### 7.1 Agents — `/api/v1/agents`

| Route | Method | Permission | Purpose |
|---|---|---|---|
| `/templates` | GET | authenticated | Eight functional agent templates (key, name, category, system prompt, tool names, default parameters) |
| `?workspace_id=` | GET | `agent.read` | List the workspace's agents with their published version and draft state |
| `?workspace_id=` | POST | `agent.write` | Create an agent draft from a template or an explicit configuration |
| `/{agent_id}` | GET | `agent.read` | Agent with draft configuration, published version and version list |
| `/{agent_id}` | PATCH | `agent.write` | Update the **draft** (name, description, configuration, tools, limits) and optionally record a change note |
| `/{agent_id}` | DELETE | `agent.write` | Delete the agent and its versions |
| `/{agent_id}/archive` | POST | `agent.write` | Archive the agent without deleting history |
| `/{agent_id}/versions` | GET | `agent.read` | Immutable published versions, newest first |
| `/{agent_id}/publish` | POST | `agent.write` | Snapshot the draft into a new immutable version (`201`) |
| `/{agent_id}/rollback` | POST | `agent.write` | Point the agent at a previous published version |
| `/{agent_id}/duplicate` | POST | `agent.write` | Create a copy of the agent as a new draft |
| `/{agent_id}/run` | POST | `run.execute` | Start a run against a published version (`202`, asynchronous) |

Creating an agent:

```json
{
  "name": "Sales Operations Assistant",
  "description": "Finds stale high-value deals and drafts follow-ups.",
  "template_key": "sales_followup_drafter",
  "provider_id": "214bb5ad-…",
  "model_config_id": "f474e9b6-…"
}
```

Publishing snapshots `provider_id`, `model_config_id`, `model_name`, the system prompt, parameters,
limits and tool ids into `app.agent_versions`. Published versions are immutable (a database trigger
rejects updates) so a historical run stays interpretable.

Starting a run:

```json
{ "input": { "message": "Find deals worth more than INR 50,000 …" } }
```

The response is the persisted `RunRead` with `status: "queued"`. The runtime then executes in the
background and the client polls `GET /runs/{id}` (or consumes the SSE stream).

### 7.2 Providers and models — `/api/v1/models`

| Route | Method | Permission | Purpose |
|---|---|---|---|
| `/providers?workspace_id=` | GET | `provider.read` | Providers with their registered models |
| `/providers?workspace_id=` | POST | `provider.write` | Create a provider (`simulation`, `ollama`, `openai_compatible`, `anthropic`) |
| `/providers/simulation?workspace_id=` | POST | `provider.write` | Idempotently ensure the labelled deterministic provider and its model exist |
| `/providers/{provider_id}?workspace_id=` | GET | `provider.read` | One provider with models |
| `/providers/{provider_id}?workspace_id=` | PATCH | `provider.write` | Rename, change base URL or secret reference, enable/disable |
| `/providers/{provider_id}?workspace_id=` | DELETE | `provider.write` | Delete the provider |
| `/providers/{provider_id}/test?workspace_id=` | POST | `provider.write` | Health check against the live provider |
| `/providers/{provider_id}/models?workspace_id=` | POST | `provider.write` | Register a model with capability and pricing metadata |
| `?workspace_id=` | GET | `provider.read` | All registered models in the workspace |
| `/{model_id}?workspace_id=` | PATCH | `provider.write` | Update capabilities, pricing, default parameters, enabled/default flags |
| `/{model_id}?workspace_id=` | DELETE | `provider.write` | Delete a model registration |

Provider creation:

```json
{
  "provider_type": "openai_compatible",
  "display_name": "OpenRouter",
  "base_url": "https://openrouter.ai/api/v1",
  "secret_reference": "OPENROUTER_API_KEY"
}
```

`secret_reference` is the **name** of a server-side environment variable. The credential itself is
never accepted by the API, never stored in the database and never returned: responses carry
`secret_reference` and `has_secret_reference` only. The value is resolved from the process
environment when the provider is called.

Model registration:

```json
{
  "model_name": "dots-studio/dots-3-note-preview:free",
  "display_name": "Dots 3 Note Preview (free)",
  "capabilities": {
    "supports_tools": true,
    "supports_structured_output": true,
    "supports_streaming": false,
    "context_window": 512000
  },
  "pricing": { "input_per_million": 0, "output_per_million": 0 }
}
```

Capabilities are tri-state: `true`, `false` or `null` for **unknown**. The platform never asserts
that a model supports tool calling, structured output or streaming because it assumed so; an
unknown capability is displayed as unknown. Pricing is optional — when it is absent the run reports
the cost as unavailable, never as zero.

The connection test never raises on a provider failure. It returns the diagnostic instead:

```json
{
  "ok": false,
  "status": "error",
  "message": "The server-side environment variable AGENTOPS_LLM_API_KEY is not set.",
  "models": [],
  "checked_at": "2026-10-21T11:14:47Z"
}
```

### 7.3 Tools — `/api/v1/tools`

| Route | Method | Permission | Purpose |
|---|---|---|---|
| `?workspace_id=` | GET | `tool.read` | The server-side tool registry: name, version, description, input/output schema, risk level, required permissions, timeout, approval requirement |

Only tools registered in the server registry can execute. Model-proposed tool names and arguments
are resolved and validated against that registry; a tool that is not registered is rejected with
`INVALID_TOOL_ARGUMENTS`.

### 7.4 Runs and traces — `/api/v1/runs`

| Route | Method | Permission | Purpose |
|---|---|---|---|
| `?workspace_id=` | GET | `run.read` | Paginated run history (`items`, `total`, `limit`, `offset`) |
| `?workspace_id=` | POST | `run.execute` | Start a run for a published agent version |
| `/{run_id}` | GET | `run.read` | One run: status, usage, cost, error code, output |
| `/{run_id}/events?after_seq=` | GET | `run.read` | Ordered events with a cursor (`last_sequence`, `has_more`) |
| `/{run_id}/events/stream` | GET | `run.read` | Server-Sent Events for live updates; reconnects with `after_seq` |
| `/{run_id}/trace` | GET | `run.read` | Hierarchical trace spans (agent run, model call, tool call) |
| `/{run_id}/cancel` | POST | `run.cancel` | Cancel an in-flight run |

Run states: `queued` → `running` → `succeeded` | `failed` | `cancelled` | `awaiting_approval`.

A successful run reports the model's message and the accumulated usage:

```json
{
  "status": "succeeded",
  "token_usage": {
    "input_tokens": 3557,
    "output_tokens": 386,
    "total_tokens": 3943,
    "model_calls": 3,
    "tool_calls": 2
  },
  "estimated_cost": 0,
  "output": { "message": "**Customer: Ananya Das** …", "steps": 3 }
}
```

`tool_calls` counts executed tool calls; an approval-gated call is not counted because it never
executed. `estimated_cost` is `null` when the model has no pricing metadata.

A run stopped by a budget fails with `EXECUTION_LIMIT_EXCEEDED` **and reports the work it did**:

```json
{
  "status": "failed",
  "error_code": "EXECUTION_LIMIT_EXCEEDED",
  "error_summary": "The run reached its tool-call budget.",
  "output": {
    "message": null,
    "steps": 3,
    "stopped_because": "The run reached its tool-call budget.",
    "completed_actions": [
      { "tool": "search_deals", "risk_level": "low", "arguments": { … }, "output": { … } }
    ]
  }
}
```

An identical tool call repeated inside one run is executed once; the second occurrence emits a
`tool.cached` event and reuses the recorded result, so a model cannot duplicate a side effect.

### 7.5 Synthetic demonstration data — `/api/v1/workspaces/{workspace_id}/demo-data`

| Route | Method | Permission | Purpose |
|---|---|---|---|
| `GET` | GET | `workspace.read` | Report whether the demo dataset is seeded and its row counts |
| `POST` | POST | `workspace.update` | Seed the fictional CRM dataset (7 customers, 12 deals, 5 companies, 5 contacts) |

The dataset is fictional, carries `is_demo = true` and is only created by this explicit, audited
action. It is never injected into a real workspace implicitly.

---

## 8. Permission matrix (M2 additions)

| Endpoint | Required permission | Roles |
|---|---|---|
| `GET/POST /agents`, `GET /agents/{id}` | `agent.read` / `agent.write` | viewer+ / developer+ |
| `POST /agents/{id}/publish|rollback|duplicate|archive`, `PATCH|DELETE /agents/{id}` | `agent.write` | developer+ |
| `POST /agents/{id}/run`, `POST /runs`, `POST /runs/{id}/cancel` | `run.execute` / `run.cancel` | operator+ |
| `GET /runs`, `GET /runs/{id}`, events, trace | `run.read` | viewer+ |
| `GET /models/providers`, `GET /models` | `provider.read` | viewer+ |
| `POST|PATCH|DELETE /models…`, `POST /models/providers/{id}/test` | `provider.write` | developer+ |
| `GET /tools` | `tool.read` | viewer+ |
| `POST /workspaces/{id}/demo-data` | `workspace.update` | admin+ |

---

## 9. Error codes used in M2

`VALIDATION_ERROR`, `AUTHENTICATION_REQUIRED`, `PERMISSION_DENIED`, `RESOURCE_NOT_FOUND`,
`CONFLICT`, `RATE_LIMITED`, `POLICY_VIOLATION`, `INTERNAL_ERROR`, plus the execution codes
`PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `INVALID_TOOL_ARGUMENTS`, `TOOL_EXECUTION_FAILED`,
`EXECUTION_LIMIT_EXCEEDED`, `RUN_CANCELLED` and `APPROVAL_REQUIRED`.

---

## 10. Not implemented yet

`/workflows`, `/approvals`, `/evaluations`, `/knowledge`, `/schedules`, `/analytics`, `/api-keys` —
specified in `AGENTS.md` §25, delivered with milestones M3–M8. They are intentionally absent rather
than returning placeholder successes.
