import { useCallback } from "react";
import { Link } from "react-router-dom";
import type { ApiSchemas } from "../generated/api";
import { api } from "../lib/api";
import { date } from "../lib/format";
import { digits, t, uiLabel } from "../lib/locale";
import { useLanguage } from "../lib/useLanguage";
import { useResource } from "../lib/useResource";
import { Amount, Empty, Notes, ResourceView, Section } from "./ui";

type Outcome = ApiSchemas["ActionOutcome"];
type OutcomeWindow = ApiSchemas["OutcomeWindow"];

const statusLabels = {
  improved: "Improved",
  unchanged: "Unchanged",
  worsened: "Worsened",
  pending: "Pending observation",
  insufficient_data: "Insufficient evidence",
} as const;

const qualityLabels = {
  recorded: "Recorded evidence",
  estimated: "Estimated evidence",
  limited: "Limited evidence",
} as const;

const settlementLabels = {
  not_settled: "Not settled",
  partially_settled: "Partially settled",
  fully_settled: "Fully settled",
} as const;

const typeTitles = {
  cash_risk: "Prepare for a possible cash shortfall",
  upcoming_obligations: "Prepare for remaining commitments",
  spending_spike: "Review a category spending increase",
  repeated_spending: "Review a repeated category increase",
  savings_opportunity: "Consider an unassigned savings reserve",
  goal_risk: "Review a savings goal at risk",
} as const;

const metricLabels = {
  category_spending: "Category spending",
  recorded_net_cashflow: "Recorded net cashflow",
  minimum_projected_balance: "Lowest projected balance",
  obligation_remaining: "Remaining obligation",
  goal_saved_amount: "Goal savings",
  unsupported: "Unsupported comparison",
} as const;

const interpretations = {
  decreased: "Recorded value decreased compared with the baseline.",
  increased: "Recorded value increased compared with the baseline.",
  unchanged: "Recorded value is unchanged compared with the baseline.",
  pending: "More follow-up time is needed before comparing evidence.",
  insufficient_data: "There is not enough comparable evidence yet.",
  obligation_settled:
    "The obligation is fully reconciled at the observation date.",
  obligation_partially_settled:
    "The obligation is partially reconciled at the observation date.",
  obligation_not_settled:
    "No confirmed settlement is recorded at the observation date.",
  goal_history_unavailable:
    "Historical goal contributions are unavailable for comparison.",
} as const;

function limitationLabel(value: string) {
  if (
    value.startsWith("Only ") &&
    value.endsWith(" elapsed day(s) are available.")
  ) {
    return t("More follow-up time is needed before comparing evidence.");
  }
  return uiLabel(value);
}

const destinations = {
  cash_risk: "/cashflow",
  upcoming_obligations: "/cashflow",
  savings_opportunity: "/plans",
  goal_risk: "/plans",
  spending_spike: "/transactions",
  repeated_spending: "/transactions",
} as const;

function Window({ label, value }: { label: string; value: OutcomeWindow }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {value.days
          ? `${date(value.start)} ${t("to")} ${date(value.end)}`
          : t("Not enough elapsed time")}{" "}
        {value.days > 0 && (
          <small>
            ({digits(value.days)} {t("days")}
            {value.is_complete ? "" : `, ${t("still open")}`})
          </small>
        )}
      </dd>
    </div>
  );
}

function OutcomeEvidence({ item }: { item: Outcome }) {
  const evidence = item.evidence;
  const obligations = evidence.obligations ?? [];
  return (
    <details className="notes outcome-evidence">
      <summary>{t("Outcome evidence")}</summary>
      <dl className="evidence-grid">
        <div>
          <dt>{t("Currency")}</dt>
          <dd>{evidence.currency ?? "BDT"}</dd>
        </div>
        <div>
          <dt>{t("Metric")}</dt>
          <dd>{t(metricLabels[item.metric])}</dd>
        </div>
        <div>
          <dt>{t("Evidence quality")}</dt>
          <dd>{t(qualityLabels[item.evidence_quality])}</dd>
        </div>
        <div>
          <dt>{t("Causal claim")}</dt>
          <dd>{item.causal_claim ? t("Yes") : t("No")}</dd>
        </div>
        {evidence.category && (
          <div>
            <dt>{t("Category")}</dt>
            <dd>{uiLabel(evidence.category)}</dd>
          </div>
        )}
        {evidence.baseline_transaction_count != null && (
          <div>
            <dt>{t("Baseline transaction count")}</dt>
            <dd>{digits(evidence.baseline_transaction_count)}</dd>
          </div>
        )}
        {evidence.follow_up_transaction_count != null && (
          <div>
            <dt>{t("Follow-up transaction count")}</dt>
            <dd>{digits(evidence.follow_up_transaction_count)}</dd>
          </div>
        )}
        {evidence.baseline_runway_status && (
          <div>
            <dt>{t("Baseline runway status")}</dt>
            <dd>{uiLabel(evidence.baseline_runway_status)}</dd>
          </div>
        )}
        {evidence.follow_up_runway_status && (
          <div>
            <dt>{t("Follow-up runway status")}</dt>
            <dd>{uiLabel(evidence.follow_up_runway_status)}</dd>
          </div>
        )}
      </dl>
      {obligations.length > 0 && (
        <ul className="outcome-obligations">
          {obligations.map((row) => (
            <li key={row.item_id}>
              <strong>{row.title}</strong> &middot; {date(row.due_date)}
              <p>
                {t("Scheduled")}: <Amount value={row.original_amount} />{" "}
                &middot; {t("Allocated")}:{" "}
                <Amount value={row.allocated_amount} /> &middot;{" "}
                {t("Remaining")}: <Amount value={row.remaining_amount} />
              </p>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

function OutcomeCard({ item }: { item: Outcome }) {
  const spending =
    item.recommendation_type === "spending_spike" ||
    item.recommendation_type === "repeated_spending";
  return (
    <article className={`outcome-card outcome-${item.status}`}>
      <p className="context">
        <strong>{t(statusLabels[item.status])}</strong> &middot;{" "}
        {t(qualityLabels[item.evidence_quality])}
      </p>
      <h3>{t(typeTitles[item.recommendation_type])}</h3>
      {item.subject && (
        <p>
          <strong>{spending ? uiLabel(item.subject) : item.subject}</strong>
        </p>
      )}
      <p className="source">
        {t("Reported acted on")}: {date(item.action_reported_on)}
      </p>
      <dl className="goal-numbers">
        <Window label={t("Baseline window")} value={item.baseline} />
        <Window label={t("Follow-up window")} value={item.follow_up} />
      </dl>
      <dl className="goal-numbers">
        <div>
          <dt>{t("Baseline")}</dt>
          <dd>
            <Amount value={item.baseline_value} />
          </dd>
        </div>
        <div>
          <dt>{t("Follow-up")}</dt>
          <dd>
            <Amount value={item.follow_up_value} />
          </dd>
        </div>
        <div>
          <dt>{t("Change")}</dt>
          <dd>
            <Amount value={item.absolute_change} />
            {item.percentage_change != null && (
              <small> ({digits(item.percentage_change)}%)</small>
            )}
          </dd>
        </div>
      </dl>
      {item.settlement_status && (
        <p>
          <strong>{t("Settlement status")}</strong>:{" "}
          {t(settlementLabels[item.settlement_status])}
        </p>
      )}
      <p>
        <strong>{t("Observation")}</strong>:{" "}
        {t(interpretations[item.interpretation])}
      </p>
      <OutcomeEvidence item={item} />
      <Notes limitations={item.limitations.map(limitationLabel)} />
      <Link to={destinations[item.recommendation_type]}>
        {t("Review related records")}
      </Link>
    </article>
  );
}

export function ActionOutcomes({ revision = 0 }: { revision?: number }) {
  useLanguage();
  const resource = useResource(
    useCallback(() => api.actionOutcomes(), []),
    revision,
  );
  return (
    <Section title={t("What changed after reported actions")}>
      <p className="source">
        {t(
          "Outcome observations compare recorded evidence before and after you reported acting. They do not prove that an action caused a change.",
        )}
      </p>
      <ResourceView
        resource={resource}
        label={t("Reading reported action outcomes...")}
      >
        {(report) => (
          <>
            <dl className="outcome-summary">
              <div>
                <dt>{t("Tracked outcomes")}</dt>
                <dd>{digits(report.summary.tracked)}</dd>
              </div>
              {(
                [
                  ["improved", report.summary.improved],
                  ["unchanged", report.summary.unchanged],
                  ["worsened", report.summary.worsened],
                  ["pending", report.summary.pending],
                  ["insufficient_data", report.summary.insufficient_data],
                ] as const
              ).map(([status, value]) => (
                <div key={status}>
                  <dt>{t(statusLabels[status])}</dt>
                  <dd>{digits(value)}</dd>
                </div>
              ))}
            </dl>
            {report.items.length ? (
              <ul
                className="outcome-list"
                aria-label={t("Reported action outcomes")}
              >
                {report.items.map((item) => (
                  <li key={item.recommendation_id}>
                    <OutcomeCard item={item} />
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title={t("No reported action outcomes yet.")}>
                {t(
                  "Mark a coaching recommendation as done, then return after at least seven days for a comparable observation.",
                )}{" "}
                {t(
                  "No outcome is not a failed action; insufficient evidence means no comparison is possible.",
                )}
              </Empty>
            )}
            <Notes limitations={report.limitations.map(limitationLabel)} />
          </>
        )}
      </ResourceView>
    </Section>
  );
}
