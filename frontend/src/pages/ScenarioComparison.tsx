import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ApiSchemas } from "../generated/api";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useLanguage } from "../lib/useLanguage";
import { date, errorMessage } from "../lib/format";
import { digits, t, uiLabel } from "../lib/locale";
import {
  ErrorNotice,
  PageHeading,
  ResourceView,
  Section,
} from "../components/ui";
import { ScenarioAssumptions } from "../components/ScenarioAssumptions";
const warnings = {
  different_baselines:
    "These scenarios have different recorded baselines. Each column shows its own real baseline.",
  different_snapshot_dates: "These scenarios use different snapshot dates.",
  different_horizons: "These scenarios use different horizons.",
  different_schedule_confirmations:
    "These scenarios use different schedule confirmations.",
  missing_results: "Some scenarios have no results.",
  stale_results:
    "Some results are stale and are excluded from the financial matrix.",
} as const;
export function ScenarioComparison() {
  useLanguage();
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<number[]>(() =>
    Array.from(
      new Set(
        (params.get("ids") || "")
          .split(",")
          .map(Number)
          .filter((n) => Number.isInteger(n) && n > 0),
      ),
    ).slice(0, 5),
  );
  const [status, setStatus] = useState("saved");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const library = useResource(
    useCallback(
      () => api.scenarioLibrary(status, search, offset),
      [status, search, offset],
    ),
  );
  const [result, setResult] = useState<
    ApiSchemas["ScenarioLibraryComparison"] | null
  >(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function compare() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.compareScenarios(selected));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const metricLabel = (key: string) => {
    const goal = key.match(/^goal_(\d+)_(.*)$/);
    const goalFields = {
      target_amount: "Target amount",
      required_contribution: "Required contribution",
      projected_contribution_capacity: "Contribution capacity",
      accepted_commitment: "Accepted commitment",
      days_to_target: "Days until target",
    } as const;
    return goal
      ? `${t("Goal")} ${digits(goal[1])} / ${uiLabel(goalFields[goal[2] as keyof typeof goalFields] || goal[2])}`
      : uiLabel(key);
  };
  return (
    <>
      <PageHeading
        title={t("Compare scenarios")}
        description={t(
          "Stored results are reused. Comparing does not run simulations or change real finances.",
        )}
      />
      <Link to="/scenarios">{t("Back to scenarios")}</Link>
      {error && <ErrorNotice message={error} />}
      <Section title={t("Selected scenarios")}>
        <p>
          {t("Select two to five scenarios.")} {digits(selected.length)} /{" "}
          {digits(5)}
        </p>
        <label className="field">
          {t("Search scenarios")}
          <input
            type="search"
            maxLength={120}
            value={search}
            disabled={busy}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label className="field">
          {t("Scenarios")}
          <select
            value={status}
            disabled={busy}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="saved">{t("Saved")}</option>
            <option value="archived">{t("Archived")}</option>
            <option value="draft">{t("Drafts")}</option>
            <option value="all">{t("All scenarios")}</option>
          </select>
        </label>
        <ResourceView resource={library}>
          {(page) => (
            <>
              <div className="scenario-library-grid">
                {page.items.map((s) => (
                  <label className="scenario-card" key={s.id}>
                    <input
                      type="checkbox"
                      aria-label={`${t("Select for comparison")}: ${s.name}`}
                      checked={selected.includes(s.id)}
                      disabled={
                        busy ||
                        (!selected.includes(s.id) && selected.length >= 5)
                      }
                      onChange={(e) => {
                        setSelected((v) =>
                          e.target.checked
                            ? [...v, s.id]
                            : v.filter((id) => id !== s.id),
                        );
                        setResult(null);
                      }}
                    />
                    <strong>{s.name}</strong>
                    <span>
                      {uiLabel(s.status)} / {t("Changes")}:{" "}
                      {digits(s.changes.length)}
                    </span>
                    <span>
                      {t("Updated")}: {date(s.updated_at)}
                    </span>
                    <span>{s.description}</span>
                  </label>
                ))}
              </div>
              {!page.items.length && <p>{t("No scenarios yet")}</p>}
              <div className="form-actions">
                <button
                  className="button secondary"
                  disabled={busy || offset === 0}
                  onClick={() => setOffset((v) => Math.max(0, v - page.limit))}
                >
                  {t("Previous")}
                </button>
                <button
                  className="button secondary"
                  disabled={busy || offset + page.limit >= page.total}
                  onClick={() => setOffset((v) => v + page.limit)}
                >
                  {t("Next")}
                </button>
              </div>
            </>
          )}
        </ResourceView>
        <button
          className="button"
          disabled={busy || selected.length < 2 || selected.length > 5}
          onClick={() => void compare()}
        >
          {busy ? t("Working\u2026") : t("Compare scenarios")}
        </button>
      </Section>
      {result && (
        <>
          <Section title={t("Assumption differences")}>
            <p>
              {t(
                "This is a scenario based on the assumptions you selected, not a guaranteed future outcome.",
              )}
            </p>
            {result.warnings.map((w) => (
              <p className="scenario-notice" role="status" key={w}>
                {t(warnings[w])}
              </p>
            ))}
            <div className="scenario-library-grid">
              {result.columns.map(({ scenario: s, result: r, assumptions }) => (
                <article className="scenario-card" key={s.id}>
                  <p className="eyebrow">{t("WHAT-IF SCENARIO")}</p>
                  <h3>{s.name}</h3>
                  <p>{s.description}</p>
                  <p>
                    {uiLabel(s.status)} / {t("Changes")}:{" "}
                    {digits(s.changes.length)}
                  </p>
                  <p>
                    {t("Updated")}: {date(s.updated_at)}
                  </p>
                  <p>
                    {t("Result status")}: {uiLabel(s.result_state || "missing")}
                  </p>
                  {r ? (
                    <>
                      <p>
                        {t("Result date")}: {date(r.baseline_snapshot_date)}
                      </p>
                      <p>
                        {t("Run horizon")}: {date(r.horizon_end)}
                      </p>
                      <p>
                        {t("Calculation version")}: {r.calculation_version}
                      </p>
                    </>
                  ) : (
                    <p>
                      {s.result_state === "stale"
                        ? t(
                            "Assumptions changed. Open the scenario and rerun it explicitly.",
                          )
                        : t(
                            "No result yet. Open the scenario and run it explicitly.",
                          )}
                    </p>
                  )}
                  <ScenarioAssumptions items={assumptions} />
                  {r && (
                    <>
                      <p>
                        {t("Affordability")}:{" "}
                        {r.affordability
                          ? uiLabel(r.affordability)
                          : uiLabel("insufficient_data")}
                      </p>
                      {r.scenario_goals.map((g) => (
                        <p key={String(g.goal_id)}>
                          {String(g.name)} / {uiLabel(String(g.feasibility))}
                        </p>
                      ))}
                    </>
                  )}
                </article>
              ))}
            </div>
          </Section>
          <Section title={t("Financial comparison")}>
            <p>
              <strong>{t("REAL FINANCIAL DATA")}</strong>:{" "}
              {t("Recorded real baseline")}.{" "}
              {t("No shared current baseline is assumed.")}
            </p>
            {!result.metrics.length ? (
              <p>{t("No current financial results to compare.")}</p>
            ) : (
              <div
                className="table-scroll"
                role="region"
                aria-label={t("Financial comparison")}
                tabIndex={0}
              >
                <table className="scenario-comparison-table">
                  <caption>
                    {t("WHAT-IF SCENARIO")} / {t("Recorded real baseline")}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("Metric")}</th>
                      {result.columns.map((c) => (
                        <th scope="col" key={c.scenario.id}>
                          {c.scenario.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.metrics.map((row) => (
                      <tr key={row.metric}>
                        <th scope="row">{metricLabel(row.metric)}</th>
                        {row.cells.map((cell) => (
                          <td key={cell.scenario_id}>
                            {cell.comparison ? (
                              <>
                                <span className="scenario-cell-label">
                                  {t("Hypothetical value")}
                                </span>
                                <strong>
                                  {cell.comparison.scenario_value == null
                                    ? uiLabel(cell.status)
                                    : digits(cell.comparison.scenario_value)}
                                </strong>
                                <span className="scenario-cell-label">
                                  {t("Recorded real baseline")}:{" "}
                                  {cell.comparison.baseline_value == null
                                    ? uiLabel("insufficient_data")
                                    : digits(cell.comparison.baseline_value)}
                                </span>
                                <span>
                                  {t("Difference")}:{" "}
                                  {cell.comparison.absolute_delta == null
                                    ? uiLabel(cell.status)
                                    : digits(
                                        cell.comparison.absolute_delta,
                                      )}{" "}
                                  / {uiLabel(cell.comparison.direction)}
                                  {cell.comparison.percentage_delta != null &&
                                    ` / ${digits(cell.comparison.percentage_delta)}%`}
                                </span>
                                {cell.reason && (
                                  <details>
                                    <summary>{t("Reason")}</summary>
                                    <p lang="en">{cell.reason}</p>
                                  </details>
                                )}
                              </>
                            ) : (
                              <>
                                <strong>{uiLabel("insufficient_data")}</strong>
                                <p>{t("No metric in stored result")}</p>
                                <details>
                                  <summary>{t("Reason")}</summary>
                                  <p lang="en">{cell.reason}</p>
                                </details>
                              </>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </>
      )}
    </>
  );
}
