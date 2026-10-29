# PorerHishab frontend

A React + TypeScript + Vite application connected to the existing FastAPI backend. The Khata redesign brings cream paper surfaces, teal ink, ledger layouts and a persistent English/Bengali language switcher to every page. Existing financial workflows and API contracts are preserved. See [the redesign audit and screenshots](../docs/frontend-khata-redesign.md) for the workflow inventory, localization guide and validation results.

## Run

Requires Node 22.12+ (Node 24 used for verification). Start the API from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend
```

`--app-dir backend` tells Uvicorn where the `app` package lives, including in the Windows reload subprocess. This command works without an editable package installation. Run it from the repository root, not from `frontend/`.

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Register or sign in with a backend account. The application contains no seeded user, demo mode or fabricated financial records. Authentication tokens remain in memory; reloading requires signing in again. Deep links are preserved through login.

The Vite development proxy forwards `/api` to `http://127.0.0.1:8000`. To use another backend, copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL` to a trusted API URL (never a secret). The API must permit that origin. Restart Vite after changing configuration.

Google Drive streamed volumes can fail when npm writes many small files. If installation reports EBADF/UNKNOWN write errors, use a normal local checkout (for example under C:\dev) and run `npm ci` there. Do not copy an incomplete node_modules tree.

## Verify

```powershell
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:browser
```

The test suite covers native dialog focus, goal editing, monthly chart inspection, sign-out/refresh races, unknown versus zero, Dhaka date boundaries, authenticated requests, refresh concurrency, expiry, validation, CSV content types, empty dashboards, grounded Ask responses and stale request protection. Automated accessibility checks cover representative page states through axe-core; they do not certify WCAG compliance or replace keyboard and screen-reader review.

## Deploy

`npm run build` creates `dist`. Serve it behind HTTPS with SPA fallback to `index.html`. Route `/api/*` to the backend and strip the `/api` prefix, or set a trusted absolute `VITE_API_BASE_URL` at build time. `npm run preview` only serves static build output; it does not provide the development API proxy. The frontend now consumes the additive read-only `/finance/intelligence` adapter. Deploy the matching backend revision alongside it. Existing calculations, routes, database migrations and credentials are preserved.

IBM Plex Sans and Hind Siliguri are loaded through Google Fonts; installed/system sans-serif fonts provide fallbacks. Self-host fonts for production deployments that prohibit external font requests.

On Windows with Google Chrome already installed, the browser suite can use it without downloading Chromium:

```powershell
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:browser
```

Browser tests use isolated synthetic API fixtures; they never sign in to or write to a real account. Desktop/mobile QA screenshots and exact results are linked from the implementation audit. They do not establish live API integration or full accessibility compliance.

## API contract synchronization

Response types in `src/generated/api.ts` are generated from the actual FastAPI OpenAPI schema. `src/domain.ts` selects the fields each view needs from those generated types. Monetary response fields remain Decimal strings. Legacy authentication endpoints lack response models, so `User` and `Tokens` remain explicit adapters verified by real-route backend tests.

Run from the repository root after backend schema changes:

```powershell
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check
```

Schema generation needs backend dependencies but makes no database query or external request. Do not format generated files by hand. CI checks for drift, runs the AI-13 route/engine tests, then runs frontend typecheck, lint, unit, build and desktop/mobile browser checks.

See [the refinement audit](../docs/frontend-refinement.md) for the current changes, validation scope and remaining product limitations.

## Khata design and language support

Use EN / Bangla in the header, authentication screens, Settings or an open dialog. The language preference persists in browser storage; authentication tokens remain in memory. Bengali localizes interface text and financial presentation. User records and backend explanations stay in their original language. Ask starter buttons retain supported English questions.

Add frontend translations to src/lib/translations.ts and use the typed t() helper; subscribe through useLanguage() in rendering components. Never translate API prose or user-entered values through the interface dictionary. Use the locale formatting helpers for display; keep API decimal/date values canonical. All styles now live in src/styles.css.

The nested Redesigned Frontend folder remains the design reference and is excluded from application linting. See [the Khata audit](../docs/frontend-khata-redesign.md) for the complete verification matrix and before/after screenshots.
