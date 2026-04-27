from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .settings import Settings


MARKET_TZ = ZoneInfo("America/New_York")

FIELD_PRICE = "price"
FIELD_HISTORY = "history"
FIELD_FUNDAMENTALS = "fundamentals"
FIELD_OWNERSHIP = "ownership"

MARKET_MAIN = "main"
MARKET_PRE = "pre"
MARKET_POST = "post"
MARKET_CLOSED_WEEKDAY = "closed_weekday"
MARKET_CLOSED_WEEKEND = "closed_weekend"


@dataclass(frozen=True)
class MarketPolicy:
    mode: str
    now: datetime


def market_policy_now(settings: Settings, now: datetime | None = None) -> MarketPolicy:
    current = (now or datetime.now(MARKET_TZ)).astimezone(MARKET_TZ)
    return MarketPolicy(mode=market_mode(settings, current), now=current)


def market_mode(settings: Settings, now: datetime) -> str:
    local = now.astimezone(MARKET_TZ)
    if local.weekday() >= 5:
        return MARKET_CLOSED_WEEKEND

    main_open = time(settings.market_main_open_hour, settings.market_main_open_minute)
    main_close = time(settings.market_main_close_hour, settings.market_main_close_minute)
    pre_start_hour = max(0, settings.market_main_open_hour - settings.market_pre_hours)
    post_end_hour = min(23, settings.market_main_close_hour + settings.market_post_hours)
    pre_start = time(pre_start_hour, settings.market_main_open_minute)
    post_end = time(post_end_hour, settings.market_main_close_minute)

    local_time = local.time()
    if pre_start <= local_time < main_open:
        return MARKET_PRE
    if main_open <= local_time < main_close:
        return MARKET_MAIN
    if main_close <= local_time < post_end:
        return MARKET_POST
    return MARKET_CLOSED_WEEKDAY


def ttl_minutes(settings: Settings, field: str, mode: str) -> int:
    field = str(field or "").lower()
    mode = str(mode or "").lower()

    if field == FIELD_PRICE:
        if mode == MARKET_MAIN:
            return settings.price_ttl_main_minutes
        if mode in {MARKET_PRE, MARKET_POST}:
            return settings.price_ttl_premarket_minutes if mode == MARKET_PRE else settings.price_ttl_postmarket_minutes
        return settings.price_ttl_closed_minutes

    if field == FIELD_HISTORY:
        return settings.history_ttl_main_minutes if mode == MARKET_MAIN else settings.history_ttl_closed_minutes

    if field == FIELD_FUNDAMENTALS:
        return settings.fundamentals_ttl_main_minutes if mode == MARKET_MAIN else settings.fundamentals_ttl_closed_minutes

    if field == FIELD_OWNERSHIP:
        return settings.ownership_ttl_main_minutes if mode == MARKET_MAIN else settings.ownership_ttl_closed_minutes

    return settings.price_ttl_main_minutes


def field_is_stale(updated_at: datetime | None, ttl_minutes_value: int, now: datetime | None = None) -> bool:
    if ttl_minutes_value <= 0:
        return False
    if updated_at is None:
        return True
    current = now or datetime.now(MARKET_TZ)
    return current.astimezone(MARKET_TZ) - updated_at.astimezone(MARKET_TZ) >= _minutes(ttl_minutes_value)


def _minutes(value: int):
    from datetime import timedelta

    return timedelta(minutes=value)
