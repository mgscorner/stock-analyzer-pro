# Deployment Runbook

This runbook describes the repeatable VM deployment model for the current prototype.

It is designed for:

- one Oracle Ubuntu VM
- one public host name or public IP
- one shared Python virtual environment
- nginx serving the frontend and proxying `/api/*` to the worker
- systemd managing the worker and scheduler

## Deployment Model

Stable server paths:

```text
/opt/stock-analyzer/releases/<release-name>/production_app
/opt/stock-analyzer/current
/opt/stock-analyzer/env/worker.env
/opt/stock-analyzer/venv
```

Rules:

- `current` is a symlink to the active release
- each deploy creates a new release directory
- nginx serves from `current/frontend/dist`
- systemd runs from `current/worker`
- rollback is a symlink switch plus service restarts

## What Runs Where

```text
nginx
    serves frontend
    proxies /api/* to 127.0.0.1:8000

worker API
    FastAPI on 127.0.0.1:8000

scheduler
    separate systemd service

Supabase
    auth + application database
```

## Required Oracle Networking

The VM must have:

- public IPv4 address
- public subnet
- route table with `0.0.0.0/0 -> Internet Gateway`

Ingress rules must allow:

```text
TCP 22   source all or your IP
TCP 80   source 0.0.0.0/0
TCP 443  source 0.0.0.0/0
```

For HTTP and HTTPS, the rule must be:

```text
source port range: all
destination port range: 80 or 443
```

## Required Local Files

Windows deployment wrappers live in:

- [deployment/windows](C:/01_DATA/MyApps/AnalyzerAppToCodex/production_app/deployment/windows)

Create this file locally before deploying:

- `deployment/windows/deploy_config.bat`

Start from:

- [deploy_config.example.bat](C:/01_DATA/MyApps/AnalyzerAppToCodex/production_app/deployment/windows/deploy_config.example.bat)

Important values:

```text
PROJECT_ROOT
SSH_KEY
DEPLOY_USER
DEPLOY_HOST
PUBLIC_HOST
LETSENCRYPT_EMAIL
FRONTEND_SUPABASE_URL
FRONTEND_SUPABASE_ANON_KEY
FRONTEND_WORKER_API_URL=/api
REMOTE_RELEASE_UPLOAD_DIR
```

The production frontend API URL should be:

```text
VITE_WORKER_API_URL=/api
```

That avoids hardcoding raw worker IPs into the built frontend.

Optional local secret file for easier repeat deployments:

- `deployment/windows/worker.env`

This file is not committed to git and can be uploaded automatically by:

- [upload_worker_env.bat](C:/01_DATA/MyApps/AnalyzerAppToCodex/production_app/deployment/windows/upload_worker_env.bat)

## Required Server Environment File

Create on the VM:

```text
/opt/stock-analyzer/env/worker.env
```

Start from:

- [worker/.env.example](C:/01_DATA/MyApps/AnalyzerAppToCodex/production_app/worker/.env.example)

Minimum required values:

```text
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
FINNHUB_API_KEY=...
FMP_API_KEY=...
SEC_USER_AGENT=real-name real-email@example.com
WORKER_ALLOWED_ORIGINS=https://your-domain.example
WORKER_DEBUG_MARKET_REQUESTS=0
WORKER_ENABLE_REQUEST_LIMITER=1
WORKER_ENABLE_FUNDAMENTALS_FALLBACKS=0
WORKER_FUNDAMENTALS_PROVIDER_ORDER=yfinance,sec,finnhub_reported,fmp
WORKER_SCHEDULER_INTERVAL_SECONDS=60
```

If you are testing temporarily by IP instead of domain, set:

```text
WORKER_ALLOWED_ORIGINS=http://<public-ip>
```

Do not place secrets in any frontend env file.

## Required Supabase SQL

Run these before first real use:

```text
docs/supabase_optimized_schema.sql
docs/ownership_snapshots_schema.sql
docs/watchlist_activity_schema.sql
docs/user_feedback_schema.sql
docs/alerts_schema_update.sql
```

If your alerts table still has old columns like `ticker` or `target_price`, also run:

```text
docs/alerts_schema_cleanup.sql
```

## One-Time VM Bootstrap

After SSH access works and `worker.env` exists on the VM, upload:

- release zip
- `deployment/scripts/bootstrap_vm.sh`
- `deployment/scripts/deploy_release.sh`

Then run on the VM:

```bash
bash /home/ubuntu/bootstrap_vm.sh
```

What it does:

```text
installs python, nginx, certbot, unzip
creates /opt/stock-analyzer paths
creates shared python venv
installs systemd units
installs persistent VM firewall allow rules for 80/443
enables nginx, worker, scheduler services
```

This is idempotent and safe to rerun.

## Release Build and Deploy From Windows

The intended Windows flow is:

### 1. Build the release

```bat
deployment\windows\build_release.bat
```

This:

```text
builds the frontend
injects production frontend env values
creates a clean release zip
writes deployment\artifacts\latest_release.txt
```

### 2. Upload the release and remote scripts

```bat
deployment\windows\upload_release.bat
```

This uploads:

```text
latest release zip
bootstrap_vm.sh
deploy_release.sh
```

If you maintain a local server env file, upload it with:

```bat
deployment\windows\upload_worker_env.bat
```

### 3. Bootstrap and deploy remotely

```bat
deployment\windows\deploy_remote.bat
```

This:

```text
runs bootstrap_vm.sh
runs deploy_release.sh against the uploaded release zip
```

### 4. Smoke test from Windows

```bat
deployment\windows\smoke_test.bat
```

### 5. Full deploy shortcut

```bat
deployment\windows\full_deploy.bat
```

That runs:

```text
optional worker env upload
build
upload
deploy
smoke test
```

## What `deploy_release.sh` Does

The server deploy script:

```text
unpacks the release zip into /opt/stock-analyzer/releases/<release-name>
installs Python requirements into the shared venv
switches /opt/stock-analyzer/current to the new release
writes nginx config
restarts worker, scheduler, nginx
runs smoke_test.sh
optionally requests or renews Let's Encrypt TLS if:
    - PUBLIC_HOST is a domain
    - LETSENCRYPT_EMAIL is provided
```

If `PUBLIC_HOST` is an IP address, TLS is skipped automatically.

## HTTPS

Preferred production target:

```text
real domain
nginx on port 80 and 443
certbot --nginx
```

Requirements for TLS:

- DNS record pointing to the VM public IP
- ports `80` and `443` open in Oracle
- `PUBLIC_HOST` set to the domain
- `LETSENCRYPT_EMAIL` set in `deploy_config.bat`

If you deploy by raw IP first:

- the app can run over HTTP
- but HTTPS cannot be provisioned for the IP itself with Let's Encrypt

## Smoke Test Expectations

Server-side smoke test checks:

- worker service active
- scheduler service active
- nginx service active
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1/`
- `http://127.0.0.1/api/health`

Windows smoke test checks:

- `http://PUBLIC_HOST/`
- `http://PUBLIC_HOST/api/health`

## Rollback

Rollback command on the VM:

```bash
bash /opt/stock-analyzer/current/deployment/scripts/rollback_release.sh
```

It:

```text
finds the previous release
switches the current symlink
restarts worker, scheduler, and nginx
```

## Oracle Ubuntu Firewall Note

Oracle Ubuntu images can include host-level iptables rules that allow SSH but reject inbound HTTP and HTTPS by default.

That is separate from Oracle subnet security lists and NSGs.

The bootstrap script now installs a small systemd-managed firewall rule set so the VM itself allows:

```text
TCP 80
TCP 443
```

If HTTP works locally on the VM but public HTTP still times out, always check both:

```text
Oracle subnet / NSG rules
VM iptables rules
```

## Current Recommendation

For the current 2-day prototype window:

1. stabilize this VM path
2. test the bat-driven deploy/update cycle
3. move to a real domain
4. enable HTTPS with certbot
5. only then share the public link widely
