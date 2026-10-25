import { useCallback } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, CalendarDays, Plus, Wallet } from "lucide-react";
import type { User } from "../domain";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { date, today } from "../lib/format";
import {
  Amount,
  Empty,
  Notes,
  PageHeading,
  ResourceView,
  Section,
} from "../components/ui";
import { FinancialContext } from "../components/FinancialContext";
import { TransactionTable } from "../components/TransactionTable";
export function Dashboard({ user }: { user: User }) {
  const picture = useResource(useCallback(() => api.intelligence(), []));
  const recent = useResource(
    useCallback(
      () => api.transactions({ limit: 5, sort: "desc", end_date: today() }),
      [],
    ),
  );
  const saving = useResource(useCallback(() => api.recommendations(), []));
  const insights = useResource(useCallback(() => api.nudges(), []));
  return (
    <>
      <PageHeading
        title={`A clearer picture${user.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}.`}
        description="What is recorded, what is coming, and what deserves your attention."
        action={
          <Link className="button primary" to="/transactions?add=1">
            <Plus size={17} />
            Add transaction
          </Link>
        }
      />
      <ResourceView
        resource={picture}
        label="Putting your recorded picture together..."
      >
        {(data) => {
          const s = data.snapshot;
          const obligations = s.scheduled_obligations;
          return (
            <>
              <div className="period-row">
                <span className="context">
                  <CalendarDays size={16} />
                  Month to date
                </span>
                <span className="source">
                  {date(s.period.start)} to {date(s.period.end)}
                </span>
              </div>
              <section className="position">
                <div className="position-main">
                  <span className="context">Recorded net activity</span>
                  <Amount
                    value={s.net_cashflow}
                    className={
                      s.net_cashflow !== null && Number(s.net_cashflow) < 0
                        ? "negative"
                        : ""
                    }
                  />
                  <p>
                    Income minus expenses in your BDT records.
                    <br />
                    This is not your account balance.
                  </p>
                  <Link
                    to={`/transactions?start_date=${s.period.start}&end_date=${s.period.end}`}
                    className="position-source"
                  >
                    Review the records
                    <ArrowUpRight size={16} />
                  </Link>
                </div>
                <div className="position-breakdown">
                  <div>
                    <span>
                      <i className="income-key" />
                      Income recorded
                    </span>
                    <Amount value={s.income} className="positive" />
                  </div>
                  <div>
                    <span>
                      <i className="expense-key" />
                      Expenses recorded
                    </span>
                    <Amount value={s.expenses} />
                  </div>
                  <p className="source">
                    Unlinked records are assumed BDT. Account-linked records
                    include owned BDT accounts only.
                  </p>
                </div>
              </section>
              <FinancialContext coverage={s.data_coverage} />
              <div className="dashboard-columns">
                <div>
                  <Section
                    title="Make room for your commitments"
                    link="Manage scheduled items"
                    to="/cashflow"
                  >
                    <div className="commitment-summary">
                      <div>
                        <span className="value-kind scheduled-kind">
                          Scheduled expenses
                        </span>
                        <Amount value={obligations.scheduled_expenses} />
                        <small>
                          {date(obligations.period.start)} to{" "}
                          {date(obligations.period.end)}
                        </small>
                      </div>
                      <div>
                        <span className="value-kind scheduled-kind">
                          Expected income
                        </span>
                        <Amount
                          value={obligations.uncertain_scheduled_income}
                        />
                        <small>Uncertain. Not currently available.</small>
                      </div>
                    </div>
                    {obligations.items.length ? (
                      <div className="schedule-list">
                        {obligations.items.slice(0, 4).map((item) => (
                          <div
                            className="schedule-row"
                            key={item.scheduled_item_id}
                          >
                            <div className="date-tile">
                              {item.due_date.slice(8)}
                            </div>
                            <div>
                              <strong>{item.title}</strong>
                              <small>
                                {date(item.due_date)} / Scheduled {item.kind}
                              </small>
                            </div>
                            <Amount value={item.amount} />
                          </div>
                        ))}
                        {obligations.items.length > 4 && (
                          <Link className="text-button" to="/cashflow">
                            Review all {obligations.items.length} items
                          </Link>
                        )}
                      </div>
                    ) : (
                      <Empty
                        title="Give your next month some shape"
                        action={
                          <Link className="button" to="/cashflow">
                            Schedule a payment
                          </Link>
                        }
                      >
                        Add upcoming bills and expected income. Plans stay
                        separate from recorded transactions.
                      </Empty>
                    )}
                    <Notes limitations={obligations.limitations} />
                  </Section>
                  <Section
                    title="Recent transactions"
                    link="All transactions"
                    to="/transactions"
                  >
                    <ResourceView resource={recent}>
                      {(p) => <TransactionTable items={p.items} />}
                    </ResourceView>
                  </Section>
                </div>
                <aside className="decision-column">
                  <section className="planning-panel">
                    <Wallet size={24} />
                    <span className="context">Before your next purchase</span>
                    <h2>Leave room for what comes next.</h2>
                    <p>
                      Supply a balance you have checked. Reserve upcoming
                      expenses and a safety buffer before deciding.
                    </p>
                    <Link className="button primary" to="/cashflow#purchase">
                      Check a purchase
                      <ArrowUpRight size={16} />
                    </Link>
                    <small>Expected income is not money available today.</small>
                  </section>
                  <Section title="Worth your attention">
                    <ResourceView resource={insights}>
                      {(p) => (
                        <>
                          {p.insights.length ? (
                            p.insights.slice(0, 2).map((n) => (
                              <article
                                className={`insight ${n.severity}`}
                                key={n.key}
                              >
                                <span className="value-kind">
                                  {n.type.includes("shortfall")
                                    ? "Estimated outlook"
                                    : "Recorded observation"}
                                </span>
                                <h3>{n.title}</h3>
                                <p>{n.next_action}</p>
                                <Link to="/insights">
                                  Review evidence
                                  <ArrowUpRight size={14} />
                                </Link>
                              </article>
                            ))
                          ) : (
                            <p className="quiet-state">
                              No supported observations yet. More complete
                              records can make changes easier to identify.
                            </p>
                          )}
                          <Notes limitations={p.limitations} />
                        </>
                      )}
                    </ResourceView>
                  </Section>
                  <Section title="Room to save">
                    <ResourceView resource={saving}>
                      {(p) => (
                        <>
                          {p.recommendations.length ? (
                            <>
                              <h3>{p.recommendations[0].title}</h3>
                              <span className="value-kind forecast-kind">
                                Estimated monthly opportunity
                              </span>
                              <Amount
                                value={
                                  p.recommendations[0].estimated_monthly_saving
                                }
                              />
                              <p className="muted">
                                A possible reduction to review, not guaranteed
                                savings.
                              </p>
                              <Link to="/insights">
                                Inspect the comparison
                                <ArrowUpRight size={14} />
                              </Link>
                            </>
                          ) : (
                            <p className="quiet-state">
                              No saving amount is assumed. Opportunities need
                              observations across three complete calendar
                              months.
                            </p>
                          )}
                          <Notes limitations={p.limitations} />
                        </>
                      )}
                    </ResourceView>
                  </Section>
                </aside>
              </div>
            </>
          );
        }}
      </ResourceView>
      {picture.error && (
        <Section title="Recent transactions">
          <ResourceView resource={recent}>
            {(p) => <TransactionTable items={p.items} />}
          </ResourceView>
        </Section>
      )}
    </>
  );
}
