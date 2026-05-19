# OSCAR v0.4.0 — Metrics & Evaluation Results

All numbers below are produced from the repository at the current `main`
HEAD. Numbers under **C/D/E** were measured by `bench/run_bench.py` on
2026-05-20; re-run any time with `python bench/run_bench.py`.

---

## A. Static surface area

| Metric | Value | How verified |
|---|---|---|
| Backend Python LOC — `tools/` + `core/` + `api/` | **2,308** | `wc -l src/oscar/{tools,core,api}/*.py` |
| Total Python files in `src/oscar/` | **19** | `find src/oscar -name '*.py' \| wc -l` |
| Tools registered with the agent | **15** (9 git · 4 browser · 1 shell · 1 web search) | `grep "agent.tool" src/oscar/core/agent.py` |
| FastAPI HTTP endpoints | **12** — `/health`, `/chat`, `/chat/stream`, `/chat/confirm`, `/chat/cancel`, `/history`, `/branches`, `/compare`, `/review`, `/memory`, `/metrics`, `/status` | `grep "^@app\\." src/oscar/api/server.py` |
| Pydantic request/response models | **7** | `grep "class .*(BaseModel)" src/oscar/api/server.py` |
| SSE event types | **6** — `step`, `confirm`, `response`, `error`, `cancelled`, `done` | `grep '"type":' src/oscar/{api,core}/*.py` |
| Test functions | **15** across 3 suites (`test_safety` 6 · `test_api` 7 · `test_git_tool` 2) | `grep -c "^def test_" tests/test_*.py` |
| VS Code modules · LOC | **4 .ts files · 508 LOC** | `wc -l vscode-oscar/src/*.ts` |
| CI Python matrix | **3.10 / 3.11 / 3.12** | `.github/workflows/ci.yml` |
| Commits on `main` | **58** | `git log --oneline main \| wc -l` |
| Development span | **2025-08-10 → 2026-05-20** (~9 months) | `git log --reverse` |

---

## B. Safety model — static description

| Metric | Value |
|---|---|
| Risk tiers | **4** — low / medium / high / dangerous |
| Dangerous-command regex patterns | **8** |
| High-risk keywords | **5** |
| Medium-risk keywords | **5** |
| Tools auto-classified medium-by-default | **3** (`git_push`, `git_checkout`, `git_commit`) |
| Shell command allowlist | **22 commands** |
| Confirmation timeout | **300 s** (defaults to reject) |
| Dangerous-tier override | typed literal `CONFIRM` required |
| Per-call audit fields | `timestamp`, `tool`, `arguments`, `risk`, `approved`, `latency_ms` |
| Audit retention | rotating JSONL, **5 MB × 5 backups = 25 MB cap** |

---

## C. T4 — Safety classifier eval (offline, no LLM)

**Run:** `python bench/run_bench.py --tasks t4`  
**Measured:** 2026-05-20 · 20 labelled cases.

| Tier | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Dangerous | 5 | 0 | 0 | **1.00** | **1.00** | **1.00** |
| High | 4 | 0 | 0 | **1.00** | **1.00** | **1.00** |
| Medium | 5 | 0 | 0 | **1.00** | **1.00** | **1.00** |
| Low | 6 | 0 | 0 | **1.00** | **1.00** | **1.00** |
| **Overall** | **20** | **0** | **0** | **1.00** | **1.00** | **1.00** |

**Overall accuracy: 100 % (20 / 20)**

### Bench-driven regression history

The first bench run scored **90 % overall** and **60 % recall in the dangerous tier** (2 / 5 missed). Both failures were real regex bugs surfaced by the harness:

| Pattern | Was | Fixed to |
|---|---|---|
| Fork bomb | `:\(\)\s*\{\s*:\|\s*:\s*;\s*\}\s*;` (rigid spacing) | `:\s*\(\s*\)\s*\{[^}]*:\s*\|\s*:[^}]*\}\s*;` (tolerates `&` / extra body) |
| Format drive | `\bformat\s+c:\b` (`\b` after `:` never matches) | `\bformat\s+[a-zA-Z]:` (any drive letter, no trailing boundary) |

This is one of the main reportable wins: **the eval harness paid for itself on the first run by catching two latent classifier gaps in shipped production code.**

---

## D. T3 — Tool selection accuracy (LLM, Gemini 2.5 Flash)

**Run:** `python bench/run_bench.py --tasks t3`  
**Measured:** 2026-05-20 · 10 prompts · Vertex AI authenticated · safety auto-approved (so we measure model routing, not the gate).

| Metric | Value |
|---|---:|
| Cases | 10 |
| Exact-match rate | **100 % (10 / 10)** |
| Mean Jaccard | **1.00** |
| Cases where Gemini chose the right single tool | 10 / 10 |
| Cases needing > 1 tool to answer | 0 |

**Per-prompt end-to-end latency** (wall clock, includes tool execution):

| Statistic | ms |
|---|---:|
| Min | 2,734 |
| Median | 5,994 |
| Mean (all 10) | **8,919** |
| Mean (excluding `browser_navigate` outlier) | 6,005 |
| Max (`browser_navigate`, Playwright cold start) | 35,146 |

---

## E. T5 / Option A — Live runtime telemetry (real measurements)

Live counters exposed by `GET /metrics` and `oscar metrics`. The numbers below come from the actual `data/logs/audit.jsonl` after the T3 run completed.

### E.1 — LLM (Gemini 2.5 Flash via Vertex AI)

Captured from `llm_manager.get_performance_metrics()` after the 10-case T3 run.

| Metric | Value |
|---|---:|
| Gemini API calls | **19** |
| Mean calls per prompt | 1.9 |
| Success rate | **100 %** |
| Failure count | 0 |
| Total processing time | 50,657.9 ms |
| **Mean processing time per call** | **2,666 ms** |
| **Total tokens consumed** | **64,680** |
| Mean tokens per call | 3,404 |
| Mean tokens per prompt | 6,468 |

**Cost estimates** for the 10-prompt T3 run (Gemini 2.5 Flash pricing: $0.30 per M input tokens, $2.50 per M output tokens).

| Method | Per 10-prompt run | Per prompt |
|---|---:|---:|
| Naive (all tokens at input rate) | **$0.019** | $0.0019 |
| Realistic (80/20 input/output split) | **$0.048** | $0.0048 |

### E.2 — Audit log aggregate (71 entries — 56 historical + 15 with the new schema)

| Metric | Value |
|---|---:|
| Total audit entries | 71 |
| Approved | 71 |
| Rejected | 0 |
| Low-risk calls (new schema) | 14 |
| Medium-risk calls (new schema) | 1 |
| High / Dangerous (new schema) | 0 / 0 |
| Pre-schema entries (no risk field) | 56 |

### E.3 — Per-tool execution latency (15 sampled calls, real)

| Tool | n | Mean ms | Median ms | Max ms |
|---|---:|---:|---:|---:|
| `browser_navigate` | 1 | 33,815 | 33,815 | 33,815 |
| `web_search` | 1 | 4,222 | 4,222 | 4,222 |
| `git_compare` | 1 | 87.2 | 87.2 | 87.2 |
| `git_branches` | 2 | 55.5 | 55.5 | 57.3 |
| `git_review` | 2 | 52.9 | 52.9 | 62.1 |
| `git_log` | 2 | 49.5 | 49.5 | 53.0 |
| `git_status` | 2 | 40.7 | 40.7 | 55.2 |
| `git_checkout` | 1 | 32.0 | 32.0 | 32.0 |
| `git_diff` | 2 | 27.6 | 27.6 | 31.7 |
| `run_shell_command` | 1 | 13.9 | 13.9 | 13.9 |

**Headline:** **git tools execute in 14–87 ms**; external network tools (web search, browser) are 4–34 s. The wide spread is meaningful — it tells you where to optimise (Playwright cold-start dominates `browser_navigate`).

### E.4 — Per-tool call distribution (historical + bench, 71 entries)

```
git_log              13
git_branches         12
run_shell_command    12
git_status           10
git_compare           5
git_review            5
git_checkout          4
web_search            3
git_commit            3
git_diff              2
conversation_search   1
browser_navigate      1
```

This is what a representative OSCAR deployment actually does: **read-heavy git workload** (status, log, branches, compare, review dominate); destructive operations (`git_commit`, `git_checkout`) are a small fraction.

---

## F. T1 — Branch-comparison correctness (stub, awaiting fixtures)

| Metric | Status |
|---|---|
| Defined in `bench/tasks/t1_branch_compare.yaml` | ✓ |
| Runner wired in `bench/run_bench.py` | ✓ |
| Cases populated | 0 — populate before quoting numbers |

When populated, the runner reports `mean_precision`, `mean_recall` per case, comparing the file set surfaced by `git_compare(base, head)` against a manually-curated golden file list.

---

## G. External benchmarks — positioning (no numbers claimed)

| Benchmark | Why it's NOT a fair OSCAR comparison |
|---|---|
| **SWE-bench / SWE-bench Verified** | Measures end-to-end repo patching. OSCAR is a review-time tool, not autonomous patching. |
| **HumanEval / MBPP / LiveCodeBench** | Single-function synthesis. Out of scope. |
| **AgentBench / ToolBench / τ-bench** | General tool-use. **T3 in this document is the OSCAR-shaped analogue.** |
| **MemGPT / AIOS / OSAgent / ReAct** | Different problem shape. The capability matrix on the website is the right qualitative comparison. |

---

## Headline numbers for the report

If you want a single one-liner per section for the abstract or conclusion:

- **Surface:** 15 tools · 12 endpoints · 2,308 LOC backend · MIT-licensed.
- **Safety eval (T4):** **100 % accuracy** across 4 risk tiers on 20 labelled cases. **Bench surfaced 2 real classifier bugs on first run** (recall improved from 60 % → 100 % in the dangerous tier).
- **Tool routing (T3):** **100 % exact-match** across 10 prompts spanning all four tool families. Median end-to-end latency **6.0 s**; per-Gemini-call mean **2.7 s**.
- **Cost:** **~$0.005 per prompt** on Gemini 2.5 Flash (realistic 80/20 split).
- **Tool latency (E.3):** git tools land in **14–87 ms**; user-perceived latency is dominated by the LLM round-trip and (for one tool) Playwright cold-start.

---

## How to reproduce every number above

```bash
# Static counts (Section A)
wc -l src/oscar/{tools,core,api}/*.py
grep "agent.tool" src/oscar/core/agent.py
grep "^@app\\." src/oscar/api/server.py

# T4 safety classifier (Section C)
python bench/run_bench.py --tasks t4

# T3 + LLM telemetry (Sections D and E.1)
gcloud auth application-default login   # one-time
python bench/run_bench.py --tasks t3

# Live audit aggregate + per-tool latency (Sections E.2/E.3/E.4)
oscar metrics

# Or programmatically:
curl http://127.0.0.1:8420/metrics      # while oscar-server is running
```

Each bench run writes a timestamped folder to `bench/results/` with one
JSONL per track and a `summary.json` containing all the aggregates above.
