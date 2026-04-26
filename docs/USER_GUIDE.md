# User Guide

This guide describes intended user-facing behavior for the production app.

## Login

After signing in, the app loads the last active watchlist when available.

The table should appear from cached data first. Prices may update shortly after the table appears.

## Reset Password

Use `Forgot Password` on the login screen to request a reset email.

After opening the reset link, enter and confirm the new password.

## Watchlists

Users can:

```text
create watchlists
switch watchlists
delete watchlists
add tickers
delete tickers
save comments
```

Switching lists should load cached data from the database. It should not refresh history or fundamentals.

## Add Ticker

When adding a ticker:

```text
if the ticker already exists in the shared cache, the app uses cached data
if the ticker is new, the app creates a pending row and fetches data for that ticker only
```

Adding one ticker must not refresh the whole watchlist.

## Refresh

The normal Refresh button refreshes prices only for the visible list.

It should not refresh:

```text
fundamentals
history
hidden watchlists
all users' data
```

## Data Status

Possible status values include:

```text
OK
Updating
Missing Fundamentals
Partial
Needs Cache
Update Failed
```

Meanings:

```text
OK
    quote, history, and fundamentals are available enough for the row

Updating
    row has useful data, but one or more slower fields are still pending

Missing Fundamentals
    price/history may exist, but revenue/profit/ownership data is missing or unavailable

Partial
    some data exists, but the row is not fully complete

Needs Cache
    no usable cached data exists yet

Update Failed
    last refresh attempt failed, but old good data should be preserved when available
```

## Missing Or Updating Fundamentals

Revenue, profit, and ownership data can be harder to fetch than price.

If a provider cannot return those values, the app should show:

```text
Updating...
Missing
Missing Fundamentals
Ownership pending
```

`Ownership pending` means the app does not have a confirmed institutional ownership value yet. It should not be interpreted as `0%`.

Price and historical performance should still work when fundamentals are missing.

## Comments

Comments are user/watchlist data.

Saving a comment should not trigger any market-data refresh.

## Delete Ticker

Deleting a ticker removes it from the current watchlist only.

It does not delete the shared cached stock data because other watchlists or users may still need that ticker.

## Future User Features

Planned but not implemented yet:

```text
manual cell overrides
manual value badges
row background colors
row font colors
row bold toggle
analysis change notifications
layer-specific refresh buttons
daily morning screen
```
