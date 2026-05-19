# OSCAR Bench

A small task-completion harness tailored to OSCAR's git-specialized scope.
It is **not** SWE-bench or HumanEval — those evaluate things OSCAR doesn't
claim to do. The tracks here measure what OSCAR is actually built for.

## Tracks

| Track | What it measures | LLM needed? |
|---|---|---|
| **T1** branch comparison | Precision/recall of files surfaced by `git_compare` against goldens | no (stub uses raw `git diff`) |
| **T3** tool selection | Exact-match + Jaccard between expected tool set and what the agent actually called | yes — Vertex AI |
| **T4** safety classifier | Per-tier precision/recall of `assess_risk` on labelled prompts | no |
| **T5** runtime | Tokens, mean Gemini latency, naive USD cost estimate, audit-log aggregates | no (reads what's been logged) |

T4 is the headline number you can get without LLM access. T3 needs
`gcloud auth application-default login`.

## Run it

```bash
# everything that doesn't need credentials
python bench/run_bench.py --offline

# everything
python bench/run_bench.py

# just one track
python bench/run_bench.py --tasks t4
```

Results land in `bench/results/<UTC-timestamp>/`:
- `summary.json` — aggregate metrics per track
- `<track>.jsonl` — one row per case

## Adding cases

Each track has a YAML in `bench/tasks/`. Edit it and re-run — the runner
picks up whatever's there. T1 ships empty on purpose: add real repos
and golden file lists before quoting numbers.

## What to report

For the capstone report, the meaningful headline numbers are:
- **T4 accuracy, per-tier precision/recall** — calibrates the safety story
- **T3 exact-match rate, mean Jaccard** — quantifies tool-routing quality
- **T5 mean Gemini latency, mean tokens, est. cost per call** — operational characteristics
- **T1 precision/recall** — only once you've populated fixtures
