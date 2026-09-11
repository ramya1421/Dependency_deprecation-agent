"""Latency metrics: p50 and p95 from a list of elapsed-second measurements."""
from __future__ import annotations

import statistics


def p50(latencies_seconds: list[float]) -> float:
    if not latencies_seconds:
        return 0.0
    return statistics.median(latencies_seconds)


def p95(latencies_seconds: list[float]) -> float:
    if not latencies_seconds:
        return 0.0
    sorted_lat = sorted(latencies_seconds)
    # Nearest-rank method.
    idx = max(int(len(sorted_lat) * 0.95) - 1, 0)
    return sorted_lat[idx]


def summarise(latencies_seconds: list[float]) -> dict[str, float]:
    if not latencies_seconds:
        return {"p50": 0.0, "p95": 0.0, "mean": 0.0, "max": 0.0}
    return {
        "p50": p50(latencies_seconds),
        "p95": p95(latencies_seconds),
        "mean": statistics.mean(latencies_seconds),
        "max": max(latencies_seconds),
    }
