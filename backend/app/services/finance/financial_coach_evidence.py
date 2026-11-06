"""Deterministic user context and evidence assembly for the financial coach (AI-15S-C).

This service gathers verified financial facts from existing deterministic
services and database repositories for the authenticated user only.
The resulting evidence package is the only context the LLM is permitted to use.
No LLM is invoked during evidence assembly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.savings_goal import SavingsGoal
from app.models.transactions import Transaction
from app.schemas.financial_coach import CoachEvidence, CoachIntent, EvidenceType
from app.services.finance.financial_coach_router import IntentRoute
from app.services.intelligence.periods import (
    BANGLADESH_TIMEZONE,
    days_in_month,
    money,
    month_shift,
    month_start,
    today_dhaka,
)


@dataclass
class EvidencePackage:
    """The complete deterministic evidence context assembled for a coach request."""

    intent: CoachIntent
    as_of_date: date
    evidence: list[CoachEvidence] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    requires_clarification: bool = False
    clarification_prompt: str | None = None
    # Canonical AI-17B review used only for the narrow review-explanation path.
    # The assembler builds it server-side; clients never supply this context.
    review: Any | None = None

    def get_evidence_by_id(self, evidence_id: str) -> CoachEvidence | None:
        for ev in self.evidence:
            if ev.evidence_id == evidence_id:
                return ev
        return None

    @property
    def evidence_ids(self) -> set[str]:
        return {ev.evidence_id for ev in self.evidence}


def parse_question_date_period(
    question: str,
    as_of: date,
    explicit_start: date | None = None,
    explicit_end: date | None = None,
) -> tuple[date | None, date | None, bool]:
    """Parse date period from question or explicit bounds.

    Returns:
        (start_date, end_date, is_ambiguous)
    """
    if explicit_start is not None and explicit_end is not None:
        if explicit_start > explicit_end:
            return None, None, True
        return explicit_start, explicit_end, False

    q = question.strip().lower()

    # Check for ISO dates: YYYY-MM-DD
    iso_dates = re.findall(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", q)
    if len(iso_dates) == 2:
        try:
            d1, d2 = date.fromisoformat(iso_dates[0]), date.fromisoformat(iso_dates[1])
            if d1 <= d2:
                return d1, d2, False
            return d2, d1, False
        except ValueError:
            return None, None, True
    elif len(iso_dates) == 1:
        try:
            d = date.fromisoformat(iso_dates[0])
            return d, d, False
        except ValueError:
            return None, None, True

    if "yesterday" in q:
        y = as_of - timedelta(days=1)
        return y, y, False

    if "today" in q:
        return as_of, as_of, False

    if "last week" in q or "previous week" in q:
        # Bangladesh week or standard Monday-Sunday:
        # Start of last week (Monday = 0)
        days_since_monday = as_of.weekday()
        this_monday = as_of - timedelta(days=days_since_monday)
        last_monday = this_monday - timedelta(days=7)
        last_sunday = this_monday - timedelta(days=1)
        return last_monday, last_sunday, False

    if "this week" in q:
        days_since_monday = as_of.weekday()
        this_monday = as_of - timedelta(days=days_since_monday)
        return this_monday, as_of, False

    if "last month" in q or "previous month" in q:
        last_m_start = month_shift(as_of, -1)
        last_m_end = month_shift(as_of, 0) - timedelta(days=1)
        return last_m_start, last_m_end, False

    if "this month" in q:
        return month_start(as_of), as_of, False

    if "last year" in q or "previous year" in q:
        return date(as_of.year - 1, 1, 1), date(as_of.year - 1, 12, 31), False

    if "this year" in q:
        return date(as_of.year, 1, 1), as_of, False

    if "last 30 days" in q or "past 30 days" in q:
        return as_of - timedelta(days=29), as_of, False

    if "last 7 days" in q or "past 7 days" in q:
        return as_of - timedelta(days=6), as_of, False

    # Default for monthly spending: current month to date
    return month_start(as_of), as_of, False


class FinancialCoachEvidenceAssembler:
    """Assembles verified, strictly user-isolated financial evidence."""

    def __init__(self, db: Session, user_id: int, as_of: date | None = None) -> None:
        self.db = db
        self.user_id = user_id
        self.as_of = as_of or today_dhaka()
        self.now_utc = datetime.now(timezone.utc)

    def assemble(
        self,
        route: IntentRoute,
        question: str,
        explicit_start_date: date | None = None,
        explicit_end_date: date | None = None,
        purchase_amount: Decimal | None = None,
        starting_balance: Decimal | None = None,
        schedules_confirmed: bool = False,
    ) -> EvidencePackage:
        """Route to appropriate intent assembler."""
        if route.requires_clarification or route.intent == CoachIntent.UNKNOWN:
            return self._assemble_unknown(route, question)

        intent_map = {
            CoachIntent.SPENDING_ANALYSIS: self._assemble_spending_analysis,
            CoachIntent.CASHFLOW: self._assemble_cashflow,
            CoachIntent.AFFORDABILITY: self._assemble_affordability,
            CoachIntent.SAVINGS: self._assemble_savings,
            CoachIntent.GOAL_PLANNING: self._assemble_goal_planning,
            CoachIntent.SCENARIO_COMPARISON: self._assemble_scenario_comparison,
            CoachIntent.ALERT_EXPLANATION: self._assemble_alert_explanation,
            CoachIntent.FINANCIAL_HEALTH: self._assemble_financial_health,
            CoachIntent.FINANCIAL_REVIEW: self._assemble_financial_review,
            CoachIntent.GENERAL_FINANCE: self._assemble_general_finance,
        }

        assembler = intent_map.get(route.intent, self._assemble_unknown)
        return assembler(
            route=route,
            question=question,
            explicit_start_date=explicit_start_date,
            explicit_end_date=explicit_end_date,
            purchase_amount=purchase_amount or route.extracted_amount,
            starting_balance=starting_balance,
            schedules_confirmed=schedules_confirmed,
        )

    # -------------------------------------------------------------------------
    # Intent: UNKNOWN / CLARIFICATION
    # -------------------------------------------------------------------------
    def _assemble_unknown(self, route: IntentRoute, question: str, **kwargs: Any) -> EvidencePackage:
        clarification = (
            "I could not clearly determine which financial area your question refers to. "
            "Could you clarify if you are asking about your spending, cashflow, purchasing affordability, "
            "savings goals, financial health, or alerts?"
        )
        if len(route.matched_signals) > 1:
            clarification = (
                f"Your question touches on multiple topics ({', '.join(route.matched_signals)}). "
                "Please ask about one topic at a time so I can provide accurate, evidence-grounded figures."
            )

        return EvidencePackage(
            intent=CoachIntent.UNKNOWN,
            as_of_date=self.as_of,
            evidence=[],
            limitations=["Question intent could not be unambiguously mapped to a deterministic finance engine."],
            missing_data=["clear_intent"],
            requires_clarification=True,
            clarification_prompt=clarification,
        )

    # -------------------------------------------------------------------------
    # Intent: SPENDING_ANALYSIS
    # -------------------------------------------------------------------------
    def _assemble_spending_analysis(
        self,
        route: IntentRoute,
        question: str,
        explicit_start_date: date | None = None,
        explicit_end_date: date | None = None,
        **kwargs: Any,
    ) -> EvidencePackage:
        from app.services.intelligence.categories import comparison_expenses_by_category
        from app.services.intelligence.facts import grouped_expenses, scoped, totals
        from app.services.intelligence.snapshot import monthly_history

        start_date, end_date, ambiguous = parse_question_date_period(
            question, self.as_of, explicit_start_date, explicit_end_date
        )

        if ambiguous or start_date is None or end_date is None:
            return EvidencePackage(
                intent=CoachIntent.SPENDING_ANALYSIS,
                as_of_date=self.as_of,
                evidence=[],
                limitations=["The requested time period is ambiguous or invalid."],
                missing_data=["valid_date_range"],
                requires_clarification=True,
                clarification_prompt="Please specify a valid date range (e.g. 'this month', 'last month', or '2026-10-01 to 2026-10-31').",
            )

        evidence_list: list[CoachEvidence] = []
        limitations: list[str] = [
            "Amounts represent recorded transactions in PorerHishab; cash or unrecorded spending is not included.",
        ]
        missing_data: list[str] = []

        # 1. Total transaction records in period
        tx_query = scoped(self.db, self.user_id, start_date, end_date)
        tx_count = tx_query.count()

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_spending_period",
                evidence_type=EvidenceType.RAW_DATA,
                source="transaction_repository",
                label="Analysis period",
                value={"start_date": str(start_date), "end_date": str(end_date)},
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_spending_tx_count",
                evidence_type=EvidenceType.RAW_DATA,
                source="transaction_repository",
                label="Transaction count in period",
                value=tx_count,
                unit="count",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        if tx_count == 0:
            missing_data.append("transactions_in_period")
            limitations.append(f"No transactions found between {start_date} and {end_date}.")
            return EvidencePackage(
                intent=CoachIntent.SPENDING_ANALYSIS,
                as_of_date=self.as_of,
                evidence=evidence_list,
                limitations=limitations,
                missing_data=missing_data,
                period_start=start_date,
                period_end=end_date,
            )

        # 2. Financial totals
        period_totals = totals(self.db, self.user_id, start_date, end_date)
        tot_exp = period_totals.get("expenses") or Decimal("0.00")
        tot_inc = period_totals.get("income") or Decimal("0.00")
        net_savings = period_totals.get("net") or Decimal("0.00")

        evidence_list.extend(
            [
                CoachEvidence(
                    evidence_id="ev_spending_total_expenses",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="intelligence_facts.totals",
                    label="Total expenses in period",
                    value=tot_exp,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("1.0"),
                ),
                CoachEvidence(
                    evidence_id="ev_spending_total_income",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="intelligence_facts.totals",
                    label="Total income in period",
                    value=tot_inc,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("1.0"),
                ),
                CoachEvidence(
                    evidence_id="ev_spending_net_savings",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="intelligence_facts.totals",
                    label="Net savings in period",
                    value=net_savings,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("1.0"),
                ),
            ]
        )

        # 3. Category breakdowns
        categories = grouped_expenses(self.db, self.user_id, start_date, end_date)
        cat_values = {
            row["category"]: row["expenses"]
            for row in categories
            if row.get("expenses") is not None and row["expenses"] > Decimal("0")
        }

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_spending_categories",
                evidence_type=EvidenceType.DERIVED_FACT,
                source="intelligence_facts.grouped_expenses",
                label="Spending breakdown by category",
                value=cat_values,
                unit="BDT",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        if cat_values:
            top_cat, top_amt = max(cat_values.items(), key=lambda x: x[1])
            top_pct = money((top_amt / tot_exp * Decimal("100")) if tot_exp > 0 else Decimal("0"))
            evidence_list.append(
                CoachEvidence(
                    evidence_id="ev_spending_top_category",
                    evidence_type=EvidenceType.INTERPRETATION,
                    source="intelligence_facts.grouped_expenses",
                    label="Top spending category",
                    value={"category": top_cat, "amount": top_amt, "percentage": top_pct},
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.95"),
                )
            )

        # 4. Monthly history & baseline
        hist = monthly_history(self.db, self.user_id, self.as_of)
        if hist.adequate:
            avg_exp = hist.baseline["average_monthly_expenses"]
            avg_inc = hist.baseline["average_monthly_income"]
            evidence_list.extend(
                [
                    CoachEvidence(
                        evidence_id="ev_spending_baseline_monthly_expenses",
                        evidence_type=EvidenceType.ESTIMATE,
                        source="intelligence_snapshot.monthly_history",
                        label="Historical average monthly expenses",
                        value=avg_exp,
                        unit="BDT",
                        as_of_date=self.as_of,
                        observed_at=self.now_utc,
                        confidence=Decimal("0.85"),
                    ),
                    CoachEvidence(
                        evidence_id="ev_spending_baseline_monthly_income",
                        evidence_type=EvidenceType.ESTIMATE,
                        source="intelligence_snapshot.monthly_history",
                        label="Historical average monthly income",
                        value=avg_inc,
                        unit="BDT",
                        as_of_date=self.as_of,
                        observed_at=self.now_utc,
                        confidence=Decimal("0.85"),
                    ),
                ]
            )
        else:
            limitations.append(
                "Historical baseline has fewer than 3 complete calendar months; long-term trend is an estimate."
            )

        return EvidencePackage(
            intent=CoachIntent.SPENDING_ANALYSIS,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
            period_start=start_date,
            period_end=end_date,
        )

    # -------------------------------------------------------------------------
    # Intent: CASHFLOW
    # -------------------------------------------------------------------------
    def _assemble_cashflow(
        self,
        route: IntentRoute,
        question: str,
        starting_balance: Decimal | None = None,
        **kwargs: Any,
    ) -> EvidencePackage:
        from app.schemas.coach import CoachCashflowRequest
        from app.services.finance.account_position import get_account_overview
        from app.services.finance.coach import coach_cashflow

        evidence_list: list[CoachEvidence] = []
        limitations: list[str] = [
            "Cashflow forecasts reserve scheduled expenses against historical income baselines.",
            "Scheduled income is uncertain and excluded from projected balances.",
        ]
        missing_data: list[str] = []

        overview = get_account_overview(self.db, user_id=self.user_id)
        trusted_pos = overview.trusted_bdt_position

        confirmed_balance = starting_balance
        balance_source = "caller_supplied"

        if confirmed_balance is None:
            if trusted_pos.total is not None:
                confirmed_balance = trusted_pos.total
                balance_source = "reconciled_accounts"
            else:
                missing_data.append("starting_balance")
                limitations.append("No reconciled BDT account position or confirmed balance is available.")
                return EvidencePackage(
                    intent=CoachIntent.CASHFLOW,
                    as_of_date=self.as_of,
                    evidence=[],
                    limitations=limitations,
                    missing_data=missing_data,
                    requires_clarification=True,
                    clarification_prompt="To forecast your cashflow, please provide a current balance or link/reconcile a BDT account.",
                )

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_cashflow_starting_balance",
                evidence_type=EvidenceType.RAW_DATA,
                source=f"account_position.{balance_source}",
                label="Starting BDT balance",
                value=confirmed_balance,
                unit="BDT",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0") if balance_source == "reconciled_accounts" else Decimal("0.9"),
            )
        )

        try:
            forecast = coach_cashflow(
                self.db,
                self.user_id,
                CoachCashflowRequest(starting_balance=confirmed_balance, months_ahead=3),
                as_of=self.as_of,
            )
        except Exception as exc:
            limitations.append(f"Could not compute full cashflow forecast: {exc}")
            return EvidencePackage(
                intent=CoachIntent.CASHFLOW,
                as_of_date=self.as_of,
                evidence=evidence_list,
                limitations=limitations,
                missing_data=["cashflow_calculation_error"],
            )

        limitations.extend(forecast.get("limitations", []))

        # Add projection months
        for idx, m in enumerate(forecast.get("months", [])):
            month_label = m["month"]
            sched_exp = m.get("scheduled_expenses", Decimal("0"))
            proj_bal = m.get("projected_balance")
            no_inc_bal = m.get("balance_without_future_income")

            evidence_list.append(
                CoachEvidence(
                    evidence_id=f"ev_cashflow_month_{idx}_scheduled_expenses",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="finance.coach_cashflow",
                    label=f"Scheduled expenses for {month_label}",
                    value=sched_exp,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("1.0"),
                )
            )

            if proj_bal is not None:
                evidence_list.append(
                    CoachEvidence(
                        evidence_id=f"ev_cashflow_month_{idx}_projected_balance",
                        evidence_type=EvidenceType.ESTIMATE,
                        source="finance.coach_cashflow",
                        label=f"Projected balance at end of {month_label}",
                        value=proj_bal,
                        unit="BDT",
                        as_of_date=self.as_of,
                        observed_at=self.now_utc,
                        confidence=Decimal("0.80"),
                    )
                )

            if no_inc_bal is not None:
                evidence_list.append(
                    CoachEvidence(
                        evidence_id=f"ev_cashflow_month_{idx}_balance_without_future_income",
                        evidence_type=EvidenceType.DERIVED_FACT,
                        source="finance.coach_cashflow",
                        label=f"Balance without future income for {month_label}",
                        value=no_inc_bal,
                        unit="BDT",
                        as_of_date=self.as_of,
                        observed_at=self.now_utc,
                        confidence=Decimal("0.90"),
                    )
                )

        return EvidencePackage(
            intent=CoachIntent.CASHFLOW,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
            period_start=self.as_of,
            period_end=month_shift(self.as_of, 3) - timedelta(days=1),
        )

    # -------------------------------------------------------------------------
    # Intent: AFFORDABILITY
    # -------------------------------------------------------------------------
    def _assemble_affordability(
        self,
        route: IntentRoute,
        question: str,
        purchase_amount: Decimal | None = None,
        starting_balance: Decimal | None = None,
        **kwargs: Any,
    ) -> EvidencePackage:
        from app.schemas.coach import CoachPurchaseRequest
        from app.services.finance.account_position import get_account_overview
        from app.services.finance.coach import coach_purchase

        evidence_list: list[CoachEvidence] = []
        limitations: list[str] = [
            "Affordability checks conservative near-term obligations (30-day runway).",
            "Unrecorded expenses, overdue bills, and future purchases may affect affordability.",
        ]
        missing_data: list[str] = []

        if purchase_amount is None or purchase_amount <= Decimal("0"):
            missing_data.append("purchase_amount")
            return EvidencePackage(
                intent=CoachIntent.AFFORDABILITY,
                as_of_date=self.as_of,
                evidence=[],
                limitations=limitations,
                missing_data=missing_data,
                requires_clarification=True,
                clarification_prompt="How much does the purchase cost in BDT? (e.g., 'Can I afford 15,000 BDT for a laptop?')",
            )

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_affordability_purchase_amount",
                evidence_type=EvidenceType.RAW_DATA,
                source="caller_request",
                label="Proposed purchase amount",
                value=purchase_amount,
                unit="BDT",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        overview = get_account_overview(self.db, user_id=self.user_id)
        trusted_pos = overview.trusted_bdt_position
        confirmed_balance = starting_balance

        if confirmed_balance is None:
            if trusted_pos.total is not None:
                confirmed_balance = trusted_pos.total
            else:
                missing_data.append("starting_balance")
                limitations.append("No reconciled BDT account position or confirmed balance is available.")
                return EvidencePackage(
                    intent=CoachIntent.AFFORDABILITY,
                    as_of_date=self.as_of,
                    evidence=evidence_list,
                    limitations=limitations,
                    missing_data=missing_data,
                    requires_clarification=True,
                    clarification_prompt="What is your current available balance in BDT to evaluate this purchase?",
                )

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_affordability_starting_balance",
                evidence_type=EvidenceType.RAW_DATA,
                source="account_position",
                label="Available starting balance",
                value=confirmed_balance,
                unit="BDT",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        try:
            decision = coach_purchase(
                self.db,
                self.user_id,
                CoachPurchaseRequest(
                    purchase_amount=purchase_amount,
                    starting_balance=confirmed_balance,
                    safety_buffer=Decimal("5000.00"),
                    horizon_days=30,
                ),
                as_of=self.as_of,
            )
        except Exception as exc:
            limitations.append(f"Affordability calculation error: {exc}")
            return EvidencePackage(
                intent=CoachIntent.AFFORDABILITY,
                as_of_date=self.as_of,
                evidence=evidence_list,
                limitations=limitations,
                missing_data=["decision_error"],
            )

        reserve = decision.get("scheduled_expense_reserve", Decimal("0"))
        remaining = decision.get("remaining_after_purchase_and_reserve", Decimal("0"))
        status = decision.get("status", "unknown")

        evidence_list.extend(
            [
                CoachEvidence(
                    evidence_id="ev_affordability_reserve",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="finance.coach_purchase",
                    label="Upcoming 30-day scheduled expense reserve",
                    value=reserve,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.95"),
                ),
                CoachEvidence(
                    evidence_id="ev_affordability_remaining_balance",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="finance.coach_purchase",
                    label="Remaining balance after purchase and reserve",
                    value=remaining,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.95"),
                ),
                CoachEvidence(
                    evidence_id="ev_affordability_status",
                    evidence_type=EvidenceType.INTERPRETATION,
                    source="finance.coach_purchase",
                    label="Affordability decision assessment",
                    value=status,
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.90"),
                ),
            ]
        )

        limitations.extend(decision.get("warnings", []))

        return EvidencePackage(
            intent=CoachIntent.AFFORDABILITY,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
            period_start=self.as_of,
            period_end=self.as_of + timedelta(days=30),
        )

    # -------------------------------------------------------------------------
    # Intent: SAVINGS
    # -------------------------------------------------------------------------
    def _assemble_savings(self, route: IntentRoute, question: str, **kwargs: Any) -> EvidencePackage:
        from app.services.finance.coach import recommendations
        from app.services.intelligence.snapshot import monthly_history

        evidence_list: list[CoachEvidence] = []
        limitations: list[str] = [
            "Savings opportunities identify categories where recent spending exceeded previous averages.",
            "Estimated savings are opportunities, not guaranteed surplus.",
        ]
        missing_data: list[str] = []

        hist = monthly_history(self.db, self.user_id, self.as_of)
        if not hist.adequate:
            missing_data.append("sufficient_monthly_history")
            limitations.append("Requires at least 3 complete observed months to calculate savings baselines.")

        recs = recommendations(self.db, self.user_id, as_of=self.as_of)
        items = recs.get("recommendations", [])

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_savings_opportunity_count",
                evidence_type=EvidenceType.RAW_DATA,
                source="finance.recommendations",
                label="Identified savings opportunities count",
                value=len(items),
                unit="count",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        total_potential_monthly = Decimal("0")
        for idx, r in enumerate(items[:5]):
            monthly_save = Decimal(str(r.get("estimated_monthly_saving", 0)))
            total_potential_monthly += monthly_save
            cat = r.get("category", "General")

            evidence_list.append(
                CoachEvidence(
                    evidence_id=f"ev_savings_opportunity_{idx}_{cat.lower()}",
                    evidence_type=EvidenceType.ESTIMATE,
                    source="finance.recommendations",
                    label=f"Potential monthly savings in {cat}",
                    value={"category": cat, "monthly_saving": monthly_save},
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.75"),
                )
            )

        if items:
            evidence_list.append(
                CoachEvidence(
                    evidence_id="ev_savings_total_potential_monthly",
                    evidence_type=EvidenceType.ESTIMATE,
                    source="finance.recommendations",
                    label="Total estimated monthly savings opportunity",
                    value=total_potential_monthly,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.75"),
                )
            )

        if hist.adequate:
            avg_surplus = hist.baseline.get("average_monthly_net", Decimal("0"))
            evidence_list.append(
                CoachEvidence(
                    evidence_id="ev_savings_historical_monthly_surplus",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="intelligence_snapshot.monthly_history",
                    label="Historical average monthly surplus",
                    value=avg_surplus,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.85"),
                )
            )

        return EvidencePackage(
            intent=CoachIntent.SAVINGS,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
            period_start=month_shift(self.as_of, -3),
            period_end=self.as_of,
        )

    # -------------------------------------------------------------------------
    # Intent: GOAL_PLANNING
    # -------------------------------------------------------------------------
    def _assemble_goal_planning(self, route: IntentRoute, question: str, **kwargs: Any) -> EvidencePackage:
        from app.services.finance.goal_planning import planning_overview

        evidence_list: list[CoachEvidence] = []
        limitations: list[str] = [
            "Savings progress reflects user-reported savings and tracked transactions.",
            "Monthly capacity is an estimate based on historical surplus and scheduled bills.",
        ]
        missing_data: list[str] = []

        overview = planning_overview(self.db, self.user_id, as_of=self.as_of)
        active_goals = overview.goals

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_goals_active_count",
                evidence_type=EvidenceType.RAW_DATA,
                source="goal_planning.overview",
                label="Active goals count",
                value=len(active_goals),
                unit="count",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        if not active_goals:
            missing_data.append("active_goals")
            limitations.append("No active savings goals found. Create a goal in the Plans section.")
            return EvidencePackage(
                intent=CoachIntent.GOAL_PLANNING,
                as_of_date=self.as_of,
                evidence=evidence_list,
                limitations=limitations,
                missing_data=missing_data,
            )

        evidence_list.extend(
            [
                CoachEvidence(
                    evidence_id="ev_goals_total_target_amount",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="goal_planning.overview",
                    label="Total target amount across goals",
                    value=overview.total_target_amount,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("1.0"),
                ),
                CoachEvidence(
                    evidence_id="ev_goals_total_remaining_amount",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="goal_planning.overview",
                    label="Total remaining amount across goals",
                    value=overview.total_remaining_amount,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("1.0"),
                ),
            ]
        )

        cap = overview.capacity.conservative_monthly_capacity
        if cap is not None:
            evidence_list.append(
                CoachEvidence(
                    evidence_id="ev_goals_conservative_monthly_capacity",
                    evidence_type=EvidenceType.ESTIMATE,
                    source="goal_planning.capacity",
                    label="Conservative monthly savings capacity",
                    value=cap,
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.85"),
                )
            )

        for idx, g in enumerate(active_goals[:5]):
            evidence_list.append(
                CoachEvidence(
                    evidence_id=f"ev_goal_{g.goal_id}_details",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="goal_planning.overview",
                    label=f"Goal details: {g.name}",
                    value={
                        "goal_id": g.goal_id,
                        "name": g.name,
                        "target_amount": g.target_amount,
                        "remaining_amount": g.remaining_amount,
                        "proposed_monthly": g.proposed_monthly,
                        "feasibility": g.feasibility,
                    },
                    unit="BDT",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.90"),
                )
            )

        return EvidencePackage(
            intent=CoachIntent.GOAL_PLANNING,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
        )

    # -------------------------------------------------------------------------
    # Intent: SCENARIO_COMPARISON
    # -------------------------------------------------------------------------
    def _assemble_scenario_comparison(self, route: IntentRoute, question: str, **kwargs: Any) -> EvidencePackage:
        from app.services.finance.scenario_library import listing

        evidence_list: list[CoachEvidence] = []
        limitations: list[str] = [
            "Scenarios simulate hypothetical changes; no real financial data is modified.",
            "Comparisons assess runway, projected balance, and goal feasibility differences.",
        ]
        missing_data: list[str] = []

        scenarios_page = listing(self.db, self.user_id, status="saved", limit=5)
        scenarios = getattr(scenarios_page, "items", []) if not isinstance(scenarios_page, dict) else scenarios_page.get("items", [])

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_scenario_saved_count",
                evidence_type=EvidenceType.RAW_DATA,
                source="scenario_library.listing",
                label="Saved scenarios count",
                value=len(scenarios),
                unit="count",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        if not scenarios:
            missing_data.append("saved_scenarios")
            limitations.append("No saved scenarios found to compare. Create scenarios in the Scenarios section.")
            return EvidencePackage(
                intent=CoachIntent.SCENARIO_COMPARISON,
                as_of_date=self.as_of,
                evidence=evidence_list,
                limitations=limitations,
                missing_data=missing_data,
            )

        for s in scenarios[:3]:
            evidence_list.append(
                CoachEvidence(
                    evidence_id=f"ev_scenario_{s.id}_summary",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="scenario_library",
                    label=f"Scenario: {s.name}",
                    value={
                        "id": s.id,
                        "name": s.name,
                        "status": s.status,
                        "description": s.description or "",
                    },
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("1.0"),
                )
            )

        return EvidencePackage(
            intent=CoachIntent.SCENARIO_COMPARISON,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
        )

    # -------------------------------------------------------------------------
    # Intent: ALERT_EXPLANATION
    # -------------------------------------------------------------------------
    def _assemble_alert_explanation(self, route: IntentRoute, question: str, **kwargs: Any) -> EvidencePackage:
        from app.services.finance.financial_alerts import list_alerts

        evidence_list: list[CoachEvidence] = []
        limitations: list[str] = [
            "Alerts indicate observable rule thresholds; they do not represent human advice.",
        ]
        missing_data: list[str] = []

        active_alerts, _ = list_alerts(self.db, self.user_id, status="active", limit=5)

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_alerts_active_count",
                evidence_type=EvidenceType.RAW_DATA,
                source="financial_alerts.list_alerts",
                label="Active alerts count",
                value=len(active_alerts),
                unit="count",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        if not active_alerts:
            missing_data.append("active_alerts")
            limitations.append("No active alerts triggered for your account.")
            return EvidencePackage(
                intent=CoachIntent.ALERT_EXPLANATION,
                as_of_date=self.as_of,
                evidence=evidence_list,
                limitations=limitations,
                missing_data=missing_data,
            )

        for a in active_alerts[:3]:
            evidence_list.append(
                CoachEvidence(
                    evidence_id=f"ev_alert_{a.id}_details",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="financial_alerts",
                    label=f"Alert: {a.title}",
                    value={
                        "id": a.id,
                        "alert_type": a.alert_type,
                        "title": a.title,
                        "severity": a.severity,
                        "message": a.message,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    },
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("1.0"),
                )
            )

        return EvidencePackage(
            intent=CoachIntent.ALERT_EXPLANATION,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
        )

    # -------------------------------------------------------------------------
    # Intent: FINANCIAL_HEALTH
    # -------------------------------------------------------------------------
    def _assemble_financial_health(self, route: IntentRoute, question: str, **kwargs: Any) -> EvidencePackage:
        from app.services.finance.financial_health import gather_profile

        evidence_list: list[CoachEvidence] = []
        limitations: list[str] = [
            "Financial health is an internal diagnostic tool; it is not a credit score or regulatory rating.",
        ]
        missing_data: list[str] = []

        profile = gather_profile(self.db, self.user_id, as_of=self.as_of)

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_health_status",
                evidence_type=EvidenceType.INTERPRETATION,
                source="financial_health.gather_profile",
                label="Overall financial health status",
                value=profile.status,
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("0.90"),
            )
        )

        evidence_list.append(
            CoachEvidence(
                evidence_id="ev_health_coverage_percent",
                evidence_type=EvidenceType.DERIVED_FACT,
                source="financial_health.gather_profile",
                label="Financial data coverage percentage",
                value=profile.coverage_percent,
                unit="%",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("1.0"),
            )
        )

        if profile.overall_score is not None:
            evidence_list.append(
                CoachEvidence(
                    evidence_id="ev_health_overall_score",
                    evidence_type=EvidenceType.DERIVED_FACT,
                    source="financial_health.gather_profile",
                    label="Overall financial health score",
                    value=profile.overall_score,
                    unit="points",
                    as_of_date=self.as_of,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.85"),
                )
            )
        else:
            missing_data.append("sufficient_health_data")
            limitations.append("Insufficient data to compute overall health score; at least 3 months history and an account balance are needed.")

        for comp in profile.components:
            if comp.data_available and comp.score is not None:
                evidence_list.append(
                    CoachEvidence(
                        evidence_id=f"ev_health_comp_{comp.key}",
                        evidence_type=EvidenceType.DERIVED_FACT,
                        source="financial_health.component",
                        label=f"Health component: {comp.key}",
                        value={"key": comp.key, "score": comp.score, "status": comp.status},
                        unit="points",
                        as_of_date=self.as_of,
                        observed_at=self.now_utc,
                        confidence=Decimal("0.85"),
                    )
                )

        limitations.extend(profile.limitations)

        return EvidencePackage(
            intent=CoachIntent.FINANCIAL_HEALTH,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
        )

    # -------------------------------------------------------------------------
    # Intent: FINANCIAL_REVIEW
    # -------------------------------------------------------------------------
    def _assemble_financial_review(
        self,
        route: IntentRoute,
        question: str,
        schedules_confirmed: bool = False,
        **kwargs: Any,
    ) -> EvidencePackage:
        """Explain the canonical AI-17B review for this authenticated owner.

        The review service owns dates, priorities, amounts and blockers. This
        assembler only projects that result into the existing evidence contract;
        it does not calculate financial values or accept client evidence.
        """
        from app.services.finance.financial_review import financial_review

        review = financial_review(
            self.db,
            self.user_id,
            as_of=self.as_of,
            schedules_confirmed=schedules_confirmed,
        )
        day = review.decisions.as_of_date
        if day != self.as_of:
            raise ValueError("Review date must match the server-controlled context")
        evidence_list: list[CoachEvidence] = [
            item.model_copy(deep=True) for item in review.decisions.evidence
        ]

        def add(
            evidence_id: str,
            evidence_type: EvidenceType,
            source: str,
            label: str,
            value: Any,
            unit: str | None = None,
        ) -> None:
            evidence_list.append(
                CoachEvidence(
                    evidence_id=evidence_id,
                    evidence_type=evidence_type,
                    source=source,
                    label=label,
                    value=value,
                    unit=unit,
                    as_of_date=day,
                    observed_at=self.now_utc,
                    confidence=Decimal("0.90"),
                )
            )

        add(
            "ev_review_source",
            EvidenceType.INTERPRETATION,
            "financial_review",
            "Canonical review source context",
            {"evidence": [e.model_dump(mode="json") for e in review.decisions.evidence],
             "capacity": review.plan.goal_planning.capacity.model_dump(mode="json") if review.plan.goal_planning else None,
             "schedules_confirmed": review.schedules_confirmed, "data_status": review.plan.data_status},
        )
        add(
            "ev_review_plan",
            EvidenceType.INTERPRETATION,
            "financial_review",
            "Read-only financial plan review",
            {
                "status": review.status,
                "requires_user_confirmation": review.requires_user_confirmation,
                "schedules_confirmed": review.schedules_confirmed,
                "data_status": review.plan.data_status,
                "planner_version": review.plan.planner_version,
            },
        )
        add(
            "ev_review_horizon",
            EvidenceType.INTERPRETATION,
            "financial_review",
            "Review reporting horizon",
            {
                "kind": review.plan.planning_horizon.kind,
                "start": str(review.plan.planning_horizon.start),
                "end": str(review.plan.planning_horizon.end),
                "is_complete": review.plan.planning_horizon.is_complete,
                "label": review.plan.planning_horizon.label,
            },
        )
        add(
            "ev_review_priorities",
            EvidenceType.INTERPRETATION,
            "financial_review",
            "Ordered financial review priorities",
            [item.model_dump(mode="python") for item in review.decisions.priorities],
        )
        add(
            "ev_review_execution_steps",
            EvidenceType.INTERPRETATION,
            "financial_review",
            "Financial review steps and blockers",
            [item.model_dump(mode="python") for item in review.execution_plan.steps],
        )
        add(
            "ev_review_warnings",
            EvidenceType.INTERPRETATION,
            "financial_review",
            "Financial review warnings",
            [item.model_dump(mode="python") for item in review.plan.warnings],
        )
        add(
            "ev_review_limitations",
            EvidenceType.INTERPRETATION,
            "financial_review",
            "Financial review limitations",
            list(review.plan.limitations),
        )

        capacity = (
            review.plan.goal_planning.capacity
            if review.plan.goal_planning is not None
            else None
        )
        missing_data: list[str] = []
        if review.plan.data_status != "sufficient":
            missing_data.append("complete_financial_review")
        if capacity is None:
            missing_data.extend(["planning_capacity", "trusted_cash"])
        else:
            if capacity.conservative_monthly_capacity is None:
                missing_data.append("planning_capacity")
                add(
                    "ev_review_capacity_status",
                    EvidenceType.INTERPRETATION,
                    "goal_planning.capacity",
                    "Planning capacity status",
                    {"status": capacity.status, "capacity_available": False},
                )
            else:
                # Projection of an existing engine value; no new arithmetic.
                add(
                    "ev_review_conservative_monthly_capacity",
                    EvidenceType.ESTIMATE,
                    "goal_planning.capacity",
                    "Estimated conservative monthly savings capacity",
                    capacity.conservative_monthly_capacity,
                    "BDT",
                )
            if capacity.trusted_cash is None:
                missing_data.append("trusted_cash")
                add(
                    "ev_review_trusted_cash_status",
                    EvidenceType.INTERPRETATION,
                    "account_position",
                    "Trusted cash status",
                    {"available": False},
                )
            else:
                add(
                    "ev_review_trusted_cash",
                    EvidenceType.DERIVED_FACT,
                    "account_position",
                    "Trusted cash",
                    capacity.trusted_cash,
                    "BDT",
                )

        limitations = list(
            dict.fromkeys(
                [
                    *review.plan.limitations,
                    *review.decisions.limitations,
                    *review.execution_plan.limitations,
                ]
            )
        )
        return EvidencePackage(
            intent=CoachIntent.FINANCIAL_REVIEW,
            as_of_date=day,
            evidence=evidence_list,
            limitations=limitations,
            missing_data=missing_data,
            period_start=review.plan.planning_horizon.start,
            period_end=review.plan.planning_horizon.end,
            review=review,
        )

    # -------------------------------------------------------------------------
    # Intent: GENERAL_FINANCE
    # -------------------------------------------------------------------------
    def _assemble_general_finance(self, route: IntentRoute, question: str, **kwargs: Any) -> EvidencePackage:
        evidence_list: list[CoachEvidence] = [
            CoachEvidence(
                evidence_id="ev_general_budgeting_rule",
                evidence_type=EvidenceType.INTERPRETATION,
                source="financial_education",
                label="50/30/20 Budgeting guideline",
                value={
                    "needs_percent": 50,
                    "wants_percent": 30,
                    "savings_percent": 20,
                    "description": "A guideline allocating 50% of net income to needs, 30% to wants, and 20% to savings/debt reduction.",
                },
                unit="%",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("0.90"),
            ),
            CoachEvidence(
                evidence_id="ev_general_emergency_fund_guideline",
                evidence_type=EvidenceType.INTERPRETATION,
                source="financial_education",
                label="Emergency fund benchmark in Bangladesh",
                value={
                    "recommended_months_min": 3,
                    "recommended_months_max": 6,
                    "description": "Keeping 3 to 6 months of essential living expenses in a liquid BDT account or savings vehicle.",
                },
                unit="months",
                as_of_date=self.as_of,
                observed_at=self.now_utc,
                confidence=Decimal("0.90"),
            ),
        ]

        return EvidencePackage(
            intent=CoachIntent.GENERAL_FINANCE,
            as_of_date=self.as_of,
            evidence=evidence_list,
            limitations=[
                "General financial education is not tailored personal advice and does not alter your financial records.",
            ],
            missing_data=[],
        )


def assemble_financial_evidence(
    db: Session,
    user_id: int,
    route: IntentRoute,
    question: str,
    as_of: date | None = None,
    explicit_start_date: date | None = None,
    explicit_end_date: date | None = None,
    purchase_amount: Decimal | None = None,
    starting_balance: Decimal | None = None,
    schedules_confirmed: bool = False,
) -> EvidencePackage:
    """Convenience functional interface for deterministic evidence assembly."""
    assembler = FinancialCoachEvidenceAssembler(db, user_id, as_of)
    return assembler.assemble(
        route=route,
        question=question,
        explicit_start_date=explicit_start_date,
        explicit_end_date=explicit_end_date,
        purchase_amount=purchase_amount,
        starting_balance=starting_balance,
        schedules_confirmed=schedules_confirmed,
    )
