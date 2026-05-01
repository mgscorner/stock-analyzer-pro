from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import Settings
from app.use_cases import add_ticker_use_case, ensure_complete_snapshot_for_add
from test_snapshot_rules import full_snapshot, make_settings


class UseCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings: Settings = make_settings()
        self.client = object()

    @patch("app.use_cases.insert_watchlist_entry")
    @patch("app.use_cases.ensure_not_duplicate_watchlist_entry")
    @patch("app.use_cases.ensure_complete_snapshot_for_add")
    def test_add_ticker_use_case_inserts_only_after_complete_snapshot(
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


if __name__ == "__main__":
    unittest.main()
