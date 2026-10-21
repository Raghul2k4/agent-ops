# AgentOps

**AI agent engineering, orchestration, observability, evaluation and governance platform.**

AgentOps lets a team design AI agents and visual workflows, execute them against approved tools
and models, inspect every execution trace, benchmark model quality, and govern what agents are
allowed to do.

> **Status: M0 + M1 delivered and verified.** Supabase Auth owns identity, Supabase Postgres is the
> system of record, and the FastAPI service verifies every Supabase access token against the
> project's JWKS. The remaining milestones (agents, workflows, runs, evaluations, knowledge) are
> tracked in [`docs/roadmap.md`](docs/roadmap.md) and [`PLAN.md`](PLAN.md).
>
> Nothing in this repository is mocked-up "success": a feature is listed only when its backend,
> persistence, authorization and tests exist and have been run. Hosted-Supabase verification is
> recorded in [`docs/supabase.md`](docs/supabase.md#8-verification-log).

---

## What it does

| Capability | Scope | Status |
|---|---|---|
| **Build** | Agents with versioned configuration; visual workflow canvas | Planned (M2/M4) |
| **Execute** | Custom runtime, registered tools, provider adapters (Ollama / OpenAI-compatible / Anthropic / labelled simulation) | Planned (M2) |
| **Observe** | Persistent run history, hierarchical traces, live updates, safe replay | Planned (M3) |
| **Evaluate** | Suites, deterministic scorers, regression gates | Planned (M6) |
| **Govern** | Workspace RBAC (delivered), tool allowlists, budgets, approvals, audit log | M1 delivers identity, workspaces, roles, audit |

---

## What M1 actually delivers

- **Identity** — Supabase Auth sign-up / sign-in in the browser with the **publishable** key only.
  The API accepts `Authorization: Bearer <access token>` and verifies it cryptographically against
  `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` (issuer, audience, expiry, subject).
- **Profiles** — the first authenticated request provisions `app.profiles` from the verified token
  subject. Authorization data is never read from `user_metadata`.
- **Workspaces** — create, rename, list, membership management, owner/admin/developer/operator/
  reviewer/viewer role matrix, per-workspace workspace-scoped authorization, audit events.
- **Database** — `supabase/migrations/20261021120000_initial_identity_schema.sql` is the single
  schema authority (Supabase CLI). Seven tables in the non-exposed `app` schema, RLS on every
  table, 20 policies, no grants to `anon` / `authenticated` / `service_role`.
- **Frontend** — Supabase session provider, bearer-token API client, email-confirmation state,
  explicit configuration error when the build has no Supabase project, bundle secret scan.
- **Tests** — 97 backend tests (unit + integration against a scratch Postgres, incl. RLS policy
  assertions) and 19 frontend unit tests; ruff, ruff-format, mypy, eslint, tsc and the production
  build all pass.

---

## Repository layout

```
agentops/
├── apps/web/                  React 19 + TypeScript + Vite + Tailwind + shadcn/ui
├── backend/                   FastAPI + SQLAlchemy 2 + psycopg 3 + Pydantic v2
│   ├── app/                   api/ auth/ core/ db/ models/ schemas/ services/
│   └── tests/                 unit/ integration/ (security, eval land with their milestones)
├── supabase/
│   ├── config.toml            local stack configuration
│   ├── migrations/            ★ schema authority: applied by `supabase db push`
│   └── tests/                 RLS/policy regression SQL run by the test suite
├── docs/                      architecture, supabase, security, schema, api, deployment, roadmap
├── evals/  infra/  scripts/   datasets, containers, setup scripts
└── docker-compose.yml  .env.example  PLAN.md  AGENTS.md
```

---

## Quick start (Windows, hosted Supabase)

```powershell
# 0. Prerequisites: Python 3.12, Node 22+, PostgreSQL 18 (for the test database),
#    Supabase CLI. Docker is optional (only for `supabase start`).

# 1. Backend dependencies
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. Configuration: copy the template and fill in backend/.env
#    (AUTH_MODE=supabase, SUPABASE_URL, DATABASE_URL via the transaction pooler)

# 3. Schema: apply the migration to the hosted project (session pooler, port 5432)
cd ..
supabase db push --db-url "postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"

# 4. Run the API (Windows: the selector loop is required by psycopg)
cd backend
python -m app                 # http://127.0.0.1:8000  (docs at /docs)

# 5. Browser configuration: apps/web/.env with VITE_SUPABASE_URL and the publishable key
cd ..\apps\web
npm ci
npm run dev                   # http://127.0.0.1:5173 (proxies /api to :8000)
```

`uvicorn app.main:app` also works on Linux/macOS. On Windows it needs
`--loop app.loop:selector_loop_factory`; `python -m app` passes that automatically.

The frontend reads the auth mode from `GET /api/v1/auth/mode`, so the API — not a build flag — is
the single source of truth. If the deployment says `supabase` but the bundle has no project
configured, the sign-in screen shows an explicit setup message; it never falls back to local
passwords.

---

## Tests

```powershell
# Backend (needs a scratch Postgres on 127.0.0.1:55432; see docs/deployment.md)
cd backend
python -m pytest -q
ruff check . ; ruff format --check . ; mypy app

# Frontend
cd apps\web
npm run lint ; npm run typecheck ; npm run test ; npm run build
```

The scratch database is separate from the hosted project: fixtures truncate it, and
`TEST_DATABASE_URL` is never pointed at Supabase.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/supabase.md`](docs/supabase.md) | Project layout, pooler, JWKS verification, RLS catalogue, storage/realtime/queue plan, env matrix, key rotation, verification log |
| [`docs/architecture.md`](docs/architecture.md) | Components, data flow, execution lifecycle, security boundaries |
| [`docs/database-schema.md`](docs/database-schema.md) | Tables, relationships, RLS policy per table, migration rules |
| [`docs/security.md`](docs/security.md) | Threat model, token verification, tenant isolation, secrets, key rotation |
| [`docs/api-reference.md`](docs/api-reference.md) | Implemented routes, error envelope, permissions |
| [`docs/deployment.md`](docs/deployment.md) | Supabase + local test database setup, troubleshooting |

---

## Known limitations (honest status)

- **Email confirmation is enabled on the Supabase project.** Sign-up creates an identity but no
  session until the address is confirmed; the UI shows that state. Completing a real sign-in
  requires either access to the mailbox or disabling confirmation in the Supabase dashboard
  (Authentication → Providers → Email). No service/secret key is stored in this repository.
- **Docker is not installed on the development machine**, so `supabase start` and the Compose path
  are unverified locally; the hosted project is the development target.
- **`supabase db lint` / advisors** need an authenticated Supabase CLI session (scoped access
  token); they were not run. The RLS assertions in `supabase/tests/rls_policies.sql` do run in the
  backend test suite against local Postgres.
- **No model provider is configured yet** (M2). Nothing in M1 fabricates model output.
- The hosted project is in `ap-northeast-2`; API requests pay a cross-region round-trip per query.

---

## Principles

- Server-side enforcement of every permission, policy and budget — prompts are not a security boundary.
- Tenant isolation on every workspace-owned record, enforced in the API **and** in RLS.
- The Supabase secret key never reaches the browser, logs, traces or test fixtures.
- Honest states: unavailable providers, empty datasets and partial failures are shown as such.
- Simulation is a first-class but **explicitly labelled** mode; it is never mixed into live analytics.

---

## License

Internal project — all rights reserved.
