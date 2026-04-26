from __future__ import annotations

import argparse
import csv
import io
import re
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from check_sec_13f_ownership import (
    download_to_cache,
    latest_13f_dataset_url,
    normalize_cusip,
    resolve_cusip,
)

from app.market_data import normalize_symbol, number_or_zero
from app.settings import get_settings
from app.supabase_db import get_snapshot, make_service_client


def main() -> int:
    args = parse_args()
    settings = get_settings()
    client = make_service_client(settings)

    symbols = load_symbols(args.symbols, args.file)
    if args.universe:
        symbols.extend(load_universe_symbols(client, args.universe))
    symbols = dedupe_symbols(symbols)

    if args.recalculate_only:
        report_period = args.report_period or latest_cached_report_period(client)
        if not report_period:
            print("No ownership report period found. Run SEC ownership bootstrap first.")
            return 2
        return recalculate_cached_ownership(
            client=client,
            symbols=symbols,
            report_period=report_period,
            missing_only=args.missing_only,
            limit=args.limit,
            dry_run=args.dry_run,
            spacing_ms=args.spacing_ms,
        )

    dataset_url = args.dataset_url or latest_13f_dataset_url()
    dataset_path = download_to_cache(dataset_url, args.force_download)
    report_period = args.report_period or report_period_from_dataset(dataset_path)

    if args.missing_only:
        symbols = filter_missing_ownership(client, symbols, report_period)
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print("No symbols provided.")
        return 2

    print(f"Ownership bootstrap: {len(symbols)} symbols")
    if args.universe:
        print(f"universe: {', '.join(args.universe)}")
    if args.limit:
        print(f"limit: {args.limit}")
    if args.missing_only:
        print(f"missing_only: report_period={report_period}")
    print(f"dry_run: {args.dry_run}")
    print(f"dataset: {dataset_path.name}")
    print(f"report_period: {report_period}")
    print(f"spacing_ms: {args.spacing_ms}")
    print("")

    symbol_cusips = resolve_symbol_cusips(symbols, args.cusip)
    resolved = {symbol: cusip for symbol, cusip in symbol_cusips.items() if cusip}
    unresolved = [symbol for symbol, cusip in symbol_cusips.items() if not cusip]
    if unresolved:
        print(f"unresolved_cusips: {', '.join(unresolved[:25])}")
        if len(unresolved) > 25:
            print(f"  ... {len(unresolved) - 25} more")
    if not resolved:
        print("No CUSIPs resolved.")
        return 1

    started = time.time()
    aggregates = aggregate_dataset_for_cusips(dataset_path, set(resolved.values()))
    rows = []
    snapshot_updates = []
    for symbol, cusip in resolved.items():
        aggregate = aggregates.get(cusip) or empty_aggregate()
        row = ownership_row(symbol, cusip, dataset_path.name, report_period, aggregate, client)
        rows.append(row)
        if number_or_zero(row.get("estimated_ownership_percent")) > 0:
            snapshot_updates.append(
                {
                    "symbol": symbol,
                    "inst_ownership": row["estimated_ownership_percent"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        print(
            f"{symbol}: holders={row['holder_count']} "
            f"shares={row['institutional_shares']} "
            f"ownership={row['estimated_ownership_percent']} "
            f"status={row['status']}"
        )
        if args.spacing_ms > 0:
            time.sleep(args.spacing_ms / 1000)

    if not args.dry_run:
        upsert_ownership_rows(client, rows)
        upsert_snapshot_ownership(client, snapshot_updates)
        print(f"database: upserted {len(rows)} ownership rows")
        print(f"database: updated {len(snapshot_updates)} stock_snapshots inst_ownership values")

    duration = time.time() - started
    print("")
    print(f"done: {len(rows)} ownership rows, {len(unresolved)} unresolved, {duration:.1f}s")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap SEC 13F institutional ownership cache.")
    parser.add_argument("--symbols", nargs="*", default=[], help="Symbols to bootstrap, for example --symbols AAPL MSFT.")
    parser.add_argument("--file", type=Path, help="Text or CSV file containing symbols.")
    parser.add_argument("--universe", nargs="*", default=[], help="Read symbols from stock_universes.")
    parser.add_argument("--limit", type=int, default=0, help="Limit symbols after de-duplication.")
    parser.add_argument("--missing-only", action="store_true", help="Skip symbols already cached for this report period.")
    parser.add_argument("--dry-run", action="store_true", help="Aggregate and print without writing to Supabase.")
    parser.add_argument("--dataset-url", help="Explicit SEC 13F data-set ZIP URL.")
    parser.add_argument("--report-period", help="Explicit report period, for example 01dec2025-28feb2026.")
    parser.add_argument(
        "--recalculate-only",
        action="store_true",
        help="Recalculate ownership percent from cached ownership rows and current price/market cap without reparsing SEC data.",
    )
    parser.add_argument("--force-download", action="store_true", help="Re-download SEC ZIP even if cached.")
    parser.add_argument("--spacing-ms", type=int, default=50, help="Pause between per-symbol output/write prep. Default 50.")
    parser.add_argument(
        "--cusip",
        action="append",
        default=[],
        help="Explicit mapping SYMBOL=CUSIP. Can be repeated, for example --cusip AAPL=037833100.",
    )
    return parser.parse_args()


def resolve_symbol_cusips(symbols: list[str], mappings: list[str]) -> dict[str, str]:
    explicit = parse_cusip_mappings(mappings)
    resolved = {}
    for symbol in symbols:
        if symbol in explicit:
            resolved[symbol] = explicit[symbol]
            continue
        try:
            resolved[symbol] = resolve_cusip(symbol)
        except Exception as exc:
            print(f"{symbol}: CUSIP resolution failed: {exc}")
            resolved[symbol] = ""
    return resolved


def aggregate_dataset_for_cusips(dataset_path: Path, cusips: set[str]) -> dict[str, dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = {cusip: empty_aggregate() for cusip in cusips}
    if not cusips:
        return aggregates

    with zipfile.ZipFile(dataset_path) as archive:
        info_name = find_info_table_member(archive)
        with archive.open(info_name) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", errors="ignore", newline="")
            sample = text.read(4096)
            text.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters="\t,")
            reader = csv.DictReader(text, dialect=dialect)
            columns = {normalize_column(column): column for column in (reader.fieldnames or [])}
            cusip_col = find_column(columns, "cusip")
            shares_col = find_column(columns, "sshprnamt", "shares", "ssh_prnamt")
            value_col = find_column(columns, "value")
            issuer_col = find_column(columns, "nameofissuer", "name_of_issuer", "issuer")
            accession_col = find_column(columns, "accessionnumber", "accession_number")
            if not cusip_col or not shares_col:
                raise RuntimeError(
                    f"SEC 13F table missing required columns: cusip={bool(cusip_col)}, shares={bool(shares_col)}"
                )

            for row in reader:
                cusip = normalize_cusip(row.get(cusip_col))
                if cusip not in cusips:
                    continue
                shares = number_or_zero(row.get(shares_col))
                if shares <= 0:
                    continue
                aggregate = aggregates[cusip]
                aggregate["holder_count"] += 1
                aggregate["institutional_shares"] += shares
                aggregate["reported_value"] += number_or_zero(row.get(value_col))
                if issuer_col:
                    issuer = str(row.get(issuer_col) or "").strip()
                    if issuer:
                        aggregate["issuers"][issuer] += 1
                if accession_col:
                    accession = str(row.get(accession_col) or "").strip()
                    if accession:
                        aggregate["accessions"].add(accession)
    return aggregates


def ownership_row(
    symbol: str,
    cusip: str,
    dataset: str,
    report_period: str,
    aggregate: dict[str, Any],
    client,
) -> dict[str, Any]:
    filing_count = len(aggregate["accessions"]) if aggregate["accessions"] else aggregate["holder_count"]
    shares_outstanding = shares_outstanding_from_cache(client, symbol)
    institutional_shares = number_or_zero(aggregate["institutional_shares"])
    estimated = (institutional_shares / shares_outstanding) * 100 if institutional_shares > 0 and shares_outstanding > 0 else None
    status, error = ownership_status(institutional_shares, estimated)
    return {
        "symbol": symbol,
        "cusip": cusip,
        "dataset": dataset,
        "report_period": report_period,
        "holder_count": aggregate["holder_count"],
        "filing_count": filing_count,
        "institutional_shares": institutional_shares,
        "reported_value": number_or_zero(aggregate["reported_value"]),
        "estimated_ownership_percent": estimated,
        "shares_outstanding_estimate": shares_outstanding or None,
        "top_issuer_names": [issuer for issuer, _count in aggregate["issuers"].most_common(5)],
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "error": error,
    }


def empty_aggregate() -> dict[str, Any]:
    return {
        "holder_count": 0,
        "institutional_shares": 0.0,
        "reported_value": 0.0,
        "issuers": Counter(),
        "accessions": set(),
    }


def upsert_ownership_rows(client, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    client.table("ownership_snapshots").upsert(rows, on_conflict="symbol,report_period").execute()


def upsert_snapshot_ownership(client, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        client.table("stock_snapshots").update(
            {"inst_ownership": row["inst_ownership"], "updated_at": row["updated_at"]}
        ).eq("symbol", row["symbol"]).execute()


def recalculate_cached_ownership(
    client,
    symbols: list[str],
    report_period: str,
    missing_only: bool,
    limit: int,
    dry_run: bool,
    spacing_ms: int,
) -> int:
    rows = load_cached_ownership_rows(client, symbols, report_period, missing_only, limit)
    if not rows:
        print(f"No cached ownership rows to recalculate for report_period={report_period}.")
        return 0

    print(f"Ownership recalculation: {len(rows)} cached rows")
    print(f"report_period: {report_period}")
    print(f"missing_only: {missing_only}")
    print(f"dry_run: {dry_run}")
    print(f"spacing_ms: {spacing_ms}")
    print("")

    updates = []
    snapshot_updates = []
    started = time.time()
    for row in rows:
        symbol = normalize_symbol(row.get("symbol"))
        institutional_shares = number_or_zero(row.get("institutional_shares"))
        shares_outstanding = shares_outstanding_from_cache(client, symbol)
        estimated = (
            (institutional_shares / shares_outstanding) * 100
            if institutional_shares > 0 and shares_outstanding > 0
            else None
        )
        status, error = ownership_status(institutional_shares, estimated)
        update = {
            "symbol": symbol,
            "report_period": report_period,
            "estimated_ownership_percent": estimated,
            "shares_outstanding_estimate": shares_outstanding or None,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "error": error,
        }
        updates.append(update)
        if number_or_zero(estimated) > 0:
            snapshot_updates.append(
                {
                    "symbol": symbol,
                    "inst_ownership": estimated,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        print(
            f"{symbol}: shares={institutional_shares} "
            f"shares_outstanding={shares_outstanding or None} "
            f"ownership={estimated} "
            f"status={status}"
        )
        if spacing_ms > 0:
            time.sleep(spacing_ms / 1000)

    if not dry_run:
        update_cached_ownership_rows(client, updates)
        upsert_snapshot_ownership(client, snapshot_updates)
        print(f"database: updated {len(updates)} ownership rows")
        print(f"database: updated {len(snapshot_updates)} stock_snapshots inst_ownership values")

    duration = time.time() - started
    print("")
    print(f"done: {len(rows)} recalculated rows, {duration:.1f}s")
    return 0


def ownership_status(institutional_shares: float, estimated: float | None) -> tuple[str, str | None]:
    if estimated and estimated > 0:
        return "complete", None
    if institutional_shares > 0:
        return (
            "shares_only",
            "SEC institutional shares found, but cached price/market cap is missing for ownership percent",
        )
    return "missing", "No matching 13F holdings found for CUSIP"


def latest_cached_report_period(client) -> str:
    result = (
        client.table("ownership_snapshots")
        .select("report_period,calculated_at")
        .order("calculated_at", desc=True)
        .limit(1)
        .execute()
    )
    data = result.data or []
    return str(data[0].get("report_period") or "") if data else ""


def load_cached_ownership_rows(
    client,
    symbols: list[str],
    report_period: str,
    missing_only: bool,
    limit: int,
) -> list[dict[str, Any]]:
    query = (
        client.table("ownership_snapshots")
        .select("symbol,report_period,institutional_shares,estimated_ownership_percent,status")
        .eq("report_period", report_period)
        .order("symbol")
    )
    if symbols:
        query = query.in_("symbol", symbols)
    result = query.execute()
    rows = result.data or []
    if missing_only:
        rows = [
            row
            for row in rows
            if row.get("status") != "complete"
            or number_or_zero(row.get("estimated_ownership_percent")) <= 0
        ]
    if limit:
        rows = rows[:limit]
    return rows


def update_cached_ownership_rows(client, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        client.table("ownership_snapshots").update(
            {
                "estimated_ownership_percent": row["estimated_ownership_percent"],
                "shares_outstanding_estimate": row["shares_outstanding_estimate"],
                "calculated_at": row["calculated_at"],
                "status": row["status"],
                "error": row["error"],
            }
        ).eq("symbol", row["symbol"]).eq("report_period", row["report_period"]).execute()


def shares_outstanding_from_cache(client, symbol: str) -> float:
    snapshot = get_snapshot(client, symbol) or {}
    market_cap = number_or_zero(snapshot.get("market_cap"))
    price = number_or_zero(snapshot.get("price"))
    return market_cap / price if market_cap > 0 and price > 0 else 0.0


def filter_missing_ownership(client, symbols: list[str], report_period: str) -> list[str]:
    result = (
        client.table("ownership_snapshots")
        .select("symbol,status,estimated_ownership_percent")
        .eq("report_period", report_period)
        .in_("symbol", symbols)
        .execute()
    )
    complete = {
        normalize_symbol(row.get("symbol"))
        for row in (result.data or [])
        if row.get("status") == "complete" and number_or_zero(row.get("estimated_ownership_percent")) > 0
    }
    return [symbol for symbol in symbols if symbol not in complete]


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


def parse_cusip_mappings(values: list[str]) -> dict[str, str]:
    mappings = {}
    for value in values:
        if "=" not in value:
            continue
        symbol, cusip = value.split("=", 1)
        mappings[normalize_symbol(symbol)] = normalize_cusip(cusip)
    return mappings


def report_period_from_dataset(path: Path) -> str:
    return path.name.replace("_form13f.zip", "").replace(".zip", "")


def find_info_table_member(archive: zipfile.ZipFile) -> str:
    names = archive.namelist()
    preferred = [name for name in names if "infotable" in name.lower()]
    if preferred:
        return preferred[0]
    tabular = [name for name in names if name.lower().endswith((".tsv", ".txt", ".csv"))]
    if tabular:
        return tabular[0]
    raise RuntimeError(f"No tabular information table found in {archive.filename}")


def normalize_column(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def find_column(columns: dict[str, str], *candidates: str) -> str:
    for candidate in candidates:
        key = normalize_column(candidate)
        if key in columns:
            return columns[key]
    for candidate in candidates:
        key = normalize_column(candidate)
        for normalized, original in columns.items():
            if key in normalized:
                return original
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
