# Current State And Testing

This document describes the current implemented behavior and the manual test checklist.

Use this to avoid confusing implemented behavior with roadmap ideas.

## Current Implemented Behavior

### App Start / Login

Expected behavior:

```text
1. User signs in or existing session is restored.
2. App loads the last active watchlist from browser storage when available.
3. App loads watchlist rows from Supabase.
4. App loads stock_snapshots from Supabase.
5. Table renders from cached DB data.
6. App starts a price-only refresh for stale visible symbols.
```

Important:

```text
App start must not trigger history refresh.
App start must not trigger fundamentals refresh.
App start must not refresh hidden watchlists.
```

### Visible Price Refresh

Expected behavior:

```text
visible list only
quote layer only
max 30 symbols
stale price only
default TTL = 15 minutes
```

The app runs visible price refresh:

```text
on first visible-list load when price is stale
every 15 minutes while the list is visible
when the user clicks Refresh
```

If bulk-style quote paths fail and individual fallback quote calls are needed, scheduled refresh mode spreads fallback calls.

### Add Existing Ticker

If the symbol already exists in `stock_snapshots`:

```text
1. Add only the watchlist row.
2. Show cached DB data immediately.
3. Refresh price only if stale.
4. Do not refresh history.
5. Do not refresh fundamentals.
6. Do not refresh the rest of the watchlist.
```

### Add New Ticker

If the symbol does not exist in `stock_snapshots`:

```text
1. Add a pending visible row.
2. Fetch quote/profile for only that symbol.
3. Fetch history baselines for only that symbol.
4. Attempt fundamentals for only that symbol.
5. Write successful layers into stock_snapshots.
6. Keep missing fundamentals marked as Missing or Updating.
7. Do not refresh the rest of the watchlist.
```

### Edit Comment

Expected behavior:

```text
update watchlists.comment only
no market-data API call
no stock_snapshots update
```

### Delete Ticker

Expected behavior:

```text
delete only the watchlist row
do not delete stock_snapshots
do not affect other watchlists
do not affect other users
```

### Duplicate Tickers Across Lists

Expected behavior:

```text
same user may have the same ticker in different watchlists
same ticker may not appear twice inside the same watchlist
```

## Provider Behavior Currently Wired

### Price / Quote

Current intended order:

```text
Yahoo Spark / Yahoo quote batch where available
Finnhub per-symbol fallback
Yahoo Chart fallback
```

### History

Current intended order:

```text
Yahoo Chart
yfinance history fallback
```

### Fundamentals

Current intended order for new ticker fundamentals:

```text
Finnhub stock/financials-reported
FMP stable/profile fallback
FMP stable/income-statement fallback
```

Fundamentals should not be called on normal list load.

Annual revenue/profit display:

```text
uses completed prior calendar years only until fiscal-year reporting logic is smarter
in 2026, annual columns should not show 2026 as Latest Revenue/Profit
current-year provider values are treated as incomplete/unsafe for annual growth logic
Growth status is calculated from four annual values when the provider returns enough history
current schema still displays three annual values until the extended annual columns migration is implemented
```

## Manual Test Checklist

### Test 1: Login / Initial Load

Steps:

```text
1. Start worker.
2. Start frontend.
3. Sign in.
4. Observe which watchlist loads.
5. Watch table render from cached data.
```

Expected:

```text
last active list loads if available
table renders quickly from Supabase
only stale visible prices refresh
no history/fundamentals provider calls
```

SQL check:

```sql
select
    job_id,
    sequence_number,
    symbol,
    layer,
    source,
    started_at,
    status_code,
    ok,
    duration_ms,
    error
from public.market_request_logs
order by started_at desc, sequence_number desc
limit 50;
```

Passing result:

```text
only quote layer calls should appear from list load
```

### Test 2: Manual Refresh Button

Steps:

```text
1. Open a watchlist.
2. Click Refresh.
3. Watch table update.
```

Expected:

```text
quote layer only
visible symbols only
no history calls
no fundamentals calls
```

### Test 3: Add Existing Ticker From Master Cache

Steps:

```text
1. Pick a ticker already in stock_snapshots but not in the current watchlist.
2. Add it.
```

Expected:

```text
row appears immediately
cached fields display from DB
price refresh only if stale
no history/fundamentals call
```

### Test 4: Add Brand-New Ticker

Steps:

```text
1. Pick a ticker not in stock_snapshots.
2. Add it.
```

Expected:

```text
pending row appears quickly
only that ticker gets quote/history/fundamentals attempts
rest of watchlist is untouched
quote/history appear before fundamentals if fundamentals is slower or missing
```

### Test 5: Edit Comment

Steps:

```text
1. Edit a ticker comment.
2. Save it.
```

Expected:

```text
comment changes
no refresh job
no market_request_logs rows
```

### Test 6: Delete Ticker

Steps:

```text
1. Delete a ticker from one watchlist.
2. Check stock_snapshots.
```

Expected:

```text
watchlist row is deleted
stock_snapshots row remains
same ticker remains in other watchlists
```

### Test 7: Price Refresh TTL

Steps:

```text
1. Open a watchlist with fresh prices.
2. Reload the app.
```

Expected:

```text
fresh prices should not trigger immediate price API calls
stale prices older than 15 minutes may trigger quote-only refresh
```

## Known Limitations

These are known and should not be mistaken for bugs during testing.

### No Durable Scheduler Yet

The app has stricter frontend/worker triggers, but the full durable scheduler is not implemented yet.

Missing future pieces:

```text
refresh_queue table
provider cooldown table
run_after scheduling
jittered slow-layer jobs
background hidden-list refresh
```

### Manual Overrides Not Implemented Yet

Manual cell overrides are documented as feature requests but not implemented.

See:

```text
FR-001
FR-002
FR-003
```

### Row Styling Not Implemented Yet

Row background color, font color, bold toggle, and clear formatting are documented as feature requests but not implemented.

See:

```text
FR-004
FR-005
FR-006
FR-007
```

### Reset Password Not Implemented Yet

Password reset is documented as a feature request but not implemented.

See:

```text
FR-022
```

### Worker Console Log Levels Not Implemented Yet

`WORKER_MARKET_LOG_LEVEL` is a planned feature request, not a current env var.

Current implemented debug switch:

```text
WORKER_DEBUG_MARKET_REQUESTS
```

### API Usage Dashboard Not Implemented Yet

API usage budget dashboard is documented as a feature request but not implemented.

See:

```text
FR-018
```

### Yfinance Primary Review Not Done Yet

The old prototype's yfinance behavior still needs a detailed comparison.

See:

```text
FR-019
FR-020
```

### Fundamentals Coverage Is Partial

Current free provider coverage is not perfect.

Known behavior:

```text
FMP stable income works for some symbols and blocks others
Finnhub reported financials fills some gaps
foreign ADRs may have reported-currency complications
institutional ownership is not cleanly solved yet
```

### Reported Currency Not Implemented Yet

Reported currency display is documented as a feature request but not implemented.

See:

```text
FR-015
```

## Test Run Notes Template

Use this format when recording manual test results:

```text
Date/time:
Worker command:
Frontend command:
Debug enabled:
Watchlist:
Action:
Expected:
Actual:
Job id:
Unexpected provider calls:
UI issue:
SQL evidence:
Decision:
```
