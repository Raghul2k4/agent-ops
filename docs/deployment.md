# AgentOps — Local Environment Setup

This guide gets a working local AgentOps environment on Windows (the current development
machine). It is the authoritative local setup path; `docker-compose.yml` is the container
equivalent used in CI and production-like environments.

---

## 1. Prerequisites

| Component | Required | Verified on this machine |
|---|---|---|
| Python | 3.12 (3.14 also works for core stack) | 3.12.7 / 3.14.7 installed |
| Node.js | 20+ (24 recommended) | 24.20.0 |
| Git | 2.40+ | 2.55.0 |
| PostgreSQL | 14+ (18 used here) | 18 x64, running on 127.0.0.1:5432 |
| Docker | optional (CI/prod path) | not installed locally |
| Redis | optional (background jobs fallback) | not installed locally |

---

## 2. PostgreSQL access (do this first — it blocks migrations and tests)

The local PostgreSQL 18 install uses `scram-sha-256` for every connection, so the application
cannot connect until a password is set. The server itself is healthy; only credentials are
missing.

### 2.1 Reset the `postgres` superuser password (run as Administrator PowerShell)

This is a **local development machine only**. The trust window below is limited to
`127.0.0.1`/`::1` and is closed immediately afterwards.

```powershell
# 1. Stop the service
Stop-Service postgresql-x64-18

# 2. Open pg_hba.conf for editing
notepad "C:\Program Files\PostgreSQL\18\data\pg_hba.conf"

#    Change ONLY these two lines (from scram-sha-256 to trust):
#      host    all    all    127.0.0.1/32    scram-sha-256
#      host    all    all    ::1/128         scram-sha-256
#    Leave every other line untouched. Save and close.

# 3. Start the service again
Start-Service postgresql-x64-18

# 4. Set the postgres password (trust auth means no password is needed right now)
$env:PGPASSWORD = ""
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -d postgres -w `
    -c "ALTER USER postgres WITH PASSWORD 'CHANGE_ME_strong_local_password';"

# 5. Close the trust window again: in pg_hba.conf restore both lines to scram-sha-256
notepad "C:\Program Files\PostgreSQL\18\data\pg_hba.conf"
Stop-Service postgresql-x64-18
Start-Service postgresql-x64-18

# 6. Verify the new password works
$env:PGPASSWORD = "CHANGE_ME_strong_local_password"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -d postgres -w -c "select version();"
```

### 2.2 Create the least-privilege application role and databases

Run with the password from step 2.1. The app role is **not** a superuser; it only needs
`CREATEDB` so the test database can be created and dropped.

```powershell
$env:PGPASSWORD = "CHANGE_ME_strong_local_password"
$PSQL = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

& $PSQL -U postgres -h 127.0.0.1 -p 5432 -d postgres -w -c `
  "CREATE ROLE agentops WITH LOGIN PASSWORD 'agentops_local_dev' CREATEDB;"
& $PSQL -U postgres -h 127.0.0.1 -p 5432 -d postgres -w -c `
  "CREATE DATABASE agentops OWNER agentops;"
& $PSQL -U postgres -h 127.0.0.1 -p 5432 -d postgres -w -c `
  "CREATE DATABASE agentops_test OWNER agentops;"
```

### 2.3 Record the credentials

Copy `.env.example` to `backend/.env` and set:

```dotenv
DATABASE_URL=postgresql+psycopg://agentops:agentops_local_dev@127.0.0.1:5432/agentops
TEST_DATABASE_URL=postgresql+psycopg://agentops:agentops_local_dev@127.0.0.1:5432/agentops_test
```

> `.env` is git-ignored. Never commit real credentials.

### 2.4 pgvector (optional)

This PostgreSQL 18 install does **not** include the `pgvector` extension, so AgentOps stores
embeddings as `double precision[]` and computes cosine similarity in SQL (documented deviation
D1 in `PLAN.md`). The application detects `pgvector` automatically and will use the native
`vector` type and HNSW index once the extension is installed — no code change required.

---

## 3. Backend setup

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
alembic upgrade head
```

## 4. Frontend setup

```powershell
cd apps/web
npm install
npm run dev      # http://localhost:5173
```

## 5. Run the stack

```powershell
# terminal 1 — backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend
cd apps/web
npm run dev
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health · Readiness: http://localhost:8000/ready

## 6. Tests

```powershell
cd backend
python -m pytest -q
```

The integration tier requires `TEST_DATABASE_URL` and the `agentops_test` database from §2.2.
Unit tests run without a database.

---

## 7. Container path (CI / production-like)

`docker compose up --build` starts PostgreSQL, Redis, the API and the web app with the same
`.env` variable names. This path is exercised in CI; it requires Docker, which is not
installed on this development machine.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: password authentication failed for user "agentops"` | wrong password or role not created | rerun §2.1/§2.2 |
| `FATAL: role "agentops" does not exist` | role creation step skipped | rerun §2.2 |
| `password authentication failed` immediately after changing pg_hba | service not restarted | `Restart-Service postgresql-x64-18` |
| `could not connect to server` | service stopped | `Start-Service postgresql-x64-18` |
| Alembic `relation "users" does not exist` | migrations not applied | `alembic upgrade head` |
| Frontend `Failed to fetch` | API not running or CORS origin mismatch | start uvicorn; check `CORS_ORIGINS` |
