# AgentOps Roadmap

Status legend: **Planned** · **In progress** · **Implemented** · **Tested** · **Blocked**

A feature is **Tested** only when its tests exist and were executed successfully, and (where it
touches identity or data) when the end-to-end path has been exercised. UI existence alone never
advances status (`AGENTS.md` §32).

Last updated: 2026-10-21

## Milestone tracker

| Milestone | Spec phase | Status | Exit evidence |
|---|---|---|---|
| M0 Foundation & plan | Phase 0 | **Tested** | `PLAN.md`, `docs/architecture.md`, `docs/roadmap.md`, `docs/deployment.md`, `scripts/verify_env.ps1`; repo initialised, design tokens and app shell running |
| M1 Platform foundation | Phase 1 | **Tested** | Supabase Auth + hosted Postgres; JWKS-verified token → profile → workspace creation exercised end to end (see below); 97 backend / 19 frontend tests; lint, format, mypy, typecheck, build and bundle secret scan green |
| M2 Agents, providers, tools, runtime | Phase 2 | Planned | real agent executes a registered tool, run + trace persisted |
| M3 Safety, approvals, observability | Phase 3 | Planned | approvals bound to canonical hash; security suite green |
| M4 Workflow builder | Phase 4 | Planned | multi-step workflow built, validated, executed with node traces |
| M5 Dashboard & Model Lab | Phase 5 | Planned | dashboard metrics match persisted fixtures; model comparison reproducible |
| M6 Evaluations & Knowledge | Phase 6 | Planned | suite reproduces; documents ingest & retrieve with citations |
| M7 Automation, memory, multi-agent | Phase 7 | Planned | durable jobs, schedules, webhooks, memory, multi-agent |
| M8 Release hardening | Phase 8 | Planned | 20/20 release acceptance checklist evidenced |

### M1 evidence

| Check | Result |
|---|---|
| Schema authority | `supabase/migrations/20261021120000_initial_identity_schema.sql` applied to the hosted project (`supabase db push`) |
| Tables / policies | 7 tables in `app`, RLS on all, 20 policies, no grants to `anon`/`authenticated`/`service_role` |
| Token verification | Real Supabase-issued ES256 token (`kid=c1cd368a-…`) verified via the project JWKS |
| Identity → workspace | `GET /api/v1/me` provisioned `app.profiles`; `POST /api/v1/workspaces` returned 201 and persisted an `owner` membership |
| Negative path | Invalid bearer token → `401` with the standard error envelope |
| Backend tests | 97 passed (`pytest`), including migration application, RLS assertions and token-verification unit tests |
| Frontend checks | `npm run lint` 0 errors, `npm run typecheck`, `npm run test` 19 passed, `npm run build` + secret scan |
| Test data | Removed; hosted `auth.users` / `app.*` row counts returned to 0 |

Details and the exact operating contract: [`docs/supabase.md`](supabase.md).

## Module status (spec §8–§23)

| Module | Priority | Status | Notes |
|---|---|---|---|
| A. Executive dashboard | P0 | In progress | shell + placeholder dashboard from M0; real metrics with M5 |
| B. Agent studio | P0 | Planned | drafts, immutable published versions, rollback |
| C. Visual workflow builder | P0 | Planned | 13 node contracts, validated graph, interpreter |
| D. Agent runtime & tool registry | P0 | Planned | 20-step lifecycle, 9 built-in CRM tools |
| E. Model providers & Model Lab | P0 (Lab P1) | Planned | ollama / openai-compatible / anthropic / simulation |
| F. Runs, traces, debugging | P0 | Planned | persisted cursor recovery, safe replay |
| G. Evaluation & regression | P0/P1 | Planned | deterministic evaluators, gates, ≥30 cases |
| H. Knowledge Hub & RAG | P1 | Planned | pgvector available on Supabase; local PG lacks it |
| I. Agent memory | P1 | Planned | typed memory, expiry, provenance |
| J. Approvals & governance | P0 | Planned | canonical-hash binding, budgets, pause switch |
| K. Tools & integrations | P0/P1 | Planned | connector contract, SSRF-safe generic HTTP |
| L. Scheduling & automation | P1 | Planned | `pgmq` + `pg_cron` + `pg_net` |
| M. Multi-agent orchestration | P2 | Planned | last, after single-agent reliability |
| N. Workspaces, users, access control | P0 | **Tested (M1)** | Supabase Auth, profiles, workspaces, members, 6-role matrix, audit, RLS |
| O. Analytics & usage | P0/P1 | Planned | percentiles, cost per successful task, turnaround |
| P. Developer platform | P1/P2 | Planned | `api_keys` table exists; authentication/UI later |

## Platform components

| Component | Status | Notes |
|---|---|---|
| Design system & tokens | **Tested (M0)** | semantic dark/light tokens, primitives, documented in `docs/design-system.md` |
| App shell & navigation | **Implemented (M0)** | sidebar, top bar, workspace switcher, command palette shell |
| API `/api/v1` | **Tested (M1)** | system, auth-mode, identity, workspaces, members; error envelope |
| Error taxonomy (§27) | **Tested (M1)** | full code list with status/retry/terminal/alert metadata |
| Authentication | **Tested (M1)** | Supabase JWKS verification + local dev issuer |
| Persistence | **Tested (M1)** | SQL migrations, SQLAlchemy 2 async, pooler-safe settings |
| Row Level Security | **Tested (M1)** | 20 policies, SQL regression assertions in the pytest suite |
| Observability | **Implemented (M1)** | structured JSON logs, request ids, rejection reasons; metrics/OTel later |
| CI | **Implemented (M1)** | backend lint/format/mypy/tests + frontend lint/typecheck/test/build/secret scan |
| Deployment | In progress | Supabase-first runbook written; container path unverified (no Docker) |
| Docs set | **Tested (M1)** | architecture, supabase, security, database schema, API, design system, deployment, roadmap |

## Deviations from spec (documented, reversible)

| ID | Decision | Status |
|---|---|---|
| D1 | pgvector absent on the local PostgreSQL 18 test instance | Reversible: Supabase has `vector`; retrieval lands in M6 and is tested on Supabase/local-with-extension |
| D2 | No Redis; in-process event bus behind an interface | Reversible; Supabase Realtime is the planned cross-process transport |
| D3 | No Temporal; durable work uses `pgmq` + an in-process worker | Reversible |
| D4 | Docker absent locally; `supabase start`/Compose unverified | Environmental, not architectural |
| D5 | Ollama absent; adapters land in M2 with health diagnostics | Environmental |
| D6 | No cloud provider key; no live paid calls (also a CI rule) | Intentional |
| D7 | Windows requires the selector event loop (`python -m app`) | Platform constraint; documented |

## Known limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Supabase email confirmation is enabled; no secret key/PAT supplied | A real UI sign-up stops at “confirm your email” | UI states it clearly; verification used an SQL-bootstrapped confirmed identity, then the real password grant |
| `supabase db lint` / advisors not run | Schema lint unverified on the hosted project | Needs an authenticated scoped CLI token; RLS is covered by SQL assertions |
| No Docker | `supabase start` and Compose unverified | Hosted project is the development target |
| Hosted project in `ap-northeast-2` | Extra round-trip per query (~⅓–¾ s per API call from this machine) | Deploy near users; pool connections |
| API-key authentication not wired | `app.api_keys` is schema-only | Documented; lands with the developer platform |

## Delivery log

| Date | Milestone | Outcome |
|---|---|---|
| 2026-10-21 | M0 | Repo initialised: monorepo, design tokens, app shell, backend layering, error taxonomy, plan and architecture docs, environment audit. |
| 2026-10-21 | M1 | Supabase identity + hosted Postgres cut-over. Migration applied (7 tables, RLS, 20 policies). Backend 97 tests, frontend 19 tests, lint/format/mypy/typecheck/build/secret scan green. Live JWKS-verified token → profile → workspace → membership verified against the hosted project; test data removed. |
