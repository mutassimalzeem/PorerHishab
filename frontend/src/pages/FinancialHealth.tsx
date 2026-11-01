import { useCallback, useState } from "react";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useLanguage } from "../lib/useLanguage";
import { digits, t, uiLabel } from "../lib/locale";
import { date, errorMessage } from "../lib/format";
import {
  ErrorNotice,
  PageHeading,
  ResourceView,
  Section,
} from "../components/ui";

export function FinancialHealth() {
  useLanguage();
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(90);
  const profile = useResource(
    useCallback(() => api.financialHealth(), []),
    revision,
  );
  const history = useResource(
    useCallback(() => api.financialHealthHistory(), []),
    revision,
  );
  const trend = useResource(
    useCallback(() => api.financialHealthTrend(days), [days]),
    revision,
  );
  async function evaluate() {
    setBusy(true);
    setError(null);
    try {
      await api.evaluateFinancialHealth();
      setRevision((v) => v + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title={t("Financial Health")}
        description={t(
          "An application-specific diagnostic, not a credit score. Missing data remains unknown.",
        )}
      />
      <button className="button" disabled={busy} onClick={evaluate}>
        {busy
          ? t("Evaluating financial health...")
          : t("Evaluate financial health")}
      </button>
      {error && <ErrorNotice message={error} />}
      <ResourceView resource={profile}>
        {(p) => (
          <>
            <Section title={t("Current financial profile")}>
              <p aria-live="polite">
                {t("Financial health score")}:{" "}
                {p.overall_score == null
                  ? t("insufficient_data")
                  : `${digits(p.overall_score)} / ${digits(100)}`}{" "}
                &mdash; {uiLabel(p.status ?? "insufficient_data")}
              </p>
              <p>
                {t("Health coverage")}: {digits(p.coverage_percent ?? "0")}% (
                {digits(p.available_components?.length ?? 0)} /{" "}
                {digits(p.components.length)})
              </p>
              <p>
                {t("Health data quality")}:{" "}
                {uiLabel(p.data_quality_status ?? "insufficient")}
              </p>
              <p>
                {t("Last evaluated")}:{" "}
                {p.observed_at ? date(p.observed_at) : t("Not evaluated yet")}
              </p>
              <p>
                {t("Financial date")}: {date(p.as_of_date)}
              </p>
              <p>
                {t("Calculation version")}: {p.calculation_version}
              </p>
            </Section>
            <Section title={t("Health dimensions")}>
              {p.components.map((c) => (
                <article className="insight insight-full" key={c.key}>
                  <h3>{uiLabel(c.key)}</h3>
                  <p>
                    {c.score == null
                      ? t("insufficient_data")
                      : `${digits(c.score)} / ${digits(100)}`}{" "}
                    &mdash; {uiLabel(c.status ?? "insufficient_data")}
                  </p>
                  <p>{uiLabel(c.explanation)}</p>
                  <details>
                    <summary>{t("Health evidence")}</summary>
                    <dl>
                      {(c.evidence ?? []).map((e, i) => (
                        <div key={i}>
                          <dt>{uiLabel(e.metric.replace(/_[123]$/, ""))}</dt>
                          <dd>
                            {digits(e.value)} {uiLabel(e.unit)} &middot;{" "}
                            {uiLabel(e.source)} &middot; {date(e.as_of_date)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                    {(c.limitations ?? []).map((l) => (
                      <p key={l}>{uiLabel(l)}</p>
                    ))}
                  </details>
                </article>
              ))}
            </Section>
            <Section title={t("Health limitations")}>
              {(p.limitations ?? []).map((l) => (
                <p key={l}>{uiLabel(l)}</p>
              ))}
            </Section>
          </>
        )}
      </ResourceView>
      <Section title={t("Health trend")}>
        <label>
          {t("Comparison window")}{" "}
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {[30, 90, 180].map((d) => (
              <option key={d} value={d}>
                {digits(d)} {t("days")}
              </option>
            ))}
          </select>
        </label>
        <ResourceView resource={trend}>
          {(v) => (
            <>
              <p>
                {uiLabel(v.direction ?? "insufficient_data")}
                {v.change != null && ` / ${digits(v.change)}`}
              </p>
              <p>
                {t("Trend confidence")}:{" "}
                {uiLabel(v.confidence ?? "insufficient")}
              </p>
              {v.comparison_date && (
                <p>
                  {date(v.comparison_date)} &mdash; {date(v.current_date ?? "")}
                </p>
              )}
              <p>{uiLabel(v.limitation ?? "")}</p>
              <dl>
                {Object.entries(v.components ?? {}).map(([key, value]) => (
                  <div key={key}>
                    <dt>{uiLabel(key)}</dt>
                    <dd>{uiLabel(value)}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}
        </ResourceView>
      </Section>
      <Section title={t("Health history")}>
        <ResourceView resource={history}>
          {(rows) =>
            rows.length ? (
              <table>
                <caption>{t("Saved financial profiles")}</caption>
                <thead>
                  <tr>
                    <th>{t("Financial date")}</th>
                    <th>{t("Financial health score")}</th>
                    <th>{t("Health coverage")}</th>
                    <th>{t("Calculation version")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p, i) => (
                    <tr key={i}>
                      <td>{date(p.as_of_date)}</td>
                      <td>
                        {p.overall_score == null
                          ? t("insufficient_data")
                          : digits(p.overall_score)}
                      </td>
                      <td>{digits(p.coverage_percent ?? "0")}%</td>
                      <td>{p.calculation_version}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>{t("No health snapshots yet")}</p>
            )
          }
        </ResourceView>
      </Section>
    </>
  );
}
