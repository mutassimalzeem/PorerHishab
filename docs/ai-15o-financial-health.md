# AI-15O: Financial Health and longitudinal profile

Financial Health is an application-specific diagnostic of observable BDT financial
condition. It is not a credit score, bank score, eligibility decision, universal
measure of financial health, validated benchmark, or prediction. It does not
infer emotions, responsibility, or psychological wellbeing. No LLM/provider is
used for scores, classifications, explanations or evidence.

## Authoritative inputs and boundaries

The evaluation context reads each of the following once:

- AI-13 `monthly_history`, excluding explicitly classified transfers: observed
  totals for the three complete preceding calendar months; missing months stay
  unknown. No income is invented or inferred from scheduled income.
- AI-15K `get_account_overview`, using AI-15A reconciliation, now with an optional
  financial date. Its batched reconciliation output is passed to AI-15D runway;
  the health evaluation does not repeat account reconciliation or introduce an
  account-count-dependent query loop. The default runway APIs retain their
  existing balance-selection behavior.
- AI-15D historical `financial_runway`, sharing the monthly-history context and
  complete account overview. The expense reserve preserves AI-15C's maximum of
  historical expense and remaining scheduled commitments, rather than adding
  overlapping forecasts and schedules. Scheduled income is excluded from cash.
- AI-15B `obligation_amounts_for_items`: remaining/reserved obligations after
  confirmed allocations, in a batch for the observed schedule window. Paid and
  cancelled obligations do not become financial transactions.
- Existing SavingsGoal reported savings and target fields; savings are never
  reconstructed from account balances. This dimension measures reported goal
  attainment, not pace, contribution history or deadline affordability.

AI-15E timeline was inspected: its projection and obligation events use the same
sources above, so rebuilding or fetching a second timeline adds no independent
financial evidence. AI-15F/G coaching and feedback, H action plans, I outcomes,
J effectiveness, L alerts, M delivery and N orchestration/digests were inspected.
They repeat primary signals or describe self-reported actions and delivery, not
additional financial facts. They do not change the score. No email or alert
lifecycle is triggered by evaluating health. Existing outcomes/effectiveness
remain available in Insights and retain their observational, noncausal semantics.

## Transparent v1 normalization

All seven top-level dimensions have equal weight 1. Weights and thresholds are
explicit product choices and require future real-world validation. Decimal is
used through monetary normalization and persisted/API scores. Scores are capped
at 0-100 and rounded half-up to two decimal places.

| Dimension | Minimum data | Normalization |
| --- | --- | --- |
| Cashflow stability | Three complete observed months, positive recorded income and spending in each | `clamp(50 + 250 * mean((income-expenses)/income))`. Break-even is 50; a 20% surplus is 100; a 20% deficit is 0. |
| Liquidity | Every BDT account reconciled with a report no older than 30 days, plus adequate historical runway and positive reserve | `clamp(trusted_cash / (3 * runway_expected_expense_reserve) * 100)`. Severe upcoming obligations increase the authoritative reserve. |
| Obligation pressure | Complete recent verified cash and at least one recorded noncancelled expense schedule within the 90-day lookback/30-day upcoming window | `clamp(100 * (1 - upcoming_remaining_reserve / trusted_cash))`. Nonpositive cash with positive obligations or negative cash scores 0. Zero cash and zero obligations has no denominator and stays unknown. |
| Spending stability | Three complete months with positive recorded spending | 40 only if *both* later months exceed the first month's spending by more than 50%; otherwise 100. An isolated large purchase is not penalized. |
| Account reliability | All BDT accounts recently verified or with observed reconciliation differences | 40 if any known conflict, otherwise 100. Missing/stale/unverified accounts make the dimension unavailable rather than inserting a financial penalty. |
| Savings progress | At least one active/completed configured goal; reported savings and positive target for every included goal | Mean of `min(reported_saved/target,1) * 100`; no configured goal is unknown, not poor savings. |
| Financial stress | Recorded expense schedules in the window | `clamp(100 - 30 * distinct overdue dates with remaining reserved amounts)`. Multiple bills on one date count once. This describes observed payment pressure, never emotions. |

Ratios never divide by missing/zero denominators. Imported activity does not prove
complete household coverage. A known schedule with no overdue amounts indicates
no *observed* overdue pressure; it cannot establish that all bills are known.
Insufficient data always has a null score and an explicit limitation.

### Relationships and overlap

`monthly_history -> cashflow surplus margin and repeated spending patterns`

`runway expense reserve + trusted cash -> liquidity`

`upcoming remaining obligations + trusted cash -> obligation pressure`

`overdue remaining obligations -> financial stress`

Liquidity represents a general spending buffer and obligation pressure represents
known commitments. They necessarily share cash/commitments; correlation is an
explicit limitation of this equal-weight v1 model, not independent confirmation.
Financial stress uses overdue dates, excluding the upcoming dates scored by
obligation pressure. Runway risk is not separately counted again as stress,
coaching, alerts, or notification volume. Cashflow and spending share recorded
activity but measure surplus and persistent growth respectively, not the same
normalized metric.

## Coverage, quality and status

Overall = sum(available score * weight) / sum(available weights). No available
components means null overall score. Coverage = available weights / all seven
weights * 100. Available and missing keys are returned explicitly. A score of 78
at 43% coverage does not imply the same confidence as 78 at 100% coverage.

Data-quality labels summarize coverage, not financial condition: insufficient
(0 components), limited (<40%), partial (40 to <70%), good (70 to <100%), high (100%).
High means all dimensions can be calculated, not that imports are complete or
bank data is live. Evidence and profile limitations still apply.

Central UX status thresholds: strained [0,40), watch [40,60), stable [60,80),
strong [80,100]. These are application categories, not standards borrowed from
external financial-health frameworks. Unknown scores use insufficient_data.

Every component has score, availability, status, deterministic explanation,
structured aggregate evidence, limitations and calculation metadata. Evidence
contains metric, value, unit, source, financial date and observation timestamp;
no raw transaction rows, merchants, account identifiers or account numbers.

## APIs and persistence

All four endpoints use the existing authenticated user and explicitly scoped
queries. No client user_id is accepted.

- `GET /finance/health`: latest saved profile, or deterministic unknown profile
  without evaluating or writing anything. The unevaluated observed_at is null.
- `POST /finance/health/evaluate`: evaluate today in Asia/Dhaka, persist and return.
  No scheduler/background scoring is added.
- `GET /finance/health/history?from_date=&to_date=&limit=90`: latest bounded window
  returned chronologically, inclusive date filters; limit 1-1000. Reversed date
  ranges and invalid query values use the existing HTTP 422 detail format.
- `GET /finance/health/trend?days=90`: descriptive difference within a 7-366 day
  window, earliest eligible observation versus the latest; not a forecast.

`as_of_date` identifies the represented financial date; `observed_at` identifies
when evaluation ran. Account reports and schedules are current mutable state;
backdated replay of historical account-report/principal versions is unsupported.

Migration `f15o00000001` follows `f15n00000001`. `financial_health_snapshots` stores
queryable date, score, status, coverage, quality, schema/calculation versions and
timestamps plus the full component/evidence JSON payload. Unique
(user_id, snapshot_date, calculation_version) defines a logical snapshot. A
PostgreSQL user row lock serializes same-user evaluation before gathering inputs;
a repeated evaluation updates today's logical row, never past dates or other
algorithm versions. Concurrent users lock different rows. SQLite is used for
focused tests; PostgreSQL is the production concurrency contract.

Version `ai-15o-v1` and schema `1` are persisted. Historical profile JSON is returned
as stored, without running current scoring logic. New algorithms must change
version and coexist. GET current attaches a fresh descriptive trend from stored
snapshots without changing their scores.

Trends require at least seven days between observations and identical available
component sets, schema and calculation versions. Within the selected window,
change >=3 is improving, <=-3 declining, otherwise stable. Missing comparable
observations means insufficient_data. Confidence is adequate at >=70% coverage,
otherwise limited. Component trends compare the same saved component values.
No score change is attributed causally to following a recommendation.

## Workspace and validation

Authenticated `/health` follows the existing design system with score, status,
coverage, quality, dates, explainable dimensions, expandable evidence, comparison
window, component trends and a chronological history table. Static English and
Bengali copy uses the existing translation dictionary. Native buttons, select,
headings, details and table preserve keyboard/screen-reader access; status is
always text, never color alone. Missing data, loading, evaluation failure and
read failure have explicit states and retry controls.

Tests: `backend/test_financial_health.py`,
`backend/test_financial_health_postgres.py`, frontend financial-health unit tests
and Playwright desktop/mobile flows. CI includes real PostgreSQL migration
upgrade/downgrade/re-upgrade and concurrent authenticated same/different-user
evaluation. API types are regenerated from OpenAPI. The pre-existing live
vector-store demonstration now runs only as a script, so pytest collection does
not require an external embedding provider.

Full PostgreSQL regression also exposed a pre-existing digest race: concurrent
workers could observe no digest, then exclude its just-committed alerts and
return skipped_no_alerts. Digest generation now locks the owned user before
these reads, reusing the existing row-lock/idempotency convention.


## Recorded implementation verification (2026-11-01)

- Full backend: 738 passed, 1 opt-in live-provider test skipped, against a fresh
  migrated PostgreSQL schema; no development rows were changed.
- Focused health tests: 39 scoring/API tests plus one PostgreSQL migration and
  concurrent authenticated evaluation test, included in that full run.
- Frontend: 143 tests passed; TypeScript, ESLint and production build passed.
- Playwright: 47 passed, 5 existing duplicate mobile viewport cases skipped.
- PostgreSQL: upgrade, downgrade, re-upgrade and concurrent evaluations passed.
- OpenAPI contract freshness, compileall and git diff --check passed.

The build retains the existing advisory about JavaScript chunks over 500 kB.
Alembic retains the existing path_separator configuration deprecation warning.

The full-backend CI job installs the existing optional requirements-rag.txt
so historical RAG tests can import their libraries. Health calculations and
the separate core-contract job do not require these optional dependencies.
