# Data Provider Decision Matrix

Measured on the Oracle production VM for `IONQ` on 2026-05-02. Timings are single-call wall-clock measurements from the server, using the production worker environment.

Benchmark script:

```powershell
python worker\local_test_scripts\Benchmark-Provider-Endpoints.py IONQ
```

Production VM command:

```bash
WORKER_ROOT=/opt/stock-analyzer/current/worker \
  /opt/stock-analyzer/venv/bin/python /home/ubuntu/Benchmark-Provider-Endpoints.py IONQ
```

## Endpoint Matrix

| Category | Provider | Endpoint | Measured | Status | Observed result | Recommended role |
|---|---|---|---:|---|---|---|
| Quote | Finnhub | `https://finnhub.io/api/v1/quote` | 0.042s | OK | Quote payload returned | Primary quote source when API key is available |
| Quote | Yahoo Spark | `https://query1.finance.yahoo.com/v7/finance/spark` | 0.038s | OK | Spark payload returned | Primary/secondary quote batch source |
| Quote | Yahoo Quote | `https://query1.finance.yahoo.com/v7/finance/quote` | 0.048s | Failed | `401 Unauthorized` | Do not rely on direct quote endpoint from Oracle |
| History | Yahoo Chart | `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}` | 0.069s | OK | Chart payload returned | Primary price history source |
| Annual fundamentals | SEC ticker map | `https://www.sec.gov/files/company_tickers.json` | 0.050s | OK | CIK map returned | Required helper for SEC fundamentals |
| Annual fundamentals | SEC company facts | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` | 0.194s | OK | Company facts returned | Primary annual revenue/profit source |
| Annual fundamentals | App SEC parser | `app.fetch_sec_fundamentals` | 0.282s | OK | Parsed annuals returned | Primary normalized annual fundamentals |
| Annual fundamentals | FMP income statement | `https://financialmodelingprep.com/stable/income-statement` | 0.034s | Failed | `429 Too Many Requests` | Fallback only; currently quota-limited |
| Annual fundamentals | Finnhub reported financials | `https://finnhub.io/api/v1/stock/financials-reported` | 0.038s | OK | Reported financials payload returned | Secondary fallback if SEC parsing fails |
| Ownership | Finviz snapshot | `https://finviz.com/quote.ashx` | 0.064s | OK | `Inst Own = 53.45%` | Fast current ownership fallback |
| Ownership | FMP positions summary | `https://financialmodelingprep.com/stable/institutional-ownership/symbol-positions-summary` | 0.238s | Partial | Returned no usable ownership in current app probe | Fallback only; check period handling and quota |
| Ownership | Finnhub metrics | `https://finnhub.io/api/v1/stock/metric` | 0.037s | Partial | Endpoint OK, but no usable IONQ ownership metric | Fallback only, symbol-dependent |
| Fundamentals/ownership | Yahoo quoteSummary | `https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}` | 0.063s | Failed | `401 Unauthorized` from direct request; previously also `429` through yfinance | Do not use first on Oracle |
| Profile/ownership | FMP profile | `https://financialmodelingprep.com/stable/profile` | 0.022s | Failed | `429 Too Many Requests` | Fallback only; currently quota-limited |
| Profile/ownership | Finviz raw page | `https://finviz.com/quote.ashx` | 0.060s | OK | Page returned | Parse only required fields |

## Current Add-Ticker Recommendation

For a strict new-ticker add, the fastest reliable production path is:

1. Quote: Finnhub quote, then Yahoo Spark/Chart fallback.
2. History: Yahoo Chart.
3. Annual revenue/profit: SEC company facts.
4. Institutional ownership: Finviz snapshot first, then FMP positions, then Finnhub metrics, then Yahoo/yfinance only as last fallback.

Measured strict full fetch after the latest optimization:

| Symbol | Total time | Status | Ownership |
|---|---:|---|---:|
| `IONQ` | 0.94s | complete | 53.45% |

## Decisions

- Yahoo is not first for production fundamentals/ownership because Oracle gets `401`/`429` from the relevant Yahoo endpoints.
- Yahoo Chart remains acceptable for history because it is fast and currently works from Oracle.
- SEC should be the primary annual fundamentals source because it is stable, free, and fast enough.
- Finviz is the fastest working ownership source right now, but it is an HTML page parse, not a contracted API. Treat it as pragmatic for MVP, not as the long-term paid-data solution.
- FMP should not be relied on until the rate-limit/quota issue is solved.
- Finnhub quote is excellent; Finnhub ownership is not complete enough for strict add on all symbols.

## Open Follow-Ups

- Add repeated-run averages and p95 latency, not just single-call timings.
- Run the matrix for representative symbols: `AAPL`, `IONQ`, `MP`, `QBTS`, `RGTI`.
- Decide whether to purchase a stable paid provider for ownership so we can remove HTML parsing from the production path.
