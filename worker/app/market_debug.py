from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any


@dataclass
class MarketRequestLogger:
    enabled: bool = False
    job_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    sequence_number: int = 0

    def record(
        self,
        symbol: str,
        layer: str,
        source: str,
        started_at: datetime,
        duration_ms: int,
        ok: bool,
        status_code: int | None = None,
        error: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        self.sequence_number += 1
        self.events.append(
            {
                "job_id": self.job_id,
                "symbol": symbol,
                "layer": layer,
                "source": source,
                "sequence_number": self.sequence_number,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
                "ok": ok,
                "status_code": status_code,
                "error": redact_secret(error)[:1000] if error else None,
            }
        )

    def track(self, symbol: str, layer: str, source: str):
        return MarketRequestSpan(self, symbol, layer, source)


def redact_secret(value: str) -> str:
    return re.sub(r"(?i)(apikey|token)=([^&\s]+)", r"\1=REDACTED", value)


class MarketRequestSpan:
    def __init__(self, logger: MarketRequestLogger, symbol: str, layer: str, source: str) -> None:
        self.logger = logger
        self.symbol = symbol
        self.layer = layer
        self.source = source
        self.started_at = datetime.now(timezone.utc)
        self.start = perf_counter()
        self.status_code: int | None = None

    def __enter__(self) -> "MarketRequestSpan":
        return self

    def __exit__(self, exc_type, exc, _tb) -> bool:
        duration_ms = int((perf_counter() - self.start) * 1000)
        self.logger.record(
            symbol=self.symbol,
            layer=self.layer,
            source=self.source,
            started_at=self.started_at,
            duration_ms=duration_ms,
            ok=exc is None,
            status_code=self.status_code,
            error=str(exc) if exc else None,
        )
        return False
