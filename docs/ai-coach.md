# Grounded AI coach backend

This milestone reuses existing analytics, categorization, cashflow arithmetic and purchase
assessment. It adds date-aware SQL chat, persistent self-reported savings goals, deterministic
savings recommendations, proactive observations, and opt-in obligation scenarios. Existing
forecast and spending-decision paths retain their original meanings. AI-11B scheduled CRUD
is included in this branch.

## Run locally without an AI provider

From the repository root with the virtual environment active:

```powershell
python -m pip install -r backend/requirements.txt
python -m pip install -e .
alembic -c alembic.ini upgrade head
uvicorn app.main:app --reload
```

Set `AI_EXTERNAL_ENABLED=false` (the default). A key, vector database, paid account, or
payment card is unnecessary for all coach APIs. Authentication and PostgreSQL are required.
Use the bearer token from `/login` or `/register` in `Authorization: Bearer <token>`.
The schema migration `b7a8c9d0e1f2` adds only `savings_goals` after `ec735533a563`.
It is additive and does not rewrite transactions or historical migrations.

Optional provider packages are in `backend/requirements-ai.txt`; optional legacy semantic
retrieval packages are in `backend/requirements-rag.txt`. The basic app does not import them
at startup. The full historical test suite imports some optional RAG modules, so install
those packages when running every historical test. Provider-enabled code uses the existing
OpenAI-compatible conventions; no new AI infrastructure is introduced.

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| POST | `/chat/ask` | Exact SQL answers with calculation, date range, coverage, assumptions, limitations and status |
| POST | `/transactions/categorize` | Categorize up to 100 unique owned transaction IDs; preserve confirmed/non-placeholder categories |
| GET | `/finance/savings/recommendations` | Up to five ranked category-review opportunities with monthly and annual estimates |
| POST, GET | `/finance/goals` | Create or paginate user-reported goals |
| GET, PATCH, DELETE | `/finance/goals/{id}` | Owned goal operations |
| GET | `/finance/goals/{id}/plan` | Weekly/monthly contribution and qualified affordability estimate |
| GET | `/insights/proactive` | Up to 30 active observations with evidence, keys and expiry |
| POST | `/finance/coach/cashflow` | Historical and known-obligation scenarios, separate from the original forecast |
| POST | `/finance/coach/spending-decision` | Purchase assessment reserving upcoming scheduled expenses |
| POST, GET | `/finance/scheduled-cashflow` | Create or filter/paginate planned records |
| GET, PATCH, DELETE | `/finance/scheduled-cashflow/{id}` | Owned planned-record operations |

The existing `/forecast/cashflow`, `/finance/spending-decision`, `/planner/savings`,
`/planner/savings/coach`, `/insights/ai`, transaction corrections and analytic APIs remain.
The existing AI insight and savings-action schemas still apply and now have offline fallbacks.
The legacy stateless savings plan adds coverage limitations and an insufficient_data status;
historical estimates are null when no usable actual history exists, rather than claiming zero.
Its historical current_saved default remains zero for compatibility; persistent goals instead
keep unreported savings unknown.

## Questions and exact periods

```json
{"question":"How much did I spend last month?"}
```

```json
{"question":"What were my largest expense categories?","start_date":"2026-09-01","end_date":"2026-09-30","k":5}
```

```json
{"question":"Compare my spending this month with last month"}
```

```json
{"question":"Which merchants contributed most to my spending last month?"}
```

```json
{"question":"What bills are coming up?"}
```

```json
{"question":"How much money could I reasonably save?"}
```

```json
{"question":"Could I afford a purchase?","purchase_amount":"2000.00","starting_balance":"10000.00","safety_buffer":"3000.00"}
```

```json
{"question":"What assumptions drive my projected cashflow?","starting_balance":"10000.00"}
```

Supported historical periods are this month, last month, last 7/30 days, two ISO dates,
or explicit `start_date` and `end_date`. With no period, historical aggregates use the current
month to date. Dates use Asia/Dhaka. Month comparisons use matching elapsed days, capped at
the previous month's end; exact ranges are included. Other ambiguous dates return 422.
Historical ranges are limited to ten years and cannot extend into the future. Upcoming bills
default to the next 30 days; supply explicit dates for another future range of up to one year.
Use the optional `category` field for a custom category; inferred aliases cover common categories.
Unknown merchant-specific filters are rejected rather than silently returning all spending.
Unsupported questions return `status: unsupported`. Missing records produce
`status: insufficient_data` and null totals, rather than a claim of zero spending.

The existing `answer`, `intent` and `sources` fields remain; structured metadata is additive.
Supported answers use deterministic templates, not model-written arithmetic. Historical SQL
only loads aggregates, and ranked lists are limited by `k`. No vector database is queried by
`/chat/ask`. English is supported for questions; broad Bangla question parsing is not yet
implemented. Bangla and mixed-language transaction categorization is supported.

## Categorization

The existing column names and taxonomy are preserved: Food (dining), Groceries, Transport,
Shopping, Bills (utilities), Business, Entertainment, Healthcare, Education, Housing, Travel,
Salary (income), Transfer, Investment, Subscription, Other, Uncategorized. Legacy manual-create
labels Coffee, Rent, Income, Health, Utilities and Fitness are also retained for compatibility.
User merchant preferences precede rules; valid optional provider output follows rules.
Provider errors or invalid categories fall back to Uncategorized with a safe explanation.
Generic transfers are not automatically classified as expenses/income by the coach: it follows
the existing signed-amount convention, so imported internal transfers can distort analytics.

```json
{"transaction_ids":[123,124]}
```

All IDs are checked for ownership before classification or writes. Missing and foreign IDs
both return 404 and leave the batch unchanged. Duplicate IDs, unexpected fields and batches
larger than 100 return 422. Each batch allows at most five ambiguous provider attempts.
Rule matches do not consume an external request. An existing manual/custom category is
preserved, including values set through `/transactions/{id}/category`. Repeated successful
classification preserves the result; ambiguous Uncategorized records can be retried.
Transaction creation shares preferences and validated fallbacks and verifies account ownership.
It retains the legacy create-rule labels (for example Netflix remains Entertainment); rules for
previously unmatched descriptions use the broader categorization service.

Extend the taxonomy and deterministic rules using JSON environment values:

```dotenv
CATEGORY_EXTRA_LABELS=["Childcare"]
CATEGORY_KEYWORD_RULES={"daycare":"Childcare","local cafe":"Food"}
```

Configured rules precede built-in rules but never override user preferences. Invalid category
mappings are ignored. Bangla keyword boundaries account for combining marks. No sensitive
personal attributes are inferred.

## Recommendations and goals

Recommendations need observations in each of the last three completed calendar months.
A record in each month is a coverage signal, not proof that the imports are complete.
Only selected discretionary categories are considered. If the latest completed month's
spending exceeds the preceding month by more than 10%, the optional saving estimate is the
smaller of 10% of latest spending and the increase. Annual impact is monthly impact times 12.
Each category has one stable period key; opportunities are ranked by estimated monthly impact.
No essential-category reductions or repeated overlapping savings are assumed. These are
potential reductions, not guaranteed savings or a statement that cuts are feasible.

```json
{"name":"Emergency buffer","description":"Self-reported cash reserve","target_amount":"60000.00","current_saved":"5000.00","target_date":"2027-06-30"}
```

`current_saved` is a nullable, explicitly self-reported amount. Omission/null means unknown,
not zero. There is no automatic transaction or account allocation. Contributions are calculated
only when this value is known. Active goals may become completed or cancelled; terminal goals
cannot reopen. Completion requires reported savings at least equal to the target. Descriptive
edits remain allowed if the completed-state invariant remains valid. Dates cannot be created or
changed into the past; an existing goal may become overdue naturally.

Remaining weeks round up from days until the target. Calendar months include the target month.
Required contributions round up to cents. With adequate observed history, historical monthly
surplus, current-month scheduled obligations and other active goal contributions inform a
qualified affordability estimate. If another active goal has unknown savings, shared affordability
is unknown. Account balances and scheduled income are never assigned to savings. A historical
surplus cannot guarantee future contributions, especially for a deadline within the current month.

## Scenarios and proactive insights

```json
{"starting_balance":"10000.00","months_ahead":3}
```

```json
{"purchase_amount":"2000.00","starting_balance":"10000.00","safety_buffer":"3000.00","horizon_days":30}
```

Cashflow scenarios begin today, prorating remaining current-month days and then using full
months. Each month reserves the larger of historical estimated expenses and scheduled expenses,
rather than adding potentially overlapping bills twice. This maximum is an explicit scenario
assumption; truly additional obligations may make the scenario too optimistic. The response
separately reports scheduled expenses, historical estimates, uncertain scheduled income, projected
balance, and a balance scenario without future income. With inadequate history, projected balance
is null while the known-obligation scenario remains available.

Purchase checks reserve all scheduled expenses in the inclusive horizon and do not count future
income. A purchase is assumed additional to the schedules. Overdue records are excluded from
future scenarios and must be reviewed separately. Paid/cancelled items are excluded and never
create actual transactions. Positive signed transactions are treated as income; incomplete imports,
refunds and transfers can distort historical estimates.

Proactive insights include upcoming plans, category-review opportunities, goal progress,
estimated monthly deficits, and unusual spending. Unusual spending requires all three historical
months and current spending above 150% of the largest recorded full month. Deficit observations
are explicitly estimates, never claims about an actual bank balance. Stable evidence keys deduplicate
results. Upcoming observations expire after the due date; monthly observations expire at the next
month boundary and are recomputed. There is no notification delivery or dismissal persistence in
this milestone. Clients can use the stable keys for local presentation/dismissal.

## Optional provider and privacy

```dotenv
AI_EXTERNAL_ENABLED=false
OPENAI_KEY=
OPENAI_BASE_URL=
OPENAI_CHAT_MODEL=gpt-4o-mini
AI_TIMEOUT_SECONDS=10
AI_MAX_OUTPUT_TOKENS=800
```

To enable optional external classification/wording, install `requirements-ai.txt`, configure a
server-side key and compatible base URL if needed, and set `AI_EXTERNAL_ENABLED=true`.
Timeout is capped at 30 seconds, output at 2000 tokens, with no automatic retries. Structured
helper inputs are bounded and Pydantic validated. Credentials never belong in client requests.
Do not enable provider request tracing that records sensitive payloads.

Only ambiguous classification needs merchant/description snippets (bounded per field); enabling it
permits sending those snippets externally. Existing savings-action wording sends only the calculated
plan, and insight presentation lets the provider select only precomputed observation indices. It cannot
author new financial claims or amounts. Provider exception messages are
neither logged nor returned. Ordinary financial APIs, grounded chat, recommendations, goals and
proactive insights remain deterministic without a key or when the provider fails. The optional
legacy semantic retrieval path uses embeddings and a local vector store, is isolated from SQL
calculations, and checks metadata ownership at retrieval and consumption boundaries. It is not used
by the chat HTTP endpoint. No new feature sends raw transaction histories to a provider.

## Validation

```powershell
python -m compileall -q backend
python -m pytest backend/test_ai_coach.py backend/test_coach_migration.py backend/test_scheduled_cashflow_api.py -q
python -m pytest backend -q
alembic -c alembic.ini check
git diff --check
```

Tests use randomized users and clean up their records. Migration tests create and remove only a
uniquely named temporary PostgreSQL schema, exercise upgrade/downgrade/re-upgrade, and verify
cascade deletion and preservation of existing user rows. The normal suite does not call a real
LLM or embedding provider. The old live embedding smoke test is skipped unless
`RUN_LIVE_AI_TESTS=1` is explicitly set. AI tests mock timeouts, malformed output and provider
configuration; they need no paid account. These checks do not certify production security or
bank-data completeness. Educational recommendations provide no investment, tax or credit guarantees.
