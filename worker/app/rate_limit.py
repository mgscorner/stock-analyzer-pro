from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class MarketRequestLimiter:
    enabled: bool = True
    quote_min_interval_ms: int = 300
    history_min_interval_ms: int = 500
    fundamentals_min_interval_ms: int = 30000
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_call_at: dict[str, float] = field(default_factory=dict)

    def wait(self, layer: str, bypass: bool = False) -> None:
        if not self.enabled or bypass:
            return

        interval = self.interval_seconds(layer)
        if interval <= 0:
            return

        with self._lock:
            now = time.monotonic()
            last_call_at = self._last_call_at.get(layer, 0.0)
            wait_seconds = max(0.0, interval - (now - last_call_at))
            if wait_seconds:
                time.sleep(wait_seconds)
            self._last_call_at[layer] = time.monotonic()

    def interval_seconds(self, layer: str) -> float:
        if layer == "quote":
            return self.quote_min_interval_ms / 1000
        if layer == "history":
            return self.history_min_interval_ms / 1000
        if layer == "fundamentals":
            return self.fundamentals_min_interval_ms / 1000
        return self.quote_min_interval_ms / 1000
