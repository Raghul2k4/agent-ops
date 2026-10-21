# AgentOps — Architecture

Companion to `PLAN.md` (plan of record) and `docs/roadmap.md` (status board).
Last updated: 2026-10-21. Status: M0 + M1 implemented and verified; later sections describe the
agreed design for milestones that are still planned, and are marked as such.

**Platform:** Supabase is the application platform (Postgres, Auth, Storage, Realtime, Queues,
scheduling). FastAPI remains the only business-logic API; React + TypeScript remains the only UI.

---

## 1. System context

AgentOps is a multi-tenant web platform for designing, running, inspecting and governing AI agents.
It has four runtime tiers:

1. **Identity plane** (Supabase Auth): sign-up, sign-in, refresh, confirmation, MFA later. The
   browser obtains an access token; FastAPI verifies it against the project JWKS.
2. **Control plane** (FastAPI + Supabase Postgres): profiles, workspaces, configuration, persisted
   history. Business logic lives here, never in Postgres functions or the browser.
3. **Execution plane**: agent runtime, tool executor, workflow interpreter — in-process for v1,
   behind interfaces that allow later extraction into durable workers.
4. **Integration plane**: model providers (Ollama / OpenAI-compatible / Anthropic / simulation),
   connectors (synthetic CRM, knowledge, generic HTTP).

```
Browser ──sign in──▶ Supabase Auth ──access token (ES256)──┐
   │                                                       │
   │ Authorization: Bearer <token>                         │
   ▼                                                       ▼
FastAPI /api/v1 ──▶ auth verifier ──▶ JWKS ────────────────┘
   │
   ├──▶ services ──▶ repositories ──SQL/TLS──▶ Supabase Postgres (app schema, RLS)
   │
   └──▶ agent runtime ──▶ providers (Ollama / cloud / simulation)
              └──▶ tool executor ──▶ CRM / knowledge / connectors
```

The Data API (PostgREST) is not used for domain data: the browser never queries `app.*` directly,
so there is exactly one authorization surface.

---

## 2. Backend layering (enforced)

```
app/api/v1/routers   HTTP concerns only: parse, authz dependency, call service, map result
app/services         business logic, transaction boundaries, orchestration
app/core             config, errors, security, permissions, logging, rate limiting
app/{agents,tools,workflows,policies,approvals,providers,evaluations,knowledge,jobs}
                     pure domain: no FastAPI imports, no request/response awareness
app/repositories     tenant-scoped SQLAlchemy data access (workspace_id always applied)
app/models           SQLAlchemy ORM mappings
app/db               engine/session/DeclarativeBase/JSON+UUID type helpers
```

Rules:
- Domain packages must not import `fastapi`.
- Repositories must not import services.
- No module may query the DB directly outside `repositories/` (enforced by review + grep check in CI).
- Services own transaction boundaries; model calls never run inside a long-lived transaction.

---

## 3. Agent execution lifecycle

The runtime implements the 20-step lifecycle from `AGENTS.md` §11. Each step maps to a runtime
module and emits a persisted `run_events` row plus a `trace_spans` entry.

| # | Step | Module | Failure mode |
|---|---|---|---|
| 1–3 | accept, authenticate, resolve workspace/resource | `api/v1/deps.py`, `services/runs.py` | `AUTHENTICATION_REQUIRED`, `RESOURCE_NOT_FOUND` |
| 4 | authorization | `core/permissions.py` | `PERMISSION_DENIED` |
| 5 | validate request + configuration | `schemas/agents.py` | `VALIDATION_ERROR` |
| 6 | create persistent run record | `services/runs.py` | — |
| 7 | load immutable agent version | `services/agents.py` | `RESOURCE_NOT_FOUND` |
| 8 | init limits + trace context | `runtime/engine.py` (`Usage`, `_check_budget`) | `EXECUTION_LIMIT_EXCEEDED` |
| 9 | invoke model | `providers/*` via `providers/factory.py` | `PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT` |
| 10–13 | validate tool call, resolve, validate args, enforce risk policy | `tools/executor.py`, `tools/base.py` | `INVALID_TOOL_ARGUMENTS`, `POLICY_VIOLATION` |
| 14–15 | pause for approval, execute permitted tool | `tools/executor.py` (approval gate) | `APPROVAL_REQUIRED`, `APPROVAL_EXPIRED` |
| 16 | persist sanitized result + trace event | `runtime/engine.py` (`_emit`) | — |
| 17 | continue within limits | `runtime/engine.py` (`RunLedger`) | `EXECUTION_LIMIT_EXCEEDED` |
| 18–20 | final result / controlled failure, persist terminal status, emit completion | `runtime/engine.py` (`_finalize`) | `INTERNAL_ERROR` |

**Tool-call trust model:** a model may only *propose* a tool call. The runtime resolves the tool
from the server-side registry, validates arguments against the tool's strict schema
(`extra="forbid"`), checks the agent's tool set and the workspace role's permissions, applies risk
policy (approval, timeout, idempotency) and only then executes.

**Duplicate calls:** the run keeps a `RunLedger` of executed calls keyed by a hash of
`(tool, arguments)`. An identical call inside the same run is **not** executed again: the recorded
result is reused and a `tool.cached` event is emitted. A model therefore cannot duplicate a side
effect by repeating itself.

**Tool-set boundary:** the published version fixes the tool set. A call to a tool the version was
not granted is refused with `POLICY_VIOLATION` before the tool body runs, whatever the model — or a
tool result — asked for.

**Budgets:** `max_steps`, `max_tool_calls`, `max_wall_clock_seconds`, `max_total_tokens`,
`max_cost_usd`. Exceeding any of them ends the run with `EXECUTION_LIMIT_EXCEEDED` — it never
silently truncates, and the failure output carries `stopped_because` plus the `completed_actions`
the run did perform.

**Approvals (M3):** a call that the policy marks as approval-worthy does not execute. The runtime
writes an `app.approval_requests` row bound to the SHA-256 hash of the canonical
`{tool, arguments}` payload, stores a `app.run_checkpoints` row with the conversation and the
pending call, and the run ends in `awaiting_approval`. A reviewer's decision must quote the same
hash; on approval the run resumes from the checkpoint, re-validates the tool against the current
policy and the published tool set, and only then executes it. A rejection or an expiry ends the run
with the business record untouched.

**Retries:** only for idempotent operations and only for retryable error classes
(`PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`) with exponential backoff + jitter.

---

## 4. Provider abstraction

```python
class Provider(Protocol):
    async def health(self) -> ProviderHealth: ...
    async def list_models(self) -> list[ModelCapability]: ...
    async def complete(self, req: ModelRequest) -> ModelResponse: ...
    async def stream(self, req: ModelRequest) -> AsyncIterator[ModelChunk]: ...   # optional
    def estimate_cost(self, usage: Usage) -> CostEstimate | None: ...
```

- Typed contracts: `ModelRequest`, `ModelResponse`, `ModelToolCall`, `ModelUsage`, `ProviderError`,
  `ProviderCapabilities`.
- Capability metadata is tri-state: `true`, `false` or `null` for **unknown**. The platform never
  asserts a capability it has not confirmed, and the UI shows an unknown capability as unknown
  instead of assuming support.
- Adapters: `ollama` (local), `openai_compatible` (OpenAI, Groq, Together, vLLM, OpenRouter),
  `anthropic`, `simulation` (deterministic, offline, always labelled `[SIMULATED]`).
- Credentials are referenced by environment-variable name (`secret_reference`) and resolved from
  the process environment at call time; they are never stored in the database.
- Pricing is external metadata attached to a model registration; when pricing is unknown the run
  reports `estimated_cost: null` and the UI says "cost unavailable" — never a fabricated number.

---

## 5. Workflow execution

**Definition** (versioned JSON): `workflow_version.graph_json` holds nodes
(`id`, `type`, `position`, `config`), edges (`source`, `source_port`, `target`, `target_port`),
input/output schemas, execution policies, and version metadata.

**Validation** (pure function, no I/O) rejects: duplicate IDs, dangling edges, unknown node
types, invalid port connections, unreachable nodes, cycles outside declared loop nodes,
unbounded loops, missing required inputs, and unsafe configs (e.g. `exec`/`eval` style configs
are not expressible — transforms are declarative mappings only).

**Interpretation:**
1. Load immutable workflow version; validate; snapshot inputs.
2. Compute execution order (topological sort with declared loop nodes handled as bounded
   sub-iterations).
3. Execute ready nodes; bounded concurrency for parallel branches; merge nodes join on
   configured strategy.
4. Each node emits `run_events` (node_started / node_completed / node_failed) and a `trace_span`
   with sanitized inputs/outputs and duration.
5. Human-approval node pauses the run (`status=awaiting_approval`) with a persisted checkpoint;
   the approval decision resumes execution from that node.
6. Terminal states are always persisted (`succeeded`, `failed`, `cancelled`, `awaiting_approval`).

**Never** execute arbitrary code from a definition: there is no `eval`, no dynamic import, no
shell, no model-generated SQL.

---

## 6. Persistence and tenancy

- **Supabase Postgres** is the source of truth. `supabase/migrations/*.sql` is the single schema
  authority; there is no Alembic and no runtime `create_all`.
- Domain tables live in the non-exposed **`app`** schema. `auth`, `storage` and `extensions` belong
  to Supabase. Privileged helpers live in `app_private`.
- Every tenant-owned table has `workspace_id NOT NULL` with FK constraints and
  `ON DELETE CASCADE`; repositories always filter by the resolved workspace.
- Composite unique constraints enforce tenant scope, e.g.
  `UNIQUE(workspace_id, user_id)` on `workspace_members`.
- All timestamps are `timestamptz` UTC; the API serializes ISO-8601 with `Z`.
- JSON payloads use `JSONB`; UUID primary keys are generated by the database.
- **Row Level Security is enabled on every table** (20 policies in M1) and mirrored in CI by SQL
  assertions. The API connects as the database owner and authorizes in the service layer; RLS is the
  independent second control that makes accidental Data API exposure harmless.
- The application uses the **transaction pooler** (port 6543) with
  `prepare_threshold=None`, explicit `statement_timeout` and
  `idle_in_transaction_session_timeout`. Slow model calls never run inside a transaction.
- Schema details and the per-table policy catalogue: [`database-schema.md`](database-schema.md).

---

## 7. Event streaming (SSE)

- `run_events` is the durable log: `(run_id, sequence_number)` unique, append-only.
- Writers persist first, then publish to an in-process `EventBus` (async pub/sub); the SSE
  handler tails from the DB using `after_seq` cursor.
- Client reconnect: `GET /api/v1/runs/{run_id}/events/stream?after_seq=N` replays missed events.
- Terminal events (`run.completed|failed|cancelled`) close the stream.
- The bus interface is pluggable → Redis pub/sub later (deviation D2) without changing clients.

---

## 8. Background processing

- `background_jobs` table is the durable queue: `job_type`, `resource_id`, `status`,
  `attempt_count`, `scheduled_at`, `lease_until`, `last_error`.
- v1 worker: in-process asyncio pool claiming rows with `FOR UPDATE SKIP LOCKED`, lease + heartbeat,
  exponential backoff with jitter, max attempts → dead-letter status.
- Schedules compute `next_run_at` (timezone-aware) and enqueue jobs; webhook triggers validate
  an HMAC signature and enforce a replay window before enqueueing.
- Graceful shutdown drains leases; a recovery sweep re-queues expired leases.

---

## 9. Security boundaries

| Boundary | Enforcement point |
|---|---|
| Identity | Supabase Auth owns credentials; the API verifies the bearer token cryptographically against the project JWKS (algorithm allowlist, `iss`, `aud`, `exp`, `sub`) and never trusts a header-supplied identity |
| Tenant | repository scoping + `workspace_id` FK + membership resolution server-side + RLS |
| Role | `core/permissions.py` matrix checked by dependency factories, not by the client |
| Tool | registry allowlist → schema validation → permission check → risk policy → (approval) → execution |
| Approval | canonical JSON → SHA-256 → compare on execution; expiry + policy version re-checked |
| Secret | `secret_reference` indirection; masked responses; redaction filter applied to logs and traces |
| Network | URL allowlist + DNS/IP validation + redirect re-validation + size/timeout caps (SSRF) |
| Upload | size/type/content validation, safe parsers, storage outside app dirs, no path traversal |
| Execution | budgets, depth/step caps, cycle detection, no dynamic code paths |

Untrusted content (user input, retrieved documents, tool output, web content) is always tagged as
data, never as instruction, and never grants permission.

---

## 10. Architecture decision records (ADR summary)

Full ADRs are added under `docs/adr/` as implementation lands.

| ADR | Decision | Status |
|---|---|---|
| ADR-001 | Custom agent runtime instead of LangChain/LlamaIndex | Accepted |
| ADR-002 | SQLAlchemy 2 async + psycopg3 over asyncpg | Accepted |
| ADR-003 | Supabase Auth owns identity; the API verifies bearer tokens via JWKS. No server-side session table, no header-trusted identity | Accepted (M1) |
| ADR-004 | Provider capability metadata drives UI exposure of parameters | Accepted |
| ADR-005 | `simulation` provider is a first-class, explicitly-labelled adapter | Accepted |
| ADR-006 | Persist events before publishing; recover with a sequence cursor | Accepted |
| ADR-007 | Supabase `app` schema + RLS as the second authorization layer; domain tables unreachable through the Data API | Accepted (M1) |
| ADR-008 | Supabase Queues (`pgmq`) + an in-process worker instead of Redis/Temporal | Accepted (deviations D2, D3) |
| ADR-009 | Declarative workflow transforms only; no dynamic code execution | Accepted |
| ADR-010 | PostgreSQL is mandatory (no SQLite fallback) to avoid dialect drift | Accepted |
| ADR-011 | Supabase CLI SQL migrations are the only schema authority (Alembic retired) | Accepted (M1) |
| ADR-012 | Development-only HS256 issuer for tests, refused in staging/production | Accepted (M1) |

---

## 11. Frontend architecture

- Feature-sliced: `features/<area>` owns its components, hooks, schemas and API calls;
  `components/ui` owns the reusable design-system primitives; `lib` owns shared utilities
  (api client, formatters, permissions); `routes` owns the route table and guards.
- Server state: TanStack Query with per-feature query keys, stale times and invalidation on
  mutations. Client state: Zustand only for genuinely shared UI state (sidebar, workspace
  selection, command palette).
- Forms: React Hook Form + Zod; the same Zod schemas are mirrored on the backend.
- API contract: `lib/api-client.ts` performs fetch + typed error mapping; response payloads are
  validated with Zod at the boundary to catch backend drift early.
- Performance: route-level code splitting, lazy loading of the workflow canvas and trace views,
  memoised table rows, virtualised long lists.
- Accessibility: semantic landmarks, visible focus rings, `aria-*` on overlays, status conveyed
  with text as well as colour, `prefers-reduced-motion` respected, chart alternatives in tables.

---

## 12. Testing architecture

- Backend: pytest with `unit`, `integration`, `security`, `eval` tiers; async tests via
  `pytest-asyncio`. A session-scoped fixture recreates the schemas in a disposable PostgreSQL
  database and applies the **same** `supabase/migrations/*.sql` files with `psql`, then runs
  `supabase/tests/rls_policies.sql`. There is no SQLite fallback and no second schema definition.
- Provider adapters are tested against mocked transports (no live paid calls, ever, in CI).
- Frontend: Vitest + Testing Library for units; Playwright for the 12 mandated journeys against
  a compose stack with stubbed provider endpoints.
- Security tests assert negative behaviour (denials, tampering, isolation) rather than just
  happy paths.

---

## 13. Known limitations of this architecture (to be revisited)

1. In-process workers are single-node; durable execution moves to `pgmq` workers (M7).
2. pgvector is unavailable on the local PostgreSQL 18 test instance; retrieval is developed and
   tested against Supabase/local-with-extension (deviation D1).
3. Live event streaming is served by the API process until Supabase Realtime is wired (M3).
4. The simulation provider must never be enabled implicitly; it requires explicit workspace opt-in.
5. The hosted development project is in `ap-northeast-2`, so each query pays a cross-region round
   trip; deploy the API close to the database.
6. Email confirmation is enabled on the hosted project and no service key/PAT is stored here, so a
   real UI sign-up stops at the confirmation step (the message is explicit, not a silent failure).
