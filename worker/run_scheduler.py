from __future__ import annotations

import time
from datetime import datetime
from uuid import uuid4

from app.main import (
    due_layers_for_visible,
    get_snapshot,
    refresh_smart_visible_symbols,
    service_client,
    settings,
)
from app.market_debug import MarketRequestLogger
from app.market_policy import FIELD_PRICE, MARKET_CLOSED_WEEKDAY, MARKET_CLOSED_WEEKEND, market_policy_now
from app.rate_limit import MarketRequestLimiter
from app.supabase_db import execute_with_retry
from app.supabase_db import insert_market_request_logs


def main() -> int:
    interval = max(15, settings.scheduler_interval_seconds)
    watchlist_batch_size = max(1, settings.scheduler_watchlist_batch_size)
    universe_batch_size = max(1, settings.scheduler_universe_batch_size)

    print("Background scheduler started")
    print(f"interval_seconds: {interval}")
    print(f"watchlist_batch_size: {watchlist_batch_size}")
    print(f"universe_batch_size: {universe_batch_size}")
    print("")

    while True:
        started = time.time()
        try:
            run_cycle(watchlist_batch_size, universe_batch_size)
        except KeyboardInterrupt:
            print("Scheduler stopped.")
            return 0
        except Exception as exc:
            print(f"scheduler cycle failed: {exc}")

        elapsed = time.time() - started
        sleep_seconds = max(5.0, interval - elapsed)
        time.sleep(sleep_seconds)


def run_cycle(watchlist_batch_size: int, universe_batch_size: int) -> None:
    policy = market_policy_now(settings)
    watchlist_symbols = load_watchlist_symbols()
    universe_symbols = [symbol for symbol in load_universe_symbols() if symbol not in set(watchlist_symbols)]

    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"mode={policy.mode} watchlist_symbols={len(watchlist_symbols)} universe_symbols={len(universe_symbols)}"
    )

    watchlist_due = due_symbols(watchlist_symbols, policy.mode, include_after_hours_prices=True)
    if watchlist_due:
        process_symbols("watchlists", watchlist_due[:watchlist_batch_size])

    if policy.mode in {MARKET_CLOSED_WEEKDAY, MARKET_CLOSED_WEEKEND}:
        universe_due = due_symbols(universe_symbols, policy.mode, include_after_hours_prices=False)
        if universe_due:
            process_symbols("universe", universe_due[:universe_batch_size])


def process_symbols(label: str, symbols: list[str]) -> None:
    logger = MarketRequestLogger(enabled=settings.debug_market_requests, job_id=str(uuid4()))
    limiter = MarketRequestLimiter(
        enabled=settings.enable_request_limiter,
        quote_min_interval_ms=settings.quote_min_interval_ms,
        history_min_interval_ms=settings.history_min_interval_ms,
        fundamentals_min_interval_ms=settings.fundamentals_min_interval_ms,
    )
    failures: list[str] = []
    refresh_smart_visible_symbols(f"scheduler-{label}", symbols, logger, limiter, failures)
    if logger.events:
        insert_market_request_logs(service_client, logger.events)
    if failures:
        print(f"  {label}: refreshed={len(symbols)} failures={len(failures)}")
        for failure in failures[:10]:
            print(f"    {failure}")
    else:
        print(f"  {label}: refreshed={len(symbols)} failures=0")


def due_symbols(symbols: list[str], mode: str, include_after_hours_prices: bool) -> list[str]:
    now = market_policy_now(settings).now
    ranked: list[tuple[int, str]] = []
    for symbol in symbols:
        snapshot = get_snapshot(service_client, symbol) or {}
        layers = due_layers_for_visible(snapshot, mode, now)
        if not include_after_hours_prices and mode in {MARKET_CLOSED_WEEKDAY, MARKET_CLOSED_WEEKEND}:
            layers = [layer for layer in layers if layer != FIELD_PRICE]
        if not layers:
            continue
        ranked.append((layer_priority(layers), symbol))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [symbol for _score, symbol in ranked]


def layer_priority(layers: list[str]) -> int:
    score = 0
    if "fundamentals" in layers:
        score += 4
    if "history" in layers:
        score += 2
    if "price" in layers:
        score += 1
    return score


def load_watchlist_symbols() -> list[str]:
    result = execute_with_retry(lambda: service_client.table("watchlists").select("ticker_symbol").execute())
    seen = set()
    symbols: list[str] = []
    for row in result.data or []:
        symbol = str(row.get("ticker_symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def load_universe_symbols() -> list[str]:
    result = execute_with_retry(lambda: service_client.table("stock_universes").select("symbol").execute())
    seen = set()
    symbols: list[str] = []
    for row in result.data or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


if __name__ == "__main__":
    raise SystemExit(main())
