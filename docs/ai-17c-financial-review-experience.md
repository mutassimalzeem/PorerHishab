# AI-17C Financial Review Experience: pre-commit review

Date: 2026-11-06, Asia/Dhaka. Branch: `feature/ai-17c-financial-review-experience`.

## Starting audit and implementation plan

The initial workspace already contained six modified coach implementation files and `backend/test_financial_coach_review.py` (14 passing tests). No frontend review integration was present. HEAD was `4f051d8`, the merge of PR #64 / AI-17B; a fresh `git fetch origin` confirmed `HEAD...origin/main` was `0 0`. The three required AI-17 architecture, correctness and review documents were read. No workspace AGENTS.md was found.

Before editing, the plan was to validate existing coach changes, finish the typed API/Insights panel using existing evidence and notes components, extend safety and stale-context coverage, regenerate contracts, run isolated backend/frontend verification, and deliver without committing. The file inventory was the six existing backend coach files, review tests, API client/contracts, Insights and its new panel, localization, focused UI/browser tests, a synthetic fixture, and this report.

Inspected the current AI-16 plan/decision/execution contracts, AI-17B service/endpoint, frontend API client, FinancialContext, FinancialCoach, ActionPlan, useResource and localization. `FinancialContext` is an existing coverage component, not a provider. No duplicate client, context, evidence widget or planner was introduced. The client supplies bearer credentials and handles refresh/session expiry; useResource suppresses results after cleanup. The review panel additionally remounts its explanation on refresh/completeness/revision changes.

## Architecture and behavior

`/coach/ask` routes financial-review questions to the canonical AI-17B service using authenticated identity and the server's Dhaka date. Schedule confirmation retains AI-17B completeness semantics. Client evidence, dates, priorities, execution data and owner IDs are never used as authoritative review input. Mismatched server context dates fail with the existing sanitized error response.

Review explanations are deterministic projections, including when a provider is configured. The validator reconstructs every review response surface from canonical data before applying existing AI-17A evidence/numeric/semantic validation. This intentionally avoids treating regex matching as proof that arbitrary model prose preserves priorities, blockers and authorization. Other coach intents retain their provider and fallback paths. Nested canonical evidence serialization supports Decimal/date values.

The typed frontend method calls authenticated GET `/finance/review`. Insights replaces its old ActionPlan block with the canonical review. It displays reporting date/horizon, status, warnings, backend priority order, ready/blocked review steps, prerequisite titles/factors, source evidence/provenance, assumptions, limitations, cash and capacity. Existing Amount renders unknown as unavailable and actual zero as zero. Links use existing Plans, Accounts, Transactions and Cashflow routes. No financial arithmetic or priority sorting occurs in React.

The explanation action calls the existing coach workflow with a fixed review question and the same schedule completeness assertion. Before displaying an explanation, the UI compares the date, horizon, priorities, steps, evidence, capacity, completeness and data status with the displayed review. Object keys are normalized; only observation timestamps are excluded because AI-17B creates new observation metadata on each read. Changed data prompts refresh. In-flight explanations are discarded after refresh. Existing ResourceView provides loading/errors/retry. Empty and insufficient-data states retain explicit limitations. English/Bengali controls and a Bengali review narrative are supported; source prose and user records retain their original language.

## Exact changed-file inventory

1. `backend/app/api/financial_coach.py` - pass completeness assertion.
2. `backend/app/schemas/financial_coach.py` - review intent and optional completeness field.
3. `backend/app/services/finance/financial_coach_evidence.py` - owner-scoped canonical review and comparison evidence, date guard.
4. `backend/app/services/finance/financial_coach_generator.py` - canonical review actions/narrative, Bengali fallback and deterministic provider boundary.
5. `backend/app/services/finance/financial_coach_router.py` - narrow English/Bengali review phrases.
6. `backend/app/services/finance/financial_coach_validator.py` - reconstruct canonical review surfaces, retain existing validator.
7. `backend/test_financial_coach_review.py` - review API, isolation, hostile output, missing data, provider, date and write-safety tests.
8. `frontend/src/generated/api.ts` - repository-generated additive coach contracts.
9. `frontend/src/lib/api.ts` - typed GET review method.
10. `frontend/src/lib/translations.ts` - Bengali review labels.
11. `frontend/src/pages/Insights.tsx` - canonical review replaces old action-plan block.
12. `frontend/src/components/FinancialReview.tsx` - review panel and explanation context checks.
13. `frontend/src/test/financial-review.fixture.json` - synthetic real-engine output from an isolated in-memory test fixture.
14. `frontend/src/test/financial-review.test.tsx` - order, blockers, language, empty/error, missing/zero and stale context tests.
15. `frontend/e2e/finance.spec.ts` - canonical fixture and desktop/mobile review retry/keyboard/Bengali/accessibility coverage.
16. `docs/ai-17c-financial-review-experience.md` - this report.

## Financial safety and security

GET `/finance/review` and its service are unchanged and remain read-only. Coach explanation persists only existing owner-scoped conversation/message history. Financial-table snapshots and captured SQL verify no financial writes. No payment, transfer, allocation, goal update, feedback submission, automatic unblocking or execution was introduced. Ready means ready to review. Existing mutation endpoints and confirmation boundaries remain intact. AI-16 and AI-17A/B policies and schemas are unchanged. No migration, table or dependency was added.

Tests cover no-goal/cash-only and empty users, dependencies/blockers, unknown capacity, invented amounts, reordered priorities, false step states, execution claims, hostile replacement actions, authentication, cross-owner isolation, ignored client context, mismatched dates, disabled/enabled providers, existing intents, and no financial writes.

## Verification commands and results

Offline backend checks use `AI_EXTERNAL_ENABLED=false`. Focused commands set `DATABASE_URL=sqlite:///:memory:`. PowerShell expands test filenames explicitly because pytest does not expand a Windows wildcard argument:

```powershell
$tests = @(rg --files backend -g 'test_financial_coach_*.py' -g 'test_financial_review.py' -g 'test_financial_planner.py' -g 'test_financial_prioritization.py' -g 'test_financial_execution*.py')
.\.venv\Scripts\python.exe -m pytest @tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check
.\.venv\Scripts\python.exe -m compileall -q backend scripts
```

Focused final: **340 passed**, one existing HTTP-status deprecation warning. Contract generation, freshness and compileall passed.

Disposable PostgreSQL databases `ai17c_review_20261106_01` and `ai17c_review_20261106_02` were created with `docker exec zyra-db createdb -U zyra <name>`. A Python wrapper read local credentials without printing them, replaced only the database name in DATABASE_URL, and invoked `python -m alembic upgrade head` followed by `python -m pytest backend -q --tb=short -rs`. Both databases were empty before migration. The development database was never migrated or modified. The initial complete run passed **1229 tests**, with one opt-in live embedding skip and 49 existing warnings. Final clean migrated PostgreSQL run: **1234 passed, 1 skipped, 49 warnings in 146.12s**. The skip is the existing opt-in live embedding smoke test. Warnings are existing Alembic path_separator and HTTP-status deprecations.

Frontend commands (from frontend):

```powershell
npm run typecheck
npm run lint
npm test -- --reporter=dot
npm run build
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:browser -- e2e/finance.spec.ts
```

Focused review UI: **7 passed** before adding source-value and missing/zero tests. Focused desktop/mobile review browser checks: **2 passed**, including axe accessibility, keyboard retry, Bengali and overflow checks. Final frontend: typecheck and lint passed; **183 unit tests passed in 25 files**; production build passed. Existing jsdom/axe canvas diagnostic was non-failing, and Vite emitted its bundle-size advisory. Final finance browser suite: **43 passed, 5 intentionally skipped in 1.5 minutes** across desktop and mobile. The five skips are the existing duplicate viewport-matrix cases on the mobile project. The corrected legacy coaching, feedback and outcome tests all passed.

Early verification found and fixed generated optional-field handling, a refresh race, and Node's JSON fixture loading requirement. A first pytest invocation passed an unexpanded Windows wildcard and collected no tests; the explicit filename list above resolved it. The first broader finance browser run found six failures (three tests on each viewport) because legacy page-wide coaching selectors also matched the new review cards. These were scoped to `.coaching-list`; the removed action-plan count assertion was moved to existing feedback history. The suite was rerun after these test changes. No failing checks are represented as passing.

## Limits

- Review narrative uses deterministic templates; no live-provider validation was run or needed for that path. Existing unrelated intent provider behavior remains.
- Backend source prose, canonical titles, claim/action details and some prerequisite descriptions retain their original language, following existing localization policy. Bengali narrative and frontend-owned controls are translated.
- Browser tests use mocked HTTP contracts and synthetic financial data; they are not a live authenticated end-to-end backend/browser session.
- Reviews are composed from separate source reads under existing isolation behavior, not an atomic immutable ledger snapshot. Historical date/source-completeness limits from AI-17B remain.
- Legacy coaching feedback/outcome/effectiveness sections remain because their existing recommendation IDs have distinct semantics. Only the duplicate action-plan block was replaced.
- Test databases are retained as disposable test artifacts. No development data was touched.

## Workspace and delivery

Unrelated untracked `ai17a-new-files.txt`, `ai17a-review-diff.txt`, `frontend/Redesigned Frontend/`, `test_transactions.csv` and `test_transactions_3_months.csv` were preserved. No files were staged, committed, merged or submitted as a PR.

## Final Git checks

`git status --short` (exit 0):

```text
 M backend/app/api/financial_coach.py
 M backend/app/schemas/financial_coach.py
 M backend/app/services/finance/financial_coach_evidence.py
 M backend/app/services/finance/financial_coach_generator.py
 M backend/app/services/finance/financial_coach_router.py
 M backend/app/services/finance/financial_coach_validator.py
 M frontend/e2e/finance.spec.ts
 M frontend/src/generated/api.ts
 M frontend/src/lib/api.ts
 M frontend/src/lib/translations.ts
 M frontend/src/pages/Insights.tsx
?? ai17a-new-files.txt
?? ai17a-review-diff.txt
?? backend/test_financial_coach_review.py
?? docs/ai-17c-financial-review-experience.md
?? "frontend/Redesigned Frontend/"
?? frontend/src/components/FinancialReview.tsx
?? frontend/src/test/financial-review.fixture.json
?? frontend/src/test/financial-review.test.tsx
?? test_transactions.csv
?? test_transactions_3_months.csv
```

`git diff --stat` (exit 0):

```text
 backend/app/api/financial_coach.py                 |   1 +
 backend/app/schemas/financial_coach.py             |  10 +
 .../services/finance/financial_coach_evidence.py   | 194 ++++++++++++++
 .../services/finance/financial_coach_generator.py  | 285 ++++++++++++++++++++-
 .../app/services/finance/financial_coach_router.py |  25 ++
 .../services/finance/financial_coach_validator.py  |   8 +
 frontend/e2e/finance.spec.ts                       |  74 ++----
 frontend/src/generated/api.ts                      |   4 +-
 frontend/src/lib/api.ts                            |   4 +
 frontend/src/lib/translations.ts                   |  17 ++
 frontend/src/pages/Insights.tsx                    |   4 +-
 11 files changed, 575 insertions(+), 51 deletions(-)
```

`git diff --check` (exit 0):

```text
(no output)
```

`git diff --stat` reports tracked files only; new task files are included in the inventory above. Git emitted existing LF-to-CRLF normalization advisories for three frontend files; diff whitespace validation passed. The unrelated untracked files listed above remain present.

## Exact isolated PostgreSQL wrapper

After `docker exec zyra-db createdb -U zyra ai17c_review_20261106_02`, this code was piped through PowerShell to `.\.venv\Scripts\python.exe -`:

```python
import os, subprocess
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
url = make_url(dotenv_values('.env')['DATABASE_URL']).set(database='ai17c_review_20261106_02')
env = dict(os.environ, DATABASE_URL=url.render_as_string(hide_password=False), AI_EXTERNAL_ENABLED='false')
for args in [['-m', 'alembic', 'upgrade', 'head'], ['-m', 'pytest', 'backend', '-q', '--tb=short', '-rs']]:
    result = subprocess.run([os.sys.executable, *args], env=env)
    if result.returncode:
        raise SystemExit(result.returncode)
```

Only the newly created test database was selected in this subprocess environment. No credentials were printed or written into the repository.

Delivery state: implementation and required verification complete. Stopped before staging, committing, opening a PR or merging; ready for human review.
