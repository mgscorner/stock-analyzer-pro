# Worker Architecture

Production target:

```text
React frontend
    -> calls Oracle FastAPI worker
    -> reads Supabase tables

Oracle FastAPI worker
    -> validates Supabase user access token
    -> creates refresh_jobs rows
    -> refreshes market data in background through provider-specific fetch modules
    -> upserts stock_snapshots
    -> marks jobs done/failed/partial

Supabase
    -> auth
    -> watchlists
    -> stock_snapshots
    -> refresh_jobs
```

The browser never receives the Supabase service-role key and never calls market-data providers directly.

Refresh behavior is governed by:

```text
production_app/docs/REFRESH_POLICY.md
production_app/docs/PROVIDER_STRATEGY.md
production_app/docs/BOOTSTRAP_PROCESS.md
```

Provider routing is category-aware. The worker should eventually choose providers per data group, not through one global provider switch:

```text
quote
history
fundamentals
ownership
screener/universe
```

Each group can have a different default provider and fallback chain.

Admin bootstrap is a separate background path:

```text
admin bootstrap
    -> builds stock universe
    -> fills annual fundamentals from SEC EDGAR
    -> fills history/profile data
    -> later runs SEC 13F ownership aggregation
    -> writes shared cache tables

normal user flow
    -> reads cached rows instantly
    -> queues only due/missing high-priority refresh work
```

## Secret Handling

The worker needs the Supabase service-role key because it writes trusted backend data into `stock_snapshots` and `refresh_jobs`.

Rules:

- Keep `SUPABASE_SERVICE_ROLE_KEY` only in `worker/.env` locally or in Oracle server environment variables.
- Never add the service-role key to `frontend/.env`.
- Never use a `VITE_` prefix for the service-role key. `VITE_` variables are bundled into the browser.
- Never print `.env` contents, request authorization headers, or Supabase keys in logs.
- Do not bake secrets into the Docker image.
- Use `docker run --env-file .env ...` or Docker Compose `env_file` on the server.
- Before production, rotate any service-role key that has been pasted into chat, logs, screenshots, or other shared places.

## Local Flow

1. Start the worker at `http://localhost:8000`.
2. Start the React app at `http://localhost:5173`.
3. User clicks `Refresh`.
4. React sends `POST /refresh` with the Supabase user access token.
5. Worker creates a `refresh_jobs` row and returns `job_id`.
6. React checks `/jobs/{job_id}` while the job is active.
7. Worker writes `stock_snapshots`.
8. React reloads `stock_snapshots` and repaints the table.

## Oracle Flow

Run the same worker container on the Oracle VM. Later, put Caddy or another reverse proxy in front of it for HTTPS:

```text
api.yourdomain.com -> worker container port 8000
```

For a free-domain setup, use a free DNS/subdomain provider that can point to the Oracle public IP.
