# Stock Analyzer Production App

This is the production-grade app workspace.

Use this folder for all forward work:

```text
production_app/
    frontend/   React/Vite browser app
    worker/     Python FastAPI worker for market-data refreshes
    supabase/   Supabase functions/archive assets
    docs/       schema and architecture notes
```

The active production architecture is:

```text
React frontend
    -> Supabase auth/database
    -> Python worker refresh API

Python worker
    -> validates Supabase user token
    -> fetches market data
    -> writes stock_snapshots and refresh_jobs

Supabase
    -> auth, watchlists, stock_snapshots, app_config, refresh_jobs
```

## Local Run

Run the schema in:

```text
production_app/docs/supabase_optimized_schema.sql
```

Start the worker:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Start the frontend:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\frontend
npm.cmd run dev
```

## Secrets

`frontend/.env` contains only browser-safe values.

`worker/.env` contains server-only values, including `SUPABASE_SERVICE_ROLE_KEY`. Do not move that key into frontend files.

Optional market-data provider keys:

```text
FINNHUB_API_KEY=...
FMP_API_KEY=...
SEC_USER_AGENT=Your Name your-email@example.com
```

SEC EDGAR is the preferred source for annual revenue/profit and does not require an API key. Set `SEC_USER_AGENT` to a real contact before production. Finnhub/FMP remain useful for quote/profile and fallback data. See `docs/PROVIDER_STRATEGY.md`.

Optional worker debug:

```text
WORKER_DEBUG_MARKET_REQUESTS=1
```

This writes market request attempts to `market_request_logs` for burst/rate-limit analysis. Keep it off unless debugging.

Market request limiter defaults:

```text
WORKER_ENABLE_REQUEST_LIMITER=1
WORKER_ENABLE_QUOTE_FAST_LANE=0
WORKER_QUOTE_MIN_INTERVAL_MS=300
WORKER_HISTORY_MIN_INTERVAL_MS=500
WORKER_FUNDAMENTALS_MIN_INTERVAL_MS=30000
```

## Design Docs

Read these before changing refresh behavior:

```text
production_app/docs/REFRESH_POLICY.md
production_app/docs/PROVIDER_STRATEGY.md
production_app/docs/WORKER_ARCHITECTURE.md
production_app/docs/ROADMAP.md
production_app/docs/ADMIN_GUIDE.md
production_app/docs/CURRENT_STATE_AND_TESTING.md
production_app/docs/USER_GUIDE.md
production_app/docs/DEPLOYMENT_RUNBOOK.md
production_app/docs/supabase_optimized_schema.sql
```
