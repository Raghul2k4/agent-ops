# AgentOps — Database Schema

**Authority:** [`supabase/migrations/20261021120000_initial_identity_schema.sql`](../supabase/migrations/20261021120000_initial_identity_schema.sql),
[`supabase/migrations/20261021130000_agents_providers_tools_runtime.sql`](../supabase/migrations/20261021130000_agents_providers_tools_runtime.sql) and
[`supabase/migrations/20261021140000_safety_approvals_observability.sql`](../supabase/migrations/20261021140000_safety_approvals_observability.sql).
These documents describe the current schema; if the two disagree, the migration wins.

**Database:** Supabase Postgres (PostgreSQL 17). Domain objects live in the `app` schema; privileged
helpers live in `app_private`. `auth`, `storage` and `extensions` belong to Supabase.

**Migration rules:** SQL files in `supabase/migrations/`, applied by `supabase db push` (hosted) or
`psql -f` (local/CI). No other migration tool runs against this database. Each migration creates its
tables, indexes, constraints, RLS enablement and policies in the same file.

---

## 1. Entity relationships

```
auth.users (Supabase)
   │ 1
   │
   ▼ 1
app.profiles ──────────────┐
   │ 1                     │ 1
   │                       │
   ▼ N                     ▼ N
app.workspace_members   app.workspace_preferences
   │ N                     │ N
   │                       │
   ▼ 1                     ▼ 1
app.workspaces ◀───────────┘
   │ 1
   ├──▶ app.api_keys          (N)
   ├──▶ app.audit_events      (N)
   └──▶ app.workspace_members (N)

app.profiles ──1:1──▶ app.local_credentials   (development only)

app.workspaces ──1:N──▶ app.model_providers ──1:N──▶ app.model_configs
app.workspaces ──1:N──▶ app.agents ──1:N──▶ app.agent_versions   (immutable snapshots)
app.workspaces ──1:N──▶ app.tool_definitions
app.agent_versions ──1:N──▶ app.agent_tools ──N:1──▶ app.tool_definitions
app.agents ──1:N──▶ app.agent_runs ──1:N──▶ app.run_events
                                        └──1:N──▶ app.trace_spans
app.workspaces ──1:N──▶ app.crm_companies / crm_customers / crm_deals / crm_contacts
app.crm_customers ──1:N──▶ app.followup_drafts
```

- `app.profiles.id` **is** the Supabase Auth subject (`auth.users.id`); a deleted identity cascades
  to the profile, memberships, and owned workspaces.
- `app.workspaces.owner_id` references `app.profiles`, not `auth.users`, so ownership survives only
  while the profile exists.
- `app.workspace_members` has two foreign keys to `app.profiles` (`user_id`, `invited_by`); ORM
  relationships name the column explicitly to avoid ambiguity.

---

## 2. Tables

### 2.1 `app.profiles`

Application profile mirroring a Supabase Auth identity. No credentials.

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK, FK → `auth.users(id)` `on delete cascade` |
| `email` | `text` | not null, non-blank; unique on `lower(email)` |
| `display_name` | `text` | not null, default `''` |
| `status` | `text` | not null, default `active`; `active` \| `disabled` \| `pending` |
| `avatar_url` | `text` | nullable |
| `created_at`, `updated_at` | `timestamptz` | not null, default `now()`; `updated_at` maintained by trigger |

Indexes: `uq_profiles_email_lower` (unique, case-insensitive).

### 2.2 `app.local_credentials`

Development-only password hashes (`AUTH_MODE=local`). Never written when `AUTH_MODE=supabase`.

| Column | Type | Constraints |
|---|---|---|
| `profile_id` | `uuid` | PK, FK → `app.profiles(id)` `on delete cascade` |
| `password_hash` | `text` | not null (Argon2id) |
| `created_at`, `updated_at` | `timestamptz` | not null, default `now()` |

No RLS policies exist for this table: even if a grant were added by mistake, the authenticated role
would see zero rows.

### 2.3 `app.workspaces`

Tenant boundary. Every future domain table carries `workspace_id` referencing this table.

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK, default `gen_random_uuid()` |
| `name` | `text` | not null, 1–160 chars after trim |
| `slug` | `text` | not null, unique, `^[a-z0-9][a-z0-9-]{0,79}$` |
| `owner_id` | `uuid` | not null, FK → `app.profiles(id)` `on delete cascade` |
| `settings` | `jsonb` | not null, default `{}` |
| `created_at`, `updated_at` | `timestamptz` | not null, default `now()`; trigger |

Indexes: unique `slug`, `ix_workspaces_owner_id`.

### 2.4 `app.workspace_members`

Membership and role. One row per (workspace, user).

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK, default `gen_random_uuid()` |
| `workspace_id` | `uuid` | not null, FK → `workspaces` `on delete cascade` |
| `user_id` | `uuid` | not null, FK → `profiles` `on delete cascade` |
| `role` | `text` | `owner` \| `admin` \| `developer` \| `operator` \| `reviewer` \| `viewer` |
| `status` | `text` | `active` \| `invited` \| `suspended`, default `active` |
| `invited_by` | `uuid` | nullable, FK → `profiles` `on delete set null` |
| `created_at` | `timestamptz` | not null, default `now()` |

Constraints/indexes: unique `(workspace_id, user_id)`;
`ix_workspace_members_user_id ... where status = 'active'` (partial, for membership lookups).

### 2.5 `app.workspace_preferences`

Per-user, per-workspace UI preferences (e.g. last active workspace).

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK |
| `workspace_id` | `uuid` | not null, FK → `workspaces` `on delete cascade` |
| `user_id` | `uuid` | not null, FK → `profiles` `on delete cascade` |
| `preferences` | `jsonb` | not null, default `{}` |
| `created_at`, `updated_at` | `timestamptz` | not null, default `now()`; trigger |

Constraint: unique `(workspace_id, user_id)`.

### 2.6 `app.api_keys`

Scoped programmatic credentials. Only the SHA-256 hash is stored; plaintext is shown once.

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK |
| `workspace_id` | `uuid` | not null, FK → `workspaces` `on delete cascade` |
| `name` | `text` | not null |
| `key_prefix` | `text` | not null, non-secret display prefix |
| `key_hash` | `text` | not null, unique |
| `scopes` | `jsonb` | not null, default `[]` |
| `expires_at`, `revoked_at`, `last_used_at` | `timestamptz` | nullable |
| `created_by` | `uuid` | nullable, FK → `profiles` `on delete set null` |
| `created_at` | `timestamptz` | not null, default `now()` |

Check: `revoked_at is null or revoked_at >= created_at`. Index: `ix_api_keys_workspace_id`.

The table is schema-ready; API-key authentication lands with the developer-platform milestone.

### 2.7 `app.audit_events`

Append-only security trail.

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK |
| `workspace_id` | `uuid` | nullable, FK → `workspaces` `on delete cascade` |
| `actor_id` | `uuid` | nullable, FK → `profiles` `on delete set null` |
| `action` | `text` | not null (e.g. `workspace.created`) |
| `resource_type` | `text` | not null |
| `resource_id` | `text` | nullable |
| `outcome` | `text` | `success` \| `denied` \| `failure`, default `success` |
| `sanitized_metadata` | `jsonb` | not null, default `{}`; secrets excluded |
| `created_at` | `timestamptz` | not null, default `now()` |

Indexes: `(workspace_id, created_at desc)`, `(action)`.

Only a `SELECT` policy exists. There is no `UPDATE`/`DELETE` policy, so audit rows cannot be
rewritten through the Data API.

### 2.8 M2 tables — agents, providers, tools, CRM and execution

Added by `20261021130000_agents_providers_tools_runtime.sql`. Every table enables RLS and carries
workspace-scoped policies that mirror the API's authorization rules.

| Table | Purpose | Key columns | Notes |
|---|---|---|---|
| `app.model_providers` | Provider configuration | `provider_type`, `display_name`, `base_url`, `secret_reference`, `configuration`, `status`, `last_health_check_at`, `last_health_error` | `secret_reference` is an environment-variable **name**; no credential value is ever stored |
| `app.model_configs` | A model on a provider | `provider_id`, `model_name`, `capabilities` (jsonb), `default_parameters` (jsonb), `pricing` (jsonb), `enabled`, `is_default` | `capabilities` is tri-state: `null` means unknown, never "supported" |
| `app.agents` | An agent draft | `name`, `description`, `status`, `draft_configuration` (jsonb), `current_published_version_id`, `created_by` | The draft is editable; the published version is not |
| `app.agent_versions` | Immutable published snapshot | `agent_id`, `version_number`, `configuration` (jsonb), `configuration_hash`, `change_summary`, `created_by` | A trigger rejects `UPDATE`, so a run stays interpretable |
| `app.tool_definitions` | Server-side tool registry | `name`, `version`, `description`, `input_schema`, `output_schema`, `risk_level`, `required_permissions`, `timeout_seconds`, `requires_approval`, `enabled` | `workspace_id` is null for global built-ins |
| `app.agent_tools` | Tool binding for an agent version | `agent_version_id`, `tool_definition_id`, `configuration` | The tool set is fixed when the version is published |
| `app.crm_companies`, `app.crm_customers`, `app.crm_deals`, `app.crm_contacts` | Synthetic CRM dataset | names, amounts, stages, timestamps, `is_demo` | Fictional data; seeded only by the explicit, audited demo-data action |
| `app.agent_runs` | One execution | `agent_version_id`, `initiated_by`, `status`, `input`, `output`, `token_usage`, `estimated_cost`, `error_code`, `error_summary`, `replay_of_run_id` | `token_usage` includes `model_calls` and `tool_calls`; `estimated_cost` is null when pricing is unknown |
| `app.run_events` | Ordered execution events | `run_id`, `sequence_number`, `event_type`, `event_status`, `payload` (jsonb), `occurred_at` | `sequence_number` is the recovery cursor; unique per run |
| `app.trace_spans` | Hierarchical spans | `run_id`, `parent_span_id`, `span_type`, `name`, `status`, `started_at`, `ended_at`, `duration_ms`, `attributes` | `span_type` is `agent_run`, `model_call` or `tool_call` |
| `app.followup_drafts` | Draft follow-up messages | `customer_id`, `deal_id`, `subject`, `body`, `status` | Internal and reversible; no message is ever sent |

Event types recorded by the runtime: `run.started`, `model.request`, `model.response`,
`tool.request`, `tool.cached`, `tool.result`, `tool.error`, `approval.required`,
`run.resumed`, `run.succeeded`, `run.failed`, `run.cancelled`, `run.awaiting_approval`.

### 2.9 M3 tables — policy, approvals and checkpoints

Added by `20261021140000_safety_approvals_observability.sql`. Every table enables RLS and carries
workspace-scoped policies that mirror the API's authorization rules.

| Table | Purpose | Key columns | Notes |
|---|---|---|---|
| `app.workspace_policies` | The workspace's enforcement document | `workspace_id` (PK), `version`, `tool_allowlist`, `blocked_tools`, `disabled_agent_ids`, `require_approval_for_risk_levels`, `tool_rate_limits`, `max_tool_calls_per_run`, `max_runs_per_hour`, `approval_ttl_minutes`, `execution_paused`, `paused_reason` | One row per workspace; the version is stamped on runs and approvals |
| `app.approval_requests` | A proposed action waiting for a human decision | `run_id`, `tool_name`, `risk_level`, `canonical_arguments_hash`, `arguments`, `status`, `decision`, `decided_by`, `decided_at`, `review_note`, `policy_version`, `expires_at` | A partial unique index allows only one **pending** request per (run, payload hash) |
| `app.run_checkpoints` | The state that lets a paused run continue | `run_id`, `step`, `state` (jsonb) | Stores the conversation, the counters and the pending call |

`app.agent_runs` gained two columns in M3: `pending_approval_id` (the request the run waits for)
and `replay_mode` (true when the run is a safe replay).

---

## 3. Functions and triggers

| Object | Schema | Security | Purpose |
|---|---|---|---|
| `app.touch_updated_at()` | `app` | invoker | Sets `updated_at = now()` on update |
| `app_private.is_workspace_member(uuid)` | `app_private` | definer | Active-membership check; breaks RLS recursion |
| `app_private.is_workspace_admin(uuid)` | `app_private` | definer | Owner/admin check |
| `app_private.workspace_owner(uuid)` | `app_private` | definer | Current owner, without re-entering the `workspaces` policy |

The `app_private` functions always derive identity from `auth.uid()` and never trust their argument
as an identity. `PUBLIC` execute is revoked; `authenticated` is granted usage.

Triggers `trg_*_touch` exist on `profiles`, `workspaces`, `workspace_preferences` and
`local_credentials`.

---

## 4. Timestamps and identifiers

- All timestamps are `timestamptz` in UTC; the API serialises ISO-8601 with `Z`.
- UUID primary keys are generated by Postgres (`gen_random_uuid()`); the API never invents ids for
  persisted rows.
- `updated_at` is maintained in the database, not by the client.

---

## 5. Row Level Security

RLS is enabled on all seven tables. Twenty policies exist, all `to authenticated`. Every policy
carries a membership or ownership predicate; every `UPDATE` policy has both `using` and
`with check`.

| Table | Policies | Rule |
|---|---|---|
| `profiles` | `profiles_select_self_or_coworker`, `profiles_insert_self`, `profiles_update_self` | Self, or a profile sharing an active workspace; insert/update only own row |
| `workspaces` | `workspaces_select_member`, `workspaces_insert_self_owned`, `workspaces_update_admin`, `workspaces_delete_owner` | Members read; creator inserts self-owned; admins update (ownership cannot change); owners delete |
| `workspace_members` | `..._select_member`, `..._insert_admin`, `..._update_admin`, `..._delete_admin` | Members read; admins mutate |
| `workspace_preferences` | `..._select_own`, `..._insert_own`, `..._update_own`, `..._delete_own` | Own row only; insert/update also require membership |
| `api_keys` | `api_keys_select_admin`, `api_keys_insert_admin`, `api_keys_update_admin`, `api_keys_delete_admin` | Workspace admins only; `created_by` must be the caller |
| `audit_events` | `audit_events_select_admin` | Workspace admins read; no write policies |
| `local_credentials` | — | No policy: unreachable by `authenticated` |

### 5.1 Grants

```sql
revoke all on schema app from anon, authenticated, service_role;
revoke all on all tables    in schema app from anon, authenticated, service_role;
revoke all on all sequences in schema app from anon, authenticated, service_role;
revoke all on all functions in schema app from anon, authenticated, service_role;
alter default privileges in schema app revoke all on tables    from anon, authenticated, service_role;
alter default privileges in schema app revoke all on sequences from anon, authenticated, service_role;
alter default privileges in schema app revoke execute on functions from public;
```

`app_private` is granted to `authenticated` for the three helper functions only; its tables (none
today) are not exposed.

### 5.2 Verification

`supabase/tests/rls_policies.sql` runs inside a transaction and raises an exception on any failure.
It asserts:

- RLS is enabled on every table in `app`.
- Each expected policy exists with the intended command and roles.
- A member sees their workspace; a non-member sees nothing.
- A non-admin cannot insert/update/delete membership rows.
- Ownership cannot be reassigned by an admin update.
- `authenticated` has no table grants in `app`.
- An `authenticated` session granted `SELECT` on `local_credentials` still sees zero rows.
- The M2 tables (providers, models, agents, versions, tools, CRM, runs, events, spans) enforce the
  same workspace-membership predicate, and the published-version trigger refuses an `UPDATE`.

Backend test: `backend/tests/integration/test_rls_policies.py` loads the migration into a scratch
database and executes the SQL assertions. It runs in the normal `pytest` suite.

---

## 6. Local/CI compatibility

The migration starts with a guarded shim that creates the following **only if absent**:

- `auth.users` (minimal: `id`, `email`, `created_at`)
- `auth.uid()` / `auth.role()` reading `request.jwt.claim.sub` / `.role`
- roles `anon`, `authenticated`, `service_role`

On Supabase these objects already exist, so the shim does nothing. This keeps one migration file as
the single authority instead of maintaining a parallel test schema.

---

## 7. Retention and backup

| Concern | Current posture |
|---|---|
| Backups | Supabase automated backups + point-in-time recovery (plan-dependent) |
| Restore drills | Documented, not yet executed (release hardening) |
| Audit retention | Append-only; retention policy lands with the governance milestone |
| Test database | Disposable; `truncate` between tests; never the hosted project |

Schema changes that would destroy data require an explicit, reviewed migration path; the initial
migration only creates objects and is safe to re-run (`if not exists`).
