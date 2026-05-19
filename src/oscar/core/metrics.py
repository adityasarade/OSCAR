"""Metric aggregation utilities.

Shared between the FastAPI /metrics endpoint and the `oscar metrics` CLI.
Reads the rotating audit JSONL on disk; never imports the agent so it
stays cheap and safe to call without Vertex AI credentials.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Optional

from oscar.config.settings import settings

_RISK_TIERS = ("low", "medium", "high", "dangerous", "unknown")


def audit_path() -> Path:
    return settings.data_dir / "logs" / "audit.jsonl"


def summarize_audit_log(path: Optional[Path] = None) -> Dict[str, Any]:
    """Aggregate the audit JSONL into a single summary dict.

    Returns counters for total entries, per-tool calls, per-risk tier,
    approval/rejection counts, and latency stats (mean/median/p95) when
    latency_ms is present on entries.
    """
    target = path or audit_path()
    summary: Dict[str, Any] = {
        "entries": 0,
        "by_tool": {},
        "by_risk": {tier: 0 for tier in _RISK_TIERS},
        "approved": 0,
        "rejected": 0,
        "latency_ms": None,
    }
    if not target.exists():
        return summary

    latencies: list[float] = []
    with open(target, "r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue

            tool = entry.get("tool")
            if not tool:
                continue

            summary["entries"] += 1
            summary["by_tool"][tool] = summary["by_tool"].get(tool, 0) + 1

            risk = entry.get("risk", "unknown")
            if risk not in summary["by_risk"]:
                risk = "unknown"
            summary["by_risk"][risk] += 1

            if entry.get("approved", True):
                summary["approved"] += 1
            else:
                summary["rejected"] += 1

            latency_ms = entry.get("latency_ms")
            if isinstance(latency_ms, (int, float)):
                latencies.append(float(latency_ms))

    if latencies:
        latencies_sorted = sorted(latencies)
        p95_index = max(0, int(round(0.95 * (len(latencies_sorted) - 1))))
        summary["latency_ms"] = {
            "count": len(latencies_sorted),
            "mean": round(mean(latencies_sorted), 2),
            "median": round(median(latencies_sorted), 2),
            "p95": round(latencies_sorted[p95_index], 2),
            "max": round(latencies_sorted[-1], 2),
        }

    return summary


def llm_performance() -> Optional[Dict[str, Any]]:
    """Return Asterix LLMProviderManager performance metrics, or None.

    The asterix runtime singleton is only populated once an Agent has
    been instantiated. Callers should treat None as "agent never ran in
    this process".
    """
    try:
        from asterix.core.llm_manager import llm_manager

        if not hasattr(llm_manager, "get_performance_metrics"):
            return None
        return llm_manager.get_performance_metrics()
    except Exception:
        return None
