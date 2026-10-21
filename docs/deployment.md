# AgentOps — Development & Deployment Setup

This is the authoritative setup guide for the current codebase (M0 + M1).

- **Application database:** hosted **Supabase Postgres** through the transaction pooler.
- **Identity:** hosted **Supabase Auth**; the API verifies access tokens via JWKS.
- **Tests:** a **disposable local PostgreSQL 18** database, using the same SQL migrations.

Docker is optional and currently not installed on the development machine; see
[§9](#9-docker--supabase-local-stack-optional).

---

## 1. Prerequisites

| Component | Version | Purpose |
|---|---|---|
| Python | 3.12 | FastAPI service |
| Node.js | 20+ (24 used here) | Web app |
| Supabase CLI | 2.x | Migrations, local stack |
| PostgreSQL | 18 | Disposable test database + `psql` (the test harness needs `psql`) |
| Git | 2.40+ | Version control |
| Docker | optional | `supabase start`, Compose |

Verify the machine:

```powershell
.\scripts\verify_env.ps1
```

---

## 2. Hosted Supabase

### 2.1 Project values

From the Supabase dashboard (**Project Settings → API**):

| Value | Where it goes | Visibility |
|---|---|---|
| Project URL | `SUPABASE_URL`, `VITE_SUPABASE_URL` | public |
| Publishable key (`sb_publishable_…`) | `VITE_SUPABASE_PUBLISHABLE_KEY` | public |
| Database password | `DATABASE_URL`, CLI migrations | **secret** |
| Secret key / service role | not required in M1 | **secret** |
| Personal access token (scoped) | CI / `supabase` CLI login | **secret** |

Never put a secret value in `apps/web/.env`, and never prefix one with `VITE_`.

### 2.2 `backend/.env`

```dotenv
ENVIRONMENT=development
AUTH_MODE=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_JWT_AUDIENCE=authenticated

# Application traffic: transaction pooler (port 6543), session-independent.
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require

# Tests only: a disposable local database, never the hosted project.
TEST_DATABASE_URL=postgresql+psycopg://agentops@127.0.0.1:55432/agentops_test

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

The direct host `db.<project-ref>.supabase.co` is **IPv6-only** on this project; do not use it from
the application. Migrations use the session pooler on the same host at port **5432**.

> `backend/.env` is git-ignored. `.env.example` lists names only.

### 2.3 Apply the schema

```powershell
supabase db push `
  --db-url "postgresql://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres" `
  --include-all --yes --skip-vault
```

The password must be inline in `--db-url`. `--skip-vault` is required because the initial migration
does not use Supabase Vault.

Verify:

```sql
select table_name from information_schema.tables where table_schema = 'app' order by 1;
-- 7 rows: api_keys, audit_events, local_credentials, profiles,
--         workspace_members, workspace_preferences, workspaces

select relname, relrowsecurity
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'app' and c.relkind = 'r';
-- relrowsecurity = true for every row
```

`python -m pytest` applies the same migration to the test database automatically.

### 2.4 Auth settings

In **Authentication → Providers → Email**:

- **Confirm email** — enabled by default. Sign-up then returns no session until the address is
  confirmed, and the UI says so. For local development you may disable it in the dashboard (never
  disable confirmation in production).
- **Site URL / Redirect URLs** — add `http://localhost:5173` (and the deployed origin) so
  confirmation links return to the app.
- Built-in SMTP is rate-limited (a few messages per hour); repeated test sign-ups produce
  `over_email_send_rate_limit`. Use your own SMTP provider for real use.

### 2.5 `apps/web/.env`

```dotenv
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
# VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1   # only if not using the dev proxy
```

The dev server proxies `/api` to `http://127.0.0.1:8000`, so no base URL is needed locally.

---

## 3. Local test database (PostgreSQL 18)

The test suite applies the migrations with `psql` and truncates tables between tests. Use a
throwaway database — **never** the hosted project.

### 3.1 Option A — the project-local cluster on port 55432

A cluster lives in `.devdb/` (git-ignored), isolated from any system PostgreSQL service:

```powershell
# start
& "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" -D .devdb\data `
  -o '"-p 55432 -c listen_addresses=127.0.0.1"' -l .devdb\server.log start

# stop
& "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" -D .devdb\data stop
```

Create the role and databases once (superuser `agentops` on this cluster):

```powershell
$env:PGPASSWORD = '<local superuser password>'
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
& $psql -h 127.0.0.1 -p 55432 -U agentops -d postgres -c "create database agentops;"
& $psql -h 127.0.0.1 -p 55432 -U agentops -d postgres -c "create database agentops_test;"
```

`TEST_DATABASE_URL=postgresql+psycopg://agentops:<password>@127.0.0.1:55432/agentops_test`.

### 3.2 Option B — an existing PostgreSQL instance

Create `agentops_test`, point `TEST_DATABASE_URL` at it, and make sure `psql` is on `PATH` (or set
`PSQL_BIN`). pgvector is **not** required by the M1 migration.

### 3.3 How the tests use it

`backend/tests/conftest.py`:

1. Drops and recreates the `app` / `app_private` schemas (and the local `auth` shim).
2. Runs every `supabase/migrations/*.sql` file in order with `psql -v ON_ERROR_STOP=1`.
3. Truncates the known tables between tests.
4. Runs `supabase/tests/rls_policies.sql` for the RLS assertions.

If `psql` is missing, database tests **skip** with an explicit message; they never silently pass.

---

## 4. Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"

python -m app          # http://127.0.0.1:8000
```

- API docs: <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/health>
- Readiness: <http://127.0.0.1:8000/ready>

**Windows note:** `psycopg` async requires a selector event loop, while uvicorn hard-wires the
Proactor loop on Windows. `python -m app` passes `loop="app.loop:selector_loop_factory"`
automatically. With the CLI, use:

```powershell
uvicorn app.main:app --reload --port 8000 --loop app.loop:selector_loop_factory
```

Without it, requests can hang and `/ready` reports a degraded database.

---

## 5. Frontend

```powershell
cd apps\web
npm ci
npm run dev            # http://localhost:5173
```

The sign-in screen reads `GET /api/v1/auth/mode`:

- `supabase` → email/password through Supabase Auth (publishable key only).
- `local` → development issuer (`/auth/login`), only when the API runs with `AUTH_MODE=local`.

If the API says `supabase` and the bundle has no `VITE_SUPABASE_URL`/publishable key, the screen
shows a configuration error instead of falling back.

---

## 6. Tests and quality gates

```powershell
# backend
cd backend
python -m pytest -q
ruff check . ; ruff format --check . ; mypy app

# frontend
cd apps\web
npm run lint ; npm run typecheck ; npm run test ; npm run build
```

`npm run build` ends with `node scripts/check-bundle-secrets.mjs`, which fails the build if a
secret-shaped value, a Postgres URL or a server-only variable's value appears in `dist/`.

Test environment is pinned by `backend/tests/conftest.py` (`ENVIRONMENT=test`, `AUTH_MODE=local`);
the hosted project is never contacted.

---

## 7. CI

`.github/workflows/ci.yml` runs two jobs:

1. **backend** — Python 3.12, a PostgreSQL 17 service, `pip install -e ".[dev]"`, ruff, format
   check, mypy, pytest. The service database is the same scratch database used locally.
2. **web** — Node 22, `npm ci`, lint, typecheck, unit tests, production build + secret scan.

CI never calls a paid model provider and never receives the Supabase secret key.

---

## 8. Production deployment (checklist)

- Separate Supabase project for production; migrations applied with a scoped access token.
- `ENVIRONMENT=production`, `AUTH_MODE=supabase`, debug off.
- API behind TLS; `CORS_ORIGINS` limited to the real web origin.
- Secrets in the platform secret store, not in image layers or build args.
- Web bundle built with only `VITE_SUPABASE_URL` + publishable key.
- Health/readiness probes wired to `/health` and `/ready`.
- Backups/PITR enabled; restore drill documented.
- Key rotation rehearsed (`docs/supabase.md` §7.1).

Not yet automated: infrastructure-as-code, blue/green rollout, and metrics/tracing exporters.

---

## 9. Docker / Supabase local stack (optional)

Docker is not installed on the development machine, so these paths are **unverified**:

```powershell
supabase start        # local Postgres, Auth, Studio, Storage, Realtime
supabase db reset     # migrations + seed.sql
supabase status
supabase db lint      # needs Docker and a running local stack
```

`supabase/config.toml` is committed and ready. `docker compose up --build` describes the API + web
containers; it has not been executed locally.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `password authentication failed for user "postgres.<ref>"` | wrong DB password or wrong pooler user format | use `postgres.<project-ref>` and the current password; rotate if unknown |
| `could not translate host name "db.<ref>.supabase.co"` / connection timeout | direct host is IPv6-only | use the pooler host on 6543 (app) or 5432 (migrations) |
| `InvalidSqlStatementName` / prepared-statement errors | server-side prepares across pooled transactions | ensure `prepare_threshold=None` in the engine (already set) |
| `/ready` says `database: unavailable` | DB unreachable or event loop is Proactor | start with `python -m app`; check `DATABASE_URL` |
| `/ready` says `auth: unavailable` | JWKS unreachable or wrong `SUPABASE_URL` | check network and URL; the JWKS path is `/auth/v1/.well-known/jwks.json` |
| `401 AUTHENTICATION_REQUIRED` with a fresh token | wrong project, wrong audience, or clock skew | verify `SUPABASE_URL`/`SUPABASE_JWT_AUDIENCE`; check system clock |
| Sign-up returns 429 `over_email_send_rate_limit` | built-in SMTP quota | wait, or configure custom SMTP; this is not an API error |
| Sign-up succeeds but there is no session | email confirmation enabled | confirm the address, or disable confirmation for local development |
| Login screen shows “Supabase is not configured” | missing `VITE_*` values | create `apps/web/.env` and restart Vite |
| RLS tests skip | `psql` not found | install PostgreSQL client or set `PSQL_BIN` |
| `npm run build` fails in the secret scan | a server-only value leaked into the bundle | remove it from `VITE_*`; rotate the secret if it was real |
| `supabase db lint` fails to authenticate | CLI not logged in | `supabase login` with a scoped token (never a classic full-access PAT) |
| Local cluster will not start | stale `postmaster.pid` or port in use | stop the process, remove `.devdb/data/postmaster.pid`, retry |
