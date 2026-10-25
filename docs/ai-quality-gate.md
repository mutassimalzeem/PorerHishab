# AI-12E — AI Quality Gate & Release Report

AI-12E is **not** a new evaluation framework. It orchestrates the four existing
offline evaluators into one deterministic quality gate with explicit
PASS / FAIL / ERROR outcomes, a human-readable report, and a machine-readable
JSON aggregate suitable for CI.

```
QualityGateResult
├── finance         (AI-12A/12B grounded finance runner)
├── categorization  (AI-12C categorization runner)
├── recommendations (AI-12D recommendation runner)
├── insights        (AI-12D insight runner)
├── overall / overall_passed
└── failures / errors
```

Each section simply **reuses** the suite's own runner, metrics, validators and
formatters. No metric is computed twice; no evaluator was weakened to make the
gate green.

## What is evaluated

| Section | Suite | Cases (current dataset) | measured properties |
|---|---|---|---|
| Finance / grounded chat | `runner.run_dataset` (+ `ground_truth_consistency`) | 26 | intent, date, numeric, status, grounding, safety/isolation |
| Categorization | `categorization_runner.run_dataset` (rules-only) | 123 | macro/micro F1, rule coverage, fallback rate, correction preservation, ambiguity guess rate |
| Recommendations | `recommendation_runner.run_recommendation_dataset` | 8 | grounding, arithmetic, estimate labeling, no double counting, personalization, data sufficiency, isolation |
| Insights | `insight_runner.run_insight_dataset` | 11 | presence (TP/FN/FP/TN per type), numbers, dates, plan labeling (scheduled ≠ actual), isolation |

Every case runs the deterministic pipeline against seeded, controlled scenario
worlds with pinned structural ground truth. **Natural-language wording is never
scored**: the same financial claim phrased two ways is equally valid; a wrong
amount in beautiful prose still fails. That distinction is deliberate —
exact financial correctness (numbers, dates, safety contracts) is measured
structurally, while wording quality is out of scope because it cannot be judged
deterministically offline.

## What is *not* evaluated

* Anything that requires an LLM, an API key, or a network — the gate sets no
  provider configuration and always runs rules-only/deterministic pipelines.
* Financial *advice quality* over real production data: the datasets are
  controlled synthetic scenarios, so the metrics prove contract/grounding
  consistency of the offline pipeline, not that advice is correct for any real
  user's finances. Real-world financial correctness cannot be proven from
  fixtures; it is out of scope by design.
* Natural-language answer wording, tone, or phrasing.
* RAG/Chroma artifacts — generated vector data is never used as evaluation data.
* Production transaction data — the gate always runs against its own
  in-memory SQLite database.

## How to run the quality gate

```powershell
cd backend
python -m app.evaluation.quality_gate          # human-readable report
python -m app.evaluation.quality_gate --json   # machine-readable aggregate
```

Or from the repository root:

```powershell
python backend/app/evaluation/quality_gate.py
```

Exit codes: `0` = PASS, `1` = FAIL, `2` = ERROR. No provider or network is
reachable in any mode.

Programmatic use:

```python
from app.evaluation import QualityThresholds, run_quality_gate
result = run_quality_gate(thresholds=QualityThresholds())  # 0 = PASS, 1 = FAIL, 2 = ERROR
result.to_json_dict()["overall"]
```

## PASS vs FAIL vs ERROR

* **PASS** — every mandatory gate satisfies its configured threshold.
* **FAIL** — at least one measured gate is violated; the failing metric is named.
* **ERROR** — an evaluator itself could not execute correctly (crash, dataset
  validator rejection, or an internally inconsistent/empty report such as zero
  cases). ERROR is never collapsed into PASS and never treated as zero cases;
  the aggregate reports `overall: "ERROR"` and a non-zero exit code (2).

## Thresholds (`QualityThresholds`)

Scale conventions follow each evaluator exactly: percent-scale (0–100) for the
`*_accuracy` metrics, fraction-scale (0–1) for the raw categorization
correction/ambiguity/micro metrics.

| Threshold | Default | Meaning / rationale |
|---|---|---|
| `finance_min_accuracy` | `100.0` | Intent, date, numeric, status, grounding and safety accuracies (percent). The controlled world pins exact structural expectations; a consistent offline pipeline can always achieve 100%, so any regression must fail. |
| `finance_min_cases` | `1` | The finance dataset must produce cases at all (guards against silent empty runs). |
| `categorization_min_macro_f1` | `100.0` (percent scale) | Mean F1 over categories with definable precision/recall. Configurable (statistical aggregate over the labeled corpus); today's deterministic rule engine reaches 100%. |
| `categorization_min_micro_f1` | `1.0` (fraction) | Pooled F1 across all confident predictions; same rationale. |
| `categorization_min_correction_preservation` | `1.0` | Confirmed user corrections must **always** take precedence — an exact safety contract, not a statistic. |
| `categorization_max_guess_rate` | `0.0` | Ambiguous inputs must never receive a confident guess. |
| `recommendation_min_percent` | `100.0` | Grounding, arithmetic, estimate labeling, no-double-counting, personalization and data sufficiency are pinned-structure checks; any violation is a defect. |
| `recommendation_max_isolation_violations` | `0` | Any canary leak is a hard defect. |
| `insight_min_percent` | `100.0` | Presence, numbers, dates and plan-labeling accuracies. |
| `insight_min_detection_rate` | `1.0` | Every "condition true" world must raise its insight. |
| `insight_max_false_alarm_rate` | `0.0` | A "condition false" world must stay silent. |
| `insight_max_isolation_violations` | `0` | Any canary leak is a hard defect. |

Rule coverage and provider-fallback rate are **measured and reported but not
gated**: they characterize the dataset composition (how many cases are
rule-resolvable vs ambiguous) rather than pipeline quality. Gate on those if a
release wants a specific coverage profile — the threshold object can be
extended without changing evaluator logic.

Thresholds are not lowered to make suites pass. If a gate becomes red, the fix
is in the product pipeline (or, if the product behavior is legitimately
changing, the threshold update is documented in the PR).

## Data hygiene of the aggregate report

The JSON/human aggregate contains **metrics, statuses, failing synthetic case
ids and gate verdicts only** — no transaction descriptions, merchant names,
goal names, account data, user identifiers, or canary strings. Full failure
detail (which may quote synthetic scenario values) lives in each evaluator's
own report and in the evaluation datasets, never in the aggregate. Wall-clock
time is deliberately absent: the only dates are the suites' fixed evaluation
`as_of` constants, so repeated runs are byte-identical.

## Example report (actual values from the current datasets)

```
AI QUALITY REPORT
──────────────────────────────────────────────────────────────
PorerHishab
Evaluation snapshot: finance: as_of=2026-10-25, categorization: as_of=n/a, ...

Finance / Grounded Chat
Cases: 26   Passed: 26   Failed: 0
Intent: 100.0%   Date: 100.0%   Numeric: 100.0%
Status: 100.0%   Grounding: 100.0%   Safety: 100.0%

Categorization
Cases: 123   Passed: 123   Failed: 0
Rule coverage: 56.8%   Fallback: 33.9%
Corrections preserved: 100.0%   Ambiguous guessed: 0.0%
Macro F1: 100.0%   Micro F1: 100.0%

Recommendations
Cases: 8   Passed: 8   Failed: 0
...

Insights
Cases: 11   Passed: 11   Failed: 0
...

──────────────────────────────────────────────────────────────
OVERALL: PASS
──────────────────────────────────────────────────────────────
```

## Limitations

* The gate is a *regression* gate for the deterministic offline pipeline. It
  cannot certify real-world advice quality (see above).
* The categorization F1 thresholds are meaningful only for the current corpus
  composition; adding cases changes the statistics, which is why they stay
  configurable.
* The finance evaluation's internal case list is AI-12A/12B's dataset; new
  behavior surfaces must extend the underlying datasets, not the gate.
* Evaluation runs are sequential on one in-memory SQLite session; they are not
  a concurrency test.
* If a gate section reports ERROR, the cause is only visible in the evaluator's
  own report/exception — the aggregate intentionally avoids embedding arbitrary
  failure text.

## Related

* AI-12A/12B: `backend/app/evaluation/runner.py`, `backend/app/evaluation/metrics.py`
* AI-12C: `backend/app/evaluation/categorization_runner.py`
* AI-12D: `docs/ai-12d-recommendation-insight-evaluation.md`
