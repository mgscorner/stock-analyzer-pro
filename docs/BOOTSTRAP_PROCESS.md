# Admin Bootstrap Process

This document defines the production bootstrap routine for preparing the shared market-data cache before users need it.

Goal:

```text
popular symbols should already have cached data before a user adds them
the frontend should load from Supabase instantly
expensive provider/SEC work should happen in background admin jobs
bootstrap must be resumable and rate-limited
```

## Scope

Bootstrap is an admin/background process. It is not triggered by normal users.

Initial symbol universes:

```text
S&P 500
Nasdaq 100
Dow Jones Industrial Average
```

Later symbol universes:

```text
Russell 1000
Russell 2000
S&P MidCap 400
S&P SmallCap 600
S&P 500 sector ETFs / sector lists
Nasdaq Biotechnology Index
Philadelphia Semiconductor Index / SOX
user-requested sector/theme lists
admin-uploaded CSV universe
```

Bootstrap order:

```text
phase 1: S&P 500, Nasdaq 100, Dow Jones Industrial Average
phase 2: Russell 1000
phase 3: Russell 2000
phase 4: S&P MidCap 400 and S&P SmallCap 600
phase 5: sector/theme lists
phase 6: broader US common-stock universe if provider budget and filtering are ready
```

## Required Properties

The bootstrap process must be:

```text
resumable
idempotent
provider-aware
rate-limited
safe to stop and restart
safe to run while users are active
lower priority than visible user work
```

## Suggested Tables

Minimum:

```sql
public.stock_universes(
    universe_name text,
    symbol text,
    source text,
    active boolean,
    added_at timestamptz,
    removed_at timestamptz,
    primary key (universe_name, symbol)
);

public.bootstrap_jobs(
    id uuid primary key,
    symbol text not null,
    job_type text not null,
    priority integer not null,
    status text not null,
    run_after timestamptz not null default now(),
    attempts integer not null default 0,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
```

Recommended later:

```sql
public.stock_snapshot_usage(
    symbol text primary key,
    watchlist_count integer,
    visible_count integer,
    last_visible_at timestamptz,
    last_used_at timestamptz
);

public.ownership_snapshots(
    symbol text not null,
    report_period text not null,
    source text not null,
    institutional_shares numeric,
    estimated_ownership_percent numeric,
    holder_count integer,
    top_holders jsonb,
    source_filed_at timestamptz,
    calculated_at timestamptz not null default now(),
    status text not null,
    error text,
    primary key (symbol, report_period, source)
);
```

## Bootstrap Phases

### Phase 1: Build Symbol Universe

Input:

```text
index membership source
manual admin CSV fallback
```

Current admin script:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python create_index_lists.py --output-dir index_exports --diff-db
python create_index_lists.py --output-dir index_exports --write-db
```

Actions:

```text
normalize symbols
deduplicate symbols across universes
upsert into stock_universes
do not delete stock_snapshots when index membership changes
mark removed index members inactive instead of deleting history
```

### Phase 2: Create Missing Cache Rows

For every active universe symbol:

```text
if stock_snapshots row does not exist, create placeholder row
do not overwrite existing good data
do not overwrite user/manual override data
```

Current full-row bootstrap:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_full_cache.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25 --dry-run
python bootstrap_full_cache.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25
python bootstrap_full_cache.py --universe sp500 nasdaq100 dow30 --missing-only --refetch-after-minutes 15 --limit 25
```

Execution model:

```text
process symbols one at a time
for each symbol, fetch quote/history/fundamentals in parallel
merge once using the production-safe stock_snapshots merge
fetch visible ownership for the same symbol in the same run
refetch-after-minutes can be used to revisit only rows older than the chosen age window
```

### Phase 3: Annual Fundamentals

Preferred source:

```text
yfinance annual financials
```

Actions:

```text
resolve ticker to CIK
fetch annual financials from the primary provider
extract annual revenue and net income/profit
accept only annual filing facts
store the annual values when available
mark fundamentals complete when valid annual values exist
optional fallbacks stay disabled unless explicitly enabled in the worker config
```

Current admin script:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_sec_fundamentals.py --symbols AAPL MSFT NVDA --dry-run --debug-logs
```

Write results to Supabase:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_sec_fundamentals.py --symbols AAPL MSFT NVDA
```

Use a file:

```powershell
python bootstrap_sec_fundamentals.py --file symbols.csv --dry-run
python bootstrap_sec_fundamentals.py --file symbols.csv
```

Use bootstrapped universe membership:

```powershell
python bootstrap_sec_fundamentals.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25 --dry-run
python bootstrap_sec_fundamentals.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25
```

File formats:

```text
plain text: one symbol per line
csv: first column, or a column named symbol
```

Retry policy:

```text
do not repeatedly retry current-year data before annual reports are expected
spread retries over low-traffic windows
```

### Phase 4: History Baselines

Preferred source:

```text
Yahoo Chart initially
future provider fallback possible
```

Actions:

```text
fetch 6 years of daily closes
store history_data
calculate 5Y, 3Y, 1Y, 6M, 3M, 1M baselines
calculate performance values when current price is available
```

Current admin script:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_history.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25 --dry-run --debug-logs
python bootstrap_history.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25
```

Efficiency rule:

```text
one 6-year history call per symbol
derive every percentage column locally
do not fetch separate 5Y/3Y/1Y/6M/3M/1M values
```

Rate:

```text
slow and steady; lower priority than visible user price refresh
```

### Phase 5: Profile And Market Cap

Preferred sources:

```text
Finnhub profile
FMP profile fallback
Yahoo Chart/Spark name fallback where available
```

Actions:

```text
fill company name
fill market cap where provider returns it
never replace a good name with the ticker symbol
never replace a positive market cap with zero
```

### Phase 6: Ownership Coverage

This is important for product value, but it is separate from annual fundamentals.

Purpose:

```text
precompute visible ownership so users see it instantly
avoid calculating ownership during add ticker or list load
```

Input:

```text
Yahoo major holders for the visible ownership field
SEC 13F data for optional diagnostic and research comparison
```

Actions:

```text
fetch the Yahoo major-holders table
extract the institutional ownership percent
store the visible ownership value in the cache
optionally keep SEC 13F data in the research path for comparison
```

Current prototype:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python check_sec_13f_ownership.py AAPL
python check_sec_13f_ownership.py MSFT
```

Prototype behavior:

```text
reads the Yahoo major holders table through yfinance
extracts the institutional ownership percentage used in the visible table
falls back to the SEC research path only for diagnostics and comparison
```

Production gap:

```text
decide whether to keep the SEC research path as an optional comparison tool
add TTL-based refresh for ownership if we want periodic revalidation
```

Current cache bootstrap script:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python bootstrap_ownership.py --symbols AAPL MSFT NVDA --dry-run
python bootstrap_ownership.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25 --dry-run
```

Before writing ownership rows, run:

```text
production_app/docs/ownership_snapshots_schema.sql
```

Write a limited batch:

```powershell
python bootstrap_ownership.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25
```

Recalculate ownership percentages from cached SEC shares after price/market-cap data is available:

```powershell
python bootstrap_ownership.py --recalculate-only --missing-only --limit 25 --dry-run
python bootstrap_ownership.py --recalculate-only --missing-only --limit 25
```

Production rule:

```text
only update stock_snapshots.inst_ownership when the Yahoo major-holders source produces a positive value
do not replace missing/failed ownership with 0.00%
keep the SEC research path separate so it cannot overwrite the visible ownership field
```

UI rule:

```text
show cached ownership instantly
label it as Yahoo major holders in the visible table
if missing, show Ownership pending or Missing, never 0.00% unless confirmed true
```

### Phase 7: Current Price Warmup

Current price goes stale quickly, so this is optional.

Actions:

```text
refresh prices for popular universe symbols shortly before launch
visible user lists still get priority when users are active
```

## Priority Order

When users are active:

```text
1. visible list price refresh
2. user adds new ticker
3. missing data for visible rows
4. recent user watchlists
5. active user hidden watchlists
6. bootstrap universe fundamentals/history
7. ownership refresh and verification
8. unused universe maintenance
```

When no users are active:

```text
1. unfinished visible/recent-user jobs
2. universe annual fundamentals
3. universe history baselines
4. profile/name/market cap cleanup
5. ownership refresh and verification
6. low-priority unused universe refresh
```

## Parallelism

Parallelism is allowed only with provider-specific limits.

Suggested defaults:

```text
SEC annual fundamentals: 3-5 workers, below SEC fair-access limits
Yahoo history: 1 worker
Finnhub/FMP: 1 worker each, budget-aware
13F local parsing: CPU count minus 1 after files are downloaded
Supabase writes: batch 50-200 rows
```

Bad pattern:

```text
many generic threads calling all providers at once
```

Good pattern:

```text
provider-specific queues
provider-specific cooldowns
batched database writes
resumable job state
```

## Success Criteria

Bootstrap is successful when:

```text
popular symbols can be added from cache instantly
annual revenue/profit is mostly prefilled from the configured primary provider
history baselines exist before users request charts/analysis
ownership is cached where the visible ownership source has completed
provider failures are logged without damaging existing good data
the process can stop and resume without duplicate damage
```
