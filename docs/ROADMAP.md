# Production Roadmap

This roadmap tracks production features and design ideas that should not be lost.

## Current Focus

Production app only:

```text
production_app/
```

Architecture:

```text
React frontend
Supabase database/auth/cache
Python FastAPI worker
Oracle deployment target
```

## Near-Term Must Fix

### Category-Aware Provider Routing

Do not build provider selection as one global configuration switch. The worker needs provider routing per data group or column group.

Examples:

```text
quote provider order
history provider order
fundamentals provider order
ownership provider order
news/sentiment provider order
analyst target provider order
screener provider order
```

On a new ticker, the worker should be allowed to use different providers for different groups:

```text
price from provider A
history from provider B
fundamentals from provider C
institutional ownership from provider D
```

Each group needs its own:

```text
default provider
fallback order
rate-limit state
cooldown/retry_after
field coverage map
merge rules that preserve existing good data
```

This should become an internal worker API later:

```text
get_quote(symbols)
get_history(symbol)
get_fundamentals(symbol)
get_ownership(symbol)
run_screener(screen_id)
```

### Layer-Aware Refresh Jobs

Current refresh behavior is still too generic. Implement explicit job types:

```text
add_symbol_initial
visible_quote_refresh
visible_history_refresh
visible_fundamentals_refresh
background_quote_refresh
background_history_refresh
background_fundamentals_refresh
```

### Batch Visible Price Refresh

When a list becomes visible, batch quote refresh all stale visible symbols, up to the watchlist limit of 30.

This is the most important UX path:

```text
cached table appears immediately
visible prices update quickly
performance and Green Charts recalculate from cached baselines
```

### Preserve Good Data

Refreshes must merge good layer data into existing rows. They must never overwrite existing valid data with missing, null, zero, placeholder, or failed data.

## Refresh Scheduler

Add scheduler/queue logic that:

```text
uses TTLs only as eligibility
spreads jobs out with jitter
respects run_after
prioritizes visible lists
avoids burst refreshes
stops fundamentals requests during Yahoo cooldown
uses Oracle always-on runtime to maintain cache while users are offline
spends provider/API budget on the highest-value stale or missing data first
```

Visible list jobs should beat background jobs.

Offline/background priority order:

```text
currently visible watchlists
recently visible watchlists
watchlists from daily/power users
watchlists from weekly users
other user watchlists
index-universe tickers not yet used by users
master-list tickers not currently used by any watchlist
```

The scheduler should inspect:

```text
price_updated_at
history_updated_at
fundamentals_updated_at
quote_status
history_status
fundamentals_status
missing annual revenue/profit years
known reporting dates and not-expected-until dates
provider cooldowns
daily/monthly provider budgets
```

Oracle production behavior:

```text
when users are active, visible-user work wins
when no users are active, run a relaxed maintenance cycle
at night or low-traffic windows, fill missing slow data
do not burn API calls on unused tickers while active users need fresh visible-list data
```

## Analysis Change Detection

Feature idea: show users what changed since they last viewed a watchlist.

Examples:

```text
V: 3M turned negative
UNH: Green Charts changed Yes -> No
JPM: Institutional ownership moved above 50%
MSFT: Revenue changed Nope -> Growth
```

Suggested table:

```sql
create table public.watchlist_symbol_views (
    user_id uuid not null,
    watchlist_name text not null,
    symbol text not null,
    analysis_signature text,
    analysis_summary jsonb,
    last_seen_at timestamptz default now(),
    primary key (user_id, watchlist_name, symbol)
);
```

Suggested signature components:

```text
green_charts
revenue_status
profit_status
ownership_bucket
perf_3m_bucket
overall_color_state
```

UI placement:

```text
notice above the table
collapsible details later
```

Example copy:

```text
Analysis changes since last view: V 3M turned negative, UNH Green Charts turned No.
```

## Numbered Feature Requests

This section captures product ideas that should not be lost. Items can move into implementation plans later.

### FR-001 Manual Cell Overrides For Missing Data

Allow users to manually enter values for cells that providers cannot fill reliably.

Target fields:

```text
Inst. Own.
Latest Revenue
Previous Revenue
Prior Revenue
Latest Profit
Previous Profit
Prior Profit
Revenue
Profit
possibly Market Cap and Name later
```

Rules:

```text
provider/cache data stays in stock_snapshots
manual user data lives in a separate user-specific override table
refresh never overwrites manual input
manual values can be cleared by the user
manual values can be used for derived Revenue/Profit status
```

### FR-002 Manual Data Source Badges

Every manually entered or overridden cell must be visibly marked so users know it was not fetched.

Possible labels:

```text
Manual
User
Provider
Missing
Updating
Fetched available but Manual active
```

Example display:

```text
$416,161,000 [Manual]
```

### FR-003 Manual Override Review When Provider Data Appears

If a user has a manual value and a provider later returns a value for the same field, do not silently replace the manual value.

Behavior:

```text
keep manual value visible
store/update provider value in cache
show that provider data is now available
let user choose Keep Manual or Use Provider
```

### FR-004 Row Background Highlight Colors

Allow users to highlight individual ticker rows with a custom background color.

Scope:

```text
per user
per watchlist
per ticker row
```

This should live with watchlist row preferences, not in the shared stock_snapshots cache.

### FR-005 Row Font Color

Allow users to set custom font color for individual ticker rows.

Scope:

```text
per user
per watchlist
per ticker row
```

### FR-006 Row Bold Toggle

Allow users to mark an individual ticker row as bold or not bold.

Scope:

```text
per user
per watchlist
per ticker row
```

### FR-007 Clear Row Formatting

Add a simple way to remove custom row formatting.

Behavior:

```text
clear background color
clear font color
clear bold flag
return row to default table style
```

### FR-008 Last Active Watchlist Preference

Remember the last active watchlist for each user and load it first after login.

Purpose:

```text
user lands on the list they used last
cached DB data renders immediately
price-only refresh can begin early during login/session restore
```

Current temporary implementation may use browser storage. Production version should consider a user_preferences table.

### FR-009 Login-Time Price Refresh Head Start

After a valid session is known and the last active list is identified, start a price-only refresh for stale visible tickers as early as possible.

Rules:

```text
price only
visible/last-active list only
max 30 tickers
respect 15-minute TTL unless explicitly configured otherwise
no history
no fundamentals
no hidden watchlists
```

### FR-010 Strict API Call Budget Enforcement

Enforce the rule that the app reads from the master cache by default and only calls market-data APIs for approved reasons.

Allowed market calls:

```text
new ticker not in stock_snapshots
stale visible-list price refresh on load
stale visible-list price refresh every configured interval
scheduled slow-layer jobs that are explicitly due
```

Everything else reads Supabase only.

### FR-011 Visible Price Refresh Spreading

If a true bulk price call is unavailable, spread individual visible-list price calls over a configured window.

Example:

```text
30 visible tickers
120 second spread window
about 4 seconds between individual quote calls
```

The first visible-list price refresh after app load may be faster, but still quote-only.

### FR-012 Provider Cooldown Table

Track provider failures and rate limits by provider and data group so the app does not keep retrying blocked endpoints.

Suggested fields:

```text
provider
data_group
symbol optional
status
last_error
cooldown_until
attempt_count
updated_at
```

### FR-013 Layer Staleness Scheduler

Build a real scheduler/policy layer that decides what is due instead of letting UI actions directly trigger broad refreshes.

Responsibilities:

```text
check quote/history/fundamentals/ownership timestamps
respect TTLs and retry_after
spread jobs with jitter
prioritize visible price refresh
prevent bursts
avoid hidden list refreshes unless background capacity exists
```

### FR-014 Earnings-Aware Fundamentals Refresh

Do not repeatedly try to fetch current-year revenue/profit if the fiscal year is not complete or data is not expected yet.

Behavior:

```text
mark current-year data as not expected yet
store next expected check date
optionally store next earnings/reporting date
retry only near or after that date
```

### FR-015 Reported Currency Display

Store and display reported currency for fundamentals.

Reason:

```text
some providers return statements as reported
foreign ADRs such as TSM may not be USD
growth logic can still work, but display should not falsely label values as USD
```

### FR-016 Provider Source And Freshness Details

Expose provider/source information in the UI for debugging and user trust.

Examples:

```text
Price: Finnhub, updated 2 minutes ago
Revenue: FMP, updated yesterday
Profit: Manual
History: Yahoo Chart, updated 2026-04-16
```

This can start as a detail panel or tooltip instead of a full table column.

### FR-017 Worker Console Market Log Levels

Add a console logging switch for provider calls.

Suggested setting:

```text
WORKER_MARKET_LOG_LEVEL=quiet
WORKER_MARKET_LOG_LEVEL=summary
WORKER_MARKET_LOG_LEVEL=debug
```

Expected output:

```text
market quote TSM finnhub_quote 200 ok 120ms
market fundamentals IBM fmp_stable_income 402 failed 161ms
market fundamentals IBM finnhub_reported 200 ok 149ms
```

Never print API keys, authorization headers, or full signed URLs.

### FR-018 API Usage Budget Dashboard

Track and display API usage so testing does not burn provider limits unexpectedly.

Useful counters:

```text
FMP calls today
Finnhub calls today
Yahoo/yfinance calls today
calls by data group
calls by user action
blocked/cooling-down providers
```

### FR-019 Yfinance Behavior Review Against Old Prototype

Compare the old working yfinance behavior with the production worker behavior.

Goal:

```text
identify why the prototype avoided rate limits for several days
copy stable call order and pacing where appropriate
avoid duplicate quoteSummary/info calls
use yfinance primarily where it is safe and valuable
fallback to Finnhub/FMP/Yahoo Chart when yfinance fails or cools down
```

### FR-020 Yfinance Primary With Controlled Fallbacks

Preferred future provider behavior if yfinance becomes stable again:

```text
yfinance primary for rich ticker data where safe
Finnhub/FMP/Yahoo Chart fallback when yfinance fails
cooldown yfinance after 429 or quoteSummary errors
do not retry yfinance repeatedly during cooldown
```

### FR-021 Manual Refresh Buttons By Layer

Add explicit advanced refresh actions instead of one broad refresh.

Possible buttons:

```text
Refresh Prices
Refresh Chart Data
Refresh Fundamentals
Full Refresh
```

Each button must state what it will call and respect provider cooldowns.

### FR-022 Reset Password Flow

Add a proper password reset feature to the login screen.

Behavior:

```text
user enters email
Supabase sends password reset email
app handles reset redirect
user sets new password
```

### FR-023 Earnings And Reporting Date Awareness

Track when the next earnings/reporting data is expected so missing fundamentals are understandable.

Purpose:

```text
show whether data is missing because a provider failed
show whether data is not expected yet because the company has not reported
avoid repeatedly fetching fundamentals before new filings are likely available
```

Suggested fields:

```text
next_earnings_date
next_report_expected_at
latest_fiscal_period
latest_fiscal_year
fundamentals_not_expected_until
fundamentals_missing_reason
```

Example UI:

```text
FY2027 annual data not expected until after Jan 31, 2027.
Next quarterly earnings expected late May 2026.
```

Possible data sources:

```text
Finnhub earnings calendar
FMP earnings calendar
company investor relations page
provider-reported fiscal period fields
```

Refresh behavior:

```text
if data is not expected yet, do not retry fundamentals on every refresh
set next check date near the expected reporting date
mark cell as Not reported yet instead of generic Missing
```

This is required before real external users.

### FR-024 Fiscal-Year Completeness And Growth Basis

Annual revenue/profit columns must make the fiscal years explicit and must base growth logic on the latest complete/reportable fiscal years.

Problem:

```text
early in a new calendar year, the newest fiscal year may not be published yet
different providers may return different latest fiscal years
Latest/Previous/Prior labels are confusing without visible year numbers
growth calculations should not fail just because an unpublished year is missing
```

Required behavior:

```text
show the fiscal year beside each annual revenue/profit value
store which fiscal years were used for revenue_status and profit_status
use only annual/FY reports, never quarterly/interim reports
if FY2025 is not reported yet, mark FY2025 as Not published yet and calculate from the next complete annual years
revenue Growth is true only when four annual revenue values form three increases, e.g. 2024 > 2023 > 2022 > 2021
profit Growth is true only when four annual profit values form three increases, e.g. 2024 > 2023 > 2022 > 2021
mark newer missing years as Not reported yet when expected reporting date is known
do not retry unavailable annual data until the configured next check date
```

Suggested future fields:

```text
revenue_growth_basis_years
profit_growth_basis_years
latest_complete_fiscal_year
next_annual_report_expected_at
fundamentals_missing_reason
```

This is linked to FR-023 but separate because the UI/calculation basis must be clear even before earnings-date automation is complete.

### FR-025 Extended Annual Revenue/Profit History

The dashboard needs at least four annual revenue/profit values for Growth logic, and ideally five values for user orientation.

Reason:

```text
Growth logic needs four annual values to test three year-over-year increases
users may want to compare the last 5 completed annual values
at the beginning of a year, a not-yet-valid current year can create confusion
growth logic should be transparent enough that users can see which years were compared
```

Possible behavior:

```text
store and display at least 4 completed annual revenue values
store and display at least 4 completed annual profit values
prefer 5 completed annual revenue/profit values when providers return enough history
optionally keep a diagnostic value when a current-year provider value exists but is not accepted as annual
show rejected current-year values as diagnostic/provider detail, not as Latest Revenue/Profit
```

### FR-026 User-Controlled Column Visibility

Allow users to hide/show table columns.

Reason:

```text
adding more annual history columns increases table width
different users care about different fields
mobile and laptop layouts need a simpler view
```

Possible behavior:

```text
per-user column visibility preferences
quick presets such as Compact, Analysis, Fundamentals, Full
default visible columns stay close to the current table
advanced yearly columns can be hidden by default
```

Current implementation note:

```text
first version uses browser localStorage per user
future version should move preferences into Supabase user_preferences
```

### FR-027 Weekly Performance Column

Add a weekly percent-change column.

Reason:

```text
it is cheap to calculate from cached history once history is available
some users want short-term context in addition to 5Y/3Y/1Y/6M/3M
users can hide the column if it is not useful
```

Suggested display:

```text
%-change 1 week
```

Implementation notes:

```text
add close_1w baseline to stock_snapshots
calculate perf_1w from current price and close_1w
do not make an extra provider call when 6y history is already cached
include the column in user-controlled visibility preferences
```

### FR-028 Table Settings Panel

Move table configuration out of the always-visible sidebar.

Reason:

```text
column visibility controls consume too much valuable sidebar space
future table settings will include column visibility, column order, density, presets, and possibly color/theme options
```

Possible UI:

```text
Settings button above the table
drawer panel from the right side
modal dialog if drawer is too much
collapsible sidebar section as a fallback
```

Design rule:

```text
keep the table visible and usable
avoid permanent controls that crowd watchlist management
store settings per user eventually, not only in browser localStorage
```

Settings groups to support:

```text
hide/show columns
reorder columns
table density
header row style
row style defaults
light/dark/system theme
reset table layout
```

### FR-029 User-Configurable Column Order

Allow users to reorder table columns.

Reason:

```text
users may prioritize price/performance, fundamentals, notes, or status differently
expanded annual columns make fixed ordering less practical
```

Possible behavior:

```text
drag-and-drop ordering in the table settings panel
simple move up/down buttons as a first accessible version
reset to default order
store order in user preferences
```

### FR-030 Dark Mode

Add a dark mode/theme preference.

Reason:

```text
the app may be used for long sessions
some users prefer lower brightness
```

Possible behavior:

```text
Light
Dark
System
```

Implementation note:

```text
theme should be driven by CSS variables so table colors, status colors, forms, and future dialogs remain consistent
```

### FR-031 Rename Watchlists

Allow users to rename an existing watchlist.

Behavior:

```text
rename all rows for the selected user and watchlist_name
prevent collision with another list name for the same user
preserve tickers, comments, row preferences, and last-active-list preference
```

### FR-032 Export Watchlists

Allow users to export watchlists.

Possible formats:

```text
CSV
Excel-compatible CSV
JSON backup
plain ticker list
```

Export should include:

```text
watchlist name
ticker
comment
visible cached values if user chooses table export
manual overrides and row styling later
```

### FR-033 Resizable And Hideable Sidebar

Allow users to resize or hide the sidebar.

Reason:

```text
the table is the primary workspace
column controls and management controls compete for horizontal space
some users will want maximum table width
```

Possible behavior:

```text
drag divider to resize sidebar
collapse sidebar completely
restore sidebar button
persist sidebar width/collapsed state per user
mobile layout uses collapsible drawer
```

### FR-034 Watchlist Chart Panel

Restore the chart below the watchlist that existed in the Streamlit prototype.

Purpose:

```text
show selected ticker chart below the table
reuse cached history_data from stock_snapshots
do not make a market-data call just to render the chart
support selected row/ticker from the table
```

Possible first version:

```text
click a row to select ticker
render cached close history below the table
show message if chart history is missing
```

Advanced version:

```text
zoomable/pannable chart
interval selector
range selector
crosshair/hover values
smooth interactions
reuse cached history_data first
fetch history only when the selected interval/range is missing or stale
```

Implementation options:

```text
lightweight-charts
Plotly
ECharts
custom SVG only for simple fallback
```

### FR-035 Yahooquery Batch Quote Provider Evaluation

Evaluate `yahooquery.Ticker(...).price` as an optional implementation for bulk quote refresh.

Context:

```text
current worker already tries Yahoo Spark first for visible-list batch quote refresh
yahooquery may provide a cleaner wrapper around Yahoo batching
adding it means adding and testing another dependency
```

Decision rule:

```text
keep current direct Yahoo Spark implementation until it fails or yahooquery proves better in local tests
do not add the dependency casually during rate-limit sensitive work
if adopted, keep it behind the quote provider abstraction/fallback chain
```

### FR-036 Ticker Identity Feedback Before Add

Show company identity before adding a ticker, without a blocking confirmation dialog.

Reason:

```text
valid tickers can still be the wrong company
MC is not Mastercard; MA is Mastercard
JMP is not JPMorgan; JPM is JPMorgan Chase
the name column helps catch this, but pre-add feedback prevents bad rows earlier
```

Behavior:

```text
user enters ticker
app fetches/loads company name
status field shows Checking MA...
status field shows Found Mastercard Incorporated. Adding MA...
row is added automatically when valid
invalid ticker shows a red error and is not inserted
if possible, suggest common alternatives for likely typos
```

No modal/confirmation dialog in the normal flow.

### FR-037 Master Universe Prefill

Prefill the master cache from common index universes before launch and during low-traffic windows.

Candidate universes:

```text
S&P 500
Nasdaq 100
Dow Jones Industrial Average
Russell 2000 later, depending on provider budgets
```

Purpose:

```text
many users will add popular large-cap tickers
preloaded cache makes first user interaction faster
annual revenue/profit/history can be fetched before launch day
background maintenance can improve unused rows gradually when API budget is available
```

Rules:

```text
deduplicate symbols across universes
track which universe each ticker belongs to
track whether a ticker is used in any user watchlist
track whether a ticker is currently/recently visible
unused universe tickers have lower priority than user watchlist tickers
```

Index membership maintenance:

```text
refresh index membership on a schedule, for example weekly
detect added/removed symbols
add new index members to the universe table
do not delete stock_snapshots automatically when a symbol leaves an index
```

Suggested tables:

```sql
public.stock_universes(universe_name, symbol, created_at)
public.stock_snapshot_usage(symbol, watchlist_count, visible_count, last_visible_at, last_used_at)
```

Implementation can start with `stock_universes`, which already exists in the schema, and add usage rollups later.

### FR-038 Background Cache Maintenance Decision Table

Create an explicit scheduler decision table for always-on cache maintenance.

Example categories:

```text
visible_price_due
recent_visible_price_due
watchlist_history_missing
watchlist_history_stale
watchlist_fundamentals_missing
watchlist_fundamentals_stale
index_universe_initial_fill
unused_master_low_priority_refresh
```

Example update rules:

```text
price: visible list at 15 minute window; background lists slower
history baselines: about once per day, spread with jitter
fundamentals: only when missing, stale, or report date suggests new annual data may exist
annual revenue/profit: do not retry if current annual report is known not published yet
index membership: weekly or manual admin trigger
```

Priority inputs:

```text
currently visible
recently visible
user activity frequency
watchlist count per ticker
missing critical fields
provider cooldown state
remaining API budget
time of day / low-traffic window
```

This is the production replacement for simple polling.

## Future Screener Features

Some providers offer a screener endpoint that can return many matching symbols in one call. Keep this as a later product feature, not part of the immediate refresh fix.

Possible feature:

```text
Daily Morning Screen
```

Behavior idea:

```text
1. Once per day before or near market open, run configured screeners.
2. Store screener results in Supabase.
3. Show users a cached daily hit list.
4. Let users add interesting hits to watchlists.
5. Do not rerun the screener repeatedly per user session.
```

Potential screen types:

```text
green charts candidates
revenue/profit growth candidates
recent 3M trend changes
institutional ownership threshold
large cap watch candidates
custom user-defined screens later
```

This fits the production direction because one scheduled call can serve many users from cache.

## Deployment

Target:

```text
React frontend hosted as static site
Oracle VM runs Python worker container
Supabase remains database/auth/cache
```

Worker deployment requirements:

```text
Docker
server-side env vars
service-role key never in frontend
HTTPS before real users
CORS locked to frontend URL
restart policy/systemd or Docker restart unless-stopped
structured logs without secrets
```

## Business Layer

Later:

```text
subscriptions table
manual beta approval
inactive account screen
PayPal payment link
PayPal webhook automation
plan-based limits
```

## Not Product Behavior

These actions must not trigger market refreshes:

```text
editing a comment
deleting a ticker from a watchlist
switching lists when cached data is still acceptable
loading hidden watchlists
```

Deleting a ticker from one watchlist must not delete it from `stock_snapshots`, because other watchlists/users may still depend on it.
