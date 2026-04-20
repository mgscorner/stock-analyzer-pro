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
    quote_min_interval_ms: int
    history_min_interval_ms: int
    fundamentals_min_interval_ms: int


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
        quote_min_interval_ms=safe_int(os.getenv("WORKER_QUOTE_MIN_INTERVAL_MS"), 300),
        history_min_interval_ms=safe_int(os.getenv("WORKER_HISTORY_MIN_INTERVAL_MS"), 500),
        fundamentals_min_interval_ms=safe_int(os.getenv("WORKER_FUNDAMENTALS_MIN_INTERVAL_MS"), 30000),
    )


def safe_int(value: str | None, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return max(0, int(float(value)))
    except Exception:
        return default
