from __future__ import annotations

import argparse
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app.market_data import fetch_snapshot, normalize_symbol, number_or_zero
from app.market_debug import MarketRequestLogger
from app.rate_limit import MarketRequestLimiter
from app.settings import get_settings
from app.supabase_db import make_service_client, merge_snapshot, upsert_snapshot


LAYERS = ["quote", "history", "fundamentals"]


def main() -> int:
    args = parse_args()
    settings = get_settings()
    client = make_service_client(settings)
    symbols = load_symbols(args.symbols, args.file)
    if args.universe:
        symbols.extend(load_universe_symbols(client, args.universe))
    symbols = dedupe_symbols(symbols)
    if args.missing_only or args.refetch_after_minutes > 0:
        symbols = filter_due_symbols(
            client,
            symbols,
            refetch_after_minutes=args.refetch_after_minutes,
        )
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print("No symbols provided.")
        return 2

    limiter = MarketRequestLimiter(
        enabled=not args.no_limiter,
        quote_min_interval_ms=args.quote_spacing_ms,
        history_min_interval_ms=args.history_spacing_ms,
        fundamentals_min_interval_ms=args.fundamentals_spacing_ms,
    )
    print(f"Full cache bootstrap: {len(symbols)} symbols")
    if args.universe:
        print(f"universe: {', '.join(args.universe)}")
    if args.limit:
        print(f"limit: {args.limit}")
    if args.missing_only:
        print("missing_only: core_cache_fields")
    if args.refetch_after_minutes > 0:
        print(f"refetch_after_minutes: {args.refetch_after_minutes}")
    print(f"dry_run: {args.dry_run}")
    print(f"layer_workers: {args.layer_workers}")
    print(f"quote_spacing_ms: {args.quote_spacing_ms if not args.no_limiter else 0}")
    print(f"history_spacing_ms: {args.history_spacing_ms if not args.no_limiter else 0}")
    print(f"fundamentals_spacing_ms: {args.fundamentals_spacing_ms if not args.no_limiter else 0}")
    print("")

    ok_count = 0
    failed: list[tuple[str, str]] = []
    started = time.time()
    for index, symbol in enumerate(symbols, start=1):
        print(f"[{index}/{len(symbols)}] {symbol}: fetching quote/history/fundamentals")
        try:
            snapshot, layer_errors = fetch_symbol_layers(
                symbol=symbol,
                limiter=limiter,
                debug_logs=args.debug_logs,
                layer_workers=args.layer_workers,
            )
            if not args.dry_run:
                upsert_snapshot(client, snapshot)
            ok_count += 1
            print(
                "  ok "
                f"name={snapshot.get('name') or symbol} "
                f"price={snapshot.get('price')} "
                f"market_cap={snapshot.get('market_cap')} "
                f"quote={snapshot.get('quote_status')} "
                f"history={snapshot.get('history_status')} "
                f"fundamentals={snapshot.get('fundamentals_status')} "
                f"ownership={snapshot.get('inst_ownership')}"
            )
            for layer, message in layer_errors:
                print(f"  layer_warning {layer}: {message}")
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


def fetch_symbol_layers(
    symbol: str,
    limiter: MarketRequestLimiter,
    debug_logs: bool,
    layer_workers: int,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    partials: list[dict[str, Any]] = []
    errors: list[tuple[str, str]] = []
    max_workers = max(1, min(layer_workers, len(LAYERS)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_layer, symbol, layer, limiter, debug_logs): layer
            for layer in LAYERS
        }
        for future in as_completed(futures):
            layer = futures[future]
            try:
                partials.append(future.result())
            except Exception as exc:
                errors.append((layer, str(exc)[:500]))

    if not partials:
        raise RuntimeError("All layers failed")

    merged: dict[str, Any] = {"symbol": symbol}
    for partial in sorted(partials, key=merge_order):
        merged = merge_snapshot(merged, partial)
    return merged, errors


def fetch_layer(
    symbol: str,
    layer: str,
    limiter: MarketRequestLimiter,
    debug_logs: bool,
) -> dict[str, Any]:
    logger = MarketRequestLogger(enabled=debug_logs)
    snapshot = fetch_snapshot(
        symbol,
        layers=[layer],
        logger=logger,
        limiter=limiter,
    )
    if debug_logs:
        for event in logger.events:
            print(
                "  request "
                f"{symbol} "
                f"{event['layer']} "
                f"{event['source']} "
                f"status={event['status_code']} "
                f"ok={event['ok']} "
                f"ms={event['duration_ms']}"
            )
    return snapshot


def merge_order(snapshot: dict[str, Any]) -> int:
    if "price_updated_at" in snapshot:
        return 1
    if "history_updated_at" in snapshot:
        return 2
    if "fundamentals_updated_at" in snapshot:
        return 3
    return 9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build complete stock_snapshots rows by fetching quote/history/fundamentals/ownership per ticker.",
    )
    parser.add_argument("--symbols", nargs="*", default=[], help="Ticker symbols, for example --symbols AAPL MSFT.")
    parser.add_argument("--file", type=Path, help="Text or CSV file containing symbols.")
    parser.add_argument("--universe", nargs="*", default=[], help="Read symbols from stock_universes.")
    parser.add_argument("--limit", type=int, default=0, help="Limit symbols after de-duplication.")
    parser.add_argument("--missing-only", action="store_true", help="Skip stock_snapshots rows already complete.")
    parser.add_argument(
        "--refetch-after-minutes",
        type=int,
        default=0,
        help="Only refetch rows whose core cache data is older than this many minutes. 0 disables the age check.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print without writing to Supabase.")
    parser.add_argument("--no-limiter", action="store_true", help="Disable provider spacing for controlled local tests.")
    parser.add_argument("--debug-logs", action="store_true", help="Print provider request events.")
    parser.add_argument("--layer-workers", type=int, default=3, help="Parallel layer workers per symbol. Default 3.")
    parser.add_argument("--quote-spacing-ms", type=int, default=300, help="Quote request spacing. Default 300.")
    parser.add_argument("--history-spacing-ms", type=int, default=750, help="History request spacing. Default 750.")
    parser.add_argument(
        "--fundamentals-spacing-ms",
        type=int,
        default=750,
        help="Fundamentals request spacing for admin bootstrap. Default 750.",
    )
    return parser.parse_args()


def load_universe_symbols(client, universes: Iterable[str]) -> list[str]:
    universe_names = [str(value).strip() for value in universes if str(value).strip()]
    if not universe_names:
        return []
    result = (
        client.table("stock_universes")
        .select("symbol")
        .in_("universe_name", universe_names)
        .order("symbol")
        .execute()
    )
    return [normalize_symbol(row.get("symbol")) for row in (result.data or []) if normalize_symbol(row.get("symbol"))]


def filter_due_symbols(client, symbols: list[str], refetch_after_minutes: int) -> list[str]:
    if not symbols:
        return []
    result = (
        client.table("stock_snapshots")
        .select(
            "symbol,quote_status,history_status,fundamentals_status,price,market_cap,"
            "price_updated_at,history_updated_at,fundamentals_updated_at"
        )
        .in_("symbol", symbols)
        .execute()
    )
    rows_by_symbol = {
        normalize_symbol(row.get("symbol")): row
        for row in (result.data or [])
        if normalize_symbol(row.get("symbol"))
    }

    ranked: list[tuple[int, str]] = []
    for symbol in symbols:
        row = rows_by_symbol.get(symbol)
        if row is None:
            ranked.append((5, symbol))
            continue
        due_score = core_due_score(row, refetch_after_minutes)
        if due_score > 0:
            ranked.append((due_score, symbol))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [symbol for _score, symbol in ranked]


def core_due_score(row: dict[str, Any], refetch_after_minutes: int) -> int:
    score = 0
    if row.get("quote_status") != "complete" or not positive_number(row.get("price")):
        score += 1
    elif refetch_after_minutes > 0 and is_older_than(row.get("price_updated_at"), refetch_after_minutes):
        score += 1
    if not positive_number(row.get("market_cap")):
        score += 1
    if row.get("history_status") != "complete" or not row.get("history_updated_at"):
        score += 1
    if row.get("fundamentals_status") != "complete" or not row.get("fundamentals_updated_at"):
        score += 1
    if refetch_after_minutes > 0:
        if is_older_than(row.get("history_updated_at"), refetch_after_minutes):
            score += 1
        if is_older_than(row.get("fundamentals_updated_at"), refetch_after_minutes):
            score += 1
    return score


def positive_number(value: Any) -> bool:
    try:
        return float(value or 0) > 0
    except Exception:
        return False


def is_older_than(value: Any, minutes: int) -> bool:
    if minutes <= 0:
        return False
    dt = parse_datetime(value)
    if not dt:
        return True
    return datetime.now(timezone.utc) - dt >= time_delta_minutes(minutes)


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def time_delta_minutes(minutes: int):
    return timedelta(minutes=minutes)


def load_symbols(cli_symbols: Iterable[str], file_path: Path | None) -> list[str]:
    symbols = [normalize_symbol(symbol) for symbol in cli_symbols if normalize_symbol(symbol)]
    if file_path:
        symbols.extend(read_symbol_file(file_path))
    return symbols


def read_symbol_file(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Symbol file not found: {path}")
    if path.suffix.lower() == ".csv":
        return read_csv_symbols(path)
    return [
        normalize_symbol(line.split(",")[0])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def read_csv_symbols(path: Path) -> list[str]:
    values = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames:
            symbol_field = next((field for field in reader.fieldnames if field.lower() == "symbol"), None)
            if symbol_field:
                return [normalize_symbol(row.get(symbol_field)) for row in reader if normalize_symbol(row.get(symbol_field))]
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if row:
                values.append(normalize_symbol(row[0]))
    return [value for value in values if value and value != "SYMBOL"]


def dedupe_symbols(symbols: Iterable[str]) -> list[str]:
    deduped = []
    seen = set()
    for symbol in symbols:
        symbol = normalize_symbol(symbol)
        if symbol and symbol not in seen:
            seen.add(symbol)
            deduped.append(symbol)
    return deduped


if __name__ == "__main__":
    raise SystemExit(main())
