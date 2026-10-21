-- AgentOps initial schema: identity, workspaces, memberships, API keys, audit.
--
-- Schema authority for the platform (AGENTS.md 4A.4). Applied by `supabase db push`
-- against Supabase Postgres, and by `psql -f` against a plain PostgreSQL instance in
-- local development and CI (the same files, so schema drift is impossible).
--
-- Conventions enforced here:
--   * domain tables live in the non-exposed `app` schema
--   * every table has Row Level Security enabled
--   * every policy carries a membership predicate, never just `to authenticated`
--   * `UPDATE` policies carry both `using` and `with check`
--   * privileged helpers live in `app_private` (not exposed, security definer)

-- ---------------------------------------------------------------------------
-- Schemas
-- ---------------------------------------------------------------------------
create schema if not exists app;
create schema if not exists app_private;

-- ---------------------------------------------------------------------------
-- Local / CI compatibility shim.
--
-- On Supabase the `auth` schema, `auth.users` and the `anon`/`authenticated`/
-- `service_role` roles already exist and this block is a no-op. On a plain
-- PostgreSQL instance (developer machines, CI) the shim provides the minimum
-- surface the policies below reference, so the exact production migration can
-- be executed unchanged.
-- ---------------------------------------------------------------------------
do $shim$
begin
    if to_regclass('auth.users') is null then
        create schema if not exists auth;

        create table auth.users (
            id uuid primary key,
            email text,
            created_at timestamptz not null default now()
        );

        -- Mirrors Supabase's helper: the request JWT subject, or null.
        create or replace function auth.uid() returns uuid
            language sql stable
            as $fn$
                select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
            $fn$;

        create or replace function auth.role() returns text
            language sql stable
            as $fn$
                select nullif(current_setting('request.jwt.claim.role', true), '')
            $fn$;
    end if;
end
$shim$;

do $roles$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin noinherit;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin noinherit;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role nologin noinherit bypassrls;
    end if;
end
$roles$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table if not exists app.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    email text not null,
    display_name text not null default '',
    status text not null default 'active'
        constraint profiles_status_valid check (status in ('active', 'disabled', 'pending')),
    avatar_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint profiles_email_not_blank check (length(btrim(email)) > 0)
);

create unique index if not exists uq_profiles_email_lower on app.profiles (lower(email));

create table if not exists app.local_credentials (
    profile_id uuid primary key references app.profiles (id) on delete cascade,
    password_hash text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on table app.local_credentials is
    'Development-only password credentials. Never written when AUTH_MODE=supabase; '
    'authentication is owned by Supabase Auth in every deployed environment.';

create table if not exists app.workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    slug text not null,
    owner_id uuid not null references app.profiles (id) on delete cascade,
    settings jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint workspaces_name_valid check (length(btrim(name)) between 1 and 160),
    constraint workspaces_slug_valid check (slug ~ '^[a-z0-9][a-z0-9-]{0,79}$')
);

create unique index if not exists uq_workspaces_slug on app.workspaces (slug);
create index if not exists ix_workspaces_owner_id on app.workspaces (owner_id);

create table if not exists app.workspace_members (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    user_id uuid not null references app.profiles (id) on delete cascade,
    role text not null
        constraint workspace_members_role_valid
        check (role in ('owner', 'admin', 'developer', 'operator', 'reviewer', 'viewer')),
    status text not null default 'active'
        constraint workspace_members_status_valid
        check (status in ('active', 'invited', 'suspended')),
    invited_by uuid references app.profiles (id) on delete set null,
    created_at timestamptz not null default now(),
    constraint uq_workspace_members_workspace_id_user_id unique (workspace_id, user_id)
);

create index if not exists ix_workspace_members_user_id
    on app.workspace_members (user_id) where status = 'active';

create table if not exists app.workspace_preferences (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    user_id uuid not null references app.profiles (id) on delete cascade,
    preferences jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_workspace_preferences_workspace_id_user_id unique (workspace_id, user_id)
);

create table if not exists app.api_keys (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    name text not null,
    key_prefix text not null,
    key_hash text not null,
    scopes jsonb not null default '[]'::jsonb,
    expires_at timestamptz,
    revoked_at timestamptz,
    last_used_at timestamptz,
    created_by uuid references app.profiles (id) on delete set null,
    created_at timestamptz not null default now(),
    constraint api_keys_hash_unique unique (key_hash),
    constraint api_keys_revoked_ok check (revoked_at is null or revoked_at >= created_at)
);

create index if not exists ix_api_keys_workspace_id on app.api_keys (workspace_id);

create table if not exists app.audit_events (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references app.workspaces (id) on delete cascade,
    actor_id uuid references app.profiles (id) on delete set null,
    action text not null,
    resource_type text not null,
    resource_id text,
    outcome text not null default 'success'
        constraint audit_events_outcome_valid
        check (outcome in ('success', 'denied', 'failure')),
    sanitized_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists ix_audit_events_workspace_created
    on app.audit_events (workspace_id, created_at desc);
create index if not exists ix_audit_events_action on app.audit_events (action);

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------
create or replace function app.touch_updated_at() returns trigger
    language plpgsql
    security invoker
    set search_path = app, pg_temp
    as $fn$
begin
    new.updated_at := now();
    return new;
end
$fn$;

drop trigger if exists trg_profiles_touch on app.profiles;
create trigger trg_profiles_touch before update on app.profiles
    for each row execute function app.touch_updated_at();

drop trigger if exists trg_workspaces_touch on app.workspaces;
create trigger trg_workspaces_touch before update on app.workspaces
    for each row execute function app.touch_updated_at();

drop trigger if exists trg_workspace_preferences_touch on app.workspace_preferences;
create trigger trg_workspace_preferences_touch before update on app.workspace_preferences
    for each row execute function app.touch_updated_at();

drop trigger if exists trg_local_credentials_touch on app.local_credentials;
create trigger trg_local_credentials_touch before update on app.local_credentials
    for each row execute function app.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Privileged helpers (non-exposed schema, explicit auth.uid() check)
--
-- `security definer` is used here only to break RLS recursion when a policy on
-- `workspace_members` needs to ask "is the caller a member of this workspace?".
-- The function body always starts from auth.uid() and never trusts caller input.
-- ---------------------------------------------------------------------------
create or replace function app_private.is_workspace_member(target_workspace uuid)
    returns boolean
    language sql
    stable
    security definer
    set search_path = app, pg_temp
    as $fn$
        select exists (
            select 1
            from app.workspace_members m
            where m.workspace_id = target_workspace
              and m.user_id = auth.uid()
              and m.status = 'active'
        )
    $fn$;

create or replace function app_private.is_workspace_admin(target_workspace uuid)
    returns boolean
    language sql
    stable
    security definer
    set search_path = app, pg_temp
    as $fn$
        select exists (
            select 1
            from app.workspace_members m
            where m.workspace_id = target_workspace
              and m.user_id = auth.uid()
              and m.status = 'active'
              and m.role in ('owner', 'admin')
        )
    $fn$;

-- Read the current owner without going through the workspaces RLS policy again
-- (which would recurse). Used by the UPDATE policy to forbid silent ownership
-- transfer: ownership moves through an explicit, audited operation instead.
create or replace function app_private.workspace_owner(target_workspace uuid)
    returns uuid
    language sql
    stable
    security definer
    set search_path = app, pg_temp
    as $fn$
        select w.owner_id from app.workspaces w where w.id = target_workspace
    $fn$;

revoke all on function app_private.is_workspace_member(uuid) from public;
revoke all on function app_private.is_workspace_admin(uuid) from public;
revoke all on function app_private.workspace_owner(uuid) from public;
grant usage on schema app_private to authenticated;
grant execute on all functions in schema app_private to authenticated;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table app.profiles enable row level security;
alter table app.local_credentials enable row level security;
alter table app.workspaces enable row level security;
alter table app.workspace_members enable row level security;
alter table app.workspace_preferences enable row level security;
alter table app.api_keys enable row level security;
alter table app.audit_events enable row level security;

-- profiles: a user sees themselves and the people they share a workspace with.
drop policy if exists profiles_select_self_or_coworker on app.profiles;
create policy profiles_select_self_or_coworker on app.profiles
    for select to authenticated
    using (
        id = (select auth.uid())
        or exists (
            select 1
            from app.workspace_members mine
            join app.workspace_members theirs on theirs.workspace_id = mine.workspace_id
            where mine.user_id = (select auth.uid())
              and mine.status = 'active'
              and theirs.user_id = app.profiles.id
              and theirs.status = 'active'
        )
    );

drop policy if exists profiles_insert_self on app.profiles;
create policy profiles_insert_self on app.profiles
    for insert to authenticated
    with check (id = (select auth.uid()));

drop policy if exists profiles_update_self on app.profiles;
create policy profiles_update_self on app.profiles
    for update to authenticated
    using (id = (select auth.uid()))
    with check (id = (select auth.uid()));

-- local_credentials: no policies at all. Development-only rows are reachable
-- only by the owning database role; the authenticated role can never read them.

-- workspaces
drop policy if exists workspaces_select_member on app.workspaces;
create policy workspaces_select_member on app.workspaces
    for select to authenticated
    using (app_private.is_workspace_member(id));

drop policy if exists workspaces_insert_self_owned on app.workspaces;
create policy workspaces_insert_self_owned on app.workspaces
    for insert to authenticated
    with check (owner_id = (select auth.uid()));

drop policy if exists workspaces_update_admin on app.workspaces;
create policy workspaces_update_admin on app.workspaces
    for update to authenticated
    using (app_private.is_workspace_admin(id))
    with check (
        app_private.is_workspace_admin(id)
        and owner_id = app_private.workspace_owner(id)
    );

drop policy if exists workspaces_delete_owner on app.workspaces;
create policy workspaces_delete_owner on app.workspaces
    for delete to authenticated
    using (
        exists (
            select 1
            from app.workspace_members m
            where m.workspace_id = app.workspaces.id
              and m.user_id = (select auth.uid())
              and m.status = 'active'
              and m.role = 'owner'
        )
    );

-- workspace_members
drop policy if exists workspace_members_select_member on app.workspace_members;
create policy workspace_members_select_member on app.workspace_members
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists workspace_members_insert_admin on app.workspace_members;
create policy workspace_members_insert_admin on app.workspace_members
    for insert to authenticated
    with check (app_private.is_workspace_admin(workspace_id));

drop policy if exists workspace_members_update_admin on app.workspace_members;
create policy workspace_members_update_admin on app.workspace_members
    for update to authenticated
    using (app_private.is_workspace_admin(workspace_id))
    with check (app_private.is_workspace_admin(workspace_id));

drop policy if exists workspace_members_delete_admin on app.workspace_members;
create policy workspace_members_delete_admin on app.workspace_members
    for delete to authenticated
    using (app_private.is_workspace_admin(workspace_id));

-- workspace_preferences: strictly personal rows.
drop policy if exists workspace_preferences_select_own on app.workspace_preferences;
create policy workspace_preferences_select_own on app.workspace_preferences
    for select to authenticated
    using (user_id = (select auth.uid()));

drop policy if exists workspace_preferences_insert_own on app.workspace_preferences;
create policy workspace_preferences_insert_own on app.workspace_preferences
    for insert to authenticated
    with check (
        user_id = (select auth.uid())
        and app_private.is_workspace_member(workspace_id)
    );

drop policy if exists workspace_preferences_update_own on app.workspace_preferences;
create policy workspace_preferences_update_own on app.workspace_preferences
    for update to authenticated
    using (user_id = (select auth.uid()))
    with check (
        user_id = (select auth.uid())
        and app_private.is_workspace_member(workspace_id)
    );

drop policy if exists workspace_preferences_delete_own on app.workspace_preferences;
create policy workspace_preferences_delete_own on app.workspace_preferences
    for delete to authenticated
    using (user_id = (select auth.uid()));

-- api_keys: workspace admins only; the hash is never exposed to members.
drop policy if exists api_keys_select_admin on app.api_keys;
create policy api_keys_select_admin on app.api_keys
    for select to authenticated
    using (app_private.is_workspace_admin(workspace_id));

drop policy if exists api_keys_insert_admin on app.api_keys;
create policy api_keys_insert_admin on app.api_keys
    for insert to authenticated
    with check (
        app_private.is_workspace_admin(workspace_id)
        and created_by = (select auth.uid())
    );

drop policy if exists api_keys_update_admin on app.api_keys;
create policy api_keys_update_admin on app.api_keys
    for update to authenticated
    using (app_private.is_workspace_admin(workspace_id))
    with check (app_private.is_workspace_admin(workspace_id));

drop policy if exists api_keys_delete_admin on app.api_keys;
create policy api_keys_delete_admin on app.api_keys
    for delete to authenticated
    using (app_private.is_workspace_admin(workspace_id));

-- audit_events: readable by workspace admins, append-only from the API.
drop policy if exists audit_events_select_admin on app.audit_events;
create policy audit_events_select_admin on app.audit_events
    for select to authenticated
    using (
        workspace_id is not null and app_private.is_workspace_admin(workspace_id)
    );

-- ---------------------------------------------------------------------------
-- Data API posture: domain tables are unreachable for the API roles.
-- The browser never queries these tables directly; FastAPI is the only writer.
-- ---------------------------------------------------------------------------
revoke all on schema app from anon, authenticated, service_role;
revoke all on all tables in schema app from anon, authenticated, service_role;
revoke all on all sequences in schema app from anon, authenticated, service_role;
revoke all on all functions in schema app from anon, authenticated, service_role;

alter default privileges in schema app revoke all on tables from anon, authenticated, service_role;
alter default privileges in schema app revoke all on sequences from anon, authenticated, service_role;
alter default privileges in schema app revoke execute on functions from public;
