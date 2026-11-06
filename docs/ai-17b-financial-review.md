# AI-17B: Financial Review API and Runtime Composition

Branch: `feature/ai-17b-financial-review-api`. Baseline: synchronized `main` / `origin/main` at `13c8365ea61b250568ea38a573696af19e8c43f8` (AI-17A PR #63). The user's explicit request to raise a PR overrides the attachment's stop-before-commit instruction. No merge is performed.

## Architecture and plan

Before editing, inspected the architecture audit, AI-17A context, AI-16A/B/C schemas/services/tests, authentication, registration, contract generator, coaching/feedback, goal context, health, account-position, history and runway services. The implementation plan was to gather existing owner-scoped sources at one shared date, compose A -> B -> C, expose canonical contracts in an authenticated read-only envelope, add offline regressions, and generate/validate contracts.

```text
GET /finance/review
  -> get_current_user (existing bearer authentication)
  -> financial_review(db, current.id, shared as_of)
     -> visible_coaching (existing feedback overlay)
     -> planning_overview (existing shared capacity and goals)
     -> gather_profile (read-only health, not snapshot persistence)
     -> build_financial_plan (AI-16A)
     -> prioritize_financial_plan (AI-16B)
     -> build_financial_execution_plan (AI-16C)
  -> FinancialReview
```

Coaching obtains existing history/runway/obligation/goal facts; goal planning reuses history, account position, runway, accepted plans and earmarks; health reuses history, account position, runway and schedules. No financial formulas, recommendation policies or parallel source of truth were added. Internal repeated reads are retained rather than refactoring established services.

## Endpoint and contract

`GET /finance/review?as_of=2026-11-01&schedules_confirmed=false`

Use `Authorization: Bearer <access_token>`. `as_of` defaults once to `today_dhaka()`; accepted dates are 1900-01-01 through 9998-12-31, leaving room for existing forward horizons. The unchanged reporting horizon runs from as-of through as-of + 30 days, inclusive. `schedules_confirmed` defaults false and asserts schedule completeness only, never execution authorization.

Response fields: literal `status: "review_only"`, literal true `requires_user_confirmation`, `schedules_confirmed`, `plan: FinancialPlan`, `decisions: FinancialDecisionSet`, and `execution_plan: FinancialExecutionPlan`. Dates/periods, evidence, warnings, assumptions, limitations, ordered priorities, conflicts, dependencies and blockers retain their existing names/types inside these contracts. Every review step requires confirmation. No duplicated top-level money or priority calculation is added. Decimal responses retain string serialization.

Generated TypeScript adds the review operation/envelope and previously internal AI-16 schemas. Existing operations/types are unchanged. No frontend rewrite or client wrapper is introduced.

Actual empty-owner example, generated offline from the service. This is a **selected-field excerpt**; the real response also includes full source evidence, health context, assumptions and limitations:

```json
{
  "status": "review_only",
  "requires_user_confirmation": true,
  "schedules_confirmed": false,
  "plan": {
    "as_of_date": "2026-11-01",
    "data_status": "insufficient_data",
    "planning_horizon": {
      "kind": "coaching_horizon",
      "start": "2026-11-01",
      "end": "2026-12-01",
      "is_complete": false,
      "label": "next 30 days inclusive"
    },
    "warnings": [
      {
        "code": "UNKNOWN_PLANNING_CAPACITY",
        "message": "Planning capacity is unavailable; no funded goal allocation is established."
      }
    ],
    "goal_planning": {
      "capacity": {
        "status": "insufficient_data",
        "trusted_cash": null,
        "conservative_monthly_capacity": null
      }
    }
  },
  "decisions": {
    "policy_version": "ai-16b-v1",
    "priorities": []
  },
  "execution_plan": {
    "policy_version": "ai-16c-v1",
    "steps": []
  }
}
```

Missing financial inputs return 200 with original insufficient/partial statuses and null capacity. Actual zero cash/capacity remains zero. Missing/invalid bearer credentials return 401, invalid query parameters 422, unsupported methods 405, and composition failures a fixed 500 response without database details. Unexpected failures are logged server-side.

## Security and read-only design

Only `get_current_user` supplies identity; no tenant ID, evidence or decisions are accepted as financial context. An extraneous `user_id` query parameter is ignored under existing FastAPI conventions and cannot override `current.id`. All sources receive that same owner ID and shared date. No plan creation, health persistence, feedback submission, alert evaluation, allocation, payment, transfer or LLM call is used.

Tests distinguish two owners by goal IDs, names and monetary values, switch the authenticated dependency, and verify the other owner's data is absent. Missing/invalid tokens exercise the real authentication dependency. Whole-database before/after snapshots and SQL statement capture verify that the tested GET emits no INSERT/UPDATE/DELETE. This is service-level isolation, not database row-level security or independent provenance authentication.

## Files

| File | Purpose |
| --- | --- |
| `backend/app/services/finance/financial_review.py` | Owner-scoped source gathering and A -> B -> C composition; integration limitations. |
| `backend/app/schemas/financial_review.py` | Typed review-only envelope over canonical schemas. |
| `backend/app/api/financial_review.py` | Authenticated GET, bounded parameters and sanitized failure. |
| `backend/app/main.py` | Router registration. |
| `backend/test_financial_review.py` | 18 offline cases covering stage handoff/order, evidence/warnings/assumptions/blockers, feedback visibility, missing/zero, deterministic replay, dates, authentication, isolation, no writes, validation, errors and OpenAPI. |
| `frontend/src/generated/api.ts` | Additive generated contracts. |
| `docs/ai-17b-financial-review.md` | This report and response example. |

AI-16 implementations, policies and existing tests are unchanged. No dependency, model or migration was added.

## Validation: exact commands and actual results

Python: existing `.venv` Python 3.12. Commands ran from repository root unless noted. Tests used `AI_EXTERNAL_ENABLED=false`. Focused and contract commands used `DATABASE_URL=sqlite:///:memory:`. New tests fail if `_call_llm` is invoked.

```powershell
$env:AI_EXTERNAL_ENABLED='false'
$env:DATABASE_URL='sqlite:///:memory:'
.\.venv\Scripts\python.exe -m pytest backend/test_financial_review.py backend/test_financial_planner.py backend/test_financial_prioritization.py backend/test_financial_execution.py backend/test_financial_execution_extra.py -q --tb=short
```

Final focused: **117 passed in 9.72s**. Earlier run: 116 passed before adding feedback visibility. Final review-only suite independently passed 18 cases in 7.44s.

Created a new empty database in the existing PostgreSQL 16 container:

```powershell
docker exec zyra-db createdb -U zyra ai17b_review_20261106_01
```

Executed the following Python wrapper through a PowerShell single-quoted here-string piped to `.\.venv\Scripts\python.exe -`. It reads existing local credentials without printing them and changes only the database name:

```python
import os, subprocess
from sqlalchemy.engine import make_url
from dotenv import load_dotenv
load_dotenv('.env')
url=make_url(os.environ['DATABASE_URL']).set(database='ai17b_review_20261106_01')
env=dict(os.environ, DATABASE_URL=url.render_as_string(hide_password=False), AI_EXTERNAL_ENABLED='false')
for args in [['-m','alembic','upgrade','head'], ['-m','pytest','backend','-q','--tb=short','-rs']]:
    result=subprocess.run([os.sys.executable,*args],env=env)
    if result.returncode:
        raise SystemExit(result.returncode)
```

Migration reached `f15s00000002`. Complete backend: **1215 passed, 1 skipped, 49 warnings in 95.25s**. PostgreSQL-specific tests ran; some existing unit fixtures use private SQLite databases. Sole skip: existing opt-in live embedding smoke. Existing warnings: Alembic `path_separator` and deprecated HTTP-status naming. Isolated database retained; no development financial database was migrated.

The first wrapper invocation used `load_dotenv()` without a filename and stopped before migration/tests because python-dotenv cannot discover the path from this stdin stack. Explicit `.env` fixed the invocation.

```powershell
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py
.\.venv\Scripts\python.exe -m compileall -q backend scripts
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check
git diff --check
# frontend/
npm run typecheck
```

All passed. Contract generation/check imports the registered API and new schema/service/router. New tests assert OpenAPI security, parameters and typed response. Frontend unit/browser/build suites were not rerun: only generated types changed, and TypeScript compilation passed.

## Limitations

- Review only: no execution, persistence, caching, background job or LLM connection. Ready means ready for review, never paid/transferred/allocated/completed. Existing explicit mutation endpoints and user confirmation remain mandatory.
- Missing history, verified cash, complete schedules or earmarks retain source prerequisites. A zero proposal does not establish affordability.
- Source selection retains existing first-five/all-critical coaching behavior; this is not an exhaustive financial issue inventory.
- As-of dates select financial windows over current records, not historical account/goal/feedback versions. Existing stored health context can carry its own date. No upstream temporal policy was changed.
- Services issue separate reads using existing session/isolation behavior; no atomic ledger snapshot under concurrent writes is promised.
- Health retains actual observation timestamps. Identical financial inputs, date and observation time yield identical output (tested). Separate API requests can differ in observation metadata even when decisions are identical; historical observation times are not fabricated.
- Evidence is inherited from owner-scoped services; source authentication, recalculation and currency conversion are not added.

## Workspace and delivery

Unrelated untracked files were preserved and excluded from staging/PR. Delivery targets `main` from `feature/ai-17b-financial-review-api`; no merge is performed.

Pre-staging `git status --short` (including this report):

```text
 M backend/app/main.py
 M frontend/src/generated/api.ts
?? ai17a-new-files.txt
?? ai17a-review-diff.txt
?? backend/app/api/financial_review.py
?? backend/app/schemas/financial_review.py
?? backend/app/services/finance/financial_review.py
?? backend/test_financial_review.py
?? docs/ai-17b-financial-review.md
?? "frontend/Redesigned Frontend/"
?? test_transactions.csv
?? test_transactions_3_months.csv
```
