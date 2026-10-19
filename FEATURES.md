# Zyra — Smart Finance Coach for Bangladesh 🇧🇩
## Complete Feature Vault & Implementation Plan (2026 → 2027+)

> Single source of truth for the 2026 market audit. **Bangladesh-first:** bKash / Nagad / Rocket / Upay, not UPI. Complements `README.md`.

### 0. Vision
**Your Money's ChatGPT on WhatsApp/Messenger — it doesn't just track your Taka, it protects it.**

Zyra turns messy bKash SMS, bank PDFs, Nagad cash-outs, DPS slips, family khoroch into one **Privacy-First AI Coach** that lives where Bangladesh lives: **WhatsApp & Messenger**. Ask in Bangla / Roman Bangla / English: *“Ei mashe koto bKash e khorcha korsi? iPhone EMI nite parbo?”*

**Target:** 60M+ salaried youth, freelancers, students, young families, remittance households.

### 1. Market Reality Check (Why CSV MVP Won't Win in 2027)

| Your MVP Oct 2025 | Bangladesh Demand 2026-27 |
|---|---|
| CSV upload + regex `starbucks -> Coffee` | BD has no UPI/AA — users demand **bKash/Nagad/Rocket SMS auto-parse + Bank PDF OCR + Email forward** |
| 12 regex rules, ~60% accuracy | Fails on `Cash Out Tk1,500 to 017XX TrxID 9AX Fee Tk27.50` — need **Bangla/Roman Bangla NLP + merchant normalization** |
| Past charts only | Future: **“Taka Sesh Date”** — cashflow forecasting is #1 premium request |
| Single user | **Family / Mess / Samity joint khata** — no BD app does it well |
| Isolated app | Users live on **WhatsApp/Messenger** — coach must live there |

**Insights (2026):** Mint dead, YNAB $109/yr roasted. BD sweet spot **Tk 2,999-4,999/yr**. Top trends: AI Agents, SMS/Statement Intelligence, Subscription/Fee Killer, Behavioral Nudges, Privacy-first. Avg BD user loses **Tk 3,800/yr in bKash fees** alone.

### 2. Project Audit (Oct 2025 Codebase)

**SOLID ✅:** FastAPI clean, JWT + refresh + peppered bcrypt + rate-limit + CORS, SQLAlchemy, per-user isolation, chunked bulk_insert, `list/search_transactions`.

**RISKY ⚠️ — Must Fix Before Scale:**
- **Storage:** `SQLite transactions.db` + `check_same_thread=False` → no scale, no encryption. Need **Postgres (Neon/Supabase) + pgvector + AES-256**.
- **Categorizer:** `categorizer.py` regex only. Need **FinBangla-BERT + LLM fallback + feedback table**.
- **Ingestion:** Only CSV. Real bKash exports need `TrxID, Sender, Amount, Fee, Balance`. Need **SMS / PDF / Email** ingestion.
- **Data Model:** `date String`, no `trx_id, source, fee, balance, account_id, is_recurring, raw JSONB`.
- **Missing:** No frontend, no tests/CI/Docker, no OAuth/2FA, no audit log, stray `ambitionbox_companies.csv`.

### 3. Tiered Feature Architecture (Freemium → Profitable)

#### TIER 0: FREE — Hook (Aha in 5 mins)
- CSV / Excel / bKash-Nagad statement import (auto-detect headers)
- Paste bKash/Nagad SMS block → auto-parse fallback
- Basic categorizer + dashboard + export
- Limit: 1 wallet, 3 months history, no predictor/WhatsApp

#### TIER 1: PRO — Tk 399/mo · Tk 2,999/yr — *The Converter* (70% revenue)

**A) True Auto-Sync Engine for Bangladesh**
- **MFS SMS Parser:** `Bkash: Cash Out Tk500 to 017... Fee Tk10 Bal Tk12,340 TrxID 9AX...` → structured txn with fee split. Same for Nagad/Rocket/Upay.
- **Bank PDF Intelligence:** BRAC, City, EBL, DBBL, Islami (NPSB/BEFTN) via OCR + layout model.
- **Email Forward:** `alert@bracbank.com`, bKash emails → auto-ingest.
- *Why premium?* Saves 3 hrs/mo, never touch CSV.

**B) AI Categorizer 2.0 — Bangla Edition**
- **FinBangla-BERT + LLM + Merchant Normalization:** Pathao, Foodpanda, Shohoz, Aarong, Shwapno, Grameenphone, `bKash Fee`, roman `bazar, rickshaw, basa vara` → auto category with logo.
- 1-tap correction learns per-user. >93% accuracy.

**C) Cashflow Predictor & "Taka Sesh Date"**
- Prophet/ARIMA on 90 days → *“Ei khoroch cholle 28 Feb taka 0 hobe. 7,500 Tk kom khoroch koro.”*
- Predicts rent, current bill, DPS, card due (Eid/bonus aware).

**D) Fee & Subscription Killer (Viral)**
- Auto-detects Netflix, Spotify, Chorki, Hoichoi, Link3, DPS, EMI, **bKash fees**.
- Insight: *“Goto 12 mase bKash Fee 3,840 Tk. BEFTN use korle 2,100 Tk bachto.”* Alert on trial ending.

#### TIER 2: PREMIUM+ — Tk 699/mo · Tk 4,999/yr — *Wealth Coach* (30% users, 80% margin)

**E) Conversational AI Coach on WhatsApp/Messenger — THE 2027 MOAT**
- Not a chatbot — proactive agent (pgvector memory).
- `User: “iPhone EMI nite parbo?”` → `Zyra: “EBL bill 42k 5 tarikhe + Foodpanda 32% barse. 2 mas por cash e nile 8k bachba. Goal banabo?”`
- Bangla/English mix, voice notes, daily 8 AM brief. Stack: `POST /coach/chat` + LLM function calling.

**F) Bangladesh Wealth OS**
- **NBR e-TIN:** slab, surcharge, DPS/FDR/savings certificate rebate, zero-return for freelancers.
- **DPS/FDR/Sanchayapatra + Gold bhori + Samity** maturity & lending tracker.
- **Monte Carlo Goal Simulator + CIB Credit Health** tips.

**G) Household & Mess OS**
- Shared vault: Couple / Family / Mess-mates (5 members), pooled budgets, Qurbani/Hajj goals, permissions.

**H) Behavioral Nudges**
- Impulse cooldown: *“Foodpanda order? 30 min wait — 60% cancel.”*
- Salary blocker 1st-5th, Ramadan/Eid mode, Zakat calc.

### 4. What NOT to Build
Don't build bKash/Nagad payment rail, don't build trading, don't do Manual Envelope Budget.

### 5. Tech Upgrade Plan
| Current | Upgrade To |
|---|---|
| SQLite | Postgres (Neon/Supabase) + pgvector + AES-256 |
| regex `categorizer.py` | `services/categorizer_ml.py` FinBERT + LLM fallback |
| `date String` no fee/trx_id | `accounts` + `transactions(trx_id, source enum[bkash/nagad/rocket/upay/bank/cash], fee, balance, recurring, raw JSONB)` |
| CSV only | `/ingest/{csv,sms,pdf,email}` + `/webhook/whatsapp` + Celery/RQ |
| No UI | Next.js 15 + Tailwind + Recharts + PWA |
| JWT only | + Google OAuth, 2FA OTP, audit log |
| No tests | pytest 80%+, GitHub Actions, Docker, Fly.io |

### 6. Roadmap — 9 Months to Profitability
- **M1-2 Foundation:** Postgres + schema + parser + categorizer v2 + Next.js
- **M3-5 PRO Moat:** SMS+Email+Predictor+Fee Killer → PRO Tk 2,999/yr via SSLCommerz / bKash Payment
- **M6-8 PREMIUM Moat:** WhatsApp/Messenger bot + NBR Tax + DPS → PREMIUM Tk 4,999/yr
- **M9+ Scale:** Household/Mess OS + Referral virality

### 7. Pricing for Bangladesh
Free 0 | PRO Tk 399/mo (Tk 2,999/yr) | PREMIUM Tk 699/mo (Tk 4,999/yr) via bKash/Nagad/Rocket + SSLCommerz/AamarPay.
**Math 2027:** 10k free → 5% → 500 paid → ~12L BDT ARR @ 72% margin (AI ~Tk 80/user/mo). Annual prepay critical (BD monthly churn 11% if monthly).

### 8. Privacy — The Real Moat
Local-first, encrypted, never sold (USP vs data sellers). Explicit SMS consent, on-device parsing option, Bangladesh Bank MFS guideline ready.

*Source: Feature vault v1 — Maintainer: mutassimalzeem — Last audit: 2026-10-19*


