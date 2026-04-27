from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.market_data import fetch_yfinance_major_holder_ownership, normalize_symbol
from app.market_debug import MarketRequestLogger
from app.settings import get_settings
from app.supabase_db import make_service_client, execute_with_retry


def main() -> int:
    args = parse_args()
    settings = get_settings()
    client = make_service_client(settings)

    symbols = load_symbols(client, args.symbols, args.file, args.universe)
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print("No symbols provided.")
        return 2

    logger = MarketRequestLogger(enabled=args.debug_logs)
    print(f"Yahoo ownership backfill: {len(symbols)} symbols")
    if args.limit:
        print(f"limit: {args.limit}")
    print(f"dry_run: {args.dry_run}")
    print(f"spacing_ms: {args.spacing_ms}")
    print("")

    changed = 0
    kept = 0
    failed = 0
    started = time.time()
    for index, symbol in enumerate(symbols, start=1):
        try:
            ownership = fetch_yfinance_major_holder_ownership(symbol, logger)
            existing = get_existing_ownership(client, symbol)
            if ownership > 0:
                if not args.dry_run:
                    update_ownership(client, symbol, ownership)
                changed += 1
                print(f"[{index}/{len(symbols)}] {symbol}: ownership={ownership:.4f}% updated")
            elif args.clear_missing:
                if not args.dry_run:
                    update_ownership(client, symbol, None)
                changed += 1
                print(f"[{index}/{len(symbols)}] {symbol}: ownership pending cleared")
            else:
                kept += 1
                print(f"[{index}/{len(symbols)}] {symbol}: no yahoo ownership, kept={existing}")
        except Exception as exc:
            failed += 1
            print(f"[{index}/{len(symbols)}] {symbol}: failed {exc}")
        if args.spacing_ms > 0:
            time.sleep(args.spacing_ms / 1000)

    duration = time.time() - started
    print("")
    print(f"done: {changed} changed, {kept} kept, {failed} failed, {duration:.1f}s")
    return 0 if failed == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill stock_snapshots.inst_ownership from Yahoo major_holders.")
    parser.add_argument("--symbols", nargs="*", default=[], help="Ticker symbols, for example --symbols AAPL MSFT.")
    parser.add_argument("--file", type=Path, help="Text or CSV file containing symbols.")
    parser.add_argument("--universe", nargs="*", default=[], help="Read symbols from stock_universes.")
    parser.add_argument("--limit", type=int, default=0, help="Limit symbols after de-duplication.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print without writing to Supabase.")
    parser.add_argument("--debug-logs", action="store_true", help="Print yfinance request events.")
    parser.add_argument("--spacing-ms", type=int, default=250, help="Pause between symbols. Default 250.")
    parser.add_argument(
        "--clear-missing",
        action="store_true",
        help="Clear inst_ownership when Yahoo returns no institutional ownership for a symbol.",
    )
    return parser.parse_args()


def load_symbols(client, cli_symbols: Iterable[str], file_path: Path | None, universes: Iterable[str]) -> list[str]:
    symbols = [normalize_symbol(symbol) for symbol in cli_symbols if normalize_symbol(symbol)]
    if file_path:
        symbols.extend(read_symbol_file(file_path))
    if universes:
        symbols.extend(load_universe_symbols(client, universes))
    if not symbols:
        result = execute_with_retry(lambda: client.table("stock_snapshots").select("symbol").order("symbol").execute())
        symbols = [normalize_symbol(row.get("symbol")) for row in (result.data or []) if normalize_symbol(row.get("symbol"))]
    return dedupe_symbols(symbols)


def load_universe_symbols(client, universes: Iterable[str]) -> list[str]:
    universe_names = [str(value).strip() for value in universes if str(value).strip()]
    if not universe_names:
        return []
    result = execute_with_retry(
        lambda: client.table("stock_universes")
        .select("symbol")
        .in_("universe_name", universe_names)
        .order("symbol")
        .execute()
    )
    return [normalize_symbol(row.get("symbol")) for row in (result.data or []) if normalize_symbol(row.get("symbol"))]


def read_symbol_file(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Symbol file not found: {path}")
    return [
        normalize_symbol(line.split(",")[0])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def dedupe_symbols(symbols: Iterable[str]) -> list[str]:
    deduped = []
    seen = set()
    for symbol in symbols:
        symbol = normalize_symbol(symbol)
        if symbol and symbol not in seen:
            seen.add(symbol)
            deduped.append(symbol)
    return deduped


def get_existing_ownership(client, symbol: str) -> float | None:
    result = execute_with_retry(
        lambda: client.table("stock_snapshots").select("inst_ownership").eq("symbol", symbol).maybe_single().execute()
    )
    row = result.data or {}
    value = row.get("inst_ownership")
    return float(value) if value is not None else None


def update_ownership(client, symbol: str, ownership: float | None) -> None:
    payload = {
        "inst_ownership": ownership,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    execute_with_retry(lambda: client.table("stock_snapshots").update(payload).eq("symbol", symbol).execute())


if __name__ == "__main__":
    raise SystemExit(main())
