# AgentOps Roadmap

Status legend: **Planned** · **In progress** · **Implemented** · **Tested** · **Blocked**

A feature is **Tested** only when its tests exist and were executed successfully. UI existence
alone never advances status (`AGENTS.md` §32).

Last updated: 2026-10-21

## Milestone tracker

| Milestone | Spec phase | Status | Exit evidence |
|---|---|---|---|
| M0 Foundation & plan | Phase 0 | **Tested** | `PLAN.md`, `docs/roadmap.md`, `docs/architecture.md`, `docs/deployment.md`, `scripts/verify_env.ps1` — environment audit and setup runbook in place |
| M1 Platform foundation | Phase 1 | **In progress** | scaffold committed; backend unit tier passes (38 tests); integration tier and frontend build not yet executed (blocked on the PostgreSQL password) |
| M2 Agents, providers, tools, runtime | Phase 2 | Planned | real agent executes a registered tool, run + trace persisted |
| M3 Safety, approvals, observability | Phase 3 | Planned | approvals bound to canonical hash; security suite green |
| M4 Workflow builder | Phase 4 | Planned | multi-step workflow built, validated, executed with node traces |
| M5 Dashboard & Model Lab | Phase 5 | Planned | dashboard metrics match persisted fixtures; model comparison reproducible |
| M6 Evaluations & Knowledge | Phase 6 | Planned | suite reproduces; documents ingest & retrieve with citations |
| M7 Automation, memory, multi-agent | Phase 7 | Planned | durable jobs, schedules, webhooks, memory, multi-agent |
| M8 Release hardening | Phase 8 | Planned | 20/20 release acceptance checklist evidenced |

## Module status (spec §8–§23)

| Module | Priority | Status | Notes |
|---|---|---|---|
| A. Executive dashboard | P0 | Planned | metrics only from persisted rows |
| B. Agent studio | P0 | Planned | drafts, immutable published versions, rollback |
| C. Visual workflow builder | P0 | Planned | 13 node contracts, validated graph, interpreter |
| D. Agent runtime & tool registry | P0 | Planned | 20-step lifecycle, 9 built-in CRM tools |
| E. Model providers & Model Lab | P0 (Lab P1) | Planned | ollama / openai-compatible / anthropic / simulation |
| F. Runs, traces, debugging | P0 | Planned | SSE with persisted cursor, safe replay |
| G. Evaluation & regression | P0/P1 | Planned | deterministic evaluators, gates, ≥30 cases |
| H. Knowledge Hub & RAG | P1 | Planned | pgvector optional — see deviation D1 |
| I. Agent memory | P1 | Planned | typed memory, expiry, provenance |
| J. Approvals & governance | P0 | Planned | canonical-hash binding, budgets, pause switch |
| K. Tools & integrations | P0/P1 | Planned | connector contract, SSRF-safe generic HTTP |
| L. Scheduling & automation | P1 | Planned | durable jobs, signed webhooks |
| M. Multi-agent orchestration | P2 | Planned | last, after single-agent reliability |
| N. Workspaces, users, access control | P0 | Planned | server-side sessions, RBAC, tenant scoping |
| O. Analytics & usage | P0/P1 | Planned | percentiles, cost per successful task, turnaround |
| P. Developer platform | P1/P2 | Planned | API keys, webhooks, docs; SDK/CLI later |

## Platform components

| Component | Status | Notes |
|---|---|---|
| Design system & tokens | Planned | semantic tokens, dark-first + light theme |
| App shell & navigation | Planned | 11 nav areas, command palette |
| API `/api/v1` | Planned | typed envelopes, cursor pagination, idempotency keys |
| Error taxonomy (§27) | Planned | 17 codes, safe messages, retry/terminal flags |
| Observability | Planned | structlog JSON, request IDs, metrics interface, OTel-compatible hooks |
| CI | Planned | lint/typecheck/test/build/e2e; compose smoke |
| Deployment | Planned | compose profile, health checks, backup/restore runbook |
| Docs set | In progress | `architecture.md`, `roadmap.md`, `PLAN.md` written; rest land with their milestone |

## Deviations from spec (documented, reversible)

See `PLAN.md` §2.3 — D1 pgvector absent, D2 Redis absent, D3 Temporal omitted,
D4 Docker absent locally, D5 Ollama absent, D6 no cloud key.

## Known blockers

| Blocker | Impact | Owner |
|---|---|---|
| PostgreSQL 18 credentials unknown (`scram-sha-256`) | blocks M1 migrations and all integration tests | user (Q1) |
| No cloud provider API key | live-model demo path | user (Q2) |
| No Docker locally | compose path only verifiable in CI | mitigated (D4) |

## Delivery log

| Date | Milestone | Outcome |
|---|---|---|
| 2026-10-21 | M0 | Plan, architecture, roadmap, deployment runbook and setup scripts delivered. Environment audited: PostgreSQL 18 present (password outstanding), Docker/Redis/Ollama absent. |
| 2026-10-21 | M1 | Work paused by request with the foundation scaffold committed but **unverified** beyond the backend unit tier (38 tests passing). Remaining: integration/security tiers, frontend typecheck/build, CI green. |
