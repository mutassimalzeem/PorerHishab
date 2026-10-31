import type { ApiSchemas } from "../generated/api";
import { coachingFixture } from "./coaching.fixture";
export const actionPlanFixture: ApiSchemas["CoachingActionPlan"] = {
  as_of_date: coachingFixture.as_of_date,
  data_status: coachingFixture.data_status,
  actions: coachingFixture.recommendations.map((item, index) => ({
    id: item.id,
    recommendation_id: item.id,
    type: item.type,
    priority: item.priority,
    rank: index + 1,
    title: item.title,
    description: item.description,
    recommended_action: item.recommended_action,
    amount: item.amount,
    currency: item.currency ?? "BDT",
    status: "active",
    source: item.source,
    evidence_quality: item.evidence_quality,
    subject: item.subject ?? null,
    assumptions: item.assumptions,
    limitations: item.limitations,
  })),
  completed_feedback: [],
  active_count: coachingFixture.recommendations.length,
  completed_count: 0,
  assumptions: [],
  limitations: [],
};
export const emptyActionPlan: ApiSchemas["CoachingActionPlan"] = {
  ...actionPlanFixture,
  actions: [],
  active_count: 0,
};
