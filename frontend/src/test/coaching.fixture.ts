import type { ApiSchemas } from "../generated/api";
const period: ApiSchemas["IntelligencePeriod"] = {
  kind: "coaching_horizon",
  start: "2026-11-01",
  end: "2026-12-01",
  is_complete: false,
  label: "next 30 days inclusive",
};
const cashRisk: ApiSchemas["CoachingRecommendation"] = {
  id: "cash_risk:2026-11-01:2026-12-01",
  type: "cash_risk",
  priority: "critical",
  title: "Prepare for a possible cash shortfall",
  description:
    "The existing cashflow scenario reaches or crosses your safety threshold.",
  recommended_action:
    "Review upcoming commitments and postpone optional spending until the gap is covered.",
  currency: "BDT",
  amount: null,
  as_of_date: "2026-11-01",
  valid_until: "2026-12-01",
  subject: null,
  evidence_quality: "limited",
  source: "financial_runway",
  source_id: "2026-11-01:2026-12-01",
  evidence: {
    period,
    starting_balance: "1000.00",
    balance_source: "derived",
    scheduled_expense_reserve: "2000.00",
    uncertain_income: "50000.00",
    minimum_projected_balance: "-1000.00",
    cash_after_known_obligations: "-1000.00",
    projected_end_balance: "-1000.00",
    safety_threshold: "0.00",
    runway_status: "cash_shortfall",
    runway_mode: "known_obligations",
    first_shortfall_date: "2026-11-03",
  },
  assumptions: [
    "Safety thresholds are caller-selected floors, not personalized recommendations.",
  ],
  limitations: [
    "Scheduled income is uncertain and is excluded from available cash and recommendation amounts.",
  ],
};
export const coachingFixture: ApiSchemas["FinancialCoaching"] = {
  as_of_date: "2026-11-01",
  period,
  data_status: "partial",
  recommendations: [
    cashRisk,
    {
      ...cashRisk,
      id: "upcoming_obligations:1",
      type: "upcoming_obligations",
      priority: "high",
      source: "scheduled_cashflow",
      source_id: "1",
      title: "Prepare for remaining commitments",
      description:
        "These obligations are due soon or are large relative to established account cash.",
      recommended_action:
        "Review the remaining amounts and due dates before reserving money or confirming a payment.",
      amount: "2000.00",
      valid_until: "2026-11-03",
      evidence_quality: "recorded",
      evidence: {
        period,
        obligations: [
          {
            item_id: 1,
            title: "Rent installment",
            due_date: "2026-11-03",
            original_amount: "15000.00",
            allocated_amount: "13000.00",
            remaining_amount: "2000.00",
            timeline_event_id: "obligation:1",
          },
        ],
      },
    },
  ],
  limitations: [
    "Recorded history may be incomplete; complete-month coverage does not prove all transactions were imported.",
  ],
};
export const emptyCoaching: ApiSchemas["FinancialCoaching"] = {
  ...coachingFixture,
  data_status: "sufficient",
  recommendations: [],
  limitations: [],
};
