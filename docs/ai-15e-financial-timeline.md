# AI-15E: financial timeline and cashflow event intelligence

## Purpose and architecture

The timeline is a deterministic read model. It does not create transactions or alter financial state.

Implemented from current main de19fd6 after inspecting the merged AI-15A through AI-15D services, APIs, schemas, repositories, authentication, intelligence facts/signals/snapshots, frontend contracts, Cashflow components/translations and tests. No AGENTS.md files were found. Untracked transaction CSVs and frontend redesign work remain untouched.

`services/finance/timeline.py` adapts existing owner-scoped facts into `FinancialTimeline` and `TimelineEvent` response models. It computes no balances, historical averages, obligation totals or runway dates independently. Current cash and projections come from AI-15D, which reuses AI-15A reconciliation. Obligations use AI-15C scheduled_obligation_values and obligation_amounts_for_items. Payment relationships use active AI-15B allocation rows and actual transaction evidence. There is no new table, migration, matching rule, forecasting engine, write lock or LLM call.

AI-15D checkpoints gain optional period_start, forecast_income, forecast_expense, scheduled_expense_reserve and expected_expense_reserve fields. The engine exposes its already-calculated local values without changing its arithmetic, monthly coverage gate, date conventions or conservative expense-before-income assumption. The timeline copies those values instead of trying to infer them from balance differences.

The typed timeline response is a reusable structured snapshot for future intelligence consumers alongside the existing intelligence API. Existing financial signals and grounded-chat inputs are preserved; this milestone does not inject the raw timeline into an LLM or recalculate existing intelligence signals from a second source.

## Vocabulary and certainty

Six constrained event types:

| Type | Certainty | Meaning |
| --- | --- | --- |
| transaction | actual | Recorded actual through as-of, preserving signed principal and fee |
| obligation_payment | confirmed | Active allocation linked to its real transaction; context only |
| obligation | scheduled / uncertain | Outstanding expense / uncertain planned income |
| forecast_expense | estimated | Existing historical expense estimate and its residual reserve impact |
| forecast_income | estimated | Existing historical income estimate within the runway scenario |
| runway_checkpoint | estimated | Existing projected/minimum cash at a forecast segment boundary |

A confirmed allocation is a user assertion supported by the selected recorded transaction, not bank verification. Candidates never generate confirmed payment events. User titles/descriptions retain their original language; the UI translates its own event, certainty, scope and source labels.

Each event has a stable namespaced id, date, constrained type/certainty/direction/source, amount/currency, source id, balance_impact, impact_scope, cash_impacting flag, optional obligation principal breakdown/status and typed evidence. Numeric source identifiers sort numerically. Ordering is date ascending, then transaction, payment relationship, obligation, forecast expense, forecast income, checkpoint, then stable source id. It is presentation order, not a claim of intraday execution order.

## Cash-impact semantics and double counting

Three explicit impact scopes prevent a misleading sum of history, current cash and estimates:

- actual_history: signed actual movement, principal minus separately recorded fee, in the transaction's native currency. These movements are already represented by AI-15A account cash where linked; never add them to starting_balance again. Unlinked imports remain historical observations rather than an invented account balance.
- future_projection: BDT remaining scheduled expenses and the historical scenario's forecast contributions.
- context: confirmed payment links, checkpoints, uncertain scheduled income and overdue obligations; balance_impact is zero.

cash_impacting means balance_impact is nonzero **within its own scope**. It does not mean every event can be summed into one cash ledger. Signed transaction amount is preserved verbatim, while scheduled/payment/forecast amounts are positive magnitudes (checkpoint amounts are signed projected balances). Direction reflects principal convention; a zero-principal fee record may have neutral direction and a negative fee impact.

A transaction -6,000 allocated to rent 15,000 produces one actual -6,000 movement, one zero-impact confirmed relationship, and one scheduled -9,000 remaining obligation. With opening cash 30,000, AI-15A starting cash is 24,000; do not subtract the actual again. The future rent reserve is 9,000, not 15,000 or a second 6,000. Fully settled obligations have no future event; their confirmed payment evidence can remain visible on its transaction date. Revocation removes the active relationship and restores the reserve without undoing or altering the actual transaction.

AI-15D reserves max(historical expense estimate, remaining scheduled expense). To avoid counting forecast expenses and scheduled bills twice, forecast_expense.amount retains the full historical estimate, while its balance_impact is the negative **residual** of the already-computed expected_expense_reserve minus scheduled_expense_reserve. This subtraction attributes an existing reserve; it is not a second forecast formula. For estimate 7,000 and bills 10,000, forecast amount is 7,000 but forecast cash impact is zero; scheduled bills carry -10,000. For estimate 7,000 and bills 4,000, residual forecast impact is -3,000. The evidence exposes both source reserve values.

With a complete uncropped projection window, starting cash plus future_projection impacts reproduces AI-15D ending cash. Checkpoints never add cash or overwrite account balances. Actual-history impacts and context amounts must not be included in that sum.

## Obligations, dates and currencies

Original_amount, allocated_amount, remaining_amount and reserved_amount come from the shared AI-15C calculation. Original schedule principal is never overwritten. Paid/cancelled/fully allocated obligations are excluded from future events. Active payments are dated by the actual transaction, independently of the obligation's due date. A due date outside the display window does not hide an in-window confirmed transaction relationship.

Scheduled expenses due on or after as-of carry only remaining reserve. Overdue plans may appear for review in the displayed history window, with status overdue and zero future impact, preserving AI-15D's exclusion from future reserves. Scheduled income has uncertain certainty and zero balance impact. It never increases authoritative available/projected cash.

Native transaction currency and safely owned account metadata are preserved. Accountless imports retain the project's BDT assumption. Foreign-currency actuals remain historical context in their native currency and are never combined with BDT projections. Malformed cross-owner account links are excluded rather than exposing account metadata.

Actuals are limited to dates on or before Bangladesh today/as-of, matching existing forecast actual-history conventions; future-dated imported rows are not represented as already-happened actuals. All date windows are inclusive. Historical statuses/allocations remain current persisted state, not versioned as-of replay.

## Forecasts, unknowns and runway checkpoints

The timeline always uses the existing historical runway mode for projections. Three complete prior months with usable records and established account cash remain required. Missing/conflicting cash stays null. No history means no fabricated forecast events or checkpoints, while actuals, payment relationships and schedules can still appear. A user without any events receives a valid empty list and zero certainty counts.

Forecast segments are dated at their existing checkpoint/segment end for chronological display. Their full period and source mode remain in evidence. A segment-end label is not an exact expected transaction day. Existing minimum balances are copied verbatim; they preserve the conservative expense-before-income assumption. No precise depletion day is inferred from monthly forecasts. Known-obligations-only mode remains available from the separate runway endpoint and is not silently mixed into this historical scenario.

## API

Authenticated read-only GET /finance/timeline accepts three optional parameters:

- start_date: inclusive ISO date, defaults to Bangladesh today minus 30 days.
- end_date: inclusive ISO date, defaults to Bangladesh today plus 30 days.
- include_estimates: boolean, default true; false omits estimated forecast/checkpoint events, without changing authoritative summary values.

Ranges must be ordered, span at most 732 days, and end at most 366 days in the future. Invalid input returns 422, missing authentication 401. All transaction, account, allocation and schedule queries are owner-scoped. There is no user-id parameter or mutation endpoint.

Response metadata includes currency (the BDT summary currency), as_of_date, display period, projection_period, starting_balance/balance_source, ending_projected_balance, runway_status, events, certainty event_counts, assumptions and limitations. Monetary fields serialize as Decimal strings, unknowns as null. Historical-only windows do not claim a starting/projected balance for that old period. A window ending today may expose today's cash but has no forward projection.

Date filters crop events; forecasts remain anchored at as_of_date through end_date. A future-only crop may omit earlier obligations or partial-segment events. Do not attempt to reconstruct the full projection by summing cropped events or an estimate-hidden view. projection_period makes that distinction explicit.

## Frontend

A compact on-request timeline is added to Cashflow, using the existing generated API client, authentication, BDT formatting, English/Bengali translations and visual system. It shows current/projected cash (null as Not available), date range, ordered events with text certainty badges, separate amount/cash-impact labels, obligation breakdown, source/payment links and source limitations. User records are not translated. Non-BDT event amounts retain their native currency code. Estimated and uncertain rows also have distinct border patterns; meaning does not depend on color.

The initial view displays 20 events; Show more reveals another 20 without duplicating rows. Refresh clears stale data. Schedule/allocation revision resets the component. Loading, errors/retry and empty states are explicit. Semantic ordered lists, headings, time/date labels and responsive wrapping support desktop/mobile accessibility without a new design or charting library.

## Tests and validation

Focused backend tests cover signed actuals/fees/currencies/accounts, ownership, malformed cross-owner links, unpaid/partial/multiple/exact/paid/cancelled/revoked/candidate obligations, zero-impact payment relationships, payment-date versus due-date windows, uncertain income, overdue context, forecast attribution above/below scheduled reserves, complete-projection cash reconciliation, multimonth segments, unknown cash/history, deterministic date/priority/source ordering, unique ids, date filters, estimate hiding, empty/read-only behavior, authentication, validation and serialization.

Frontend tests cover unique events, certainty/scope labels, nulls, loading, errors/retry, empty state, Bengali/user-content preservation, progressive display and refresh. Browser tests cover the timeline in both languages on desktop/mobile, with axe and overflow checks. Existing AI-15A/B/C/D tests remain unchanged. The existing CI backend selection includes the new timeline suite.

Validation completed:

- Focused AI-15E backend: 25 passed.
- Full backend: 494 passed, 1 existing opt-in smoke skip; 7 existing Alembic configuration deprecation warnings.
- Updated CI-selected backend tests under SQLite: 147 passed.
- Python compileall backend/app: passed.
- Generated frontend contract consistency: passed.
- Frontend typecheck, lint, production build: passed.
- Frontend unit tests: 51 passed across 10 files, including 6 new timeline tests.
- Focused Chrome timeline scenarios: 2 passed (desktop/mobile, both languages).
- Complete Chrome browser suite: 25 passed, 5 existing duplicate mobile viewport skips; accessibility and overflow included.
- git diff --check: passed.

An initial unit-test selector expected a standalone scope label although it shares an element with the event type; its matcher was corrected. Initial browser runs sampled the existing language buttons during their brief color crossfade and flagged contrast. The new test explicitly waits for active language-button transitions to finish before the same axe checks; the final focused and complete browser runs passed. No accessibility rules or assertions were removed.


## Limitations and extension points

This is a live read model rather than a ledger or consistent historical replay. Separate queries/requests may observe newly committed changes. Read windows are bounded but event counts are not server-paginated; large histories may need cursor pagination and bounded allocation batches. Current allocation reads reuse the existing owner-scoped repository and can scan active user history. Monthly estimates retain their original uncertainty and cannot establish precise payment/depletion dates. Filtering hides events but never changes accounting reality. No FX conversion, bank synchronization, recurring expansion, automatic matching, transaction splitting, new forecasting algorithm or LLM financial calculation is added.

Future structured-coach integration can consume the typed response or a deliberately bounded summary, rather than asking a model to infer principal, confidence or cash impact from free text. Versioned accounting snapshots, transfer classification, pagination and richer dated forecasts remain separate work.
