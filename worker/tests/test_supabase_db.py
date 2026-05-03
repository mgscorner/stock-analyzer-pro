from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.supabase_db import merge_snapshot


class SupabaseDbTests(unittest.TestCase):
    def test_fundamentals_refresh_clears_stale_annual_fields(self) -> None:
        existing = {
            "symbol": "AEM",
            "price": 185.75,
            "history_data": [{"date": "2026-05-01", "close": 185.75}],
            "history_status": "complete",
            "revenue_year_1_label": 2009,
            "revenue_year_1_value": 640_076_000,
            "profit_year_1_label": 2013,
            "profit_year_1_value": -406_526_000,
            "fundamentals_status": "complete",
        }
        fresh = {
            "symbol": "AEM",
            "fundamentals_updated_at": "2026-05-03T00:00:00+00:00",
            "fundamentals_status": "missing",
            "revenue_year_1_label": None,
            "revenue_year_1_value": None,
            "profit_year_1_label": None,
            "profit_year_1_value": None,
        }

        merged = merge_snapshot(existing, fresh)

        self.assertIsNone(merged["revenue_year_1_label"])
        self.assertIsNone(merged["revenue_year_1_value"])
        self.assertIsNone(merged["profit_year_1_label"])
        self.assertIsNone(merged["profit_year_1_value"])
        self.assertEqual(merged["fundamentals_status"], "missing")
        self.assertEqual(merged["snapshot_status"], "partial")


if __name__ == "__main__":
    unittest.main()
