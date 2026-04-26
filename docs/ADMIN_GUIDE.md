# Admin Guide

This guide collects operational SQL and admin checks for the production app.

Run these queries in the Supabase SQL editor unless noted otherwise.

## Environment Variables

Environment variables are split between frontend and worker.

Frontend variables are browser-visible and must only contain public/browser-safe values. Worker variables are server-only and may contain secrets.

### Frontend `.env`

File:

```text
production_app/frontend/.env
```

Example:

```text
VITE_SUPABASE_URL=your_supabase_url_here
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key_here
VITE_WORKER_API_URL=http://localhost:8000
```

| Variable | Required | Purpose |
|---|---:|---|
| `VITE_SUPABASE_URL` | yes | Browser-safe Supabase project URL used by React. |
| `VITE_SUPABASE_ANON_KEY` | yes | Browser-safe Supabase anon key. This is not the service-role key. |
| `VITE_WORKER_API_URL` | yes | Base URL for the Python worker API. Use HTTPS worker URL in production. |

Frontend safety rules:

```text
never put SUPABASE_SERVICE_ROLE_KEY in frontend/.env
never put provider API keys in frontend/.env
never put any secret behind a VITE_ prefix
```

### Supabase Auth Redirects

Password reset emails return the user to the frontend URL. Configure Supabase Auth URL settings so the reset link can return to both local development and production.

Local development:

```text
http://localhost:5173
```

Production:

```text
https://your-production-frontend-domain
```

Supabase dashboard location:

```text
Authentication -> URL Configuration
```

Required behavior:

```text
Site URL points to the production frontend when deployed.
Redirect URLs include localhost for development and the production frontend URL.
```

### Worker `.env`

File:

```text
production_app/worker/.env
```

Example:

```text
SUPABASE_URL=your_supabase_url_here
SUPABASE_ANON_KEY=your_supabase_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
FINNHUB_API_KEY=your_finnhub_api_key_here
FMP_API_KEY=your_fmp_api_key_here
SEC_USER_AGENT="Your Name your-email@example.com"
WORKER_ALLOWED_ORIGINS=http://localhost:5173
WORKER_DEBUG_MARKET_REQUESTS=0
WORKER_ENABLE_REQUEST_LIMITER=1
WORKER_ENABLE_QUOTE_FAST_LANE=0
WORKER_QUOTE_MIN_INTERVAL_MS=300
WORKER_HISTORY_MIN_INTERVAL_MS=500
WORKER_FUNDAMENTALS_MIN_INTERVAL_MS=30000
```

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `SUPABASE_URL` | yes | none | Supabase project URL used by the worker. |
| `SUPABASE_ANON_KEY` | yes | none | Used by the worker to validate incoming user access tokens. |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | none | Server-only key used by the worker to write trusted data such as `stock_snapshots` and `refresh_jobs`. |
| `FINNHUB_API_KEY` | optional | empty | Enables Finnhub quote/profile and reported-financials fallback calls. |
| `FMP_API_KEY` | optional | empty | Enables FMP stable profile and stable income-statement calls. |
| `SEC_USER_AGENT` | recommended | development placeholder | User-Agent sent to SEC EDGAR APIs. Set this to a real name/app and email before production. |
| `WORKER_ALLOWED_ORIGINS` | yes | `http://localhost:5173` | Comma-separated CORS allowlist for browser origins allowed to call the worker. |
| `WORKER_DEBUG_MARKET_REQUESTS` | optional | `0` | When `1`, writes provider/API request attempts to `public.market_request_logs`. |
| `WORKER_ENABLE_REQUEST_LIMITER` | optional | `1` | Enables spacing between outbound provider calls. Keep enabled by default. |
| `WORKER_ENABLE_QUOTE_FAST_LANE` | optional | `0` | Allows the first visible-list quote batch attempt to bypass the quote limiter. Off by default. |
| `WORKER_QUOTE_MIN_INTERVAL_MS` | optional | `300` | Minimum spacing for quote-layer calls when the limiter applies. |
| `WORKER_HISTORY_MIN_INTERVAL_MS` | optional | `500` | Minimum spacing for history-layer calls when the limiter applies. |
| `WORKER_FUNDAMENTALS_MIN_INTERVAL_MS` | optional | `30000` | Minimum spacing for fundamentals-layer attempts when the limiter applies. |

Boolean true values:

```text
1
true
True
yes
```

Boolean false values:

```text
0
false
False
no
```

### Provider Key Behavior

If `FINNHUB_API_KEY` is present, the worker can use:

```text
Finnhub quote
Finnhub profile
Finnhub stock/financials-reported
```

If `FMP_API_KEY` is present, the worker can use:

```text
FMP stable/profile
FMP stable/income-statement
```

Current provider direction:

```text
visible price:
    Yahoo Spark / Yahoo quote batch if available
    Finnhub per-symbol fallback
    Yahoo Chart fallback

new ticker fundamentals:
    SEC EDGAR companyfacts for annual revenue/profit
    Finnhub reported financials fallback
    FMP stable income statement fallback
```

SEC EDGAR does not require an API key and is preferred for annual revenue/profit when a symbol maps to a SEC CIK. It should not be treated as an ownership source.

### Debug Settings

Use this when investigating provider calls:

```text
WORKER_DEBUG_MARKET_REQUESTS=1
```

Then restart the worker and query:

```text
public.market_request_logs
```

Turn it off for normal production:

```text
WORKER_DEBUG_MARKET_REQUESTS=0
```

### SEC Fundamentals Bootstrap

Dry-run a few symbols:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_sec_fundamentals.py --symbols AAPL MSFT NVDA --dry-run --debug-logs
```

Write annual SEC revenue/profit to `stock_snapshots`:

```powershell
python bootstrap_sec_fundamentals.py --symbols AAPL MSFT NVDA
```

Run from a file:

```powershell
python bootstrap_sec_fundamentals.py --file symbols.csv --dry-run
python bootstrap_sec_fundamentals.py --file symbols.csv
```

Run from bootstrapped index universes:

```powershell
python bootstrap_sec_fundamentals.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25 --dry-run --debug-logs
python bootstrap_sec_fundamentals.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25
```

Remove `--limit` when running the full phase-1 annual fundamentals preload.

This script uses the same safe merge path as normal refresh jobs. It should not overwrite existing good values with null/zero provider output.

### History Bootstrap

Dry-run a few symbols:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_history.py --symbols AAPL MSFT NVDA --dry-run --debug-logs
```

Run from bootstrapped index universes:

```powershell
python bootstrap_history.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25 --dry-run --debug-logs
python bootstrap_history.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25
```

History bootstrap uses one 6-year history call per symbol and calculates these locally:

```text
close_5y, close_3y, close_1y, close_6m, close_3m, close_1m
perf_5y, perf_3y, perf_1y, perf_6m, perf_3m, perf_1m
green_charts
```

It should not make separate provider calls for each percentage column.

### One-Symbol Full Bootstrap

Use this when a user enters a valid ticker that is not in the preloaded universe and the cache does not have it yet.

Dry-run:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_symbol.py SOFI --dry-run --debug-logs
```

Write to Supabase:

```powershell
python bootstrap_symbol.py SOFI
```

This uses the normal worker fetch path:

```text
quote
history
fundamentals
safe stock_snapshots merge
```

### SEC 13F Ownership Probe

Prototype institutional ownership from SEC 13F data sets:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python check_sec_13f_ownership.py AAPL
python check_sec_13f_ownership.py MSFT
```

If automatic CUSIP matching fails or is ambiguous:

```powershell
python check_sec_13f_ownership.py AAPL --cusip 037833100
```

The first run downloads the latest SEC quarterly 13F data-set ZIP into `worker/sec_cache`. Later runs reuse the cached ZIP.

Current prototype output includes:

```text
symbol
cusip
dataset
holder_count
filing_count
institutional_shares
reported_value
estimated_ownership_percent when price and market cap are cached
```

The standalone probe is diagnostic. Use the ownership bootstrap below for cache preparation.

### SEC 13F Ownership Bootstrap

Before writing ownership cache rows, run this SQL file in Supabase:

```text
production_app/docs/ownership_snapshots_schema.sql
```

Dry-run ownership for a few symbols:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_ownership.py --symbols AAPL MSFT NVDA --dry-run
```

Run from bootstrapped index universes:

```powershell
python bootstrap_ownership.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25 --dry-run
python bootstrap_ownership.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25
```

After price and market-cap cache is available, recalculate percentages from existing SEC ownership rows without reparsing the SEC ZIP:

```powershell
python bootstrap_ownership.py --recalculate-only --missing-only --limit 25 --dry-run
python bootstrap_ownership.py --recalculate-only --missing-only --limit 25
```

Recalculate a specific report period:

```powershell
python bootstrap_ownership.py --recalculate-only --report-period 01dec2025-28feb2026 --missing-only --limit 25
```

If automatic CUSIP matching fails or needs correction:

```powershell
python bootstrap_ownership.py --symbols BRK.B --cusip BRK.B=084670702 --dry-run
```

Production safety rules:

```text
do not show missing ownership as 0.00%
do not overwrite a positive cached ownership value with null or zero
cache report period and calculated_at so users understand the 13F lag
run this as an admin/background job, not during normal list loading
```

Status meanings:

```text
complete: SEC institutional shares were found and ownership percent was calculated
shares_only: SEC institutional shares were found, but price/market cap is missing so the percent cannot be calculated yet
missing: no matching SEC holdings were found for the resolved CUSIP
```

Inspect latest ownership cache:

```sql
select
    symbol,
    report_period,
    holder_count,
    filing_count,
    institutional_shares,
    estimated_ownership_percent,
    shares_outstanding_estimate,
    status,
    error,
    calculated_at
from public.ownership_snapshots
order by calculated_at desc, symbol
limit 100;
```

Find rows that need price/market-cap cache before ownership percent can be calculated:

```sql
select
    o.symbol,
    o.report_period,
    o.institutional_shares,
    o.status,
    s.price,
    s.market_cap,
    s.quote_status,
    s.snapshot_status
from public.ownership_snapshots o
left join public.stock_snapshots s
    on s.symbol = o.symbol
where o.status = 'shares_only'
order by o.symbol;
```

### Index Universe Bootstrap

Generate current index CSVs:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python create_index_lists.py --output-dir index_exports
```

Compare fetched constituents with `stock_universes` without writing:

```powershell
python create_index_lists.py --output-dir index_exports --diff-db
```

Write fetched index memberships to `stock_universes`:

```powershell
python create_index_lists.py --output-dir index_exports --write-db
```

Current script sources:

```text
S&P 500 constituents from Wikipedia public table
Nasdaq 100 constituents from Wikipedia public table
Dow 30 constituents from Wikipedia public table
```

Current schema behavior:

```text
new index members are upserted into stock_universes
removed members are reported in diff mode
removed members cannot be marked inactive until stock_universes gets active/removed_at columns
```

Optional schema upgrade for inactive/removed-member tracking:

```text
docs/stock_universes_membership_update.sql
```

### Limiter Settings

Recommended production defaults:

```text
WORKER_ENABLE_REQUEST_LIMITER=1
WORKER_ENABLE_QUOTE_FAST_LANE=0
WORKER_QUOTE_MIN_INTERVAL_MS=300
WORKER_HISTORY_MIN_INTERVAL_MS=500
WORKER_FUNDAMENTALS_MIN_INTERVAL_MS=30000
```

Do not disable the limiter unless doing a controlled local test.

### CORS Settings

Local:

```text
WORKER_ALLOWED_ORIGINS=http://localhost:5173
```

Production example:

```text
WORKER_ALLOWED_ORIGINS=https://your-frontend-domain.example
```

Multiple origins:

```text
WORKER_ALLOWED_ORIGINS=http://localhost:5173,https://your-frontend-domain.example
```

Do not use `*` for production.

### Env Change Restart Rule

After changing worker env vars, restart the worker:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

After changing frontend env vars, restart the Vite dev server:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\frontend
npm.cmd run dev
```

### Secret Rotation Rule

Rotate any key that appears in:

```text
chat
screenshots
logs
committed files
frontend env
browser console
shared documents
```

This especially applies to:

```text
SUPABASE_SERVICE_ROLE_KEY
FINNHUB_API_KEY
FMP_API_KEY
```

## Debug Market Requests

Enable worker debug logging locally or on the server:

```text
WORKER_DEBUG_MARKET_REQUESTS=1
```

Restart the worker after changing the env var.

Market request logs are stored in:

```text
public.market_request_logs
```

## Annual History Schema Update

Before testing the expanded annual revenue/profit columns, run:

```text
production_app/docs/annual_history_schema_update.sql
```

This adds:

```text
revenue_year_4_label
revenue_year_4_value
revenue_year_5_label
revenue_year_5_value
profit_year_4_label
profit_year_4_value
profit_year_5_label
profit_year_5_value
```

Run the schema update before restarting/testing the worker. The worker writes these fields during fundamentals upsert.

Optional cleanup lives in a separate file:

```text
production_app/docs/cleanup_fundamentals_cache.sql
```

Run the cleanup only if you intentionally want to force fundamentals refetching. It keeps watchlists, price, history, and chart baselines.

## 1M Performance Schema Update

Before relying on persisted one-month performance values, run:

```text
production_app/docs/performance_1m_schema_update.sql
```

This adds:

```text
close_1m
perf_1m
```

Existing rows may still show `1M %` in the frontend when `history_data` is cached, because the browser can calculate it from stored chart history. Persisted `perf_1m` updates after the next history refresh or quote refresh with a stored `close_1m`.

Use this query to see recent provider calls and spacing:

```sql
select
    job_id,
    sequence_number,
    symbol,
    layer,
    source,
    started_at,
    lag(started_at) over (
        partition by job_id
        order by sequence_number
    ) as previous_started_at,
    extract(epoch from (
        started_at - lag(started_at) over (
            partition by job_id
            order by sequence_number
        )
    )) as seconds_since_previous,
    status_code,
    ok,
    duration_ms,
    error
from public.market_request_logs
order by started_at desc, sequence_number desc
limit 100;
```

Use `started_at`, not `created_at`, to analyze request spacing. Log rows may be inserted in one batch, so `created_at` can be identical.

## Provider Calls By Source

Use this to see which providers are being used most:

```sql
select
    source,
    layer,
    count(*) as calls,
    count(*) filter (where ok) as ok_calls,
    count(*) filter (where not ok) as failed_calls,
    round(avg(duration_ms)) as avg_duration_ms,
    max(started_at) as last_started_at
from public.market_request_logs
where started_at >= now() - interval '24 hours'
group by source, layer
order by calls desc, source, layer;
```

## Failed Provider Calls

Use this to inspect current API errors:

```sql
select
    started_at,
    job_id,
    sequence_number,
    symbol,
    layer,
    source,
    status_code,
    duration_ms,
    error
from public.market_request_logs
where ok = false
order by started_at desc
limit 100;
```

## Calls By Job

Use this when a specific refresh felt slow or blocked:

```sql
select
    sequence_number,
    symbol,
    layer,
    source,
    started_at,
    finished_at,
    duration_ms,
    status_code,
    ok,
    error
from public.market_request_logs
where job_id = 'PASTE_JOB_ID_HERE'
order by sequence_number;
```

## Recent Refresh Jobs

Use this to see what the worker has been asked to do:

```sql
select
    id,
    user_id,
    watchlist_name,
    symbols,
    status,
    requested_by,
    error,
    created_at,
    started_at,
    finished_at,
    extract(epoch from (finished_at - started_at)) as runtime_seconds
from public.refresh_jobs
order by created_at desc
limit 50;
```

## Active Or Stuck Jobs

Use this to find jobs that did not finish:

```sql
select
    id,
    user_id,
    watchlist_name,
    symbols,
    status,
    requested_by,
    error,
    created_at,
    started_at,
    now() - coalesce(started_at, created_at) as age
from public.refresh_jobs
where status in ('queued', 'running')
order by created_at asc;
```

## Snapshot Health

Use this to see which cached symbols are complete, partial, or missing:

```sql
select
    symbol,
    price,
    quote_status,
    history_status,
    fundamentals_status,
    snapshot_status,
    price_updated_at,
    history_updated_at,
    fundamentals_updated_at,
    last_error
from public.stock_snapshots
order by updated_at desc nulls last, symbol
limit 100;
```

## Missing Or Partial Fundamentals

Use this to find rows where fundamentals need attention:

```sql
select
    symbol,
    name,
    fundamentals_status,
    fundamentals_updated_at,
    revenue_status,
    profit_status,
    inst_ownership,
    revenue_year_1_label,
    revenue_year_1_value,
    revenue_year_2_label,
    revenue_year_2_value,
    revenue_year_3_label,
    revenue_year_3_value,
    revenue_year_4_label,
    revenue_year_4_value,
    revenue_year_5_label,
    revenue_year_5_value,
    profit_year_1_label,
    profit_year_1_value,
    profit_year_2_label,
    profit_year_2_value,
    profit_year_3_label,
    profit_year_3_value,
    profit_year_4_label,
    profit_year_4_value,
    profit_year_5_label,
    profit_year_5_value,
    last_error
from public.stock_snapshots
where fundamentals_status is distinct from 'complete'
   or revenue_year_1_value is null
   or profit_year_1_value is null
order by fundamentals_updated_at nulls first, symbol;
```

## Stale Visible Price Candidates

Use this to find cached symbols with stale or missing prices:

```sql
select
    symbol,
    name,
    price,
    quote_status,
    price_updated_at,
    now() - price_updated_at as price_age
from public.stock_snapshots
where price_updated_at is null
   or price_updated_at < now() - interval '15 minutes'
order by price_updated_at nulls first, symbol;
```

This query is global. The app should only refresh the visible list, not every row returned here.

## Watchlists By User

Use this to inspect a user's watchlists:

```sql
select
    user_id,
    watchlist_name,
    ticker_symbol,
    comment,
    created_at
from public.watchlists
where user_id = 'PASTE_USER_ID_HERE'
order by watchlist_name, ticker_symbol;
```

## Duplicate Symbol Check

The same ticker is allowed in different watchlists for the same user. Duplicates are only invalid inside the same watchlist.

Use this to check for invalid duplicates:

```sql
select
    user_id,
    watchlist_name,
    ticker_symbol,
    count(*) as duplicate_count
from public.watchlists
group by user_id, watchlist_name, ticker_symbol
having count(*) > 1
order by duplicate_count desc;
```

## Watchlist Size Check

Use this to see list sizes:

```sql
select
    user_id,
    watchlist_name,
    count(*) as ticker_count
from public.watchlists
group by user_id, watchlist_name
order by ticker_count desc, watchlist_name;
```

## App Config

Use this to inspect runtime config values:

```sql
select
    key,
    value
from public.app_config
order by key;
```

Useful keys include:

```text
max_watchlists
max_tickers_per_list
visible_quote_ttl_minutes
visible_quote_batch_limit
enable_debug_output
```

## Redact Existing Secret Leaks In Logs

If an API key was accidentally stored in debug logs, redact it:

```sql
update public.market_request_logs
set error = regexp_replace(error, '(apikey|token)=([^&\s]+)', '\1=REDACTED', 'gi')
where error is not null
  and error ~* '(apikey|token)=';
```

After a real leak, rotate the provider key before production.

## Clear Old Debug Logs

Keep debug logs short-lived. Use this only for old diagnostics:

```sql
delete from public.market_request_logs
where created_at < now() - interval '14 days';
```

For local testing, you can clear all market request logs:

```sql
delete from public.market_request_logs;
```

Do not clear production logs if they are needed for active debugging.

## Clear Current Test Debug Logs

For local development, clear the current noisy test logs before a clean test run:

```sql
truncate table public.market_request_logs;
```

If you also want to clear old refresh job history from local testing:

```sql
truncate table public.market_request_logs;
delete from public.refresh_jobs
where created_at < now() - interval '5 minutes';
```

Safer alternative: keep recent jobs and delete only old debug logs:

```sql
delete from public.market_request_logs
where created_at < now() - interval '1 hour';
```

Do not truncate production logs while investigating an active user issue.

## Reset A Failed Snapshot Status

Use this if a symbol has an old error but valid cached data:

```sql
update public.stock_snapshots
set
    last_error = null,
    last_error_at = null,
    snapshot_status = case
        when quote_status = 'complete'
         and history_status = 'complete'
         and fundamentals_status = 'complete'
        then 'complete'
        else 'partial'
    end,
    updated_at = now()
where symbol = 'PASTE_SYMBOL_HERE';
```

## Check A Single Symbol Cache

Use this before deciding whether an API call is needed:

```sql
select *
from public.stock_snapshots
where symbol = 'PASTE_SYMBOL_HERE';
```

## Production Safety Checklist

Before exposing the app to real users:

```text
rotate any provider/Supabase keys pasted into chat, logs, screenshots, or documents
set WORKER_DEBUG_MARKET_REQUESTS=0 unless actively debugging
confirm CORS is locked to the frontend URL
confirm service-role key exists only on the worker/server
confirm frontend env does not contain service-role key
confirm refresh logs redact apikey/token values
confirm no broad full-table refresh runs on login/list switch
```
