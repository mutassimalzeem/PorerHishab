import type { Intelligence } from "../domain";
import { date } from "../lib/format";
import { Notes } from "./ui";
import { Check, Info } from "lucide-react";
export function FinancialContext({
  coverage,
}: {
  coverage: Intelligence["snapshot"]["data_coverage"];
}) {
  const titles = {
    no_records: "Your financial picture starts with a record",
    partial_current_only: "Only the current month has records",
    insufficient_history: "Some history is still missing",
    adequate_history: "Three complete months contain records",
  };
  return (
    <section
      className={`data-quality ${coverage.is_adequate ? "adequate" : "partial"}`}
      aria-label="Data coverage"
    >
      <div className="quality-icon">
        {coverage.is_adequate ? <Check size={18} /> : <Info size={18} />}
      </div>
      <div>
        <strong>{titles[coverage.status]}</strong>
        <p>
          {coverage.complete_months_observed.length} of{" "}
          {coverage.months_expected_complete} complete months observed.{" "}
          {date(coverage.period.start)} to {date(coverage.period.end)}. Records
          may still be incomplete.
        </p>
        <Notes limitations={coverage.limitations} />
      </div>
      <div className="coverage-months" aria-label="History coverage">
        {Array.from({ length: coverage.months_expected_complete }, (_, i) => {
          const start = new Date(`${coverage.period.start}T12:00:00Z`);
          start.setUTCMonth(start.getUTCMonth() + i);
          const key = start.toISOString().slice(0, 7);
          return (
            <span
              key={key}
              className={
                coverage.complete_months_observed.includes(key)
                  ? "has-records"
                  : "missing-records"
              }
            >
              <i aria-hidden="true" />
              {new Intl.DateTimeFormat("en", {
                month: "short",
                timeZone: "UTC",
              }).format(start)}
              <small>
                {coverage.complete_months_observed.includes(key)
                  ? "Recorded"
                  : "Missing"}
              </small>
            </span>
          );
        })}
      </div>
    </section>
  );
}
