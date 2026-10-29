# Initial frontend product map and implementation audit

This report records the first frontend implementation. The current [refinement audit](frontend-refinement.md) supersedes its architecture, API integration and validation notes.

## Discovery and architecture

The repository had no frontend, package.json, router, UI components, state store, chart library or JavaScript checks. The existing root SKILL.md supplied frontend-design guidance. FastAPI routes and Pydantic schemas were inspected before choosing the UI contracts, along with the AI-12 evaluation documentation, AI-13 Financial Intelligence Engine documentation and coach APIs.

The frontend is isolated under `frontend/`: React 19, strict TypeScript, Vite, React Router, Lucide icons, CSS semantic tokens, native SVG charts, Vitest, Testing Library and ESLint. A single typed API client owns headers, JSON/form handling, errors, timeouts and single-flight token refresh. Page-level resource hooks discard stale responses. Financial calculations remain in the backend; frontend arithmetic is limited to display geometry and goal-progress percentages. Decimal API fields remain strings in domain models. No mock transport or demo dataset is connected to the application.

## Product UX map

| Area | Primary job and hierarchy |
| --- | --- |
| Overview `/` | Understand selected-month recorded net activity, then upcoming commitments, purchase assessment entry point, meaningful observations, savings opportunities and recent records. No KPI wall or ornamental historical chart. |
| Cashflow `/cashflow` | Review scheduled obligations including overdue records; create income/expense schedules; mark paid/cancelled; supply a checked balance for a 3/6/12-month scenario; compare qualified forecasts with the no-future-income path; inspect exact monthly values; assess a purchase and reserve a safety buffer. |
| Transactions `/transactions` | Search, filter by dates/category/signed income/expense, paginate, import CSV, add a signed record, inspect details and correct categorization. Filters live in URL search parameters. |
| Plans `/plans` | Create a dated savings target, report known savings or keep them unknown, review backend required contributions and qualified capacity. Goal lists are paginated. |
| Insights `/insights` | Review sparse grounded observations, exact periods, next actions and inspectable evidence; hide/restore for this visit; inspect estimated savings and uncertainty. |
| Ask `/ask` | Choose a financial question, supply optional purchase context, inspect deterministic answers, calculations, sources, periods, coverage and limitations. No conversational persona or fabricated certainty. |
| Settings `/settings` | Review identity, BDT, Dhaka calendar, session behavior, signed-amount conventions and data limitations; sign out. |
| Authentication | Register/sign in, preserve deep links, explain expiry and failure; onboarding begins with an actionable empty dashboard and transaction entry. No made-up user data. |

Loading geometry follows lists/financial rows. Each major read has an independent error and retry boundary, allowing partially available dashboards. Empty views explain the next action. Unknown values say Not available. Insufficient history does not turn into zero. Mutation forms retain input after failure, prevent duplicate submissions and confirm successful changes. Mobile layout promotes the financial position and obligations, stacks columns, uses collapsible navigation and turns transaction rows into a readable two-column ledger. Larger cashflow tables remain horizontally scrollable to preserve exact values.

## Visual system and critique

The design borrows from the clarity of a personal ledger rather than a marketing dashboard. Palette: slate text #253b43, white #ffffff, cool canvas #f5f7f8, forest #164b40, warning ochre #80501a and forecast slate-blue #526a91. Semantic custom properties define surfaces, text, borders, income, expenses, warnings, errors, estimates, focus, spacing, radii and type. IBM Plex Sans handles English and numbers; Noto Sans Bengali supports Bangla and mixed merchant content. Numerals deliberately remain Latin. Bangla brand presentation is preserved in Unicode escapes to survive Windows shell encodings.

The strongest visual emphasis belongs to recorded position, explicitly qualified as net activity rather than balance. Upcoming plans follow before historical records. Quiet dividers replace repetitive cards; limited surface panels group balance, purchase planning and editable goals. Forecasts use dashed lines and text labels; scheduled plans are explicitly named. Chart data is available in an adjacent table. No decorative illustrations, gradients, testimonials, AI labels or animated financial counters are used.

## Reusable components

`Amount`, `Field`, `PageHeading`, `Section`, `ResourceView`, `Loading`, `Empty`, `ErrorNotice`, `Notes`, `Evidence`, `Pager`, `TransactionTable`, `CashflowChart`, a shared application shell and per-goal detail composition. Page components own orchestration; API calls do not occur inside low-level display components.

## Consumed contracts

| Backend path | Frontend use |
| --- | --- |
| POST `/register`, `/login`; POST `/refresh`; GET `/me` | JSON registration/login, form-encoded refresh, identity, expiry handling. Registration may omit a refresh token. |
| GET `/insights/summary` | Explicit month-to-date or completed-month signed totals; transaction_count gates unknown history. |
| GET/POST `/transactions` | Paginated search, date/category/signed-amount filters, manual creation. |
| PATCH `/transactions/{id}/category` | Category corrections through the backend preference pipeline. |
| POST `/upload-csv` | Multipart CSV file ingestion. |
| GET/POST `/finance/scheduled-cashflow`; PATCH `/{id}` | Paginated plans, creation and status changes; no actual money movement. |
| GET/POST `/finance/goals`; PATCH `/{id}`; GET `/{id}/plan` | Persistent goals, nullable reported savings and deterministic plans. |
| GET `/insights/proactive` | Qualified observations and evidence. |
| GET `/finance/savings/recommendations` | Coverage, estimated potential savings, assumptions and limitations. |
| POST `/finance/coach/cashflow` | Caller-supplied balance, monthly obligation/forecast scenarios. |
| POST `/finance/coach/spending-decision` | Purchase assessment with scheduled expense reserve and safety buffer. |
| POST `/chat/ask` | Answer, intent, calculations, sources, dates, coverage, status and uncertainty. |

The AI-13 engine is internal Python, not a public `/intelligence` HTTP endpoint. This UI consumes its existing coach/chat presentation adapters and existing analytics routes. No new endpoints or duplicate forecast calculations were invented. An unused typed monthly-history adapter is available for future historical detail without placing an ornamental chart on the overview.

## Missing capabilities and deliberate boundaries

- No reconciled current balance or bank/MFS connection: balances must be supplied explicitly for scenarios. Dashboard net activity is never a balance.
- No persisted user-editable contribution schedule endpoint: required goal contributions come from the backend. Users can update reported savings, target/name/date edits and contribution-plan persistence are future UI work; no pretend save control exists.
- No profile editing, password reset, session revocation, UI locale or preference-write endpoint. Settings communicates current capabilities.
- No insight dismissal persistence endpoint: hide/restore is explicitly scoped to this visit.
- No broad Bangla question parsing in grounded chat: typography/content are Bangla-ready; Ask clearly states English-question support.
- Scheduled status changes do not create actual transactions. Users must record actual payments separately.
- No direct AI-13 snapshot endpoint. A future dashboard adapter should expose snapshot and first-class coverage together rather than require parallel requests.
- Goal status changes/deletion, scheduled title/amount editing/deletion, account-specific forecasts and dedicated historical analytics navigation are not exposed by this first frontend.

## Accessibility and responsive design

Semantic landmarks/headings, a skip link, active route indication, explicit form labels/hints, visible focus rings, native keyboard controls, Escape dismissal for mobile navigation, hidden collapsed navigation, announcement of errors/loading/results, reduced-motion support, signed amounts plus income/expense text, chart title/legend and an exact-value table. Typography supports Bangla fallback and long strings. Major breakpoints are 1200, 1000 and 760 pixels. Accessibility verification is scoped to tooling results; browser, screen-reader, visual contrast and touch-target review remain necessary before production.

## Verification

Verified on 25 October 2026 with Node 24.20.0 and headless Google Chrome:

| Check | Result |
| --- | --- |
| TypeScript `npm run typecheck` | Passed |
| ESLint `npm run lint` | Passed, zero warnings/errors |
| Vitest `npm test` | 23 passed across four files, including four axe structural checks |
| Production `npm run build` | Passed; JS 315.08 kB / 98.45 kB gzip, CSS 23.89 kB / 5.64 kB gzip |
| Playwright `npm run test:browser` | Six passed: three desktop and three mobile (390 x 844) scenarios |
| Browser axe WCAG A/AA checks | Passed for overview, transaction detail, cashflow and Ask states, including color contrast |
| Page-width overflow assertions | Passed in tested desktop/mobile states |
| `npm audit --omit=optional` | Zero reported vulnerabilities |
| Screenshot review | Desktop/mobile overview and mobile cashflow reviewed; mobile hierarchy and scroll-region keyboard access corrected |

[Desktop overview](frontend-preview/overview-desktop.png), [mobile overview](frontend-preview/overview-mobile.png), and [mobile cashflow](frontend-preview/cashflow-mobile.png) are QA screenshots using explicitly synthetic test fixtures. Those fixtures exist only in tests and are never bundled into the application.

Dependency installation on the Google Drive streamed workspace failed with EBADF/UNKNOWN file-write errors. Checks ran against an identical temporary local copy at `%TEMP%/porerhishab-frontend-qa-clean-20261025`, with a fresh npm cache. The final formatted source and lockfile were copied back to this repository and content hashes checked. Prefer a local filesystem checkout for npm development.

Backend source and contracts were not changed, so the database-backed backend suite was not rerun. No production data was created. Browser tests intercept the API with test-only fixtures; live authentication/CRUD against a running development database and full assistive-technology acceptance testing remain release checks. This is not a production-readiness certification.

## Next product improvements

1. Expose an authenticated AI-13 snapshot/coverage endpoint and reconcile actual balances.
2. Persist contribution plans and connect goal changes to a clearly modeled allocation flow.
3. Add backend-backed preferences, password recovery and persistent insight acknowledgements.
4. Add full Bangla UI translation and supported Bangla financial-question intents.
5. Complete real-browser responsive, keyboard and screen-reader acceptance review against a development API before release.
