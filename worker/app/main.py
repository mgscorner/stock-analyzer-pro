from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .market_debug import MarketRequestLogger
from .market_data import batch_quote_snapshots, fetch_snapshot, normalize_symbol
from .rate_limit import MarketRequestLimiter
from .settings import get_settings
from .supabase_db import (
    create_refresh_job,
    get_snapshot,
    get_job,
    get_user_from_token,
    insert_market_request_logs,
    make_service_client,
    mark_job,
    mark_symbol_failed,
    upsert_snapshot,
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
VISIBLE_PRICE_TTL_MINUTES = 15


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

    if request.mode in {"smart_visible", "visible_smart"}:
        plan = smart_visible_plan(symbols)
        due_symbols = plan["missing_symbols"] + plan["stale_quote_symbols"]
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
    job = get_job(service_client, job_id, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"ok": True, "job": job}


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


def smart_visible_plan(symbols: list[str]) -> dict[str, list[str]]:
    missing_symbols: list[str] = []
    stale_quote_symbols: list[str] = []
    current_symbols: list[str] = []

    for symbol in symbols:
        snapshot = get_snapshot(service_client, symbol) or {}
        if not has_positive_price(snapshot):
            missing_symbols.append(symbol)
        elif is_price_stale(snapshot):
            stale_quote_symbols.append(symbol)
        else:
            current_symbols.append(symbol)

    return {
        "missing_symbols": missing_symbols,
        "stale_quote_symbols": stale_quote_symbols,
        "current_symbols": current_symbols,
    }


def has_positive_price(snapshot: dict[str, Any]) -> bool:
    try:
        return float(snapshot.get("price") or 0) > 0
    except Exception:
        return False


def is_price_stale(snapshot: dict[str, Any], ttl_minutes: int = VISIBLE_PRICE_TTL_MINUTES) -> bool:
    if not has_positive_price(snapshot):
        return True
    updated_at = parse_datetime(snapshot.get("price_updated_at"))
    if not updated_at:
        return True
    return datetime.now(timezone.utc) - updated_at >= timedelta(minutes=ttl_minutes)


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
            core_snapshot = fetch_snapshot(symbol, layers=["quote", "history"], logger=logger, limiter=limiter)
            upsert_snapshot(service_client, core_snapshot)
        except Exception as exc:
            message = str(exc)
            failures.append(f"{symbol}: {message}")
            try:
                mark_symbol_failed(service_client, symbol, message)
            except Exception as mark_exc:
                failures.append(f"{symbol}: could not record failure: {mark_exc}")

        if not failures:
            try:
                fundamentals_snapshot = fetch_snapshot(
                    symbol,
                    layers=["fundamentals"],
                    logger=logger,
                    limiter=limiter,
                )
                upsert_snapshot(service_client, fundamentals_snapshot)
            except Exception as exc:
                failures.append(f"{symbol} fundamentals: {exc}")
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
    initial_symbols: list[str] = []
    quote_symbols: list[str] = []

    for symbol in symbols:
        snapshot = get_snapshot(service_client, symbol) or {}
        if not has_positive_price(snapshot):
            initial_symbols.append(symbol)
        elif is_price_stale(snapshot):
            quote_symbols.append(symbol)

    if quote_symbols:
        try:
            existing = {symbol: get_snapshot(service_client, symbol) or {} for symbol in quote_symbols}
            for snapshot in batch_quote_snapshots(
                quote_symbols,
                existing,
                logger,
                limiter,
                fast_lane=settings.enable_quote_fast_lane,
                fallback_spacing_seconds=0.0,
            ):
                if snapshot.get("quote_status") == "error":
                    failures.append(f"{snapshot['symbol']}: {snapshot.get('quote_last_error', 'quote failed')}")
                upsert_snapshot(service_client, snapshot)
        except Exception as exc:
            failures.append(f"batch quote: {exc}")

    for symbol in initial_symbols:
        try:
            core_snapshot = fetch_snapshot(symbol, layers=["quote", "history"], logger=logger, limiter=limiter)
            upsert_snapshot(service_client, core_snapshot)
        except Exception as exc:
            message = str(exc)
            failures.append(f"{symbol}: {message}")
            try:
                mark_symbol_failed(service_client, symbol, message)
            except Exception as mark_exc:
                failures.append(f"{symbol}: could not record failure: {mark_exc}")
            continue

        try:
            fundamentals_snapshot = fetch_snapshot(
                symbol,
                layers=["fundamentals"],
                logger=logger,
                limiter=limiter,
            )
            upsert_snapshot(service_client, fundamentals_snapshot)
        except Exception as exc:
            failures.append(f"{symbol} fundamentals: {exc}")
