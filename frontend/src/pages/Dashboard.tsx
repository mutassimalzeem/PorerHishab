import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, CalendarDays, Plus, Wallet } from "lucide-react";
import type { User } from "../domain";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { date, monthRange, today } from "../lib/format";
import {
  Amount,
  Empty,
  Notes,
  PageHeading,
  ResourceView,
  Section,
} from "../components/ui";
import { TransactionTable } from "../components/TransactionTable";
export function Dashboard({ user }: { user: User }) {
  const [month, setMonth] = useState(today().slice(0, 7));
  const summary = useResource(
    useCallback(() => api.summary(monthRange(month)), [month]),
  );
  const recent = useResource(
    useCallback(
      () => api.transactions({ ...monthRange(month), limit: 5, sort: "desc" }),
      [month],
    ),
  );
  const upcoming = useResource(
    useCallback(
      () =>
        api.scheduled({
          status: "scheduled",
          due_date_from: today(),
          limit: 4,
        }),
      [],
    ),
  );
  const insights = useResource(useCallback(() => api.nudges(), []));
  const saving = useResource(useCallback(() => api.recommendations(), []));
  return (
    <>
      <PageHeading
        title={`A clearer picture${user.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}.`}
        description="Your money today, with an eye on what comes next."
        action={
          <Link className="button primary" to="/transactions?add=1">
            <Plus size={17} />
            Add transaction
          </Link>
        }
      />
      <div className="period-row">
        <span className="context">
          <CalendarDays size={16} />
          Recorded activity
        </span>
        <label>
          Period{" "}
          <input
            aria-label="Dashboard month"
            type="month"
            value={month}
            max={today().slice(0, 7)}
            onChange={(e) => {
              if (e.target.value) setMonth(e.target.value);
            }}
          />
        </label>
      </div>
      <ResourceView
        resource={summary}
        label="Reading your recorded position..."
      >
        {(s) => (
          <section className="position">
            <div className="position-main">
              <span className="context">Recorded net activity</span>
              <Amount
                value={s.transaction_count ? s.net : null}
                className={Number(s.net) < 0 ? "negative" : ""}
              />
              <p>
                Income minus expenses in this period.
                <br />
                This is not your account balance.
              </p>
              <span className="source">
                {s.transaction_count} recorded transactions /{" "}
                {date(monthRange(month).start_date)} to{" "}
                {date(monthRange(month).end_date)}
              </span>
            </div>
            <div className="position-breakdown">
              <div>
                <span>Income recorded</span>
                <Amount
                  value={s.transaction_count ? s.total_income : null}
                  className="positive"
                />
              </div>
              <div>
                <span>Expenses recorded</span>
                <Amount value={s.transaction_count ? s.total_expenses : null} />
              </div>
              <Link to="/cashflow">
                Put your next month in perspective
                <ArrowUpRight size={17} />
              </Link>
            </div>
          </section>
        )}
      </ResourceView>
      <div className="dashboard-columns">
        <div>
          <Section title="What comes next" link="Open cashflow" to="/cashflow">
            <ResourceView resource={upcoming}>
              {(p) =>
                p.items.length ? (
                  <>
                    <p className="muted">
                      Next scheduled items, from today. These have not happened
                      yet.
                    </p>
                    <div className="schedule-list">
                      {p.items.map((item) => (
                        <div className="schedule-row" key={item.id}>
                          <div className="date-tile">
                            <CalendarDays size={20} />
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
                    </div>
                    {p.total > p.items.length && (
                      <p className="muted">
                        Showing {p.items.length} of {p.total} scheduled items.
                      </p>
                    )}
                  </>
                ) : (
                  <Empty
                    title="Give your next month some shape"
                    action={
                      <Link className="button" to="/cashflow">
                        Schedule a payment
                      </Link>
                    }
                  >
                    Add upcoming bills and expected income. They stay separate
                    from your recorded money.
                  </Empty>
                )
              }
            </ResourceView>
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
            <h2>What can you spend next?</h2>
            <p>
              Start with an amount you know is available. We will reserve
              scheduled expenses before assessing a purchase.
            </p>
            <Link className="button" to="/cashflow#purchase">
              Check a purchase
              <ArrowUpRight size={16} />
            </Link>
            <small>
              Future income is never counted as money available today.
            </small>
          </section>
          <Section title="Worth your attention">
            <ResourceView resource={insights}>
              {(p) => (
                <>
                  {p.insights.length ? (
                    p.insights.slice(0, 2).map((n) => (
                      <article className={`insight ${n.severity}`} key={n.key}>
                        <span className="context">
                          {n.type.replaceAll("_", " ")}
                        </span>
                        <h3>{n.title}</h3>
                        <p>{n.next_action}</p>
                        <small>
                          {date(n.period_start)} to {date(n.period_end)}
                        </small>
                        <Link to="/insights">
                          Review details
                          <ArrowUpRight size={14} />
                        </Link>
                      </article>
                    ))
                  ) : (
                    <p className="quiet-state">
                      No observations to show. More recorded history can help
                      identify meaningful changes.
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
                      <p>
                        Potential monthly reduction:{" "}
                        <Amount
                          value={p.recommendations[0].estimated_monthly_saving}
                        />
                      </p>
                      <Link to="/insights">
                        Review the opportunity
                        <ArrowUpRight size={14} />
                      </Link>
                    </>
                  ) : (
                    <p className="quiet-state">
                      Savings opportunities need enough recent history. Keep
                      recording your transactions to build that picture.
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
}
