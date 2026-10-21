-- Row Level Security regression checks.
--
-- Executed in CI and locally after migrations:
--
--     psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/rls_policies.sql
--
-- Every check raises an exception, so a non-zero exit fails the build. No
-- pgTAP dependency: these are plain PL/pgSQL assertions over the catalog.

do $rls$
declare
    missing_rls text[];
    missing_policy text[];
    wrong_role text[];
    missing_with_check text[];
    deprecated_helper text[];
begin
    -- 1. Every table in the `app` schema must have RLS enabled.
    select array_agg(c.relname order by c.relname)
      into missing_rls
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'app'
       and c.relkind = 'r'
       and not c.relrowsecurity;

    if missing_rls is not null then
        raise exception 'RLS is not enabled on: %', array_to_string(missing_rls, ', ');
    end if;

    -- 2. Every table must carry at least one policy. `local_credentials` is the
    --    single documented exception: it is development-only and must have no
    --    policy at all, so that the authenticated role can never reach it.
    select array_agg(c.relname order by c.relname)
      into missing_policy
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'app'
       and c.relkind = 'r'
       and c.relname <> 'local_credentials'
       and not exists (
           select 1 from pg_policies p
            where p.schemaname = 'app' and p.tablename = c.relname
       );

    if missing_policy is not null then
        raise exception 'Tables without any policy: %', array_to_string(missing_policy, ', ');
    end if;

    -- 3. `local_credentials` must stay policy-free.
    if exists (select 1 from pg_policies where schemaname = 'app' and tablename = 'local_credentials') then
        raise exception 'app.local_credentials must not carry RLS policies (development-only table)';
    end if;

    -- 4. Policies must target an explicit role, never rely on public/default.
    select array_agg(format('%s.%s', p.tablename, p.policyname) order by p.tablename, p.policyname)
      into wrong_role
      from pg_policies p
     where p.schemaname = 'app'
       and p.roles <> '{authenticated}';

    if wrong_role is not null then
        raise exception 'Policies must target the authenticated role explicitly: %',
            array_to_string(wrong_role, ', ');
    end if;

    -- 5. UPDATE policies need both USING and WITH CHECK, otherwise a row could
    --    be reassigned to another owner.
    select array_agg(format('%s.%s', p.tablename, p.policyname) order by p.tablename, p.policyname)
      into missing_with_check
      from pg_policies p
     where p.schemaname = 'app'
       and p.cmd = 'UPDATE'
       and (p.qual is null or p.with_check is null);

    if missing_with_check is not null then
        raise exception 'UPDATE policies missing USING or WITH CHECK: %',
            array_to_string(missing_with_check, ', ');
    end if;

    -- 6. The deprecated `auth.role()` helper must not appear in any predicate.
    select array_agg(format('%s.%s', p.tablename, p.policyname) order by p.tablename, p.policyname)
      into deprecated_helper
      from pg_policies p
     where p.schemaname = 'app'
       and (coalesce(p.qual, '') || coalesce(p.with_check, '')) like '%auth.role(%';

    if deprecated_helper is not null then
        raise exception 'Policies must not use auth.role(): %', array_to_string(deprecated_helper, ', ');
    end if;

    raise notice 'RLS policy checks passed';
end
$rls$;
