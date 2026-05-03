from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.market_data import (
    download_fundamentals,
    annual_fundamentals_status,
    fetch_fmp_institutional_ownership_summary,
    fetch_fmp_fundamentals,
    fundamentals_cache_is_complete,
    parse_finviz_institutional_ownership,
    sec_concept_series,
)


class MarketDataTests(unittest.TestCase):
    @patch("app.market_data.fmp_ownership_period_candidates", return_value=[(2026, 1), (2025, 4)])
    @patch("app.market_data.provider_key", return_value="fmp-key")
    @patch("app.market_data.requests.get")
    def test_fmp_institutional_ownership_summary_uses_latest_positive_period(
        self,
        requests_get,
        _provider_key,
        _periods,
    ) -> None:
        empty_response = Mock()
        empty_response.status_code = 200
        empty_response.raise_for_status.return_value = None
        empty_response.json.return_value = {"ownershipPercent": 0}

        ownership_response = Mock()
        ownership_response.status_code = 200
        ownership_response.raise_for_status.return_value = None
        ownership_response.json.return_value = {"ownershipPercent": 65.727}

        requests_get.side_effect = [empty_response, ownership_response]
        limiter = Mock()
        limiter.wait.return_value = None
        logger = Mock()
        logger.track.return_value = MagicMock()
        logger.track.return_value.__enter__.return_value = Mock()
        logger.track.return_value.__exit__.return_value = None

        ownership = fetch_fmp_institutional_ownership_summary("IONQ", logger, limiter)

        self.assertEqual(ownership, 65.727)
        self.assertEqual(requests_get.call_count, 2)

    @patch("app.market_data._fundamentals_cache", {})
    @patch("app.market_data.fundamentals_provider_order", return_value=["sec", "fmp", "yfinance"])
    @patch("app.market_data.fetch_fundamentals_provider")
    def test_download_fundamentals_stops_before_yfinance_when_payload_complete(
        self,
        fetch_provider,
        _provider_order,
    ) -> None:
        financials = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): [130_016_000, -510_378_000],
                pd.Timestamp("2024-12-31"): [43_073_000, -331_647_000],
                pd.Timestamp("2023-12-31"): [22_042_000, -157_771_000],
                pd.Timestamp("2022-12-31"): [11_131_000, -48_511_000],
            },
            index=["Total Revenue", "Net Income"],
        )
        fetch_provider.side_effect = [
            {"name": "IONQ Inc", "market_cap": 0, "inst_ownership": 0, "financials": financials},
            {"name": "", "market_cap": 0, "inst_ownership": 65.727, "financials": pd.DataFrame()},
        ]
        limiter = Mock()
        limiter.wait.return_value = None

        payload = download_fundamentals(
            "IONQ",
            logger=Mock(),
            limiter=limiter,
            force_all_providers=True,
        )

        self.assertEqual(payload["inst_ownership"], 65.727)
        self.assertEqual(fetch_provider.call_count, 2)
        self.assertEqual([call.args[0] for call in fetch_provider.call_args_list], ["sec", "fmp"])

    def test_fundamentals_cache_requires_ownership(self) -> None:
        financials = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): [130_016_000, -510_378_000],
                pd.Timestamp("2024-12-31"): [43_073_000, -331_647_000],
                pd.Timestamp("2023-12-31"): [22_042_000, -157_771_000],
                pd.Timestamp("2022-12-31"): [11_131_000, -48_511_000],
            },
            index=["Total Revenue", "Net Income"],
        )

        self.assertFalse(
            fundamentals_cache_is_complete(
                {"financials": financials, "inst_ownership": 0}
            )
        )
        self.assertTrue(
            fundamentals_cache_is_complete(
                {"financials": financials, "inst_ownership": 65.727}
            )
        )

    @patch("app.market_data.provider_key", return_value="fmp-key")
    @patch("app.market_data.fetch_fmp_institutional_ownership_summary", return_value=65.727)
    @patch("app.market_data.fetch_finviz_institutional_ownership", return_value=0)
    @patch("app.market_data.fetch_fmp_profile_fields", return_value={})
    @patch("app.market_data.requests.get")
    def test_fmp_fundamentals_returns_ownership_when_profile_and_income_missing(
        self,
        requests_get,
        _profile,
        _finviz,
        _ownership,
        _provider_key,
    ) -> None:
        empty_income = Mock()
        empty_income.status_code = 200
        empty_income.raise_for_status.return_value = None
        empty_income.json.return_value = []
        requests_get.return_value = empty_income
        limiter = Mock()
        limiter.wait.return_value = None
        logger = Mock()
        logger.track.return_value = MagicMock()
        logger.track.return_value.__enter__.return_value = Mock()
        logger.track.return_value.__exit__.return_value = None

        payload = fetch_fmp_fundamentals("IONQ", logger, limiter)

        self.assertEqual(payload["inst_ownership"], 65.727)
        self.assertTrue(payload["financials"].empty)

    @patch("app.market_data.provider_key", return_value="fmp-key")
    @patch("app.market_data.fetch_finviz_institutional_ownership", return_value=53.45)
    @patch("app.market_data.fetch_fmp_profile_fields")
    @patch("app.market_data.fetch_fmp_institutional_ownership_summary")
    def test_fmp_fundamentals_returns_fast_finviz_ownership_before_slow_providers(
        self,
        fmp_ownership,
        fmp_profile,
        _finviz,
        _provider_key,
    ) -> None:
        payload = fetch_fmp_fundamentals("IONQ", logger=Mock(), limiter=Mock())

        self.assertEqual(payload["inst_ownership"], 53.45)
        fmp_ownership.assert_not_called()
        fmp_profile.assert_not_called()

    def test_parse_finviz_institutional_ownership(self) -> None:
        html = (
            '<div class="snapshot-td-label">Inst Own</div></td>'
            '<td class="snapshot-td2"><div class="snapshot-td-content"><b>53.45%</b></div></td>'
        )

        self.assertEqual(parse_finviz_institutional_ownership(html), 53.45)

    def test_sec_concept_series_rejects_stale_ancient_values(self) -> None:
        facts = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"form": "10-K", "fp": "FY", "fy": 2009, "end": "2009-12-31", "filed": "2010-02-01", "val": 640_076_000},
                        {"form": "10-K", "fp": "FY", "fy": 2008, "end": "2008-12-31", "filed": "2009-02-01", "val": 406_285_000},
                    ]
                }
            }
        }

        self.assertEqual(sec_concept_series(facts, ["Revenues"]), {})

    def test_annual_fundamentals_status_requires_current_target_years(self) -> None:
        stale_snapshot = {
            "revenue_year_1_label": 2009,
            "revenue_year_1_value": 640_076_000,
            "revenue_year_2_label": 2008,
            "revenue_year_2_value": 406_285_000,
            "revenue_year_3_label": 2007,
            "revenue_year_3_value": 461_435_000,
            "profit_year_1_label": 2013,
            "profit_year_1_value": -406_526_000,
            "profit_year_2_label": 2012,
            "profit_year_2_value": 310_916_000,
            "profit_year_3_label": 2011,
            "profit_year_3_value": -568_955_000,
            "profit_year_4_label": 2010,
            "profit_year_4_value": 332_116_000,
        }

        self.assertEqual(annual_fundamentals_status(stale_snapshot), "partial")


if __name__ == "__main__":
    unittest.main()
