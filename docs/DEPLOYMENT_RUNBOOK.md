# Deployment Runbook

This is the production deployment checklist. The exact Oracle VM setup is still pending, but these rules should guide it.

## Target Architecture

```text
React frontend
    hosted as static site

Python FastAPI worker
    runs on Oracle VM or equivalent always-on server

Supabase
    auth
    database
    cache
```

## Local Production-Like Check

Before deploying:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python -c "from app.main import app; print(app.title)"
```

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\frontend
npm.cmd run build
```

## Worker Requirements

The worker needs:

```text
Python dependencies installed
worker/.env configured
network access to Supabase and providers
stable process manager
restart on failure
HTTPS before real users
CORS locked to frontend origin
```

## Frontend Requirements

The frontend needs:

```text
VITE_SUPABASE_URL
VITE_SUPABASE_ANON_KEY
VITE_WORKER_API_URL
```

`VITE_WORKER_API_URL` must point to the public HTTPS worker URL in production.

## Secrets

Never expose these in frontend files:

```text
SUPABASE_SERVICE_ROLE_KEY
FINNHUB_API_KEY
FMP_API_KEY
SEC_USER_AGENT
```

Before production, rotate keys that appeared in:

```text
chat
logs
screenshots
shared documents
committed files
```

## Worker Startup

Local command:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\production_app\worker
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Production should run this through Docker, systemd, or another restart manager. Do not rely on a manually opened terminal for production users.

## Debug Settings

Normal production:

```text
WORKER_DEBUG_MARKET_REQUESTS=0
WORKER_ENABLE_REQUEST_LIMITER=1
WORKER_ENABLE_QUOTE_FAST_LANE=0
```

Temporary diagnostics:

```text
WORKER_DEBUG_MARKET_REQUESTS=1
```

Turn debug logging off after investigation.

## CORS

Local:

```text
WORKER_ALLOWED_ORIGINS=http://localhost:5173
```

Production:

```text
WORKER_ALLOWED_ORIGINS=https://your-frontend-domain.example
```

Do not use:

```text
*
```

## Health Check

Worker health endpoint:

```text
GET /health
```

Expected response:

```json
{"ok":"true"}
```

## Pre-User Checklist

Before inviting real users:

```text
schema has been run in Supabase
frontend builds successfully
worker imports successfully
worker health endpoint responds
frontend can sign in
frontend can load watchlist from cache
visible price refresh is quote-only
add existing ticker does not refresh all data
add new ticker only refreshes that ticker
market_request_logs does not expose API keys
debug logging is off
CORS is locked down
service-role key is only on server
password reset flow is implemented
```

## Known Deployment Gaps

Still pending:

```text
Dockerfile / Compose production setup
Oracle VM setup commands
reverse proxy / HTTPS configuration
domain or subdomain final choice
systemd or Docker restart policy
log rotation
backup/restore procedure
```
