# AgentOps

**AI agent engineering, orchestration, observability, evaluation and governance platform.**

AgentOps lets a team design AI agents and visual workflows, execute them against approved tools
and models, inspect every execution trace, benchmark model quality, and govern what agents are
allowed to do.

> **Status: under active construction (M0–M1).** The authoritative build plan is
> [`PLAN.md`](PLAN.md); feature status is tracked in [`docs/roadmap.md`](docs/roadmap.md);
> architecture is in [`docs/architecture.md`](docs/architecture.md); local setup is in
> [`docs/deployment.md`](docs/deployment.md).
>
> Nothing in this repository is mocked-up "success": features land only when their backend,
> persistence, authorization and tests exist and have been run.

---

## What it does

| Capability | Scope |
|---|---|
| **Build** | Agents with versioned configuration; visual workflow canvas with 13 node contracts |
| **Execute** | Custom agent runtime, registered tools, provider abstraction (Ollama / OpenAI-compatible / Anthropic / labelled simulation) |
| **Observe** | Persistent run history, hierarchical traces, live SSE updates, safe replay |
| **Evaluate** | Suites, deterministic + model-judged scorers, regression gates, reproducible benchmarks |
| **Govern** | Role-based access, tool allowlists, budgets, human-in-the-loop approvals, audit log |

---

## Repository layout

```
agentops/
├── apps/web/          React 19 + TypeScript + Vite + Tailwind + shadcn/ui frontend
├── backend/           FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 backend
│   ├── app/           api/ services/ domain packages/ repositories/ models/
│   └── tests/         unit/ integration/ security/ eval/
├── evals/             datasets, suites, reports
├── docs/              architecture, database schema, API reference, security, design system, deployment, roadmap
├── infra/             container and proxy configuration
├── scripts/           bootstrap.ps1, verify_env.ps1, seed_demo.py
└── docker-compose.yml
```

---

## Quick start

```powershell
# 1. Verify the machine (optional services are reported separately)
.\scripts\verify_env.ps1

# 2. Bootstrap
.\scripts\bootstrap.ps1

# 3. Run
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000
cd apps\web; npm run dev
```

Database setup, including the local PostgreSQL credential reset runbook, is documented in
[`docs/deployment.md`](docs/deployment.md).

---

## Tests

```powershell
cd backend; python -m pytest -q          # unit + integration + security
cd apps\web; npm run test               # component tests
cd apps\web; npx playwright test         # end-to-end journeys
```

---

## Principles

- Server-side enforcement of every permission, policy and budget — prompts are not a security boundary.
- Tenant isolation on every workspace-owned record, enforced in the data layer.
- Human approval bound to an exact canonical action payload, re-verified at execution time.
- Honest states: unavailable providers, empty datasets and partial failures are shown as such.
- Simulation is a first-class but **explicitly labelled** mode; it is never mixed into live analytics.

---

## License

Internal project — all rights reserved.
