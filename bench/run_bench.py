"""GitTaskBench-Lite runner for OSCAR.

Tracks:
  - T4 safety classifier precision/recall    (offline; no LLM)
  - T3 tool-selection accuracy + Jaccard     (requires Vertex auth)
  - T5 latency / token / cost stats          (piggy-backs T3)
  - T1 branch-comparison precision/recall    (stub until you add cases)

Usage:
    python bench/run_bench.py                     # run everything
    python bench/run_bench.py --offline           # T4 only
    python bench/run_bench.py --tasks t3,t4       # subset

Results write to bench/results/<UTC-timestamp>/summary.json plus a
per-track JSONL of individual case outcomes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    import yaml
except ImportError as exc:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1) from exc

BENCH_DIR = Path(__file__).resolve().parent
TASKS_DIR = BENCH_DIR / "tasks"
RESULTS_ROOT = BENCH_DIR / "results"

# Gemini 2.5 Flash list price as of 2026-01 — USD per million tokens.
GEMINI_FLASH_USD_PER_M_INPUT = 0.30
GEMINI_FLASH_USD_PER_M_OUTPUT = 2.50


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------


@dataclass
class TrackResult:
    name: str
    cases: List[Dict[str, Any]] = field(default_factory=list)
    aggregate: Dict[str, Any] = field(default_factory=dict)


def _load_cases(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return list(data.get("cases") or [])


# ---------------------------------------------------------------------------
# T4 - safety classifier (offline)
# ---------------------------------------------------------------------------


def run_t4_safety() -> TrackResult:
    from oscar.core.safety import assess_risk

    track = TrackResult(name="t4_safety")
    cases = _load_cases(TASKS_DIR / "t4_safety.yaml")
    if not cases:
        track.aggregate = {"skipped": "no cases"}
        return track

    confusion: Dict[str, Counter] = {}
    correct = 0
    for case in cases:
        expected = case["expected_risk"]
        got = assess_risk(case["tool"], case.get("arguments") or {})
        passed = got == expected
        correct += int(passed)
        confusion.setdefault(expected, Counter())[got] += 1
        track.cases.append(
            {
                "id": case["id"],
                "tool": case["tool"],
                "expected": expected,
                "got": got,
                "pass": passed,
            }
        )

    accuracy = correct / len(cases)

    per_tier: Dict[str, Dict[str, float]] = {}
    tiers = sorted({c["expected_risk"] for c in cases})
    for tier in tiers:
        tp = confusion.get(tier, Counter()).get(tier, 0)
        fn = sum(v for k, v in confusion.get(tier, Counter()).items() if k != tier)
        fp = sum(
            row.get(tier, 0)
            for other, row in confusion.items()
            if other != tier
        )
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        per_tier[tier] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
        }

    track.aggregate = {
        "cases": len(cases),
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "per_tier": per_tier,
        "confusion": {k: dict(v) for k, v in confusion.items()},
    }
    return track


# ---------------------------------------------------------------------------
# T3 - tool selection accuracy  (and T5 latency piggy-back)
# ---------------------------------------------------------------------------


def _read_tail_audit_lines(audit_path: Path, start_offset: int) -> List[dict]:
    """Return audit entries appended after start_offset bytes."""
    if not audit_path.exists():
        return []
    entries = []
    with open(audit_path, "r", encoding="utf-8") as handle:
        handle.seek(start_offset)
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if entry.get("tool"):
                entries.append(entry)
    return entries


def run_t3_tool_selection(quiet: bool) -> TrackResult:
    track = TrackResult(name="t3_tool_selection")
    cases = _load_cases(TASKS_DIR / "t3_tool_selection.yaml")
    if not cases:
        track.aggregate = {"skipped": "no cases"}
        return track

    from oscar.core import agent as agent_mod
    from oscar.core.agent import get_agent
    from oscar.core.metrics import audit_path, llm_performance

    # Bench mode auto-approves so we measure tool *selection*, not the
    # interactive safety gate (which would default-reject without stdin).
    # agent_mod has its own binding from `from oscar.core.safety import ...`
    # so we override the binding it uses.
    agent_mod.on_before_tool_call = lambda tool_name, arguments: True

    audit_file = audit_path()
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.touch(exist_ok=True)

    agent = get_agent()
    exact = 0
    jaccard_total = 0.0

    perf_before = llm_performance() or {}

    for case in cases:
        expected = set(case["expected_tools"])
        offset = audit_file.stat().st_size
        started = time.perf_counter()
        try:
            response = agent.chat(case["prompt"])
            error: Optional[str] = None
        except Exception as exc:  # pragma: no cover - depends on Vertex auth
            response = ""
            error = str(exc)
        elapsed_ms = (time.perf_counter() - started) * 1000

        new_entries = _read_tail_audit_lines(audit_file, offset)
        called = {entry["tool"] for entry in new_entries}
        union = expected | called
        jaccard = len(expected & called) / len(union) if union else 0.0
        is_exact = called == expected
        if is_exact:
            exact += 1
        jaccard_total += jaccard

        case_record = {
            "id": case["id"],
            "prompt": case["prompt"],
            "expected": sorted(expected),
            "called": sorted(called),
            "exact": is_exact,
            "jaccard": round(jaccard, 4),
            "latency_ms": round(elapsed_ms, 2),
            "response_chars": len(response),
        }
        if error:
            case_record["error"] = error
        track.cases.append(case_record)
        if not quiet:
            print(
                f"[t3] {case['id']:<24} "
                f"expected={sorted(expected)} called={sorted(called)} "
                f"exact={is_exact} jaccard={jaccard:.2f} "
                f"{elapsed_ms:.0f}ms"
            )

    perf_after = llm_performance() or {}

    track.aggregate = {
        "cases": len(cases),
        "exact_match": exact,
        "exact_match_rate": round(exact / len(cases), 4),
        "mean_jaccard": round(jaccard_total / len(cases), 4),
        "llm_before": perf_before,
        "llm_after": perf_after,
    }
    return track


# ---------------------------------------------------------------------------
# T5 - cost + latency from audit log
# ---------------------------------------------------------------------------


def run_t5_runtime_summary() -> TrackResult:
    from oscar.core.metrics import llm_performance, summarize_audit_log

    track = TrackResult(name="t5_runtime")
    audit = summarize_audit_log()
    perf = llm_performance() or {}

    estimated_cost_usd: Optional[float] = None
    providers = perf.get("providers") or {}
    gemini = providers.get("gemini") or {}
    total_tokens = gemini.get("total_tokens")
    if isinstance(total_tokens, (int, float)) and total_tokens > 0:
        estimated_cost_usd = round(
            (total_tokens * GEMINI_FLASH_USD_PER_M_INPUT) / 1_000_000,
            6,
        )

    track.aggregate = {
        "audit": audit,
        "llm": perf,
        "estimated_input_cost_usd_naive": estimated_cost_usd,
        "pricing_notes": (
            "Naive: treats all tokens as input. Re-compute with actual "
            "input/output split if you start tracking them separately."
        ),
    }
    return track


# ---------------------------------------------------------------------------
# T1 - branch comparison correctness  (stub)
# ---------------------------------------------------------------------------


def run_t1_branch_compare(quiet: bool) -> TrackResult:
    track = TrackResult(name="t1_branch_compare")
    cases = _load_cases(TASKS_DIR / "t1_branch_compare.yaml")
    if not cases:
        track.aggregate = {"skipped": "no cases — add fixtures to enable"}
        return track

    precision_total = 0.0
    recall_total = 0.0
    for case in cases:
        repo = case["repo"]
        result = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            track.cases.append(
                {"id": case["id"], "error": "not a git repo", "repo": repo}
            )
            continue

        # Run git_compare from inside the target repo. git_compare uses
        # subprocess so we cd via cwd= would need a refactor; for the
        # stub, we shell out directly to get a comparable diff.
        diff_result = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", case["base"], case["head"]],
            capture_output=True,
            text=True,
            check=False,
        )
        actual_files = {
            line.strip()
            for line in diff_result.stdout.splitlines()
            if line.strip()
        }
        expected_files = set(case.get("expected_files") or [])

        tp = len(actual_files & expected_files)
        precision = tp / len(actual_files) if actual_files else None
        recall = tp / len(expected_files) if expected_files else None
        if precision is not None:
            precision_total += precision
        if recall is not None:
            recall_total += recall

        track.cases.append(
            {
                "id": case["id"],
                "expected": sorted(expected_files),
                "actual": sorted(actual_files),
                "precision": precision,
                "recall": recall,
            }
        )
        if not quiet:
            print(
                f"[t1] {case['id']:<24} P={precision} R={recall} "
                f"(expected {len(expected_files)} files, "
                f"got {len(actual_files)})"
            )

    n = len(cases) or 1
    track.aggregate = {
        "cases": len(cases),
        "mean_precision": round(precision_total / n, 4),
        "mean_recall": round(recall_total / n, 4),
        "note": "Stub uses raw `git diff --name-only`; swap in git_compare "
                "for an end-to-end check once you parse its text output.",
    }
    return track


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


TRACKS: Dict[str, Callable[..., TrackResult]] = {
    "t1": lambda args: run_t1_branch_compare(args.quiet),
    "t3": lambda args: run_t3_tool_selection(args.quiet),
    "t4": lambda args: run_t4_safety(),
    "t5": lambda args: run_t5_runtime_summary(),
}

OFFLINE_TRACKS = {"t4", "t5", "t1"}


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OSCAR bench runner")
    parser.add_argument(
        "--tasks",
        default="t1,t3,t4,t5",
        help="Comma-separated track ids (default: t1,t3,t4,t5)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip tracks that require Vertex AI authentication",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case logging",
    )
    return parser.parse_args(list(argv))


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    requested = [t.strip() for t in args.tasks.split(",") if t.strip()]

    if args.offline:
        requested = [t for t in requested if t in OFFLINE_TRACKS]
        if not args.quiet:
            print(f"Offline mode: running {requested}")

    run_dir = RESULTS_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "tracks": {},
    }

    for track_id in requested:
        runner = TRACKS.get(track_id)
        if runner is None:
            print(f"Unknown track: {track_id}", file=sys.stderr)
            continue
        if not args.quiet:
            print(f"\n--- {track_id} ---")
        result = runner(args)
        track_path = run_dir / f"{track_id}.jsonl"
        with open(track_path, "w", encoding="utf-8") as handle:
            for case in result.cases:
                handle.write(json.dumps(case) + "\n")
        summary["tracks"][track_id] = result.aggregate

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary_path = run_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    if not args.quiet:
        print(f"\nWrote summary to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
