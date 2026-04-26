from __future__ import annotations

import argparse
import csv
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.market_data import SEC_TICKER_CIK_URL, normalize_symbol, number_or_zero, sec_lookup_headers
from app.settings import get_settings
from app.supabase_db import get_snapshot, make_service_client


SEC_13F_DATASETS_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
SEC_13F_SECURITIES_URL = "https://www.sec.gov/rules-regulations/staff-guidance/official-list-section-13f-securities"
CACHE_DIR = Path("sec_cache")


def main() -> int:
    args = parse_args()
    symbol = normalize_symbol(args.symbol)
    CACHE_DIR.mkdir(exist_ok=True)

    cusip = normalize_cusip(args.cusip) if args.cusip else resolve_cusip(symbol)
    if not cusip:
        print(f"{symbol}: could not resolve CUSIP from SEC 13F securities list.")
        print("Retry with an explicit CUSIP:")
        print(f"  python check_sec_13f_ownership.py {symbol} --cusip CUSIPHERE")
        return 2

    dataset_url = args.dataset_url or latest_13f_dataset_url()
    dataset_path = download_to_cache(dataset_url, args.force_download)
    result = aggregate_13f_dataset(dataset_path, cusip)
    result["symbol"] = symbol
    result["cusip"] = cusip
    result["dataset"] = dataset_path.name

    shares_outstanding = shares_outstanding_from_cache(symbol)
    if shares_outstanding > 0 and result["institutional_shares"] > 0:
        result["estimated_ownership_percent"] = (result["institutional_shares"] / shares_outstanding) * 100
        result["shares_outstanding_estimate"] = shares_outstanding
    else:
        result["estimated_ownership_percent"] = None
        result["shares_outstanding_estimate"] = None

    print(json.dumps(result, indent=2, default=str))
    return 0 if result["holder_count"] > 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prototype SEC 13F ownership aggregation for one ticker/CUSIP.")
    parser.add_argument("symbol", help="Ticker symbol, for example AAPL.")
    parser.add_argument("--cusip", help="Explicit CUSIP override. Recommended if automatic matching is ambiguous.")
    parser.add_argument("--dataset-url", help="Explicit SEC 13F data-set ZIP URL. Defaults to latest listed SEC ZIP.")
    parser.add_argument("--force-download", action="store_true", help="Re-download cached SEC ZIP.")
    return parser.parse_args()


def latest_13f_dataset_url() -> str:
    CACHE_DIR.mkdir(exist_ok=True)
    response = requests.get(SEC_13F_DATASETS_URL, headers=sec_lookup_headers(), timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        if href.lower().endswith(".zip"):
            return urljoin(SEC_13F_DATASETS_URL, href)
    raise RuntimeError("No SEC 13F data-set ZIP link found.")


def latest_13f_securities_txt_url() -> str:
    CACHE_DIR.mkdir(exist_ok=True)
    response = requests.get(SEC_13F_SECURITIES_URL, headers=sec_lookup_headers(), timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        text = link.get_text(" ", strip=True).lower()
        if href.lower().endswith(".txt") or text == "txt":
            return urljoin(SEC_13F_SECURITIES_URL, href)
    raise RuntimeError("No SEC 13F securities TXT link found.")


def download_to_cache(url: str, force_download: bool = False) -> Path:
    filename = sanitize_filename(url.rsplit("/", 1)[-1] or "sec_13f_dataset.zip")
    path = CACHE_DIR / filename
    if path.exists() and path.stat().st_size > 0 and not force_download:
        return path

    print(f"downloading: {url}")
    with requests.get(url, headers=sec_lookup_headers(), timeout=60, stream=True) as response:
        response.raise_for_status()
        with path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return path


def resolve_cusip(symbol: str) -> str:
    company = sec_company_for_symbol(symbol)
    if not company:
        return ""
    issuer_tokens = issuer_search_tokens(company.get("title") or "")
    if not issuer_tokens:
        return ""

    securities = fetch_13f_security_list()
    candidates = []
    for row in securities:
        issuer = row["issuer_name"]
        score = token_score(issuer_tokens, issuer)
        if score > 0:
            candidates.append((score, row))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        return ""
    return candidates[0][1]["cusip"]


def sec_company_for_symbol(symbol: str) -> dict[str, Any] | None:
    response = requests.get(SEC_TICKER_CIK_URL, headers=sec_lookup_headers(), timeout=30)
    response.raise_for_status()
    for row in (response.json() or {}).values():
        if normalize_symbol(row.get("ticker")) == symbol:
            return row
    return None


def fetch_13f_security_list() -> list[dict[str, str]]:
    CACHE_DIR.mkdir(exist_ok=True)
    txt_url = latest_13f_securities_txt_url()
    cache_path = CACHE_DIR / sanitize_filename(txt_url.rsplit("/", 1)[-1] or "13f_securities.txt")
    if cache_path.exists() and cache_path.stat().st_size > 0:
        text = cache_path.read_text(encoding="utf-8", errors="ignore")
    else:
        response = requests.get(txt_url, headers=sec_lookup_headers(), timeout=30)
        response.raise_for_status()
        text = response.text
        cache_path.write_text(text, encoding="utf-8")

    rows = []
    for line in text.splitlines():
        if len(line) < 40:
            continue
        cusip = normalize_cusip(line[0:9])
        issuer = line[10:40].strip()
        security_class = line[40:67].strip()
        if re.fullmatch(r"[A-Z0-9]{9}", cusip) and issuer:
            rows.append({"cusip": cusip, "issuer_name": issuer, "class": security_class})
    return rows


def aggregate_13f_dataset(dataset_path: Path, cusip: str) -> dict[str, Any]:
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

            holder_count = 0
            institutional_shares = 0.0
            reported_value = 0.0
            issuers = Counter()
            accessions = set()
            for row in reader:
                if normalize_cusip(row.get(cusip_col)) != cusip:
                    continue
                shares = number_or_zero(row.get(shares_col))
                value = number_or_zero(row.get(value_col))
                if shares <= 0:
                    continue
                holder_count += 1
                institutional_shares += shares
                reported_value += value
                if issuer_col:
                    issuers[str(row.get(issuer_col) or "").strip()] += 1
                if accession_col:
                    accessions.add(str(row.get(accession_col) or "").strip())

    return {
        "holder_count": holder_count,
        "filing_count": len(accessions) if accessions else holder_count,
        "institutional_shares": institutional_shares,
        "reported_value": reported_value,
        "top_issuer_names": [issuer for issuer, _count in issuers.most_common(5) if issuer],
    }


def find_info_table_member(archive: zipfile.ZipFile) -> str:
    names = archive.namelist()
    preferred = [name for name in names if "infotable" in name.lower()]
    if preferred:
        return preferred[0]
    tabular = [name for name in names if name.lower().endswith((".tsv", ".txt", ".csv"))]
    if tabular:
        return tabular[0]
    raise RuntimeError(f"No tabular information table found in {archive.filename}")


def shares_outstanding_from_cache(symbol: str) -> float:
    try:
        client = make_service_client(get_settings())
        snapshot = get_snapshot(client, symbol) or {}
    except Exception:
        return 0.0
    market_cap = number_or_zero(snapshot.get("market_cap"))
    price = number_or_zero(snapshot.get("price"))
    if market_cap > 0 and price > 0:
        return market_cap / price
    return 0.0


def issuer_search_tokens(name: str) -> set[str]:
    stop = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "PLC", "LTD", "LIMITED", "CLASS"}
    tokens = set(re.findall(r"[A-Z0-9]+", name.upper()))
    return {token for token in tokens if len(token) > 1 and token not in stop}


def token_score(tokens: set[str], issuer: str) -> int:
    issuer_tokens = issuer_search_tokens(issuer)
    return len(tokens & issuer_tokens)


def normalize_cusip(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())[:9]


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


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


if __name__ == "__main__":
    raise SystemExit(main())
