# Supabase Edge Functions

## refresh-symbol

Used by the React frontend when a user adds a ticker that is not yet in `stock_snapshots`.

Behavior:

- Receives a ticker symbol.
- Fetches quote and daily chart data from Yahoo Finance endpoints.
- Rejects invalid/missing tickers.
- Upserts a basic `stock_snapshots` row.
- Returns the snapshot to the frontend.

It does not currently fetch full fundamentals. Revenue/profit fields remain `Nope`/`N/A` until a deeper Python refresher is added.

Deploy later with Supabase CLI:

```powershell
supabase functions deploy refresh-symbol
```

Required Supabase secrets for the function runtime:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

Do not expose `SUPABASE_SERVICE_ROLE_KEY` in the frontend.
