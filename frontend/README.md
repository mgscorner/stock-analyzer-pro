# Stock Analyzer Frontend

React/Vite frontend for the product version of Stock Analyzer Pro.

This frontend uses Supabase directly for:

- Auth
- Watchlists
- Comments
- App config
- Cached stock snapshots

It does not call yFinance. Stock refresh should stay server-side through the Python cache refresher or a future backend worker.

## Run Locally

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\frozen_react\react_supabase_v0_1\frontend
copy .env.example .env
```

Edit `.env`:

```text
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_WORKER_API_URL=http://localhost:8000
```

Install dependencies:

```powershell
npm.cmd install
```

Run:

```powershell
npm.cmd run dev
```

Start the Python worker in a second terminal:

```powershell
cd C:\01_DATA\MyApps\AnalyzerAppToCodex\frozen_react\react_supabase_v0_1\worker
copy .env.example .env
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The worker `.env` needs:

```text
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
WORKER_ALLOWED_ORIGINS=http://localhost:5173
```

`SUPABASE_SERVICE_ROLE_KEY` must stay server-side. Do not put it in this frontend `.env`, do not prefix it with `VITE_`, and rotate it before production if it has been exposed in chat, logs, screenshots, or shared files.

Before using worker refreshes, run the schema in:

```text
C:\01_DATA\MyApps\AnalyzerAppToCodex\frozen_react\react_supabase_v0_1\docs\supabase_optimized_schema.sql
```

## Notes

The Streamlit prototype is preserved in:

```text
C:\01_DATA\MyApps\AnalyzerAppToCodex\prototype
```

The matching worker, archived Supabase Edge Function, and migration notes are frozen next to this frontend in:

```text
C:\01_DATA\MyApps\AnalyzerAppToCodex\frozen_react\react_supabase_v0_1\worker
C:\01_DATA\MyApps\AnalyzerAppToCodex\frozen_react\react_supabase_v0_1\supabase
C:\01_DATA\MyApps\AnalyzerAppToCodex\frozen_react\react_supabase_v0_1\docs
```
