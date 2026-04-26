# Refresh Policy

This document is the production refresh design. The app must be cache-first, layer-aware, priority-aware, provider-aware, and safe against bursty market-data requests.

## Core Principles

- `stock_snapshots` is the shared master cache.
- The frontend loads cached data immediately from Supabase.
- User actions must not refresh unrelated tickers.
- Existing good data must never be overwritten by missing, null, zero, placeholder, or failed refresh data.
- A TTL means a layer is eligible for refresh, not that every stale row should refresh at once.
- Refreshes are layered: quote, history, fundamentals, ownership, and derived analysis have independent timestamps, statuses, retry rules, provider chains, and priorities.

## Data Layers

### Quote Layer

Fields:

```text
price
market_cap
name
price_updated_at
quote_status
```

Purpose:

```text
Most frequently updated layer. Used for visible-list freshness and recalculating performance from cached baselines.
```

### History Layer

Fields:

```text
close_5y
close_3y
close_1y
close_6m
close_1m
close_3m
history_data
history_updated_at
history_status
```

Purpose:

```text
Less frequent layer. Supplies baselines and chart data.
```

### Derived Analysis Layer

Fields:

```text
perf_5y
perf_3y
perf_1y
perf_6m
perf_1m
perf_3m
green_charts
```

Purpose:

```text
Recalculated whenever price changes if cached baselines exist. Does not require a new history fetch.
```

Formula:

```text
perf_1m = ((current_price - close_1m) / close_1m) * 100
perf_3m = ((current_price - close_3m) / close_3m) * 100
```

Green Charts:

```text
green_charts = Yes when perf_5y > 0, perf_1y > 0, and perf_3m > 0
```

### Fundamentals Layer

Fields:

```text
inst_ownership
revenue_status
profit_status
revenue_year_1_label
revenue_year_1_value
revenue_year_2_label
revenue_year_2_value
revenue_year_3_label
revenue_year_3_value
revenue_year_4_label
revenue_year_4_value
revenue_year_5_label
revenue_year_5_value
profit_year_1_label
profit_year_1_value
profit_year_2_label
profit_year_2_value
profit_year_3_label
profit_year_3_value
profit_year_4_label
profit_year_4_value
profit_year_5_label
profit_year_5_value
fundamentals_updated_at
fundamentals_status
```

Purpose:

```text
Slowest and most fragile layer. Updated infrequently and never on every simple user action.
```

Current annual-value safety rule:

```text
do not use current-calendar-year values as annual revenue/profit
in 2026, latest annual revenue/profit should come from 2025 or earlier
future fiscal-calendar logic can accept current-year annual data only when the annual report is confirmed complete
use only annual/FY financial statements for annual revenue/profit fields
Growth requires four annual values so it can test three year-over-year increases
```

### Ownership Layer

Fields:

```text
inst_ownership
ownership_updated_at
ownership_status
```

Purpose:

```text
Institutional ownership may come from a different provider than price, history, or fundamentals. Treat it as its own data group when provider coverage and rate limits make that useful.
```

The current schema still stores `inst_ownership` with fundamentals. Future schema work can split the timestamp/status if a separate provider becomes the default source.

## Provider Routing

Do not implement provider selection as one global switch.

Production provider logic should be category-aware. Each data group can have its own default provider and fallback order:

```text
quote
history
fundamentals
ownership
news/sentiment
analyst targets
screener/universe
```

Example initial-ticker flow:

```text
1. Use the quote provider chain to get price/name/market cap.
2. Use the history provider chain to get 3M/6M/1Y/3Y/5Y baselines.
3. Use the fundamentals provider chain to get revenue/profit fields.
4. Use the ownership provider chain to get institutional ownership.
5. Merge each successful group independently.
6. Mark the snapshot Partial when some groups are missing.
7. Retry only the missing groups according to their own cooldowns.
```

Provider fallback order should be configurable per group, not hard-coded:

```text
quote_provider_order = finnhub,fmp,yahoo_spark,yahoo_chart,yahoo_quote_api
history_provider_order = yahoo_chart,twelve_data,tiingo
fundamentals_provider_order = finnhub,fmp,alpha_vantage,yahoo_quote_summary
ownership_provider_order = finnhub,fmp,nasdaq_data_link
screener_provider_order = fmp,mboum,eodhd
```

These are design examples, not final production defaults. A provider must prove field coverage, stability, legal fit, rate limits, and data quality before becoming a default.

Failure behavior:

```text
provider returns rate limit
    mark that provider cooling_down for this group
    try next configured provider if allowed
    do not overwrite existing good values

provider returns missing field
    keep old value if valid
    mark field/group partial
    try next provider only for missing fields when configured

all providers fail
    preserve cache
    show old data or N/A
    schedule retry_after for the affected group only
```

Provider routing should eventually live behind internal worker modules so the rest of the app asks for a data group, not for a specific API:

```text
get_quote(symbols)
get_history(symbol)
get_fundamentals(symbol)
get_ownership(symbol)
run_screener(screen_id)
```

## Recommended Config Defaults

Store these in `app_config` or worker settings.

```text
visible_quote_ttl_minutes = 15
hidden_quote_ttl_minutes = 240
market_closed_quote_ttl_minutes = 720

visible_history_ttl_hours = 24
hidden_history_ttl_hours = 48

visible_fundamentals_ttl_hours = 24
hidden_fundamentals_ttl_hours = 48

quote_retry_after_minutes = 15
history_retry_after_minutes = 60
fundamentals_retry_after_hours = 12

visible_quote_batch_limit = 30
visible_history_batch_limit = 5
visible_fundamentals_batch_limit = 2

quote_min_spacing_seconds = 1
history_min_spacing_seconds = 5
fundamentals_min_spacing_seconds = 30

history_refresh_jitter_hours = 6
fundamentals_refresh_jitter_hours = 24
```

## Freshness States

Each layer should be classified independently:

```text
fresh
    updated recently enough; show normally

acceptable
    older than ideal TTL but still useful; show normally with subtle status

stale
    too old; show old value but queue refresh

missing
    no usable value; show N/A and prioritize refresh

error
    last attempt failed; preserve old value and respect retry_after

cooling_down
    upstream rate-limited; do not retry until retry_after
```

## Anti-Burst Rules

Do not refresh every stale row immediately when a TTL expires.

TTL means:

```text
eligible for refresh
```

Not:

```text
refresh all stale rows now
```

Use:

```text
run_after timestamps
random jitter
priority ordering
batch limits
spacing between calls
max jobs per worker cycle
```

## Always-On Background Maintenance

On Oracle, the worker is expected to run continuously. When users are not actively using the app, the worker can improve the master cache at a relaxed pace.

This is not a blind poller. The scheduler should inspect database state and choose the best next work item.

Priority order:

```text
currently visible user watchlists
recently visible user watchlists
daily/power-user watchlists
weekly-user watchlists
other user watchlists
index-universe prefill tickers
unused master-cache tickers
```

Scheduler inputs:

```text
watchlist_count per symbol
visible_count per symbol
last_visible_at
last_used_at
user activity frequency
price_updated_at
history_updated_at
fundamentals_updated_at
missing annual revenue/profit fields
provider cooldowns
remaining provider call budget
```

Low-traffic behavior:

```text
run missing history jobs slowly
run missing fundamentals jobs slowly
check whether a not-yet-published annual year may now be available
refresh popular universe tickers if user-facing work is idle
avoid unused tickers when provider budget is tight
```

This always-on maintenance is a performance booster for launch because the admin can prefill common tickers before real users log in.

## Request Limiter

All outbound market-data calls should pass through the shared worker limiter by default.

Environment defaults:

```text
WORKER_ENABLE_REQUEST_LIMITER=1
WORKER_ENABLE_QUOTE_FAST_LANE=0
WORKER_QUOTE_MIN_INTERVAL_MS=300
WORKER_HISTORY_MIN_INTERVAL_MS=500
WORKER_FUNDAMENTALS_MIN_INTERVAL_MS=30000
```

Default behavior:

```text
visible quote refresh uses the limiter
history uses the limiter
fundamentals uses the strictest limiter
```

Quote fast lane:

```text
WORKER_ENABLE_QUOTE_FAST_LANE=1
```

This allows the one visible-list batch quote attempt to bypass the normal quote limiter. It is off by default. Fallback quote calls still use the limiter.

Use the fast lane only if visible-list price refresh is too slow with the default limiter.

Future columns:

```text
quote_refresh_after
history_refresh_after
fundamentals_refresh_after

quote_last_error
history_last_error
fundamentals_last_error
```

After success:

```text
refresh_after = now + ttl + jitter
```

After rate limit or failure:

```text
refresh_after = now + retry_after
```

## User Action Behavior

## Strict Call Budget

Default rule:

```text
No market-data API calls just because a user logs in, switches lists, edits comments, sorts, or looks around.
```

Allowed calls:

```text
1. Visible-list price refresh on initial visible-list load when price is stale.
2. Visible-list price refresh every configured interval, default 15 minutes.
3. New ticker initial snapshot only when the symbol does not already exist in stock_snapshots.
4. Explicit scheduled slow-layer jobs that are due and spaced out.
```

App/list load:

```text
1. Load watchlist rows from Supabase.
2. Load stock_snapshots from Supabase.
3. Render immediately.
4. Refresh stale visible prices only.
```

Do not call:

```text
history
fundamentals
ownership
hidden watchlists
full-table refresh
```

Visible price refresh:

```text
default interval = 15 minutes
max visible symbols = 30
preferred path = one bulk-capable quote request
fallback path = individual quote calls
```

If individual fallback quote calls are needed for a scheduled 15-minute refresh, spread them over a window instead of bursting. For example:

```text
30 symbols across 120 seconds = about 4 seconds between individual calls
```

The first visible-list price refresh after app load may run faster, but it must still be quote-only.

### Add New Ticker

Highest priority.

Behavior:

```text
1. Validate only the new symbol.
2. If symbol exists in stock_snapshots, add the watchlist row and render cached data immediately.
3. If existing price is stale, refresh price only.
4. If symbol does not exist in stock_snapshots, create a pending visible row.
5. Fetch quote/profile for only that symbol.
6. Fetch history baselines for only that symbol.
7. Attempt fundamentals for only that symbol.
8. If quote/history succeeds but fundamentals or ownership fails, keep the ticker as Partial/Missing Fundamentals.
9. Queue retries only for the failed groups after their cooldowns.
10. Do not refresh the rest of the watchlist.
```

Expected result:

```text
New row appears quickly with price/history-derived analysis.
Fundamentals may show N/A until available.
```

UX rule:

```text
Do not block the visible row on fundamentals.
Insert or display the row as pending immediately after the user adds it.
Write quote/history as soon as they are available.
Show missing fundamentals fields as Updating... while the layer is still pending.
If the fundamentals provider fails, mark the fundamentals group missing and increase its retry priority.
```

### Open Or Switch Visible Watchlist

Behavior:

```text
1. Load watchlist rows immediately.
2. Load stock_snapshots immediately.
3. Render cached table immediately.
4. Inspect timestamps/status per row/layer.
5. Batch refresh stale visible prices, max 30.
6. Recalculate performance and Green Charts from cached baselines.
7. Queue history/fundamentals only if stale and capacity allows.
```

Expected result:

```text
Table appears instantly from cache.
Visible prices update within a few seconds.
Analysis colors update after price recalculation.
History/fundamentals improve in the background.
```

### Refresh Button On Visible List

Behavior:

```text
The user sees one Refresh button.
The app decides internally what is due from timestamps, missing fields, retry windows, and refresh policy.
If visible prices are still inside the configured 15 minute window, explain that data was refreshed recently.
Do not expose quote/history/fundamentals/provider details to normal users.
Do not touch hidden watchlists unless background capacity exists.
```

Internal actions the policy may choose:

```text
visible quote refresh
missing history refresh
missing/stale fundamentals refresh
cooldown/retry scheduling
no-op with user-friendly message
```

### Edit Comment

Behavior:

```text
Update watchlists.comment only.
Do not refresh ticker data.
```

### Delete Ticker From Watchlist

Behavior:

```text
Delete only that watchlist row.
Do not delete stock_snapshots.
Do not affect other watchlists or users.
```

## Job Priorities

Suggested priority values:

```text
100 add_symbol_initial_quote_history
90  add_symbol_initial_fundamentals
85  add_symbol_cached_ownership
80  visible_list_quote
70  visible_missing_history_or_fundamentals
60  recently_visible_quote
50  active_user_background_history_or_fundamentals
40  weekly_user_background_history_or_fundamentals
30  other_watchlist_background_work
20  index_universe_prefill
15  sec_13f_ownership_prefill
10  unused_master_ticker_maintenance
```

The worker should process:

```text
priority desc
run_after asc
created_at asc
```

## Batch Price Refresh

Visible list price refresh must batch up to 30 symbols in one Yahoo quote request:

```text
/v7/finance/quote?symbols=AAPL,MSFT,JPM,V,UNH
```

Expected target:

```text
30 visible tickers updated in 2-6 seconds
```

The batch quote refresh should update:

```text
price
market_cap
price_updated_at
quote_status
perf_5y
perf_3y
perf_1y
perf_6m
perf_1m
perf_3m
green_charts
```

It should not touch:

```text
revenue_status
profit_status
inst_ownership
fundamental year fields
history baselines unless a history job is running
```

## Bootstrap And Ownership

The full admin bootstrap process is documented in:

```text
docs/BOOTSTRAP_PROCESS.md
```

Ownership policy:

```text
Institutional ownership must be cached before the user needs it.
Do not scan SEC 13F filings when a user opens a list or adds a ticker.
Do not overwrite a positive cached ownership value with zero/null provider output.
Do not show 0.00% unless the value is confirmed true.
Show Ownership pending or Missing if SEC 13F ownership is not cached yet.
```

SEC 13F ownership jobs should run:

```text
after quarterly 13F filing windows
during low-traffic server time
as an admin bootstrap phase before launch
with lower priority than visible user refresh work
```

## Debug Market Request Logging

The worker can log market request attempts for burst analysis.

Enable locally with:

```text
WORKER_DEBUG_MARKET_REQUESTS=1
```

When enabled, the worker writes one row per market operation to:

```text
public.market_request_logs
```

Logged fields:

```text
job_id
symbol
layer
source
sequence_number
started_at
finished_at
duration_ms
ok
status_code
error
```

Use `started_at`, not `created_at`, when analyzing spacing between market requests. Rows may be inserted into Supabase as a batch, so `created_at` can be identical for multiple logged requests.

Debug query:

```sql
select
    job_id,
    sequence_number,
    symbol,
    layer,
    source,
    started_at,
    lag(started_at) over (partition by job_id order by sequence_number) as previous_started_at,
    extract(epoch from (
        started_at - lag(started_at) over (partition by job_id order by sequence_number)
    )) as seconds_since_previous,
    status_code,
    ok,
    duration_ms,
    error
from public.market_request_logs
order by started_at desc, sequence_number desc
limit 100;
```

Sources include:

```text
yahoo_quote_api
yahoo_chart_api
yfinance_info
yfinance_history
yfinance_financials
```

This is intended to answer:

```text
how many calls happened before a Yahoo/yfinance error
how much time passed between calls
which layer/source caused rate limiting
whether a user action created a burst
```

Keep this disabled in normal production unless diagnosing rate limits.

## Future Worker Modules

Suggested structure:

```text
worker/app/refresh_policy.py
worker/app/refresh_jobs.py
worker/app/quote_layer.py
worker/app/history_layer.py
worker/app/fundamentals_layer.py
worker/app/ownership_layer.py
worker/app/provider_router.py
worker/app/analysis_signature.py
```

The policy module should decide what is stale and what should be queued. Fetch modules should only fetch and merge layer data.
