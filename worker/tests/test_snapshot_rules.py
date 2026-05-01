from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import Settings
from app.snapshot_rules import (
    add_incomplete_reason,
    add_snapshot_usable,
    annual_fundamentals_missing,
    due_layers_for_visible,
)


def make_settings() -> Settings:
    return Settings(
        supabase_url="",
        supabase_anon_key="",
        supabase_service_role_key="",
        finnhub_api_key="",
        fmp_api_key="",
        allowed_origins=["http://localhost:5173"],
        debug_market_requests=False,
        enable_request_limiter=False,
        enable_quote_fast_lane=False,
        enable_fundamentals_fallbacks=True,
        fundamentals_provider_order=["yfinance", "sec", "finnhub_reported", "fmp"],
        market_main_open_hour=9,
        market_main_open_minute=30,
        market_main_close_hour=16,
        market_main_close_minute=0,
        market_pre_hours=4,
        market_post_hours=4,
        price_ttl_main_minutes=5,
        price_ttl_premarket_minutes=5,
        price_ttl_postmarket_minutes=5,
        price_ttl_closed_minutes=240,
        history_ttl_main_minutes=1440,
        history_ttl_closed_minutes=10080,
        fundamentals_ttl_main_minutes=1440,
        fundamentals_ttl_closed_minutes=4320,
        ownership_ttl_main_minutes=10080,
        ownership_ttl_closed_minutes=20160,
        quote_min_interval_ms=300,
        history_min_interval_ms=500,
        fundamentals_min_interval_ms=30000,
        scheduler_interval_seconds=60,
        scheduler_watchlist_batch_size=30,
        scheduler_universe_batch_size=15,
        active_watchlist_window_minutes=10,
    )


def full_snapshot() -> dict:
    return {
        "symbol": "IONQ",
        "price": 42.11,
        "price_updated_at": "2026-05-01T14:58:00+00:00",
        "history_data": [{"date": "2026-04-30", "close": 41.0}],
        "history_updated_at": "2026-05-01T14:58:00+00:00",
        "fundamentals_updated_at": "2026-05-01T14:58:00+00:00",
        "inst_ownership": 33.11,
        "revenue_year_1_label": 2025,
        "revenue_year_1_value": 130_016_000,
        "revenue_year_2_label": 2024,
        "revenue_year_2_value": 43_073_000,
        "revenue_year_3_label": 2023,
        "revenue_year_3_value": 22_042_000,
        "revenue_year_4_label": 2022,
        "revenue_year_4_value": 11_131_000,
        "profit_year_1_label": 2025,
        "profit_year_1_value": -510_378_000,
        "profit_year_2_label": 2024,
        "profit_year_2_value": -331_647_000,
        "profit_year_3_label": 2023,
        "profit_year_3_value": -157_771_000,
        "profit_year_4_label": 2022,
        "profit_year_4_value": -48_511_000,
    }


class SnapshotRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = make_settings()
        self.now = datetime.fromisoformat("2026-05-01T11:00:00-04:00")

    def test_full_snapshot_is_usable_for_add(self) -> None:
        self.assertTrue(add_snapshot_usable(full_snapshot(), self.settings, self.now))

    def test_missing_ownership_rejects_add(self) -> None:
        snapshot = full_snapshot()
        snapshot["inst_ownership"] = 0
        self.assertFalse(add_snapshot_usable(snapshot, self.settings, self.now))
        self.assertIn("institutional ownership", add_incomplete_reason(snapshot, self.settings, self.now))

    def test_missing_annual_year_marks_fundamentals_incomplete(self) -> None:
        snapshot = full_snapshot()
        snapshot["profit_year_4_label"] = None
        snapshot["profit_year_4_value"] = None
        self.assertTrue(annual_fundamentals_missing(snapshot, self.settings, self.now))

    def test_due_layers_include_fundamentals_when_ownership_missing(self) -> None:
        snapshot = full_snapshot()
        snapshot["inst_ownership"] = 0
        layers = due_layers_for_visible(snapshot, self.settings, self.now)
        self.assertIn("fundamentals", layers)


if __name__ == "__main__":
    unittest.main()
