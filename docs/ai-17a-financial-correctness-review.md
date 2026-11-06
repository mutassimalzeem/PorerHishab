# AI-17A review fixes: final uncommitted review report

Ready for human review. No files were staged, committed, pushed or submitted as a PR. This report supersedes the earlier pre-commit report and its test counts.

Branch: `feature/ai-17a-financial-correctness`; base/HEAD remains `7151fb6` (`origin/main` inspected before implementation). The review fixes add no dependencies, migrations or AI-16 policy changes.

## Findings and fixes

### Bengali UTF-8 verification

The semantic module and its test file were decoded from bytes using strict UTF-8 and parsed with Python AST. Their Bengali literals were already valid; no genuine source mojibake was found. No terminal-encoding workaround or character replacement was used to disguise bad source.

The AST-level `str.maketrans` arguments both have length **10**. The source is exactly U+09E6 through U+09EF; the destination is ASCII `0123456789`. Runtime translation returns those ten ASCII digits. UTF-8 source checks, Bengali currency/metric regex checks and semantic-module import checks pass. The validator's Bengali source was also checked before editing and was valid.

### Financial semantics

The previous early return for clauses without a recognized metric or currency allowed bare unknown money claims through. Every numeric token now needs an explicit classification: calendar date, nonmonetary dimension, known educational ratio, or supported monetary assertion. Currency omission no longer bypasses checking. Unknown monetary metrics, bare emergency-fund claims, ambiguous alternatives and source-like expense wording used to imply cash fail closed.

Monetary matches require metric identity, exact signed Decimal, supported currency, applicable date and evidence classification. IDs must be unique, source/ID/date metadata must be present, and recognized ID/label metrics must agree. Missing amounts never become zero. Raw, derived, interpreted and estimated evidence are kept distinct; arbitrary interpreted money is not treated as a recorded fact. No available cash is inferred from expenses, income, savings or balances.

Nonmonetary counts, percentages, durations, date tokens and health-score ratios have separate syntax checks. Currency adjacency and Bengali numeral/count suffixes are handled explicitly. Terse legacy `Total: <amount>` summaries retain their expense meaning; `Total wealth`, for example, does not inherit that exception.

Fallback claims/actions are checked independently against their own evidence references on every fallback path. Fallback summaries, warnings and limitations are filtered too. When a template contains unsupported money, the answer uses fixed metric names and actual supported values; producer labels cannot supply new financial assertions. Rendered fact lines are themselves validated. Response evidence is copied from the supplied package rather than trusting generator-supplied evidence.

**Provenance limit:** CoachEvidence has producer-supplied `source`, `evidence_id`, label, classification and date fields. These support membership and metadata-consistency checks, not independent authentication. The validator does not authenticate database origin, attest the source string, establish tenant ownership, or recompute upstream calculations. It relies on the existing tenant-scoped evidence assembler. A forged but internally consistent package cannot be disproved from this contract alone. No claim of independent provenance verification is made.

### CSV integrity

The endpoint no longer computes summaries from a dataframe that exists before persistence. `save_transactions(..., detailed=True)` normalizes once and returns the actual records returned/refreshed by the existing repository. Counts, totals and preview use that same result. Existing callers can still receive the legacy integer count.

- `rows_received`: parsed CSV data records, excluding the header and blank lines ignored by pandas.
- `rows_persisted`: actual records returned after successful repository persistence.
- `records`: compatibility alias for `rows_persisted`.
- `rows_rejected`: `rows_received - rows_persisted`; currently invalid date/amount rows.
- `rows_skipped`: zero; this importer has no skipping/deduplication policy.
- Errors identify parsed record number (header is row 1), field and correction guidance. A rejected row can have two field errors.

Amounts use Decimal throughout parsing, storage and summation. Actual zeroes and negative amounts are valid. Commas must use normal thousands grouping. Nonfinite values, fractional cents and values outside the existing Numeric(14, 2) boundary are rejected without rounding. Trailing fractional zeroes are accepted if the exact value is already whole cents. Legacy response totals remain JSON numbers at serialization.

String dates must now be valid ISO `YYYY-MM-DD`, year 1900 or later, matching the transaction schema's lower bound. Ambiguous slash dates, malformed dates and invalid calendar dates are rejected rather than guessed. Programmatic date/datetime values remain supported. This is an intentional compatibility tightening and is explained in row errors.

No new all-or-nothing policy was introduced: valid rows still import while validation-invalid rows are reported. A persistence/commit failure never returns a success response; the service rolls back and the API returns a sanitized failure. Repeated uploads still append duplicates because this CSV path supplies no external transaction ID. No deduplication policy was invented.

## Every changed file and why

Paths below cover the entire current AI-17A uncommitted diff, including implementation from the preceding turn.

| File | Reason |
| --- | --- |
| `backend/app/main.py` | Remove amount-to-zero preprocessing; publish additive row/error fields; derive counts, Decimal totals and preview from actual persisted records; preserve client errors and sanitize persistence failures. |
| `backend/app/services/transaction_service.py` | Decimal amount/precision policy; explicit ISO calendar-date policy; row errors; detailed persisted-result object with legacy integer return compatibility. |
| `backend/app/services/finance/financial_coach_semantics.py` (new) | Typed projection of existing evidence, strict numeric classification, exact money matching, conservative ambiguity handling and explicit provenance limitations. |
| `backend/app/services/finance/financial_coach_validator.py` | Apply semantic checks across generated fields; preserve signs; validate every fallback surface/reference; render safe structured facts; return original package evidence. |
| `backend/test_csv_amount_integrity.py` (new) | Isolated CSV parser/API/persistence regression tests, including the review's date and boundary cases. |
| `backend/test_financial_coach_semantics.py` (new) | Stub-only monetary misuse, metadata, nonmonetary compatibility, safe fallback, UTF-8/AST mapping and classification regressions. |
| `backend/test_financial_coach_api.py` | Four API cases proving repaired answer/summary/claim/action content is not persisted as unsupported cash. |
| `backend/test_intelligence_api.py` | Explicit upload schema expectation includes every additive count/error field. |
| `frontend/src/generated/api.ts` | Generated row-error/upload response contracts. No schema regeneration delta was needed during this review; freshness was checked. |
| `frontend/src/pages/Transactions.tsx` | Show actual import/rejection counts and corrective row errors instead of unconditional import success wording. |
| `frontend/src/test/csv-upload.test.tsx` (new) | Verify partial import counts and row errors are shown. |
| `docs/ai-17a-financial-correctness-review.md` (this report) | Replace stale review claims/results with the actual final behavior, validation, compatibility changes and limitations. |

The frontend and API-contract test changes existed before this review-fix turn and remain part of the uncommitted AI-17A implementation.

## Every added regression test

Each parameterized test's input families are listed, rather than hiding separate cases behind a single test name. This review added **77 backend parameterized cases** to the previous implementation's 1120 passing backend cases.

### CSV (`backend/test_csv_amount_integrity.py`)

| Test | Behavior protected |
| --- | --- |
| `test_amount_policy` | Positive, comma-formatted, negative, zero, cent precision, trailing zeroes, empty/missing/invalid values, fractional cents, NaN, infinity, overflow, malformed grouping and boolean input. |
| `test_partial_import_counts_totals_and_repeated_upload` | Mixed valid/invalid rows; field/row errors; exact persisted amounts and counts; signed totals; intelligence totals and coach evidence coverage; duplicate-appending repeat behavior. |
| `test_all_rejected_or_header_only` | Zero persistence and zero imported totals for all-invalid or header-only files. |
| `test_missing_columns_or_empty_file_is_client_error` | Missing date/amount columns and an empty file return HTTP 400. |
| `test_persistence_failure_does_not_report_success` | A save failure returns HTTP 500 and does not disclose raw database error text. |
| `test_precision_and_nonfinite_boundaries` (review) | Both signs at 999999999999.99; overflow at 1000000000000.00; positive/negative fractional cents; float NaN and both infinities; negative infinity text. |
| `test_explicit_iso_date_policy` (review) | ISO dates; valid leap day; lower bound; two ambiguous slash orders; year-first slash date; invalid leap/calendar/month/day values; missing zero padding; pre-1900, relative, missing and numeric input. |
| `test_ambiguous_and_invalid_calendar_rows_are_rejected` (review) | API imports only valid ISO/leap-day rows and reports four invalid date rows with format guidance; totals exclude rejected rows. |
| `test_upload_summary_uses_actual_database_values` (review) | Simulated database canonicalization changes 1.23 to 9.87; the stored amount, preview and response totals all report 9.87. |
| `test_database_commit_failure_rolls_back_import` (review) | A real repository commit failure returns HTTP 500, leaves no inserted transactions and does not expose private failure details. |

### Semantics (`backend/test_financial_coach_semantics.py`)

| Test | Behavior protected |
| --- | --- |
| `test_semantic_misuse_falls_back` | Expenses as cash; income as balance; counts/percentages/months as money; bare cash; unsupported and mismatched currency; both sign reversals; unknown balances; estimates relabelled as recorded; stale/different dates; English/Bengali numerals; no-space currency; multiple metrics in one answer. |
| `test_correct_metric_value_unit_type_and_date_pass` | Real zero; negative recorded value; income with correct metric; explicitly estimated savings; valid Bengali expenses; USD facts; explicitly dated historical evidence. Renamed to avoid claiming provenance authentication. |
| `test_all_surfaces_enforce_meaning` | Unsupported cash in summary, claims and actions is repaired/removed. |
| `test_external_ai_disabled_never_calls_provider` | Provider seam raises if invoked; unknown balances never produce zero cash. |
| `test_unknown_or_ambiguous_money_fails_closed_without_currency` (review) | Emergency/rainy-day funds; nest eggs, cushions, wealth, purchasing power; unclassified amounts and money set aside; expense-source laundering; numeric-before-metric wording; trailing cash semantics; cash-or-expense alternatives; Total wealth; fake currency; percentages/months masquerading as cash; fractional precision, malformed grouping, sign-before-currency; bare Bengali emergency amounts. |
| `test_nonmonetary_counts_dates_percentages_and_durations_remain_valid` (review) | Transactions, goals, alerts, saved scenarios, coverage percentages, score ratios, month/day durations, duration ranges, ISO date metadata, mixed spending/count sentence, Bengali count suffixes. |
| `test_incomplete_or_conflicting_metadata_cannot_authorize_money` (review) | Empty source, missing date, unknown amount, conflicting ID/label metrics, and arbitrary interpretation cannot authorize money. |
| `test_duplicate_ids_and_cash_inference_are_rejected` (review) | Duplicate evidence identifiers are ambiguous; expenses, income, savings and balances never authorize available cash. |
| `test_fallback_rechecks_each_reference_and_cannot_reuse_other_evidence` (review) | A stub deterministic fallback cannot borrow a value from unrelated evidence, invent an emergency reserve, or turn an unknown balance into zero; final rendered answer is checked too. |
| `test_utf8_bengali_source_literals_and_digit_mapping` (review) | Strict UTF-8/AST checks of module/test bytes; no replacement/mojibake markers; both mapping arguments length ten; exact Bengali code-point range; correct ASCII translation and currency/metric regex behavior. |
| `test_recorded_derived_estimated_classification` (review) | Recorded raw facts stay valid; raw facts cannot claim to be derived; derived facts stay valid; estimates cannot claim to be recorded; explicitly estimated facts remain valid. |

An autouse test fixture blocks `_call_llm` for all semantic validator tests. No new test calls an external LLM.

### API, contract and frontend regressions

- `test_semantic_repairs_are_persisted` in `backend/test_financial_coach_api.py`: four parameterized generator stubs target answer, summary, claim and action. API responses and stored assistant messages must not retain expense-as-cash assertions.
- Existing `test_auth_and_csv_routes_publish_explicit_response_contracts` now checks the new schema fields explicitly; its assertion was updated, not weakened.
- `reports partial CSV persistence and row errors` in `frontend/src/test/csv-upload.test.tsx`: actual persisted/received counts, rejected count and row correction text appear in the UI.

## Exact validation commands and results

Commands ran from the repository root unless marked `frontend/`. Python is the existing `.venv` Python 3.12. Backend environment was `AI_EXTERNAL_ENABLED=false`. Schema-only/focused SQLite commands used `DATABASE_URL=sqlite:///:memory:`; the full backend used PostgreSQL below. Test runners were not reconfigured and no tests were excluded.

### Focused tests first

The first focused run exposed two newly tested defects (ambiguous cash-or-expenses wording and the Bengali count suffix). Both were fixed without loosening assertions:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/test_csv_amount_integrity.py backend/test_transaction_service.py backend/test_financial_coach_semantics.py backend/test_financial_coach_validator.py -q --tb=short
```

Initial result: **150 passed, 2 failed**. The corrected broader focused run passed 252 cases. After the additional ambiguity/classification regressions, the final focused command was:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/test_csv_amount_integrity.py backend/test_transaction_service.py backend/test_financial_coach_semantics.py backend/test_financial_coach_validator.py backend/test_financial_coach_api.py backend/test_financial_coach_security.py backend/test_financial_coach_schemas.py backend/test_financial_coach_router.py backend/test_financial_coach_evidence.py backend/test_financial_coach_generator.py backend/test_financial_coach_persistence.py backend/test_financial_coach_eval.py -q --tb=short
```

Final result: **260 passed**, one existing HTTP-status deprecation warning, 41.66 seconds. No external provider was called.

### Complete backend on clean migrated PostgreSQL

Created a new empty database in the existing local PostgreSQL 16 container:

```powershell
docker exec zyra-db createdb -U zyra ai17a_review_fixes_20261106_01
```

`DATABASE_URL` was set to that new database on localhost:5432 using the existing local test role. No production/development financial database was migrated. Then:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest backend -q --tb=short -rs
```

Migration reached `f15s00000002`. Full result: **1197 passed, 1 skipped**, 49 warnings, **87.92 seconds**. The sole skip is the existing opt-in live embedding smoke test (`RUN_LIVE_AI_TESTS` unset); PostgreSQL-specific tests ran. Existing warnings concern Alembic `path_separator` and deprecated HTTP-status naming. Some unit fixtures intentionally use private SQLite databases; integration tests also exercised actual PostgreSQL. The isolated PostgreSQL database is retained for inspection.

### Complete frontend using existing configuration (`frontend/`)

```powershell
npm run typecheck
npm run lint
npm test -- --run
npm run build
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:browser
```

All commands exited successfully:

- Typecheck: passed.
- Lint: passed.
- Unit suite: **24 files / 173 tests passed**, 54.62 seconds.
- Production build: passed, 7.06 seconds.
- Existing desktop/mobile browser suite: **53 passed / 5 skipped**, 1.4 minutes. The five skips are the existing mobile duplicate viewport-matrix cases; the desktop project runs that matrix once and mobile touch flows have separate coverage. No test was disabled for this task.

Nonfatal diagnostics remain: jsdom/axe canvas support, Vite's existing large bundle warning, and Node color-environment warnings.

### Compile, import, encoding, contract and whitespace checks

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend scripts
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend'); from app.services.finance.financial_coach_semantics import DIGITS, CURRENCY, METRICS; from app.services.finance.financial_coach_validator import FinancialCoachValidator; from app.services.transaction_service import TransactionImportResult; from app.main import app; assert len(DIGITS) == 10; print('Semantic, validator, import service, and API imports OK; DIGITS has 10 entries.')"
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check
git diff --check
```

All passed. Strict UTF-8 decode/AST checks were also run directly on module/test bytes before and after editing, and are reproduced in the persistent UTF-8 regression test. Git's LF-to-CRLF advisory is nonfatal; there are no whitespace errors.

## Unresolved limitations and compatibility implications

1. **Provenance is not authenticated.** Metadata/reference consistency is checked, but actual source truth and tenant scoping remain the assembler's responsibility. No independent source verification is claimed.
2. Semantic matching uses a conservative explicit grammar, not a general natural-language proof system. Unclassified numeric wording falls back. Complex valid prose may be replaced by labelled facts. Quantities spelled entirely as words and arbitrary multilingual paraphrases are not comprehensively parsed. Nonmoney tokens are classified syntactically; this milestone does not revalidate all nonmonetary analytics calculations.
3. Implicit monetary figures follow the existing BDT convention. USD/EUR/GBP require matching evidence; mixed currencies in one clause and unsupported currencies are rejected, with no conversion. The narrowly recognized existing AI-16 planner reserve adapter still relies on its established BDT producer convention when unit is omitted.
4. Raw CSV string dates are deliberately restricted to ISO calendar dates, year 1900 onward. Files relying on pandas date guessing must be corrected. Row errors state the required format.
5. Legacy upload totals serialize as JSON numbers after Decimal summation; clients should use stored Decimal transaction values for subsequent financial calculations. Preview is now composed from persisted transaction fields and omits arbitrary unused CSV columns.
6. CSV record numbers are logical parsed-record numbers, not physical multiline-file line offsets. Row errors cover date/amount validation. Other database constraint failures still fail the request; no new field-validation or import-atomicity policy was introduced.
7. Repeated uploads append duplicate transactions. Deduplication is not implemented.
8. Existing nonfatal warnings and the opt-in live AI test remain as documented above.

## Diff and workspace preservation

Implementation/tests (excluding this report): **11 files, 936 insertions, 60 deletions**, including four new files. This report is the twelfth changed file. Standard `git diff` omits those untracked new-file bodies until staging; nothing was staged to produce these counts.

The unrelated untracked `frontend/Redesigned Frontend/`, `test_transactions.csv`, `test_transactions_3_months.csv`, `ai17a-review-diff.txt` and `ai17a-new-files.txt` were preserved. A baseline of 80 protected files was hashed at review start and rechecked at completion. Staging is empty; HEAD and the working branch are unchanged. No commit, push, PR creation or unrelated deletion was performed.

## Human review readiness

Ready for human review with the limitations above stated explicitly. All requested focused, complete backend/PostgreSQL, frontend, import/compile, contract and whitespace checks passed. Changes remain uncommitted as requested; no publication or approval action is pending in this task.
