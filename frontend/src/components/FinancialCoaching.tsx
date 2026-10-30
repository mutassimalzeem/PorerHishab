import { useId, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiSchemas } from "../generated/api";
import { api } from "../lib/api";
import { date, errorMessage } from "../lib/format";
import { digits, t, uiLabel } from "../lib/locale";
import { useLanguage } from "../lib/useLanguage";
import { Amount, Empty, ErrorNotice, Notes, Section } from "./ui";

type Recommendation = ApiSchemas["CoachingRecommendation"];
type Evidence = ApiSchemas["CoachingEvidence"];
const priorities = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
} as const;
const qualities = {
  recorded: "Recorded evidence",
  estimated: "Estimated evidence",
  limited: "Limited evidence",
} as const;
const moneyFields = {
  starting_balance: "Account starting cash",
  scheduled_expense_reserve: "Remaining commitments",
  uncertain_income: "Uncertain scheduled income",
  minimum_projected_balance: "Lowest projected balance",
  projected_end_balance: "Projected ending cash",
  cash_after_known_obligations: "Cash after known commitments",
  safety_threshold: "Safety threshold",
  observed_value: "Observed category spending",
  reference_value: "Comparison category spending",
  current_saved: "Current savings",
  target_amount: "Target amount",
  remaining_amount: "Remaining",
  required_monthly: "Required monthly contribution",
  estimated_monthly_capacity: "Estimated monthly capacity",
} as const;
function CoachingEvidence({ evidence }: { evidence: Evidence }) {
  return (
    <details className="notes">
      <summary>{t("Why this recommendation?")}</summary>
      <p>
        {t("Evidence period")}: {date(evidence.period.start)} {t("to")}{" "}
        {date(evidence.period.end)}
      </p>
      {evidence.comparison_period && (
        <p>
          {t("Comparison period")}: {date(evidence.comparison_period.start)}{" "}
          {t("to")} {date(evidence.comparison_period.end)}
        </p>
      )}
      {evidence.balance_source && (
        <p>
          {t("Balance source")}: {uiLabel(evidence.balance_source)}
        </p>
      )}
      {evidence.runway_status && (
        <p>
          {t("Runway status")}: {uiLabel(evidence.runway_status)}
        </p>
      )}
      {evidence.runway_mode && (
        <p>
          {t("Scenario")}:{" "}
          <span>
            {evidence.runway_mode === "known_obligations"
              ? t("Known obligations only")
              : t("Historical scenario")}
          </span>
        </p>
      )}
      <dl className="evidence-grid">
        {Object.entries(moneyFields).map(([key, label]) => {
          const value = evidence[key as keyof typeof moneyFields];
          return value == null ? null : (
            <div key={key}>
              <dt>{t(label)}</dt>
              <dd>
                <Amount value={value} />
              </dd>
            </div>
          );
        })}
        {evidence.percentage_change != null && (
          <div>
            <dt>{t("Percentage change")}</dt>
            <dd>{digits(evidence.percentage_change)}%</dd>
          </div>
        )}
      </dl>
      {evidence.first_shortfall_date && (
        <p>
          {t("Known-obligations shortfall date")}:{" "}
          {date(evidence.first_shortfall_date)}
        </p>
      )}
      {evidence.first_shortfall_period && (
        <p>
          {t("Estimated shortfall window")}:{" "}
          {date(evidence.first_shortfall_period.start)} {t("to")}{" "}
          {date(evidence.first_shortfall_period.end)}
        </p>
      )}
      {evidence.target_date && (
        <p>
          {t("Target date")}: {date(evidence.target_date)}
        </p>
      )}
      {(evidence.obligations?.length ?? 0) > 0 && (
        <ul className="coaching-obligations">
          {evidence.obligations!.map((item) => (
            <li key={item.item_id}>
              <strong>{item.title}</strong> &middot; {date(item.due_date)}
              <p>
                {t("Scheduled")}: <Amount value={item.original_amount} />{" "}
                &middot; {t("Allocated")}:{" "}
                <Amount value={item.allocated_amount} /> &middot;{" "}
                {t("Remaining")}: <Amount value={item.remaining_amount} />
              </p>
            </li>
          ))}
        </ul>
      )}
      {(evidence.monthly_values?.length ?? 0) > 0 && (
        <ul>
          {evidence.monthly_values!.map((row) => (
            <li key={row.period.start}>
              {date(row.period.start)} {t("to")} {date(row.period.end)}:{" "}
              <Amount value={row.amount} />
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
type FeedbackStatus = ApiSchemas["CoachingFeedbackInput"]["status"];
const feedbackLabels = {
  acted_on: "Mark as done",
  dismissed: "Dismiss",
  not_relevant: "Not relevant",
  snoozed: "Snooze",
} as const;
const recordedLabels = {
  acted_on: "Reported done",
  dismissed: "Dismissed",
  not_relevant: "Not relevant",
  snoozed: "Snoozed",
} as const;
function FeedbackControls({
  id,
  refresh,
  restore = false,
}: {
  id: string;
  refresh: () => Promise<void>;
  restore?: boolean;
}) {
  const dateId = useId();
  const [busy, setBusy] = useState(false);
  const [snooze, setSnooze] = useState(false);
  const [until, setUntil] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState<FeedbackStatus | "restore" | null>(null);
  async function update(status: FeedbackStatus | "restore") {
    setBusy(true);
    setError(null);
    setRetry(status);
    try {
      if (status === "restore") await api.restoreCoaching(id);
      else
        await api.coachingFeedback(id, {
          status,
          snoozed_until: status === "snoozed" ? until : null,
        });
      await refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Dhaka",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const limit = (days: number) =>
    new Date(Date.parse(today + "T00:00:00Z") + days * 86400000)
      .toISOString()
      .slice(0, 10);
  return (
    <div className="coaching-feedback" aria-busy={busy}>
      <div className="coaching-feedback-actions">
        {restore ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => update("restore")}
          >
            {t("Restore recommendation")}
          </button>
        ) : (
          <>
            {(["acted_on", "dismissed", "not_relevant"] as const).map(
              (status) => (
                <button
                  key={status}
                  type="button"
                  disabled={busy}
                  onClick={() => update(status)}
                >
                  {t(feedbackLabels[status])}
                </button>
              ),
            )}
            <button
              type="button"
              disabled={busy}
              aria-expanded={snooze}
              onClick={() => setSnooze(!snooze)}
            >
              {t("Snooze")}
            </button>
          </>
        )}
      </div>
      {snooze && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void update("snoozed");
          }}
        >
          <label htmlFor={dateId}>{t("Snooze until")}</label>
          <input
            id={dateId}
            type="date"
            required
            min={limit(1)}
            max={limit(90)}
            value={until}
            disabled={busy}
            onChange={(event) => setUntil(event.target.value)}
          />
          <button type="submit" disabled={busy}>
            {t("Save snooze")}
          </button>
        </form>
      )}
      {busy && <p role="status">{t("Saving feedback...")}</p>}
      {error && (
        <>
          <ErrorNotice message={error} />
          <button
            type="button"
            disabled={busy}
            onClick={() => retry && update(retry)}
          >
            {t("Retry feedback")}
          </button>
        </>
      )}
    </div>
  );
}
function Advice({
  item,
  refresh,
}: {
  item: Recommendation;
  refresh: () => Promise<void>;
}) {
  const to =
    item.type === "goal_risk" || item.type === "savings_opportunity"
      ? "/plans"
      : item.type === "spending_spike" || item.type === "repeated_spending"
        ? "/transactions"
        : "/cashflow";
  return (
    <article className={`coaching-card coaching-${item.priority}`}>
      <p className="context">
        <strong>{t(priorities[item.priority])}</strong> &middot;{" "}
        {t(qualities[item.evidence_quality])}
      </p>
      <h3>{uiLabel(item.title)}</h3>
      {item.subject && (
        <p>
          <strong>
            {item.type === "spending_spike" || item.type === "repeated_spending"
              ? uiLabel(item.subject)
              : item.subject}
          </strong>
        </p>
      )}
      <p>{uiLabel(item.description)}</p>
      {item.amount !== null && (
        <p>
          <Amount value={item.amount} />
        </p>
      )}
      <p>
        <strong>{t("Recommended action")}</strong>:{" "}
        <span>{uiLabel(item.recommended_action)}</span>
      </p>
      <p className="source">
        {t("Review by")}: {date(item.valid_until)} &middot; {t("Source")}:{" "}
        {uiLabel(item.source)}
      </p>
      <CoachingEvidence evidence={item.evidence} />
      <Notes
        assumptions={item.assumptions.map(uiLabel)}
        limitations={item.limitations.map(uiLabel)}
      />
      <Link to={to}>{t("Review related records")}</Link>
      <FeedbackControls id={item.id} refresh={refresh} />
    </article>
  );
}
export function FinancialCoaching() {
  useLanguage();
  const [result, setResult] = useState<ApiSchemas["FinancialCoaching"] | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function refresh() {
    setNotice(false);
    setResult(await api.coaching());
    setNotice(true);
  }
  async function load() {
    setResult(null);
    setNotice(false);
    setError(null);
    setBusy(true);
    try {
      setResult(await api.coaching());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Section title={t("Financial alerts & coaching")}>
      <p className="source">
        {t("Evidence-backed reviews, with no automatic financial actions.")}
      </p>
      <button type="button" disabled={busy} onClick={load}>
        {result ? t("Refresh coaching") : t("Review financial coaching")}
      </button>
      {busy && <p role="status">{t("Reading financial coaching...")}</p>}
      {error && <ErrorNotice message={error} />}
      {notice && (
        <p role="status">
          {t("Feedback saved. Financial records are unchanged.")}
        </p>
      )}
      {result && (
        <>
          <p className="source">
            {date(result.as_of_date)} &middot; {date(result.period.start)}{" "}
            {t("to")} {date(result.period.end)}
          </p>
          {result.data_status !== "sufficient" && (
            <p className="coaching-data-note">
              {t(
                "Some financial inputs are unavailable. Existing alerts may still be useful; missing alerts do not establish safety.",
              )}
            </p>
          )}
          {result.recommendations.length ? (
            <div className="coaching-list">
              {result.recommendations.map((item) => (
                <Advice key={item.id} item={item} refresh={refresh} />
              ))}
            </div>
          ) : (
            <Empty
              title={
                result.data_status === "insufficient_data"
                  ? t("More financial evidence is needed")
                  : t("No actionable coaching right now")
              }
            >
              {t(
                "Review account cash, transaction coverage and upcoming commitments before drawing conclusions.",
              )}
            </Empty>
          )}
          <details className="notes coaching-history">
            <summary>{t("Coaching feedback history")}</summary>
            <p>
              {t(
                "Feedback records your report and does not verify a financial action.",
              )}
            </p>
            {(result.feedback ?? []).length ? (
              <ul>
                {result.feedback!.map((record) => (
                  <li key={record.recommendation_id}>
                    <p>
                      <strong>{t(recordedLabels[record.status])}</strong>{" "}
                      &middot; {date(record.updated_at.slice(0, 10))}
                    </p>
                    <p>
                      {uiLabel(
                        (
                          {
                            cash_risk: "Prepare for a possible cash shortfall",
                            upcoming_obligations:
                              "Prepare for remaining commitments",
                            spending_spike:
                              "Review a category spending increase",
                            repeated_spending:
                              "Review a repeated category increase",
                            savings_opportunity:
                              "Consider an unassigned savings reserve",
                            goal_risk: "Review a savings goal at risk",
                          } as Record<string, string>
                        )[record.recommendation_id.split(":")[0]] ??
                          "Recommended action",
                      )}
                    </p>
                    {record.snoozed_until && (
                      <p>
                        {t("Snooze until")}: {date(record.snoozed_until)}
                      </p>
                    )}
                    {!record.is_current && (
                      <p>
                        {t(
                          "This recommendation has changed or is no longer current.",
                        )}
                      </p>
                    )}
                    {record.status === "snoozed" &&
                      record.is_current &&
                      !record.is_hidden && <p>{t("Snooze expired")}</p>}
                    <FeedbackControls
                      id={record.recommendation_id}
                      refresh={refresh}
                      restore
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <p>{t("No coaching feedback yet.")}</p>
            )}
          </details>
          <Notes limitations={result.limitations.map(uiLabel)} />
        </>
      )}
    </Section>
  );
}
