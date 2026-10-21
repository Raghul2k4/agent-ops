# AgentOps — Database Schema

**Authority:** [`supabase/migrations/20261021120000_initial_identity_schema.sql`](../supabase/migrations/20261021120000_initial_identity_schema.sql).
This document describes the current schema; if the two disagree, the migration wins.

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
