# AI-15K: Account Position & Trusted Cash Integration

## 1. Overview & Objectives

**Milestone:** AI-15K
**Repository:** `mutassimalzeem/PorerHishab`
**Branch:** `feature/ai-15k-account-position`
**Base:** `main`

The objective of AI-15K is to answer the core financial question:
> *"What money do I actually have in my accounts, and how much confidence should I place in that number?"*

Prior to AI-15K, PorerHishab provided account reconciliation mechanics (AI-15A) but lacked a user-facing overview of account positions, trusted cash aggregation, and seamless integration of trusted account balances into cashflow and purchase assessment flows. AI-15K connects these components deterministically.

---

## 2. Mandatory Safety & Design Principles

1. **Strict Financial Determinism**
   - No LLMs are involved in account balance calculations, reconciliation arithmetic, cash position aggregation, safe-to-spend evaluations, runway projections, or obligation reservations.
   - All balance operations rely strictly on deterministic decimal arithmetic (`Decimal` in Python, string-preserved numbers in TypeScript).

2. **Never Invent an Account Balance**
   - When an account has no reported balance, no opening balance, insufficient transaction history, or stale evidence, the system returns an explicit `insufficient_data` or `unavailable` state.
   - Unavailable positions are displayed as `"Not available yet"`. The system **never** substitutes `0.00` for missing or unverified balances. Zero balance (`৳0.00`) is valid only when reconciled.

3. **No Silent Record Mutation**
   - AI-15K never creates adjustment transactions automatically.
   - Transactions are never auto-reconciled, and scheduled obligations are never modified.
   - Foreign currencies are never automatically converted into BDT.

4. **Mandatory User Ownership Isolation**
   - Every account operation is strictly scoped to the authenticated user (`Account.user_id == current.id`).
   - Client-provided `user_id` values are never trusted. Cross-user access returns `404 Not Found`.

---

## 3. Financial Concepts & Reconciliation Mechanics

### Terminology

- **Reported Balance (`current_balance`)**: The balance explicitly supplied by the user/system along with metadata: `balance_source` (`manual`, `statement`, `app`) and `balance_as_of` timestamp.
- **Opening Balance (`opening_balance`)**: Known historical cutoff balance at `opening_balance_date`.
- **Derived Balance**: Calculated deterministically from opening balance + transaction activity after the opening date (`reconcile_account_balance`).
- **Difference**: The difference between reported/current and derived balance when both are available.
- **Reconciliation Status**: Reuses authoritative status semantics from AI-15A:
  - `reconciled`: High confidence, zero difference between reported and derived balances.
  - `mismatch`: Low confidence, difference exists between reported and derived balances.
  - `derived_from_opening`: Derived from opening balance and transactions; no current balance reported.
  - `transaction_snapshot`: Derived from transactions without an opening balance.
  - `reported_only`: Current balance reported without transaction history.
  - `unreconciled`: Insufficient data to derive or reconcile.

### Batch Transaction Pre-fetching (Eliminating N+1 Queries)

To prevent database query bloat when fetching an overview of all user accounts, `reconcile_account_balance` was enhanced with an optional pre-fetched `transactions` argument. `get_account_overview` executes a single query to retrieve all account-linked transactions for the user and partitions them by account in memory before running reconciliation.

---

## 4. Trusted BDT Cash Position Aggregation

The trusted BDT cash position represents funds the user can confidently rely upon for planning:

1. **Eligibility Rules**:
   - Currency must be `BDT`.
   - `position_status` must be `trusted` (which requires `status == "reconciled"` and `diff == 0.00`).
2. **Review & Exclusion States**:
   - Accounts with a discrepancy (`mismatch`) or unverified status are categorized under `review_accounts` and **excluded** from the aggregate total.
   - Non-BDT accounts (e.g. `USD`) are classified as `unsupported_currency` and tracked individually with explicit exclusion notice.
   - Accounts lacking sufficient data are classified as `insufficient_data` and excluded.
3. **Aggregate Status**:
   - `available`: All eligible BDT accounts are reconciled with no review accounts.
   - `partial`: At least one trusted BDT account exists, but other accounts require review or use foreign currencies.
   - `unavailable`: No trusted BDT accounts exist (`total` is `null`).

---

## 5. API Endpoints

### Accounts Overview & Management (`/accounts`)

- `GET /accounts`: Authenticated account overview containing list of accounts with reconciliation metadata and `trusted_bdt_position`.
- `POST /accounts`: Creates a new account scoped to the authenticated user (201 Created).
- `GET /accounts/position`: Standalone endpoint returning the user's `trusted_bdt_position`.
- `GET /accounts/{account_id}`: Detail for a single user-owned account.
- `PATCH /accounts/{account_id}/balance`: Updates current balance, balance source, and balance as-of timestamp.
- `PATCH /accounts/{account_id}/balance/opening`: Updates opening balance and opening cutoff date.

### Coach Cashflow & Spending Integration

- `POST /finance/coach/cashflow`:
  - Accepts optional `use_account_position: bool` and optional `starting_balance: str`.
  - When `use_account_position: true`, resolves trusted BDT position total as starting balance.
  - Returns `balance_source: "account_position"` or `"user_supplied"`.
- `POST /finance/coach/spending-decision`:
  - Accepts optional `use_account_position: bool` and optional `starting_balance: str`.
  - When `use_account_position: true`, resolves trusted BDT position total as available balance.
  - Returns `balance_source: "account_position"` or `"user_supplied"`.

---

## 6. Frontend Khata Workspace Integration

1. **Accounts Screen (`/accounts`)**:
   - **Total Trusted BDT Position**: Highlighted summary card displaying trusted aggregate, contributing accounts, and notice regarding non-bank verification.
   - **Accounts List**: Cards showing account name, type, source, currency, reported balance with timestamp, reconciliation status badge, and difference display.
   - **Expandable Reconciliation Details**: Detailed panel showing opening balance, derived balance, transaction count, and possible explanations for differences (missing transactions, duplicates, timing differences).
   - **Foreign Currency Callout**: Explicit explanation when an account is excluded due to non-BDT currency.
   - **Action Dialogs**: Accessible dialogs for Add Account, Update Current Balance, and Update Opening Balance.
2. **Dashboard**:
   - Dedicated **Account position** card directly adjacent to **Recorded net activity**.
   - Preserves clear distinction between recorded activity (cashflow) and actual account position.
   - Displays "Not available yet" when unverified, never showing `0.00`.
3. **Cashflow Outlook & Purchase Assessment**:
   - Radio selector: "Use trusted account position" vs "Enter a balance".
   - Lists contributing accounts and exclusions when trusted position is active.
   - Clearly discloses balance source in resulting projections and assessment decisions.
4. **Bilingual Support & Accessibility**:
   - Complete English and Bengali translations across all account terminology, statuses, actions, and explanations.
   - `aria-expanded`, `aria-label`, and accessible role semantics throughout.

---

## 7. Verification Summary

- **Backend Tests**: 20 unit tests in `backend/test_account_position.py` covering authentication, ownership isolation, account creation, trusted aggregation, foreign currency exclusion, mismatch handling, zero and negative balances, patch updates, and coach integrations.
  - **Full Backend Suite**: 629 tests passed, 1 skipped.
- **Frontend Tests**: 12 unit tests in `frontend/src/test/accounts.test.tsx` covering loading, empty states, account list, badge rendering, expandable details, dialog submissions, Bengali localization, Dashboard integration, and Cashflow/Purchase integrations.
  - **Full Frontend Suite**: 117 tests passed across 16 test files.
- **Contract Synchronization**: `scripts/generate_frontend_contracts.py --check` verified clean contract match.
- **Typecheck & Lint**: `npm run typecheck`, `npm run lint`, and `npm run build` passed with zero errors.
