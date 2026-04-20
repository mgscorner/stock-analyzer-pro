-- Annual history schema update for the production app.
-- Run this in the Supabase SQL editor before testing the expanded annual columns.
-- This is non-destructive: it adds columns and does not delete watchlists.

alter table public.stock_snapshots
    add column if not exists revenue_year_4_label integer,
    add column if not exists revenue_year_4_value numeric,
    add column if not exists revenue_year_5_label integer,
    add column if not exists revenue_year_5_value numeric,
    add column if not exists profit_year_4_label integer,
    add column if not exists profit_year_4_value numeric,
    add column if not exists profit_year_5_label integer,
    add column if not exists profit_year_5_value numeric;
