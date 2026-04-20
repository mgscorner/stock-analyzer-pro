# Stock Analyzer Worker

Python FastAPI worker for the frozen React/Supabase app.

The frontend calls this worker when a user requests a refresh. The worker validates the user's Supabase access token, creates a `refresh_jobs` row, refreshes market data with `yfinance`, writes `stock_snapshots`, and marks the job done or failed.

## Local Run

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\frozen_react\react_supabase_v0_1\worker
copy .env.example .env
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set the frontend env var:

```text
VITE_WORKER_API_URL=http://localhost:8000
```

## Docker

```powershell
docker build -t stock-analyzer-worker .
docker run --env-file .env -p 8000:8000 stock-analyzer-worker
```

## Endpoints

```text
GET  /health
POST /refresh
GET  /jobs/{job_id}
```

`POST /refresh` requires:

```text
Authorization: Bearer <Supabase user access token>
```
