import type { ApiSchemas } from "../generated/api";
import { date } from "../lib/format";
import { digits, t, uiLabel } from "../lib/locale";
export function ScenarioAssumptions({
  items,
}: {
  items: ApiSchemas["AssumptionComparison"][];
}) {
  if (!items.length) return <p>{t("No changes yet")}</p>;
  return (
    <ul>
      {items.map(({ change: c, shared }, i) => (
        <li key={i}>
          <strong>{uiLabel(c.change_type)}</strong> /{" "}
          <span>
            {c.percentage != null
              ? `${digits(c.percentage)}%`
              : c.amount != null
                ? `BDT ${digits(c.amount)}`
                : c.target_date
                  ? date(c.target_date)
                  : uiLabel("insufficient_data")}
          </span>{" "}
          {c.frequency && uiLabel(c.frequency)}
          <p>{c.description}</p>
          <p>
            {t("Effective date")}: {date(c.effective_date)}
            {c.end_date && ` / ${date(c.end_date)}`}
            {c.target_id != null && ` / ${t("Goal")}: ${digits(c.target_id)}`}
          </p>
          <small>
            {shared ? t("Shared assumption") : t("Different assumption")}
          </small>
        </li>
      ))}
    </ul>
  );
}
