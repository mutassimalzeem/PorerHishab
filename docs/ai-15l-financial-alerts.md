# AI-15L — Proactive Financial Alerts & Notification Readiness

## Overview

AI-15L introduces a persistent, user-scoped in-app financial alert system that proactively highlights important financial conditions, obligations, and risks across PorerHishab.

Rather than requiring users to open individual screens (Runway, Cashflow, Accounts, Plans, Insights) to discover important financial conditions, AI-15L deterministically synthesizes conditions into prioritized, actionable in-app notifications.

## 1. Supported Alert Types and Trigger Sources

All alert triggers build on existing deterministic financial engines (AI-15A through AI-15K). No new financial calculation engine or LLM trigger generation is introduced.

| Alert Type | Severity | Category | Trigger Source | Condition | Action URL |
| --- | --- | --- | --- | --- | --- |
| `cash_shortfall` | `critical` | Cash Position | `app.services.finance.runway.financial_runway` | Projected cash balance falls below zero BDT within 30-day forecast horizon | `/cashflow` |
| `cash_at_risk` | `high` | Cash Position | `app.services.finance.runway.financial_runway` | Projected cash balance falls to or below safety threshold | `/cashflow` |
| `obligation_overdue` | `high` / `critical` | Upcoming Obligations | `app.models.scheduled_cashflow_item` + `app.services.finance.obligations` | Scheduled expense obligation is past due date with remaining amount > 0 BDT (critical if > 7 days overdue) | `/cashflow` |
| `obligation_due_soon` | `medium` / `high` | Upcoming Obligations | `app.models.scheduled_cashflow_item` + `app.services.finance.obligations` | Scheduled expense obligation is due within 3 days (or within 7 days if >= 50% of known cash) | `/cashflow` |
| `account_unreconciled` | `medium` | Account Reliability | `app.services.finance.account_position.get_account_overview` | Account position status is `unreconciled` (reported balance != derived balance) | `/accounts` |
| `savings_goal_at_risk` | `medium` / `high` | Coaching / Goals | `app.services.finance.coaching_feedback.visible_coaching` | Active savings goal target date is overdue or required contribution exceeds capacity | `/plans` |
| `spending_spike` | `medium` | Coaching / Categories | `app.services.finance.coaching_feedback.visible_coaching` | Spending in reducible category increased by > 50% vs previous complete month | `/transactions` |

### Non-Negotiable Financial Safety Guardrails
- **Insufficient Data Suppression**: When cash runway or monthly history has `insufficient_data`, no cash-risk alert is generated. Insufficient data is never represented as zero.
- **Foreign Currency Isolation**: Non-BDT accounts are classified as `unsupported_currency` and are excluded from BDT cash position alerts and reconciliation mismatch alerts.
- **Historical Evidence Framing**: Evidence stored in alert records includes `observed_at` timestamps. The UI explicitly states that evidence reflects conditions at detection time and is not a live balance.
- **User-Reported Action Disclaimers**: Marking an alert as actioned records `actioned_at` but does not verify that the financial condition has cleared.

## 2. Deduplication Policy and Stable Identity

Every alert record has a deterministic `alert_key` uniquely scoped to `user_id`:
- Cash runway: `cash_position:runway_risk`
- Obligations: `obligation:{item_id}:due`
- Account position: `account:{account_id}:reconciliation_mismatch`
- Coaching recommendations: `coaching:{rec_id}`

### Concurrency and Deduplication Protection
- **Database Constraint**: `UniqueConstraint("user_id", "alert_key", name="uq_financial_alerts_user_key")`
- **Row-Level Serialization**: `lock_user_for_evaluation(db, user_id)` uses PostgreSQL row-level locks on `User` to serialize concurrent evaluation runs for the same user.

## 3. Lifecycle Semantics

Alerts have explicit status values: `active`, `resolved`, and `dismissed`.

```
                  [Condition Detected]
                           │
                           ▼
                      ┌─────────┐
         ┌───────────►│ active  │◄────────────┐
         │            └────┬────┘             │
         │                 │                  │
    Reappearance      User Dismiss      Reactivation
    after resolution       │            (Critical escalation)
         │                 ▼                  │
         │           ┌───────────┐            │
         │           │ dismissed ├────────────┘
         │           └───────────┘
   [Condition Cleared]
         │
         ▼
   ┌──────────┐
   │ resolved │
   └──────────┘
```

1. **Active State**:
   - `first_detected_at` and `last_detected_at` record detection timestamps.
   - Repeated evaluation of an unchanged active condition updates `last_detected_at` idempotently, without incrementing unread count or modifying `read_at`.
   - When a meaningful change occurs (e.g. escalation from at-risk to shortfall), `occurrence_count` increments, severity/message/evidence update, and `read_at` is cleared so the critical escalation is surfaced.

2. **Resolution State**:
   - An alert transitions to `resolved` when its underlying condition is reliably verified to have cleared:
     - Cash risk resolves when runway is verified `positive`.
     - Obligation alert resolves when the obligation is paid, cancelled, has zero remaining balance, or is deleted.
     - Account mismatch resolves when the account position becomes `trusted` or the account is deleted.
     - Coaching alerts resolve when the recommendation is no longer returned by `visible_coaching`.

3. **Reappearance after Resolution**:
   - If a previously resolved condition recurs (e.g. balance drops again into shortfall), the alert reactivates to `active`, sets `resolved_at = None`, increments `occurrence_count`, and clears `read_at`.

4. **Dismissal and Critical Override**:
   - When a user dismisses an alert, `status = "dismissed"` and `dismissed_at` are recorded.
   - Normal repeat evaluations keep the alert dismissed and do not spam the user.
   - **Critical Warning Override**: If a dismissed condition meaningfully escalates to `critical` (e.g. from at-risk to cash shortfall), the alert reactivates to `active` because critical financial warnings must not be suppressed by old dismissals.

5. **Read State**:
   - Represented independently via `read_at: datetime | None`.
   - An unread alert has `read_at IS NULL`.
   - Unread count (`GET /finance/alerts/unread-count`) counts all active alerts for the user where `read_at IS NULL`.

## 4. Evaluation Strategy

- **On-Demand Authenticated Endpoint**: `POST /finance/alerts/evaluate`.
- **Idempotency**: Repeated evaluations with unchanged conditions return `unchanged` counts without creating duplicates or modifying timestamps.
- **Summary Contract**: Returns `{ created, updated, resolved, unchanged, evaluated_at }`.
- **Performance**: Queries are user-scoped with indexed lookups (`ix_financial_alerts_user_status`, `ix_financial_alerts_user_read`, `ix_financial_alerts_user_severity`).

## 5. API Endpoints

All endpoints require JWT bearer authentication and derive user identity from `get_current_user`.

- `POST /finance/alerts/evaluate`: Evaluate conditions and synchronize alerts.
- `GET /finance/alerts`: Retrieve alerts with deterministic priority sorting (Critical > High > Medium > Low > Info; Active > Dismissed > Resolved) and pagination (`limit`, `offset`).
- `GET /finance/alerts/unread-count`: Retrieve unread count across all user records.
- `PATCH /finance/alerts/{id}/read`: Mark alert as read (`read_at = now`).
- `PATCH /finance/alerts/{id}/dismiss`: Dismiss alert (`dismissed_at = now`).
- `PATCH /finance/alerts/{id}/actioned`: Record user-reported action (`actioned_at = now`).
- `POST /finance/alerts/{id}/restore`: Restore dismissed alert to active.

## 6. Notification Readiness Contract

The internal notification delivery contract is defined in `backend/app/schemas/notification_delivery.py`:
- `NotificationChannel`: `"in_app" | "web_push" | "email" | "sms" | "whatsapp"`
- `DeliveryStatus`: `"pending" | "delivered" | "failed" | "suppressed"`
- `DeliveryFailureCategory`: `"invalid_recipient" | "rate_limited" | "provider_error" | "channel_disabled" | "frequency_capped" | "none"`
- `NotificationDeliveryEvent`: Full contract capturing alert ID, recipient user, channel, idempotency key, timestamps, and metadata.

### Explicit Delivery Boundary
- This milestone prepares notification contracts but does not integrate external providers.
- No push notification permissions are requested in the browser.
- No SMS, WhatsApp, or email credentials/gateways are configured.
- No device tokens are stored.

## 7. Frontend Notification Center

- **Page**: `frontend/src/pages/Alerts.tsx` (`/alerts`).
- **Navigation**: Alerts tab with unread count badge in sidebar and mobile nav, plus persistent bell icon in topbar.
- **Controls**: Tab filters (All, Unread, Active, Dismissed, Resolved), severity pills (All, Critical, High, Medium, Low), and manual evaluate button.
- **Alert Cards**: Severity indicators, detection timestamps, occurrence counts, expandable historical evidence with disclaimer, recommended action callout with direct link to relevant screen, and action buttons (Mark as read, I took this action, Dismiss, Restore).
- **Localization**: 100% bilingual coverage (English and Bengali) across all titles, descriptions, buttons, timestamps, and accessibility labels.
- **Accessibility**: Semantic HTML, ARIA tabs/regions, keyboard navigable, axe-core WCAG 2.1 AA compliant, zero horizontal overflow.
