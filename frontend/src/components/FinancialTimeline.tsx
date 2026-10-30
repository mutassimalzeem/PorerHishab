import { useState } from "react";
import type { ApiSchemas } from "../generated/api";
import { api } from "../lib/api";
import { date, errorMessage } from "../lib/format";
import { digits, t, uiLabel } from "../lib/locale";
import { useLanguage } from "../lib/useLanguage";
import { Amount, Empty, ErrorNotice, Notes, Section } from "./ui";

type Timeline = ApiSchemas["FinancialTimeline"];
type Event = ApiSchemas["TimelineEvent"];
const eventLabels = {
  transaction: "Transaction",
  obligation: "Obligation",
  obligation_payment: "Confirmed payment",
  forecast_expense: "Forecast expense",
  forecast_income: "Forecast income",
  runway_checkpoint: "Runway checkpoint",
} as const;
const certaintyLabels = {
  actual: "Actual",
  confirmed: "Confirmed",
  scheduled: "Scheduled",
  estimated: "Estimated",
  uncertain: "Uncertain",
} as const;
const scopeLabels = {
  actual_history: "Historical movement",
  future_projection: "Future scenario",
  context: "Context only",
} as const;
function EventAmount({
  value,
  currency,
}: {
  value: string | null;
  currency: string;
}) {
  return currency === "BDT" ? (
    <Amount value={value} />
  ) : (
    <span className="amount">
      {value === null ? t("Not available") : digits(value)} {currency}
    </span>
  );
}
function TimelineRow({ event }: { event: Event }) {
  return (
    <li className="timeline-event" data-certainty={event.certainty}>
      <div className="timeline-event-heading">
        <time dateTime={event.date}>{date(event.date)}</time>
        <span className="timeline-certainty">
          {t(certaintyLabels[event.certainty])}
        </span>
      </div>
      <h3>{event.title || t(eventLabels[event.event_type])}</h3>
      <p className="source">
        {t(eventLabels[event.event_type])} &middot;{" "}
        {t(scopeLabels[event.impact_scope])}
      </p>
      {event.description && event.description !== event.title && (
        <p>{event.description}</p>
      )}
      <dl className="timeline-amounts">
        <div>
          <dt>{t("Amount")}</dt>
          <dd>
            <EventAmount value={event.amount} currency={event.currency} />
          </dd>
        </div>
        <div>
          <dt>{t("Cash impact")}</dt>
          <dd>
            {event.cash_impacting ? (
              <EventAmount
                value={event.balance_impact}
                currency={event.currency}
              />
            ) : (
              t("Context only")
            )}
          </dd>
        </div>
      </dl>
      {event.original_amount != null && (
        <p className="source">
          {t("Scheduled")}: <Amount value={event.original_amount} /> &middot;{" "}
          {t("Allocated")}: <Amount value={event.allocated_amount} /> &middot;{" "}
          {t("Remaining")}: <Amount value={event.remaining_amount} />
        </p>
      )}
      {event.evidence.period && (
        <p className="source">
          {t("Estimated period")}: {date(event.evidence.period.start)} {t("to")}{" "}
          {date(event.evidence.period.end)}
        </p>
      )}
      <small>
        {t("Source")}: {uiLabel(event.source)} {digits(event.source_id)}
        {event.evidence.transaction_id != null &&
          event.event_type === "obligation_payment" && (
            <>
              {" "}
              &middot; {t("Transaction")}{" "}
              {digits(event.evidence.transaction_id)}
            </>
          )}
      </small>
    </li>
  );
}
export function FinancialTimeline() {
  useLanguage();
  const [result, setResult] = useState<Timeline | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(20);
  async function load() {
    setBusy(true);
    setResult(null);
    setError(null);
    setVisible(20);
    try {
      setResult(await api.timeline());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Section title={t("Financial timeline")}>
      <p className="source">
        {t(
          "Recorded history, remaining commitments and estimates stay separate.",
        )}
      </p>
      <button type="button" disabled={busy} onClick={load}>
        {result ? t("Refresh timeline") : t("Load timeline")}
      </button>
      {busy && <p role="status">{t("Loading timeline...")}</p>}
      {error && <ErrorNotice message={error} />}
      {result && (
        <>
          <p>
            {t("Date range")}: {date(result.period.start)} {t("to")}{" "}
            {date(result.period.end)}
          </p>
          <dl className="runway-summary">
            <div>
              <dt>{t("Starting cash")}</dt>
              <dd>
                <Amount value={result.starting_balance} />
              </dd>
            </div>
            <div>
              <dt>{t("Projected ending cash")}</dt>
              <dd>
                <Amount value={result.ending_projected_balance} />
              </dd>
            </div>
          </dl>
          <p className="source">
            {t(
              "Do not add historical movements to starting cash again. Confirmed payments are links, not additional spending.",
            )}
          </p>
          <p className="source">
            {t(
              "Forecast expense impact excludes the reserve already shown as scheduled commitments.",
            )}
          </p>
          {result.events.length ? (
            <>
              <ol
                className="financial-timeline"
                aria-label={t("Financial timeline")}
              >
                {result.events.slice(0, visible).map((event) => (
                  <TimelineRow key={event.id} event={event} />
                ))}
              </ol>
              {visible < result.events.length && (
                <button type="button" onClick={() => setVisible((n) => n + 20)}>
                  {t("Show more events")}
                </button>
              )}
            </>
          ) : (
            <Empty title={t("No timeline events")}>
              {t("No financial events were found in this date range.")}
            </Empty>
          )}
          <Notes
            assumptions={result.assumptions}
            limitations={result.limitations}
          />
        </>
      )}
    </Section>
  );
}
