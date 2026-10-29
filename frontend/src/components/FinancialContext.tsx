import { useLanguage } from "../lib/useLanguage";
import { t, getLocale, digits } from "../lib/locale";
import type { Intelligence } from "../domain";
import { date } from "../lib/format";
import { Notes } from "./ui";
import { Check, Info } from "lucide-react";
export function FinancialContext({
  coverage,
}: {
  coverage: Intelligence["snapshot"]["data_coverage"];
}) {
  useLanguage();
  const titles = {
    no_records: t("Your financial picture starts with a record"),
    partial_current_only: t("Only the current month has records"),
    insufficient_history: t("Some history is still missing"),
    adequate_history: t("Three complete months contain records"),
  };
  return (
    <section
      className={`data-quality ${coverage.is_adequate ? "adequate" : "partial"}`}
      aria-label={t("Data coverage")}
    >
      <div className="quality-icon">
        {coverage.is_adequate ? <Check size={18} /> : <Info size={18} />}
      </div>
      <div>
        <strong>{titles[coverage.status]}</strong>
        <p>
          {digits(coverage.complete_months_observed.length)} {t("of")}{" "}
          {digits(coverage.months_expected_complete)}{" "}
          {t("complete months observed.")} {date(coverage.period.start)}{" "}
          {t("to")} {date(coverage.period.end)}
          {t(". Records may still be incomplete.")}{" "}
        </p>
        <Notes limitations={coverage.limitations} />
      </div>
      <div className="coverage-months" aria-label={t("History coverage")}>
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
              {new Intl.DateTimeFormat(getLocale(), {
                month: "short",
                timeZone: "UTC",
              }).format(start)}
              <small>
                {coverage.complete_months_observed.includes(key)
                  ? t("Recorded")
                  : t("Missing")}
              </small>
            </span>
          );
        })}
      </div>
    </section>
  );
}
