# Market Data Provider Strategy

This document records the selected provider direction for the production app.

The app should not use one global provider switch. Provider routing must be category-aware. Each data group can have its own preferred provider and fallback chain.

## First Implementation Wave

Use these first:

```text
SEC EDGAR
Finnhub
FMP
Yahoo Chart
Yahoo Spark
```

### SEC EDGAR

Primary source for:

```text
annual revenue
annual profit / net income
annual fiscal-year history from companyfacts
```

Why:

```text
official public filing source
free and does not require an API key
reduces load on Yahoo/Finnhub/FMP for historical financial statements
fits the app cache model because annual financials change rarely
```

Risk:

```text
requires ticker-to-CIK mapping
some companies use different XBRL revenue tags
coverage is strongest for SEC filers
not a live price source
companyfacts is not an institutional ownership percentage source
```

Decision:

```text
Use SEC companyfacts first for annual revenue/profit.
Use only annual filing facts and avoid quarterly data in yearly columns.
Keep Finnhub/FMP/yfinance as fallbacks, not as the default for annual revenue/profit.
```

### SEC 13F

Planned source for:

```text
institutional ownership percentage
top institutional holders
holder count
quarter-over-quarter ownership changes
```

Why:

```text
official source for institutional manager holdings
free
same delayed source commercial APIs depend on
better fit for background precomputation than per-click APIs
```

Risk:

```text
13F data is delayed by design
filings are quarterly and can arrive up to 45 days after quarter end
aggregation requires scanning many manager filings
filings identify securities primarily by CUSIP
estimated ownership percent also needs shares outstanding
```

Decision:

```text
Do not calculate 13F ownership during user interactions.
Build a background SEC 13F ownership pipeline.
Cache ownership in Supabase before users need it.
Show report period and source in the UI.
Show Missing/Ownership pending instead of fake zero when not cached.
```

### Finnhub

Primary candidate for:

```text
quote
company profile
market cap
fundamentals fallback where stock/financials-reported maps cleanly
news/sentiment later
analyst data later
possible ownership later
```

Why:

```text
good testing/free-tier candidate
straightforward API
better production candidate than scraper-based yfinance
user already has an API key
```

Risk:

```text
fundamentals may not map cleanly to our revenue/profit fields
some richer datasets may require paid access
rate limits still need to be respected
```

Decision:

```text
Use Finnhub first for quote/profile when FINNHUB_API_KEY is present.
Use Finnhub stock/financials-reported as annual fundamentals fallback when SEC does not cover a symbol.
```

### FMP

Fallback candidate for:

```text
fundamentals
annual revenue
annual profit
company profile
market cap
future screener
possible institutional ownership
```

Why:

```text
best fit for the app's revenue/profit growth logic
has financial statements, profiles, quote endpoints, and screeners
free tier is useful for development/testing
```

Risk:

```text
free tier is limited
commercial/display terms must be checked before real production users
some endpoints may be paid-only
```

Decision:

```text
Use FMP stable income-statement as fundamentals fallback when FMP_API_KEY is present.
Do not use old /api/v3 income-statement endpoints for the current account; they return legacy/plan errors.
```

### Yahoo Chart

Primary candidate for:

```text
history fallback
price fallback
3M/6M/1Y/3Y/5Y baselines
```

Why:

```text
currently works even while yfinance quoteSummary is rate-limited
no API key required
already integrated
```

Risk:

```text
unofficial endpoint
can change or block requests
does not provide reliable fundamentals
```

Decision:

```text
Keep Yahoo Chart as fallback, especially for history.
```

### Yahoo Spark

Candidate for:

```text
experimental quote fallback
sparkline/short history fallback
```

Why:

```text
worked in testing when Yahoo quote API returned 401
can return multiple symbols in one request
```

Risk:

```text
unofficial endpoint
not a primary production dependency
```

Decision:

```text
Add as fallback only, behind the internal quote provider flow.
```

## Promising Second Wave

These are not first-wave implementation targets, but keep them in mind.

### Twelve Data

Good for:

```text
batch quotes
historical prices
ticker lookup
technical indicators
```

Why promising:

```text
free tier around 800 daily API credits
batch-capable
good fallback candidate for quote/history
```

Concern:

```text
fundamentals are not the main reason to use it
credit weights can make some endpoints expensive
```

Possible use:

```text
quote/history fallback
initial database fill for selected lists if credits allow
```

### Tiingo

Good for:

```text
clean historical EOD prices
adjusted prices
news
```

Why promising:

```text
known for clean historical datasets
could be useful for initial database fill or history fallback
```

Concern:

```text
current free-tier limits need direct account verification before coding
not the first choice for revenue/profit fundamentals
```

Possible use:

```text
history fallback
initial baseline fill
```

### iTick

Good for:

```text
batch quotes
global quote data
WebSocket later
```

Why promising:

```text
has documented batch quote endpoint
supports US stocks and global markets
```

Concern:

```text
free plan appears limited to 5 REST calls/minute
personal-use wording must be reviewed
needs data-quality testing
```

Possible use:

```text
quote fallback
batch quote fallback
future live-data experiment
```

## Provider Order By Data Group

Initial target order:

```text
quote:
    Finnhub
    FMP quote/profile
    Yahoo Spark
    Yahoo Chart
    Yahoo quote API

history:
    Yahoo Chart
    Twelve Data later
    Tiingo later

fundamentals:
    Finnhub stock/financials-reported
    FMP stable/income-statement
    Alpha Vantage emergency fallback later
    EODHD paid later

market cap/name/profile:
    Finnhub
    FMP
    Yahoo metadata fallback

ownership:
    FMP if field is available
    Finnhub if field is available
    otherwise N/A

screener:
    FMP later
    Mboum later
    EODHD paid later
```

## Implementation Rule

Each provider call must return normalized internal fields. UI and database code should not know which provider supplied the value.

Internal function shape:

```text
get_quote(symbols)
get_history(symbol)
get_fundamentals(symbol)
get_ownership(symbol)
run_screener(screen_id)
```

Failures must be scoped to the data group that failed. Never overwrite existing good data with missing values from a failed provider.
