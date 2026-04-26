from __future__ import annotations

import json
import sys
from typing import Any


def main() -> int:
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").strip().upper()

    try:
        from openbb import obb
    except ImportError:
        print("OpenBB is not installed in this Python environment.")
        print("Install test dependency:")
        print("  pip install openbb")
        print("")
        print("After install, run:")
        print(f"  python check_openbb_ownership.py {symbol}")
        return 2

    print(f"symbol: {symbol}")
    print("probe: obb.equity.ownership.institutional")
    institutional = call_openbb(
        lambda: obb.equity.ownership.institutional(symbol=symbol),
        "institutional",
    )
    print_result_summary(institutional)

    print("")
    print("probe: obb.equity.ownership.equity")
    equity = call_openbb(
        lambda: obb.equity.ownership.equity(symbol=symbol, limit=10),
        "equity",
    )
    print_result_summary(equity)

    return 0


def call_openbb(callback, label: str) -> dict[str, Any]:
    try:
        result = callback()
    except Exception as exc:
        return {
            "label": label,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "label": label,
        "ok": True,
        "raw_type": type(result).__name__,
        "payload": normalize_openbb_result(result),
    }


def normalize_openbb_result(result: Any) -> Any:
    if hasattr(result, "to_df"):
        try:
            df = result.to_df()
            return {
                "shape": list(df.shape),
                "columns": list(df.columns),
                "rows": df.head(10).to_dict(orient="records"),
            }
        except Exception as exc:
            return {"to_df_error": f"{type(exc).__name__}: {exc}"}

    if hasattr(result, "model_dump"):
        try:
            return result.model_dump()
        except Exception:
            pass

    if hasattr(result, "dict"):
        try:
            return result.dict()
        except Exception:
            pass

    return str(result)


def print_result_summary(result: dict[str, Any]) -> None:
    if not result["ok"]:
        print(f"{result['label']}: error {result['error']}")
        return

    payload = result["payload"]
    print(f"{result['label']}: ok {result['raw_type']}")
    if isinstance(payload, dict) and "shape" in payload:
        print(f"shape: {payload['shape']}")
        print(f"columns: {', '.join(payload['columns'])}")
        print("rows:")
        print(json.dumps(payload["rows"], indent=2, default=str)[:5000])
        return

    print(json.dumps(payload, indent=2, default=str)[:5000])


if __name__ == "__main__":
    raise SystemExit(main())
