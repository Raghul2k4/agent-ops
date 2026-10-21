# Supabase integration

AgentOps runs on **Supabase** as its application platform. The Python/FastAPI service remains the
only business-logic API and the React/TypeScript application remains the only UI.

This document is the operating contract for the hosted project: how schema changes are applied, how
tokens are verified, which Row Level Security policies exist, how secrets are handled, and what has
actually been verified.

---

## 1. Role boundary

| Concern | Owner | Implemented in M1 |
|---|---|---|
| Identity (sign-up, sign-in, refresh) | Supabase Auth | Yes — browser uses `@supabase/supabase-js` with the publishable key |
| Authoritative domain data | Supabase Postgres (`app` schema) | Yes — profiles, workspaces, memberships, API keys, audit |
| Row-level enforcement | Postgres RLS | Yes — enabled on every table, 20 policies |
| Object storage | Supabase Storage | Not yet (M6) |
| Live execution events | Supabase Realtime | Not yet (M3) |
| Durable jobs | Supabase Queues (`pgmq`) | Not yet (M7) |
| Schedules / outbound webhooks | `pg_cron` / `pg_net` | Not yet (M7) |
| Vector search | pgvector | Not yet (M6) |
| Business logic, orchestration, runtime | FastAPI | Yes (identity + workspaces) |

The Data API (PostgREST) is **not** a domain API. The `app` schema is not exposed, has no grants to
`anon`/`authenticated`/`service_role`, and default privileges are revoked.

---

## 2. Repository layout

```
supabase/
├── config.toml       # local stack configuration (ports, auth settings)
├── migrations/       # schema authority: *.sql applied by `supabase db push`
├── seed.sql          # reference/demo seed (applied by `supabase db reset`)
└── tests/            # RLS and policy regression SQL, executed by the backend test suite
```

The backend never calls `Base.metadata.create_all()`. ORM models declare the schema once
(`MetaData(schema="app")`) and are only used for queries.

---

## 3. Environments and connections

| Environment | Database | Identity |
|---|---|---|
| Local development (this machine) | Hosted project via the **transaction pooler**, port 6543 | Hosted Supabase Auth |
| Backend tests | Local PostgreSQL 18 on `127.0.0.1:55432`, database `agentops_test` | Local HS256 issuer (`AUTH_MODE=local`) |
| CI | A Postgres service container + the same SQL migrations | Local HS256 issuer |
| Future staging/production | Hosted project(s) | Supabase Auth |

### 3.1 Pooler, not the direct host

- The application uses the **transaction pooler**:
  `postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require`.
- The direct host `db.<ref>.supabase.co` is **IPv6-only** on this project and is not reachable from
  the development machine. Do not encode it in application configuration.
- Migrations use the **session pooler** on the same host at port **5432**, because DDL and the
  migration ledger want a session-scoped connection.

### 3.2 Driver settings

`backend/app/db/session.py` sets, on every pooled connection:

- `prepare_threshold=None` — the transaction pooler hands a connection to a different client
  between transactions, so server-side prepared statements cannot be reused. Disabling them avoids
  intermittent `InvalidSqlStatementName` errors and works identically against a direct connection.
- `statement_timeout` and `idle_in_transaction_session_timeout` from
  `DB_STATEMENT_TIMEOUT_MS` / `DB_IDLE_TX_TIMEOUT_MS`.
- `application_name=agentops-api` for Supabase Logs.

Model calls and other slow work must stay **outside** database transactions (spec §4A.3).

---

## 4. Schema and migration rules

1. `supabase/migrations/*.sql` is the **single schema authority**. There is no Alembic.
2. Every domain table lives in the `app` schema. `auth`, `storage` and `extensions` belong to
   Supabase.
3. Every migration that creates a table creates its indexes, constraints, RLS enablement and
   policies **in the same file**.
4. Extension installation never pins a version: `create extension vector with schema extensions`.
5. A new table is not mergeable until `supabase/tests/rls_policies.sql` covers it.

### 4.1 Local / CI compatibility shim

The migration begins with a guarded shim that runs **only when the objects are absent**:

- `auth.users` (FK target for `app.profiles`), `auth.uid()` and `auth.role()`.
- The `anon`, `authenticated` and `service_role` roles.

On the hosted project every one of those already exists, so the shim is a no-op. This is why the
same SQL file runs unchanged on Supabase and on a plain PostgreSQL test instance.

### 4.2 Applying a migration

```powershell
# Hosted (session pooler; inline password is required because --password is ignored with --db-url)
supabase db push `
  --db-url "postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres" `
  --include-all --yes --skip-vault

# Local stack, once Docker is available
supabase db reset
```

The CLI records applied versions in `supabase_migrations.schema_migrations`.

Applied migrations to date:

| Migration | Contents |
|---|---|
| `20261021120000_initial_identity_schema.sql` | profiles, local credentials, workspaces, memberships, preferences, API keys, audit events + RLS |
| `20261021130000_agents_providers_tools_runtime.sql` | model providers and models, agents and immutable versions, tool definitions and bindings, synthetic CRM tables, agent runs, run events, trace spans, follow-up drafts + RLS |

---

## 5. Authentication

### 5.1 Browser

`apps/web/src/lib/supabase.ts` creates a single client from `VITE_SUPABASE_URL` and
`VITE_SUPABASE_PUBLISHABLE_KEY`. The SDK persists the session, refreshes it automatically, and
handles the confirmation link (`detectSessionInUrl`, PKCE).

`GET /api/v1/auth/mode` is the single source of truth for the mode:

```json
{ "auth_mode": "supabase", "local_sign_in_enabled": false, "supabase_url": "https://<ref>.supabase.co" }
```

- `supabase` → Supabase gateway. If the bundle lacks the two `VITE_` values, the sign-in screen
  shows a configuration error. There is **no silent fallback** to local passwords.
- `local` → development gateway that calls `/auth/login` and stores the HS256 token. The API refuses
  to start with `AUTH_MODE=local` outside `development`/`test`.

The API client sends `Authorization: Bearer <token>` and `credentials: 'omit'`. No cookie and no
CSRF token are involved.

### 5.2 Server verification

`backend/app/auth/verify.py`:

1. Reads the `Authorization: Bearer` header (no header-derived identity, ever).
2. Fetches the project JWKS from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, caches it for
   `SUPABASE_JWKS_CACHE_SECONDS` (600), and re-fetches when an unknown `kid` appears (rotation).
3. Selects the key by `kid`, restricts algorithms to asymmetric ones (ES256/RS256/EdDSA), and
   verifies the signature, `iss`, `aud` (`authenticated` by default), `exp` and `sub`.
4. Returns typed `TokenClaims`; the identity key is `sub` (= `auth.users.id`).

Negative paths are tested: malformed tokens, tampered signatures, wrong audience, wrong issuer,
expired tokens, unknown `kid`, and an unreachable JWKS endpoint.

### 5.3 Profile provisioning

The first authenticated request inserts `app.profiles` from the verified claims (`sub`, `email`,
`display_name` from `raw_user_meta_data` when present). `app.profiles.id` references
`auth.users.id`, and a deleted identity cascades to its profile.

Authorization data is read from `app.workspace_members`, never from `user_metadata`.

---

## 6. Row Level Security catalogue

Every table has RLS enabled. Every policy targets `to authenticated` **and** carries a membership
predicate. `UPDATE` policies carry both `using` and `with check`.

Helper functions in `app_private` (non-exposed schema, owned by `postgres`, not granted to
`PUBLIC`):

| Function | Purpose |
|---|---|
| `app_private.is_workspace_member(uuid)` | active membership check |
| `app_private.is_workspace_admin(uuid)` | owner/admin check |
| `app_private.workspace_owner(uuid)` | owner check |

| Table | Policies | Rule |
|---|---|---|
| `app.profiles` | 3 | select self or a co-member; insert self; update self |
| `app.workspaces` | 4 | select/update/delete by member/admin/owner; insert by the creating user |
| `app.workspace_members` | 4 | select by members; insert/update/delete by admins; owner protected |
| `app.workspace_preferences` | 4 | own row only |
| `app.api_keys` | 4 | admin-only CRUD |
| `app.audit_events` | 1 | admin-only select; no update/delete policy (append-only) |
| `app.local_credentials` | 0 | development-only hashes; unreachable through any policy |

Grants: no `USAGE` on schema `app` for `anon`/`authenticated`/`service_role`, no table grants, and
default privileges revoked. The policies are defence in depth for the day a grant is accidentally
added — they are not the API's authorization mechanism.

`supabase/tests/rls_policies.sql` asserts all of the above and is executed by
`backend/tests/integration/test_rls_policies.py` (it also proves that an `authenticated` session
with `SELECT` granted on `app.local_credentials` still sees zero rows because no policy exists).

---

## 7. Secrets and keys

| Variable | Visibility | Notes |
|---|---|---|
| `SUPABASE_URL` | public | project URL |
| `VITE_SUPABASE_URL` | public | same value, browser |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | public | protected by RLS; safe in a bundle |
| `SUPABASE_JWT_AUDIENCE` | public | `authenticated` |
| `DATABASE_URL` | **server only** | pooler URL including the DB password |
| `SUPABASE_SECRET_KEY` | **server only** | not required by M1; never in the browser |
| `SUPABASE_DB_PASSWORD` | **server only** | CLI/CI migrations |
| `SUPABASE_DB_URL` / `SUPABASE_POOLER_URL` | **server only** | direct / pooled connection strings |
| `SUPABASE_ACCESS_TOKEN` | **CI only** | scoped personal access token |
| `OPENROUTER_API_KEY` | **server only** | example provider credential; referenced by name through a provider row's `secret_reference`, never stored in the database |

Rules:

- `backend/.env` and `apps/web/.env` are git-ignored; `.env.example` contains names only.
- `apps/web/scripts/check-bundle-secrets.mjs` runs as part of `npm run build`. It fails when a
  `sb_secret_…`/`sbp_…` value, a Postgres URL, or the value of a server-only environment variable
  appears in `dist/`. (Bare prefixes are allowed: `supabase-js` mentions them in key-format checks.)
- Logs never contain tokens, passwords or connection strings. `auth.token_rejected` records a
  reason, not the token.
- The API loads `.env` into the process environment at startup (`python-dotenv`), so a local
  credential referenced by `secret_reference` resolves the same way as a real environment variable.
  Real environment variables always win, and the file is ignored in production.
- A provider row stores only the **name** of the environment variable. Rotating a provider key is
  an environment change; no database row and no migration is involved.

### 7.1 Key rotation

1. **Publishable key** — create the replacement in the dashboard, update
   `VITE_SUPABASE_PUBLISHABLE_KEY`, rebuild and redeploy the web app. Old keys can be revoked after
   the new bundle is live.
2. **Secret key** — only server-side consumers are affected; update the secret store, restart the
   API, then revoke the old key.
3. **Database password** — reset in the dashboard, update `DATABASE_URL` for the API and the CLI
   password for migrations. Existing pooled connections fail and the pool reconnects
   (`pool_pre_ping`).
4. **Access token (CLI/CI)** — create a new **scoped** token, update the CI secret, revoke the old
   one. Never use a classic full-access token.
5. **JWT signing keys** — Supabase rotates keys and publishes both in JWKS; the verifier refreshes
   on an unknown `kid`, so no restart is required. Access tokens remain valid until they expire.

Deleting a user does not invalidate already-issued access tokens. Sensitive operations re-check
membership server-side (and RLS does too), and access tokens stay short-lived with automatic refresh.

---

## 8. Verification log

Performed on 2026-10-21 against `https://gflolifmzoadpnezjwtz.supabase.co` (region
`aws-0-ap-northeast-2`, PostgreSQL 17.11).

| Check | Result |
|---|---|
| JWKS endpoint | HTTP 200, one ES256 key, `kid=c1cd368a-5146-41e9-b379-8f813b732003` |
| Extensions available | `vector 0.8.2`, `pg_trgm 1.6`, `pgmq 1.5.1`, `pg_cron 1.6.4`, `pg_net 0.20.4` |
| Migration applied | `20261021120000_initial_identity_schema.sql` recorded in `supabase_migrations.schema_migrations` |
| Tables | 7 tables in `app`, RLS enabled on all 7 |
| Policies | 20, all `to authenticated`, `UPDATE` policies carry `with check` |
| `app_private` | 3 security-definer helpers, not granted to `PUBLIC` |
| Data API posture | no grants on schema `app` to `anon`/`authenticated`/`service_role` |
| API `/health` | `{"status":"ok",...}` |
| API `/ready` | `{"status":"ready","checks":{"database":"ok","auth":"ok"}}` |
| API `/api/v1/auth/mode` | `{"auth_mode":"supabase","local_sign_in_enabled":false,...}` |
| Real token | Signed by Supabase Auth (ES256, `kid` above), verified by the API through JWKS |
| `GET /api/v1/me` | 200; profile provisioned with `id = sub` |
| `POST /api/v1/workspaces` | 201; membership row with role `owner`; persisted |
| `GET /api/v1/workspaces/{id}/members` | 200; owner listed |
| Invalid token | 401 with the standard error envelope |
| Browser UI sign-in | Password sign-in through the real login form; profile and session restored after reload |
| Browser UI workspace | `Acme Sales Ops` created through the UI, listed after reload with 1 member and role `owner` |
| Browser UI sign-out | Redirected to `/login`; a deep link to a workspace while signed out also redirects to `/login` |
| UI defect found and fixed | `Button` with `asChild` rendered the loading icon plus the child, so Radix Slot rejected two children and the dashboard crashed; fixed and covered by `button.test.tsx` |
| Test data | Removed afterwards; `auth.users`, `app.*` row counts returned to 0 |

**How the real token was obtained.** The project has `mailer_autoconfirm: false` and no secret key
or personal access token was supplied, so the email-confirmation step could not be completed
through the UI. A confirmed test identity was bootstrapped with SQL (`auth.users` +
`auth.identities`, bcrypt password) and then authenticated through the real Supabase Auth password
grant. The resulting token was issued and signed by Supabase — no token was fabricated — and the
API verified it via JWKS. The identity was deleted after the test. This is an administrative test
bootstrap, not a product code path: the application never writes to `auth.*`.

### 8.1 M2 verification (2026-10-21)

| Check | Result |
|---|---|
| M2 migration applied | `20261021130000_agents_providers_tools_runtime.sql` applied to the hosted project and to the local test database |
| Tables | 13 additional tables in `app` (providers, models, agents, versions, tools, bindings, 4 CRM tables, runs, events, spans, drafts), RLS enabled on all |
| Published versions | `UPDATE` on `app.agent_versions` is rejected by trigger; a run's configuration stays interpretable |
| Runs and traces | `app.agent_runs`, `app.run_events` (monotonic `sequence_number`) and `app.trace_spans` persisted for the deterministic and the hosted-model runs |
| RLS regression | `supabase/tests/rls_policies.sql` passes on the hosted project with the M2 tables present |
| Provider credential | Stored only as the environment-variable name `OPENROUTER_API_KEY`; the value never reached the database, an API response, the logs or the browser bundle |
| Browser end-to-end | Workspace → provider → model → agent → publish → run → trace, exercised in a real browser against the hosted project |
| Retained demo data | The hosted project keeps one demonstration workspace (`AgentOps Demo`) with 3 agents, 5 runs, the synthetic CRM dataset and both providers, so the platform can be inspected without re-seeding. The demo identity is bootstrapped with SQL because the project requires email confirmation; **its password is not stored in this repository** |

---

## 9. Local stack

`supabase start` requires Docker, which is not installed on the development machine. The configuration
in `supabase/config.toml` is ready for it; until then the hosted project is the development target
and the native PostgreSQL 18 instance is the test database.

When Docker becomes available:

```powershell
supabase start
supabase db reset          # applies migrations + seed.sql
supabase status            # local API URL and keys
supabase db lint           # schema/policy lint
```

CI should run the same sequence and point the backend tests at the stack's database.

---

## 10. Not yet implemented

- Storage buckets, signed upload/download URLs and document ingestion (M6).
- Realtime channels and cursor-based event recovery (M3).
- `pgmq` workers, `pg_cron` schedules, `pg_net` webhooks (M7).
- pgvector embeddings and hybrid retrieval (M6).
- `supabase db lint` and the dashboard advisors in CI (needs an authenticated CLI session).
- MFA, password reset flows and account deletion in the UI.
