# AI-12D — Recommendation & insight evaluation

This milestone evaluates the two coach output systems that read the user's
financial data directly: **savings recommendations** and **proactive
insights**. It is deliberately not a string-matching evaluation. Both phrase
variants below are equally valid outcomes; what must match is the structured
financial claim behind them.

> "Reduce dining spending by about ৳1,200/month."
> "A 15% reduction in your dining budget could free roughly ৳1,263 each month."

Everything runs offline: no provider call is reachable, and every pinned
number is re-derived from the seeded scenario blueprint with plain Python
arithmetic (`recommendation_ground_truth_consistency` and
`insight_ground_truth_consistency`), independent of the systems under test.

Run the milestone tests with:

```powershell
cd backend
../.venv/Scripts/python.exe -m pytest test_ai_12d_evaluation.py -q
```

## What is evaluated

```
Financial data
     │
     ├───────────────┐
     ▼               ▼
Savings             Proactive
recommendations     insights
(planner plan +     (coach nudges)
 coach reductions)
     │               │
     └───────┬───────┘
             ▼
       Ground truth
       evaluation
```

### Savings recommendations (`app/evaluation/recommendation_runner.py`)

Eight cases across the deterministic savings plan
(`app/services/planning/savings.py`) and the coach's spending-reduction
opportunities (`app/services/finance/coach.py`). Each case is scored on:

| Dimension | What is checked |
|---|---|
| Grounding | Every pinned field and recommendation derives from the seeded user's own transactions (plan totals, category spending, evidence amounts) |
| Arithmetic | `observed spending × reduction fraction ≈ suggested saving`, within the configured tolerance (`ARITHMETIC_TOLERANCE = 0.01`); each suggestion is also bounded by its contract cap (plan ≤ 20% of observed category spending, coach ≤ 10% of latest monthly spending) |
| Estimate labeling | Estimates are labeled (`estimated_*`, assumptions, confidence) and observed facts are kept separate (`monthly_spending`, evidence amounts) |
| No double counting | Summed per-category cuts never exceed the monthly gap they are meant to close; one entry per category; recommendation ids unique |
| Personalization | Amounts equal this user's actual category spending, not a template |
| Insufficient data | No usable history → `insufficient_data` status, `None` estimates, no recommendations, explicit limitation; coach stays silent under three incomplete calendar months |

### Proactive insights (`app/evaluation/insight_runner.py`)

Eleven controlled scenarios cover all five insight types produced by
`finance.coach.nudges`, each with a *triggered* world (condition true) and a
*silent* world (condition false):

| Insight type | Trigger condition | Silent condition |
|---|---|---|
| `unusual_spending` | Current month spending > 1.5× the prior three-month ceiling | Spending inside the historical range |
| `savings_opportunity` | Reducible category spending > 110% of the prior month | No increase (or a non-reducible category spikes) |
| `upcoming_expense` | Scheduled expense due within 30 days | Paid/beyond-horizon/income entries only |
| `projected_shortfall` | Historical baseline monthly net < 0 | Positive baseline net |
| `goal_progress` | Active savings goal exists | No active goals |

An eleventh scenario proves insights never fire on inadequate history (one
empty history month even with a suspicious spike). Every case verifies:

* **presence** — insight exists iff the condition is true; no undeclared types;
* **numbers** — evidence amounts equal scenario ground truth to the cent;
* **dates** — evidence periods, due dates and expiry match the calendar;
* **plan labeling** — scheduled obligations carry `record_type: "plan"` and
  state they are not actual transactions (scheduled ≠ actual);
* **isolation** — a canary user's merchant, bill title, goal name and amounts
  (৳777,777 / ৳888,888) never appear in another user's payload.

## Metrics and reports

* `run_insight_dataset` → `InsightReport` with per-type TP/FN/FP/TN,
  detection and false-alarm rates, and number/date accuracy
  (`insight_metrics.format_insight_report`).
* `run_recommendation_dataset` → `RecommendationReport` with grounding and
  arithmetic accuracy, estimate-labeling / no-double-counting /
  personalization / data-sufficiency rates
  (`recommendation_metrics.format_recommendation_report`).

Both reuse the AI-12A report shape and its failure listing; the runner itself
is proven able to fail (mutated pins and inflated cut projections trip the
matching dimension) so a clean report is evidence, not tautology.

## Files

| Path | Purpose |
|---|---|
| `backend/app/evaluation/datasets/insight_scenarios.py` | Controlled insight worlds, expected structured insights, seeding |
| `backend/app/evaluation/insight_runner.py` | Insight case runner + per-case outcome trace |
| `backend/app/evaluation/insight_metrics.py` | Detection matrix, report and formatter |
| `backend/app/evaluation/datasets/recommendation_cases.py` | Recommendation worlds, pinned structured properties, contract re-derivation |
| `backend/app/evaluation/recommendation_runner.py` | Plan and coach case runners |
| `backend/app/evaluation/recommendation_metrics.py` | Property rates, report and formatter |
| `backend/test_ai_12d_evaluation.py` | The milestone test suite (offline, SQLite in-memory) |
