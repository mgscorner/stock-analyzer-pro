from __future__ import annotations

import argparse

from app.market_data import fetch_snapshot, normalize_symbol
from app.market_debug import MarketRequestLogger
from app.rate_limit import MarketRequestLimiter
from app.settings import get_settings
from app.supabase_db import make_service_client, upsert_snapshot


def main() -> int:
    args = parse_args()
    symbol = normalize_symbol(args.symbol)
    if not symbol:
        print("No symbol provided.")
        return 2

    settings = get_settings()
    limiter = MarketRequestLimiter(
        enabled=not args.no_limiter,
        quote_min_interval_ms=settings.quote_min_interval_ms,
        history_min_interval_ms=settings.history_min_interval_ms,
        fundamentals_min_interval_ms=settings.fundamentals_min_interval_ms,
    )
    logger = MarketRequestLogger(enabled=args.debug_logs)

    snapshot = fetch_snapshot(symbol, logger=logger, limiter=limiter)
    if not args.dry_run:
        upsert_snapshot(make_service_client(settings), snapshot)

    print(
        "ok "
        f"symbol={snapshot.get('symbol')} "
        f"name={snapshot.get('name')} "
        f"quote={snapshot.get('quote_status')} "
        f"history={snapshot.get('history_status')} "
        f"fundamentals={snapshot.get('fundamentals_status')} "
        f"snapshot={snapshot.get('snapshot_status')}"
    )
    if args.debug_logs:
        for event in logger.events:
            print(
                "request "
                f"{event['layer']} "
                f"{event['source']} "
                f"status={event['status_code']} "
                f"ok={event['ok']} "
                f"ms={event['duration_ms']}"
            )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and cache all available data for one ticker.")
    parser.add_argument("symbol", help="Ticker symbol, for example SOFI.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print result without writing to Supabase.")
    parser.add_argument("--no-limiter", action="store_true", help="Disable request spacing for a controlled local probe.")
    parser.add_argument("--debug-logs", action="store_true", help="Print provider request events.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
