# AI-15B: transaction-to-obligation reconciliation

Implemented from `origin/main` at `b1dccd2` on `feature/ai-15b-obligation-reconciliation`. The pre-existing untracked frontend redesign directory and two transaction CSV files are preserved and excluded from commits.

## Design and persistence

The existing schedule is a single dated income/expense expectation with a positive `Numeric(14,2)` amount. Transactions use signed `Numeric(14,2)` amounts. There was no separate scheduled-cashflow repository/service: its CRUD lives in the authenticated finance router. AI-15B adds a small scoped repository and deterministic reconciliation service rather than an account-management abstraction.

`obligation_allocations` stores whole-transaction principal allocations with owner, schedule, transaction, amount, confirmation time, active flag, and revocation time. Multiple transactions can settle a schedule. A partial payment never changes the scheduled amount. Suggested candidates are computed and never stored as confirmations. Active persisted rows are explicit user confirmations; revoked rows remain as history.

Composite foreign keys `(item_id,user_id)` and `(transaction_id,user_id)` enforce ownership in PostgreSQL. A positive-amount check, owner/item index, and partial unique active-transaction index prevent invalid principal and transaction reuse. Parent `(id,user_id)` unique constraints support those foreign keys. Parent deletions are restricted when allocation history exists. API edits also protect reconciled amount, direction, and due date; reconciled records cannot be cancelled or deleted.

Confirm, revoke, schedule patch and schedule delete acquire the same owner row lock. Under the repository's PostgreSQL default READ COMMITTED isolation, requests for one owner serialize, so a second request observes the first committed allocation before checking remaining principal. The unique index independently rejects transaction reuse. This is tested with real concurrent sessions, including two transactions competing for one schedule and one transaction competing for two schedules. SQLite is not a substitute for this concurrency guarantee.

The shared `scheduled_totals` calculation reserves only original principal minus active allocations, preventing partial payments from being reserved again. Historical transaction totals and original scheduled amounts remain separate.

## Matching rules

- Same authenticated user and matching signed direction are mandatory.
- Only the user's BDT accounts and unlinked imports assumed BDT are eligible, consistent with existing finance facts. There is no currency conversion.
- Default inclusive date tolerance: 7 days either side of the due date; configurable from 0 through 90.
- Default absolute amount tolerance: BDT 0.00; configurable through BDT 1,000,000.00 with at most two decimal places.
- Exact remaining-principal matches, amounts within tolerance, and smaller partial principal payments are candidates. Positive income and negative expense are determined by stored amount; text classification cannot override direction.
- Category equality and title/notes token overlap with merchant/description are supporting signals. They cannot bypass ownership, direction, amount, date, or prior allocation rules.
- Candidates sort by absolute remaining-amount difference, date distance, then transaction ID. Multiple candidates are marked ambiguous and require review. Confidence is qualitative low/medium, never certainty or a probability.
- Cancelled and paid schedules produce no candidates; already allocated transactions are excluded. Repeated reads are deterministic and write nothing.
- Amount tolerance never authorizes an over-allocation. Oversized candidates can be reviewed but cannot be confirmed. Allocations consume the entire transaction principal; splitting one transaction across obligations is deliberately unsupported.
- Fees stored separately are excluded from settlement principal. No LLM or floating-point money arithmetic is used. Frontend comparisons use integer cents; progress converts a bounded integer ratio to a display number.
- Timing is independently overdue/due/not_due using Dhaka's date. Reconciliation distinguishes partial, review_required, unmatched, insufficient_data, paid, cancelled, overdue and not_due. A fully allocated schedule remains unmarked until explicit full-payment confirmation.

## Authenticated API

All paths below start with `/finance/scheduled-cashflow` and require the existing bearer authentication.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/reconciliation` | Paged owner-only overview; `limit` 1..500, `offset` >= 0 |
| GET | `/{item_id}/matches` | Candidate evidence, allocation history, original/allocated/remaining amounts and timing |
| POST | `/{item_id}/matches/{transaction_id}/confirm` | Confirm principal allocation; JSON `{ "confirm_full_settlement": false }` |
| DELETE | `/{item_id}/matches/{transaction_id}` | Revoke allocation, retain audit row, reopen paid item |

Both GET routes accept optional ISO `as_of`, `date_tolerance_days`, and decimal `amount_tolerance`. The static overview route is registered before existing dynamic item routes. Overview batches transaction/allocation reads for the page.

`confirm_full_settlement: true` requires exact full settlement after allocation and marks paid in the same commit. Repeating a confirmation for the same item/transaction returns the existing state without duplicating an allocation; retrying with full confirmation cannot mark a partial payment paid. Removing an already removed allocation is idempotent. Revoked transactions may subsequently be explicitly reallocated, creating a new history row.

404 hides foreign-owned/missing schedules and transactions. 409 reports an already allocated transaction, terminal schedule conflict, immutable terms, or protected history. 422 reports invalid request fields, currency/direction mismatch, over-allocation, or incomplete full settlement. Explicit confirmation is an owner assertion and may select a transaction outside the suggestion date window; the date tolerance controls suggestions, not authoritative financial truth.

### Compatibility decision

The existing domain explicitly supports manually marking schedules paid without a transaction (and existing tests pin that behavior). This explicit action remains available for schedules without reconciliation history. It does not claim transaction verification. Once reconciliation history exists, paid status requires full allocation. Revocation reopens an allocation-settled schedule. Changing this existing manual-paid domain is deferred rather than silently rewriting existing records.

## Frontend

Cashflow has a review control for each scheduled item, with loading/retry, empty, error and success states. Expanding shows status/timing, principal progress, remaining amount, exact tolerance settings, ambiguous-match guidance and candidate amount/date/category/text evidence. Confirm allocation and confirm allocation plus full payment are distinct actions. Confirmed allocations can be removed; full allocations can be explicitly marked paid later. Overpayments are disabled with an explanation. Allocation changes invalidate displayed cashflow scenarios. English and Bengali copy follows the existing localization system. Controls wrap below the original schedule row at desktop/mobile sizes.

## Migration

`f15b00000001` follows `8d51117bc8d5`, adds parent ownership unique constraints and creates the allocation table/indexes. `alembic upgrade head` was executed on the configured development PostgreSQL database. A temporary isolated PostgreSQL schema tests upgrade, populated schedule preservation on downgrade, and upgrade again. Downgrade drops allocation history and parent helper constraints while preserving schedules and transactions; it is a rollback operation, not an audit export.

## Changed files

- Models: `backend/app/models/{obligation_allocation,scheduled_cashflow_item,transactions,__init__}.py`
- Migration: `alembic/versions/f15b00000001_obligation_allocations.py`
- Repository/schema/service: `backend/app/repositories/obligation_reconciliation.py`, `backend/app/schemas/obligation_reconciliation.py`, `backend/app/services/finance/obligation_reconciliation.py`
- API: `backend/app/api/{obligation_reconciliation,scheduled_cashflow}.py`, `backend/app/main.py`
- Shared unpaid reserve: `backend/app/services/intelligence/facts.py`
- Backend regression suite: `backend/test_obligation_reconciliation.py`
- Frontend: `frontend/src/components/ObligationMatches.tsx`, `frontend/src/pages/Cashflow.tsx`, `frontend/src/lib/{api,translations}.ts`, `frontend/src/styles.css`, generated `frontend/src/generated/api.ts`
- Frontend regressions: `frontend/src/test/obligation-matches.test.tsx`, `frontend/e2e/finance.spec.ts`
- This report: `docs/ai-15b-obligation-reconciliation.md`

## Validation

Commands run from the repository root unless a frontend working directory is specified. Final results:

- `.\.venv\Scripts\python.exe -m pytest backend/test_obligation_reconciliation.py -q`: **15 passed**, including migration roundtrip and concurrency.
- `.\.venv\Scripts\python.exe -m pytest backend -q -rs`: **418 passed, 1 skipped** (opt-in live embedding smoke), 7 existing Alembic configuration deprecation warnings.
- `.\.venv\Scripts\python.exe -m compileall -q backend/app`: **passed**.
- `.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check`: **passed**.
- Frontend `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`: **all passed**; unit tests **41 passed**.
- Frontend `$env:PLAYWRIGHT_CHANNEL='chrome'; npm run test:browser`: **21 passed, 5 skipped**. Existing viewport cases skip the duplicate mobile project; they execute in the desktop project at all five widths. Includes confirm/remove on desktop and mobile, accessibility and overflow checks.
- Final targeted browser rerun after progress/copy polish: **2 passed** (desktop and mobile), including accessibility and overflow checks. A transient Vite proxy refusal was logged during teardown; assertions all passed.
- `git diff --check`: **passed**, including staged whitespace validation.

An initial full backend attempt had three failures because the development DB had not yet received the allocation migration; after applying it, the next full run passed (415 passed, 1 skipped at that stage). Initial UI type checks caught unsupported test selector options, which were removed. Browser testing caught title compression caused by the added control, fixed by placing controls on their own flex row; the subsequent full browser suite passed. The final targeted browser run also caught duplicate success announcements; the parent page now owns the single announcement, and both desktop/mobile scenarios pass. No failures were silently skipped.

## Release and remaining limits

The dedicated branch is intended for a PR targeting `main`; do not merge automatically. Commit identifiers and publishing outcome are reported in the final handoff. GitHub authentication was verified after the user signed in; the branch is ready for publication.

No bank verification, FX conversion, automatic matching/settlement, one-transaction splitting, recurring-instance expansion, or arbitrary overpayment adjustment is provided. Suggestions inspect eligible imported history and cannot prove coverage or that a similarly sized transaction belongs to a particular bill. Overview pages reuse loaded transaction history; very large histories may eventually need a date-window index/query optimization. The existing live embedding smoke test remains opt-in; it does not exercise deterministic reconciliation.

Implementation commits: persistence `80ee325`; service/API/backend regression layer `3490039`. Frontend/report commit and PR URL are provided in the final handoff.
