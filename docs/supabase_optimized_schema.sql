-- Schema for app/AnalyzerApp_optimized.py
-- Run in Supabase SQL editor, then enable RLS policies appropriate for your project.

create table if not exists public.stock_snapshots (
    symbol text primary key,
    name text,
    price numeric,
    market_cap numeric,
    inst_ownership numeric,
    revenue_status text,
    profit_status text,
    green_charts text,
    perf_5y numeric,
    perf_3y numeric,
    perf_1y numeric,
    perf_6m numeric,
    perf_1m numeric,
    perf_3m numeric,
    revenue_year_1_label integer,
    revenue_year_1_value numeric,
    revenue_year_2_label integer,
    revenue_year_2_value numeric,
    revenue_year_3_label integer,
    revenue_year_3_value numeric,
    revenue_year_4_label integer,
    revenue_year_4_value numeric,
    revenue_year_5_label integer,
    revenue_year_5_value numeric,
    profit_year_1_label integer,
    profit_year_1_value numeric,
    profit_year_2_label integer,
    profit_year_2_value numeric,
    profit_year_3_label integer,
    profit_year_3_value numeric,
    profit_year_4_label integer,
    profit_year_4_value numeric,
    profit_year_5_label integer,
    profit_year_5_value numeric,
    close_5y numeric,
    close_3y numeric,
    close_1y numeric,
    close_6m numeric,
    close_1m numeric,
    close_3m numeric,
    history_data jsonb default '[]'::jsonb,
    quote_status text,
    history_status text,
    fundamentals_status text,
    snapshot_status text,
    quote_last_error text,
    history_last_error text,
    fundamentals_last_error text,
    quote_retry_after timestamptz,
    history_retry_after timestamptz,
    fundamentals_retry_after timestamptz,
    price_updated_at timestamptz,
    history_updated_at timestamptz,
    fundamentals_updated_at timestamptz,
    last_error text,
    last_error_at timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

alter table public.stock_snapshots
    add column if not exists name text,
    add column if not exists price numeric,
    add column if not exists market_cap numeric,
    add column if not exists inst_ownership numeric,
    add column if not exists revenue_status text,
    add column if not exists profit_status text,
    add column if not exists green_charts text,
    add column if not exists perf_5y numeric,
    add column if not exists perf_3y numeric,
    add column if not exists perf_1y numeric,
    add column if not exists perf_6m numeric,
    add column if not exists perf_1m numeric,
    add column if not exists perf_3m numeric,
    add column if not exists revenue_year_1_label integer,
    add column if not exists revenue_year_1_value numeric,
    add column if not exists revenue_year_2_label integer,
    add column if not exists revenue_year_2_value numeric,
    add column if not exists revenue_year_3_label integer,
    add column if not exists revenue_year_3_value numeric,
    add column if not exists revenue_year_4_label integer,
    add column if not exists revenue_year_4_value numeric,
    add column if not exists revenue_year_5_label integer,
    add column if not exists revenue_year_5_value numeric,
    add column if not exists profit_year_1_label integer,
    add column if not exists profit_year_1_value numeric,
    add column if not exists profit_year_2_label integer,
    add column if not exists profit_year_2_value numeric,
    add column if not exists profit_year_3_label integer,
    add column if not exists profit_year_3_value numeric,
    add column if not exists profit_year_4_label integer,
    add column if not exists profit_year_4_value numeric,
    add column if not exists profit_year_5_label integer,
    add column if not exists profit_year_5_value numeric,
    add column if not exists close_5y numeric,
    add column if not exists close_3y numeric,
    add column if not exists close_1y numeric,
    add column if not exists close_6m numeric,
    add column if not exists close_1m numeric,
    add column if not exists close_3m numeric,
    add column if not exists history_data jsonb default '[]'::jsonb,
    add column if not exists quote_status text,
    add column if not exists history_status text,
    add column if not exists fundamentals_status text,
    add column if not exists snapshot_status text,
    add column if not exists quote_last_error text,
    add column if not exists history_last_error text,
    add column if not exists fundamentals_last_error text,
    add column if not exists quote_retry_after timestamptz,
    add column if not exists history_retry_after timestamptz,
    add column if not exists fundamentals_retry_after timestamptz,
    add column if not exists price_updated_at timestamptz,
    add column if not exists history_updated_at timestamptz,
    add column if not exists fundamentals_updated_at timestamptz,
    add column if not exists last_error text,
    add column if not exists last_error_at timestamptz,
    add column if not exists created_at timestamptz default now(),
    add column if not exists updated_at timestamptz default now();

create index if not exists stock_snapshots_price_updated_idx
    on public.stock_snapshots (price_updated_at);

create index if not exists stock_snapshots_history_updated_idx
    on public.stock_snapshots (history_updated_at);

create index if not exists stock_snapshots_fundamentals_updated_idx
    on public.stock_snapshots (fundamentals_updated_at);

create index if not exists stock_snapshots_quote_retry_idx
    on public.stock_snapshots (quote_retry_after);

create index if not exists stock_snapshots_history_retry_idx
    on public.stock_snapshots (history_retry_after);

create index if not exists stock_snapshots_fundamentals_retry_idx
    on public.stock_snapshots (fundamentals_retry_after);

create table if not exists public.app_config (
    key text primary key,
    value text not null
);

insert into public.app_config (key, value)
values
    ('price_ttl_minutes', '15'),
    ('history_ttl_hours', '24'),
    ('fundamentals_ttl_hours', '24'),
    ('alert_price_ttl_minutes', '2'),
    ('auto_refresh_stale_on_load', '0'),
    ('enable_scanner', '0'),
    ('max_watchlists', '5'),
    ('max_tickers_per_list', '30'),
    ('market_closed_price_ttl_minutes', '720'),
    ('enable_table_styling', '1'),
    ('enable_debug_output', '0'),
    ('visible_quote_ttl_minutes', '15'),
    ('hidden_quote_ttl_minutes', '240'),
    ('visible_history_ttl_hours', '24'),
    ('hidden_history_ttl_hours', '48'),
    ('visible_fundamentals_ttl_hours', '24'),
    ('hidden_fundamentals_ttl_hours', '48'),
    ('quote_retry_after_minutes', '15'),
    ('history_retry_after_minutes', '60'),
    ('fundamentals_retry_after_hours', '12'),
    ('visible_quote_batch_limit', '30'),
    ('visible_history_batch_limit', '5'),
    ('visible_fundamentals_batch_limit', '2'),
    ('debug_market_requests', '0')
on conflict (key) do nothing;

create table if not exists public.watchlists (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    ticker_symbol text not null,
    comment text,
    watchlist_name text not null default 'Default',
    created_at timestamptz default now()
);

alter table public.watchlists
    add column if not exists id uuid default gen_random_uuid(),
    add column if not exists user_id uuid,
    add column if not exists ticker_symbol text,
    add column if not exists comment text,
    add column if not exists watchlist_name text not null default 'Default',
    add column if not exists created_at timestamptz default now();

alter table public.watchlists
    drop constraint if exists watchlists_user_id_ticker_symbol_key;

create unique index if not exists watchlists_user_list_symbol_key
    on public.watchlists (user_id, watchlist_name, ticker_symbol);

create index if not exists watchlists_user_list_idx
    on public.watchlists (user_id, watchlist_name);

create table if not exists public.refresh_jobs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    watchlist_name text,
    symbols text[] not null default '{}',
    status text not null default 'queued',
    requested_by text,
    error text,
    created_at timestamptz default now(),
    started_at timestamptz,
    finished_at timestamptz
);

alter table public.refresh_jobs
    add column if not exists id uuid default gen_random_uuid(),
    add column if not exists user_id uuid,
    add column if not exists watchlist_name text,
    add column if not exists symbols text[] not null default '{}',
    add column if not exists status text not null default 'queued',
    add column if not exists requested_by text,
    add column if not exists error text,
    add column if not exists created_at timestamptz default now(),
    add column if not exists started_at timestamptz,
    add column if not exists finished_at timestamptz;

create index if not exists refresh_jobs_user_created_idx
    on public.refresh_jobs (user_id, created_at desc);

create index if not exists refresh_jobs_status_created_idx
    on public.refresh_jobs (status, created_at);

create table if not exists public.market_request_logs (
    id uuid primary key default gen_random_uuid(),
    job_id uuid,
    symbol text,
    layer text,
    source text,
    sequence_number integer,
    started_at timestamptz default now(),
    finished_at timestamptz,
    duration_ms integer,
    ok boolean,
    status_code integer,
    error text,
    created_at timestamptz default now()
);

alter table public.market_request_logs
    add column if not exists id uuid default gen_random_uuid(),
    add column if not exists job_id uuid,
    add column if not exists symbol text,
    add column if not exists layer text,
    add column if not exists source text,
    add column if not exists sequence_number integer,
    add column if not exists started_at timestamptz default now(),
    add column if not exists finished_at timestamptz,
    add column if not exists duration_ms integer,
    add column if not exists ok boolean,
    add column if not exists status_code integer,
    add column if not exists error text,
    add column if not exists created_at timestamptz default now();

create index if not exists market_request_logs_job_idx
    on public.market_request_logs (job_id, sequence_number);

create index if not exists market_request_logs_created_idx
    on public.market_request_logs (created_at desc);

create table if not exists public.stock_universes (
    universe_name text not null,
    symbol text not null,
    created_at timestamptz default now(),
    primary key (universe_name, symbol)
);

alter table public.stock_universes
    add column if not exists universe_name text,
    add column if not exists symbol text,
    add column if not exists created_at timestamptz default now();

create table if not exists public.alerts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    symbol text not null,
    condition_type text not null default 'price_above',
    threshold numeric,
    active boolean not null default true,
    last_checked_at timestamptz,
    last_triggered_at timestamptz,
    created_at timestamptz default now()
);

alter table public.alerts
    add column if not exists id uuid default gen_random_uuid(),
    add column if not exists user_id uuid,
    add column if not exists symbol text,
    add column if not exists condition_type text not null default 'price_above',
    add column if not exists threshold numeric,
    add column if not exists active boolean not null default true,
    add column if not exists last_checked_at timestamptz,
    add column if not exists last_triggered_at timestamptz,
    add column if not exists created_at timestamptz default now();

create index if not exists alerts_user_active_idx
    on public.alerts (user_id, active);
