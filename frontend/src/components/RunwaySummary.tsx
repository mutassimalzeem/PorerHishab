import { useState } from "react";
import type { ApiSchemas } from "../generated/api";
import { api } from "../lib/api";
import { date, errorMessage } from "../lib/format";
import { t, uiLabel } from "../lib/locale";
import { useLanguage } from "../lib/useLanguage";
import { Amount, ErrorNotice, Notes, Section } from "./ui";

export function RunwaySummary() {
  useLanguage();
  const [result, setResult] = useState<ApiSchemas["FinancialRunway"] | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function load() {
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      setResult(await api.runway());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Section title={t("Account cash & runway")}>
      <p className="source">
        {t(
          "Account balances and three complete months of history are needed. Scheduled income remains uncertain.",
        )}
      </p>
      <button type="button" disabled={busy} onClick={load}>
        {busy
          ? t("Checking account runway...")
          : result
            ? t("Refresh account runway")
            : t("Check account runway")}
      </button>
      {error && <ErrorNotice message={error} />}
      {result && (
        <div aria-live="polite">
          <p>
            {date(result.period.start)} {t("to")} {date(result.period.end)}
          </p>
          <p>
            <strong>{uiLabel(result.runway_status)}</strong> &middot;{" "}
            {t("Confidence")}: {uiLabel(result.confidence)}
          </p>
          <dl className="runway-summary">
            <div>
              <dt>{t("Account starting cash")}</dt>
              <dd>
                <Amount value={result.starting_balance} />
              </dd>
            </div>
            <div>
              <dt>{t("Remaining commitments")}</dt>
              <dd>
                <Amount value={result.scheduled_expense_reserve} />
              </dd>
            </div>
            <div>
              <dt>{t("Projected balance")}</dt>
              <dd>
                <Amount value={result.projected_end_balance} />
              </dd>
            </div>
            <div>
              <dt>{t("Lowest projected balance")}</dt>
              <dd>
                <Amount value={result.minimum_projected_balance} />
              </dd>
            </div>
          </dl>
          <p className="source">
            {t("Monthly estimates cannot establish an exact depletion day.")}
          </p>
          <p className="source">
            {t(
              "Account reports may be incomplete or stale. This forecast assumes expenses precede income within each month.",
            )}
          </p>
          <Notes
            assumptions={result.assumptions}
            limitations={result.limitations}
          />
        </div>
      )}
    </Section>
  );
}
