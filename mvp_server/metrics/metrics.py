from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, Dict, List


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lo = int(index)
    hi = min(lo + 1, len(ordered) - 1)
    frac = index - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: DefaultDict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: DefaultDict[str, List[float]] = defaultdict(list)

    def inc(self, key: str, amount: int = 1) -> None:
        self._counters[key] += amount

    def set_gauge(self, key: str, value: float) -> None:
        self._gauges[key] = value

    def observe(self, key: str, value: float) -> None:
        self._histograms[key].append(float(value))

    def snapshot(self) -> Dict[str, Dict[str, float | dict[str, float]]]:
        histograms: Dict[str, Dict[str, float]] = {}
        for key, values in self._histograms.items():
            histograms[key] = {
                "count": float(len(values)),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
                "min": min(values) if values else 0.0,
                "max": max(values) if values else 0.0,
            }
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": histograms,
        }
