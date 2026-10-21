-- AgentOps M3: runtime safety, approvals and observability.
--
-- Adds the workspace policy document, the approval lifecycle, the resume
-- checkpoint that lets a paused run continue after a decision, and the
-- run-level flags that make a replay safe.
--
-- Rules that apply to every object in this file:
--   * domain tables live in the `app` schema
--   * RLS is enabled on every table
--   * every policy carries an ownership or workspace-membership predicate
--   * UPDATE policies carry both `using` and `with check`
--   * no grants to `anon` / `authenticated` / `service_role`

-- --------------------------------------------------------------------------- --
-- Workspace policy document
-- --------------------------------------------------------------------------- --
create table if not exists app.workspace_policies (
    workspace_id uuid primary key references app.workspaces (id) on delete cascade,
    version integer not null default 1 check (version >= 1),
    -- Empty allowlist means "every registered tool"; the deny list always wins.
    tool_allowlist jsonb not null default '[]'::jsonb,
    blocked_tools jsonb not null default '[]'::jsonb,
    disabled_agent_ids jsonb not null default '[]'::jsonb,
    require_approval_for_risk_levels jsonb not null default '["high", "critical"]'::jsonb,
    -- {tool name: max calls per minute}
    tool_rate_limits jsonb not null default '{}'::jsonb,
    max_tool_calls_per_run integer check (max_tool_calls_per_run is null or max_tool_calls_per_run > 0),
    max_runs_per_hour integer check (max_runs_per_hour is null or max_runs_per_hour > 0),
    approval_ttl_minutes integer not null default 60
        check (approval_ttl_minutes between 1 and 10080),
    execution_paused boolean not null default false,
    paused_reason text,
    updated_by uuid references app.profiles (id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on table app.workspace_policies is
    'One policy document per workspace: tool allow/deny lists, approval thresholds, rate limits, quota and the emergency pause switch.';

-- --------------------------------------------------------------------------- --
-- Approval requests
-- --------------------------------------------------------------------------- --
create table if not exists app.approval_requests (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    run_id uuid not null references app.agent_runs (id) on delete cascade,
    agent_version_id uuid references app.agent_versions (id) on delete set null,
    tool_definition_id uuid references app.tool_definitions (id) on delete set null,
    tool_name text not null,
    risk_level text not null
        constraint approval_requests_risk_valid check (risk_level in ('low', 'medium', 'high', 'critical')),
    -- SHA-256 of the canonical {tool, arguments} payload. The decision is bound
    -- to this exact action; a changed payload can never be approved.
    canonical_arguments_hash text not null check (length(canonical_arguments_hash) = 64),
    arguments jsonb not null default '{}'::jsonb,
    requested_by uuid references app.profiles (id) on delete set null,
    status text not null default 'pending'
        constraint approval_requests_status_valid
        check (
            status in (
                'pending',
                'approved',
                'rejected',
                'changes_requested',
                'expired',
                'executed',
                'revoked'
            )
        ),
    decision text,
    decided_by uuid references app.profiles (id) on delete set null,
    decided_at timestamptz,
    review_note text,
    policy_version integer not null default 1 check (policy_version >= 1),
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);

create index if not exists ix_approval_requests_workspace_status
    on app.approval_requests (workspace_id, status, created_at desc);
create index if not exists ix_approval_requests_run
    on app.approval_requests (run_id, created_at desc);
create index if not exists ix_approval_requests_decided_by
    on app.approval_requests (decided_by, decided_at desc)
    where decided_by is not null;

-- One pending request per exact action and run: a duplicate request for the
-- same payload is rejected instead of creating a second queue entry.
create unique index if not exists ux_approval_requests_pending_action
    on app.approval_requests (run_id, canonical_arguments_hash)
    where status = 'pending';

-- --------------------------------------------------------------------------- --
-- Resume checkpoints
-- --------------------------------------------------------------------------- --
create table if not exists app.run_checkpoints (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    run_id uuid not null references app.agent_runs (id) on delete cascade,
    step integer not null check (step >= 0),
    -- The conversation and the pending tool call needed to continue the run.
    state jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists ux_run_checkpoints_run_step
    on app.run_checkpoints (run_id, step);

-- --------------------------------------------------------------------------- --
-- Run flags for approvals and safe replay
-- --------------------------------------------------------------------------- --
alter table app.agent_runs
    add column if not exists pending_approval_id uuid
        references app.approval_requests (id) on delete set null;
alter table app.agent_runs
    add column if not exists replay_mode boolean not null default false;

create index if not exists ix_agent_runs_pending_approval
    on app.agent_runs (pending_approval_id)
    where pending_approval_id is not null;

-- --------------------------------------------------------------------------- --
-- Row Level Security
-- --------------------------------------------------------------------------- --
alter table app.workspace_policies enable row level security;
alter table app.approval_requests enable row level security;
alter table app.run_checkpoints enable row level security;

-- workspace_policies: administrators manage the document, members may read it.
drop policy if exists workspace_policies_select_member on app.workspace_policies;
create policy workspace_policies_select_member on app.workspace_policies
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists workspace_policies_insert_admin on app.workspace_policies;
create policy workspace_policies_insert_admin on app.workspace_policies
    for insert to authenticated
    with check (app_private.is_workspace_admin(workspace_id));

drop policy if exists workspace_policies_update_admin on app.workspace_policies;
create policy workspace_policies_update_admin on app.workspace_policies
    for update to authenticated
    using (app_private.is_workspace_admin(workspace_id))
    with check (app_private.is_workspace_admin(workspace_id));

drop policy if exists workspace_policies_delete_admin on app.workspace_policies;
create policy workspace_policies_delete_admin on app.workspace_policies
    for delete to authenticated
    using (app_private.is_workspace_admin(workspace_id));

-- approval_requests: readable by members, decidable by reviewers, written by the
-- runtime (service role) and by administrators when revoking.
drop policy if exists approval_requests_select_member on app.approval_requests;
create policy approval_requests_select_member on app.approval_requests
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists approval_requests_insert_reviewer on app.approval_requests;
create policy approval_requests_insert_reviewer on app.approval_requests
    for insert to authenticated
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists approval_requests_update_reviewer on app.approval_requests;
create policy approval_requests_update_reviewer on app.approval_requests
    for update to authenticated
    using (app_private.can_operate_workspace(workspace_id))
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists approval_requests_delete_admin on app.approval_requests;
create policy approval_requests_delete_admin on app.approval_requests
    for delete to authenticated
    using (app_private.is_workspace_admin(workspace_id));

-- run_checkpoints: execution state is readable by members and writable by the
-- runtime; a client may never author its own checkpoint.
drop policy if exists run_checkpoints_select_member on app.run_checkpoints;
create policy run_checkpoints_select_member on app.run_checkpoints
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists run_checkpoints_insert_operator on app.run_checkpoints;
create policy run_checkpoints_insert_operator on app.run_checkpoints
    for insert to authenticated
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists run_checkpoints_update_operator on app.run_checkpoints;
create policy run_checkpoints_update_operator on app.run_checkpoints
    for update to authenticated
    using (app_private.can_operate_workspace(workspace_id))
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists run_checkpoints_delete_admin on app.run_checkpoints;
create policy run_checkpoints_delete_admin on app.run_checkpoints
    for delete to authenticated
    using (app_private.is_workspace_admin(workspace_id));

-- --------------------------------------------------------------------------- --
-- Grants: the app schema stays unreachable through the Data API
-- --------------------------------------------------------------------------- --
revoke all on table app.workspace_policies from anon, authenticated, service_role;
revoke all on table app.approval_requests from anon, authenticated, service_role;
revoke all on table app.run_checkpoints from anon, authenticated, service_role;

alter default privileges in schema app revoke all on tables from anon, authenticated, service_role;
