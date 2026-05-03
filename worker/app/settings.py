from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    finnhub_api_key: str
    fmp_api_key: str
    allowed_origins: list[str]
    debug_market_requests: bool
    enable_request_limiter: bool
    enable_quote_fast_lane: bool
    enable_fundamentals_fallbacks: bool
    fundamentals_provider_order: list[str]
    market_main_open_hour: int
    market_main_open_minute: int
    market_main_close_hour: int
    market_main_close_minute: int
    market_pre_hours: int
    market_post_hours: int
    price_ttl_main_minutes: int
    price_ttl_premarket_minutes: int
    price_ttl_postmarket_minutes: int
    price_ttl_closed_minutes: int
    history_ttl_main_minutes: int
    history_ttl_closed_minutes: int
    fundamentals_ttl_main_minutes: int
    fundamentals_ttl_closed_minutes: int
    ownership_ttl_main_minutes: int
    ownership_ttl_closed_minutes: int
    quote_min_interval_ms: int
    history_min_interval_ms: int
    fundamentals_min_interval_ms: int
    scheduler_interval_seconds: int
    scheduler_watchlist_batch_size: int
    scheduler_universe_batch_size: int
    active_watchlist_window_minutes: int


def get_settings() -> Settings:
    origins = os.getenv("WORKER_ALLOWED_ORIGINS", "http://localhost:5173")
    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", "").strip(),
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", "").strip(),
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        finnhub_api_key=os.getenv("FINNHUB_API_KEY", "").strip(),
        fmp_api_key=os.getenv("FMP_API_KEY", "").strip(),
        allowed_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        debug_market_requests=os.getenv("WORKER_DEBUG_MARKET_REQUESTS", "0").strip() in {"1", "true", "True", "yes"},
        enable_request_limiter=os.getenv("WORKER_ENABLE_REQUEST_LIMITER", "1").strip() not in {"0", "false", "False", "no"},
        enable_quote_fast_lane=os.getenv("WORKER_ENABLE_QUOTE_FAST_LANE", "0").strip() in {"1", "true", "True", "yes"},
        enable_fundamentals_fallbacks=os.getenv("WORKER_ENABLE_FUNDAMENTALS_FALLBACKS", "0").strip()
        in {"1", "true", "True", "yes"},
        fundamentals_provider_order=parse_csv_list(
            os.getenv("WORKER_FUNDAMENTALS_PROVIDER_ORDER"),
            ["sec", "fmp", "finnhub_reported", "yfinance"],
        ),
        market_main_open_hour=safe_int(os.getenv("WORKER_MARKET_MAIN_OPEN_HOUR"), 9),
        market_main_open_minute=safe_int(os.getenv("WORKER_MARKET_MAIN_OPEN_MINUTE"), 30),
        market_main_close_hour=safe_int(os.getenv("WORKER_MARKET_MAIN_CLOSE_HOUR"), 16),
        market_main_close_minute=safe_int(os.getenv("WORKER_MARKET_MAIN_CLOSE_MINUTE"), 0),
        market_pre_hours=safe_int(os.getenv("WORKER_MARKET_PRE_HOURS"), 4),
        market_post_hours=safe_int(os.getenv("WORKER_MARKET_POST_HOURS"), 4),
        price_ttl_main_minutes=safe_int(os.getenv("WORKER_PRICE_TTL_MAIN_MINUTES"), 5),
        price_ttl_premarket_minutes=safe_int(os.getenv("WORKER_PRICE_TTL_PREMARKET_MINUTES"), 5),
        price_ttl_postmarket_minutes=safe_int(os.getenv("WORKER_PRICE_TTL_POSTMARKET_MINUTES"), 5),
        price_ttl_closed_minutes=safe_int(os.getenv("WORKER_PRICE_TTL_CLOSED_MINUTES"), 240),
        history_ttl_main_minutes=safe_int(os.getenv("WORKER_HISTORY_TTL_MAIN_MINUTES"), 1440),
        history_ttl_closed_minutes=safe_int(os.getenv("WORKER_HISTORY_TTL_CLOSED_MINUTES"), 10080),
        fundamentals_ttl_main_minutes=safe_int(os.getenv("WORKER_FUNDAMENTALS_TTL_MAIN_MINUTES"), 1440),
        fundamentals_ttl_closed_minutes=safe_int(os.getenv("WORKER_FUNDAMENTALS_TTL_CLOSED_MINUTES"), 4320),
        ownership_ttl_main_minutes=safe_int(os.getenv("WORKER_OWNERSHIP_TTL_MAIN_MINUTES"), 10080),
        ownership_ttl_closed_minutes=safe_int(os.getenv("WORKER_OWNERSHIP_TTL_CLOSED_MINUTES"), 20160),
        quote_min_interval_ms=safe_int(os.getenv("WORKER_QUOTE_MIN_INTERVAL_MS"), 300),
        history_min_interval_ms=safe_int(os.getenv("WORKER_HISTORY_MIN_INTERVAL_MS"), 500),
        fundamentals_min_interval_ms=safe_int(os.getenv("WORKER_FUNDAMENTALS_MIN_INTERVAL_MS"), 30000),
        scheduler_interval_seconds=safe_int(os.getenv("WORKER_SCHEDULER_INTERVAL_SECONDS"), 60),
        scheduler_watchlist_batch_size=safe_int(os.getenv("WORKER_SCHEDULER_WATCHLIST_BATCH_SIZE"), 30),
        scheduler_universe_batch_size=safe_int(os.getenv("WORKER_SCHEDULER_UNIVERSE_BATCH_SIZE"), 15),
        active_watchlist_window_minutes=safe_int(os.getenv("WORKER_ACTIVE_WATCHLIST_WINDOW_MINUTES"), 10),
    )


def parse_csv_list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    items: list[str] = []
    seen: set[str] = set()
    for raw in value.split(","):
        item = raw.strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
    return items or default


def safe_int(value: str | None, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return max(0, int(float(value)))
    except Exception:
        return default
