# AI-15M — Notification Delivery Infrastructure

## Overview

AI-15M implements the notification delivery infrastructure required to turn AI-15L persistent proactive financial alerts into controlled, reliable, and privacy-preserving notifications.

AI-15L financial alerts remain the single authoritative source of truth. Notification delivery is purely downstream infrastructure.

```
Financial Data
      ↓
Deterministic Financial Services (AI-15A through AI-15K)
      ↓
AI-15L Alert Evaluation
      ↓
Persisted Financial Alert (`financial_alerts`)
      ↓
Notification Eligibility & Preferences (`notification_preferences`)
      ↓
Notification Delivery Record / Outbox (`notification_deliveries`)
      ↓
Channel Adapter (In-App, EmailSender)
      ↓
Delivery Result
```

## 1. Supported Channels & Future Scope

### Initial Channels (AI-15M)
- **In-App Notifications**: Integrated with the AI-15L alert center without duplicating financial alert data.
- **Email Notifications**: Provider-independent, privacy-preserving transactional notifications directing users to the authenticated web application.

### Future Channels
- SMS, WhatsApp, and mobile push notifications are deferred to future milestones. The architecture and schemas (`NotificationChannel`, `notification_deliveries`) support these channels without requiring architectural refactoring.

## 2. Notification Preferences Model

Persisted in the user-scoped `notification_preferences` table:

| Field | Type | Default | Semantics |
| --- | --- | --- | --- |
| `in_app_enabled` | `Boolean` | `True` | Controls in-app notification creation |
| `in_app_min_severity` | `String(20)` | `'info'` | Minimum severity threshold for in-app delivery |
| `email_enabled` | `Boolean` | `False` | Conservative default: email disabled until explicitly toggled |
| `email_consent` | `Boolean` | `False` | Explicit opt-in consent requirement |
| `email_consent_at` | `DateTime` | `None` | Audit timestamp when email consent was granted |
| `email_min_severity` | `String(20)` | `'warning'` | Minimum severity threshold for email delivery |
| `quiet_hours_enabled` | `Boolean` | `False` | Enables time-based suppression of non-critical alerts |
| `quiet_hours_start` | `String(5)` | `'22:00'` | 24-hour time string in user's timezone |
| `quiet_hours_end` | `String(5)` | `'07:00'` | 24-hour time string in user's timezone |
| `timezone` | `String(50)` | `'Asia/Dhaka'` | IANA timezone identifier |
| `frequency_mode` | `String(20)` | `'immediate'` | `'immediate'`, `'daily_digest'`, or `'off'` |

### Preference Semantics & Privacy Principles
- **Email Consent Requirement**: A user will never receive financial email notifications without explicit opt-in consent (`email_consent == True`).
- **Conservative Defaults**: New user accounts default to `email_enabled = False` and `email_consent = False`.
- **Severity Filtering**: Alerts below the user's minimum severity threshold are suppressed (`BELOW_SEVERITY_THRESHOLD`).
- **Deterministic Quiet Hours**:
  - Timezone-aware calculation handling overnight windows (e.g. 22:00 to 07:00).
  - Explicit Policy: `info`, `low`, `medium`, and `high` alerts respect quiet hours and are deferred (`next_attempt_at` rescheduled to window end). `critical` alerts bypass quiet hours to guarantee user financial protection.
- **Frequency Control**:
  - `immediate`: Immediate processing upon alert creation or escalation.
  - `daily_digest`: Immediate dispatch is suppressed; earmarked for future digest aggregation.
  - `off`: Complete channel suppression.

## 3. Persistent Delivery Outbox & Concurrency

Deliveries are recorded in `notification_deliveries`:

- **Deterministic Idempotency Key**:
  `generate_idempotency_key(user_id, alert_id, channel, notification_event)`
  Example: `usr_1:alt_42:chn_email:evt_ALERT_CREATED`
  No timestamps are used in the identity.
- **Database Unique Constraints**:
  - `uq_notification_deliveries_logical_identity`: `(user_id, alert_id, channel, notification_event)`
  - `uq_notification_deliveries_idempotency_key`: `(idempotency_key)`
- **Row-Level Claiming**:
  `SELECT ... FROM notification_deliveries WHERE status IN ('PENDING', 'FAILED') AND (next_attempt_at IS NULL OR next_attempt_at <= :now) FOR UPDATE SKIP LOCKED`
  Ensures competing workers claim disjoint deliveries atomically without double-claiming or double-incrementing attempts.

### Delivery Lifecycle State Machine

```
              ┌───────────┐
              │  PENDING  │
              └─────┬─────┘
                    │ (claimed by worker / SKIP LOCKED)
                    ▼
              ┌────────────┐
   ┌─────────►│ PROCESSING │
   │          └─────┬──────┘
   │                │
   │   ┌────────────┼─────────────┐
   │   │ (success)  │ (transient) │ (permanent / max retries)
   │   ▼            ▼             ▼
   │ ┌──────┐   ┌────────┐   ┌─────────────┐
   │ │ SENT │   │ FAILED │   │ DEAD_LETTER │
   │ └──────┘   └───┬────┘   └─────────────┘
   │                │
   └────────────────┘ (next_attempt_at reached)
```

- `SUPPRESSED`: Evaluated as ineligible at enqueue or processing time (e.g. quiet hours, no consent, below threshold).

### Bounded Retry Policy
- Configurable maximum retries (default 3).
- Exponential/staged backoff delays: 60s, 300s, 900s.
- Failure classification:
  - **Transient** (connection timeout, SMTP server busy, temporary provider outage): status transitions to `FAILED` with `next_attempt_at = now + backoff`.
  - **Permanent** (invalid recipient format, SMTP authentication failure, rejected address): status transitions immediately to `DEAD_LETTER`.

## 4. Email Privacy & Security Guarantees

Email notifications strictly preserve financial privacy:
1. **No Sensitive Financial Amounts**: Email subjects and bodies NEVER include account balances, transaction amounts, merchant names, account numbers, or detailed financial evidence.
2. **Generic Safe Subjects**:
   - Non-critical: `"PorerHishab financial alert"`
   - Critical: `"PorerHishab critical financial alert"`
3. **Authenticated Links Only**: Directs the user to the authenticated web app (`/alerts`).
4. **No Financial Parameters in URLs**: URL query parameters never contain transaction or balance details.

## 5. Development & Testing Safety

- **Default Test Backend**: The application defaults to `EMAIL_BACKEND=test`, capturing all sent emails in memory (`TestEmailSender.get_sent_messages()`). Real emails are never sent in local development, CI, or automated tests.
- **External SMTP Configuration**: Sending real emails requires explicit configuration via environment variables:
  - `EMAIL_BACKEND=smtp`
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`

## 6. Background Worker Architecture & Future Scaling

- **Current Implementation**: Lightweight DB-backed outbox with independent database sessions (`SessionLocal`) inside FastAPI background execution and worker tasks. No request-scoped SQLAlchemy sessions leak into background tasks.
- **Future Queue Migration**: When traffic demands multi-process or distributed asynchronous execution across nodes, the outbox design readily migrates to Celery, Arq, or Redis Streams without modifying domain models or alert engines.
