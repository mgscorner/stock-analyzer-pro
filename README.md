### 🤖 AI-Assisted Co-Development: Prototyping, Strategy, & Engineering Insights

This application marks my first successful initiative in **AI-assisted co-development using OpenAI Codex**, transforming my core systems engineering expertise into a functional web application. As an engineer with a professional focus on **embedded and low-level code**, I used AI to bridge the web-syntax gap—leveraging my fundamental knowledge in databases, servers, and basic frontend concepts to read, audit, and debug code without needing to write every syntax element from scratch.

The development journey provided critical insights into architectural research, rapid prototyping, and the realities of human-AI collaboration:

* **Early Bottleneck Discovery & Pivoting:** The project began with multiple local prototyping iterations. An initial attempt using Streamlit revealed that the AI struggled to map complex requirements directly to the visual interface. This limitation triggered a dedicated research and planning phase to evaluate alternative implementations, weigh trade-offs, and ultimately pivot to a completely redesigned user interface and a more optimal technology stack.
* **Architecture Over Syntax:** Rapid AI code generation shifts the developer’s primary value. For a non-web developer, it serves as a force multiplier: it automates tedious tasks—such as generating documentation, commenting code, staging repository commits, and configuring deployment scripts—allowing the engineer to focus entirely on system architecture, code review, and high-level feature planning.
* **Guarding Against AI Blindspots:** AI tools frequently exhibit cyclic behaviors, such as writing superficial patches to bypass bugs or overwriting optimized blocks with lower-quality code. Strong technical oversight is critical to look behind the syntax, identify design weaknesses, and ensure errors are fundamentally fixed rather than just worked around.
* **The Necessity of Automated Testing:** Because AI updates can introduce silent regressions, establishing a rigid verification, guardrail, and automated testing infrastructure is non-negotiable to future-proof the application across iterations.

**Key Takeaway:** While AI can accelerate the baseline build, a skilled human engineer remains entirely indispensable. Bringing a product to a high-performance, enterprise-ready, and highly usable finish line requires structural engineering expertise, deep code comprehension, and strategic design oversight.


# 📈 Stock Analyzer App

This repository contains the **production-grade** workspace for the Stock Analyzer App. 

By production-grade, I mean the application has successfully transitioned out of the local "it works on my machine" prototyping phase into a fully functional, cloud-deployed MVP (Minimum Viable Product). The primary milestone of this phase was achieving an end-to-end live deployment on a remote server, moving beyond a simple prototype running on localhost.

🔗 **Live Application Link:** **https://stockanalyzerpro.duckdns.org/**

### 🛠 Cloud Infrastructure & Deployment Details
Instead of using managed, single-click platform-as-a-service providers, I self-hosted the architecture to gain a deeper understanding of network infrastructure and deployment pipelines:

* **Compute & Virtualization:** Provisioned and configured an **Oracle Cloud Infrastructure (OCI) Compute Instance** running an enterprise Linux distribution to act as the dedicated application host.
* **Network & Ingress Configuration:** Configured the OCI Virtual Cloud Network (VCN) security lists, opening explicit ingress rules for HTTP/HTTPS web traffic while keeping management ports isolated.
* **Dynamic DNS Routing:** Integrated a **DuckDNS** automation daemon on the host. Because residential or free-tier cloud IPs can rotate, this background script continuously syncs the server's public IP address with a custom subdomain to guarantee reliable routing.
* **Current Status & Minor Technical Debt:** The core data pipelines and analysis engine are stable. There are minor known edge cases within the asset discovery module and the live data-point patching routine. These do not block core usage and are prioritized for refactoring in the next scheduled release.


# Project Organization

## Use this folder for all forward work:

```text
production_app/
    frontend/   React/Vite browser app
    worker/     Python FastAPI worker for market-data refreshes
    supabase/   Supabase functions/archive assets
    docs/       schema and architecture notes
```

## The active production architecture is:

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
cd \AnalyzerAppToCodex\production_app\worker
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Start the frontend:

```powershell
cd  \AnalyzerAppToCodex\production_app\frontend
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
