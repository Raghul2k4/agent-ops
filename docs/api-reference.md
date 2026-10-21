# AgentOps — API Reference

**Base path:** `/api/v1` (configurable via `API_PREFIX`)
**Interactive docs:** `GET /docs` (OpenAPI), `GET /openapi.json`
**Status:** M0 + M1 endpoints only. Routes for agents, workflows, runs, approvals, evaluations and
knowledge are specified in `AGENTS.md` §25 and land with their milestones — they are not stubs in
the service today.

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

## 7. Error codes used in M1

`VALIDATION_ERROR`, `AUTHENTICATION_REQUIRED`, `PERMISSION_DENIED`, `RESOURCE_NOT_FOUND`,
`CONFLICT`, `RATE_LIMITED`, `POLICY_VIOLATION`, `INTERNAL_ERROR`. The remaining codes in
`backend/app/core/errors.py` are reserved for execution, approvals, workflows and providers.

---

## 8. Not implemented yet

`/agents`, `/workflows`, `/runs`, `/approvals`, `/evaluations`, `/models`, `/tools`,
`/knowledge`, `/schedules`, `/analytics` — specified in `AGENTS.md` §25, delivered with milestones
M2–M8. They are intentionally absent rather than returning placeholder successes.
