alter table public.alerts
    add column if not exists watchlist_name text,
    add column if not exists interval_minutes integer not null default 1,
    add column if not exists last_triggered_price numeric,
    add column if not exists last_triggered_bar_time timestamptz,
    add column if not exists updated_at timestamptz not null default now();

create index if not exists alerts_symbol_active_idx
    on public.alerts (symbol, active);

create index if not exists alerts_user_symbol_idx
    on public.alerts (user_id, symbol, created_at desc);

create table if not exists public.alert_events (
    id uuid primary key default gen_random_uuid(),
    alert_id uuid not null references public.alerts(id) on delete cascade,
    user_id uuid not null,
    symbol text not null,
    trigger_price numeric,
    bar_time timestamptz,
    created_at timestamptz not null default now()
);

alter table public.alerts enable row level security;
alter table public.alert_events enable row level security;

drop policy if exists alerts_select_own on public.alerts;
create policy alerts_select_own
    on public.alerts
    for select
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists alerts_insert_own on public.alerts;
create policy alerts_insert_own
    on public.alerts
    for insert
    to authenticated
    with check (auth.uid() = user_id);

drop policy if exists alerts_update_own on public.alerts;
create policy alerts_update_own
    on public.alerts
    for update
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

drop policy if exists alerts_delete_own on public.alerts;
create policy alerts_delete_own
    on public.alerts
    for delete
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists alert_events_select_own on public.alert_events;
create policy alert_events_select_own
    on public.alert_events
    for select
    to authenticated
    using (auth.uid() = user_id);

create index if not exists alert_events_user_created_idx
    on public.alert_events (user_id, created_at desc);

create index if not exists alert_events_alert_created_idx
    on public.alert_events (alert_id, created_at desc);
