from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException

from .market_data import batch_quote_snapshots, fetch_full_snapshot_for_add, fetch_snapshot, fetch_snapshot_for_add
from .market_policy import FIELD_FUNDAMENTALS, FIELD_HISTORY, FIELD_PRICE
from .settings import Settings
from .snapshot_rules import (
    add_incomplete_reason,
    add_snapshot_fresh,
    add_snapshot_usable,
    due_layers_for_visible,
    has_history,
    has_positive_ownership,
    has_positive_price,
)
from .supabase_db import get_snapshot, mark_symbol_failed, upsert_snapshot


SnapshotFetcher = Callable[..., dict[str, Any]]


def ensure_complete_snapshot_for_add(
    client,
    settings: Settings,
    symbol: str,
    logger,
    limiter,
    fetcher: SnapshotFetcher = fetch_full_snapshot_for_add,
) -> dict[str, Any]:
    existing = get_snapshot(client, symbol) or {}
    if add_snapshot_usable(existing, settings):
        return existing

    fetched = fetcher(symbol, logger, limiter)
    upsert_snapshot(client, fetched)
    persisted = get_snapshot(client, symbol) or {}
    if not add_snapshot_usable(persisted, settings):
        raise ValueError(add_incomplete_reason(persisted, settings))
    return persisted


def ensure_snapshot_for_add_or_partial(
    client,
    settings: Settings,
    symbol: str,
    logger,
    limiter,
    fetcher: SnapshotFetcher = fetch_snapshot_for_add,
) -> dict[str, Any]:
    existing = get_snapshot(client, symbol) or {}
    if add_snapshot_usable(existing, settings) or partial_add_snapshot_usable(existing, settings):
        return existing

    fetched = fetcher(symbol, logger, limiter)
    if not partial_add_snapshot_has_required_market_data(fetched):
        raise ValueError(add_incomplete_reason(fetched, settings))

    if add_snapshot_usable(fetched, settings):
        fetched["snapshot_status"] = "complete"
        fetched["last_error"] = None
    elif partial_add_snapshot_has_some_fundamentals(fetched):
        fetched["snapshot_status"] = "partial"
        fetched["last_error"] = add_incomplete_reason(fetched, settings)
    else:
        fetched["fundamentals_status"] = "missing"
        fetched["snapshot_status"] = "partial"
        fetched["last_error"] = "missing fundamentals"

    upsert_snapshot(client, fetched)

    persisted = get_snapshot(client, symbol) or fetched
    if not partial_add_snapshot_has_required_market_data(persisted):
        raise ValueError(add_incomplete_reason(persisted, settings))
    return persisted


def partial_add_snapshot_usable(snapshot: dict[str, Any], settings: Settings) -> bool:
    return (
        partial_add_snapshot_has_required_market_data(snapshot)
        and partial_add_snapshot_has_some_fundamentals(snapshot)
        and add_snapshot_fresh(snapshot, settings)
    )


def partial_add_snapshot_has_required_market_data(snapshot: dict[str, Any]) -> bool:
    return has_positive_price(snapshot) and has_history(snapshot)


def partial_add_snapshot_has_some_fundamentals(snapshot: dict[str, Any]) -> bool:
    return has_positive_ownership(snapshot) or any(
        snapshot.get(f"{prefix}_year_{idx}_label") is not None
        and snapshot.get(f"{prefix}_year_{idx}_value") is not None
        for prefix in ("revenue", "profit")
        for idx in range(1, 6)
    )


def ensure_not_duplicate_watchlist_entry(client, user_id: str, watchlist_name: str, symbol: str) -> None:
    result = (
        client.table("watchlists")
        .select("ticker_symbol")
        .eq("user_id", user_id)
        .eq("watchlist_name", watchlist_name)
        .eq("ticker_symbol", symbol)
        .maybe_single()
        .execute()
    )
    duplicate = getattr(result, "data", None) if result is not None else None
    if duplicate:
        raise HTTPException(status_code=409, detail=f"{symbol} is already in {watchlist_name}.")


def insert_watchlist_entry(client, user_id: str, watchlist_name: str, symbol: str) -> None:
    result = (
        client.table("watchlists")
        .insert(
            {
                "user_id": user_id,
                "ticker_symbol": symbol,
                "comment": "",
                "watchlist_name": watchlist_name,
            }
        )
        .execute()
    )
    if not (getattr(result, "data", None) or []):
        raise RuntimeError("Ticker insert failed.")


def add_ticker_use_case(
    client,
    settings: Settings,
    user_id: str,
    watchlist_name: str,
    symbol: str,
    logger,
    limiter,
) -> dict[str, Any]:
    ensure_not_duplicate_watchlist_entry(client, user_id, watchlist_name, symbol)
    snapshot = ensure_snapshot_for_add_or_partial(client, settings, symbol, logger, limiter)
    insert_watchlist_entry(client, user_id, watchlist_name, symbol)
    return snapshot


def refresh_visible_fundamentals_use_case(client, settings: Settings, symbol: str, logger, limiter) -> None:
    existing = get_snapshot(client, symbol) or {"symbol": symbol}
    fundamentals_snapshot = fetch_snapshot(
        symbol,
        ["fundamentals"],
        logger=logger,
        limiter=limiter,
        force_fundamentals_fallbacks=True,
        allow_yfinance_fundamentals=False,
    )
    merged = {**existing, **fundamentals_snapshot}
    upsert_snapshot(client, merged)


def refresh_visible_missing_fundamentals_use_case(client, settings: Settings, symbol: str, logger, limiter) -> None:
    existing = get_snapshot(client, symbol) or {"symbol": symbol}
    fundamentals_snapshot = fetch_snapshot(
        symbol,
        ["fundamentals"],
        logger=logger,
        limiter=limiter,
        force_fundamentals_fallbacks=True,
        allow_yfinance_fundamentals=False,
    )
    if fundamentals_snapshot.get("fundamentals_status") != "complete":
        raise ValueError("No complete annual fundamentals returned by configured providers")
    merged = {**existing, **fundamentals_snapshot}
    upsert_snapshot(client, merged)


def refresh_symbol_layers_use_case(client, settings: Settings, symbol: str, layers: list[str], logger, limiter) -> None:
    snapshot = fetch_snapshot(symbol, layers=layers, logger=logger, limiter=limiter)
    upsert_snapshot(client, snapshot)


def refresh_smart_visible_symbols_use_case(
    client,
    settings: Settings,
    symbols: list[str],
    logger,
    limiter,
    failures: list[str],
) -> None:
    quote_only_symbols: list[str] = []
    history_symbols: list[str] = []
    fundamentals_symbols: list[str] = []
    combined_symbols: list[str] = []

    for symbol in symbols:
        snapshot = get_snapshot(client, symbol) or {}
        layers = due_layers_for_visible(snapshot, settings)
        if not layers:
            continue
        if layers == [FIELD_PRICE]:
            quote_only_symbols.append(symbol)
        elif layers == [FIELD_HISTORY]:
            history_symbols.append(symbol)
        elif layers == [FIELD_FUNDAMENTALS]:
            fundamentals_symbols.append(symbol)
        else:
            combined_symbols.append(symbol)

    if quote_only_symbols:
        try:
            existing = {symbol: get_snapshot(client, symbol) or {} for symbol in quote_only_symbols}
            for snapshot in batch_quote_snapshots(
                quote_only_symbols,
                existing,
                logger,
                limiter,
                fast_lane=settings.enable_quote_fast_lane,
                fallback_spacing_seconds=0.0,
            ):
                if snapshot.get("quote_status") == "error":
                    failures.append(f"{snapshot['symbol']}: {snapshot.get('quote_last_error', 'quote failed')}")
                upsert_snapshot(client, snapshot)
        except Exception as exc:
            failures.append(f"batch quote: {exc}")

    for symbol in history_symbols:
        try:
            refresh_symbol_layers_use_case(client, settings, symbol, [FIELD_HISTORY], logger, limiter)
        except Exception as exc:
            message = str(exc)
            failures.append(f"{symbol}: {message}")
            _record_failure(client, symbol, message, failures)

    for symbol in fundamentals_symbols:
        try:
            refresh_visible_fundamentals_use_case(client, settings, symbol, logger, limiter)
        except Exception as exc:
            message = str(exc)
            failures.append(f"{symbol}: {message}")
            _record_failure(client, symbol, message, failures)

    for symbol in combined_symbols:
        snapshot = get_snapshot(client, symbol) or {}
        layers = due_layers_for_visible(snapshot, settings)
        non_fund_layers = [layer for layer in layers if layer != FIELD_FUNDAMENTALS]
        try:
            if non_fund_layers:
                refresh_symbol_layers_use_case(client, settings, symbol, non_fund_layers, logger, limiter)
            if FIELD_FUNDAMENTALS in layers:
                refresh_visible_fundamentals_use_case(client, settings, symbol, logger, limiter)
        except Exception as exc:
            message = str(exc)
            failures.append(f"{symbol}: {message}")
            _record_failure(client, symbol, message, failures)


def _record_failure(client, symbol: str, message: str, failures: list[str]) -> None:
    try:
        mark_symbol_failed(client, symbol, message)
    except Exception as mark_exc:
        failures.append(f"{symbol}: could not record failure: {mark_exc}")
