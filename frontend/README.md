# PorerHishab frontend

A React + TypeScript + Vite application connected to the existing FastAPI backend. See [the implementation audit](../docs/frontend-implementation.md) for UX decisions, API contracts and limitations.

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

The test suite covers unknown versus zero, Dhaka date boundaries, authenticated requests, refresh concurrency, expiry, validation, CSV content types, empty dashboards, grounded Ask responses and stale request protection. Automated accessibility checks cover representative page states through axe-core; they do not certify WCAG compliance or replace keyboard and screen-reader review.

## Deploy

`npm run build` creates `dist`. Serve it behind HTTPS with SPA fallback to `index.html`. Route `/api/*` to the backend and strip the `/api` prefix, or set a trusted absolute `VITE_API_BASE_URL` at build time. `npm run preview` only serves static build output; it does not provide the development API proxy. No backend code, database migrations or credentials are changed by this frontend.

IBM Plex Sans and Noto Sans Bengali are loaded through Google Fonts; installed/system sans-serif fonts provide fallbacks. Self-host fonts for production deployments that prohibit external font requests.

On Windows with Google Chrome already installed, the browser suite can use it without downloading Chromium:

```powershell
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:browser
```

Browser tests use isolated synthetic API fixtures; they never sign in to or write to a real account. Desktop/mobile QA screenshots and exact results are linked from the implementation audit. They do not establish live API integration or full accessibility compliance.
