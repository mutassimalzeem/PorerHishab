import { useLanguage } from "../lib/useLanguage";
import { t, digits, percent } from "../lib/locale";
import type { Intelligence } from "../domain";
import { date, money } from "../lib/format";
import { Amount, Empty, Notes, Section } from "./ui";
import { FinancialContext } from "./FinancialContext";
export function IntelligencePanels({ data }: { data: Intelligence }) {
  useLanguage();
  const history = data.monthly_history;
  const max = Math.max(
    1,
    ...history.flatMap((m) => [Number(m.income ?? 0), Number(m.expenses ?? 0)]),
  );
  return (
    <>
      <FinancialContext coverage={data.snapshot.data_coverage} />
      <Section title={t("Does recorded income cover recorded spending?")}>
        <p className="muted">
          {t(
            "Complete calendar months only. Missing records stay unknown; they are not a zero-spending month.",
          )}{" "}
        </p>
        <div className="history-chart">
          <div className="legend">
            <span>
              <i className="income-key" />
              {t("Observed income")}{" "}
            </span>
            <span>
              <i className="expense-key" />
              {t("Observed expenses")}{" "}
            </span>
          </div>
          {history.map((m) => (
            <div className="history-row" key={digits(m.month)}>
              <strong>{digits(m.month)}</strong>
              {m.transaction_count ? (
                <div className="history-bars">
                  <div>
                    <span>{t("Income")}</span>
                    <div className="bar-track">
                      <i
                        style={{
                          width: `${(Number(m.income ?? 0) / max) * 100}%`,
                        }}
                      />
                    </div>
                    <Amount value={m.income} />
                  </div>
                  <div className="expense-bar">
                    <span>{t("Expenses")}</span>
                    <div className="bar-track">
                      <i
                        style={{
                          width: `${(Number(m.expenses ?? 0) / max) * 100}%`,
                        }}
                      />
                    </div>
                    <Amount value={m.expenses} />
                  </div>
                </div>
              ) : (
                <p className="history-missing">
                  {t("No records. Income and expenses are unknown.")}{" "}
                </p>
              )}
            </div>
          ))}
        </div>
        <details className="notes">
          <summary>{t("Exact monthly values")}</summary>
          <div
            className="table-wrap"
            tabIndex={0}
            role="region"
            aria-label={t("Monthly recorded totals")}
          >
            <table>
              <caption>
                {t(
                  "Observed values in BDT. Net is activity, not an account balance.",
                )}{" "}
              </caption>
              <thead>
                <tr>
                  <th>{t("Month")}</th>
                  <th>{t("Income")}</th>
                  <th>{t("Expenses")}</th>
                  <th>{t("Net activity")}</th>
                </tr>
              </thead>
              <tbody>
                {history.map((m) => (
                  <tr key={digits(m.month)}>
                    <th>{digits(m.month)}</th>
                    <td>{money(m.income)}</td>
                    <td>{money(m.expenses)}</td>
                    <td>{money(m.net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Section>
      <Section title={t("Which categories changed?")}>
        <p className="muted">
          {t(
            "Latest complete month compared with the previous complete month. These are recorded amounts, not a prediction.",
          )}{" "}
        </p>
        {data.category_comparisons.length ? (
          <div className="category-comparisons">
            {data.category_comparisons.map((c) => (
              <article key={c.category}>
                <div>
                  <h3>{c.category}</h3>
                  <small>
                    {date(c.observed_period.start)} {t("to")}{" "}
                    {date(c.observed_period.end)}
                  </small>
                </div>
                <div>
                  <Amount value={c.observed_expenses} />
                  <small>{t("Latest recorded expenses")}</small>
                </div>
                <div>
                  <Amount value={c.comparison_expenses} />
                  <small>{t("Previous month")}</small>
                </div>
                <div
                  className={
                    c.delta !== null && Number(c.delta) > 0
                      ? "expense-text"
                      : "muted"
                  }
                >
                  <strong>
                    {c.percentage_change === null
                      ? t("No comparable baseline")
                      : (Number(c.percentage_change) > 0 ? "+" : "") +
                        percent(Number(c.percentage_change), 2)}
                  </strong>
                  <small>
                    {c.delta === null
                      ? t("Change unknown")
                      : money(c.delta) + " " + t("change")}
                  </small>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty title={t("No category comparison yet")}>
            {t(
              "Record expenses in complete months to compare categories.",
            )}{" "}
          </Empty>
        )}
      </Section>
      <Section title={t("Repeated charges to keep in view")}>
        <p className="muted">
          {t(
            "Detected in recorded history. These are patterns, not confirmed upcoming bills.",
          )}{" "}
        </p>
        {data.snapshot.recurring_patterns.length ? (
          <div className="recurring-list">
            {data.snapshot.recurring_patterns.map((r) => (
              <article key={r.merchant}>
                <div>
                  <h3>{r.merchant}</h3>
                  <small>
                    {digits(r.occurrences)} {t("records across")}{" "}
                    {digits(r.months)} {t("months,")} {date(r.first_date)}{" "}
                    {t("to")} {date(r.last_date)}
                  </small>
                </div>
                <div>
                  <Amount value={r.median_amount} />
                  <small>{t("Median recorded charge")}</small>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty title={t("No recurring pattern established")}>
            {t(
              "Repeated merchant charges across months may appear here when enough history is recorded.",
            )}{" "}
          </Empty>
        )}
      </Section>
      <Section title={t("The historical monthly baseline")}>
        <div className="baseline-row">
          <div>
            <small>{t("Estimated monthly income")}</small>
            <Amount value={data.cashflow.forecast_income} />
          </div>
          <div>
            <small>{t("Estimated monthly expenses")}</small>
            <Amount value={data.cashflow.forecast_expense} />
          </div>
          <div>
            <small>{t("Estimated monthly net")}</small>
            <Amount value={data.cashflow.forecast_net} />
          </div>
        </div>
        <p className="muted">
          {t(
            "A historical average, not available money. Scheduled income is not added to this estimate.",
          )}{" "}
        </p>
        <Notes
          assumptions={data.cashflow.assumptions}
          limitations={data.cashflow.limitations}
        />
      </Section>
    </>
  );
}
