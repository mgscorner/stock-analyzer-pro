from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from supabase import Client, create_client

from .settings import Settings


def make_service_client(settings: Settings) -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_user_from_token(settings: Settings, token: str) -> dict[str, Any]:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY.")

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = client.auth.get_user(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session.") from exc

    user = getattr(response, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    return {
        "id": getattr(user, "id", None),
        "email": getattr(user, "email", None),
    }


def create_refresh_job(
    client: Client,
    user_id: str,
    email: str | None,
    symbols: list[str],
    watchlist_name: str | None,
) -> dict[str, Any]:
    result = (
        client.table("refresh_jobs")
        .insert(
            {
                "user_id": user_id,
                "requested_by": email,
                "watchlist_name": watchlist_name,
                "symbols": symbols,
                "status": "queued",
            }
        )
        .execute()
    )
    data = result.data or []
    if not data:
        raise RuntimeError("Could not create refresh job.")
    return data[0]


def get_job(client: Client, job_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = client.table("refresh_jobs").select("*").eq("id", job_id)
    if user_id:
        query = query.eq("user_id", user_id)
    result = query.maybe_single().execute()
    return result.data


def get_snapshot(client: Client, symbol: str) -> dict[str, Any] | None:
    result = (
        client.table("stock_snapshots")
        .select("*")
        .eq("symbol", symbol)
        .maybe_single()
        .execute()
    )
    if result is None:
        return None
    return result.data


def mark_job(client: Client, job_id: str, status: str, error: str | None = None) -> None:
    payload: dict[str, Any] = {"status": status}
    now = datetime.now(timezone.utc).isoformat()
    if status == "running":
        payload["started_at"] = now
    if status in {"done", "failed", "partial"}:
        payload["finished_at"] = now
    if error:
        payload["error"] = error[:2000]

    execute_with_retry(lambda: client.table("refresh_jobs").update(payload).eq("id", job_id).execute())


def execute_with_retry(operation, attempts: int = 3, delay_seconds: float = 0.5) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(delay_seconds * (attempt + 1))
    if last_error:
        raise last_error
    return None


def insert_market_request_logs(client: Client, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    execute_with_retry(lambda: client.table("market_request_logs").insert(events).execute())


def upsert_snapshot(client: Client, snapshot: dict[str, Any]) -> None:
    existing = get_snapshot(client, snapshot["symbol"]) or {}
    merged = merge_snapshot(existing, snapshot)
    execute_with_retry(lambda: client.table("stock_snapshots").upsert(merged, on_conflict="symbol").execute())


def merge_snapshot(existing: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    merged = {**existing}
    symbol = fresh["symbol"]
    merged["symbol"] = symbol

    # Price quote data is allowed to update frequently, but never replace a
    # good value with null/zero from a degraded upstream response.
    copy_if_meaningful(merged, fresh, "name")
    copy_if_positive(merged, fresh, "price")
    copy_if_positive(merged, fresh, "market_cap")
    copy_if_present(merged, fresh, "quote_status")
    copy_if_present(merged, fresh, "price_updated_at")

    # Historical data changes slowly. Only replace it when the worker fetched
    # a usable history layer.
    history_keys = [
        "green_charts",
        "perf_5y",
        "perf_3y",
        "perf_1y",
        "perf_6m",
        "perf_1m",
        "perf_3m",
        "close_5y",
        "close_3y",
        "close_1y",
        "close_6m",
        "close_1m",
        "close_3m",
        "history_data",
        "history_status",
        "history_updated_at",
    ]
    if fresh.get("history_updated_at") and fresh.get("history_data"):
        for key in history_keys:
            copy_if_present(merged, fresh, key)

    # Fundamentals are a separate layer. Do not let a fast quote/history
    # refresh overwrite expensive cached fundamentals with placeholders.
    fundamentals_keys = [
        "inst_ownership",
        "revenue_status",
        "profit_status",
        "revenue_year_1_label",
        "revenue_year_1_value",
        "revenue_year_2_label",
        "revenue_year_2_value",
        "revenue_year_3_label",
        "revenue_year_3_value",
        "revenue_year_4_label",
        "revenue_year_4_value",
        "revenue_year_5_label",
        "revenue_year_5_value",
        "profit_year_1_label",
        "profit_year_1_value",
        "profit_year_2_label",
        "profit_year_2_value",
        "profit_year_3_label",
        "profit_year_3_value",
        "profit_year_4_label",
        "profit_year_4_value",
        "profit_year_5_label",
        "profit_year_5_value",
        "fundamentals_updated_at",
        "fundamentals_status",
    ]
    if fresh.get("fundamentals_updated_at"):
        for key in fundamentals_keys:
            copy_if_present(merged, fresh, key)

    if fresh.get("last_error"):
        merged["last_error"] = fresh.get("last_error")
        merged["last_error_at"] = fresh.get("last_error_at")
    elif fresh.get("quote_status") == "complete" and fresh.get("history_status") == "complete":
        merged["last_error"] = None
        merged["last_error_at"] = None
    merged["snapshot_status"] = snapshot_status(merged)
    copy_if_present(merged, fresh, "updated_at")
    return merged


def snapshot_status(snapshot: dict[str, Any]) -> str:
    if snapshot.get("last_error"):
        return "error"
    if quote_complete(snapshot) and history_complete(snapshot) and fundamentals_complete(snapshot):
        return "complete"
    if snapshot.get("price") or snapshot.get("history_data"):
        return "partial"
    return "missing"


def quote_complete(snapshot: dict[str, Any]) -> bool:
    return snapshot.get("quote_status") == "complete" or bool(snapshot.get("price_updated_at") and snapshot.get("price"))


def history_complete(snapshot: dict[str, Any]) -> bool:
    return snapshot.get("history_status") == "complete" or bool(snapshot.get("history_updated_at") and snapshot.get("history_data"))


def fundamentals_complete(snapshot: dict[str, Any]) -> bool:
    if snapshot.get("fundamentals_status") == "complete":
        return True
    if snapshot.get("fundamentals_status") in {"missing", "error"}:
        return False
    return bool(snapshot.get("fundamentals_updated_at") and has_real_fundamentals(snapshot))


def has_real_fundamentals(snapshot: dict[str, Any]) -> bool:
    try:
        ownership = float(snapshot.get("inst_ownership") or 0)
    except Exception:
        ownership = 0
    return (
        ownership > 0
        or snapshot.get("revenue_status") == "Growth"
        or snapshot.get("profit_status") == "Growth"
        or bool(snapshot.get("revenue_year_1_value"))
        or bool(snapshot.get("profit_year_1_value"))
    )


def copy_if_present(target: dict[str, Any], source: dict[str, Any], key: str) -> None:
    if key in source and source[key] is not None:
        target[key] = source[key]


def copy_if_meaningful(target: dict[str, Any], source: dict[str, Any], key: str) -> None:
    value = source.get(key)
    if value not in (None, "", "N/A"):
        if key == "name" and normalize_text(value) == normalize_text(source.get("symbol")):
            return
        target[key] = value


def copy_if_positive(target: dict[str, Any], source: dict[str, Any], key: str) -> None:
    try:
        value = float(source.get(key) or 0)
    except Exception:
        value = 0
    if value > 0:
        target[key] = source[key]


def normalize_text(value: Any) -> str:
    return str(value or "").strip().upper()


def mark_symbol_failed(client: Client, symbol: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    existing = get_snapshot(client, symbol)
    payload = {
        "symbol": symbol,
        "last_error": error[:1000],
        "last_error_at": now,
        "updated_at": now,
    }
    if existing:
        client.table("stock_snapshots").update(payload).eq("symbol", symbol).execute()
    else:
        client.table("stock_snapshots").insert(payload).execute()
