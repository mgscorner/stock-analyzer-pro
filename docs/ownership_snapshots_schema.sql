-- SEC 13F institutional ownership cache.
-- Run in Supabase SQL editor before using bootstrap_ownership.py with writes.

create table if not exists public.ownership_snapshots (
    symbol text not null,
    cusip text not null,
    dataset text not null,
    report_period text not null,
    holder_count integer,
    filing_count integer,
    institutional_shares numeric,
    reported_value numeric,
    estimated_ownership_percent numeric,
    shares_outstanding_estimate numeric,
    top_issuer_names jsonb,
    calculated_at timestamptz not null default now(),
    status text not null default 'complete',
    error text,
    primary key (symbol, report_period)
);

alter table public.ownership_snapshots
    add column if not exists symbol text,
    add column if not exists cusip text,
    add column if not exists dataset text,
    add column if not exists report_period text,
    add column if not exists holder_count integer,
    add column if not exists filing_count integer,
    add column if not exists institutional_shares numeric,
    add column if not exists reported_value numeric,
    add column if not exists estimated_ownership_percent numeric,
    add column if not exists shares_outstanding_estimate numeric,
    add column if not exists top_issuer_names jsonb,
    add column if not exists calculated_at timestamptz not null default now(),
    add column if not exists status text not null default 'complete',
    add column if not exists error text;

create index if not exists ownership_snapshots_symbol_idx
    on public.ownership_snapshots (symbol);

create index if not exists ownership_snapshots_report_period_idx
    on public.ownership_snapshots (report_period desc);
