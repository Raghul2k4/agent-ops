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
| M2 Agents, providers, tools, runtime | Phase 2 | **Tested** | a real agent executes registered tools against synthetic CRM data; runs, events and trace spans persisted; exercised with the labelled deterministic provider **and** a hosted cloud model (OpenRouter) |
| M3 Safety, approvals, observability | Phase 3 | **Tested** | a high-risk tool pauses the run; a reviewer decides the exact payload; the run resumes and only then does the record change |
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

### M3 evidence

| Check | Result |
|---|---|
| Schema authority | `supabase/migrations/20261021140000_safety_approvals_observability.sql` applied to the hosted project and to the local test database |
| Tables / policies | 3 new tables in `app` (workspace policies, approval requests, run checkpoints) with 12 policies; RLS on all three |
| Approval pause | A high-risk tool (`mark_deal_contacted`) stopped the run: `approval.required` → `run.awaiting_approval`, the deal was **not** modified |
| Decision | Approving the quoted payload hash in the browser resumed the run: `run.resumed` → the tool executed → `run.succeeded` (3 model calls, 2 tool calls, 1 925 tokens) |
| Tampered payload | A decision with a different hash was refused with `APPROVAL_MISMATCH`; the run stayed paused and the record stayed unchanged |
| Rejection | Rejecting ended the run with `APPROVAL_REJECTED`; the record stayed unchanged |
| Expiry | An aged request was refused with `APPROVAL_EXPIRED` |
| Policy | A blocked tool, the emergency pause, a disabled agent and the run quota each refused the run with `POLICY_VIOLATION` / `RATE_LIMITED` |
| Safe replay | Replaying a run re-ran the scenario and stopped the write action for a **fresh** decision; the replay links to the source run |
| Tenant isolation | Another workspace received `404` for the approval list, the detail and the decision |
| Security suite | 13 cases: tenant isolation, tool-set boundary, argument validation, injection, secret handling, privilege escalation, idempotency |
| Backend tests | 188 passed (`pytest`), including the 13 approval-flow cases and the 13 security cases |
| Frontend checks | `npm run lint` 0 errors, `npm run typecheck`, `npm run test` 32 passed, `npm run build` + bundle secret scan |
| Browser end-to-end | Pause → queue → approve → resume → execute, plus the rejection path, the emergency pause and the policy editor, all against the hosted project |

---

### M2 evidence

| Check | Result |
|---|---|
| Schema authority | `supabase/migrations/20261021130000_agents_providers_tools_runtime.sql` applied to the hosted project and to the local test database |
| Agent lifecycle | draft → save → publish (immutable `agent_versions` snapshot) → run → persisted `agent_runs`, `run_events`, `trace_spans`; rollback, duplicate and archive available |
| Deterministic demo | Sales Operations Assistant (simulation provider) succeeded in 9.08 s: 3 model calls, **2 tool calls** (`search_deals`, `create_followup_draft`), 2 333 tokens, cost unavailable (no pricing metadata) and a `[SIMULATED]`-prefixed result |
| Hosted cloud model | `dots-studio/dots-3-note-preview:free` on OpenRouter: 3 model calls, 2 tool calls (`search_customers`, `get_customer_summary`), 3 943 tokens, USD 0.0000 (free model, priced from the provider's own rates) |
| Bounded failure | The same sales prompt on the free preview model exhausted the tool-call budget; the run failed with `EXECUTION_LIMIT_EXCEEDED` and persisted the 8 completed actions instead of an empty result |
| Approval gate | `mark_deal_contacted` (high risk) pauses the run with `awaiting_approval`, a canonical argument hash and no execution (decisions land in M3) |
| Provider health | OpenRouter connection test succeeded and listed the provider's model catalogue; credentials are referenced by environment-variable name and never returned |
| Backend tests | 159 passed (`pytest`), including the duplicate-call guard and the budget-reporting behaviour |
| Frontend checks | `npm run lint` 0 errors (7 pre-existing Fast Refresh warnings), `npm run typecheck`, `npm run test` 22 passed, `npm run build` + bundle secret scan |
| RLS | `supabase/tests/rls_policies.sql` passes on the hosted project for the M2 tables |

## Module status (spec §8–§23)

| Module | Priority | Status | Notes |
|---|---|---|---|
| A. Executive dashboard | P0 | In progress | shell + placeholder dashboard from M0; real metrics with M5 |
| B. Agent studio | P0 | **Tested (M2)** | drafts, immutable published versions, rollback, duplicate, archive; model/tool/limit configuration |
| C. Visual workflow builder | P0 | Planned | 13 node contracts, validated graph, interpreter |
| D. Agent runtime & tool registry | P0 | **Tested (M2)** | 20-step lifecycle, 9 built-in CRM tools, budgets, cancellation, duplicate-call guard |
| E. Model providers & Model Lab | P0 (Lab P1) | **Tested (M2)** | ollama / openai-compatible / anthropic / simulation; health checks, capability and pricing metadata; comparison lands in M5 |
| F. Runs, traces, debugging | P0 | **Tested (M2/M3)** | persisted events with cursor recovery, hierarchical trace spans, run detail, server-side filters and safe replay |
| G. Evaluation & regression | P0/P1 | Planned | deterministic evaluators, gates, ≥30 cases |
| H. Knowledge Hub & RAG | P1 | Planned | pgvector available on Supabase; local PG lacks it |
| I. Agent memory | P1 | Planned | typed memory, expiry, provenance |
| J. Approvals & governance | P0 | **Tested (M3)** | canonical-hash approvals with resume, policy document, allow/deny lists, rate limits, quota, emergency pause |
| K. Tools & integrations | P0/P1 | **Tested (M2)** | built-in tool registry and execution; external connectors land later |
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
| API `/api/v1` | **Tested (M1–M3)** | system, auth-mode, identity, workspaces, members, agents, providers, models, tools, runs, traces, policies, approvals; error envelope |
| Error taxonomy (§27) | **Tested (M1–M3)** | full code list with status/retry/terminal/alert metadata, plus `APPROVAL_MISMATCH` and `APPROVAL_REJECTED` |
| Authentication | **Tested (M1)** | Supabase JWKS verification + local dev issuer |
| Persistence | **Tested (M1–M3)** | SQL migrations, SQLAlchemy 2 async, pooler-safe settings |
| Row Level Security | **Tested (M1–M3)** | 32 policies across the M1–M3 tables, SQL regression assertions in the pytest suite |
| Observability | **Implemented (M1–M3)** | structured JSON logs, request ids, rejection reasons, live event stream with cursor recovery; metrics/OTel later |
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
| D8 | Model capability metadata is tri-state (unknown / supported / not supported) | Intentional: the platform never asserts a capability it has not confirmed |
| D9 | An identical tool call inside one run is executed once and reused | Intentional: protects against a model duplicating a side effect |
| D10 | A run's published tool set is enforced server-side | Intentional: a model may only call the tools its version was granted |
| D11 | A replay re-requests a human decision for irreversible actions | Intentional: a replay never repeats a business-record change on its own |
| D12 | The approval resume runs in-process after the decision | Reversible: the durable queue worker (M7) takes over the same entry point |

## Known limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Supabase email confirmation is enabled; no secret key/PAT supplied | A real UI sign-up stops at “confirm your email” | UI states it clearly; verification used an SQL-bootstrapped confirmed identity, then the real password grant |
| `supabase db lint` / advisors not run | Schema lint unverified on the hosted project | Needs an authenticated scoped CLI token; RLS is covered by SQL assertions |
| No Docker | `supabase start` and Compose unverified | Hosted project is the development target |
| Hosted project in `ap-northeast-2` | Extra round-trip per query (~⅓–¾ s per API call from this machine) | Deploy near users; pool connections |
| API-key authentication not wired | `app.api_keys` is schema-only | Documented; lands with the developer platform |
| `search_knowledge` returns an empty result | No knowledge documents exist before M6 | The tool states that the corpus is empty instead of inventing an answer |
| Free hosted preview model loops on tool calls | The sales prompt fails with `EXECUTION_LIMIT_EXCEEDED` on that model | The budget is enforced and the completed actions are reported; the deterministic provider is the reference behaviour |
| Provider model catalogues are large | The connection test returns a large list of model ids | Only the first ids are surfaced in the UI notice; registration is explicit |
| The approval resume is in-process | A restart between the decision and the resume leaves the run paused | The run keeps its checkpoint, so the worker (M7) can pick it up; the UI shows the paused state |
| A paused run's duration includes the review time | The wall-clock duration is longer than the execution time | Start and completion timestamps are both persisted and shown, so the pause is visible |
| Per-tool rate limits are counted from the event log | A busy minute is measured over persisted events, not an in-memory counter | The count is exact for the workspace and survives restarts; a high-volume deployment moves the counter to `pgmq`/Redis |

## Delivery log

| Date | Milestone | Outcome |
|---|---|---|
| 2026-10-21 | M0 | Repo initialised: monorepo, design tokens, app shell, backend layering, error taxonomy, plan and architecture docs, environment audit. |
| 2026-10-21 | M1 | Supabase identity + hosted Postgres cut-over. Migration applied (7 tables, RLS, 20 policies). Backend 97 tests, frontend 19 tests, lint/format/mypy/typecheck/build/secret scan green. Live JWKS-verified token → profile → workspace → membership verified against the hosted project; test data removed. |
| 2026-10-21 | M2 | Agents, providers, tools and runtime. Migration applied (M2 tables, RLS, policies). Backend 159 tests, frontend 22 tests, lint/format/mypy/typecheck/build/secret scan green. Verified in a real browser against the hosted project: workspace → provider → agent → publish → run → trace, first with the labelled deterministic provider and then with a hosted cloud model (OpenRouter). Fixed a tool-call accounting defect, added a duplicate-call guard, bounded-failure reporting and tri-state capability metadata. |
| 2026-10-21 | M3 | Safety, approvals and observability. Migration applied (3 tables, 12 policies). Backend 188 tests (13 approval-flow, 13 security), frontend 32 tests, lint/format/mypy/typecheck/build/secret scan green. Verified in a real browser against the hosted project: a high-risk tool paused the run, the exact payload was approved in the approval queue, the run resumed and only then did the business record change; the rejection path, the tampered-payload refusal, the emergency pause and the safe replay were exercised too. Closed a real gap: a model can no longer call a tool its published version was not granted. |
