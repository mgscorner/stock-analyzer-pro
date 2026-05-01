from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .market_policy import (
    FIELD_FUNDAMENTALS,
    FIELD_HISTORY,
    FIELD_OWNERSHIP,
    FIELD_PRICE,
    field_is_stale,
    market_policy_now,
    ttl_minutes,
)
from .settings import Settings


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


def has_positive_price(snapshot: dict[str, Any]) -> bool:
    try:
        return float(snapshot.get("price") or 0) > 0
    except Exception:
        return False


def has_history(snapshot: dict[str, Any]) -> bool:
    return bool(snapshot.get("history_data"))


def has_positive_ownership(snapshot: dict[str, Any]) -> bool:
    try:
        return float(snapshot.get("inst_ownership") or 0) > 0
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


def required_annual_years(settings: Settings, now: datetime | None = None) -> list[int]:
    market_now = market_policy_now(settings, now).now
    return [market_now.year - offset for offset in range(1, 5)]


def annual_fundamentals_missing(snapshot: dict[str, Any], settings: Settings, now: datetime | None = None) -> bool:
    for target_year in required_annual_years(settings, now):
        if not annual_series_has_year(snapshot, "revenue", target_year):
            return True
        if not annual_series_has_year(snapshot, "profit", target_year):
            return True
    return False


def add_snapshot_complete(snapshot: dict[str, Any], settings: Settings, now: datetime | None = None) -> bool:
    return (
        has_positive_price(snapshot)
        and has_history(snapshot)
        and not annual_fundamentals_missing(snapshot, settings, now)
        and has_positive_ownership(snapshot)
    )


def add_snapshot_fresh(snapshot: dict[str, Any], settings: Settings, now: datetime | None = None) -> bool:
    if not snapshot:
        return False
    policy = market_policy_now(settings, now)
    current = policy.now
    return not (
        field_is_stale(parse_datetime(snapshot.get("price_updated_at")), ttl_minutes(settings, FIELD_PRICE, policy.mode), current)
        or field_is_stale(parse_datetime(snapshot.get("history_updated_at")), ttl_minutes(settings, FIELD_HISTORY, policy.mode), current)
        or field_is_stale(parse_datetime(snapshot.get("fundamentals_updated_at")), ttl_minutes(settings, FIELD_FUNDAMENTALS, policy.mode), current)
        or field_is_stale(parse_datetime(snapshot.get("fundamentals_updated_at")), ttl_minutes(settings, FIELD_OWNERSHIP, policy.mode), current)
    )


def add_snapshot_usable(snapshot: dict[str, Any], settings: Settings, now: datetime | None = None) -> bool:
    return add_snapshot_complete(snapshot, settings, now) and add_snapshot_fresh(snapshot, settings, now)


def add_incomplete_reason(snapshot: dict[str, Any], settings: Settings, now: datetime | None = None) -> str:
    if not snapshot:
        return "snapshot missing"
    reasons: list[str] = []
    if not has_positive_price(snapshot):
        reasons.append("price")
    if not has_history(snapshot):
        reasons.append("history")
    if annual_fundamentals_missing(snapshot, settings, now):
        reasons.append("annual fundamentals")
    if not has_positive_ownership(snapshot):
        reasons.append("institutional ownership")
    if not reasons and not add_snapshot_fresh(snapshot, settings, now):
        reasons.append("stale cached snapshot")
    return "missing or stale " + ", ".join(reasons or ["snapshot"])


def is_layer_due(snapshot: dict[str, Any], field: str, settings: Settings, now: datetime | None = None) -> bool:
    policy = market_policy_now(settings, now)
    current = policy.now
    mode = policy.mode
    if field == FIELD_PRICE:
        if not has_positive_price(snapshot):
            return True
        return field_is_stale(parse_datetime(snapshot.get("price_updated_at")), ttl_minutes(settings, FIELD_PRICE, mode), current)
    if field == FIELD_HISTORY:
        return field_is_stale(parse_datetime(snapshot.get("history_updated_at")), ttl_minutes(settings, FIELD_HISTORY, mode), current) or not has_history(snapshot)
    if field == FIELD_FUNDAMENTALS:
        return field_is_stale(parse_datetime(snapshot.get("fundamentals_updated_at")), ttl_minutes(settings, FIELD_FUNDAMENTALS, mode), current) or annual_fundamentals_missing(snapshot, settings, current)
    if field == FIELD_OWNERSHIP:
        return field_is_stale(parse_datetime(snapshot.get("fundamentals_updated_at")), ttl_minutes(settings, FIELD_OWNERSHIP, mode), current) or not has_positive_ownership(snapshot)
    return False


def due_layers_for_visible(snapshot: dict[str, Any], settings: Settings, now: datetime | None = None) -> list[str]:
    layers: list[str] = []
    if is_layer_due(snapshot, FIELD_PRICE, settings, now):
        layers.append(FIELD_PRICE)
    if is_layer_due(snapshot, FIELD_HISTORY, settings, now):
        layers.append(FIELD_HISTORY)
    if is_layer_due(snapshot, FIELD_FUNDAMENTALS, settings, now):
        layers.append(FIELD_FUNDAMENTALS)
    if is_layer_due(snapshot, FIELD_OWNERSHIP, settings, now) and FIELD_FUNDAMENTALS not in layers:
        layers.append(FIELD_FUNDAMENTALS)
    return layers
