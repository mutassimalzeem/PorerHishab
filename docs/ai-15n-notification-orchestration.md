# AI-15N — Notification Orchestration & Digest Engine

## Overview

AI-15N builds the notification orchestration and digest engine on top of the deterministic financial alert infrastructure (AI-15L) and persistent notification delivery outbox (AI-15M).

It connects alert evaluation to downstream delivery via explicit lifecycle events, provides daily digest consolidation, and maintains strict user privacy and financial safety guarantees.

```
Financial Alert Evaluation (AI-15L)
        │
        ▼
Alert Lifecycle Transition (ACTIVE / ESCALATED / RECURRED / UNCHANGED)
        │
        ▼
Domain Notification Event (ALERT_CREATED / ALERT_ESCALATED / ALERT_RECURRED)
        │
        ▼
Notification Orchestrator (`orchestrate_alert_lifecycle_event`)
        │
        ├─────────────────────────────────────────┐
        ▼                                         ▼
Immediate Notification Outbox             Daily Digest Candidate
(`notification_deliveries`)               (`notification_digests` / `items`)
        │                                         │
        ▼                                         ▼
PostgreSQL Outbox Worker                  Digest Engine (`evaluate_daily_digest`)
(`FOR UPDATE SKIP LOCKED`)                        │
        │                                         ▼
        │                                 Daily Digest Delivery Record
        │                                 (`notification_deliveries`)
        │                                         │
        └─────────────────┬───────────────────────┘
                          ▼
            Channel Adapter (In-App / EmailSender)
                          ▼
                    Delivery Result
```

---

## 1. Core Architectural Guarantees

1. **Financial Source of Truth**: Financial alerts (`financial_alerts`) remain the authoritative domain records. Notification orchestration is purely downstream. Delivery successes or failures never alter, dismiss, or action underlying alerts.
2. **Financial Determinism**: Orchestration never calculates financial metrics (balances, runway, cashflow). All financial data is calculated upstream by deterministic services. Zero LLM involvement in notification decisions or financial amounts.
3. **Delivery Semantics**: The system guarantees **at-least-once processing**. Idempotency is enforced at the database level via unique constraints on idempotency keys (`uq_notification_deliveries_idempotency_key`) and digest user/local-date pairs (`uq_notification_digests_user_local_date`).
4. **Queue Architecture**: Operates without external brokers (zero Redis, Celery, RabbitMQ, or Kafka). Concurrency is managed with PostgreSQL row-level locks (`SELECT FOR UPDATE SKIP LOCKED`).

---

## 2. Milestone A & B: Domain Lifecycle Events

Alert evaluations emit explicit domain events only upon actual state changes:

| Alert Lifecycle Event | Trigger Condition | Orchestration Action |
| --- | --- | --- |
| `ALERT_CREATED` | New alert transitioned to `ACTIVE` | Evaluates immediate notification eligibility; registers digest candidacy |
| `ALERT_ESCALATED` | Existing active alert escalated in severity (e.g. `medium` → `high`) | Triggers escalation notification; updates delivery tracking |
| `ALERT_RECURRED` | Active alert condition re-detected on re-evaluation | Evaluates recurrence policy; increments occurrence count |
| `UNCHANGED` | Active alert condition evaluated with no change | **No-op**: No duplicate events or notification deliveries created |

### Occurrence Tracking & Idempotency
- Deliveries record `occurrence_count` alongside `alert_id` and `channel`.
- Idempotency key format for immediate alerts: `alert:{alert_id}:{channel}:{occurrence_count}:{event_type}`.
- Repeated evaluations within the same lifecycle state produce no new notifications.

---

## 3. Milestone C: Extended Notification Preferences

The user-scoped `notification_preferences` table is extended with granular delivery and digest controls:

| Field | Type | Default | Semantics |
| --- | --- | --- | --- |
| `immediate_enabled` | `Boolean` | `True` | Whether non-critical alerts are delivered immediately |
| `daily_digest_enabled` | `Boolean` | `False` | Whether alerts are consolidated into a daily digest |
| `daily_digest_time` | `String(5)` | `'09:00'` | Preferred local time (HH:MM) for digest dispatch in user's timezone |

### Critical Safety Alert Bypass
- To ensure user financial safety, **`critical` alerts bypass the `immediate_enabled = False` toggle**.
- Critical alerts are always delivered immediately (subject only to channel enablement and email consent).
- During quiet hours, `critical` alerts bypass suppression and deliver immediately.

---

## 4. Milestone D: Daily Digest Engine

The digest engine consolidates active financial alerts into a single privacy-preserving daily communication:

### Aggregation & Inclusion Rules
- **Active Only**: Only alerts in `active` state are included. Dismissed, actioned, or resolved alerts are strictly excluded.
- **Timezone-Aware Local Date**: The user's configured timezone (e.g. `'Asia/Dhaka'`) determines the start and end of the local calendar day.
- **At Most One Digest Per Date**: Database unique constraint `uq_notification_digests_user_local_date (user_id, local_date)` prevents duplicate digests for the same calendar date.
- **Deterministic Ordering**:
  1. Severity: `CRITICAL` > `HIGH` > `MEDIUM` > `LOW` > `INFO`
  2. Timestamp: `created_at` ASC
- **Recurrence & Redundancy Filter**:
  - Non-critical alerts that were already emailed immediately earlier on the same local date are excluded from the digest to prevent duplicate notifications.
  - Critical alerts are retained in the digest as high-priority reminders.
- **Clean Inbox Guarantee**: If a user has zero eligible active alerts on a given date, **no digest record or email is generated**.

---

## 5. Strict Privacy & Content Contract

Transactional notification emails adhere to strict banking and financial privacy standards:

- **Zero Sensitive Data**: Emails NEVER contain account balances, financial amounts, currency symbols, merchant names, account numbers, or raw telemetry.
- **Action-Oriented Messaging**: Emails provide high-level category notices with a secure link to the authenticated web application.
- **Bilingual Content**: All email subjects and bodies are rendered in the user's preferred language (English or Bengali).

---

## 6. API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/finance/notifications/preferences` | Retrieve user notification preferences |
| `PUT` | `/finance/notifications/preferences` | Update user notification preferences |
| `GET` | `/finance/notifications/history` | Paginated delivery history for the current user |
| `POST` | `/finance/notifications/digest/evaluate` | Trigger on-demand digest evaluation for the current user |
| `GET` | `/finance/notifications/digests` | List generated digests and item summaries for the user |
| `GET` | `/finance/notifications/operational-health` | Operational health and queue backlog telemetry (internal/admin) |

---

## 7. Frontend Integration

1. **Notification Preferences (`/settings`)**:
   - Immediate notification toggle.
   - Daily email digest toggle.
   - Digest delivery time picker.
   - Full bilingual support (English and Bengali).
2. **Alerts Center (`/alerts`)**:
   - Tabbed view modes: "Alerts" and "Notification history".
   - Delivery status indicators (`sent`, `delivered`, `pending`, `failed`, `dead_letter`).
   - "Evaluate daily digest" manual trigger button.
