# Frontend Migration

The Streamlit app remains preserved as the working prototype. The new product UI is being built in:

```text
frontend/
```

## Preserved Prototype

Current Streamlit work was copied to:

```text
prototype/
```

The active Streamlit files still also exist in:

```text
app/
docs/
```

## New Frontend Stack

```text
Vite + React + Supabase
```

The frontend uses Supabase for:

- login/signup
- watchlists
- comments
- cached stock snapshots
- app config

The frontend does not call yFinance. Stock refresh should remain server-side through Python scripts, GitHub Actions, or a future worker.

For immediate add-ticker behavior, a Supabase Edge Function was added:

```text
supabase/functions/refresh-symbol
```

The React app calls this function when a user adds a ticker that is missing from `stock_snapshots`.

## Run

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\frontend
copy .env.example .env
```

Edit `.env`:

```text
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
```

Install dependencies:

```powershell
npm.cmd install
```

Run:

```powershell
npm.cmd run dev
```

Build check:

```powershell
npm.cmd run build
```

## Implemented In React v0.1

- Supabase auth
- Watchlist switcher
- Create watchlist
- Delete current watchlist with confirmation
- Add ticker if it already exists in `stock_snapshots`
- Manage ticker comment
- Delete ticker
- Colored table
- Failed rows styled gray/italic
- Basic plan limits from `app_config`

## Not Yet Implemented

- Python cache refresh script
- Subscription/access enforcement
- Admin roles
- PayPal flow
- Scanner UI
- Chart view
- CSV export
- Hosted deployment

## Why This Migration Exists

Streamlit reruns the full Python script on most widget changes. That made small UI actions feel slow. React gives component-level updates and direct control over what refreshes.
