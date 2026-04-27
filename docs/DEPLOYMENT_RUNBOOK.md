# Deployment Runbook

This is the Oracle production procedure for the current app shape.

Current production layout:

```text
frontend:
    static React build
    hosted behind HTTPS

worker API:
    FastAPI on Oracle VM
    handles /refresh, /jobs, /activity

scheduler:
    separate long-running Python process on Oracle VM
    drives background refresh priority

Supabase:
    auth
    watchlists
    stock_snapshots
    refresh_jobs
    market_request_logs
    stock_universes
    watchlist_activity
```

## 1. Oracle VM Shape

Minimum practical VM:

```text
Ubuntu 22.04 or newer
2 OCPU
8 GB RAM
public IP
outbound internet access to Supabase, Yahoo, Finnhub, FMP, SEC
```

Open inbound ports:

```text
22    SSH
80    HTTP  (only if reverse proxy handles redirect/ACME)
443   HTTPS
8000  do not expose publicly if reverse proxy is used
```

Recommended:

```text
keep 8000 private to localhost
put Caddy or Nginx in front of the worker
serve the frontend from static hosting or from the proxy separately
```

## 2. Directory Layout

Suggested Oracle paths:

```text
/opt/stock-analyzer/app
/opt/stock-analyzer/logs
/opt/stock-analyzer/venv
/opt/stock-analyzer/env/worker.env
```

Suggested copy target:

```text
/opt/stock-analyzer/app/production_app
```

## 3. VM Bootstrap

Install system packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl
```

Optional reverse proxy:

```bash
sudo apt install -y caddy
```

Create runtime directories:

```bash
sudo mkdir -p /opt/stock-analyzer/app
sudo mkdir -p /opt/stock-analyzer/logs
sudo mkdir -p /opt/stock-analyzer/env
sudo chown -R $USER:$USER /opt/stock-analyzer
```

Copy the repo to Oracle:

```bash
scp -r production_app user@oracle-vm:/opt/stock-analyzer/app/
```

Create the virtual environment:

```bash
cd /opt/stock-analyzer
python3 -m venv venv
source /opt/stock-analyzer/venv/bin/activate
pip install --upgrade pip
pip install -r /opt/stock-analyzer/app/production_app/worker/requirements.txt
```

Build the frontend locally before upload, or on the VM if Node is available:

```bash
cd /opt/stock-analyzer/app/production_app/frontend
npm install
npm run build
```

## 4. Worker Environment

Create:

```text
/opt/stock-analyzer/env/worker.env
```

Start from:

```text
production_app/worker/.env.example
```

Required production values:

```text
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
FINNHUB_API_KEY=...
FMP_API_KEY=...
SEC_USER_AGENT=real-name real-email@example.com
WORKER_ALLOWED_ORIGINS=https://your-frontend-domain.example
WORKER_DEBUG_MARKET_REQUESTS=0
WORKER_ENABLE_REQUEST_LIMITER=1
WORKER_ENABLE_QUOTE_FAST_LANE=0
WORKER_ENABLE_FUNDAMENTALS_FALLBACKS=0
WORKER_FUNDAMENTALS_PROVIDER_ORDER=yfinance,sec,finnhub_reported,fmp
WORKER_MARKET_MAIN_OPEN_HOUR=9
WORKER_MARKET_MAIN_OPEN_MINUTE=30
WORKER_MARKET_MAIN_CLOSE_HOUR=16
WORKER_MARKET_MAIN_CLOSE_MINUTE=0
WORKER_MARKET_PRE_HOURS=4
WORKER_MARKET_POST_HOURS=4
WORKER_PRICE_TTL_MAIN_MINUTES=5
WORKER_PRICE_TTL_PREMARKET_MINUTES=5
WORKER_PRICE_TTL_POSTMARKET_MINUTES=5
WORKER_PRICE_TTL_CLOSED_MINUTES=240
WORKER_HISTORY_TTL_MAIN_MINUTES=1440
WORKER_HISTORY_TTL_CLOSED_MINUTES=10080
WORKER_FUNDAMENTALS_TTL_MAIN_MINUTES=1440
WORKER_FUNDAMENTALS_TTL_CLOSED_MINUTES=4320
WORKER_OWNERSHIP_TTL_MAIN_MINUTES=10080
WORKER_OWNERSHIP_TTL_CLOSED_MINUTES=20160
WORKER_QUOTE_MIN_INTERVAL_MS=300
WORKER_HISTORY_MIN_INTERVAL_MS=500
WORKER_FUNDAMENTALS_MIN_INTERVAL_MS=30000
WORKER_SCHEDULER_INTERVAL_SECONDS=120
WORKER_SCHEDULER_WATCHLIST_BATCH_SIZE=30
WORKER_SCHEDULER_UNIVERSE_BATCH_SIZE=15
WORKER_ACTIVE_WATCHLIST_WINDOW_MINUTES=10
```

Do not place these in any frontend env file:

```text
SUPABASE_SERVICE_ROLE_KEY
FINNHUB_API_KEY
FMP_API_KEY
SEC_USER_AGENT
```

## 5. Frontend Environment

Frontend production env must contain:

```text
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_WORKER_API_URL=https://your-worker-domain.example
```

Supabase Auth URL configuration must include:

```text
https://your-frontend-domain.example
http://localhost:5173
```

## 6. Required Supabase SQL

Before first real use, run:

```text
production_app/docs/supabase_optimized_schema.sql
production_app/docs/ownership_snapshots_schema.sql
production_app/docs/watchlist_activity_schema.sql
```

Optional admin/bootstrap SQL:

```text
production_app/docs/stock_universes_membership_update.sql
production_app/docs/stamp_cache_timestamps.sql
```

## 7. First Boot Order

Use this order on a fresh production environment:

1. Run required Supabase schema SQL.
2. Verify worker env file.
3. Start worker API.
4. Confirm `/health`.
5. Start scheduler.
6. Build/deploy frontend with production worker URL.
7. Sign in with one test user.
8. Verify watchlist activity heartbeat is writing.
9. Run optional preload/bootstrap jobs.

## 8. Manual Start Commands

Worker API:

```bash
cd /opt/stock-analyzer/app/production_app/worker
source /opt/stock-analyzer/venv/bin/activate
set -a
source /opt/stock-analyzer/env/worker.env
set +a
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Scheduler:

```bash
cd /opt/stock-analyzer/app/production_app/worker
source /opt/stock-analyzer/venv/bin/activate
set -a
source /opt/stock-analyzer/env/worker.env
set +a
python run_scheduler.py
```

## 9. systemd Services

Service unit templates are included in:

```text
production_app/deployment/systemd/stock-analyzer-worker.service
production_app/deployment/systemd/stock-analyzer-scheduler.service
```

Install them:

```bash
sudo cp /opt/stock-analyzer/app/production_app/deployment/systemd/stock-analyzer-worker.service /etc/systemd/system/
sudo cp /opt/stock-analyzer/app/production_app/deployment/systemd/stock-analyzer-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable stock-analyzer-worker
sudo systemctl enable stock-analyzer-scheduler
sudo systemctl start stock-analyzer-worker
sudo systemctl start stock-analyzer-scheduler
```

Check status:

```bash
sudo systemctl status stock-analyzer-worker
sudo systemctl status stock-analyzer-scheduler
```

View logs:

```bash
journalctl -u stock-analyzer-worker -f
journalctl -u stock-analyzer-scheduler -f
```

## 10. Reverse Proxy

Recommended:

```text
public HTTPS -> reverse proxy -> 127.0.0.1:8000
```

Minimum rule set:

```text
/health
/refresh
/jobs/*
/activity
```

Requirements:

```text
HTTPS enabled
CORS origin matches frontend domain
do not expose service-role secrets anywhere in the proxy config
```

## 11. Health Verification

Worker:

```bash
curl http://127.0.0.1:8000/health
```

Expected:

```json
{"ok":"true"}
```

Scheduler:

```text
console/journal output shows cycle lines
no uuid/job_id insert errors
active_visible / active_hidden / inactive_watchlists counts appear
```

Supabase checks:

```sql
select * from public.watchlist_activity order by last_seen_at desc limit 20;
```

```sql
select * from public.refresh_jobs order by created_at desc limit 20;
```

```sql
select * from public.market_request_logs order by created_at desc limit 20;
```

## 12. First Production Tests

Run these after deployment:

```text
sign in
load existing watchlist
add valid ticker
reject invalid ticker
remove ticker
switch watchlists
refresh visible list
verify scheduler starts collecting watchlist activity
verify active visible watchlist symbols appear in scheduler logs
verify no worker 500s in add/refresh flow
```

## 13. Optional Preload Jobs

Index universe load:

```bash
cd /opt/stock-analyzer/app/production_app/worker
source /opt/stock-analyzer/venv/bin/activate
set -a
source /opt/stock-analyzer/env/worker.env
set +a
python create_index_lists.py --output-dir index_exports --write-db
```

Full cache preload:

```bash
python bootstrap_full_cache.py --universe sp500 nasdaq100 dow30 --missing-only --limit 25
```

Yahoo ownership backfill:

```bash
python backfill_yahoo_ownership.py --universe sp500 nasdaq100 dow30 --spacing-ms 250
```

Use preload jobs before launch or during low-traffic windows.

## 14. Recovery

Restart services:

```bash
sudo systemctl restart stock-analyzer-worker
sudo systemctl restart stock-analyzer-scheduler
```

Stop services:

```bash
sudo systemctl stop stock-analyzer-worker
sudo systemctl stop stock-analyzer-scheduler
```

If the scheduler is noisy or provider behavior changes:

```text
set WORKER_DEBUG_MARKET_REQUESTS=1 temporarily
restart worker and scheduler
inspect market_request_logs
set WORKER_DEBUG_MARKET_REQUESTS=0 again
restart both services
```

## 15. Current Limitations

Current production limitations:

```text
frontend heartbeat drives watchlist activity; if a browser disappears without logout, the active window must expire
no persistent per-symbol visible_count ranking yet
no automatic bootstrap daemon beyond the current scheduler loop
reverse proxy config is deployment-specific and not committed yet
```
