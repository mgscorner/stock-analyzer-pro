-- Adds 1-month baseline and performance columns.
-- Run in Supabase SQL editor before relying on persisted 1M values.
-- Existing rows can still display 1M from cached history_data until history is refreshed.

alter table public.stock_snapshots
    add column if not exists close_1m numeric,
    add column if not exists perf_1m numeric;
