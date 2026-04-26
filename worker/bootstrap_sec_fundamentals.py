from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Iterable

from app.market_data import fetch_snapshot, normalize_symbol
from app.market_debug import MarketRequestLogger
from app.rate_limit import MarketRequestLimiter
from app.settings import get_settings
from app.supabase_db import make_service_client, upsert_snapshot


def main() -> int:
    args = parse_args()
    symbols = load_symbols(args.symbols, args.file)
    if not symbols:
        print("No symbols provided.")
        return 2

    settings = get_settings()
    client = None if args.dry_run else make_service_client(settings)
    limiter = MarketRequestLimiter(
        enabled=not args.no_limiter,
        quote_min_interval_ms=settings.quote_min_interval_ms,
        history_min_interval_ms=settings.history_min_interval_ms,
        fundamentals_min_interval_ms=args.spacing_ms,
    )

    print(f"SEC fundamentals bootstrap: {len(symbols)} symbols")
    print(f"dry_run: {args.dry_run}")
    print(f"spacing_ms: {args.spacing_ms if not args.no_limiter else 0}")
    print("")

    ok_count = 0
    failed: list[tuple[str, str]] = []
    started = time.time()

    for index, symbol in enumerate(symbols, start=1):
        print(f"[{index}/{len(symbols)}] {symbol}: fetching annual fundamentals")
        logger = MarketRequestLogger(enabled=args.debug_logs)
        try:
            snapshot = fetch_snapshot(
                symbol,
                layers=["fundamentals"],
                logger=logger,
                limiter=limiter,
            )
            if not args.dry_run and client is not None:
                upsert_snapshot(client, snapshot)
            ok_count += 1
            print(
                "  ok "
                f"name={snapshot.get('name') or symbol} "
                f"status={snapshot.get('fundamentals_status')} "
                f"revenue={snapshot.get('revenue_year_1_label')}:{snapshot.get('revenue_year_1_value')} "
                f"profit={snapshot.get('profit_year_1_label')}:{snapshot.get('profit_year_1_value')}"
            )
            if args.debug_logs and logger.events:
                for event in logger.events:
                    print(
                        "  request "
                        f"{event['source']} "
                        f"status={event['status_code']} "
                        f"ok={event['ok']} "
                        f"ms={event['duration_ms']}"
                    )
        except Exception as exc:
            message = str(exc)[:500]
            failed.append((symbol, message))
            print(f"  failed {message}")

    duration = time.time() - started
    print("")
    print(f"done: {ok_count} ok, {len(failed)} failed, {duration:.1f}s")
    if failed:
        print("failed symbols:")
        for symbol, message in failed:
            print(f"  {symbol}: {message}")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap annual revenue/profit from SEC EDGAR into stock_snapshots.",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=[],
        help="Ticker symbols to bootstrap, for example --symbols AAPL MSFT NVDA.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Text or CSV file containing symbols. CSV uses the first column unless a symbol column exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print results without writing to Supabase.",
    )
    parser.add_argument(
        "--spacing-ms",
        type=int,
        default=300,
        help="Minimum spacing between fundamentals requests. Default: 300.",
    )
    parser.add_argument(
        "--no-limiter",
        action="store_true",
        help="Disable request spacing for a controlled local probe.",
    )
    parser.add_argument(
        "--debug-logs",
        action="store_true",
        help="Print provider request events for each symbol.",
    )
    return parser.parse_args()


def load_symbols(cli_symbols: Iterable[str], file_path: Path | None) -> list[str]:
    symbols = [normalize_symbol(symbol) for symbol in cli_symbols if normalize_symbol(symbol)]
    if file_path:
        symbols.extend(read_symbol_file(file_path))
    deduped: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if symbol and symbol not in seen:
            seen.add(symbol)
            deduped.append(symbol)
    return deduped


def read_symbol_file(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Symbol file not found: {path}")
    if path.suffix.lower() == ".csv":
        return read_csv_symbols(path)
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        values.append(normalize_symbol(line.split(",")[0]))
    return [value for value in values if value]


def read_csv_symbols(path: Path) -> list[str]:
    values = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames:
            symbol_field = next((field for field in reader.fieldnames if field.lower() == "symbol"), None)
            if symbol_field:
                for row in reader:
                    values.append(normalize_symbol(row.get(symbol_field)))
                return [value for value in values if value]

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if row:
                values.append(normalize_symbol(row[0]))
    return [value for value in values if value and value != "SYMBOL"]


if __name__ == "__main__":
    raise SystemExit(main())
