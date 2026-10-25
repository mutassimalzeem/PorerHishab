import type { Intelligence } from "../domain";
import { date, money } from "../lib/format";
import { Amount, Empty, Notes, Section } from "./ui";
import { FinancialContext } from "./FinancialContext";
export function IntelligencePanels({ data }: { data: Intelligence }) {
  const history = data.monthly_history;
  const max = Math.max(
    1,
    ...history.flatMap((m) => [Number(m.income ?? 0), Number(m.expenses ?? 0)]),
  );
  return (
    <>
      <FinancialContext coverage={data.snapshot.data_coverage} />
      <Section title="Does recorded income cover recorded spending?">
        <p className="muted">
          Complete calendar months only. Missing records stay unknown; they are
          not a zero-spending month.
        </p>
        <div className="history-chart">
          <div className="legend">
            <span>
              <i className="income-key" />
              Observed income
            </span>
            <span>
              <i className="expense-key" />
              Observed expenses
            </span>
          </div>
          {history.map((m) => (
            <div className="history-row" key={m.month}>
              <strong>{m.month}</strong>
              {m.transaction_count ? (
                <div className="history-bars">
                  <div>
                    <span>Income</span>
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
                    <span>Expenses</span>
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
                  No records. Income and expenses are unknown.
                </p>
              )}
            </div>
          ))}
        </div>
        <details className="notes">
          <summary>Exact monthly values</summary>
          <div
            className="table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Monthly recorded totals"
          >
            <table>
              <caption>
                Observed values in BDT. Net is activity, not an account balance.
              </caption>
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Income</th>
                  <th>Expenses</th>
                  <th>Net activity</th>
                </tr>
              </thead>
              <tbody>
                {history.map((m) => (
                  <tr key={m.month}>
                    <th>{m.month}</th>
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
      <Section title="Which categories changed?">
        <p className="muted">
          Latest complete month compared with the previous complete month. These
          are recorded amounts, not a prediction.
        </p>
        {data.category_comparisons.length ? (
          <div className="category-comparisons">
            {data.category_comparisons.map((c) => (
              <article key={c.category}>
                <div>
                  <h3>{c.category}</h3>
                  <small>
                    {date(c.observed_period.start)} to{" "}
                    {date(c.observed_period.end)}
                  </small>
                </div>
                <div>
                  <Amount value={c.observed_expenses} />
                  <small>Latest recorded expenses</small>
                </div>
                <div>
                  <Amount value={c.comparison_expenses} />
                  <small>Previous month</small>
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
                      ? "No comparable baseline"
                      : `${Number(c.percentage_change) > 0 ? "+" : ""}${c.percentage_change}%`}
                  </strong>
                  <small>
                    {c.delta === null
                      ? "Change unknown"
                      : `${money(c.delta)} change`}
                  </small>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty title="No category comparison yet">
            Record expenses in complete months to compare categories.
          </Empty>
        )}
      </Section>
      <Section title="Repeated charges to keep in view">
        <p className="muted">
          Detected in recorded history. These are patterns, not confirmed
          upcoming bills.
        </p>
        {data.snapshot.recurring_patterns.length ? (
          <div className="recurring-list">
            {data.snapshot.recurring_patterns.map((r) => (
              <article key={r.merchant}>
                <div>
                  <h3>{r.merchant}</h3>
                  <small>
                    {r.occurrences} records across {r.months} months,{" "}
                    {date(r.first_date)} to {date(r.last_date)}
                  </small>
                </div>
                <div>
                  <Amount value={r.median_amount} />
                  <small>Median recorded charge</small>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty title="No recurring pattern established">
            Repeated merchant charges across months may appear here when enough
            history is recorded.
          </Empty>
        )}
      </Section>
      <Section title="The historical monthly baseline">
        <div className="baseline-row">
          <div>
            <small>Estimated monthly income</small>
            <Amount value={data.cashflow.forecast_income} />
          </div>
          <div>
            <small>Estimated monthly expenses</small>
            <Amount value={data.cashflow.forecast_expense} />
          </div>
          <div>
            <small>Estimated monthly net</small>
            <Amount value={data.cashflow.forecast_net} />
          </div>
        </div>
        <p className="muted">
          A historical average, not available money. Scheduled income is not
          added to this estimate.
        </p>
        <Notes
          assumptions={data.cashflow.assumptions}
          limitations={data.cashflow.limitations}
        />
      </Section>
    </>
  );
}
