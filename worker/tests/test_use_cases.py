from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import Settings
from app.use_cases import (
    add_ticker_use_case,
    ensure_complete_snapshot_for_add,
    ensure_snapshot_for_add_or_partial,
    refresh_visible_fundamentals_use_case,
)
from test_snapshot_rules import full_snapshot, make_settings


class UseCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings: Settings = make_settings()
        self.client = object()

    @patch("app.use_cases.insert_watchlist_entry")
    @patch("app.use_cases.ensure_not_duplicate_watchlist_entry")
    @patch("app.use_cases.ensure_snapshot_for_add_or_partial")
    def test_add_ticker_use_case_inserts_after_add_snapshot_is_ready(
        self,
        ensure_snapshot,
        ensure_not_duplicate,
        insert_watchlist_entry,
    ) -> None:
        ensure_snapshot.return_value = full_snapshot()

        snapshot = add_ticker_use_case(
            self.client,
            self.settings,
            "user-1",
            "Tech",
            "IONQ",
            logger=None,
            limiter=None,
        )

        ensure_not_duplicate.assert_called_once()
        ensure_snapshot.assert_called_once()
        insert_watchlist_entry.assert_called_once_with(self.client, "user-1", "Tech", "IONQ")
        self.assertEqual(snapshot["symbol"], "IONQ")

    @patch("app.use_cases.upsert_snapshot")
    @patch("app.use_cases.get_snapshot")
    def test_add_snapshot_accepts_partial_fundamentals_with_single_fetch(self, get_snapshot, upsert_snapshot) -> None:
        partial = full_snapshot()
        partial["symbol"] = "IREN"
        partial["revenue_year_4_label"] = None
        partial["revenue_year_4_value"] = None
        partial["profit_year_4_label"] = None
        partial["profit_year_4_value"] = None
        partial["snapshot_status"] = "partial"
        partial["fundamentals_status"] = "complete"
        get_snapshot.side_effect = [{}, partial]
        calls = []

        result = ensure_snapshot_for_add_or_partial(
            self.client,
            self.settings,
            "IREN",
            logger=None,
            limiter=None,
            fetcher=lambda symbol, logger, limiter: (
                calls.append(symbol) or partial
            ),
        )

        upsert_snapshot.assert_called_once()
        self.assertEqual(result["symbol"], "IREN")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], "IREN")
        self.assertEqual(upsert_snapshot.call_args.args[1]["snapshot_status"], "partial")
        self.assertIn("annual fundamentals", upsert_snapshot.call_args.args[1]["last_error"])

    @patch("app.use_cases.upsert_snapshot")
    @patch("app.use_cases.get_snapshot")
    def test_add_snapshot_rejects_partial_without_market_data(self, get_snapshot, upsert_snapshot) -> None:
        partial = {"symbol": "BAD", "price": 0, "history_data": []}
        get_snapshot.return_value = {}

        with self.assertRaises(ValueError):
            ensure_snapshot_for_add_or_partial(
                self.client,
                self.settings,
                "BAD",
                logger=None,
                limiter=None,
                fetcher=lambda symbol, logger, limiter: partial,
            )

        upsert_snapshot.assert_not_called()

    @patch("app.use_cases.add_snapshot_usable")
    @patch("app.use_cases.upsert_snapshot")
    @patch("app.use_cases.get_snapshot")
    def test_ensure_complete_snapshot_reuses_fresh_complete_snapshot(self, get_snapshot, upsert_snapshot, add_snapshot_usable) -> None:
        snapshot = full_snapshot()
        get_snapshot.return_value = snapshot
        add_snapshot_usable.return_value = True

        result = ensure_complete_snapshot_for_add(
            self.client,
            self.settings,
            "IONQ",
            logger=None,
            limiter=None,
            fetcher=lambda symbol, logger, limiter: self.fail("fetcher should not be called"),
        )

        self.assertEqual(result, snapshot)
        upsert_snapshot.assert_not_called()

    @patch("app.use_cases.add_snapshot_usable")
    @patch("app.use_cases.upsert_snapshot")
    @patch("app.use_cases.get_snapshot")
    def test_ensure_complete_snapshot_fetches_and_persists_when_cache_missing(self, get_snapshot, upsert_snapshot, add_snapshot_usable) -> None:
        fetched = full_snapshot()
        get_snapshot.side_effect = [{}, fetched]
        add_snapshot_usable.side_effect = [False, True]

        result = ensure_complete_snapshot_for_add(
            self.client,
            self.settings,
            "IONQ",
            logger=None,
            limiter=None,
            fetcher=lambda symbol, logger, limiter: fetched,
        )

        upsert_snapshot.assert_called_once_with(self.client, fetched)
        self.assertEqual(result["symbol"], "IONQ")

    @patch("app.use_cases.upsert_snapshot")
    @patch("app.use_cases.get_snapshot")
    @patch("app.use_cases.fetch_snapshot")
    def test_visible_fundamentals_refresh_does_not_use_yfinance(self, fetch_snapshot, get_snapshot, upsert_snapshot) -> None:
        get_snapshot.return_value = full_snapshot()
        fetch_snapshot.return_value = {
            "symbol": "IONQ",
            "fundamentals_status": "complete",
            "revenue_year_1_label": 2025,
            "revenue_year_1_value": 130_016_000,
            "profit_year_1_label": 2025,
            "profit_year_1_value": -510_378_000,
        }

        refresh_visible_fundamentals_use_case(
            self.client,
            self.settings,
            "IONQ",
            logger=None,
            limiter=None,
        )

        fetch_snapshot.assert_called_once_with(
            "IONQ",
            ["fundamentals"],
            logger=None,
            limiter=None,
            force_fundamentals_fallbacks=True,
            allow_yfinance_fundamentals=False,
        )
        upsert_snapshot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
