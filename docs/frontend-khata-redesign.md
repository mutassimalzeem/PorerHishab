# Khata frontend redesign

Implemented locally on 29 October 2026. The existing React application now uses the Khata reference's paper-and-teal visual language and an English/Bengali interface. The concept showcase remains a separate, unchanged reference.

## Workflow inventory and regression checklist

| Route | Preserved behavior | Data and states |
| --- | --- | --- |
| /login and protected deep links | Register, sign in, recover from expiry, return to requested route | Existing /register, /login, /me and refresh handling; busy, validation and failure states |
| / | Recorded activity, coverage, upcoming commitments, recent transactions, insight and savings links | /finance/intelligence, /transactions, /insights/proactive, /finance/savings/recommendations; empty, partial history, unknown and failed requests |
| /transactions | Filtering, pagination, manual entry, CSV import, details drawer, category correction | Existing transaction, category and upload endpoints; validation, pending requests, success and failure notices |
| /cashflow | Schedule creation/editing, paid/cancelled status, filtering, forecast, purchase assessment, accessible chart and data table | Existing scheduled-cashflow and coach endpoints; supplied balances, unavailable projections, warnings and assumptions |
| /plans | Goal creation/editing, reported savings, terminal statuses, pagination, weekly/monthly contribution details | Existing goal and goal-plan endpoints; unknown savings, insufficient history, validation and failed requests |
| /insights | Observations, visit-only hiding, category comparisons, recurring patterns, recommendations and evidence | Existing intelligence, proactive insights and recommendation endpoints; empty and insufficient history states |
| /ask | Starter prompts, custom questions, optional financial context, answers, evidence and limitations | Existing /chat/ask; busy, unsupported/insufficient results and errors |
| /settings | Account details, language selection, session/privacy explanation, sign out | Existing account data; no new profile or password endpoints |

Desktop navigation, mobile drawer, quick navigation, skip link, route focus, native dialogs, focus restoration, session invalidation and stale-request protection remain in place. No backend, generated contract, database or deployment changes were needed.

## Design implementation

- One imported stylesheet, src/styles.css, combines the existing responsive workflow layouts with Khata tokens and removes superseded declarations. The separate polish.css is removed.
- Palette: paper #FAF6EE, desk #E8E6DF, teal ink #165E50, body #263E38, ledger rule #DEDBCD and pale green #E7EEE3.
- IBM Plex Sans is paired with Hind Siliguri. Fonts use Google Fonts with system fallbacks. Self-host them if deployment policy requires it.
- The workspace resembles a ledger page with a teal binding edge; activity uses subtle ruled paper, while transaction and schedule rows retain a ledger rhythm.
- Native focus outlines, readable contrast, reduced-motion support, wrapping Bengali labels and responsive tables remain available.
- The nested Redesigned Frontend project is excluded from the main lint scope. Its dependencies and Git metadata are not integrated.

## Localization maintenance

src/lib/translations.ts holds the Bengali dictionary; its English source keys define TranslationKey. Add both the English key and Bengali translation, then call t(key) for frontend copy. Components subscribe through useLanguage. Only pass frontend-owned navigation/status labels to uiLabel; never pass user records or API-generated prose.

LanguageProvider updates the document language and native form-validation messages. The language switcher appears on authentication, the app header, Settings and inside dialogs. The non-sensitive porerhishab.language preference is the only new persisted state. English is the default; unavailable storage falls back safely.

Money, dates, chart labels, counts and percentages use the chosen locale. Bengali presentation uses Bengali numerals; editable numeric/date controls and API payloads retain canonical values. Financial dates stay in Asia/Dhaka. Browser-native date-picker chrome follows the browser/OS language.

Backend explanations, chat answers, assumptions, limitations and user-entered names/categories are preserved verbatim. Frontend labels for known statuses and evidence fields are translated. Unknown backend errors receive a translated recovery message in Bengali. Unknown future evidence keys retain their original labels rather than inventing a translation.

Ask starter buttons display translated labels but insert the supported English question. The interface explicitly explains that the current backend supports English questions.

Language changes do not remount pages or dialogs, clear draft values, modify financial payloads, or invalidate contribution-plan cache keys.

## Verification

The streamed Google Drive workspace failed dependency extraction with EBADF/UNKNOWN writes. Verification therefore ran against the same frontend source in C:/Users/mutas/AppData/Local/Temp/porer-khata-frontend with a clean npm ci. No dependency or framework migration was made.

Baseline before changes:

- Typecheck, lint and production build passed.
- 29 unit tests passed.
- 10 desktop/mobile browser tests passed.
- Frontend contracts matched the FastAPI OpenAPI schema.

Final:

- Typecheck, lint and production build passed.
- 35 unit tests passed across six files.
- 19 browser tests passed; five duplicate viewport-matrix entries were intentionally skipped in the mobile project.
- Every authenticated route was checked in both languages at 360, 390, 768, 1024 and 1440 pixels, including automated accessibility and document-overflow assertions.
- Separate desktop/mobile flows cover authentication persistence, native validation, switching inside an open schedule editor and canonical decimal/date payloads.
- Unit coverage verifies unavailable storage, input retention, untranslated backend/user content, locale formatting, an existing error switching languages, and an open goal editor retaining its values without refetching its plan.
- Existing financial, authentication, chart inspection, category correction, goal editing and dialog keyboard regression tests remain passing.

The browser suite uses synthetic API fixtures and installed Chrome. It does not certify live-backend integration or replace a manual screen-reader audit. English and Bengali overview screenshots and an open Bengali editor were visually reviewed.

## Review artifacts

All screenshots contain synthetic test records.

- [Before: desktop](frontend-preview/khata/before-desktop.png)
- [Before: mobile](frontend-preview/khata/before-mobile.png)
- [Khata: desktop English](frontend-preview/khata/overview-en-desktop.png)
- [Khata: desktop Bengali](frontend-preview/khata/overview-bn-desktop.png)
- [Khata: mobile English](frontend-preview/khata/overview-en-mobile.png)
- [Khata: mobile Bengali](frontend-preview/khata/overview-bn-mobile.png)
- [Bengali authentication](frontend-preview/khata/auth-bn.png)
- [Bengali schedule editor](frontend-preview/khata/schedule-editor-bn.png)

No deployment was performed.
