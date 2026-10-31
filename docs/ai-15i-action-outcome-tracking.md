# AI-15I — Action Outcome Tracking & Coaching Effectiveness

## Objective and lifecycle

Observe recorded financial changes after a user reports acting on advice:
recommendation → existing `acted_on` feedback → observation window → evidence
comparison. A reported action is never verified behaviour. A comparison does
not establish causality, recommendation effectiveness, or money saved by advice.

## Architecture

`GET /finance/action-outcomes` → `finance.action_outcome.action_outcomes` →
existing coaching identity, AI-15G feedback, intelligence facts, AI-15D runway,
and AI-15B/15C obligation reconciliation. Results are read-only derived models;
there is no new table, migration, background job, LLM or network dependency.
The frontend reuses the generated FastAPI contract.

## Eligibility and identity

Only the authenticated owner's current `acted_on` feedback rows are evaluated.
Dismissed, not-relevant, snoozed and unrated advice are excluded. Restoring or
changing feedback removes the corresponding observation on refresh. Advice may
expire without deleting its outcome: the stable recommendation ID continues to
identify the category/month, goal or obligation set. Unknown identities are
ignored; unresolvable categories, deleted obligations and hashed obligation sets
are reported as insufficient data. Future-dated action feedback is excluded.

## Baseline and follow-up rules

All transaction dates and action-report dates use Asia/Dhaka. Naive stored
feedback/allocation timestamps mean UTC. Windows are inclusive.

* Spending advice IDs contain the original observed calendar month, matching
  AI-15F `evidence.period`. Reuse that complete month if it precedes the action.
  Follow-up starts the day after the action-report date and lasts the same
  number of days (28–31). Wait for that full window before comparing amounts.
  This preserves the baseline even after the recommendation expires.
* Legacy identities without an eligible evidence month use equal rolling
  windows: baseline ends on the action date, follow-up starts the next day.
  The observed length is the elapsed time, capped at 30 days.
* Savings uses those equal rolling windows for recorded net cashflow.
* Every measurable comparison requires at least seven elapsed days. A monthly
  spending comparison also waits for its equal full follow-up. Pending outcomes
  contain no amounts. A missing/empty window is insufficient data, not zero.
* Obligation baseline is remaining principal at the actual feedback timestamp.
  Follow-up is remaining principal at the end of the follow-up date, capped at
  30 days. The authoritative obligation service replays existing confirmation
  and revocation timestamps. Payments confirmed before the action are already
  in the baseline; later revocations can produce a worsening observation.
* Cash compares existing 30-day runway projections anchored on the action date
  and observation date (capped at action + 30 days). These are recalculations
  using currently recorded evidence, not stored historical forecasts. If
  scheduled obligations or allocations changed after the action date, the
  historical runway cannot be recovered safely: return insufficient data.

Feedback update time is the action-report time: explicitly reporting the action
again restarts observation. No earlier action history is invented.

## Supported metrics and directions

| Recommendation | Metric | Improvement |
| --- | --- | --- |
| Spending spike, repeated spending | Category expense magnitude | Lower |
| Savings opportunity | Recorded net cashflow, excluding explicit transfers | Higher |
| Cash risk | Authoritative minimum projected cash balance | Higher |
| Upcoming obligations | Authoritative remaining obligation amount | Lower |
| Goal risk | Goal saved amount | Insufficient data: contribution history unavailable |

Recorded net cashflow is a surplus proxy, not proof of a savings transfer.
Category reductions are observations, not proof that purchases were optional.
Expense totals and transaction counts come from shared authoritative facts.

## Classification, evidence and mathematics

Statuses: `pending`, `insufficient_data`, `improved`, `unchanged`, `worsened`.
Direction is explicit per metric; higher is not always better. Money uses
Decimal and existing money quantization. Percentage change is
`(after - before) / abs(before) * 100`, rounded to two places; zero baseline
returns null percentage while keeping absolute change.

Each item exposes recommendation ID/type, action date, baseline/follow-up dates,
metric/direction, before/after amounts, absolute/percentage change, interpretation,
evidence quality, structured evidence, limitations and `causal_claim: false`.
Obligations also expose original, allocated and remaining amounts plus current
settlement status at the observation date. Settlement and change are separate:
a fully settled obligation can be unchanged if settled before the action.

## Currency and ownership

Only owner-scoped BDT accounts and unlinked imported records (assumed BDT by the
existing facts contract) are included. Foreign-currency transactions are excluded
without conversion. Windows lacking comparable BDT evidence are insufficient.
Every feedback, category, account, goal, obligation and allocation query is scoped
to the authenticated user. A client `user_id` cannot change that scope. Filtering
for an ID with no owned acted-on feedback returns 404. The endpoint is read-only
and never confirms payments, modifies balances or edits financial records.

## API

Authenticated `GET /finance/action-outcomes` returns `ActionOutcomeReport` with
`as_of_date`, BDT currency, ordered items, status counts and report limitations.
Optional filters: `recommendation_id` and `status`. Invalid status is 422.
There is no client-controlled observation date or ownership parameter.

## Examples

For a completed equal-length comparison:

| Before (BDT) | After (BDT) | Absolute change | Percentage | Spending status |
| --- | --- | --- | --- | --- |
| 20,000 | 15,000 | -5,000 | -25% | improved |
| 10,000 | 10,000 | 0 | 0% | unchanged |
| 10,000 | 13,000 | +3,000 | +30% | worsened |
| 0 | 3,000 | +3,000 | null | worsened |

The wording is "Recorded value decreased compared with the baseline", never
"This action saved money". No observed change is evidence of causation.

## Frontend

The Insights page includes outcomes alongside the existing action plan and
coaching. Feedback updates refresh both plan and outcomes. Cards expose status,
reported-action date, periods, amounts, localized observation, evidence details,
limitations and related-record links. English/Bengali labels and explanations
use the existing localization system; user-entered goal names remain untouched.
Loading, API failure, keyboard retry, empty and insufficient-data states are
explicit. Semantic lists/details/links, visible textual statuses and responsive
wrapping support keyboard, screen-reader and mobile use.

## Testing strategy

`backend/test_action_outcome.py` covers lifecycle/directions, all six advice
types, zero/negative baselines, currency exclusion, ownership/API scope,
minimum/full-month windows, historical settlement/revocations, deterministic
output and SQL mutation detection. Parameterized offline evaluation asserts
independent arithmetic ground truth through real database-backed outcomes.
Existing obligation tests protect the shared service's default behaviour.
Frontend tests cover statuses, both languages, localized evidence, retry,
related links and revision refresh. Browser tests exercise English/Bengali,
accessibility, mobile overflow, insufficient evidence and feedback refresh.
The frontend CI workflow includes the backend AI-15I tests.

Run the full backend suite against a disposable PostgreSQL database, focused
outcome tests, compileall, generated-contract check, Alembic heads, frontend
typecheck/lint/unit/build and Chrome browser tests. Keep local databases, browser
profiles, package caches and validation output inside `.task-tmp`.

## Limitations and future extensions

Current financial records may be corrected or imported late, changing derived
outcomes. Original obligation principal is read from the current item; edits to
principal are not historically versioned. Cash comparisons are estimates and
decline when relevant schedule/allocation history cannot be reconstructed. Goal
contribution history is unavailable, so no goal progress change is invented.
Repeated-spending outcomes compare category amount, not causal behaviour or a
verified reduction in purchase frequency. No aggregate effectiveness score is
claimed. Future work could add authoritative goal contribution history or
versioned forecast inputs if a concrete requirement justifies persistence.
