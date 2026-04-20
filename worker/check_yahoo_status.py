from __future__ import annotations

import sys

import requests
import yfinance as yf


def main() -> int:
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "UNH").strip().upper()
    headers = {"User-Agent": "Mozilla/5.0"}

    quote = requests.get(
        "https://query1.finance.yahoo.com/v7/finance/quote",
        params={"symbols": symbol},
        headers=headers,
        timeout=12,
    )
    chart = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"range": "5d", "interval": "1d"},
        headers=headers,
        timeout=12,
    )

    print(f"symbol: {symbol}")
    print(f"quote_api: {quote.status_code} {quote.text[:160]}")
    print(f"chart_api: {chart.status_code} {chart.text[:160]}")

    try:
        info = yf.Ticker(symbol).info
        name = info.get("shortName") or info.get("longName") or ""
        print(f"yfinance_info: ok {bool(info)} {name}")
    except Exception as exc:
        print(f"yfinance_info: error {str(exc)[:200]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
