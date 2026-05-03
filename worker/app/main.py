from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .market_debug import MarketRequestLogger
from .market_data import (
    batch_quote_snapshots,
    fetch_snapshot,
    fetch_recent_intraday_bars,
    normalize_symbol,
)
from .market_policy import (
    FIELD_FUNDAMENTALS,
    FIELD_HISTORY,
    FIELD_PRICE,
    market_policy_now,
)
from .rate_limit import MarketRequestLimiter
from .settings import get_settings
from .snapshot_rules import (
    add_incomplete_reason as add_incomplete_reason_rule,
    add_snapshot_complete as add_snapshot_complete_rule,
    add_snapshot_fresh as add_snapshot_fresh_rule,
    add_snapshot_usable as add_snapshot_usable_rule,
    annual_fundamentals_missing as annual_fundamentals_missing_rule,
    due_layers_for_visible as due_layers_for_visible_rule,
    is_layer_due as is_layer_due_rule,
    parse_datetime,
)
from .supabase_db import (
    create_refresh_job,
    get_snapshot,
    get_job,
    get_user_from_token,
    insert_market_request_logs,
    make_service_client,
    mark_job,
    mark_symbol_failed,
    upsert_watchlist_activity,
    upsert_snapshot,
)
from .use_cases import (
    add_ticker_use_case,
    ensure_complete_snapshot_for_add,
    refresh_smart_visible_symbols_use_case,
    refresh_visible_missing_fundamentals_use_case,
)


settings = get_settings()
service_client = make_service_client(settings)

app = FastAPI(title="Stock Analyzer Worker", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

SYMBOL_RE = re.compile(r"^[A-Z0-9.-]{1,12}$")
MAX_SYMBOLS_PER_JOB = 30


class RefreshRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    watchlist_name: str | None = None
    mode: str = "visible_quote"
    layers: list[str] = Field(default_factory=list)


class RefreshResponse(BaseModel):
    ok: bool
    job_id: str
    status: str
    symbols: list[str]
    message: str | None = None


class ActivityRequest(BaseModel):
    watchlists: list[str] = Field(default_factory=list)
    active_watchlist: str | None = None


class ActivityResponse(BaseModel):
    ok: bool
    tracked_watchlists: int


class AddTickerRequest(BaseModel):
    symbol: str
    watchlist_name: str


class AddTickerResponse(BaseModel):
    ok: bool
    symbol: str
    name: str
    message: str | None = None


class IntradayChartResponse(BaseModel):
    ok: bool
    symbol: str
    interval_minutes: int
    bars: list[dict[str, Any]]


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return token


def current_user(token: Annotated[str, Depends(bearer_token)]) -> dict:
    return get_user_from_token(settings, token)


@app.get("/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


@app.post("/refresh", response_model=RefreshResponse)
def refresh(
    request: RefreshRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[dict, Depends(current_user)],
) -> RefreshResponse:
    symbols = clean_symbols(request.symbols)
    if not symbols:
        raise HTTPException(status_code=400, detail="No valid symbols supplied.")

    if request.mode == "initial" and len(symbols) == 1:
        symbol = symbols[0]
        existing = get_snapshot(service_client, symbol) or {}
        if add_snapshot_usable_rule(existing, settings):
            job = create_refresh_job(
                service_client,
                user_id=user["id"],
                email=user.get("email"),
                symbols=[symbol],
                watchlist_name=request.watchlist_name,
            )
            try:
                mark_job(service_client, job["id"], "done")
            except Exception as exc:
                print(f"Could not mark job {job['id']} done: {exc}")
            return RefreshResponse(
                ok=True,
                job_id=job["id"],
                status="done",
                symbols=[symbol],
                message=f"Using current cached snapshot for {symbol}.",
            )

    if request.mode in {"smart_visible", "visible_smart"}:
        plan = smart_visible_plan(symbols)
        due_symbols = unique_symbols(
            plan["quote_only_symbols"]
            + plan["history_symbols"]
            + plan["fundamentals_symbols"]
            + plan["combined_symbols"]
        )
        if not due_symbols:
            job = create_refresh_job(
                service_client,
                user_id=user["id"],
                email=user.get("email"),
                symbols=[],
                watchlist_name=request.watchlist_name,
            )
            try:
                mark_job(service_client, job["id"], "done")
            except Exception as exc:
                print(f"Could not mark job {job['id']} done: {exc}")
            return RefreshResponse(
                ok=True,
                job_id=job["id"],
                status="done",
                symbols=[],
                message="Prices were refreshed recently. The visible list uses a 15 minute price window.",
            )

        job = create_refresh_job(
            service_client,
            user_id=user["id"],
            email=user.get("email"),
            symbols=due_symbols,
            watchlist_name=request.watchlist_name,
        )
        background_tasks.add_task(process_job, job["id"], due_symbols, "smart_visible", [])
        return RefreshResponse(
            ok=True,
            job_id=job["id"],
            status="queued",
            symbols=due_symbols,
            message=f"Refreshing {len(due_symbols)} ticker(s) that are due.",
        )

    job = create_refresh_job(
        service_client,
        user_id=user["id"],
        email=user.get("email"),
        symbols=symbols,
        watchlist_name=request.watchlist_name,
    )
    layers = clean_layers(request.layers, request.mode)
    background_tasks.add_task(process_job, job["id"], symbols, request.mode, layers)

    return RefreshResponse(ok=True, job_id=job["id"], status="queued", symbols=symbols)


@app.get("/jobs/{job_id}")
def job_status(job_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    try:
        job = get_job(service_client, job_id, user_id=user["id"])
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not read refresh job status. Retry shortly.") from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"ok": True, "job": job}


@app.post("/activity", response_model=ActivityResponse)
def record_activity(
    request: ActivityRequest,
    user: Annotated[dict, Depends(current_user)],
) -> ActivityResponse:
    watchlists = clean_watchlist_names(request.watchlists)
    active_watchlist = str(request.active_watchlist or "").strip() or None
    if active_watchlist and active_watchlist not in watchlists:
        watchlists.append(active_watchlist)
    upsert_watchlist_activity(service_client, user["id"], watchlists, active_watchlist)
    return ActivityResponse(ok=True, tracked_watchlists=len(watchlists))


@app.post("/add-ticker", response_model=AddTickerResponse)
def add_ticker(
    request: AddTickerRequest,
    user: Annotated[dict, Depends(current_user)],
) -> AddTickerResponse:
    symbol = normalize_symbol(request.symbol)
    watchlist_name = str(request.watchlist_name or "").strip()
    if not symbol or not SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol.")
    if not watchlist_name:
        raise HTTPException(status_code=400, detail="Missing watchlist name.")
    logger = MarketRequestLogger(enabled=settings.debug_market_requests, job_id=str(uuid4()))
    limiter = MarketRequestLimiter(
        enabled=settings.enable_request_limiter,
        quote_min_interval_ms=settings.quote_min_interval_ms,
        history_min_interval_ms=settings.history_min_interval_ms,
        fundamentals_min_interval_ms=0,
    )
    try:
        snapshot = add_ticker_use_case(
            service_client,
            settings,
            user["id"],
            watchlist_name,
            symbol,
            logger,
            limiter,
        )
    except HTTPException:
        raise
    except Exception as exc:
        persisted = get_snapshot(service_client, symbol) or {}
        detail = str(exc).strip() or add_incomplete_reason_rule(persisted, settings)
        print(f"add_ticker failed for {symbol}: {detail}")
        raise HTTPException(status_code=400, detail=f"Could not fully fetch {symbol}: {detail}") from exc
    finally:
        try:
            insert_market_request_logs(service_client, logger.events)
        except Exception as log_exc:
            print(f"Could not write market request logs for add-ticker {symbol}: {log_exc}")

    return AddTickerResponse(ok=True, symbol=symbol, name=str(snapshot.get("name") or symbol), message=f"Added {symbol}.")


@app.get("/chart/{symbol}/intraday", response_model=IntradayChartResponse)
def intraday_chart(
    symbol: str,
    user: Annotated[dict, Depends(current_user)],
    interval_minutes: int = 5,
) -> IntradayChartResponse:
    clean_symbol = normalize_symbol(symbol)
    if not clean_symbol or not SYMBOL_RE.match(clean_symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol.")
    interval = max(1, min(int(interval_minutes or 5), 60))
    logger = MarketRequestLogger(enabled=False)
    limiter = MarketRequestLimiter(
        enabled=settings.enable_request_limiter,
        quote_min_interval_ms=settings.quote_min_interval_ms,
        history_min_interval_ms=settings.history_min_interval_ms,
        fundamentals_min_interval_ms=settings.fundamentals_min_interval_ms,
    )
    bars = fetch_recent_intraday_bars(clean_symbol, interval, logger, limiter, range_value="1d")
    return IntradayChartResponse(ok=True, symbol=clean_symbol, interval_minutes=interval, bars=bars)


def clean_symbols(raw_symbols: list[str]) -> list[str]:
    symbols: list[str] = []
    seen = set()
    for raw in raw_symbols:
        symbol = normalize_symbol(raw)
        if not symbol or not SYMBOL_RE.match(symbol) or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
        if len(symbols) >= MAX_SYMBOLS_PER_JOB:
            break
    return symbols


def clean_layers(raw_layers: list[str], mode: str) -> list[str]:
    allowed = {"quote", "history", "fundamentals"}
    layers = [layer for layer in raw_layers if layer in allowed]
    if layers:
        return layers
    if mode == "initial":
        return ["quote", "history", "fundamentals"]
    if mode == "initial_core":
        return ["quote", "history"]
    if mode == "fundamentals":
        return ["fundamentals"]
    if mode in {"visible_quote", "visible_quote_initial", "visible_quote_scheduled"}:
        return ["quote"]
    if mode == "visible_full":
        return ["quote", "history", "fundamentals"]
    return ["quote"]


def clean_watchlist_names(raw_names: list[str]) -> list[str]:
    names: list[str] = []
    seen = set()
    for raw in raw_names:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def smart_visible_plan(symbols: list[str]) -> dict[str, list[str]]:
    market_policy = market_policy_now(settings)
    quote_only_symbols: list[str] = []
    history_symbols: list[str] = []
    fundamentals_symbols: list[str] = []
    combined_symbols: list[str] = []
    current_symbols: list[str] = []

    for symbol in symbols:
        snapshot = get_snapshot(service_client, symbol) or {}
        layers = due_layers_for_visible(snapshot, market_policy.mode, market_policy.now)
        if not layers:
            current_symbols.append(symbol)
            continue
        if layers == [FIELD_PRICE]:
            quote_only_symbols.append(symbol)
        elif layers == [FIELD_HISTORY]:
            history_symbols.append(symbol)
        elif layers == [FIELD_FUNDAMENTALS]:
            fundamentals_symbols.append(symbol)
        else:
            combined_symbols.append(symbol)

    return {
        "quote_only_symbols": quote_only_symbols,
        "history_symbols": history_symbols,
        "fundamentals_symbols": fundamentals_symbols,
        "combined_symbols": combined_symbols,
        "current_symbols": current_symbols,
    }


def has_positive_price(snapshot: dict[str, Any]) -> bool:
    try:
        return float(snapshot.get("price") or 0) > 0
    except Exception:
        return False


def has_positive_ownership(snapshot: dict[str, Any]) -> bool:
    try:
        return float(snapshot.get("inst_ownership") or 0) > 0
    except Exception:
        return False


def unique_symbols(symbols: list[str]) -> list[str]:
    return list(dict.fromkeys(symbols))


def due_layers_for_visible(snapshot: dict[str, Any], mode: str, now: datetime) -> list[str]:
    return due_layers_for_visible_rule(snapshot, settings, now)


def is_layer_due(snapshot: dict[str, Any], field: str, mode: str, now: datetime) -> bool:
    return is_layer_due_rule(snapshot, field, settings, now)


def annual_fundamentals_missing(snapshot: dict[str, Any]) -> bool:
    return annual_fundamentals_missing_rule(snapshot, settings)


def is_positive_number(value: Any) -> bool:
    try:
        return float(value or 0) > 0
    except Exception:
        return False


def annual_series_has_year(snapshot: dict[str, Any], prefix: str, target_year: int) -> bool:
    for idx in range(1, 6):
        label = snapshot.get(f"{prefix}_year_{idx}_label")
        value = snapshot.get(f"{prefix}_year_{idx}_value")
        if label is None or value is None:
            continue
        try:
            if int(label) != int(target_year):
                continue
        except Exception:
            continue
        return True
    return False


def initial_snapshot_ready(snapshot: dict[str, Any]) -> bool:
    return add_snapshot_usable_rule(snapshot, settings)


def initial_incomplete_reason(snapshot: dict[str, Any]) -> str:
    return add_incomplete_reason_rule(snapshot, settings)


def add_snapshot_complete(snapshot: dict[str, Any]) -> bool:
    return add_snapshot_complete_rule(snapshot, settings)


def add_snapshot_fresh(snapshot: dict[str, Any]) -> bool:
    return add_snapshot_fresh_rule(snapshot, settings)


def add_snapshot_usable(snapshot: dict[str, Any]) -> bool:
    return add_snapshot_usable_rule(snapshot, settings)


def add_incomplete_reason(snapshot: dict[str, Any]) -> str:
    return add_incomplete_reason_rule(snapshot, settings)


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def process_job(job_id: str, symbols: list[str], mode: str, layers: list[str]) -> None:
    logger = MarketRequestLogger(enabled=settings.debug_market_requests, job_id=job_id)
    limiter = MarketRequestLimiter(
        enabled=settings.enable_request_limiter,
        quote_min_interval_ms=settings.quote_min_interval_ms,
        history_min_interval_ms=settings.history_min_interval_ms,
        fundamentals_min_interval_ms=settings.fundamentals_min_interval_ms,
    )
    try:
        mark_job(service_client, job_id, "running")
    except Exception as exc:
        print(f"Could not mark job {job_id} running: {exc}")

    failures: list[str] = []

    if mode == "smart_visible":
        refresh_smart_visible_symbols(job_id, symbols, logger, limiter, failures)
    elif mode == "initial" and len(symbols) == 1:
        symbol = symbols[0]
        try:
            ensure_complete_snapshot_for_add(service_client, settings, symbol, logger, limiter)
        except Exception as exc:
            message = str(exc)
            failures.append(f"{symbol}: {message}")
            try:
                mark_symbol_failed(service_client, symbol, message)
            except Exception as mark_exc:
                failures.append(f"{symbol}: could not record failure: {mark_exc}")
    elif layers == ["quote"] and len(symbols) > 1:
        try:
            existing = {symbol: get_snapshot(service_client, symbol) or {} for symbol in symbols}
            fallback_spacing_seconds = 4.0 if mode == "visible_quote_scheduled" else 0.0
            for snapshot in batch_quote_snapshots(
                symbols,
                existing,
                logger,
                limiter,
                fast_lane=settings.enable_quote_fast_lane,
                fallback_spacing_seconds=fallback_spacing_seconds,
            ):
                if snapshot.get("quote_status") == "error":
                    failures.append(f"{snapshot['symbol']}: {snapshot.get('quote_last_error', 'quote failed')}")
                upsert_snapshot(service_client, snapshot)
        except Exception as exc:
            failures.append(f"batch quote: {exc}")
    else:
        for symbol in symbols:
            try:
                snapshot = fetch_snapshot(symbol, layers=layers, logger=logger, limiter=limiter)
                upsert_snapshot(service_client, snapshot)
            except Exception as exc:
                message = str(exc)
                failures.append(f"{symbol}: {message}")
                try:
                    mark_symbol_failed(service_client, symbol, message)
                except Exception as mark_exc:
                    failures.append(f"{symbol}: could not record failure: {mark_exc}")

    try:
        insert_market_request_logs(service_client, logger.events)
    except Exception as exc:
        print(f"Could not write market request logs for job {job_id}: {exc}")

    try:
        if not failures:
            mark_job(service_client, job_id, "done")
        elif len(failures) >= len(symbols):
            mark_job(service_client, job_id, "failed", "; ".join(failures))
        else:
            mark_job(service_client, job_id, "partial", "; ".join(failures))
    except Exception as exc:
        print(f"Could not mark job {job_id} complete: {exc}")


def refresh_smart_visible_symbols(
    job_id: str,
    symbols: list[str],
    logger: MarketRequestLogger,
    limiter: MarketRequestLimiter,
    failures: list[str],
) -> None:
    refresh_smart_visible_symbols_use_case(service_client, settings, symbols, logger, limiter, failures)


def refresh_visible_missing_fundamentals(
    symbol: str,
    logger: MarketRequestLogger,
    limiter: MarketRequestLimiter,
    failures: list[str],
) -> None:
    refresh_visible_missing_fundamentals_use_case(service_client, settings, symbol, logger, limiter)


def merge_visible_fundamentals(existing: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    merged = {**existing}
    for key, value in payload.items():
        if value is None:
            continue
        merged[key] = value
    return merged

