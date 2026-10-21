# AgentOps — Security Model

**Scope:** M0 + M1 (identity, tenancy, secrets, platform posture). Execution-time controls
(tool authorization, approvals, budgets) are specified in `AGENTS.md` §11/§17/§26 and land with
their milestones; this document states which of them exist today and which do not.

**Rule of thumb:** the UI is never a security boundary, and a prompt is never a security boundary.
Every decision is re-made on the server from data the server controls.

---

## 1. Assets and trust boundaries

| Asset | Where it lives | Who may read it |
|---|---|---|
| Identity (passwords, session) | Supabase Auth (`auth.users`) | Supabase Auth only; the API stores no passwords in Supabase mode |
| Profile + workspaces | `app.*` in Supabase Postgres | The owning user and co-members, through the API |
| Workspace membership and roles | `app.workspace_members` | Workspace members (read), admins (write) |
| API keys | `app.api_keys` (SHA-256 hash only) | Workspace admins; plaintext shown once at creation |
| Audit trail | `app.audit_events` | Workspace admins (read); append-only |
| Server secrets | Environment / secret store | FastAPI process only |
| Browser config | `VITE_*` variables | Public by design |

Trust boundaries crossed on every request:

```
Browser ──(bearer token)──▶ FastAPI ──(SQL over TLS)──▶ Supabase Postgres (RLS)
                                  └──(HTTPS)──▶ Supabase JWKS  ──▶ signature + claims
```

The browser is untrusted. The token is untrusted until its **signature** is verified. A workspace
id in a URL or body is untrusted until membership is re-read from the database.

---

## 2. Authentication

### 2.1 Token acquisition

- The browser signs in with `@supabase/supabase-js` using the **publishable** key
  (`VITE_SUPABASE_PUBLISHABLE_KEY`). Passwords never reach the FastAPI service.
- The SDK stores and refreshes the session; the API client only reads the current access token.
- `GET /api/v1/auth/mode` tells the SPA how to authenticate. If the API reports `supabase` but the
  bundle has no project configured, the login screen shows a configuration error — there is **no
  fallback** to the development issuer.

### 2.2 Verification (server)

`backend/app/auth/verify.py`

| Check | Implementation |
|---|---|
| Algorithm | Allowlist: ES256, RS256, EdDSA. `none` and HMAC are rejected for Supabase tokens |
| Key | Selected by `kid` from the project JWKS, fetched over HTTPS and cached for 10 minutes; an unknown `kid` triggers a refresh (rotation) |
| Signature | Verified cryptographically with the project key |
| Issuer | Must equal `{SUPABASE_URL}/auth/v1` |
| Audience | Must equal `SUPABASE_JWT_AUDIENCE` (default `authenticated`) |
| Expiry | `exp` is required and enforced; `iat`/`nbf` are honoured when present |
| Subject | `sub` must be a UUID; it is the only identity key |

Failure returns `401 AUTHENTICATION_REQUIRED` with a generic message. The rejection reason is logged
(`auth.token_rejected`) without the token value.

**Not accepted:** an identity taken from `X-User-Id`, a query parameter, a body field, or an
unverified claim. There is no such code path.

### 2.3 Development issuer

`AUTH_MODE=local` issues HS256 tokens from `LOCAL_JWT_SECRET` for local development and tests.
The configuration validator **refuses to start** when `AUTH_MODE=local` and
`ENVIRONMENT` is `staging` or `production`. Tests pin `ENVIRONMENT=test` + `AUTH_MODE=local`; the
hosted project is never used by the test suite.

### 2.4 Session lifetime

Supabase access tokens are short-lived and refreshed by the SDK. Deleting a user does not revoke an
already-issued access token; therefore membership and resource authorization are re-checked on
every request (and by RLS), and sensitive operations do not rely on the token alone.

---

## 3. Authorization

### 3.1 Layers

1. **Authentication dependency** — resolves verified claims to a `Profile`, or `401`.
2. **Role/permission matrix** — `backend/app/core/permissions.py`, evaluated server-side.
3. **Resource scoping** — services resolve the workspace from the resource and verify the caller's
   membership before reading or writing.
4. **Row Level Security** — Postgres re-checks membership for direct database access.

Layer 4 exists because layers 1–3 are application code; it is a second, independent control, not a
replacement for them.

### 3.2 Roles

| Role | Summary |
|---|---|
| `owner` | Everything an admin has, plus workspace deletion |
| `admin` | Workspace settings, members, audit log, plus developer capabilities |
| `developer` | Agents, workflows, tools, providers, evaluations, knowledge writes |
| `operator` | Reviewer capabilities plus knowledge writes |
| `reviewer` | Execute/cancel runs, decide approvals, read everything |
| `viewer` | Read-only |

Permissions are additive per role (`ROLE_PERMISSIONS` in `core/permissions.py`). Every
authenticated user additionally carries `workspace.create` and `workspace.read` so they can create
their first workspace (`BASELINE_PERMISSIONS`).

### 3.3 Tenancy

- Every tenant-owned table has `workspace_id NOT NULL` with a foreign key and cascade behaviour.
- Services never trust a client-supplied workspace id: membership is resolved from
  `app.workspace_members` (status `active`) before the operation.
- Cross-workspace access is tested (`backend/tests/integration/`, RLS assertions in
  `supabase/tests/rls_policies.sql`).
- Errors do not reveal whether a resource exists in another workspace: a non-member receives
  `404 RESOURCE_NOT_FOUND` or `403 PERMISSION_DENIED` consistently, never content.

---

## 4. Row Level Security

Mandatory rules (verified in CI by the backend test suite):

1. RLS enabled on **every** table.
2. Policies target `to authenticated` explicitly; `auth.role()` is not used.
3. Every policy carries an ownership or membership predicate.
4. `UPDATE` policies have both `using` and `with check`.
5. Views use `with (security_invoker = true)`; helpers live in the non-exposed `app_private` schema.
6. `security definer` is used only for the three `app_private` helpers, which contain an explicit
   `auth.uid()` check and are not granted to `PUBLIC`.
7. Domain tables are not exposed: no grants to `anon`/`authenticated`/`service_role` on schema
   `app`, and default privileges revoked.

The full policy catalogue is in [`database-schema.md`](database-schema.md#5-row-level-security).

Because the API connects as the database owner, RLS is not what authorizes API traffic — the
service does. RLS protects against a future mistake such as exposing the Data API or granting a
role access to `app`.

---

## 5. Secrets

| Rule | Enforcement |
|---|---|
| No secrets in git | `backend/.env` and `apps/web/.env` are git-ignored; `.env.example` lists names only |
| No secrets in the browser | Only `VITE_SUPABASE_URL` and the publishable key are exposed; the secret key is never referenced in web code |
| No secrets in the bundle | `apps/web/scripts/check-bundle-secrets.mjs` fails `npm run build` on a secret-shaped value, a Postgres URL, or the value of a server-only variable |
| No secrets in logs | Structured logging records reasons, ids and counts — never tokens, passwords or connection strings |
| No secrets in errors | The error envelope contains a safe message, a stable code and optional non-sensitive details |
| No secrets in test fixtures | Tests use the local issuer and throwaway passwords; the hosted project is not used |

Key inventory, rotation and the environment matrix: [`supabase.md`](supabase.md#7-secrets-and-keys).

---

## 6. Error handling

Every failure crossing the API boundary uses one envelope:

```json
{ "error": { "code": "PERMISSION_DENIED", "message": "…", "retryable": false, "request_id": "…" } }
```

| Code | HTTP | Retryable | Notes |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | no | Pydantic detail is reduced to safe field messages |
| `AUTHENTICATION_REQUIRED` | 401 | no | Missing/invalid/expired token |
| `PERMISSION_DENIED` | 403 | no | Authenticated but not allowed |
| `RESOURCE_NOT_FOUND` | 404 | no | Also used to avoid cross-tenant existence leaks |
| `CONFLICT` | 409 | no | Uniqueness or state conflict |
| `RATE_LIMITED` | 429 | yes | Includes `Retry-After` |
| `POLICY_VIOLATION` | 403 | no | Alerts |
| `INTERNAL_ERROR` | 500 | no | Alerts; stack traces are never returned |

Unhandled exceptions are logged with a request id and converted to `INTERNAL_ERROR`. Database
driver messages are never echoed to the client.

---

## 7. Transport and browser posture

- HTTPS is terminated by the platform; the application assumes TLS and sets HSTS at the edge.
- Authentication uses a bearer token, not an ambient cookie, so cookie CSRF protections are not
  required. The API client sends `credentials: 'omit'`.
- CORS is an explicit allowlist (`CORS_ORIGINS`), not `*`, and credentials are disabled.
- The frontend never renders untrusted HTML; no `dangerouslySetInnerHTML` in the codebase.
- Tokens are kept in Supabase's storage (localStorage by default). This is acceptable for a
  bearer-token SPA; if a cookie session is ever introduced, CSRF protection, `HttpOnly`, `Secure`,
  `SameSite` and rotation become mandatory.

---

## 8. Logging and audit

- **Application logs** are structured JSON with request id, route, status and duration; secrets and
  payload bodies are excluded.
- **Audit events** are append-only rows in `app.audit_events` for security-relevant actions:
  workspace creation/update/deletion, membership changes, role changes, API key lifecycle.
- Audit rows are written with the acting profile and workspace; admins can read them through the
  API. There is no update or delete policy.

Planned with later milestones: tool execution attempts, approval decisions, policy violations,
provider configuration changes, emergency pause.

---

## 9. Not yet implemented (honest list)

| Control | Milestone |
|---|---|
| Tool allowlists, argument validation, risk policy | M2/M3 |
| Human approvals bound to a canonical argument hash | M3 |
| Execution budgets, step/time caps, cancellation | M3 |
| SSRF-safe generic HTTP connector | M7 |
| Upload validation, private buckets, signed URLs | M6 |
| API key authentication (schema exists, handshake not wired) | M8/P1 |
| MFA, password reset, account deletion UI | later |
| Rate limiting beyond the auth endpoints | later |
| `supabase db lint` + advisors in CI | needs an authenticated CLI session |

Nothing above is claimed as working in the UI. Screens that reference these capabilities are not
shipped yet.
