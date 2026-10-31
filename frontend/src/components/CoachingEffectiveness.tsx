import { useCallback } from "react";
import type { ApiSchemas } from "../generated/api";
import { api } from "../lib/api";
import { digits, t, uiLabel } from "../lib/locale";
import { useLanguage } from "../lib/useLanguage";
import { useResource } from "../lib/useResource";
import { Empty, Notes, ResourceView, Section } from "./ui";
import "./coaching-effectiveness.css";

type Counts = ApiSchemas["CoachingEffectivenessCounts"];
type Rates = ApiSchemas["CoachingEffectivenessRates"];
const countLabels = {
  total_recommendations: "Recommendations with feedback",
  acted_on: "Reported acted on",
  dismissed: "Dismissed",
  not_relevant: "Not relevant",
  snoozed: "Snoozed",
  measurable_outcomes: "Measurable outcomes",
  improved: "Improved",
  unchanged: "Unchanged",
  worsened: "Worsened",
  insufficient_data: "Insufficient-data outcomes",
} as const;
const rateLabels = {
  observable_outcome_rate: "Observable outcome rate",
  improvement_rate_among_observed: "Improvement rate among observed",
  worsening_rate_among_observed: "Worsening rate among observed",
} as const;
const rateDescriptions = {
  observable_outcome_rate:
    "Measurable outcomes out of reported acted-on recommendations.",
  improvement_rate_among_observed:
    "Improved outcomes out of measurable outcomes.",
  worsening_rate_among_observed:
    "Worsened outcomes out of measurable outcomes.",
} as const;
const typeLabels = {
  cash_risk: "Prepare for a possible cash shortfall",
  upcoming_obligations: "Prepare for remaining commitments",
  spending_spike: "Review a category spending increase",
  repeated_spending: "Review a repeated category increase",
  savings_opportunity: "Consider an unassigned savings reserve",
  goal_risk: "Review a savings goal at risk",
} as const;

// Accept the schema default and an explicitly non-causal response alike.
function isNonCausal(value: boolean | undefined) {
  return value !== true;
}

function CountMetrics({ counts }: { counts: Partial<Counts> }) {
  return (
    <dl className="effectiveness-counts">
      {(Object.keys(countLabels) as (keyof Counts)[]).map((key) =>
        counts[key] == null ? null : (
          <div key={key}>
            <dt>{t(countLabels[key])}</dt>
            <dd>{digits(counts[key])}</dd>
          </div>
        ),
      )}
    </dl>
  );
}
function RateMetrics({
  rates,
  explain = false,
}: {
  rates: Rates;
  explain?: boolean;
}) {
  return (
    <dl className="effectiveness-rates">
      {(Object.keys(rateLabels) as (keyof Rates)[]).map((key) => (
        <div key={key}>
          <dt>{t(rateLabels[key])}</dt>
          <dd>
            {rates[key] == null
              ? t("Not enough data")
              : `${digits(rates[key])}%`}
          </dd>
          {explain && <dd className="source">{t(rateDescriptions[key])}</dd>}
        </div>
      ))}
    </dl>
  );
}

export function CoachingEffectiveness({ revision = 0 }: { revision?: number }) {
  useLanguage();
  const resource = useResource(
    useCallback(() => api.coachingEffectiveness(), []),
    revision,
  );
  return (
    <Section title={t("Coaching effectiveness")}>
      <div className="coaching-effectiveness">
        <p className="source">
          {t(
            "A summary of your reported coaching feedback and observable outcomes.",
          )}
        </p>
        <ResourceView
          resource={{
            ...resource,
            error: resource.error
              ? t("Could not load coaching effectiveness. Please try again.")
              : null,
          }}
          label={t("Reading coaching effectiveness...")}
        >
          {(report) => (
            <>
              {isNonCausal(report.causal_claim) && (
                <p className="source">
                  {t(
                    "Observed changes do not prove that coaching caused them. Acting on a recommendation is self-reported.",
                  )}
                </p>
              )}
              {report.counts.total_recommendations === 0 ? (
                <Empty title={t("No coaching feedback yet.")}>
                  {t(
                    "Effectiveness will appear after you give feedback on coaching recommendations. No outcomes are assumed.",
                  )}
                </Empty>
              ) : (
                <>
                  <CountMetrics counts={report.counts} />
                  <h3>{t("Effectiveness rates")}</h3>
                  <RateMetrics rates={report.rates} explain />
                </>
              )}
              <h3>{t("By recommendation type")}</h3>
              {report.by_type.length ? (
                <ul
                  className="effectiveness-types"
                  aria-label={t("By recommendation type")}
                >
                  {report.by_type.map((item) => (
                    <li key={item.recommendation_type}>
                      <h4>{t(typeLabels[item.recommendation_type])}</h4>
                      <CountMetrics counts={item} />
                      <RateMetrics rates={item} />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="source">
                  {t("No recommendation-type breakdown yet.")}
                </p>
              )}
              <Notes limitations={report.limitations.map(uiLabel)} />
            </>
          )}
        </ResourceView>
      </div>
    </Section>
  );
}
