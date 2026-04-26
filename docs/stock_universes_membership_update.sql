-- Optional schema upgrade for index membership maintenance.
-- Run this before implementing inactive/removed-member tracking.

alter table public.stock_universes
    add column if not exists source text,
    add column if not exists active boolean not null default true,
    add column if not exists added_at timestamptz default now(),
    add column if not exists removed_at timestamptz,
    add column if not exists last_seen_at timestamptz default now();

create index if not exists stock_universes_active_idx
    on public.stock_universes (universe_name, active, symbol);
