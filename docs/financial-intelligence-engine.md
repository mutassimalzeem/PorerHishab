# Financial Intelligence Engine (AI-13)

The Financial Intelligence Engine is PorerHishab's reusable, deterministic
layer that turns a user's raw financial records into structured financial
**facts**, **coverage**, **cashflow views** and **signals**. Downstream
experiences — AI chat, recommendations, proactive insights, and a future
dashboard or notification system — consume the engine's structured output and
add presentation (wording, status codes, styling) on top.

It replaces scattered, private aggregation logic (previously embedded in the
coach, insights and forecasting surfaces) with one shared implementation, and
makes the distinction between *observed*, *scheduled* and *estimated* values
impossible to blur by accident.

**AI-13's core rule: the engine is deterministic software. It requires no
LLM, no network, no embeddings and no vector database. LLMs may later
*explain* the engine's structured output, but they never produce financial
arithmetic.*

## Architecture

```
                        ┌──────────────────────────────────────┐
                        │           raw financial data         │
                        │  transactions · scheduled cashflow · │
                        │  savings goals · accounts            │
                        └──────────────────┬───────────────────┘
                                           │  (user-scoped SQL facts)
                                           ▼
                        ┌──────────────────────────────────────┐
                        │     FINANCIAL INTELLIGENCE ENGINE    │
                        │  app/services/intelligence/          │
                        │                                      │
                        │  periods      → central windows      │
                        │  coverage     → data sufficiency     │
                        │  facts        → scoped aggregates    │
                        │  snapshot     → observed + plans     │
                        │  cashflow     → actual/plan/estimate │
                        │  categories   → category facts       │
                        │  goals        → affordability        │
                        │  signals      → rules + evidence     │
                        │  engine       → one entry point      │
                        └──────────────────┬───────────────────┘
                                           │
             structured facts / signals (evidence, stable ids, estimates labeled)
                                           │
   ┌───────────────┬───────────────────────┼───────────────────────┬───────────────┐
   ▼               ▼                       ▼                       ▼               ▼
 grounded      savings                 proactive               future           future
 chat          recommendations         insights                dashboard        notifications
(presenta-    (presents engine        (presents engine        (renders         (uses stable
 tion only)    signals + narrows        signals + adds          snapshot +       signal ids for
               wording)                 titles/next actions)    signals)         lifecycle)
```

Where the code lives:

| Module | Responsibility |
| --- | --- |
| `app/services/intelligence/periods.py` | `Period` objects and month math; one timezone (Asia/Dhaka) |
| `app/services/intelligence/coverage.py` | first-class data-coverage statements |
| `app/services/intelligence/facts.py` | user-scoped SQL aggregates (single implementation) |
| `app/services/intelligence/snapshot.py` | `FinancialSnapshot`, `MonthlyHistory`, `ScheduledObligations` |
| `app/services/intelligence/categories.py` | `CategorySpendingFact` and comparisons |
| `app/services/intelligence/goals.py` | `GoalAssessment` (shared with `finance.coach`) |
| `app/services/intelligence/signals.py` | `FinancialSignal` generators, thresholds, stable ids |
| `app/services/intelligence/engine.py` | `FinancialIntelligence`, `CashflowIntelligence`, `build_financial_intelligence` |
| `app/services/finance/coach.py` | presentation layer: titles, status codes, expiry dates, response shapes |

## The four layers of information (never blurred)

1. **Raw data** — the user's own rows: transactions, scheduled cashflow
   items, savings goals. Never re-derived differently by consumers.
2. **Derived facts (observed)** — deterministic aggregates of those rows
   (income, expenses, net cashflow, per-category totals, recurring
   patterns). Labeled `observed`.
3. **Estimates / forecasts** — computed projections (monthly-average
   baseline via the existing `forecasting.cashflow` service, savings
   estimates, projected shortfall). Always labeled `estimate`, carry their
   assumptions, and are `None` when history cannot support them.
4. **Interpretations / recommendations** — wording, titles, severities and
   next actions owned by consumers (coach, AI layers). The engine never
   embeds marketing language into facts.

Concretely, the same Food-spend observation decomposes as:

* *observed fact*: "Food spending in the latest complete month is ৳9,000
  vs ৳5,000 the month before" (delta ৳4,000, +80%);
* *estimate*: "an optional reduction of at most ৳900/month (10% of the
  latest month) would be worth about ৳10,800/year if sustained";
* *recommendation (consumer wording)*: "Review increased Food spending…"

## Period handling

`Period` carries `kind`, inclusive `start`/`end`, `is_complete` and a
`label` (`Period.to_dict()` is frontend-ready). All construction goes
through one module so no consumer re-implements date math:

* `current_month_period(as_of)` — the running month, **never** complete;
* `calendar_month_period(first_day)` / `latest_complete_month_period` /
  `previous_complete_month_period(as_of)` — fully elapsed months;
* `history_window_period(as_of, months=3)` — the product's standard
  three-complete-months window (excludes the running month);
* `upcoming_period(as_of, days=30)` — forward-looking plan horizon;
* `explicit_period(start, end, anchor)` — arbitrary caller ranges; complete
  only once every day has elapsed relative to the anchor.

Timezone: the product's calendar is Bangladesh's (`Asia/Dhaka`), shared with
`finance.coach.today_dhaka` and the forecasting service. Boundaries are
plain dates with explicit inclusive semantics, so results are identical
regardless of the time of day they are computed.

## Data coverage is first-class

`assess_coverage(period, months_with_records, as_of, required_complete_months)`
returns a structured `DataCoverage` with one of four statuses:

| Status | Meaning |
| --- | --- |
| `no_records` | nothing observed in the window; totals are unknown, **not zero** |
| `partial_current_only` | only the running (incomplete) month has records |
| `insufficient_history` | fewer complete months than the window requires |
| `adequate_history` | every window month has records |

Every coverage outcome carries explicit `limitations`. They keep the exact
product copy the evaluation suites pin (e.g. *"Three complete calendar
months with observed records are required; missing months are unknown."*),
so a one-month user can never be told their spending is "unusually high
compared with normal spending": history signals (unusual spending, category
increase, projected shortfall) are simply **not generated** without adequate
history, and the limitation strings state why.

History-gated facts are independent of history depth: upcoming scheduled
plans and goal progress remain available because they are plan/record facts,
not historical claims.

## Aggregations (single implementation)

`facts.py` hosts the shared user-scoped SQL aggregates (moved verbatim from
the coach so behaviour is unchanged):

* `scoped()` — BDT-account-aware query scope (`None` account = assumed BDT),
  raising on invalid windows;
* `totals()` — income, expenses, net plus a `Coverage` statement. Amounts
  are `None` when no records exist (unknown ≠ zero);
* `grouped_expenses()` — ranked category/merchant spending magnitudes;
* `scheduled_totals()` / `scheduled_cashflow_items()` — planned amounts and
  rows filtered to `status='scheduled'` only.

The engine orchestrates these with `analytics.insights` (summary/category/
recurring math over scoped rows) and `forecasting.cashflow`
(`calculate_cashflow_forecast` for the monthly-average baseline estimate).
Nothing is duplicated.

## Scheduled vs actual vs forecast

`CashflowIntelligence` keeps three planes apart:

* `actual_income` / `actual_expense` — observed records up to `as_of`
  (`actual_until` = `as_of`);
* `scheduled_expense` / `scheduled_income` — unpaid, uncancelled plans in
  the horizon; `paid` rows are past facts, `cancelled` rows are not
  obligations, and **neither ever enters the other planes**;
* `forecast_income` / `forecast_expense` / `forecast_net` — the monthly
  average estimate from the deterministic forecasting service over the
  complete prior months. `None` when history is inadequate.

Two hard rules the engine enforces structurally:

1. **Scheduled income never silently becomes available money.** It is
   reported separately (`uncertain_scheduled_income` in coach wording) and
   excluded from projected balances — the limitation is carried in the
   payload.
2. **Forecasts expose their assumptions.** The `assumptions` list is copied
   from the forecasting service (simple averages, missing months count as
   zero activity, no seasonality) and `estimated: true` plus
   `"type": "forecast"` make the projection explicit in serialized output.

## Signal generation

`build_signals(db, user_id, as_of, history)` produces deterministic signals
with today's product thresholds (extracted, not re-implemented):

| Signal | Rule (preserved from the coach contract) |
| --- | --- |
| `savings_opportunity` | latest complete month spending on a reducible category (`Food, Shopping, Entertainment, Subscription, Travel`) exceeds `1.10×` the previous month, generating `estimated_monthly_saving = min(latest×10%, latest − previous)` |
| `unusual_spending` | current month-to-date expenses exceed `1.5×` the largest complete prior month |
| `upcoming_expense` | scheduled (unpaid) expense plans due within 30 days, marked `record_type: plan` |
| `projected_shortfall` | historical-average monthly net < 0 (estimate, never a predicted bank balance) |
| `goal_progress` | one signal per active goal, cheapest-first ordering by target date, with the shared affordability assessment |

### Evidence

Every signal carries structured `evidence` — exactly the structural keys
consumers already use (e.g. `latest_expenses`, `previous_expenses`,
`estimated_monthly_saving`, `scheduled_item_id`, `current_expenses`,
`largest_prior_month`, `estimated_monthly_net`, `goal_id`) plus the rule
constants (`increase_factor`, `reduction_fraction`, `unusual_factor`) so any
reader can re-derive the verdict:

```json
{
    "signal_type": "savings_opportunity",
    "subject": "Food",
    "observed_value": "9000.00",
    "reference_value": "5000.00",
    "delta": "4000.00",
    "percentage_change": "80.00",
    "estimate": true,
    "estimate_label": "estimate",
    "observed_period": {"kind": "latest_complete_month", "start": "2026-09-01",
                        "end": "2026-09-30", "is_complete": true},
    "comparison_period": {"kind": "previous_complete_month", "start": "2026-08-01",
                          "end": "2026-08-31", "is_complete": true},
    "evidence": {"latest_expenses": "9000.00", "previous_expenses": "5000.00",
                 "estimated_monthly_saving": "900.00",
                 "increase_factor": "1.10", "reduction_fraction": "0.10"},
    "stable_id": "review-category:2026-09:42b3f6e1a09c"
}
```

Evidence only ever derives from the authenticated user's own records; the
isolation suites verify with a canary user whose records must not appear in
another user's payload.

### Stable ids

Signal `stable_id`s are deterministic functions of stable properties —
signal type, category/record identity and period — and deliberately exclude
internal user ids:

* `review-category:{latest month}:{sha256(category)[:12]}` — matches the
  existing recommendation id scheme;
* `unusual-spending:{as_of:%Y-%m}`;
* `estimated-deficit:{as_of:%Y-%m}`;
* `scheduled-expense:{item id}:{due_date}`;
* `goal-progress:{goal id}:{as_of:%Y-%m}`.

The same facts always regenerate the same id, so future notification and
insight-lifecycle layers can dedupe and track dismissal without random
UUID churn. (Signal payloads across users are self-describing; user
scoping is enforced at query level, never by embedding user ids.)

## Confidence and limitations

The engine refuses fake statistical certainty. Instead of a numeric
confidence, each value states what it is:

* `estimate` / `estimate_label` — `observed` or `estimate`;
* `assumptions` — rule constants and scenario premises;
* `limitations` — unknown/insufficient-data statements, carried verbatim
  where product copy is pinned (e.g. income guarded by established
  limitations list).

Amounts backed by no records are `None`, never zero — consumer code cannot
accidentally interpret silence as zero spending.

## Refactored consumers (no silent behaviour changes)

`finance.coach` is now the presentation layer and delegates every shared
computation to the engine:

* `history()` → `intelligence.snapshot.monthly_history`;
* `recommendations()` → `intelligence.signals.savings_opportunity_signals`;
* `nudges()` → `intelligence.signals.build_signals` (presentation only:
  titles, next actions, expiry dates, dedupe/sort/cap by stable key);
* `goal_plan()` → `intelligence.goals.goal_assessment` (core affordability
  arithmetic unchanged);
* `coach_cashflow()` / `coach_purchase()` — unchanged logic over engine
  facts (`totals`, `scheduled_totals`, periods);

Grounded chat, savings-plan and forecasting suites are untouched: all
AI-12A..AI-12E evaluation suites and the AI-12E quality gate continue to
pass unchanged, which is the regression proof that behaviour is identical.

## Determinism and isolation

* Every engine function is a pure function of `(database state, as_of)`.
  Two runs over the same state with the same `as_of` build byte-equal
  serialized intelligence (`test_intelligence_snapshot.py`).
* Money is `Decimal` throughout, quantized half-up to 2 dp for product
  money and 4 dp for rates; percent changes are half-even at 2 dp.
* All queries filter `user_id` at the repository/fact layer. There are no
  client-supplied user ids in the engine or its consumers; API surfaces
  continue to derive the user from the authenticated session only.
* The engine imports nothing from `services.ai`, `services.rag` or any
  optional AI/LLM dependency and performs no network I/O
  (`test_ai_coach.py::test_app_imports_without_optional_ai_or_vector_packages`
  covers the offline import path).

## Testing map

| Area | File |
| --- | --- |
| Period semantics (year boundaries, completeness, validation) | `test_intelligence_periods.py` |
| Data sufficiency (zero/one/adequate history, partial month) | `test_intelligence_coverage.py` |
| Aggregation, isolation canary, scheduled separation, determinism, non-BDT exclusion | `test_intelligence_snapshot.py` |
| Signals (thresholds, silence at boundaries, evidence, ids) | `test_intelligence_signals.py` |
| Category comparisons + coach migration regressions | `test_intelligence_categories.py` |
| Full offline AI quality gate (AI-12A–E) | `python -m app.evaluation.quality_gate` |

## Future consumers (not part of AI-13)

The engine's serialized contract is already frontend-friendly
(`snapshot.to_dict()`, `cashflow.to_dict()`, `signal.to_dict()`), so a future
dashboard can request summary income/expenses/net, top categories, upcoming
obligations, projected cashflow, goal progress and notable signals in one
deterministic payload. AI-13 deliberately builds **no** new endpoints, UI or
LLM features.
