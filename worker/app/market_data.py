from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
import yfinance as yf

from .market_debug import MarketRequestLogger
from .rate_limit import MarketRequestLimiter


TRADING_DAY_OFFSETS = {
    "close_5y": 1260,
    "close_3y": 756,
    "close_1y": 252,
    "close_6m": 126,
    "close_1m": 21,
    "close_3m": 63,
}

QUOTE_CACHE_TTL_SECONDS = 120
HISTORY_CACHE_TTL_SECONDS = 900
FUNDAMENTALS_CACHE_TTL_SECONDS = 1800
QUOTE_SUMMARY_BACKOFF_SECONDS = 900
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
FMP_STABLE_BASE_URL = "https://financialmodelingprep.com/stable"
YAHOO_SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"

_quote_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_history_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_fundamentals_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_quote_summary_blocked_until = 0.0
_batch_quote_blocked_until = 0.0

PERIOD_BASELINES = {
    "perf_5y": "close_5y",
    "perf_3y": "close_3y",
    "perf_1y": "close_1y",
    "perf_6m": "close_6m",
    "perf_1m": "close_1m",
    "perf_3m": "close_3m",
}


def normalize_symbol(value: str) -> str:
    return str(value or "").strip().upper()


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def provider_key(name: str) -> str:
    return os.getenv(name, "").strip()


def number_or_zero(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        if isinstance(value, float) and pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def fetch_snapshot(
    symbol: str,
    layers: list[str] | None = None,
    logger: MarketRequestLogger | None = None,
    limiter: MarketRequestLimiter | None = None,
) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    requested_layers = set(layers or ["quote", "history", "fundamentals"])
    logger = logger or MarketRequestLogger(enabled=False)
    limiter = limiter or MarketRequestLimiter(enabled=False)
    snapshot: dict[str, Any] = {"symbol": symbol}
    errors: list[str] = []

    history = pd.DataFrame()
    if "quote" in requested_layers:
        try:
            snapshot.update(download_quote(symbol, logger, limiter))
            snapshot["quote_status"] = "complete"
            snapshot["price_updated_at"] = iso_now()
        except Exception as exc:
            snapshot["quote_status"] = "error"
            errors.append(f"quote: {exc}")

    if "history" in requested_layers:
        try:
            history = download_history(symbol, logger, limiter)
            if history.empty:
                raise ValueError("No price history")
            snapshot.update(extract_close_baselines(history))
            snapshot["history_data"] = history_to_records(history)
            if number_or_zero(snapshot.get("price")) <= 0:
                snapshot["price"] = latest_close(history)
                snapshot["name"] = snapshot.get("name") or symbol
                snapshot["price_updated_at"] = iso_now()
                if number_or_zero(snapshot.get("price")) > 0:
                    snapshot["quote_status"] = "complete"
            snapshot["history_status"] = "complete"
            snapshot["history_updated_at"] = iso_now()
        except Exception as exc:
            snapshot["history_status"] = "error"
            errors.append(f"history: {exc}")

    if ("quote" in requested_layers or "history" in requested_layers) and number_or_zero(snapshot.get("price")) <= 0:
        raise ValueError(f"No valid market data found for {symbol}. Check the ticker symbol.")

    if number_or_zero(snapshot.get("price")) > 0:
        snapshot = recalc_performance(snapshot)

    if "fundamentals" in requested_layers:
        try:
            fundamentals = download_fundamentals(symbol, logger, limiter)
            fundamentals_name = fundamentals.get("name")
            snapshot.update(
                {
                    "name": (
                        fundamentals_name
                        if fundamentals_name and normalize_symbol(fundamentals_name) != symbol
                        else snapshot.get("name") or symbol
                    ),
                    "market_cap": fundamentals["market_cap"] or snapshot.get("market_cap") or 0,
                    "inst_ownership": fundamentals["inst_ownership"],
                }
            )
            snapshot.update(extract_fundamental_fields(fundamentals["financials"]))
            snapshot["fundamentals_status"] = "complete"
            snapshot["fundamentals_updated_at"] = iso_now()
        except Exception as exc:
            snapshot["fundamentals_status"] = "error"
            errors.append(f"fundamentals: {exc}")

    snapshot["snapshot_status"] = snapshot_status(snapshot)
    snapshot["last_error"] = None
    snapshot["last_error_at"] = None
    snapshot["updated_at"] = iso_now()
    return snapshot


def batch_quote_snapshots(
    symbols: list[str],
    existing_snapshots: dict[str, dict[str, Any]],
    logger: MarketRequestLogger | None = None,
    limiter: MarketRequestLimiter | None = None,
    fast_lane: bool = False,
    fallback_spacing_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    logger = logger or MarketRequestLogger(enabled=False)
    limiter = limiter or MarketRequestLimiter(enabled=False)
    symbols = [normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)]
    quote_map = fetch_yahoo_spark_quotes(symbols, logger, limiter, bypass_limiter=fast_lane)
    if not quote_map:
        quote_map = fetch_quote_api_batch(symbols, logger, limiter, bypass_limiter=fast_lane)
    snapshots = []
    now = iso_now()
    fallback_calls = 0
    for symbol in symbols:
        quote = quote_map.get(symbol, {})
        price = number_or_zero(
            quote.get("regularMarketPrice")
            or quote.get("postMarketPrice")
            or quote.get("preMarketPrice")
            or quote.get("regularMarketPreviousClose")
        )
        if price <= 0:
            if fallback_calls and fallback_spacing_seconds > 0:
                time.sleep(fallback_spacing_seconds)
            fallback_calls += 1
            quote = fetch_finnhub_quote(symbol, logger, limiter)
            price = number_or_zero(quote.get("regularMarketPrice"))
        if price <= 0:
            if fallback_calls and fallback_spacing_seconds > 0:
                time.sleep(fallback_spacing_seconds)
            fallback_calls += 1
            quote = fetch_chart_quote_api(symbol, logger, limiter)
            price = number_or_zero(quote.get("regularMarketPrice"))
        if price <= 0:
            snapshots.append(
                {
                    "symbol": symbol,
                    "quote_status": "error",
                    "quote_last_error": "No valid batch quote",
                    "quote_retry_after": None,
                    "updated_at": now,
                }
            )
            continue

        existing = existing_snapshots.get(symbol, {})
        snapshot = {
            "symbol": symbol,
            "name": quote.get("longName") or quote.get("shortName") or existing.get("name") or symbol,
            "price": price,
            "market_cap": number_or_zero(quote.get("marketCap")),
            "quote_status": "complete",
            "quote_last_error": None,
            "quote_retry_after": None,
            "price_updated_at": now,
            "updated_at": now,
        }
        snapshot.update(recalc_performance({**existing, **snapshot}))
        snapshots.append(snapshot)
    return snapshots


def download_quote(symbol: str, logger: MarketRequestLogger, limiter: MarketRequestLimiter) -> dict[str, Any]:
    cached = cache_get(_quote_cache, symbol, QUOTE_CACHE_TTL_SECONDS)
    if cached:
        return cached

    quote = fetch_finnhub_quote(symbol, logger, limiter)
    if not quote:
        quote = fetch_quote_api(symbol, logger, limiter)
    if not quote:
        quote = fetch_yahoo_spark_quote(symbol, logger, limiter)
    if quote:
        price = number_or_zero(
            quote.get("regularMarketPrice")
            or quote.get("postMarketPrice")
            or quote.get("preMarketPrice")
            or quote.get("regularMarketPreviousClose")
        )
        if price > 0:
            result = {
                "name": quote.get("longName") or quote.get("shortName") or symbol,
                "price": price,
                "market_cap": number_or_zero(quote.get("marketCap")),
            }
            cache_set(_quote_cache, symbol, result)
            return result

    ensure_quote_summary_allowed()
    stock = yf.Ticker(symbol)
    limiter.wait("quote")
    with logger.track(symbol, "quote", "yfinance_info"):
        info = safe_stock_info(stock)
    price = number_or_zero(info.get("currentPrice") or info.get("regularMarketPrice"))
    if price <= 0:
        fast_info = safe_fast_info(stock)
        price = number_or_zero(fast_info.get("last_price") or fast_info.get("previous_close"))
    if price <= 0:
        raise ValueError("No valid quote")

    result = {
        "name": info.get("longName") or info.get("shortName") or symbol,
        "price": price,
        "market_cap": number_or_zero(info.get("marketCap")),
    }
    cache_set(_quote_cache, symbol, result)
    return result


def download_history(symbol: str, logger: MarketRequestLogger, limiter: MarketRequestLimiter) -> pd.DataFrame:
    cached = cache_get(_history_cache, symbol, HISTORY_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached.copy()

    history = fetch_history_api(symbol, logger, limiter)
    if history is not None and not history.empty:
        cache_set(_history_cache, symbol, history.copy())
        return history

    stock = yf.Ticker(symbol)
    limiter.wait("history")
    with logger.track(symbol, "history", "yfinance_history"):
        history = stock.history(period="6y", auto_adjust=False)
    if history is None or history.empty or "Close" not in history.columns:
        return pd.DataFrame()
    cache_set(_history_cache, symbol, history.copy())
    return history


def download_fundamentals(symbol: str, logger: MarketRequestLogger, limiter: MarketRequestLimiter) -> dict[str, Any]:
    cached = cache_get(_fundamentals_cache, symbol, FUNDAMENTALS_CACHE_TTL_SECONDS)
    if cached:
        return cached

    limiter.wait("fundamentals")
    result = fetch_finnhub_reported_fundamentals(symbol, logger, limiter)
    if result:
        cache_set(_fundamentals_cache, symbol, result)
        return result

    result = fetch_fmp_fundamentals(symbol, logger, limiter)
    if result:
        cache_set(_fundamentals_cache, symbol, result)
        return result

    if provider_key("FMP_API_KEY") or provider_key("FINNHUB_API_KEY"):
        raise ValueError("Provider fundamentals unavailable")

    ensure_quote_summary_allowed()
    stock = yf.Ticker(symbol)
    with logger.track(symbol, "fundamentals", "yfinance_info"):
        info = safe_stock_info(stock)
    try:
        with logger.track(symbol, "fundamentals", "yfinance_financials"):
            financials = stock.financials
    except Exception:
        financials = pd.DataFrame()
    if financials is None or not isinstance(financials, pd.DataFrame):
        financials = pd.DataFrame()

    result = {
        "name": info.get("longName") or info.get("shortName") or symbol,
        "market_cap": number_or_zero(info.get("marketCap")),
        "inst_ownership": number_or_zero(info.get("heldPercentInstitutions")) * 100,
        "financials": financials,
    }
    cache_set(_fundamentals_cache, symbol, result)
    return result


def cache_get(cache: dict[str, tuple[float, Any]], key: str, ttl_seconds: int) -> Any:
    entry = cache.get(key)
    if not entry:
        return None
    created_at, value = entry
    if time.time() - created_at > ttl_seconds:
        cache.pop(key, None)
        return None
    return value


def cache_set(cache: dict[str, tuple[float, Any]], key: str, value: Any) -> None:
    cache[key] = (time.time(), value)


def ensure_quote_summary_allowed() -> None:
    if time.time() < _quote_summary_blocked_until:
        remaining = int(_quote_summary_blocked_until - time.time())
        raise ValueError(f"Yahoo fundamentals endpoint is cooling down for {remaining}s after rate limiting")


def safe_stock_info(stock: yf.Ticker) -> dict[str, Any]:
    global _quote_summary_blocked_until
    try:
        return dict(stock.info or {})
    except Exception as exc:
        message = str(exc)
        if "Too Many Requests" in message or "Expecting value" in message:
            _quote_summary_blocked_until = time.time() + QUOTE_SUMMARY_BACKOFF_SECONDS
        raise


def fetch_finnhub_quote(symbol: str, logger: MarketRequestLogger, limiter: MarketRequestLimiter) -> dict[str, Any]:
    api_key = provider_key("FINNHUB_API_KEY")
    if not api_key:
        return {}
    symbol = normalize_symbol(symbol)
    try:
        limiter.wait("quote")
        with logger.track(symbol, "quote", "finnhub_quote") as span:
            quote_response = requests.get(
                f"{FINNHUB_BASE_URL}/quote",
                params={"symbol": symbol, "token": api_key},
                timeout=12,
            )
            span.status_code = quote_response.status_code
            quote_response.raise_for_status()
        quote_data = quote_response.json() or {}
        price = number_or_zero(quote_data.get("c"))
        if price <= 0:
            return {}

        profile = {}
        try:
            limiter.wait("quote")
            with logger.track(symbol, "quote", "finnhub_profile") as span:
                profile_response = requests.get(
                    f"{FINNHUB_BASE_URL}/stock/profile2",
                    params={"symbol": symbol, "token": api_key},
                    timeout=12,
                )
                span.status_code = profile_response.status_code
                profile_response.raise_for_status()
            profile = profile_response.json() or {}
        except Exception:
            profile = {}

        market_cap = number_or_zero(profile.get("marketCapitalization"))
        if market_cap > 0 and market_cap < 1_000_000_000:
            market_cap *= 1_000_000
        return {
            "symbol": symbol,
            "shortName": profile.get("ticker") or symbol,
            "longName": profile.get("name") or symbol,
            "regularMarketPrice": price,
            "regularMarketPreviousClose": number_or_zero(quote_data.get("pc")),
            "marketCap": market_cap,
        }
    except Exception:
        return {}


def fetch_fmp_quote_batch(
    symbols: list[str],
    logger: MarketRequestLogger,
    limiter: MarketRequestLimiter,
    bypass_limiter: bool = False,
) -> dict[str, dict[str, Any]]:
    api_key = provider_key("FMP_API_KEY")
    symbols = [normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)]
    if not api_key or not symbols:
        return {}
    try:
        batch_symbol = ",".join(symbols)
        limiter.wait("quote", bypass=bypass_limiter)
        with logger.track(batch_symbol, "quote", "fmp_quote_batch") as span:
            response = requests.get(
                f"{FMP_BASE_URL}/quote/{batch_symbol}",
                params={"apikey": api_key},
                timeout=12,
            )
            span.status_code = response.status_code
            response.raise_for_status()
        rows = response.json() or []
        if isinstance(rows, dict):
            rows = [rows]
        quotes: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = normalize_symbol(row.get("symbol"))
            price = number_or_zero(row.get("price"))
            if symbol and price > 0:
                quotes[symbol] = {
                    "symbol": symbol,
                    "shortName": row.get("name") or symbol,
                    "longName": row.get("name") or symbol,
                    "regularMarketPrice": price,
                    "regularMarketPreviousClose": number_or_zero(row.get("previousClose")),
                    "marketCap": number_or_zero(row.get("marketCap")),
                }
        return quotes
    except Exception:
        return {}


def fetch_yahoo_spark_quote(symbol: str, logger: MarketRequestLogger, limiter: MarketRequestLimiter) -> dict[str, Any]:
    quotes = fetch_yahoo_spark_quotes([symbol], logger, limiter)
    return quotes.get(normalize_symbol(symbol), {})


def fetch_yahoo_spark_quotes(
    symbols: list[str],
    logger: MarketRequestLogger,
    limiter: MarketRequestLimiter,
    bypass_limiter: bool = False,
) -> dict[str, dict[str, Any]]:
    symbols = [normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)]
    if not symbols:
        return {}
    try:
        batch_symbol = ",".join(symbols)
        limiter.wait("quote", bypass=bypass_limiter)
        with logger.track(batch_symbol, "quote", "yahoo_spark_api") as span:
            response = requests.get(
                YAHOO_SPARK_URL,
                params={"symbols": batch_symbol, "range": "5d", "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=12,
            )
            span.status_code = response.status_code
            response.raise_for_status()
        data = response.json()
        rows = data.get("spark", {}).get("result", [])
        quotes: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = normalize_symbol(row.get("symbol"))
            response_rows = row.get("response") or []
            payload = response_rows[0] if response_rows else {}
            meta = payload.get("meta", {})
            closes = payload.get("indicators", {}).get("quote", [{}])[0].get("close") or []
            close_values = [number_or_zero(close) for close in closes if number_or_zero(close) > 0]
            price = number_or_zero(meta.get("regularMarketPrice"))
            if price <= 0 and close_values:
                price = close_values[-1]
            if symbol and price > 0:
                quotes[symbol] = {
                    "symbol": symbol,
                    "shortName": meta.get("shortName") or symbol,
                    "longName": meta.get("longName") or meta.get("shortName") or symbol,
                    "regularMarketPrice": price,
                    "regularMarketPreviousClose": number_or_zero(meta.get("chartPreviousClose")),
                    "marketCap": number_or_zero(meta.get("marketCap")),
                }
        return quotes
    except Exception:
        return {}


def fetch_fmp_fundamentals(
    symbol: str,
    logger: MarketRequestLogger,
    limiter: MarketRequestLimiter,
) -> dict[str, Any]:
    api_key = provider_key("FMP_API_KEY")
    if not api_key:
        return {}
    symbol = normalize_symbol(symbol)
    try:
        profile = {}
        with logger.track(symbol, "fundamentals", "fmp_profile") as span:
            profile_response = requests.get(
                f"{FMP_STABLE_BASE_URL}/profile",
                params={"symbol": symbol, "apikey": api_key},
                timeout=12,
            )
            span.status_code = profile_response.status_code
            profile_response.raise_for_status()
        profile_rows = profile_response.json() or []
        if isinstance(profile_rows, list) and profile_rows:
            profile = profile_rows[0] or {}
        elif isinstance(profile_rows, dict):
            profile = profile_rows

        with logger.track(symbol, "fundamentals", "fmp_income_statement") as span:
            income_response = requests.get(
                f"{FMP_STABLE_BASE_URL}/income-statement",
                params={"symbol": symbol, "period": "FY", "limit": 5, "apikey": api_key},
                timeout=12,
            )
            span.status_code = income_response.status_code
            income_response.raise_for_status()
        income_rows = income_response.json() or []
        if not isinstance(income_rows, list) or not income_rows:
            return {}

        financials = fmp_income_statement_to_frame(income_rows)
        if financials.empty:
            return {}

        return {
            "name": profile.get("companyName") or profile.get("companyName") or symbol,
            "market_cap": number_or_zero(profile.get("mktCap") or profile.get("marketCap")),
            "inst_ownership": number_or_zero(
                profile.get("institutionalOwnership") or profile.get("heldPercentInstitutions")
            ),
            "financials": financials,
        }
    except Exception:
        return {}


def fmp_income_statement_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    values: dict[str, dict[pd.Timestamp, float]] = {
        "Total Revenue": {},
        "Net Income": {},
        "Gross Profit": {},
    }
    for row in rows:
        date_value = row.get("date") or row.get("calendarYear")
        try:
            column = pd.to_datetime(date_value)
        except Exception:
            year = row.get("calendarYear")
            if not year:
                continue
            column = pd.to_datetime(f"{year}-12-31")
        values["Total Revenue"][column] = number_or_zero(row.get("revenue"))
        values["Net Income"][column] = number_or_zero(row.get("netIncome"))
        values["Gross Profit"][column] = number_or_zero(row.get("grossProfit"))
    return pd.DataFrame(values).T


def fetch_finnhub_reported_fundamentals(
    symbol: str,
    logger: MarketRequestLogger,
    limiter: MarketRequestLimiter,
) -> dict[str, Any]:
    api_key = provider_key("FINNHUB_API_KEY")
    if not api_key:
        return {}
    symbol = normalize_symbol(symbol)
    try:
        with logger.track(symbol, "fundamentals", "finnhub_financials_reported") as span:
            response = requests.get(
                f"{FINNHUB_BASE_URL}/stock/financials-reported",
                params={"symbol": symbol, "freq": "annual", "token": api_key},
                timeout=20,
            )
            span.status_code = response.status_code
            response.raise_for_status()
        rows = (response.json() or {}).get("data") or []
        financials = finnhub_reported_to_frame(rows[:5])
        if financials.empty:
            return {}
        return {
            "name": "",
            "market_cap": 0,
            "inst_ownership": 0,
            "financials": financials,
        }
    except Exception:
        return {}


def finnhub_reported_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    values: dict[str, dict[pd.Timestamp, float]] = {
        "Total Revenue": {},
        "Net Income": {},
        "Gross Profit": {},
    }
    for row in rows:
        year = row.get("year")
        try:
            column = pd.to_datetime(f"{int(year)}-12-31")
        except Exception:
            continue
        income_items = ((row.get("report") or {}).get("ic") or [])
        revenue = reported_value(income_items, REVENUE_CONCEPTS, REVENUE_LABELS)
        net_income = reported_value(income_items, NET_INCOME_CONCEPTS, NET_INCOME_LABELS)
        gross_profit = reported_value(income_items, GROSS_PROFIT_CONCEPTS, GROSS_PROFIT_LABELS)
        if revenue is not None:
            values["Total Revenue"][column] = revenue
        if net_income is not None:
            values["Net Income"][column] = net_income
        if gross_profit is not None:
            values["Gross Profit"][column] = gross_profit
    return pd.DataFrame(values).T


REVENUE_CONCEPTS = {
    "us-gaap_revenues",
    "us-gaap_revenuefromcontractwithcustomerexcludingassessedtax",
    "us-gaap_revenuefromcontractwithcustomerincludingassessedtax",
    "ifrs-full_revenue",
}
REVENUE_LABELS = {"revenue", "total revenues", "net sales", "net revenue"}
NET_INCOME_CONCEPTS = {"us-gaap_netincomeloss", "us-gaap_profitloss", "ifrs-full_profitloss"}
NET_INCOME_LABELS = {"net income", "net earnings", "net loss", "profit loss"}
GROSS_PROFIT_CONCEPTS = {"us-gaap_grossprofit", "ifrs-full_grossprofit"}
GROSS_PROFIT_LABELS = {"gross profit", "gross margin"}


def reported_value(items: list[dict[str, Any]], concepts: set[str], labels: set[str]) -> float | None:
    for item in items:
        concept = str(item.get("concept") or "").lower()
        label = str(item.get("label") or "").lower()
        if concept in concepts or label in labels:
            return number_or_zero(item.get("value"))
    for item in items:
        concept = str(item.get("concept") or "").lower()
        label = str(item.get("label") or "").lower()
        if any(label == candidate or candidate in concept for candidate in labels):
            return number_or_zero(item.get("value"))
    return None


def fetch_quote_api(symbol: str, logger: MarketRequestLogger, limiter: MarketRequestLimiter) -> dict[str, Any]:
    quotes = fetch_quote_api_batch([symbol], logger, limiter)
    return quotes.get(symbol, {})


def fetch_quote_api_batch(
    symbols: list[str],
    logger: MarketRequestLogger,
    limiter: MarketRequestLimiter,
    bypass_limiter: bool = False,
) -> dict[str, dict[str, Any]]:
    global _batch_quote_blocked_until

    symbols = [normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)]
    if not symbols:
        return {}
    if time.time() < _batch_quote_blocked_until:
        return {}
    response = None
    try:
        batch_symbol = ",".join(symbols)
        limiter.wait("quote", bypass=bypass_limiter)
        with logger.track(batch_symbol, "quote", "yahoo_quote_api") as span:
            response = requests.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": batch_symbol},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=12,
            )
            span.status_code = response.status_code
            response.raise_for_status()
        data = response.json()
        quote = data.get("quoteResponse", {}).get("result", [])
        return {normalize_symbol(row.get("symbol")): dict(row) for row in quote if row.get("symbol")}
    except Exception:
        if response is not None and response.status_code in {401, 403, 429}:
            _batch_quote_blocked_until = time.time() + QUOTE_SUMMARY_BACKOFF_SECONDS
        return {}


def fetch_history_api(symbol: str, logger: MarketRequestLogger, limiter: MarketRequestLimiter) -> pd.DataFrame:
    try:
        limiter.wait("history")
        with logger.track(symbol, "history", "yahoo_chart_api") as span:
            response = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"range": "6y", "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            span.status_code = response.status_code
            response.raise_for_status()
        data = response.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        timestamps = result.get("timestamp") or []
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
        rows = []
        for ts, close in zip(timestamps, closes):
            close_value = number_or_zero(close)
            if not ts or close_value <= 0:
                continue
            rows.append({"Date": datetime.fromtimestamp(ts, timezone.utc), "Close": close_value})
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index("Date")
    except Exception:
        return pd.DataFrame()


def fetch_chart_quote_api(
    symbol: str,
    logger: MarketRequestLogger,
    limiter: MarketRequestLimiter,
) -> dict[str, Any]:
    try:
        limiter.wait("quote")
        with logger.track(symbol, "quote", "yahoo_chart_quote_api") as span:
            response = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"range": "5d", "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=12,
            )
            span.status_code = response.status_code
            response.raise_for_status()
        data = response.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        timestamps = result.get("timestamp") or []
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
        price = number_or_zero(meta.get("regularMarketPrice"))
        if price <= 0:
            close_values = [number_or_zero(close) for close in closes if number_or_zero(close) > 0]
            price = close_values[-1] if close_values else 0.0
        regular_time = meta.get("regularMarketTime")
        return {
            "symbol": symbol,
            "regularMarketPrice": price,
            "regularMarketTime": regular_time or (timestamps[-1] if timestamps else None),
            "shortName": meta.get("shortName") or symbol,
        }
    except Exception:
        return {}


def safe_fast_info(stock: yf.Ticker) -> dict[str, Any]:
    try:
        fast_info = stock.fast_info
        if not fast_info:
            return {}
        return {
            "last_price": mapping_value(fast_info, "last_price"),
            "previous_close": mapping_value(fast_info, "previous_close"),
        }
    except Exception:
        return {}


def mapping_value(value: Any, key: str) -> Any:
    try:
        if hasattr(value, "get"):
            return value.get(key)
        return value[key]
    except Exception:
        return None


def extract_close_baselines(history: pd.DataFrame) -> dict[str, float | None]:
    baselines: dict[str, float | None] = {}
    for key, days in TRADING_DAY_OFFSETS.items():
        if history is not None and not history.empty and len(history) > days:
            baselines[key] = number_or_zero(history["Close"].iloc[-days])
        else:
            baselines[key] = None
    return baselines


def history_to_records(history: pd.DataFrame) -> list[dict[str, Any]]:
    if history is None or history.empty or "Close" not in history.columns:
        return []
    chart_df = history[["Close"]].reset_index()
    date_col = "Date" if "Date" in chart_df.columns else chart_df.columns[0]
    chart_df = chart_df.rename(columns={date_col: "date", "Close": "close"})
    chart_df["date"] = pd.to_datetime(chart_df["date"]).dt.strftime("%Y-%m-%d")
    chart_df["close"] = chart_df["close"].map(lambda value: number_or_zero(value))
    return chart_df.to_dict("records")


def latest_close(history: pd.DataFrame) -> float:
    if history is None or history.empty or "Close" not in history.columns:
        return 0.0
    close_values = history["Close"].dropna()
    if close_values.empty:
        return 0.0
    return number_or_zero(close_values.iloc[-1])


def extract_year_values(series: pd.Series, limit: int = 5) -> list[tuple[int, float]]:
    if series is None or len(series) == 0:
        return []
    latest_allowed_year = datetime.now(timezone.utc).year - 1
    values: list[tuple[int, float]] = []
    for idx, raw_value in series.items():
        year = getattr(idx, "year", None)
        if year is None:
            try:
                year = pd.to_datetime(idx).year
            except Exception:
                year = None
        value = number_or_zero(raw_value)
        if year and year <= latest_allowed_year and value:
            values.append((int(year), value))
    values.sort(key=lambda item: item[0], reverse=True)
    return values[:limit]


def extract_fundamental_fields(financials: pd.DataFrame) -> dict[str, Any]:
    revenue_values: list[tuple[int, float]] = []
    profit_values: list[tuple[int, float]] = []
    if financials is not None and not financials.empty:
        if "Total Revenue" in financials.index:
            revenue_values = extract_year_values(financials.loc["Total Revenue"])
        profit_label = next((label for label in ["Net Income", "Gross Profit"] if label in financials.index), None)
        if profit_label:
            profit_values = extract_year_values(financials.loc[profit_label])

    revenue_growth = (
        len(revenue_values) >= 4
        and revenue_values[0][1] > revenue_values[1][1] > revenue_values[2][1] > revenue_values[3][1]
    )
    profit_growth = (
        len(profit_values) >= 4
        and profit_values[0][1] > profit_values[1][1] > profit_values[2][1] > profit_values[3][1]
    )
    fields: dict[str, Any] = {
        "revenue_status": "Growth" if revenue_growth else "Nope",
        "profit_status": "Growth" if profit_growth else "Nope",
    }
    for idx in range(5):
        fields[f"revenue_year_{idx + 1}_label"] = revenue_values[idx][0] if idx < len(revenue_values) else None
        fields[f"revenue_year_{idx + 1}_value"] = revenue_values[idx][1] if idx < len(revenue_values) else None
        fields[f"profit_year_{idx + 1}_label"] = profit_values[idx][0] if idx < len(profit_values) else None
        fields[f"profit_year_{idx + 1}_value"] = profit_values[idx][1] if idx < len(profit_values) else None
    return fields


def recalc_performance(snapshot: dict[str, Any]) -> dict[str, Any]:
    price = number_or_zero(snapshot.get("price"))
    for perf_key, baseline_key in PERIOD_BASELINES.items():
        baseline = number_or_zero(snapshot.get(baseline_key))
        snapshot[perf_key] = ((price - baseline) / baseline) * 100 if price > 0 and baseline > 0 else 0.0
    snapshot["green_charts"] = (
        "Yes"
        if snapshot["perf_5y"] > 0 and snapshot["perf_1y"] > 0 and snapshot["perf_3m"] > 0
        else "No"
    )
    return snapshot


def snapshot_status(snapshot: dict[str, Any]) -> str:
    if snapshot.get("last_error"):
        return "partial"
    if (
        snapshot.get("quote_status") == "complete"
        and snapshot.get("history_status") == "complete"
        and snapshot.get("fundamentals_status") == "complete"
    ):
        return "complete"
    return "partial"
