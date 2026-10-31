import type { ApiSchemas } from "../generated/api";
export const effectivenessFixture: ApiSchemas["CoachingEffectivenessResponse"] =
  {
    counts: {
      total_recommendations: 7,
      acted_on: 4,
      dismissed: 1,
      not_relevant: 1,
      snoozed: 1,
      measurable_outcomes: 3,
      improved: 1,
      unchanged: 2,
      worsened: 0,
      insufficient_data: 1,
    },
    rates: {
      observable_outcome_rate: "75.00",
      improvement_rate_among_observed: "33.33",
      worsening_rate_among_observed: "0.00",
    },
    by_type: [
      {
        recommendation_type: "spending_spike",
        total_recommendations: 7,
        acted_on: 4,
        measurable_outcomes: 3,
        improved: 1,
        unchanged: 2,
        worsened: 0,
        insufficient_data: 1,
        observable_outcome_rate: "75.00",
        improvement_rate_among_observed: "33.33",
        worsening_rate_among_observed: "0.00",
      },
    ],
    causal_claim: false,
    limitations: [
      "Outcomes are observational and do not establish causation.",
      "Action completion is based on user-reported feedback.",
    ],
  };
export const emptyEffectiveness: ApiSchemas["CoachingEffectivenessResponse"] = {
  counts: {
    total_recommendations: 0,
    acted_on: 0,
    dismissed: 0,
    not_relevant: 0,
    snoozed: 0,
    measurable_outcomes: 0,
    improved: 0,
    unchanged: 0,
    worsened: 0,
    insufficient_data: 0,
  },
  rates: {
    observable_outcome_rate: null,
    improvement_rate_among_observed: null,
    worsening_rate_among_observed: null,
  },
  by_type: [],
  causal_claim: false,
  limitations: effectivenessFixture.limitations,
};
