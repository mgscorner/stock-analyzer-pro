from __future__ import annotations

import argparse
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from app.market_data import normalize_symbol
from app.settings import get_settings
from app.supabase_db import make_service_client


HEADERS = {
    "User-Agent": "AnalyzerApp index universe bootstrap contact@example.com",
    "Accept": "text/html,text/plain,*/*",
}


@dataclass(frozen=True)
class IndexSource:
    universe_name: str
    url: str
    table_match: str
    symbol_columns: tuple[str, ...]
    name_columns: tuple[str, ...]
    sector_columns: tuple[str, ...] = ()


SOURCES = [
    IndexSource(
        universe_name="sp500",
        url="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        table_match="Symbol",
        symbol_columns=("Symbol", "Ticker"),
        name_columns=("Security", "Company"),
        sector_columns=("GICS Sector", "Sector"),
    ),
    IndexSource(
        universe_name="nasdaq100",
        url="https://en.wikipedia.org/wiki/Nasdaq-100",
        table_match="Ticker",
        symbol_columns=("Ticker", "Symbol"),
        name_columns=("Company", "Security"),
        sector_columns=("GICS Sector", "Sector"),
    ),
    IndexSource(
        universe_name="dow30",
        url="https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
        table_match="Company",
        symbol_columns=("Symbol", "Ticker"),
        name_columns=("Company", "Security"),
        sector_columns=("Sector", "Industry"),
    ),
]


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_ok = True
    universe_rows: list[dict[str, str]] = []
    for source in SOURCES:
        try:
            frame = fetch_index_frame(source)
            output_file = output_dir / f"{source.universe_name}_tickers.csv"
            write_frame(frame, output_file)
            universe_rows.extend(
                {"universe_name": source.universe_name, "symbol": row["symbol"]}
                for row in frame.to_dict(orient="records")
            )
            print(f"{source.universe_name}: {len(frame)} symbols -> {output_file}")
        except Exception as exc:
            all_ok = False
            print(f"{source.universe_name}: failed {exc}")

    if universe_rows:
        combined = pd.DataFrame(universe_rows).drop_duplicates().sort_values(["universe_name", "symbol"])
        combined_file = output_dir / "index_universes.csv"
        combined.to_csv(combined_file, index=False)
        print(f"combined: {len(combined)} universe rows -> {combined_file}")

        if args.write_db:
            upsert_universe_rows(combined.to_dict(orient="records"))
            print(f"database: upserted {len(combined)} rows into stock_universes")
        elif args.diff_db:
            print_db_diff(combined.to_dict(orient="records"))

    return 0 if all_ok else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch index constituent lists and optionally update stock_universes.")
    parser.add_argument(
        "--output-dir",
        default="index_exports",
        help="Directory for generated CSV files. Default: index_exports.",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Upsert fetched universe rows into Supabase stock_universes.",
    )
    parser.add_argument(
        "--diff-db",
        action="store_true",
        help="Print added/removed rows compared with Supabase stock_universes without writing.",
    )
    return parser.parse_args()


def fetch_index_frame(source: IndexSource) -> pd.DataFrame:
    response = requests.get(source.url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    tables = pd.read_html(io.StringIO(response.text), match=source.table_match)
    for table in tables:
        frame = normalize_index_table(table, source)
        if not frame.empty:
            return frame
    raise ValueError("No usable constituent table found")


def normalize_index_table(table: pd.DataFrame, source: IndexSource) -> pd.DataFrame:
    table = flatten_columns(table)
    symbol_col = first_existing_column(table, source.symbol_columns)
    name_col = first_existing_column(table, source.name_columns)
    sector_col = first_existing_column(table, source.sector_columns)
    if not symbol_col or not name_col:
        return pd.DataFrame(columns=["symbol", "name", "sector"])

    rows = []
    for _idx, row in table.iterrows():
        symbol = normalize_index_symbol(row.get(symbol_col))
        name = clean_text(row.get(name_col))
        sector = clean_text(row.get(sector_col)) if sector_col else ""
        if not symbol or not name or symbol in {"SYMBOL", "TICKER"}:
            continue
        rows.append({"symbol": symbol, "name": name, "sector": sector})

    frame = pd.DataFrame(rows).drop_duplicates(subset=["symbol"]).sort_values("symbol")
    return frame.reset_index(drop=True)


def flatten_columns(table: pd.DataFrame) -> pd.DataFrame:
    if isinstance(table.columns, pd.MultiIndex):
        table = table.copy()
        table.columns = [
            " ".join(str(part) for part in column if str(part) != "nan").strip()
            for column in table.columns
        ]
    return table


def first_existing_column(table: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    normalized = {normalize_header(column): column for column in table.columns}
    for candidate in candidates:
        match = normalized.get(normalize_header(candidate))
        if match:
            return str(match)
    for candidate in candidates:
        candidate_norm = normalize_header(candidate)
        for norm, original in normalized.items():
            if candidate_norm in norm:
                return str(original)
    return None


def normalize_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def normalize_index_symbol(value: Any) -> str:
    symbol = normalize_symbol(str(value or "").split()[0])
    return symbol.replace(".", "-")


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def write_frame(frame: pd.DataFrame, output_file: Path) -> None:
    columns = ["symbol", "name"]
    if "sector" in frame.columns and frame["sector"].astype(bool).any():
        columns.append("sector")
    frame.to_csv(output_file, columns=columns, index=False)


def upsert_universe_rows(rows: list[dict[str, str]]) -> None:
    client = make_service_client(get_settings())
    payload = [{"universe_name": row["universe_name"], "symbol": row["symbol"]} for row in rows]
    client.table("stock_universes").upsert(payload, on_conflict="universe_name,symbol").execute()


def print_db_diff(rows: list[dict[str, str]]) -> None:
    client = make_service_client(get_settings())
    result = client.table("stock_universes").select("universe_name,symbol").execute()
    existing = {(row["universe_name"], row["symbol"]) for row in (result.data or [])}
    fetched = {(row["universe_name"], row["symbol"]) for row in rows}
    added = sorted(fetched - existing)
    removed = sorted(existing - fetched)

    print(f"diff: {len(added)} added, {len(removed)} removed")
    if added:
        print("added:")
        for universe_name, symbol in added[:100]:
            print(f"  {universe_name} {symbol}")
        if len(added) > 100:
            print(f"  ... {len(added) - 100} more")
    if removed:
        print("removed:")
        for universe_name, symbol in removed[:100]:
            print(f"  {universe_name} {symbol}")
        if len(removed) > 100:
            print(f"  ... {len(removed) - 100} more")


if __name__ == "__main__":
    raise SystemExit(main())
