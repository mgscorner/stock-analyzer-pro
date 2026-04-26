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
Russell 2000
user-requested sector lists
admin-uploaded CSV universe
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

### Phase 3: Annual Fundamentals

Preferred source:

```text
SEC EDGAR companyfacts
```

Actions:

```text
resolve ticker to CIK
fetch companyfacts
extract annual revenue and net income/profit
accept only annual filing facts
store five annual values when available
mark fundamentals complete when valid annual values exist
fallback to Finnhub/FMP only when SEC cannot cover the symbol
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

### Phase 6: SEC 13F Ownership

This is important for product value, but it is heavier than annual fundamentals.

Purpose:

```text
precompute institutional ownership so users see it instantly
avoid calculating ownership during add ticker or list load
```

Input:

```text
latest available 13F-HR quarter
all relevant institutional manager filings
symbol-to-CUSIP mapping
shares outstanding from a separate provider/cache source
```

Actions:

```text
download/parse 13F holdings in background
filter holdings by CUSIP/ticker mapping
sum institutional shares and reported value by symbol
calculate estimated ownership percent when shares outstanding is available
store holder count and top holders
store report period and source filing dates
```

UI rule:

```text
show cached ownership instantly
label it as SEC 13F and show report period
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
7. SEC 13F ownership background aggregation
8. unused universe maintenance
```

When no users are active:

```text
1. unfinished visible/recent-user jobs
2. universe annual fundamentals
3. universe history baselines
4. profile/name/market cap cleanup
5. SEC 13F ownership pipeline
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
annual revenue/profit is mostly prefilled from SEC
history baselines exist before users request charts/analysis
ownership is cached where the SEC 13F pipeline has completed
provider failures are logged without damaging existing good data
the process can stop and resume without duplicate damage
```
