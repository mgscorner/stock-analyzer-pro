-- Optional local cleanup for the experimental/bad fundamentals cache.
-- Run this only if you intentionally want to force fundamentals refetching.
-- This keeps watchlists, price, history, and chart baselines.

update public.stock_snapshots
set
    fundamentals_status = 'missing',
    fundamentals_updated_at = null,
    inst_ownership = null,
    revenue_status = null,
    profit_status = null,
    revenue_year_1_label = null,
    revenue_year_1_value = null,
    revenue_year_2_label = null,
    revenue_year_2_value = null,
    revenue_year_3_label = null,
    revenue_year_3_value = null,
    revenue_year_4_label = null,
    revenue_year_4_value = null,
    revenue_year_5_label = null,
    revenue_year_5_value = null,
    profit_year_1_label = null,
    profit_year_1_value = null,
    profit_year_2_label = null,
    profit_year_2_value = null,
    profit_year_3_label = null,
    profit_year_3_value = null,
    profit_year_4_label = null,
    profit_year_4_value = null,
    profit_year_5_label = null,
    profit_year_5_value = null,
    updated_at = now();

-- Optional local debug cleanup.
-- Do not run during active production debugging.

truncate table public.market_request_logs;
