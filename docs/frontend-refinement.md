# Frontend refinement and AI-13 integration

This change builds on the existing React/Vite frontend on `feature/ai-13-financial-intelligence`. It preserves routing, memory-only authentication, the central API client, deterministic backend arithmetic, and the distinction between recorded activity and account balance.

## Product and design changes

- Overview is now a current-month decision surface backed directly by AI-13's BDT-scoped snapshot. It shows observed income/expenses/net activity, explicit historical coverage, next-30-day expense reserves, uncertain expected income, and routes into purchase assessment, observations and savings. History remains available in Insights; transaction date filters remain available for arbitrary periods.
- Coverage is a first-class component: named status, exact period, observed/missing months, and limitations. Recorded months are a coverage signal, not proof of complete imports.
- Semantic tokens, typography hierarchy, spacing, denser transaction rows, quieter surfaces, contextual empty/loading states and form controls were refined. Bangla and mixed-language content retains the existing font fallback. Latin numerals remain intentional.
- Transaction creation uses a native modal; detail and category correction use a drawer. Inline server errors remain visible inside the modal. Forms retain values on failure.
- Goal creation and editing support name, target, target date, nullable reported savings and backend-validated terminal statuses. Weekly/monthly contribution toggles display the backend's values; no forecast arithmetic is duplicated. Unchanged overdue target dates are omitted from PATCH requests.
- Scheduled items can be created and edited through existing CRUD contracts. Changing obligations clears previously calculated purchase/forecast results so stale advice is not left on screen.
- Cashflow charts have meaningful axes, exact keyboard-accessible month selectors and a live value readout. Missing forecasts are explicitly unavailable, with no drawn line connecting gaps and no invented uncertainty band. The exact monthly table remains available.
- Insights retain observations and saving opportunities first, followed by observed monthly income/expense comparison, category movement, recurring patterns and the qualified historical baseline.
- Ask calculations, coverage and source objects are presented as labeled details rather than raw JSON. Settings and authentication receive the same visual refinements; token storage behavior remains unchanged.
- Mobile has a native modal navigation drawer, inert background, focus containment/return, Escape dismissal and a persistent four-destination quick navigation bar. Desktop retains the sidebar. Dialogs focus the first relevant field and do not fade through low-contrast intermediate states.

## Architecture and contracts

The only new public backend route is authenticated, read-only `GET /finance/intelligence`. It delegates to `build_financial_intelligence`, `category_spending_facts` and the existing period helpers. It returns an explicit Pydantic response model containing the engine snapshot, coverage, cashflow separation, signals, category comparisons and complete-month observations. It performs no money arithmetic and creates no records. Internal user IDs are not serialized. The engine's diagnostic baseline is omitted (null) when its own coverage gate is not adequate; the original engine and existing routes are unchanged.

`frontend/src/generated/api.ts` is generated from this checkout's actual OpenAPI schema by `scripts/generate_frontend_contracts.py`. Domain response models are field projections of generated schemas, preserving decimal strings, nullable values and literal statuses. `ApiOperations` includes request/query/response contracts for the exposed routes. Legacy auth routes do not declare response models, so User and Tokens remain explicit adapters covered by real-route tests. Runtime API failures continue to surface as errors rather than fake records.

The existing resource hook remains adequate: pages load fresh on navigation, mutations explicitly refresh their resource, and stale/unmounted requests cannot overwrite state. A new session-generation guard prevents a late refresh from restoring a signed-out session. No query library, localStorage tokens or replacement framework was introduced.

New reusable components: `Dialog`, `FinancialContext`, `IntelligencePanels`, `useMediaQuery`, and expanded `CashflowChart`/evidence rendering. `polish.css` is a scoped refinement layer over the existing styling, using the same semantic tokens. Generated code is excluded from hand-formatting.

## Repeatable verification

Run the backend from the root with `--app-dir backend`; the frontend's development `/api` proxy remains unchanged. Deploy the matching backend revision before serving this UI, because the overview and intelligence panels require the new adapter.

```powershell
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check
.\.venv\Scripts\python.exe -m pytest backend -q --tb=short
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:browser
```

CI in `.github/workflows/frontend.yml` checks contract drift, the isolated API/AI-13 suite, typecheck/lint/unit/build, and Chromium desktop/mobile acceptance tests. It uses an in-memory database, no production credentials and no external AI provider. Local browser verification used the installed Google Chrome and the existing local verification copy because Google Drive streamed volumes previously failed npm dependency writes.

Verified on 25 October 2026:

| Check | Result |
| --- | --- |
| Full backend suite | 391 passed, 1 skipped; four existing Alembic configuration deprecation warnings |
| AI-13 adapter/engine regression subset | Passed; new route, auth, refresh, CSV, filters, category correction, goals/plans, scheduling, recommendations, proactive insights, cashflow, purchase checks and grounded Ask exercised through actual FastAPI routes |
| TypeScript | Passed |
| ESLint | Passed, zero application warnings/errors |
| Frontend unit/component tests | 29 passed |
| Desktop/mobile browser scenarios | 10 passed; populated and empty records, dialogs, goal/schedule editing, mobile focus containment and navigation |
| Browser axe checks | Passed in tested overview, transaction drawer, cashflow, Ask, populated Insights and goal editor states, including contrast |
| Production build | Passed; JS 331.27 kB / 102.27 kB gzip, CSS 48.02 kB / 10.01 kB gzip |
| OpenAPI drift check | Passed |
| Database/schema changes | No migrations, data transformations or storage-identity changes |

Backend integration tests use actual authentication, SQL queries, deterministic calculations, and persistence against isolated SQLite. The legacy CSV service's session factory is pointed to that same test-only database. Canary records verify user isolation. Browser tests use explicit test-only contract fixtures; those fixtures are not imported by production entry points or written to real user accounts. Generated rich/empty AI-13 fixtures were validated by the actual response model.

QA screenshots show synthetic test records, not customer data: [desktop overview](frontend-preview/refined/overview-desktop.png), [mobile overview](frontend-preview/refined/overview-mobile.png), [desktop insights](frontend-preview/refined/insights-desktop.png), [mobile insights](frontend-preview/refined/insights-mobile.png), [goal editor](frontend-preview/refined/goal-editor.png) and [transaction drawer](frontend-preview/refined/transaction-drawer.png).

## Remaining limitations

- There is no reconciled balance, bank/MFS sync, contribution-allocation endpoint, persisted custom contribution schedule, profile/preference write endpoint, password recovery or persistent insight acknowledgements. The UI does not invent these capabilities.
- Goal and scheduled-item deletion are still not exposed in this frontend. Terminal status transitions are governed by the existing backend.
- Bangla typography/content is supported; broad Bangla question parsing and full UI translation remain outside the current backend contract.
- No statistical forecast interval exists in the backend. Chart styling cannot imply a confidence range the engine does not compute.
- Current-month overview now uses the AI-13 BDT scope; historical transactions/analytics endpoints retain their existing backend scope. Their signed-amount and transfer/refund limitations still apply.
- Automated checks and screenshot review do not certify production readiness or replace screen-reader/device review, deployment security review or real-bank data reconciliation.

Next improvements should prioritize real balance/coverage reconciliation, persisted contribution planning, explicit transaction-to-plan reconciliation and full Bangla intent support over additional decorative charts.
