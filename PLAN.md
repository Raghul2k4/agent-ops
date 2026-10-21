# AgentOps — Implementation Plan (Plan of Record)

**Status:** Active
**Owner:** Coding agent (per `AGENTS.md` §36)
**Last updated:** 2026-10-21
**Spec source:** `AGENTS.md` (2063 lines, sections 1–36) — this plan is the execution map for that specification.
**Supersedes:** none (first plan; repo contained only `AGENTS.md`)

---

## 0. Executive summary

`AGENTS.md` is a full product specification for **AgentOps**, an AI agent engineering platform
(build → execute → observe → evaluate → govern). The repository was **empty** apart from the
spec, so this plan covers greenfield initialization.

The plan is organised as **9 milestones (M0–M8)**, each with a vertical slice that ends
runnable and testable, gated on the spec's *Definition of Done* (§33) and the
*Release Acceptance Checklist* (§33). Nothing is marked complete on the basis of UI existing;
each milestone carries explicit verification commands.

Three facts discovered during the environment audit materially shape delivery
(see §1.2): there is **no Docker**, **pgvector is not installed** in the local PostgreSQL 18
install, and **Ollama/Redis are absent**. Each has an explicit, documented fallback
(§2.3, §12).

---

## 1. Context

### 1.1 What the spec demands

| Spec section | Requirement summary | Priority |
|---|---|---|
| §1 | 20 mandatory engineering rules (inspect first, no mocks, no fabricated success, keep runnable) | Binding |
| §2–3 | Platform across Build / Execute / Observe / Evaluate / Govern; P0/P1/P2 scope | P0 first |
| §4 | Fixed stack: React+TS+Vite+Tailwind+shadcn+React Flow+TanStack Query+RHF/Zod+Recharts+Playwright; FastAPI+Pydantic+SQLAlchemy 2+Alembic+PostgreSQL+HTTPX; Ollama + cloud adapters; pgvector; Redis queues | Binding |
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
| Python | `3.14.7` (default), `3.12` also installed | `py -0p` | Build on 3.12 for widest wheel coverage; 3.14 fallback. See §2.2 |
| pip | `26.2.1` | `pip --version` | Optional `uv` accelerator |
| Node / npm | `24.20.0` / `11.19.0` | `node --version` | Vite 7 / React 19 compatible |
| **Docker** | **NOT INSTALLED** | `docker --version` → not recognized | `docker-compose.yml` authored for CI/prod but **cannot be verified locally**; local stack uses native services |
| **PostgreSQL** | **18 x64 installed & RUNNING**, `127.0.0.1:5432` | service `postgresql-x64-18`, port listen | Real Postgres available — target DB is genuine PG18, not SQLite |
| PG auth | `scram-sha-256` on local + host | `pg_hba.conf` | **Password unknown → blocks M1 migrations.** Ask user (§11 Q1) |
| **pgvector** | **NOT INSTALLED** in PG18 | `share/extension/vector.control` absent | Knowledge Hub needs documented fallback (§2.3) |
| PostGIS / pg_trgm / pgcrypto | Present (3.6.2 etc.) | `share/extension/*.control` | Bonus: keyword search + geo not required |
| Redis | Not installed | `Get-Service` | Background jobs use in-process worker + `background_jobs` table; Redis adapter deferred (§2.3) |
| Ollama | Not installed | `Get-Command ollama` | Local-model path code-complete but unrunnable here; simulation provider keeps demo honest |
| `make` | Not installed | `Get-Command make` | Cross-platform scripts (`scripts/*.ps1` + `npm`/`python` entrypoints) instead of Makefiles |
| Network | PyPI + npm reachable | `Invoke-WebRequest` → HTTP 200 | Dependency install works |
| cp314 wheels | pydantic-core, SQLAlchemy 2.1.5, psycopg-binary 3.3.6 all resolve | `pip download` | No hard 3.12 dependency for core stack |
| Disk free | ~89 GB | `Get-PSDrive C` | Fine |

### 1.3 Gaps against the spec (what must be built)

Everything except the spec itself. Concretely: 0/30+ DB tables, 0/50+ API routes, 0 UI screens,
0 tools, 0 providers, 0 tests, 0 docs, 0 CI, 0 seed data.

---

## 2. Technical decisions (locked at M0; ADRs in `docs/architecture.md`)

### 2.1 Runtime and framework

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI (async) + Pydantic v2 | Mandated; async suits SSE + concurrent tool calls |
| ORM / migrations | SQLAlchemy 2.0 async + Alembic | Mandated; Alembic is the only schema authority (§24: no auto-create) |
| Async driver | `psycopg` 3 (binary) | Native async, better PG type coverage (uuid/jsonb/array/pgvector) than asyncpg |
| Agent runtime | **Custom** (no LangChain/LlamaIndex) | Spec §4 mandates a custom runtime; full auditability of tool/permission enforcement, no heavy transitive deps |
| Provider abstraction | Own interface + adapters: `ollama`, `openai_compatible`, `anthropic`, `simulation` | Ollama is local; `openai_compatible` also covers Groq/Together/vLLM/OpenRouter with one adapter |
| Demo-mode provider | `simulation` — deterministic, **always labelled `SIMULATED` in UI/API** | §29/§30 forbid fabricated success; simulation must be explicit, never mixed into live analytics |
| Frontend | React 19 + Vite 7 + TS strict + Tailwind v4 + shadcn/ui + TanStack Query v5 + Zustand + RHF/Zod + Recharts + `@xyflow/react` | Mandated stack, mutually compatible |
| Workflow canvas | `@xyflow/react` (React Flow v12) | Mandated |
| Auth | Server-side session table + HttpOnly/Secure/SameSite cookie + argon2id password hashing + CSRF double-submit token; scoped API keys (hashed) | §21 forbids trusting header user IDs; server sessions allow revocation & expiry |
| API keys | Stored as SHA-256 hashes, shown once, scoped + expirable | §23 |
| Event streaming | SSE with persisted `run_events.sequence_number` cursor | §13: persist before broadcast, reconnect with cursor |

### 2.2 Python version policy

Build on **Python 3.12** (`C:\Users\Raven\AppData\Local\Programs\Python\Python312`) for the
widest binary-wheel coverage of PDF/DOCX/embedding/parsing libraries; the repo pins
`requires-python = ">=3.12,<3.14"` in `pyproject.toml` while 3.14 remains available as a
fallback. Core stack has cp314 wheels, so the decision is reversible; it is re-evaluated at
M2 when document-parsing deps are introduced.

### 2.3 Documented deviations from the spec (spec §1: "choose the safer implementation and document the trade-off")

| # | Spec asks | Local reality | Decision | Reversal path |
|---|---|---|---|---|
| D1 | pgvector for vector search | extension absent from PG18 install | Store embeddings as `double precision[]` with a pure-SQL cosine similarity function; **auto-detect** pgvector at startup and use `Vector` type + HNSW index when present | Install pgvector (needs VS Build Tools for PG18 on Windows) → migration flips column type |
| D2 | Redis-backed queue/workers | Redis absent | In-process asyncio worker pool + `background_jobs` table as the durable queue; a `QueueBackend` interface allows a Redis implementation later | `docker compose up redis` (CI/prod) |
| D3 | Temporal for long-running workflows | Not installed, heavy | Workflow interpreter with persisted checkpoints + pause/resume in Postgres | Wrap interpreter in Temporal activities |
| D4 | Docker Compose local dev | Docker absent | Compose file authored & CI-verified; local dev uses natively running PG18; `.env.example` documents both paths | — |
| D5 | Ollama local model execution | Ollama absent | Adapter fully implemented & unit-tested against a mocked transport; UI surfaces a clear "provider unreachable" diagnostic (§12 E2) | `ollama serve` |
| D6 | Cloud LLM provider | No API key | `openai_compatible` + `anthropic` adapters implemented, connection-tested, and disabled until a key is configured | Provide key in UI/provider form |

### 2.4 Non-negotiable engineering rules (carried from `AGENTS.md` §1, §35)

1. No fabricated results anywhere. Every metric derives from persisted rows.
2. No business logic in React components or route handlers — routers are thin, services own behaviour.
3. Every tenant-owned table carries `workspace_id`; every query is tenant-scoped by construction.
4. Tool names/arguments from a model are untrusted input, validated server-side.
5. Approval binds to a canonical argument hash; expiry/policy/version re-verified at execution time.
6. Playwright journeys are real E2E against a running stack; provider calls are mocked in CI.
7. Documentation updated in the same milestone as the code it describes.

---

## 3. Target architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│ apps/web (React 19 + TS strict + Vite + Tailwind v4 + shadcn)            │
│  shell: sidebar · header · command palette (cmdk) · toasts (sonner)        │
│  features: dashboard agents workflows runs evaluations models knowledge     │
│            approvals integrations workspace analytics settings              │
│  server state: TanStack Query  |  client state: Zustand  |  forms: RHF+Zod  │
└───────────────▲───────────────────────────────────────────────▲────────────┘
                │ REST /api/v1 (JSON, typed envelopes)         │ SSE
┌───────────────┴───────────────────────────────────────────────┴────────────┐
│ backend (FastAPI, async)                                                  │
│  api/v1/routers/*  → thin handlers + dependency injection                 │
│  services/*        → all business logic (agents, runs, approvals, evals)    │
│  agents/runtime    → custom runtime: model loop → tool dispatch → policy   │
│  providers/*       → ollama | openai_compatible | anthropic | simulation   │
│  tools/registry    → typed schemas, risk levels, approval rules, limits    │
│  workflows/engine  → graph validator + interpreter + node executors       │
│  policies/*        → permission + risk + budget enforcement                │
│  approvals/*       → canonical-hash binding, expiry, decision workflow     │
│  evaluations/*     → deterministic + optional model-judged scorers         │
│  knowledge/*       → ingestion → chunking → embeddings → retrieval        │
│  jobs/worker       → in-process pool over durable `background_jobs`       │
│  observability/*   → structlog JSON logs, request-id, metrics interface   │
└───────────────▲───────────────────────────────────────────────────────────┘
                │ SQLAlchemy async / psycopg
┌───────────────┴───────────────────────────────────────────────────────────┐
│ PostgreSQL 18 (source of truth) — Alembic migrations only                 │
│  tenancy: workspace_id on every tenant table · tenant-scoped repositories │
│  events: run_events(sequence_number) → SSE cursor · trace_spans hierarchy │
└───────────────────────────────────────────────────────────────────────────┘
```

**Layering rule (enforced by review + import-lint):**
`api → services → domain(core/agents/workflows/tools/policies) → repositories → db`.
Domain packages never import FastAPI; repositories never import services.

---

## 4. Repository layout (target)

```
agentops/
├─ apps/web/                     # React app
│  ├─ src/{app,components,features,hooks,lib,routes,schemas,styles,types}/
│  ├─ public/  tests/{unit,e2e}/  vite.config.ts  tsconfig.json
├─ backend/
│  ├─ pyproject.toml  alembic.ini  .env.example
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
│  │  ├─ policies/  approvals/  jobs/  observability/
│  │  └─ main.py
│  └─ tests/{unit,integration,security,eval,fixtures}/
├─ evals/{datasets,suites,reports}/
├─ docs/{architecture,database-schema,api-reference,security,design-system,deployment,roadmap}.md
├─ infra/{docker,nginx,alembic}/
├─ scripts/{bootstrap.ps1,seed_demo.py,verify_env.ps1}/
├─ .github/workflows/{ci.yml,release.yml}
├─ docker-compose.yml  .env.example  .gitignore  README.md  AGENTS.md  PLAN.md
```

---

## 5. Data model plan (spec §24)

All tables: `uuid` PK (`uuid4`, app-generated), `created_at/updated_at` `timestamptz` UTC,
tenant tables carry `workspace_id NOT NULL` with FK `ON DELETE CASCADE`.

| Area | Tables (spec names) | Notable constraints / indexes |
|---|---|---|
| Identity | `users`, `workspaces`, `workspace_members` | unique `(workspace_id,user_id)`; `workspaces.slug` unique; role enum (owner/admin/developer/operator/reviewer/viewer) |
| Agents | `agents`, `agent_versions` | unique `(agent_id,version_number)`; `configuration_hash`; published versions immutable (app-level + `published_at`) |
| Models | `model_providers`, `model_configs` | `secret_reference` only — **no plaintext credentials in JSON columns**; `capability_metadata` JSONB |
| Tools | `tool_definitions`, `agent_tools` | global built-ins have `workspace_id NULL` + `is_global`; unique `(workspace_id,name,version)` |
| Workflows | `workflow_definitions`, `workflow_versions` | unique `(workflow_id,version_number)`; `graph_hash` |
| Execution | `agent_runs`, `workflow_runs`, `run_events`, `trace_spans` | `run_events UNIQUE(run_id, sequence_number)`; `trace_spans(parent_span_id)`; index `(workspace_id,status,started_at)` |
| Approvals/Audit | `approval_requests`, `audit_events` | unique `(run_id,tool_definition_id,canonical_arguments_hash)` pending guard; audit append-only |
| Evaluation | `evaluation_suites`, `evaluation_cases`, `evaluation_results` | `evaluation_cases UNIQUE(suite_id,case_key)`; results carry agent_version + model_config |
| Knowledge/Memory | `knowledge_sources`, `documents`, `document_chunks`, `memory_records` | `documents.file_hash` unique per workspace; `document_chunks UNIQUE(document_id,chunk_index)`; embedding column per D1 |
| Automation | `schedules`, `webhook_endpoints`, `background_jobs` | `webhook_endpoints.secret_reference` (hashed); `background_jobs(workspace_id,status,scheduled_at)` |

Additions beyond spec (documented, minimal): `sessions`, `api_keys`, `workspace_invitations`,
`notifications` — required by §21/§23 auth & dev-platform features.

---

## 6. API plan (spec §25)

Prefix `/api/v1`. Thin routers; all responses typed; errors use the §27 taxonomy:
`{ "error": { "code": "...", "message": "...", "request_id": "...", "details": {...} } }`.

Router groups → spec endpoints:
`system` (health/ready/me) · `workspaces` (+members) · `dashboard` (summary/activity/usage/health)
· `agents` (+versions/publish/rollback/test) · `models` (providers/models/compare) ·
`tools` (+test) · `workflows` (+versions/validate/publish/run) · `runs` (+events/trace/cancel/replay)
· `approvals` (+decision) · `evaluations` (suites/results) · `knowledge` (sources/documents/search)
· `schedules` (+pause/resume) · `integrations` · `memory` · `analytics` · `webhooks` · `api-keys`.

Conventions: cursor pagination (`limit`/`cursor`), `Idempotency-Key` on all POST side effects,
`X-Request-ID` echoed, RBAC check on every handler, rate limits on auth/model/eval/run-create.

---

## 7. Frontend plan (spec §6–7)

- **Shell:** collapsible dark sidebar (11 areas), compact header (workspace switcher, env selector,
  breadcrumb, search, command palette, notifications, help, profile), responsive down to 390px.
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
- **Mock vs live:** a global `DataModeBanner` shows `SIMULATED` whenever the simulation provider
  or demo dataset is active; demo records carry `is_demo` and are excluded from live analytics
  unless explicitly requested.

---

## 8. Security model (spec §26)

| Threat | Control | Verified by |
|---|---|---|
| Prompt injection (direct/indirect) | Tool authz outside the model; retrieved content wrapped as untrusted data; approval for writes; per-agent tool allowlist | `tests/security/test_prompt_injection.py` |
| Cross-tenant access | `workspace_id` scoping in every repository + FK constraints + workspace membership resolved server-side | `tests/security/test_tenant_isolation.py` |
| Privilege escalation | Role→permission matrix enforced in `core/permissions.py`; tool `required_permissions` checked before execution | `tests/security/test_privilege_escalation.py` |
| Forged/tampered approval | SHA-256 canonical-argument hash + expiry + policy version re-verified at execution; decision requires reviewer permission | `tests/security/test_approval_binding.py` |
| Secret leakage | Secrets stored via `secret_reference` (env/manager), never in JSON columns; responses masked; redaction filter on logs/traces | `tests/security/test_secret_leakage.py` |
| Unsafe tool args | Strict Pydantic schemas, `extra="forbid"`, unknown tool name → typed error | unit + integration |
| SSRF | URL scheme allowlist, DNS resolution check, private/loopback/link-local block, redirect re-validation, size+timeout caps | `tests/security/test_ssrf.py` |
| Upload abuse | Size/type/content validation, safe parsers, no path traversal, storage outside app dirs | `tests/security/test_uploads.py` |
| Runaway execution | `max_steps`, `max_wall_clock_ms`, `max_tool_calls`, `max_tokens`, `max_cost_usd`, per-tool rate limit, recursion guard | unit + integration |
| Audit | Append-only `audit_events` for auth, denial, provider change, tool attempt, approval, policy violation, publish, role change | integration |

---

## 9. Milestones

Each milestone ends with a **runnable vertical slice**, executed tests, and updated docs.
Status legend: `[ ]` todo · `[~]` in progress · `[x]` done & verified.

---

### M0 — Repository foundation & plan (spec Phase 0)

- [x] Audit repository (empty) and environment (audit table in §1.2)
- [x] Extract spec requirements → this plan + `docs/roadmap.md` + `docs/architecture.md`
- [x] Lock architectural decisions (§2) with fallbacks for missing infrastructure (§2.3)
- [ ] `git init`, `.gitignore` (py/node/env/IDE), `.editorconfig`
- [ ] `README.md` skeleton, `docs/` scaffold
- [ ] Record open decisions + blockers (§11)

**Exit:** repo initialised, plan committed, blockers identified with owners.
**Verify:** `git status` clean; plan documents reviewed.

---

### M1 — Platform foundation (spec Phase 1)

Backend
- [ ] `backend/` package, `pyproject.toml` (ruff, mypy, pytest config), venv on 3.12
- [ ] `core/config.py` (pydantic-settings; env-prefixed; `.env` support)
- [ ] `db/session.py` (async engine, pool, `get_session` dependency), `db/base.py`
- [ ] Alembic scaffold + initial migration (users, workspaces, workspace_members, sessions, api_keys, audit_events)
- [ ] `core/errors.py` — §27 taxonomy registry; `api/error_handlers.py` → uniform envelope
- [ ] `core/security.py` — argon2id hashing, session tokens, CSRF double-submit, API-key hashing
- [ ] `core/permissions.py` — role→permission matrix
- [ ] `api/v1/deps.py` — current user, workspace resolution, RBAC dependency factories
- [ ] Auth routes: register/login/logout/me/CSRF; rate-limited; session rotation
- [ ] Workspaces routes: create/list/get/patch/members (+invite, role change)
- [ ] `GET /health` (liveness), `GET /ready` (DB + dependency readiness), `GET /api/v1/me`
- [ ] Request-ID middleware, structlog JSON logging, CORS with explicit origin allowlist

Frontend
- [ ] Vite + React 19 + TS strict + Tailwind v4 + path aliases (`@/`)
- [ ] Design tokens + base styles + font stack (Inter) + theme toggle
- [ ] shadcn component set (button/input/select/dialog/dropdown/tooltip/badge/table/skeleton/tabs)
- [ ] App shell: sidebar (11 areas), header, breadcrumbs, command palette (cmdk), user menu
- [ ] Auth pages (login/register) + session-expiry handling
- [ ] Workspace switcher + onboarding empty state
- [ ] TanStack Query provider, API client with typed error mapping, Zod response validation
- [ ] Route guards by role, error boundary, 404/403 pages

Infra & CI
- [ ] `docker-compose.yml` (postgres, redis, backend, web) — authored, CI-verified (D4)
- [ ] `.env.example`, `scripts/bootstrap.ps1`, `scripts/verify_env.ps1`
- [ ] GitHub Actions `ci.yml`: ruff, mypy, pytest, web lint/typecheck/build, compose smoke

**Exit:** user can register, log in, create a workspace; `/health` + `/ready` green; CI green.
**Verify:** `pytest -q`, `npm run lint && npm run typecheck && npm run build`, `docker compose config`.

---

### M2 — Agents, providers, tools, runtime (spec Phase 2)

Backend
- [ ] Provider interface: `Provider` protocol, `ModelRequest/Response/ToolCall/Usage/ProviderError`,
      capability metadata (`supports_tools`, `supports_structured_output`, `supports_streaming`, `context_window`)
- [ ] Adapters: `ollama`, `openai_compatible`, `anthropic`, `simulation` (deterministic, labelled)
- [ ] Provider health check + `POST /providers/{id}/test`; secrets masked in/out
- [ ] `model_providers` + `model_configs` persistence and CRUD
- [ ] Tool registry: `ToolDefinition` (id, name, version, schemas, risk, permissions, timeout,
      retry policy, idempotency, requires_approval, enabled, audit metadata) + server-side resolution
- [ ] 9 built-in CRM tools: `search_customers`, `search_deals`, `get_customer_summary`,
      `get_deal_details`, `calculate_metrics`, `search_knowledge`, `create_followup_draft`,
      `generate_sales_report`, `mark_deal_contacted`
- [ ] Synthetic CRM dataset (INR, fictional names) as a deterministic seed module
- [ ] Agent CRUD, configuration schema (system prompt, model+params, tools, knowledge, memory,
      input/output schema, limits, permission profile), immutable published versions, drafts,
      duplication, rollback, change summaries
- [ ] Runtime engine: 20-step lifecycle (§11 of spec) with per-step trace emission, step/time/token/
      cost budgets, retries (safe ops only), cancellation, terminal-state persistence
- [ ] `agent_runs`, `run_events`, `trace_spans` persistence; `/runs/{id}/events` + SSE stream
- [ ] `POST /agents/{id}/test` playground endpoint (real backend runtime)

Frontend
- [ ] Agent list + create/edit (RHF+Zod forms) + template gallery (8 functional templates)
- [ ] Agent Studio: configuration panel, model/parameter selector (capability-aware), tool picker
- [ ] Version history, diff/publish/rollback/duplicate
- [ ] Playground: chat input, structured input editor, streaming output, tool events, usage/cost,
      trace link, cancel, error + retry
- [ ] Provider configuration screens (connect, test, model list, default model)

**Exit:** a real agent calls a registered tool against synthetic CRM data and the run is persisted
with a full trace.
**Verify:** integration test `test_agent_runtime_end_to_end` + provider adapter unit tests.

---

### M3 — Runtime safety, approvals, observability (spec Phase 3)

- [ ] Policy engine: allowlists, budgets, rate limits, max steps/duration/spend, emergency pause,
      agent disable switch, policy-version stamping
- [ ] Approval lifecycle: create → pending → approve/reject/request-changes; canonical hash binding;
      expiry; re-validation at execution; mismatch rejection; reviewer permissions
- [ ] Tool executor: strict validation, timeout, sanitized result persistence, idempotency keys,
      controlled error categories, concurrency limits
- [ ] Runs & Traces UI: filterable history (server-side), run detail, hierarchical trace timeline,
      span inspector with sanitized inputs/outputs, cancel, safe replay (dry-run default, linked to source)
- [ ] Error taxonomy surfaced consistently in UI + audit events
- [ ] Security test suite (§8 table)

**Exit:** executions are bounded, inspected, and controlled; protected actions require a valid approval.
**Verify:** `tests/security/*` + `tests/integration/test_approval_flow.py`.

---

### M4 — Workflow builder (spec Phase 4)

Backend
- [ ] Versioned workflow JSON schema (nodes, edges, ports, config schemas, policies, metadata)
- [ ] Validator: duplicate IDs, missing refs, invalid edges, unknown node types, schema errors,
      unreachable nodes, illegal cycles, unbounded loops, missing required inputs, unsafe configs
- [ ] Interpreter: topological execution, bounded parallelism, condition/router/merge/transform,
      agent + tool nodes, human-approval node (pause/resume), knowledge node, delay node, loop node
      (bounded), start/end; node-level events, timeouts, retries, cancellation, checkpoints, structured output
- [ ] Never execute arbitrary code from a definition (no eval/exec; declarative transforms only)

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
- [ ] Dashboard aggregation queries (runs, success rate, latency percentiles, token usage, estimated
      cost, pending approvals, policy violations) — all from persisted rows; explicit "no data" state
- [ ] Activity feed from `run_events` + `audit_events`
- [ ] Model comparison harness: same cases across models, success/validity/tool-accuracy/latency/cost,
      sample counts, provider failures, retry rate; persisted results
- [ ] Cost estimation from a versioned pricing table; "unavailable" when pricing is unknown (never invented)
- [ ] Smart router: explicit rule-based routing (capability, latency target, budget, availability, fallback order);
      never bypasses permissions/approvals/budgets
- [ ] Provider health dashboard

Frontend
- [ ] Dashboard: metric cards, run volume, success/failure trend, latency distribution, model usage,
      spend over time, top agents, failure categories, tool distribution; date-range + filters; drill-down;
      refresh; live updates via SSE
- [ ] Model Lab: provider/model matrix, comparison table, side-by-side outputs, cost/latency scatter

**Exit:** dashboard reflects real persisted data; comparison results reproducible.
**Verify:** integration tests asserting metrics equal a known fixture's persisted values.

---

### M6 — Evaluations & Knowledge (spec Phase 6)

Backend
- [ ] Suites/cases CRUD; case model: input, fixture, expected output, required facts, prohibited outcomes,
      expected tool calls, expected policy decisions, reference answer, tags, difficulty
- [ ] Evaluators: exact-match, schema-validity, required-fields, rule-based, tool-selection/args,
      groundedness, custom-Python (sandboxed, allow-listed imports), optional model-judge (labelled)
- [ ] Benchmark runner: fixture isolation, no cross-run contamination, version stamping
      (prompt/model/tool/dataset/config), reproducible reports
- [ ] Regression gates: min success rate, max violation rate, max schema-failure rate, max latency,
      max cost/task — a release cannot pass if a gate was not evaluated
- [ ] Knowledge: sources, document upload (PDF/TXT/MD/DOCX/CSV) with size/type/content validation,
      parsing, chunking (size/overlap configurable), embeddings (provider/model config, dimension validation),
      retrieval (vector + metadata filter + optional hybrid), top-K, thresholds, citations, no-source behaviour
- [ ] RAG safety: retrieval-time ACL, content treated as untrusted, citation↔source integrity, retrieval failure tracking

Frontend
- [ ] Suite builder + case editor, run, results table, per-case detail, regression comparison, gate configuration
- [ ] Knowledge Hub: source list, document upload with progress, chunk/embedding status, search playground
      with scores/sources/config, reindex

**Exit:** evaluations persist and reproduce; documents ingest and retrieve with citations.
**Verify:** eval suite runs deterministically; ≥30 synthetic cases seeded in `evals/datasets`.

---

### M7 — Automation, memory, multi-agent (spec Phase 7)

- [ ] Durable jobs: `background_jobs` table, in-process worker pool, lease/heartbeat, attempt counts,
      backoff with jitter, dead-letter, graceful shutdown, stuck-run recovery
- [ ] Schedules: cron expressions, timezone-aware, enable/disable, pause/resume, concurrency limits,
      next-run computation, safe backfill
- [ ] Webhooks: HMAC signature verification, replay protection, secret rotation, per-endpoint enable
- [ ] Notifications: in-app + webhook destinations, failure alerts
- [ ] Memory: types (session, history, preference, entity, workspace-shared), provenance, expiry, ACL,
      inspection/deletion, no auto-promotion into privileged instructions
- [ ] Analytics: usage limits, cost per successful task, approval turnaround, evaluation trends, provider availability
- [ ] Multi-agent orchestration (last, only after M2–M6 are reliable): coordinator/specialists, task contracts,
      structured handoffs, shared state, depth/step/duration/spend caps, cycle detection, hierarchical traces

**Exit:** long-running work survives request boundaries; automation is safe and observable.

---

### M8 — Release hardening (spec Phase 8)

- [ ] Full suite green (backend unit/integration/security/eval, web unit, Playwright E2E)
- [ ] 12 Playwright journeys (§28) against the running stack with mocked providers
- [ ] Sales Operations Assistant demo (§30) verified end-to-end: parse → search → filter → research →
      drafts → validate args → trace → proposed actions → approval → execute → per-status report
- [ ] Seed/demo workspace with explicit labelling; `is_demo` isolation from live analytics
- [ ] Performance: pagination, indexes from real query plans, lazy-loaded heavy views, bounded concurrency
- [ ] Accessibility audit (keyboard, focus, contrast, reduced motion, chart alternatives)
- [ ] Ops: liveness/readiness separation, structured logs, failed-job monitoring, migration + backup/restore docs
- [ ] Deployment: compose profile, env matrix, release checklist, known limitations
- [ ] Documentation set complete (`README`, `AGENTS.md`, `docs/*`)

**Exit:** Release Acceptance Checklist (§33) — all 20 items evidenced by a run command or test.

---

## 10. Testing strategy (spec §28)

| Layer | Location | Focus | Target |
|---|---|---|---|
| Unit (BE) | `backend/tests/unit` | schemas, config validation, tool args, permissions, risk, approval match, graph validation, routing, budgets, error normalization, scoring, cost | ~120 cases |
| Integration (BE) | `backend/tests/integration` | migrations, persistence, API authz, agent execution, tool execution, approval+resume, provider adapters (mocked), SSE, workflow engine, ingestion/retrieval, worker retries | ~70 cases |
| Security | `backend/tests/security` | tenant isolation, unauthorized tool call, forged approval, tampered payload, expired approval, secret leakage, prompt injection, unsafe args, SSRF, uploads, rate limit, idempotency, escalation | ~40 cases |
| Evaluation | `backend/tests/eval` + `evals/` | ≥30 synthetic cases across 13 categories (success, missing data, ambiguity, bad args, tool failure, provider timeout, injection, denial, approval-required, retrieval failure, schema error, budget exhaustion) | ≥30 cases |
| Frontend unit | `apps/web/tests/unit` | components, hooks, formatters, api client, permission gates | ~50 cases |
| E2E | `apps/web/tests/e2e` | 12 journeys (§28) | 12 specs |

**Gates:** CI runs lint (ruff) + format check + mypy + pytest (coverage floor 70% on `app/core`,
`app/tools`, `app/policies`) + web lint/typecheck/unit/build + Playwright against compose stack
with mocked provider transports. Live paid providers never run in CI.

**Local DB strategy:** native PostgreSQL 18 — one `agentops` DB for dev, one `agentops_test`
DB recreated per test session; Alembic applied via `alembic upgrade head`; no SQLite fallback
(Postgres semantics are the target).

---

## 11. Open decisions (need input — each has a documented default so work can continue)

| # | Question | Default if unanswered | Blocks |
|---|---|---|---|
| Q1 | PostgreSQL 18 superuser/app password for `127.0.0.1:5432`? | User resets it locally (instructions in `docs/deployment.md`) | **M1 migrations + all integration tests** |
| Q2 | Which cloud provider to wire first (`openai_compatible` vs `anthropic`)? | Implement both; no key required to build/test | M2 demo with a live model |
| Q3 | Confirm the `simulation` provider is acceptable as the offline demo path (clearly labelled `SIMULATED`)? | Yes | M2/M5 demo without keys |
| Q4 | Prefer `uv` for Python env/deps, or stdlib `venv` + `pip`? | `venv` + `pip` (uv optional accelerator) | M1 ergonomics |
| Q5 | Install `pgvector` for PG18 on Windows (needs VS Build Tools, ~large) now or defer? | Defer; use `float8[]` + SQL cosine (D1) | M6 retrieval quality/perf |
| Q6 | Should the demo workspace be seeded automatically on first boot? | No — explicit `scripts/seed_demo.py` command only (§29) | M2 demo |

---

## 12. Risks & mitigations

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | No Docker → compose path unverifiable locally | High | Med | Compose authored for CI (GitHub runners have Docker); local dev uses native PG18; `verify_env.ps1` checks parity |
| R2 | DB password unknown | High | **High** | Ask now (Q1); provide reset runbook; keep a mocked-DB unit tier so unit work is not blocked |
| R3 | Python 3.14 dependency gaps (parsing/embedding libs) | Med | Med | Build on 3.12; verify each new dep's wheel before adopting |
| R4 | pgvector absent → slow/approximate vector search | High | Low–Med | D1 fallback; auto-detect and upgrade path; dataset sizes in scope are small |
| R5 | No Ollama/keys → demo looks non-functional | High | High | Q3: `simulation` provider, explicitly labelled; provider-offline diagnostics; never fake a live provider |
| R6 | Scope explosion (16 modules, 30+ tables, 50+ routes) | High | Med | Milestone slicing, thin vertical slices, Definition-of-Done gates, P1/P2 deferred to M7 |
| R7 | Tailwind v4 + shadcn friction | Med | Low | Fallback to Tailwind v3 + shadcn classic config; tokens already semantic |
| R8 | Workflow engine edge cases (loops, merge, pause) | Med | High | Validator rejects unsafe graphs; bounded loop counter; checkpointed resume; explicit error categories |
| R9 | Approval-binding bypass via argument mutation | Low | **Critical** | Canonical JSON + SHA-256 hash re-verified at execution; negative security tests |
| R10 | SSE event loss / duplication | Med | Med | Persist-then-publish, monotonic `sequence_number`, client cursor reconnect, dedupe on sequence |
| R11 | CI flakiness from external deps | Med | Med | Provider transports mocked in CI; compose service health-gates; retries with jitter only for eligible ops |
| R12 | Docs drift from implementation | Med | Med | Docs updated inside each milestone; release checklist cross-checks `docs/*` |

---

## 13. Commands (target)

```powershell
# setup
scripts/bootstrap.ps1                      # venv + npm install + .env + DB create
scripts/verify_env.ps1                     # checks Python/Node/Postgres/optional services

# backend
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q                        # all suites
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/security -q
ruff check . && ruff format --check .
mypy app
alembic upgrade head
alembic revision --autogenerate -m "msg"

# frontend
cd apps/web
npm run dev | npm run build | npm run lint | npm run typecheck | npm run test
npx playwright test

# seed + run
python scripts/seed_demo.py --workspace "AgentOps Demo"
uvicorn app.main:app --reload --port 8000   # backend
npm run dev                                 # frontend (5173)
```

---

## 14. Definition of Done (per feature, spec §33)

UI + backend behaviour + persistence + authorization + validation/error states +
loading/empty/success states + tests written **and run** + docs updated + no secrets or
cross-tenant leakage + real integration or clearly-labelled simulation + no fabricated success.

**Release gate:** all 20 items of §33's Release Acceptance Checklist evidenced by a command or
test run output.
