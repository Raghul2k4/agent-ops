-- AgentOps M2 schema: providers, agents, tool registry, CRM data, runs and traces.
--
-- Same rules as the initial migration: domain tables live in `app`, every table
-- has RLS enabled, every policy targets `authenticated` with a membership
-- predicate, UPDATE policies carry both `using` and `with check`, and the API
-- roles receive no grants (FastAPI is the only domain API).
--
-- `agent_versions` rows are immutable snapshots. Draft edits live on
-- `app.agents.draft_configuration`, so publishing never mutates history.

-- ---------------------------------------------------------------------------
-- Model providers and model configurations
-- ---------------------------------------------------------------------------
create table if not exists app.model_providers (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    provider_type text not null
        constraint model_providers_type_valid
        check (provider_type in ('ollama', 'openai_compatible', 'anthropic', 'simulation')),
    display_name text not null,
    base_url text,
    -- Name of the server-side environment variable holding the credential.
    -- The credential itself is never stored in the database.
    secret_reference text,
    configuration jsonb not null default '{}'::jsonb,
    status text not null default 'unconfigured'
        constraint model_providers_status_valid
        check (status in ('unconfigured', 'connected', 'error', 'disabled')),
    last_health_check_at timestamptz,
    last_health_error text,
    created_by uuid references app.profiles (id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint model_providers_name_unique unique (workspace_id, display_name),
    constraint model_providers_secret_reference_valid
        check (secret_reference is null or secret_reference ~ '^[A-Z][A-Z0-9_]{2,79}$')
);

create index if not exists ix_model_providers_workspace_id
    on app.model_providers (workspace_id);

create table if not exists app.model_configs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    provider_id uuid not null references app.model_providers (id) on delete cascade,
    model_name text not null,
    display_name text,
    capabilities jsonb not null default '{}'::jsonb,
    default_parameters jsonb not null default '{}'::jsonb,
    pricing jsonb not null default '{}'::jsonb,
    enabled boolean not null default true,
    is_default boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint model_configs_model_unique unique (provider_id, model_name),
    constraint model_configs_name_not_blank check (length(btrim(model_name)) > 0)
);

create index if not exists ix_model_configs_workspace_id
    on app.model_configs (workspace_id);
create unique index if not exists uq_model_configs_workspace_default
    on app.model_configs (workspace_id) where is_default;

-- ---------------------------------------------------------------------------
-- Agents and immutable versions
-- ---------------------------------------------------------------------------
create table if not exists app.agents (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    name text not null,
    description text not null default '',
    status text not null default 'draft'
        constraint agents_status_valid
        check (status in ('draft', 'published', 'archived')),
    draft_configuration jsonb not null default '{}'::jsonb,
    current_published_version_id uuid,
    created_by uuid references app.profiles (id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint agents_name_valid check (length(btrim(name)) between 1 and 120)
);

create unique index if not exists uq_agents_workspace_name
    on app.agents (workspace_id, lower(name));
create index if not exists ix_agents_workspace_updated
    on app.agents (workspace_id, updated_at desc);

create table if not exists app.agent_versions (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    agent_id uuid not null references app.agents (id) on delete cascade,
    version_number integer not null check (version_number > 0),
    configuration jsonb not null,
    configuration_hash text not null,
    change_summary text not null default '',
    created_by uuid references app.profiles (id) on delete set null,
    created_at timestamptz not null default now(),
    constraint agent_versions_number_unique unique (agent_id, version_number)
);

create index if not exists ix_agent_versions_agent_created
    on app.agent_versions (agent_id, created_at desc);

alter table app.agents
    drop constraint if exists agents_current_published_version_fk;
alter table app.agents
    add constraint agents_current_published_version_fk
    foreign key (current_published_version_id)
    references app.agent_versions (id) on delete set null;

-- Published snapshots never change. Deleting a version is only possible via an
-- agent cascade; a version referenced by a run is protected by the FK there.
create or replace function app.prevent_version_mutation() returns trigger
    language plpgsql
    security invoker
    set search_path = app, pg_temp
    as $fn$
begin
    raise exception 'agent_versions rows are immutable; publish a new version instead';
end
$fn$;

drop trigger if exists trg_agent_versions_immutable on app.agent_versions;
create trigger trg_agent_versions_immutable
    before update on app.agent_versions
    for each row execute function app.prevent_version_mutation();

-- ---------------------------------------------------------------------------
-- Tool registry
-- ---------------------------------------------------------------------------
create table if not exists app.tool_definitions (
    id uuid primary key default gen_random_uuid(),
    -- NULL identifies a platform-wide built-in. Workspace rows are custom tools.
    workspace_id uuid references app.workspaces (id) on delete cascade,
    name text not null,
    version integer not null default 1 check (version > 0),
    description text not null default '',
    input_schema jsonb not null default '{}'::jsonb,
    output_schema jsonb not null default '{}'::jsonb,
    risk_level text not null default 'low'
        constraint tool_definitions_risk_valid
        check (risk_level in ('low', 'medium', 'high', 'critical')),
    required_permissions jsonb not null default '[]'::jsonb,
    requires_approval boolean not null default false,
    timeout_seconds integer not null default 30
        constraint tool_definitions_timeout_valid
        check (timeout_seconds between 1 and 600),
    max_retries integer not null default 0
        constraint tool_definitions_retries_valid
        check (max_retries between 0 and 5),
    idempotent boolean not null default true,
    -- Server-side registry key used to resolve the implementation. Callers can
    -- never supply executable code through this column.
    implementation text not null,
    enabled boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint tool_definitions_name_valid check (name ~ '^[a-z][a-z0-9_]{2,63}$')
);

create unique index if not exists uq_tool_definitions_global
    on app.tool_definitions (name, version) where workspace_id is null;
create unique index if not exists uq_tool_definitions_workspace
    on app.tool_definitions (workspace_id, name, version) where workspace_id is not null;

create table if not exists app.agent_tools (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    agent_version_id uuid not null references app.agent_versions (id) on delete cascade,
    tool_definition_id uuid not null references app.tool_definitions (id) on delete restrict,
    configuration jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint agent_tools_unique unique (agent_version_id, tool_definition_id)
);

create index if not exists ix_agent_tools_workspace_id
    on app.agent_tools (workspace_id);

-- ---------------------------------------------------------------------------
-- Synthetic CRM dataset (fictional records, labelled with is_demo)
-- ---------------------------------------------------------------------------
create table if not exists app.crm_companies (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    name text not null,
    industry text,
    website text,
    employee_count integer check (employee_count is null or employee_count >= 0),
    is_demo boolean not null default false,
    created_at timestamptz not null default now(),
    constraint crm_companies_name_unique unique (workspace_id, name)
);

create index if not exists ix_crm_companies_workspace_id
    on app.crm_companies (workspace_id);

create table if not exists app.crm_customers (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    company_id uuid references app.crm_companies (id) on delete set null,
    name text not null,
    email text not null,
    phone text,
    title text,
    status text not null default 'active'
        constraint crm_customers_status_valid
        check (status in ('active', 'prospect', 'churned')),
    is_demo boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists ix_crm_customers_workspace_id
    on app.crm_customers (workspace_id);
create index if not exists ix_crm_customers_company_id
    on app.crm_customers (company_id);
create unique index if not exists uq_crm_customers_workspace_email
    on app.crm_customers (workspace_id, lower(email));

create table if not exists app.crm_deals (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    customer_id uuid not null references app.crm_customers (id) on delete cascade,
    name text not null,
    amount numeric(14, 2) not null check (amount >= 0),
    currency char(3) not null default 'INR',
    stage text not null default 'prospecting'
        constraint crm_deals_stage_valid
        check (stage in ('prospecting', 'qualified', 'proposal', 'negotiation', 'won', 'lost')),
    probability integer not null default 20 check (probability between 0 and 100),
    owner_name text,
    last_contacted_at timestamptz,
    next_follow_up_at timestamptz,
    is_demo boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_crm_deals_workspace_last_contact
    on app.crm_deals (workspace_id, last_contacted_at);
create index if not exists ix_crm_deals_workspace_stage
    on app.crm_deals (workspace_id, stage);

create table if not exists app.crm_contacts (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    customer_id uuid not null references app.crm_customers (id) on delete cascade,
    deal_id uuid references app.crm_deals (id) on delete set null,
    channel text not null
        constraint crm_contacts_channel_valid
        check (channel in ('email', 'call', 'meeting', 'note')),
    summary text not null,
    contacted_at timestamptz not null default now(),
    created_by uuid references app.profiles (id) on delete set null,
    is_demo boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists ix_crm_contacts_workspace_contacted
    on app.crm_contacts (workspace_id, contacted_at desc);
create index if not exists ix_crm_contacts_deal_id on app.crm_contacts (deal_id);

-- ---------------------------------------------------------------------------
-- Runs, events and spans
-- ---------------------------------------------------------------------------
create table if not exists app.agent_runs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    agent_id uuid not null references app.agents (id) on delete restrict,
    agent_version_id uuid not null references app.agent_versions (id) on delete restrict,
    initiated_by uuid references app.profiles (id) on delete set null,
    status text not null default 'queued'
        constraint agent_runs_status_valid
        check (
            status in ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'awaiting_approval')
        ),
    input jsonb not null default '{}'::jsonb,
    output jsonb,
    model_config_id uuid references app.model_configs (id) on delete set null,
    started_at timestamptz,
    completed_at timestamptz,
    duration_ms integer check (duration_ms is null or duration_ms >= 0),
    token_usage jsonb not null default '{}'::jsonb,
    estimated_cost numeric(12, 6),
    error_code text,
    error_summary text,
    replay_of_run_id uuid references app.agent_runs (id) on delete set null,
    created_at timestamptz not null default now()
);

create index if not exists ix_agent_runs_workspace_created
    on app.agent_runs (workspace_id, created_at desc);
create index if not exists ix_agent_runs_workspace_status
    on app.agent_runs (workspace_id, status);
create index if not exists ix_agent_runs_agent_created
    on app.agent_runs (agent_id, created_at desc);

create table if not exists app.run_events (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    run_id uuid not null references app.agent_runs (id) on delete cascade,
    sequence_number integer not null check (sequence_number > 0),
    event_type text not null,
    event_status text not null default 'ok'
        constraint run_events_status_valid
        check (event_status in ('ok', 'error', 'warning', 'info')),
    payload jsonb not null default '{}'::jsonb,
    occurred_at timestamptz not null default now(),
    constraint run_events_sequence_unique unique (run_id, sequence_number)
);

create index if not exists ix_run_events_run_sequence
    on app.run_events (run_id, sequence_number);
create index if not exists ix_run_events_workspace_occurred
    on app.run_events (workspace_id, occurred_at desc);

create table if not exists app.trace_spans (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    run_id uuid not null references app.agent_runs (id) on delete cascade,
    parent_span_id uuid references app.trace_spans (id) on delete cascade,
    span_type text not null,
    name text not null,
    status text not null default 'running'
        constraint trace_spans_status_valid
        check (status in ('running', 'ok', 'error', 'cancelled')),
    started_at timestamptz not null default now(),
    ended_at timestamptz,
    duration_ms integer check (duration_ms is null or duration_ms >= 0),
    attributes jsonb not null default '{}'::jsonb
);

create index if not exists ix_trace_spans_run_started
    on app.trace_spans (run_id, started_at);
create index if not exists ix_trace_spans_parent
    on app.trace_spans (parent_span_id);

create table if not exists app.followup_drafts (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references app.workspaces (id) on delete cascade,
    customer_id uuid not null references app.crm_customers (id) on delete cascade,
    deal_id uuid references app.crm_deals (id) on delete set null,
    run_id uuid references app.agent_runs (id) on delete set null,
    channel text not null default 'email'
        constraint followup_drafts_channel_valid
        check (channel in ('email', 'call', 'note')),
    subject text not null default '',
    body text not null,
    status text not null default 'draft'
        constraint followup_drafts_status_valid
        check (status in ('draft', 'discarded')),
    created_by uuid references app.profiles (id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint followup_drafts_body_not_blank check (length(btrim(body)) > 0)
);

create index if not exists ix_followup_drafts_workspace_created
    on app.followup_drafts (workspace_id, created_at desc);

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------
do $triggers$
declare
    target text;
begin
    foreach target in array array[
        'model_providers', 'model_configs', 'agents', 'tool_definitions',
        'crm_deals', 'followup_drafts'
    ]
    loop
        execute format('drop trigger if exists trg_%s_touch on app.%I', target, target);
        execute format(
            'create trigger trg_%s_touch before update on app.%I '
            'for each row execute function app.touch_updated_at()',
            target, target
        );
    end loop;
end
$triggers$;

-- ---------------------------------------------------------------------------
-- Privileged helpers (non-exposed schema, security definer, auth.uid() based)
-- ---------------------------------------------------------------------------
create or replace function app_private.can_edit_workspace(target_workspace uuid)
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
              and m.role in ('owner', 'admin', 'developer')
        )
    $fn$;

create or replace function app_private.can_operate_workspace(target_workspace uuid)
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
              and m.role in ('owner', 'admin', 'developer', 'operator')
        )
    $fn$;

revoke all on function app_private.can_edit_workspace(uuid) from public;
revoke all on function app_private.can_operate_workspace(uuid) from public;
grant execute on function app_private.can_edit_workspace(uuid) to authenticated;
grant execute on function app_private.can_operate_workspace(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table app.model_providers enable row level security;
alter table app.model_configs enable row level security;
alter table app.agents enable row level security;
alter table app.agent_versions enable row level security;
alter table app.tool_definitions enable row level security;
alter table app.agent_tools enable row level security;
alter table app.crm_companies enable row level security;
alter table app.crm_customers enable row level security;
alter table app.crm_deals enable row level security;
alter table app.crm_contacts enable row level security;
alter table app.agent_runs enable row level security;
alter table app.run_events enable row level security;
alter table app.trace_spans enable row level security;
alter table app.followup_drafts enable row level security;

-- model_providers
drop policy if exists model_providers_select_member on app.model_providers;
create policy model_providers_select_member on app.model_providers
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists model_providers_insert_editor on app.model_providers;
create policy model_providers_insert_editor on app.model_providers
    for insert to authenticated
    with check (
        app_private.can_edit_workspace(workspace_id)
        and created_by = (select auth.uid())
    );

drop policy if exists model_providers_update_editor on app.model_providers;
create policy model_providers_update_editor on app.model_providers
    for update to authenticated
    using (app_private.can_edit_workspace(workspace_id))
    with check (app_private.can_edit_workspace(workspace_id));

drop policy if exists model_providers_delete_editor on app.model_providers;
create policy model_providers_delete_editor on app.model_providers
    for delete to authenticated
    using (app_private.can_edit_workspace(workspace_id));

-- model_configs
drop policy if exists model_configs_select_member on app.model_configs;
create policy model_configs_select_member on app.model_configs
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists model_configs_insert_editor on app.model_configs;
create policy model_configs_insert_editor on app.model_configs
    for insert to authenticated
    with check (app_private.can_edit_workspace(workspace_id));

drop policy if exists model_configs_update_editor on app.model_configs;
create policy model_configs_update_editor on app.model_configs
    for update to authenticated
    using (app_private.can_edit_workspace(workspace_id))
    with check (app_private.can_edit_workspace(workspace_id));

drop policy if exists model_configs_delete_editor on app.model_configs;
create policy model_configs_delete_editor on app.model_configs
    for delete to authenticated
    using (app_private.can_edit_workspace(workspace_id));

-- agents
drop policy if exists agents_select_member on app.agents;
create policy agents_select_member on app.agents
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists agents_insert_editor on app.agents;
create policy agents_insert_editor on app.agents
    for insert to authenticated
    with check (
        app_private.can_edit_workspace(workspace_id)
        and created_by = (select auth.uid())
    );

drop policy if exists agents_update_editor on app.agents;
create policy agents_update_editor on app.agents
    for update to authenticated
    using (app_private.can_edit_workspace(workspace_id))
    with check (app_private.can_edit_workspace(workspace_id));

drop policy if exists agents_delete_editor on app.agents;
create policy agents_delete_editor on app.agents
    for delete to authenticated
    using (app_private.can_edit_workspace(workspace_id));

-- agent_versions (immutability enforced by trigger; no update/delete policy)
drop policy if exists agent_versions_select_member on app.agent_versions;
create policy agent_versions_select_member on app.agent_versions
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists agent_versions_insert_editor on app.agent_versions;
create policy agent_versions_insert_editor on app.agent_versions
    for insert to authenticated
    with check (
        app_private.can_edit_workspace(workspace_id)
        and created_by = (select auth.uid())
    );

-- tool_definitions: global built-ins are readable by every authenticated user;
-- workspace custom tools follow membership.
drop policy if exists tool_definitions_select_visible on app.tool_definitions;
create policy tool_definitions_select_visible on app.tool_definitions
    for select to authenticated
    using (
        workspace_id is null
        or app_private.is_workspace_member(workspace_id)
    );

drop policy if exists tool_definitions_insert_editor on app.tool_definitions;
create policy tool_definitions_insert_editor on app.tool_definitions
    for insert to authenticated
    with check (
        workspace_id is not null
        and app_private.can_edit_workspace(workspace_id)
    );

drop policy if exists tool_definitions_update_editor on app.tool_definitions;
create policy tool_definitions_update_editor on app.tool_definitions
    for update to authenticated
    using (
        workspace_id is not null
        and app_private.can_edit_workspace(workspace_id)
    )
    with check (
        workspace_id is not null
        and app_private.can_edit_workspace(workspace_id)
    );

drop policy if exists tool_definitions_delete_editor on app.tool_definitions;
create policy tool_definitions_delete_editor on app.tool_definitions
    for delete to authenticated
    using (
        workspace_id is not null
        and app_private.can_edit_workspace(workspace_id)
    );

-- agent_tools
drop policy if exists agent_tools_select_member on app.agent_tools;
create policy agent_tools_select_member on app.agent_tools
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists agent_tools_insert_editor on app.agent_tools;
create policy agent_tools_insert_editor on app.agent_tools
    for insert to authenticated
    with check (app_private.can_edit_workspace(workspace_id));

drop policy if exists agent_tools_update_editor on app.agent_tools;
create policy agent_tools_update_editor on app.agent_tools
    for update to authenticated
    using (app_private.can_edit_workspace(workspace_id))
    with check (app_private.can_edit_workspace(workspace_id));

drop policy if exists agent_tools_delete_editor on app.agent_tools;
create policy agent_tools_delete_editor on app.agent_tools
    for delete to authenticated
    using (app_private.can_edit_workspace(workspace_id));

-- CRM tables: members read; operators (owner/admin/developer/operator) write.
drop policy if exists crm_companies_select_member on app.crm_companies;
create policy crm_companies_select_member on app.crm_companies
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists crm_companies_insert_operator on app.crm_companies;
create policy crm_companies_insert_operator on app.crm_companies
    for insert to authenticated
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_companies_update_operator on app.crm_companies;
create policy crm_companies_update_operator on app.crm_companies
    for update to authenticated
    using (app_private.can_operate_workspace(workspace_id))
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_companies_delete_operator on app.crm_companies;
create policy crm_companies_delete_operator on app.crm_companies
    for delete to authenticated
    using (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_customers_select_member on app.crm_customers;
create policy crm_customers_select_member on app.crm_customers
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists crm_customers_insert_operator on app.crm_customers;
create policy crm_customers_insert_operator on app.crm_customers
    for insert to authenticated
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_customers_update_operator on app.crm_customers;
create policy crm_customers_update_operator on app.crm_customers
    for update to authenticated
    using (app_private.can_operate_workspace(workspace_id))
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_customers_delete_operator on app.crm_customers;
create policy crm_customers_delete_operator on app.crm_customers
    for delete to authenticated
    using (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_deals_select_member on app.crm_deals;
create policy crm_deals_select_member on app.crm_deals
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists crm_deals_insert_operator on app.crm_deals;
create policy crm_deals_insert_operator on app.crm_deals
    for insert to authenticated
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_deals_update_operator on app.crm_deals;
create policy crm_deals_update_operator on app.crm_deals
    for update to authenticated
    using (app_private.can_operate_workspace(workspace_id))
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_deals_delete_operator on app.crm_deals;
create policy crm_deals_delete_operator on app.crm_deals
    for delete to authenticated
    using (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_contacts_select_member on app.crm_contacts;
create policy crm_contacts_select_member on app.crm_contacts
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists crm_contacts_insert_operator on app.crm_contacts;
create policy crm_contacts_insert_operator on app.crm_contacts
    for insert to authenticated
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_contacts_update_operator on app.crm_contacts;
create policy crm_contacts_update_operator on app.crm_contacts
    for update to authenticated
    using (app_private.can_operate_workspace(workspace_id))
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists crm_contacts_delete_operator on app.crm_contacts;
create policy crm_contacts_delete_operator on app.crm_contacts
    for delete to authenticated
    using (app_private.can_operate_workspace(workspace_id));

-- agent_runs: members read; editors create and update (the runtime uses the
-- database role, which is not subject to RLS; these policies protect direct
-- authenticated access if it is ever enabled).
drop policy if exists agent_runs_select_member on app.agent_runs;
create policy agent_runs_select_member on app.agent_runs
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists agent_runs_insert_editor on app.agent_runs;
create policy agent_runs_insert_editor on app.agent_runs
    for insert to authenticated
    with check (app_private.can_edit_workspace(workspace_id));

drop policy if exists agent_runs_update_editor on app.agent_runs;
create policy agent_runs_update_editor on app.agent_runs
    for update to authenticated
    using (app_private.can_edit_workspace(workspace_id))
    with check (app_private.can_edit_workspace(workspace_id));

-- run_events
drop policy if exists run_events_select_member on app.run_events;
create policy run_events_select_member on app.run_events
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists run_events_insert_editor on app.run_events;
create policy run_events_insert_editor on app.run_events
    for insert to authenticated
    with check (app_private.can_edit_workspace(workspace_id));

-- trace_spans
drop policy if exists trace_spans_select_member on app.trace_spans;
create policy trace_spans_select_member on app.trace_spans
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists trace_spans_insert_editor on app.trace_spans;
create policy trace_spans_insert_editor on app.trace_spans
    for insert to authenticated
    with check (app_private.can_edit_workspace(workspace_id));

-- followup_drafts
drop policy if exists followup_drafts_select_member on app.followup_drafts;
create policy followup_drafts_select_member on app.followup_drafts
    for select to authenticated
    using (app_private.is_workspace_member(workspace_id));

drop policy if exists followup_drafts_insert_operator on app.followup_drafts;
create policy followup_drafts_insert_operator on app.followup_drafts
    for insert to authenticated
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists followup_drafts_update_operator on app.followup_drafts;
create policy followup_drafts_update_operator on app.followup_drafts
    for update to authenticated
    using (app_private.can_operate_workspace(workspace_id))
    with check (app_private.can_operate_workspace(workspace_id));

drop policy if exists followup_drafts_delete_operator on app.followup_drafts;
create policy followup_drafts_delete_operator on app.followup_drafts
    for delete to authenticated
    using (app_private.can_operate_workspace(workspace_id));

-- ---------------------------------------------------------------------------
-- Data API posture for the new tables
-- ---------------------------------------------------------------------------
revoke all on all tables in schema app from anon, authenticated, service_role;
revoke all on all sequences in schema app from anon, authenticated, service_role;
