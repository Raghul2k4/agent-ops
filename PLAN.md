# AgentOps — Implementation Plan (Plan of Record)

**Status:** Active
**Owner:** Coding agent (per `AGENTS.md` §36)
**Last updated:** 2026-10-21
**Spec source:** `AGENTS.md` (2063 lines, sections 1–36) — this plan is the execution map for that specification.
**Platform decision:** **Supabase** is the data, identity, storage, realtime and scheduling platform
for AgentOps. The AI agent runtime stays in **Python + FastAPI**; the UI stays **React + TypeScript**.
**Supersedes:** the PostgreSQL-only / self-managed-auth variant of this plan.

**Reference convention:** `§N` refers to a section of the specification (`AGENTS.md`); `Plan §N`
refers to a section of this document.

---

## 0. Executive summary

`AGENTS.md` is a full product specification for **AgentOps**, an AI agent engineering platform
(build → execute → observe → evaluate → govern). The repository was **empty** apart from the
spec, so this plan covers greenfield initialization.

The plan is organised as **9 milestones (M0–M8)**, each ending with a vertical slice that is
runnable and testable, gated on the spec's *Definition of Done* (§33) and *Release Acceptance
Checklist* (§33). Nothing is marked complete because UI exists; every milestone carries explicit
verification commands.

**Platform shape (decided 2026-10-21):** AgentOps runs on **Supabase** as the application
platform — Supabase Postgres for the system of record, Supabase Auth for identity, Supabase
Storage for document artifacts, Supabase Realtime for live execution events, and Supabase Queues
(`pgmq`) + `pg_cron` for durable background work and schedules. **FastAPI remains the only
business-logic API**; the browser never talks to PostgREST for domain data, and Supabase Row
Level Security is applied as defence in depth beneath the API's own authorization.

---

## 1. Context

### 1.1 What the spec demands

| Spec section | Requirement summary | Priority |
|---|---|---|
| §1 | 20 mandatory engineering rules (inspect first, no mocks, no fabricated success, keep runnable) | Binding |
| §2–3 | Platform across Build / Execute / Observe / Evaluate / Govern; P0/P1/P2 scope | P0 first |
| §4 | Fixed stack: React+TS+Vite+Tailwind+shadcn+React Flow+TanStack Query+RHF/Zod+Recharts+Playwright; FastAPI+Pydantic+SQLAlchemy 2+PostgreSQL+HTTPX; Ollama + cloud adapters; pgvector; queues | Binding |
| §5 | Monorepo layout (`apps/web`, `backend/app/...`, `evals`, `docs`, `infra`, `scripts`) | Binding |
| §6–7 | Dark-first design system, semantic tokens, app shell, 11 nav areas, command palette | P0 |
| §8–23 | 16 feature modules (Dashboard, Agent Studio, Workflow Builder, Runtime/Tool Registry, Model Lab, Runs/Traces, Evaluations, Knowledge/RAG, Memory, Approvals/Governance, Integrations, Automation, Multi-Agent, Workspaces/ACL, Analytics, Developer Platform) | P0–P2 |
| §24 | 30+ named tables with explicit columns, tenant boundaries, indexes | Binding |
| §25 | Versioned REST API `/api/v1/...` with a named route list | Binding |
| §26–27 | Threat model: prompt injection, secret handling, tenant isolation, SSRF, upload safety; unified error taxonomy | Binding |
| §28–30 | Unit/integration/security/eval/frontend test layers; ≥30 synthetic eval cases; seeded demo workspace; **Sales Operations Assistant** end-to-end demo | P0 |
| §31–36 | Documentation set, phased delivery, definition of done, performance/a11y/ops, anti-patterns | Binding |

### 1.2 Environment audit (verified, not assumed)

| Component | Status | Evidence | Plan impact |
|---|---|---|---|
| Repository | Empty except `AGENTS.md` | `Get-ChildItem -Recurse` | Greenfield init required |
| Git | Installed `2.55.0`, **not a repo** | `git --version` | `git init` in M0 |
| Python | `3.14.7` (default), `3.12` also installed | `py -0p` | Build on 3.12 for wheel coverage; 3.14 fallback (Plan §2.2) |
| pip | `26.2.1` | `pip --version` | Optional `uv` accelerator |
| Node / npm | `24.20.0` / `11.19.0` | `node --version` | Vite 7 / React 19 compatible; Supabase JS requires Node ≥ 22 |
| **Supabase CLI** | **Installed `2.121.0`** | `supabase --version` | Migrations, lint, link, local stack, deploy all CLI-driven |
| **Docker** | **NOT INSTALLED** | `docker --version` → not recognized | `supabase start` (local stack) and `docker compose` **cannot run here**; a hosted Supabase project is required for local development until Docker exists |
| **PostgreSQL** | **18 x64 installed & RUNNING**, `127.0.0.1:5432` | service `postgresql-x64-18` | Useful as a throwaway Postgres for applying the same SQL migrations in backend integration tests; **not** the system of record |
| PG auth | `scram-sha-256` | `pg_hba.conf` | The system cluster's password is not needed: tests use the project-local cluster on `127.0.0.1:55432` (`.devdb/`, Plan §12 Q7) |
| **pgvector** | **NOT INSTALLED** in the local PG18 | `share/extension/vector.control` absent | Resolved on the target platform: Supabase Postgres ships `vector` (Plan §3.3) |
| Redis | Not installed | `Get-Service` | Replaced by Supabase Queues (`pgmq`) + `pg_cron` (Plan §2.3 D2/D3) |
| Ollama | Not installed | `Get-Command ollama` | Local-model path code-complete but unrunnable here; simulation provider keeps the demo honest |
| `make` | Not installed | `Get-Command make` | Cross-platform PowerShell/CLI scripts instead of Makefiles |
| Network | PyPI + npm reachable | `Invoke-WebRequest` → HTTP 200 | Dependency install works |
| Disk free | ~89 GB | `Get-PSDrive C` | Fine |

### 1.3 Gaps against the spec (what must be built)

Everything except the spec itself: 0/30+ tables, 0/50+ routes, 0 UI screens, 0 tools,
0 providers, 0 tests, 0 docs, 0 CI, 0 seed data — plus the Supabase project itself
(project ref, keys, migrations, RLS policies, buckets).

---

## 2. Technical decisions (locked at M0; ADRs in `docs/architecture.md`)

### 2.1 Runtime and framework

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI (async) + Pydantic v2 | Mandated; async suits concurrent tool calls and Realtime fan-out |
| ORM | SQLAlchemy 2.0 async + psycopg 3 (binary) | Mandated; psycopg3 has the best PG type coverage (`uuid`, `jsonb`, `vector`) |
| Migrations | **Supabase CLI SQL migrations** (`supabase/migrations/*.sql`) applied by `supabase db push` | Single schema authority for the platform; Alembic is **retired** to avoid two competing sources of truth (Plan §2.3 D6) |
| Database | **Supabase Postgres** via the Supavisor **transaction pooler** | Managed, backed up, with `vector`, `pgmq`, `pg_cron`, `pg_net` available |
| Schemas | `app` (domain), `auth` (Supabase-managed users), `storage` (Supabase-managed objects), `extensions` (extensions only) | Keeps domain tables out of the Data API surface entirely (Plan §3.2) |
| Identity | **Supabase Auth** (managed IdP); FastAPI verifies the signed access token | Satisfies §21 ("a suitable managed identity provider") without trusting client headers |
| Agent runtime | **Custom** (no LangChain/LlamaIndex) | Spec §4 mandates a custom runtime; full auditability of tool/permission enforcement |
| Provider abstraction | Own interface + adapters: `ollama`, `openai_compatible`, `anthropic`, `simulation` | Ollama local; `openai_compatible` also covers Groq/Together/vLLM/OpenRouter |
| Demo-mode provider | `simulation` — deterministic, **always labelled `SIMULATED`** | §29/§30 forbid fabricated success; simulation must be explicit, never mixed into live analytics |
| Object storage | **Supabase Storage** (private bucket) via signed upload/download URLs | Mandated abstraction now has a concrete implementation; no local disk blobs |
| Live updates | **Supabase Realtime** broadcast for run events; persisted `run_events` cursor for recovery | Removes the need for a separate Redis pub/sub tier |
| Background work | **Supabase Queues (`pgmq`)** + `pg_cron` schedules + `pg_net` webhooks | Durable, survives restarts, no extra infrastructure |
| Vector search | **pgvector** (`extensions.vector`) with HNSW index + hybrid keyword/vector retrieval | Available on the target platform; supersedes the earlier fallback |
| Frontend | React 19 + Vite 7 + TS strict + Tailwind v4 + shadcn/ui + TanStack Query v5 + Zustand + RHF/Zod + Recharts + `@xyflow/react` | Mandated stack, mutually compatible |
| Auth in the browser | `@supabase/supabase-js` v2 with the **publishable** key only | Publishable key + RLS is the safe client posture; secret key never ships to the browser |
| Authorization | FastAPI RBAC (role→permission matrix) **plus** RLS policies on every table | Application checks stay authoritative; RLS is the backstop if a query path slips |
| Workflow engine | Versioned JSON graph, validator + interpreter with persisted checkpoints | Durable enough without Temporal; upgrade path documented (Plan §2.3 D3) |

### 2.2 Python version policy

Build on **Python 3.12** (`py -3.12`) for the widest binary-wheel coverage of PDF/DOCX/embedding
parsing libraries; the repo pins `requires-python = ">=3.12,<3.14"`. Core stack has cp314 wheels,
so the decision is reversible; it is re-evaluated at M2 when document-parsing deps are introduced.

### 2.3 Deviations from the spec (spec §1: "choose the safer implementation and document the trade-off")

| # | Spec asks | Decision | Status |
|---|---|---|---|
| D1 | pgvector for vector search | **pgvector on Supabase Postgres** (`create extension vector with schema extensions`) + HNSW index; hybrid retrieval via `tsvector`/`pg_trgm` + reciprocal rank fusion | **Resolved** by the Supabase decision |
| D2 | Redis-backed queue and workers | **Supabase Queues (`pgmq`)** with `FOR UPDATE SKIP LOCKED` claiming; FastAPI workers poll | **Resolved** by the Supabase decision |
| D3 | Temporal for long-running workflows | Postgres-backed checkpoints + `pg_cron`/`pg_net`; interpreter unchanged so a Temporal activity wrapper can be added later | Partially resolved; upgrade path retained |
| D4 | Docker Compose local dev | Compose file authored and CI-verified; **local dev targets a hosted Supabase project** until Docker is available | Open (environment) |
| D5 | Ollama local model execution | Adapter fully implemented and unit-tested against a mocked transport; UI surfaces a clear "provider unreachable" diagnostic | Open (environment) |
| D6 | Alembic migrations | **Supabase CLI SQL migrations** are the single schema authority; the Alembic scaffold is retired and its DDL re-expressed as a Supabase migration | **New deviation**, created by the platform decision |
| D7 | Direct Data API (PostgREST) access | **Disabled.** Domain tables live in the non-exposed `app` schema, default privileges are revoked, and the Data API is switched off in project settings. The browser only talks to FastAPI for domain data | **New deviation**, created by the platform decision |
| D8 | Cloud LLM provider | `openai_compatible` + `anthropic` adapters implemented, connection-tested, disabled until a key is configured | Open (credentials) |

### 2.4 Non-negotiable engineering rules (carried from `AGENTS.md` §1, §35)

1. No fabricated results anywhere. Every metric derives from persisted rows.
2. No business logic in React components or route handlers — routers are thin, services own behaviour.
3. Every tenant-owned table carries `workspace_id`; every query is tenant-scoped by construction.
4. Tool names/arguments from a model are untrusted input, validated server-side.
5. Approval binds to a canonical argument hash; expiry/policy/version re-verified at execution time.
6. Playwright journeys are real E2E against a running stack; provider calls are mocked in CI.
7. Documentation updated in the same milestone as the code it describes.
8. **Supabase-specific:** the secret key never reaches the browser, every table has RLS, and no
   query bypasses the tenant boundary.

---

## 3. Supabase platform integration

### 3.1 Product boundary (what Supabase does and does not do)

| Concern | Owner | Rule |
|---|---|---|
| Identity (sign-up, sign-in, refresh, MFA, password reset) | **Supabase Auth** | The browser signs in with `@supabase/supabase-js`; FastAPI verifies the token |
| Authoritative domain data | **Supabase Postgres** (`app` schema) | FastAPI is the only writer; all reads are tenant-scoped |
| Row-level enforcement | **RLS policies on every table** | Defence in depth beneath the API's RBAC |
| Object storage (documents, artifacts) | **Supabase Storage** (private bucket) | Signed upload/download URLs; bucket policies mirror workspace membership |
| Live run events | **Supabase Realtime** (broadcast) | Events are persisted first, then broadcast; clients recover missed events via the cursor |
| Background jobs | **Supabase Queues (`pgmq`)** | Durable queue table; workers claim with `SKIP LOCKED` |
| Schedules / outbound webhooks | **`pg_cron` + `pg_net`** | Cron expressions and signed outbound HTTP |
| Vector search | **pgvector** (`extensions.vector`) | HNSW index; hybrid retrieval with full-text search |
| Business logic / orchestration | **FastAPI (Python)** | Never moved to Postgres functions, Edge Functions or the browser |
| Observability | Application JSON logs + **Supabase Logs** | Log Drains to the chosen sink; no secrets in logs |

**Explicitly out of scope for Supabase:** Edge Functions are *not* used for the agent runtime;
PostgREST is *not* used as a domain API; service-role SQL is *not* used to make authorization
decisions.

### 3.2 Schemas and Data API posture

| Schema | Contents | Data API exposure |
|---|---|---|
| `app` | All domain tables, views and functions | **Not exposed** — no grants to `anon`/`authenticated`; default privileges revoked |
| `auth` | Supabase-managed users and sessions | Managed by Supabase |
| `storage` | Supabase-managed objects | Managed by Supabase; bucket policies are ours |
| `extensions` | `vector`, `pg_trgm`, `pgmq`, `pg_cron`, `pg_net` | Extensions only, no tables |

Actions taken in the first migration (and asserted by CI):

```sql
create schema if not exists app;
create extension if not exists vector with schema extensions;
create extension if not exists pg_trgm with schema extensions;

-- Domain tables are not reachable through the Data API.
alter default privileges for role postgres in schema app
  revoke all on tables from anon, authenticated, service_role;
alter default privileges for role postgres in schema app
  revoke all on sequences from anon, authenticated, service_role;
alter default privileges for role postgres in schema app
  revoke execute on functions from public;
```

Project settings: **Data API disabled** (the product does not use PostgREST), Storage public
buckets **disabled**, email confirmations and password strength enforced by Supabase Auth.

### 3.3 Extensions

| Extension | Purpose | Notes |
|---|---|---|
| `vector` | Embeddings + similarity search | Column type `extensions.vector(<dim>)`; HNSW index `using hnsw (embedding vector_cosine_ops)`; dimension validated per embedding model |
| `pg_trgm` | Keyword/fuzzy matching for hybrid search | Paired with `tsvector` for the lexical half of hybrid retrieval |
| `pgmq` | Durable job queue (Supabase Queues) | Queue per job family; `pgmq.read_with_poll` + `SKIP LOCKED` claiming |
| `pg_cron` | Scheduled jobs (cron syntax, timezone-aware) | Schedules live in `app.schedules`; cron materialises them |
| `pg_net` | Outbound HTTP from Postgres | Used for webhook dispatch only, with signed payloads |

### 3.4 Authentication flow

```
Browser                     FastAPI                        Supabase
   │  supabase.auth.signInWithPassword()                     │
   ├────────────────────────────────────────────────────────►│
   │◄──────────────── access token (JWT) + refresh token ─────┤
   │
   │  Authorization: Bearer <access token>                   │
   ├─────────────────────────────►│                           │
   │                              │ verify signature via JWKS │
   │                              │ check iss/aud/exp/sub     │
   │                              │ resolve app.workspace_members
   │◄─────── 200 + data ─────────┤
```

- Tokens are verified **cryptographically** (JWKS at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`,
  cached briefly and purged on rotation). A shared-secret HS256 check against the Auth server is
  the documented fallback, never "trust the header".
- `sub` (the `auth.users.id`) is the identity key. Authorization data lives in
  `app.workspace_members` — **never** in `user_metadata` (user-editable) — and roles are read
  from `app_metadata` only for platform-level flags.
- Authorisation uses the **user's own token** where a query could be RLS-scoped, so the database
  enforces the same boundary as the API. The secret key is used only for privileged maintenance
  paths that cannot be expressed as a user-scoped query (queue administration, migrations).
- Because the API authenticates with a bearer token (not an ambient cookie), **CSRF protection is
  not required** for API calls. The locally-implemented cookie session + CSRF machinery from the
  M1 scaffold is **retired** in favour of Supabase Auth sessions.
- Deleting a Supabase user does not invalidate already-issued access tokens; sensitive operations
  therefore re-check membership server-side, and access tokens are short-lived with automatic
  refresh.

### 3.5 Row Level Security requirements (non-negotiable)

1. `alter table ... enable row level security;` on **every** table and view in `app`.
2. Policies target roles explicitly (`to authenticated`); `auth.role()` is not used (deprecated).
3. `to authenticated` **alone is not authorization** — every policy also carries an ownership or
   membership predicate, e.g.
   `workspace_id in (select workspace_id from app.workspace_members where user_id = (select auth.uid()) and status = 'active')`.
4. `UPDATE` policies carry both `using` and `with check`.
5. Views are created `with (security_invoker = true)`; helper functions are `security invoker`
   unless they live in a non-exposed schema, in which case they must contain an explicit
   `auth.uid()` check.
6. `security definer` functions are never created in an exposed schema and never used to "fix" a
   permission error.
7. Every migration that creates a table also creates its policies and grants **in the same file**.
8. `supabase db lint` and the RLS advisor run in CI and must be clean.

### 3.6 Storage

- Bucket `agentops-knowledge` — **private**, no public URLs, no public bucket listing.
- Uploads flow browser → Supabase Storage using a **signed upload URL** minted by FastAPI after a
  permission check; the backend records `storage_reference` in `app.documents`.
- Downloads use short-lived signed URLs minted after a workspace-membership check.
- Bucket size limits mirror `STORAGE_MAX_UPLOAD_MB`; file-type and content validation happen
  server-side **before** the document is accepted for ingestion.
- Storage upsert requires `insert` + `select` + `update` grants; policies are bound to workspace
  membership, not to a bare authenticated check.

### 3.7 Realtime and event streaming

- `app.run_events` remains the durable, ordered log (`(run_id, sequence_number)` unique).
- The runtime persists an event **first**, then broadcasts it on a Realtime channel `run:{run_id}`.
- The browser subscribes with the user's access token; Realtime authorization applies
  `realtime.messages` RLS, so only workspace members receive the event.
- On reconnect the client calls `GET /api/v1/runs/{run_id}/events?after_seq=N` to recover missed
  events. The cursor, not the socket, is the source of truth.

### 3.8 Queues, schedules and webhooks

- `pgmq` queue `agentops_jobs` carries durable job payloads (`job_type`, `resource_id`,
  `attempt_count`, `scheduled_at`).
- FastAPI workers poll with `FOR UPDATE SKIP LOCKED`, apply exponential backoff with jitter, and
  move exhausted jobs to a dead-letter queue. A lease/heartbeat prevents duplicate execution.
- `pg_cron` schedules are materialised from `app.schedules` (cron expression + timezone).
- Webhook triggers are dispatched through `pg_net` with an HMAC signature and a replay window.

### 3.9 Environments and credentials

| Variable | Visibility | Purpose |
|---|---|---|
| `SUPABASE_URL` | public | Project API URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | public (browser) | Client key for Auth/Storage/Realtime |
| `SUPABASE_PUBLISHABLE_KEY` | server | Same key for server-side client calls |
| `SUPABASE_SECRET_KEY` | **server only** | Privileged operations; never in the browser, never in logs |
| `SUPABASE_DB_URL` | **server only** | Direct Postgres connection (port 5432) for migrations and admin |
| `SUPABASE_POOLER_URL` | **server only** | Transaction pooler connection (port 6543) used by the app pool |
| `SUPABASE_DB_PASSWORD` | **server only** | Database password for CLI/CI |
| `SUPABASE_ACCESS_TOKEN` | **CI only** | Scoped personal access token for the CLI/MCP — never a classic full-access PAT |
| `SUPABASE_JWKS_URL` | public | Derived: `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` |
| `SUPABASE_PROJECT_REF` | public | Project reference for the CLI and pooler URLs |

Rules: legacy `anon`/`service_role` keys remain supported for compatibility but the publishable /
secret key pair is preferred; no key is committed; `.env.example` lists names only; CI uses
**scoped** access tokens; key rotation is documented in `docs/security.md`.

### 3.10 Local development

| Path | Requirement | Notes |
|---|---|---|
| Hosted project (primary here) | A Supabase project + its keys | Works without Docker; `supabase link`, `supabase db push`, `supabase db pull` |
| Local stack `supabase start` | **Docker** | Not available on this machine yet; preferred once Docker exists |
| Backend integration tests | A reachable Postgres | The same `supabase/migrations/*.sql` files are applied to a scratch database (hosted scratch DB, or the native PostgreSQL 18 instance) so schema drift is impossible |
| CI | GitHub Actions (Docker available) | `supabase start` → `supabase db reset` → run migrations → tests |

---

## 4. Target architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│ apps/web (React 19 + TS strict + Vite + Tailwind v4 + shadcn)            │
│  @supabase/supabase-js (publishable key only): Auth · Storage · Realtime │
│  features: dashboard agents workflows runs evaluations models knowledge    │
│            approvals integrations workspace analytics settings            │
│  server state: TanStack Query  |  client state: Zustand  |  forms: RHF+Zod│
└───────────▲──────────────────────────────────────────────────▲─────────────┘
            │ REST /api/v1 (Bearer Supabase access token)   │ Realtime
┌───────────┴──────────────────────────────────────────────┴──────────────┐
│ backend (FastAPI, async) — the only business-logic API                  │
│  api/v1/routers/*  → thin handlers + dependency injection                │
│  services/*        → all business logic (agents, runs, approvals, evals)  │
│  agents/runtime    → custom runtime: model loop → tool dispatch → policy  │
│  providers/*       → ollama | openai_compatible | anthropic | simulation  │
│  tools/registry    → typed schemas, risk levels, approval rules, limits   │
│  workflows/engine  → graph validator + interpreter + node executors       │
│  policies/*  approvals/*  evaluations/*  knowledge/*  jobs/*  observability│
│  auth/verify       → JWKS verification of the Supabase access token       │
└───────────▲──────────────────────────────────────────────────────────────┘
            │ SQLAlchemy async / psycopg3 over the Supabase transaction pooler
┌───────────┴──────────────────────────────────────────────────────────────┐
│ Supabase                                                                   │
│  Postgres: app schema (domain) · auth schema (users) · extensions schema  │
│    RLS on every table · pgvector + HNSW · pg_trgm hybrid search            │
│  Auth (managed IdP, JWT)   Storage (private buckets)   Realtime (broadcast)│
│  Queues (pgmq)             pg_cron (schedules)          pg_net (webhooks)   │
└───────────────────────────────────────────────────────────────────────────┘
```

**Layering rule (enforced by review + import-lint):**
`api → services → domain(core/agents/workflows/tools/policies) → repositories → db`.
Domain packages never import FastAPI; repositories never import services.

---

## 5. Repository layout (target)

```
agentops/
├─ apps/web/                     # React app
│  ├─ src/{app,components,features,hooks,lib,routes,schemas,styles,types}/
│  ├─ public/  tests/{unit,e2e}/  vite.config.ts  tsconfig.json
├─ backend/
│  ├─ pyproject.toml  .env.example
│  ├─ app/
│  │  ├─ api/v1/{routers,deps,error_handlers,response_models}
│  │  ├─ core/{config,security,errors,logging,types,permissions,ratelimit}
│  │  ├─ db/{base,session,types,seed}
│  │  ├─ models/            # SQLAlchemy ORM (one module per bounded area)
│  │  ├─ schemas/           # Pydantic v2 request/response models
│  │  ├─ repositories/      # tenant-scoped data access
│  │  ├─ services/          # business logic
│  │  ├─ agents/{runtime,prompts,context}
│  │  ├─ workflows/{schema,validation,engine,nodes}
│  │  ├─ tools/{registry,builtins,executor}
│  │  ├─ providers/{base,ollama,openai_compatible,anthropic,simulation}
│  │  ├─ evaluations/{harness,evaluators,benchmarks,gates}
│  │  ├─ knowledge/{ingestion,chunking,embeddings,retrieval}
│  │  ├─ policies/  approvals/  jobs/  observability/  auth/
│  │  └─ main.py
│  └─ tests/{unit,integration,security,eval,fixtures}/
├─ supabase/
│  ├─ config.toml              # project config (local stack, ports, auth)
│  ├─ migrations/              # ★ schema authority: *.sql, applied by `supabase db push`
│  ├─ seed.sql                 # reference/demo seed applied after `supabase db reset`
│  └─ tests/                   # RLS / policy regression SQL run in CI
├─ evals/{datasets,suites,reports}/
├─ docs/{architecture,database-schema,api-reference,security,design-system,deployment,roadmap,supabase}.md
├─ infra/{docker,nginx}/
├─ scripts/{bootstrap.ps1,verify_env.ps1,seed_demo.py,supabase_link.ps1}/
├─ .github/workflows/{ci.yml,release.yml}
├─ docker-compose.yml  .env.example  .gitignore
└─ README.md  AGENTS.md  PLAN.md
```

---

## 6. Data model plan (spec §24)

All domain tables live in the **`app`** schema. Every table: `uuid` PK (app-generated), UTC
`timestamptz`, `workspace_id NOT NULL` on tenant-owned tables, **RLS enabled**.

| Area | Tables (spec names) | Notable constraints / RLS |
|---|---|---|
| Identity | `auth.users` (Supabase-managed), `app.profiles`, `app.workspaces`, `app.workspace_members` | `app.profiles.id` = `auth.users.id`; unique `(workspace_id,user_id)`; workspace slug unique; role enum (owner/admin/developer/operator/reviewer/viewer) |
| Agents | `app.agents`, `app.agent_versions` | unique `(agent_id,version_number)`; `configuration_hash`; published versions immutable |
| Models | `app.model_providers`, `app.model_configs` | `secret_reference` only — no plaintext credentials in JSON; `capability_metadata` JSONB |
| Tools | `app.tool_definitions`, `app.agent_tools` | global built-ins have `workspace_id NULL` + `is_global`; unique `(workspace_id,name,version)` |
| Workflows | `app.workflow_definitions`, `app.workflow_versions` | unique `(workflow_id,version_number)`; `graph_hash` |
| Execution | `app.agent_runs`, `app.workflow_runs`, `app.run_events`, `app.trace_spans` | `run_events UNIQUE(run_id, sequence_number)`; `trace_spans(parent_span_id)`; index `(workspace_id,status,started_at)` |
| Approvals/Audit | `app.approval_requests`, `app.audit_events` | unique `(run_id,tool_definition_id,canonical_arguments_hash)` pending guard; audit append-only |
| Evaluation | `app.evaluation_suites`, `app.evaluation_cases`, `app.evaluation_results` | `evaluation_cases UNIQUE(suite_id,case_key)`; results carry agent_version + model_config |
| Knowledge/Memory | `app.knowledge_sources`, `app.documents`, `app.document_chunks`, `app.memory_records` | `documents.file_hash` unique per workspace; `document_chunks UNIQUE(document_id,chunk_index)`; `embedding extensions.vector(<dim>)` + HNSW index; `storage_reference` points at a Supabase Storage object |
| Automation | `app.schedules`, `app.webhook_endpoints`, `app.background_jobs` | `webhook_endpoints.secret_reference` (hashed); `background_jobs(workspace_id,status,scheduled_at)`; `pgmq` queue for job payloads |
| Platform | `app.sessions` (retired with the Supabase Auth cut-over), `app.api_keys`, `app.audit_events` | scoped API keys hashed; audit append-only |

Additions beyond the spec (documented, minimal): `app.profiles`, `app.api_keys`,
`app.notifications`, `app.workspace_invitations` — required by the §21/§23 auth and dev-platform
features.

**Tenancy pattern.** Every tenant table is reached through a repository that always filters on the
resolved `workspace_id`; RLS then applies the same rule at the row level using
`app.workspace_members`. Both layers must agree — a policy that is broader than the API check, or
narrower, is a bug.

---

## 7. API plan (spec §25)

Prefix `/api/v1`. Thin routers; typed responses; errors use the §27 taxonomy:
`{ "error": { "code": "...", "message": "...", "request_id": "...", "details": {...} } }`.

Authentication: `Authorization: Bearer <supabase access token>`. There is no cookie session and no
CSRF token on API calls. Scoped `app.api_keys` remain supported for machine access
(`Authorization: Bearer agoa_...`).

Router groups → spec endpoints:
`system` (health/ready/me) · `workspaces` (+members) · `dashboard` (summary/activity/usage/health)
· `agents` (+versions/publish/rollback/test) · `models` (providers/models/compare) ·
`tools` (+test) · `workflows` (+versions/validate/publish/run) · `runs` (+events/trace/cancel/replay)
· `approvals` (+decision) · `evaluations` (suites/results) · `knowledge` (sources/documents/search,
signed upload URLs) · `schedules` (+pause/resume) · `integrations` · `memory` · `analytics` ·
`webhooks` · `api-keys`.

Conventions: cursor pagination (`limit`/`cursor`), `Idempotency-Key` on all POST side effects,
`X-Request-ID` echoed, RBAC check on every handler, rate limits on auth/model/eval/run-create.
Supabase is **not** exposed as a second domain API: the Data API stays disabled.

---

## 8. Frontend plan (spec §6–7)

- **Supabase client:** a single `@supabase/supabase-js` instance created with
  `VITE_SUPABASE_URL` + `VITE_SUPABASE_PUBLISHABLE_KEY`, used for sign-in/out, session refresh,
  Realtime subscriptions and signed Storage URLs. The secret key is never referenced.
- **Shell:** collapsible dark sidebar (11 areas), compact header (workspace switcher, env selector,
  breadcrumb, search, command palette, notifications, help, profile), responsive to 390px.
- **Design tokens** in `styles/tokens.css`: `--background --foreground --surface --surface-elevated
  --surface-muted --border --primary --primary-foreground --secondary --success --warning --danger
  --muted --muted-foreground --focus-ring`; dark-first + light theme via `[data-theme]`.
- **Component library** in `components/ui` (shadcn-derived, locally owned): button, icon-button,
  input, textarea, select, combobox, form-field, card, metric-card, table+pagination, tabs, segmented
  control, badge, status-dot, tooltip, popover, dialog, dropdown, toast, command-palette,
  breadcrumb, empty-state, skeleton, error-boundary, code-viewer, json-viewer, trace-row,
  status-timeline, model-selector, provider-form, approval-card, workflow-node, date-range-filter.
- **States mandated everywhere:** loading / empty / no-results / success / API error / provider
  offline / permission denied / session expired / validation error / long-running / partial /
  cancelled.
- **Accessibility:** semantic HTML, visible focus, `aria-*` on dialogs/menus/palette, status never
  conveyed by colour alone, `prefers-reduced-motion` honoured, charts have text summaries.
- **Mock vs live:** a global `DataModeBanner` shows `SIMULATED` whenever the simulation provider or
  demo dataset is active; demo records carry `is_demo` and are excluded from live analytics unless
  explicitly requested.
- **Session handling:** Supabase Auth session is the single source of truth; the API client attaches
  the current access token and refreshes it on expiry; a 401 triggers a re-auth flow rather than a
  silent retry loop.

---

## 9. Security model (spec §26)

| Threat | Control | Verified by |
|---|---|---|
| Prompt injection (direct/indirect) | Tool authz outside the model; retrieved content wrapped as untrusted data; approval for writes; per-agent tool allowlist | `tests/security/test_prompt_injection.py` |
| Cross-tenant access | `workspace_id` scoping in every repository + RLS on every table + membership resolved server-side | `tests/security/test_tenant_isolation.py` + SQL policy tests |
| Privilege escalation | Role→permission matrix in `core/permissions.py`; tool `required_permissions` checked before execution; RLS membership predicates | `tests/security/test_privilege_escalation.py` |
| Forged/tampered approval | SHA-256 canonical-argument hash + expiry + policy version re-verified at execution; decision requires reviewer permission | `tests/security/test_approval_binding.py` |
| Secret leakage | Supabase secret key and DB password only in server env; publishable key is public by design; responses masked; redaction filter on logs/traces | `tests/security/test_secret_leakage.py` |
| JWT forgery | Signatures verified via JWKS; `iss`/`aud`/`exp` checked; shared-secret HS256 path calls the Auth server; no header-derived identity | `tests/security/test_jwt_verification.py` |
| RLS misconfiguration | `supabase db lint` + RLS advisor in CI; every table has policies; `to authenticated` never used alone; `with check` on updates | `supabase/tests/` policy regression SQL |
| Data API exposure | `app` schema not exposed, default privileges revoked, Data API disabled in project settings | CI assertion on grants |
| Storage exposure | Private buckets, signed URLs, membership-bound policies, size/type validation server-side | `tests/security/test_uploads.py` |
| Unsafe tool args | Strict Pydantic schemas, `extra="forbid"`, unknown tool name → typed error | unit + integration |
| SSRF | URL allowlist + DNS/IP validation + redirect re-validation + size/timeout caps | `tests/security/test_ssrf.py` |
| Runaway execution | `max_steps`, `max_wall_clock_ms`, `max_tool_calls`, `max_tokens`, `max_cost_usd`, per-tool rate limit, recursion guard | unit + integration |
| Audit | Append-only `app.audit_events` for auth, denial, provider change, tool attempt, approval, policy violation, publish, role change | integration |

---

## 10. Milestones

Each milestone ends with a **runnable vertical slice**, executed tests, and updated docs.
Status legend: `[ ]` todo · `[~]` in progress · `[x]` done & verified.

---

### M0 — Repository foundation & plan (spec Phase 0)

- [x] Audit repository (empty) and environment (audit table in Plan §1.2)
- [x] Extract spec requirements → this plan + `docs/roadmap.md` + `docs/architecture.md`
- [x] Lock architectural decisions (Plan §2) with fallbacks for missing infrastructure (Plan §2.3)
- [x] `git init`, `.gitignore`, `.editorconfig`, `.gitattributes`
- [x] `README.md`, `docs/` scaffold (`architecture`, `roadmap`, `deployment`)
- [x] `docs/deployment.md` — local setup including the PostgreSQL credential reset runbook
- [x] `scripts/bootstrap.ps1`, `scripts/verify_env.ps1`
- [x] `.env.example` with every configuration key documented
- [x] Record open decisions + blockers (Plan §12)

**Exit:** repo initialised, plan committed, blockers identified with owners. **Reached.**
**Verify:** `git status` clean; `scripts/verify_env.ps1` reports the environment.

> **Delivery note (2026-10-21):** M1 is **complete and verified** against the hosted Supabase
> project. Evidence, including the exact checks and the administrative test bootstrap used because
> email confirmation is enabled, is recorded in `docs/supabase.md` §8 and `docs/roadmap.md`.

---

### M1 — Platform foundation (spec Phase 1) — *complete, tested*

Backend
- [x] `backend/` package, `pyproject.toml` (ruff, mypy, pytest config), venv on 3.12
- [x] `core/config.py` — pydantic-settings; auth mode, Supabase/JWKS settings, DB timeouts;
      refuses `AUTH_MODE=local` outside development/test
- [x] `db/session.py` — async engine, pooler-safe connect args (`prepare_threshold=None`),
      statement/idle timeouts, `application_name`; `db/base.py` pins `MetaData(schema="app")`
- [x] **Alembic retired.** `supabase/migrations/20261021120000_initial_identity_schema.sql` is the
      single schema authority: 7 tables, indexes, constraints, RLS, 20 policies, 3 `app_private`
      helpers, revoked grants, and a local/CI auth shim
- [x] `core/errors.py` — §27 taxonomy registry; uniform error envelope
- [x] `core/security.py` — Argon2id for the development issuer, canonical payload hashing
- [x] `core/permissions.py` — 6-role → permission matrix
- [x] `auth/verify.py` — `LocalTokenVerifier` (HS256, dev/test) and `SupabaseTokenVerifier`
      (JWKS, ES256/RS256/EdDSA, `iss`/`aud`/`exp`/`sub`, key rotation, negative paths tested)
- [x] `api/v1/deps.py` — verified-claims resolution, profile provisioning, RBAC dependencies;
      no session cookies and no CSRF machinery (bearer tokens only)
- [x] Routes: `/health`, `/ready`, `/auth/mode`, `/auth/register|login|logout`, `/me`,
      `/workspaces` CRUD, `/workspaces/{id}/members` CRUD
- [x] Request-ID middleware, structlog JSON logging, CORS allowlist
- [x] `python -m app` entry point + `app/loop.py` selector loop for Windows/psycopg
- [x] **Executed:** 97 tests pass (unit + integration + RLS assertions); ruff, format, mypy clean

Frontend
- [x] Vite + React 19 + TS strict + Tailwind v4 + path aliases
- [x] Design tokens + theme toggle; UI primitives; app shell and command palette
- [x] `@supabase/supabase-js` client, Supabase and local auth gateways, explicit configuration
      error (no silent fallback), email-confirmation state
- [x] Session provider reads the Supabase session; API client sends the bearer token with
      `credentials: 'omit'`
- [x] Login/register pages, workspace switcher, workspace create/detail with member roles
- [x] **Executed:** 19 unit tests; lint 0 errors; typecheck; production build; bundle secret scan

Infra & CI
- [x] `.env.example`, `scripts/bootstrap.ps1` (SQL migrations via `psql`), `scripts/verify_env.ps1`
- [x] GitHub Actions `ci.yml`: ruff, format, mypy, pytest against a PostgreSQL service;
      web lint/typecheck/unit/build/secret scan
- [x] Hosted migration applied and verified; test data removed
- [ ] `supabase db lint` / advisors — needs an authenticated scoped CLI token (documented gap)

**Exit:** a user can authenticate with Supabase, is provisioned as a profile, and can create a
workspace with an owner membership; `/health` and `/ready` are green; backend and frontend checks
pass. **Reached and verified live.**

**Verify:** `python -m pytest -q`; `ruff check .`; `ruff format --check .`; `mypy app`;
`npm run lint && npm run typecheck && npm run test && npm run build`;
`supabase db push --db-url …`.

---

### M2 — Agents, providers, tools, runtime (spec Phase 2) — *complete, tested*

Backend
- [x] Provider interface: `Provider` protocol, `ModelRequest/Response/ToolCall/Usage/ProviderError`,
      capability metadata (`supports_tools`, `supports_structured_output`, `supports_streaming`,
      `context_window`)
- [x] Adapters: `ollama`, `openai_compatible`, `anthropic`, `simulation` (deterministic, labelled)
- [x] Provider health check + `POST /providers/{id}/test`; secrets stored by reference, masked out
- [x] `app.model_providers` + `app.model_configs` persistence and CRUD
- [x] Tool registry: `ToolDefinition` (id, name, version, schemas, risk, permissions, timeout,
      retry policy, idempotency, requires_approval, enabled, audit metadata) + server-side resolution
- [x] 9 built-in CRM tools over synthetic data: `search_customers`, `search_deals`,
      `get_customer_summary`, `get_deal_details`, `calculate_metrics`, `search_knowledge`,
      `create_followup_draft`, `generate_sales_report`, `mark_deal_contacted`
- [x] Synthetic CRM dataset (INR, fictional names) seeded only by an explicit audited action
- [x] Agent CRUD, configuration schema, immutable published versions, drafts, duplication, rollback
- [x] Runtime engine: the 20-step lifecycle with per-step trace emission, step/time/token/cost
      budgets, retries (safe ops only), cancellation, terminal-state persistence
- [x] `app.agent_runs`, `app.run_events`, `app.trace_spans`; `/runs/{id}/events`; cursor recovery
- [x] `POST /agents/{id}/run` playground endpoint against the real backend runtime
- [x] Duplicate-call guard: an identical call inside one run reuses the recorded result
      (`tool.cached` event) instead of repeating a possible side effect
- [x] Bounded failures report their work: a run stopped by a budget persists
      `output.completed_actions` and `output.stopped_because` instead of an empty result
- [x] Tri-state capability metadata: unknown is never reported as supported

Frontend
- [x] Agent list + create (template gallery of 8 functional templates) + configuration in Studio
- [x] Agent Studio: configuration panel, model/parameter selector, tool picker, limits
- [x] Version history, publish, rollback, duplicate, archive
- [x] Playground: request input, version selector, run/cancel, tool events, usage/cost, trace link,
      labelled simulation notice, partial results for a bounded failure
- [x] Provider configuration screens (connect, test, model list, capability + pricing metadata)
- [x] Runs & traces: run list, run detail with outcome, events, trace spans, completed actions
- [x] Tools & integrations: registry view and the explicit audited demo-data action

**Exit:** a real agent calls a registered tool against synthetic CRM data and the run is persisted
with a full trace. — *Met twice: once through the labelled deterministic provider and once through a
hosted cloud model (`dots-studio/dots-3-note-preview:free` on OpenRouter).*
**Verify:** `backend/tests/integration/test_agents_api.py` (authoritative flow),
`backend/tests/unit/test_provider_adapters.py`, `backend/tests/unit/test_tool_executor.py`,
`backend/tests/unit/test_simulation_provider.py`; 159 backend tests green.

**M2 findings carried forward**
- The free preview model loops on tool calls; the runtime stopped it at the tool-call budget with
  `EXECUTION_LIMIT_EXCEEDED` and reported the eight completed actions. This is the platform behaving
  correctly, not a defect, and it is the honest reason the same prompt succeeds on the deterministic
  provider and fails on a weak hosted model.
- Approval decisions, streaming output, the workflow canvas and the approval queue remain M3/M4.
- `search_knowledge` returns an explicit empty result with a note until the Knowledge Hub lands (M6).

---

### M3 — Runtime safety, approvals, observability (spec Phase 3)

- [ ] Policy engine: allowlists, budgets, rate limits, max steps/duration/spend, emergency pause,
      agent disable switch, policy-version stamping
- [ ] Approval lifecycle: create → pending → approve/reject/request-changes; canonical hash binding;
      expiry; re-validation at execution; mismatch rejection; reviewer permissions
- [ ] Tool executor: strict validation, timeout, sanitized result persistence, idempotency keys,
      controlled error categories, concurrency limits
- [ ] Runs & Traces UI: filterable history, run detail, hierarchical trace timeline, span inspector,
      cancel, safe replay (dry-run default, linked to the source run)
- [ ] Realtime live updates with cursor-based recovery
- [ ] Error taxonomy surfaced consistently in UI + audit events
- [ ] Security test suite (Plan §9 table) + RLS policy regression tests in `supabase/tests/`

**Exit:** executions are bounded, inspected, and controlled; protected actions require a valid approval.
**Verify:** `tests/security/*`, `tests/integration/test_approval_flow.py`, `supabase db lint`.

---

### M4 — Workflow builder (spec Phase 4)

Backend
- [ ] Versioned workflow JSON schema (nodes, edges, ports, config schemas, policies, metadata)
- [ ] Validator: duplicate IDs, dangling edges, invalid edges, unknown node types, invalid schemas,
      unreachable nodes, illegal cycles, unbounded loops, missing required inputs, unsafe configs
- [ ] Interpreter: topological execution, bounded parallelism, condition/router/merge/transform,
      agent + tool nodes, human-approval node (pause/resume), knowledge node, delay node, bounded
      loop node, start/end; node-level events, timeouts, retries, cancellation, checkpoints
- [ ] Never execute arbitrary code from a definition (declarative transforms only)

Frontend
- [ ] React Flow canvas: drag/drop, typed ports, zoom/pan, minimap, selection, copy/paste, delete,
      duplicate, undo/redo, keyboard shortcuts, autosave + save status, validation panel
- [ ] 13 node types with typed config forms; experimental status explicit
- [ ] Version history, publish, run, debug (run from node, node input/output inspection)

**Exit:** user builds, validates, publishes and runs a multi-step workflow with node-level traces.
**Verify:** integration `test_workflow_engine_*` + graph-validator unit tests.

---

### M5 — Dashboard & Model Lab (spec Phase 5)

Backend
- [ ] Dashboard aggregation queries from persisted rows, with an explicit "no data" state
- [ ] Activity feed from `app.run_events` + `app.audit_events`
- [ ] Model comparison harness: same cases across models, success/validity/tool-accuracy/latency/cost,
      sample counts, provider failures, retry rate; persisted results
- [ ] Cost estimation from a versioned pricing table; "unavailable" when pricing is unknown
- [ ] Smart router: explicit rule-based routing; never bypasses permissions/approvals/budgets
- [ ] Provider health dashboard

Frontend
- [ ] Dashboard: metric cards, run volume, success/failure trend, latency distribution, model usage,
      spend over time, top agents, failure categories, tool distribution; filters; drill-down; refresh
- [ ] Model Lab: provider/model matrix, comparison table, side-by-side outputs, cost/latency view

**Exit:** dashboard reflects real persisted data; comparison results reproducible.
**Verify:** integration tests asserting metrics equal a known fixture's persisted values.

---

### M6 — Evaluations & Knowledge (spec Phase 6)

Backend
- [ ] Suites/cases CRUD; case model: input, fixture, expected output, required facts, prohibited
      outcomes, expected tool calls, expected policy decisions, reference answer, tags, difficulty
- [ ] Evaluators: exact-match, schema-validity, required-fields, rule-based, tool-selection/args,
      groundedness, custom-Python (sandboxed), optional model-judge (labelled)
- [ ] Benchmark runner: fixture isolation, no cross-run contamination, version stamping, reproducible
      reports
- [ ] Regression gates: min success rate, max violation rate, max schema-failure rate, max latency,
      max cost/task — a release cannot pass if a gate was not evaluated
- [ ] Knowledge: sources, document upload to **Supabase Storage** via signed URLs (PDF/TXT/MD/DOCX/CSV)
      with size/type/content validation, parsing, chunking, embeddings (dimension-validated),
      **pgvector + HNSW** storage, hybrid retrieval (vector + `tsvector`/`pg_trgm`), top-K, thresholds,
      citations, explicit no-source behaviour
- [ ] RAG safety: retrieval-time ACL, content treated as untrusted, citation↔source integrity,
      retrieval failure tracking

Frontend
- [ ] Suite builder + case editor, run, results table, per-case detail, regression comparison, gates
- [ ] Knowledge Hub: source list, upload with progress, chunk/embedding status, search playground with
      scores/sources/config, reindex

**Exit:** evaluations persist and reproduce; documents ingest and retrieve with citations.
**Verify:** eval suite runs deterministically; ≥30 synthetic cases seeded in `evals/datasets`.

---

### M7 — Automation, memory, multi-agent (spec Phase 7)

- [ ] Durable jobs on **Supabase Queues (`pgmq`)**: claim with `SKIP LOCKED`, lease/heartbeat, attempt
      counts, backoff with jitter, dead-letter, graceful shutdown, stuck-job recovery
- [ ] Schedules on **`pg_cron`**: cron expressions, timezone-aware, enable/disable, pause/resume,
      concurrency limits, next-run computation, safe backfill
- [ ] Webhooks dispatched via **`pg_net`**: HMAC signature verification, replay protection, rotation
- [ ] Notifications: in-app + webhook destinations, failure alerts
- [ ] Memory: types (session, history, preference, entity, workspace-shared), provenance, expiry, ACL,
      inspection/deletion, no auto-promotion into privileged instructions
- [ ] Analytics: usage limits, cost per successful task, approval turnaround, evaluation trends,
      provider availability
- [ ] Multi-agent orchestration (last): coordinator/specialists, task contracts, structured handoffs,
      shared state, depth/step/duration/spend caps, cycle detection, hierarchical traces

**Exit:** long-running work survives request boundaries; automation is safe and observable.

---

### M8 — Release hardening (spec Phase 8)

- [ ] Full suite green (backend unit/integration/security/eval, web unit, Playwright E2E)
- [ ] 12 Playwright journeys (§28) against the running stack with mocked providers
- [ ] Sales Operations Assistant demo (§30) verified end-to-end
- [ ] Seed/demo workspace with explicit labelling; `is_demo` isolation from live analytics
- [ ] Performance: pagination, indexes from real query plans, lazy-loaded heavy views, bounded
      concurrency, pooler sizing
- [ ] Accessibility audit (keyboard, focus, contrast, reduced motion, chart alternatives)
- [ ] Ops: liveness/readiness separation, structured logs, Supabase Logs + Log Drains, failed-job
      monitoring, Point-in-Time Recovery and restore runbook
- [ ] Deployment: compose profile, env matrix, release checklist, known limitations
- [ ] Documentation set complete (`README`, `AGENTS.md`, `docs/*`, `docs/supabase.md`)

**Exit:** Release Acceptance Checklist (§33) — all 20 items evidenced by a run command or test.

---

## 11. Testing strategy (spec §28)

| Layer | Location | Focus | Target |
|---|---|---|---|
| Unit (BE) | `backend/tests/unit` | schemas, config validation, tool args, permissions, risk, approval match, graph validation, routing, budgets, error normalization, scoring, cost | ~120 cases |
| Integration (BE) | `backend/tests/integration` | migrations applied to a scratch DB, persistence, API authz, agent execution, tool execution, approval+resume, provider adapters (mocked), Realtime events, workflow engine, ingestion/retrieval, worker retries | ~70 cases |
| Security | `backend/tests/security` | tenant isolation, unauthorized tool call, forged approval, tampered payload, expired approval, secret leakage, **JWT forgery**, prompt injection, unsafe args, SSRF, uploads, rate limit, idempotency, escalation | ~45 cases |
| RLS policy | `supabase/tests/*.sql` | every table has RLS; cross-tenant SELECT/UPDATE/DELETE denied; `with check` present on updates; non-member sees no rows | ~12 SQL tests |
| Evaluation | `backend/tests/eval` + `evals/` | ≥30 synthetic cases across 13 categories | ≥30 cases |
| Frontend unit | `apps/web/tests/unit` | components, hooks, formatters, api client, permission gates | ~50 cases |
| E2E | `apps/web/tests/e2e` | 12 journeys (§28) | 12 specs |

**Gates:** CI runs lint (ruff) + format check + mypy + pytest (coverage floor 70% on `app/core`,
`app/tools`, `app/policies`) + `supabase db lint` + RLS policy tests + web lint/typecheck/unit/build
+ Playwright against the local Supabase stack with stubbed provider endpoints. Live paid providers
never run in CI.

**Database in tests:** the same `supabase/migrations/*.sql` files are applied to a scratch database
(hosted scratch DB or the native PostgreSQL 18 instance) so schema drift between environments is
impossible. No SQLite fallback.

---

## 12. Open decisions (each has a documented default so work can continue)

| # | Question | Default if unanswered | Blocks |
|---|---|---|---|
| Q1 | Supabase project: hosted project ref + keys, or a local stack once Docker is installed? | **Resolved:** hosted project (Docker absent). Credentials live in the git-ignored `backend/.env` and `apps/web/.env` | — |
| Q2 | Which cloud provider to wire first (`openai_compatible` vs `anthropic`)? | Implement both; no key required to build/test | M2 demo with a live model |
| Q3 | Confirm the `simulation` provider is acceptable as the offline demo path (labelled `SIMULATED`)? | Yes | M2/M5 demo without keys |
| Q4 | Prefer `uv` for Python env/deps, or stdlib `venv` + `pip`? | **Resolved:** `venv` + `pip` on Python 3.12 | — |
| Q5 | Data API: keep disabled (recommended) or expose a narrow read-only `api` schema? | **Resolved:** disabled; no grants on `app` to API roles | — |
| Q6 | Seed the demo workspace automatically on first boot? | No — explicit `scripts/seed_demo.py` / `supabase seed.sql` | M2 demo |
| Q7 | PostgreSQL 18 password for the local scratch DB used by integration tests? | **Resolved:** project-local cluster on `127.0.0.1:55432`, database `agentops_test` (never the hosted project) | — |

---

## 13. Risks & mitigations

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | No Docker → `supabase start` and the Compose path are unverifiable locally | High | Med | Hosted project for development; compose + local stack exercised in CI (GitHub runners have Docker) |
| R2 | Supabase project not provisioned yet (needs account, keys, region choice) | **Resolved** | — | Project provisioned (`ap-northeast-2`), migration applied, live flow verified (`docs/supabase.md` §8) |
| R3 | Database password unknown for the local scratch DB | **Resolved** | — | Project-local cluster on port 55432; tests apply the same migrations with `psql` |
| R4 | Supabase free-tier limits (DB size, egress, MAU, pausing) | Med | Med | Size monitoring, explicit "unavailable" states, plan upgrade path documented |
| R5 | pgvector cost/performance at scale | Med | Low–Med | HNSW indexes, hybrid retrieval, chunk-size tuning, cap top-K |
| R6 | Pooler transaction-mode caveats (session state, prepared statements) | Med | Med | No session-level state in transactions; `FOR UPDATE SKIP LOCKED` instead of advisory locks |
| R7 | RLS policy drift between API checks and database policies | Med | **High** | Policy regression tests in `supabase/tests/`, `supabase db lint` in CI, policies written in the same migration as the table |
| R8 | JWT verification mistakes (HS256 shortcut, stale JWKS cache) | Med | **Critical** | JWKS with short cache + purge on rotation; HS256 path calls the Auth server; negative tests for forged/expired tokens |
| R9 | Secret key leaking into the client bundle | Low | **Critical** | Only `VITE_`-prefixed publishable keys are inlined; a build-time assertion greps `dist/` for the secret key |
| R10 | Scope explosion (16 modules, 30+ tables, 50+ routes) | High | Med | Milestone slicing, thin vertical slices, Definition-of-Done gates, P1/P2 deferred to M7 |
| R11 | Tailwind v4 + shadcn friction | Med | Low | Fallback to Tailwind v3; tokens already semantic |
| R12 | Workflow engine edge cases (loops, merge, pause) | Med | High | Validator rejects unsafe graphs; bounded loop counter; checkpointed resume; explicit error categories |
| R13 | Approval-binding bypass via argument mutation | Low | **Critical** | Canonical JSON + SHA-256 re-verified at execution; negative security tests |
| R14 | Docs drift from implementation | Med | Med | Docs updated inside each milestone; release checklist cross-checks `docs/*` |

---

## 14. Commands (target)

```powershell
# Supabase
supabase login                                   # scoped access token preferred
supabase link --project-ref <ref>
supabase db push --linked                        # apply supabase/migrations to the linked project
supabase db pull --local                         # capture remote drift as a migration
supabase db lint --linked                        # schema/policy lint on the linked project
supabase db reset                                # local stack: apply migrations + seed
supabase status                                  # local stack endpoints and keys
supabase projects api-keys --project-ref <ref>   # key inventory (never use --reveal in CI or logs)

# setup
scripts/bootstrap.ps1
scripts/verify_env.ps1

# backend
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
python -m pytest tests/unit -q
python -m pytest tests/integration -q
ruff check .
ruff format --check .
mypy app
python -m app                                    # Windows: selector loop wired automatically
# uvicorn app.main:app --reload --port 8000 --loop app.loop:selector_loop_factory

# frontend
cd apps/web
npm run dev | npm run build | npm run lint | npm run typecheck | npm run test
npx playwright test

# seed + demo
python scripts/seed_demo.py --workspace "AgentOps Demo"
```

---

## 15. Definition of Done (per feature, spec §33)

UI + backend behaviour + persistence + authorization + validation/error states +
loading/empty/success states + tests written **and run** + docs updated + no secrets or
cross-tenant leakage + real integration or clearly-labelled simulation + no fabricated success +
**every new table has RLS policies in the same migration**.

**Release gate:** all 20 items of §33's Release Acceptance Checklist evidenced by a command or
test run output.
