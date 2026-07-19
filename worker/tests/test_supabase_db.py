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

    def test_partial_fundamentals_never_make_snapshot_complete(self) -> None:
        existing = {
            "symbol": "IREN",
            "price": 57.99,
            "quote_status": "complete",
            "price_updated_at": "2026-05-03T00:00:00+00:00",
            "history_status": "complete",
            "history_updated_at": "2026-05-03T00:00:00+00:00",
            "history_data": [{"date": "2026-05-01", "close": 57.99}],
        }
        fresh = {
            "symbol": "IREN",
            "fundamentals_status": "partial",
            "fundamentals_updated_at": "2026-05-03T00:00:00+00:00",
            "inst_ownership": 43.34,
            "revenue_year_1_label": 2025,
            "revenue_year_1_value": 501_023_000,
            "profit_year_1_label": 2025,
            "profit_year_1_value": 86_941_000,
        }

        merged = merge_snapshot(existing, fresh)

        self.assertEqual(merged["fundamentals_status"], "partial")
        self.assertEqual(merged["snapshot_status"], "partial")

    def test_fundamentals_refresh_updates_positive_ownership_change(self) -> None:
        existing = {
            "symbol": "IREN",
            "price": 57.99,
            "quote_status": "complete",
            "history_status": "complete",
            "history_data": [{"date": "2026-05-01", "close": 57.99}],
            "inst_ownership": 43.34,
        }
        fresh = {
            "symbol": "IREN",
            "fundamentals_status": "complete",
            "fundamentals_updated_at": "2026-05-03T00:00:00+00:00",
            "inst_ownership": 19.1,
            "revenue_year_1_label": 2025,
            "revenue_year_1_value": 501_023_000,
            "revenue_year_2_label": 2024,
            "revenue_year_2_value": 187_192_000,
            "revenue_year_3_label": 2023,
            "revenue_year_3_value": 75_509_000,
            "revenue_year_4_label": 2022,
            "revenue_year_4_value": 59_024_000,
            "profit_year_1_label": 2025,
            "profit_year_1_value": 86_941_000,
            "profit_year_2_label": 2024,
            "profit_year_2_value": -28_920_000,
            "profit_year_3_label": 2023,
            "profit_year_3_value": -171_827_000,
            "profit_year_4_label": 2022,
            "profit_year_4_value": -419_784_000,
        }

        merged = merge_snapshot(existing, fresh)

        self.assertEqual(merged["inst_ownership"], 19.1)
        self.assertEqual(merged["fundamentals_status"], "complete")

    def test_fundamentals_refresh_does_not_overwrite_ownership_with_zero(self) -> None:
        existing = {
            "symbol": "IREN",
            "price": 57.99,
            "quote_status": "complete",
            "history_status": "complete",
            "history_data": [{"date": "2026-05-01", "close": 57.99}],
            "inst_ownership": 43.34,
        }
        fresh = {
            "symbol": "IREN",
            "fundamentals_status": "partial",
            "fundamentals_updated_at": "2026-05-03T00:00:00+00:00",
            "inst_ownership": 0,
            "revenue_year_1_label": 2025,
            "revenue_year_1_value": 501_023_000,
            "profit_year_1_label": 2025,
            "profit_year_1_value": 86_941_000,
        }

        merged = merge_snapshot(existing, fresh)

        self.assertEqual(merged["inst_ownership"], 43.34)


if __name__ == "__main__":
    unittest.main()
