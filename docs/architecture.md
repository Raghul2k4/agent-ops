# AgentOps — Architecture

Companion to `PLAN.md` (plan of record) and `docs/roadmap.md` (status board).
Last updated: 2026-10-21. Status: initial architecture (M0).

---

## 1. System context

AgentOps is a single-tenant-per-workspace web platform for designing, running, inspecting and
governing AI agents. It has three runtime tiers:

1. **Control plane** (FastAPI + Postgres): identity, workspaces, configuration, persisted history.
2. **Execution plane**: agent runtime, tool executor, workflow interpreter — in-process for v1,
   behind interfaces that allow later extraction into durable workers.
3. **Integration plane**: model providers (Ollama / OpenAI-compatible / Anthropic / simulation),
   connectors (synthetic CRM, knowledge, generic HTTP).

```
Browser ──HTTP/JSON──▶ api/v1 ──▶ services ──▶ repositories ──▶ PostgreSQL
   │                        │           │                            │
   │                     SSE │           └── agent runtime ──▶ providers
   └────────────────────────┘                     └── tool executor ──▶ CRM/knowledge
```

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
| 1–3 | accept, authenticate, resolve workspace/resource | `api/deps.py`, `services/runs.py` | `AUTHENTICATION_REQUIRED`, `RESOURCE_NOT_FOUND` |
| 4 | authorization | `core/permissions.py` | `PERMISSION_DENIED` |
| 5 | validate request + configuration | `schemas/agents.py` | `VALIDATION_ERROR` |
| 6 | create persistent run record | `services/runs.py` | — |
| 7 | load immutable agent version | `services/agents.py` | `RESOURCE_NOT_FOUND` |
| 8 | init limits + trace context | `agents/runtime/budget.py` | `EXECUTION_LIMIT_EXCEEDED` |
| 9 | invoke model | `providers/*` | `PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT` |
| 10–13 | validate tool call, resolve, validate args, enforce risk policy | `tools/registry.py`, `policies/` | `INVALID_TOOL_ARGUMENTS`, `POLICY_VIOLATION` |
| 14–15 | pause for approval, execute permitted tool | `approvals/`, `tools/executor.py` | `APPROVAL_REQUIRED`, `APPROVAL_EXPIRED` |
| 16 | persist sanitized result + trace event | `repositories/runs.py` | — |
| 17 | continue within limits | `agents/runtime/loop.py` | `EXECUTION_LIMIT_EXCEEDED` |
| 18–20 | final result / controlled failure, persist terminal status, emit completion | `services/runs.py` | `INTERNAL_ERROR` |

**Tool-call trust model:** a model may only *propose* a tool call. The runtime resolves the tool
from the server-side registry, validates arguments against the tool's strict schema
(`extra="forbid"`), checks the agent's tool allowlist and the workspace role's permissions,
applies risk policy (approval, rate limit, idempotency), and only then executes.

**Budgets:** `max_steps`, `max_tool_calls`, `max_wall_clock_ms`, `max_tokens`,
`max_cost_usd`. Exceeding any of them ends the run with `EXECUTION_LIMIT_EXCEEDED` — it never
silently truncates.

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

- Typed contracts: `ModelRequest`, `ModelResponse`, `ToolCall`, `Usage`, `ProviderError`,
  `ModelCapability`.
- `ModelCapability` declares `supports_tools`, `supports_structured_output`,
  `supports_streaming`, `context_window`, `pricing` — the UI hides unsupported settings instead
  of pretending they work.
- Adapters: `ollama` (local), `openai_compatible` (OpenAI, Groq, Together, vLLM, OpenRouter),
  `anthropic`, `simulation` (deterministic, offline, always labelled `SIMULATED`).
- Pricing is an external, versioned table; when pricing is unknown the API returns
  `estimated_cost: null` + `cost_status: "unavailable"` — never a fabricated number.

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

- PostgreSQL 18 is the source of truth; Alembic owns the schema (no runtime `create_all`).
- Every tenant-owned table has `workspace_id NOT NULL` with FK constraints and
  `ON DELETE CASCADE`; repositories always filter by the resolved workspace.
- Composite unique constraints enforce tenant scope, e.g.
  `UNIQUE(workspace_id, user_id)` on `workspace_members`,
  `UNIQUE(agent_id, version_number)` on `agent_versions`.
- All timestamps are `timestamptz` UTC; the API serializes ISO-8601 with `Z`.
- JSON payloads use `JSONB` with a shared `JSONBType` mapping; UUIDs are app-generated `uuid4`.
- Row-level security is a planned defence-in-depth layer (`docs/security.md`), not the primary
  control — the primary control is tenant-scoped repositories + service authorization.

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
| Identity | `sessions` table + HttpOnly/Secure/SameSite cookie; argon2id; CSRF double-submit; rate limits on auth endpoints |
| Tenant | repository scoping + `workspace_id` FK + membership resolution server-side |
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
| ADR-003 | Server-side sessions + scoped hashed API keys; no header-trusted identity | Accepted |
| ADR-004 | Provider capability metadata drives UI exposure of parameters | Accepted |
| ADR-005 | `simulation` provider is a first-class, explicitly-labelled adapter | Accepted |
| ADR-006 | Persistence-before-publish SSE with sequence cursor | Accepted |
| ADR-007 | pgvector-optional embedding storage (float8[] + SQL cosine fallback) | Accepted (deviation D1) |
| ADR-008 | In-process worker over `background_jobs` table instead of Redis/Temporal | Accepted (deviations D2, D3) |
| ADR-009 | Declarative workflow transforms only; no dynamic code execution | Accepted |
| ADR-010 | PostgreSQL is mandatory (no SQLite fallback) to avoid dialect drift | Accepted |

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
  `pytest-asyncio`; a session-scoped fixture creates/refreshes the `agentops_test` database and
  applies Alembic migrations.
- Provider adapters are tested against mocked transports (no live paid calls, ever, in CI).
- Frontend: Vitest + Testing Library for units; Playwright for the 12 mandated journeys against
  a compose stack with stubbed provider endpoints.
- Security tests assert negative behaviour (denials, tampering, isolation) rather than just
  happy paths.

---

## 13. Known limitations of this architecture (to be revisited)

1. In-process workers are single-node; horizontal scaling requires the Redis/D2 path.
2. Embeddings without pgvector are linear-scan; acceptable at current data volumes.
3. SSE is served by the API process; a large fan-out would need a dedicated stream tier.
4. The simulation provider must never be enabled implicitly; it requires explicit workspace opt-in.
