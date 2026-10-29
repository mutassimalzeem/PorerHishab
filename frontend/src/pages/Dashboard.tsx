import { useLanguage } from "../lib/useLanguage";
import { t, uiLabel, digits } from "../lib/locale";
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
  useLanguage();
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
        title={`${t("A clearer picture")}${user.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}.`}
        description={t(
          "What is recorded, what is coming, and what deserves your attention.",
        )}
        action={
          <Link className="button primary" to="/transactions?add=1">
            <Plus size={17} />
            {t("Add transaction")}{" "}
          </Link>
        }
      />
      <ResourceView
        resource={picture}
        label={t("Putting your recorded picture together...")}
      >
        {(data) => {
          const s = data.snapshot;
          const obligations = s.scheduled_obligations;
          return (
            <>
              <div className="period-row">
                <span className="context">
                  <CalendarDays size={16} />
                  {t("Month to date")}{" "}
                </span>
                <span className="source">
                  {date(s.period.start)} {t("to")} {date(s.period.end)}
                </span>
              </div>
              <section className="position">
                <div className="position-main">
                  <span className="context">{t("Recorded net activity")}</span>
                  <Amount
                    value={s.net_cashflow}
                    className={
                      s.net_cashflow !== null && Number(s.net_cashflow) < 0
                        ? "negative"
                        : ""
                    }
                  />
                  <p>
                    {t("Income minus expenses in your BDT records.")} <br />
                    {t("This is not your account balance.")}{" "}
                  </p>
                  <Link
                    to={`/transactions?start_date=${s.period.start}&end_date=${s.period.end}`}
                    className="position-source"
                  >
                    {t("Review the records")} <ArrowUpRight size={16} />
                  </Link>
                </div>
                <div className="position-breakdown">
                  <div>
                    <span>
                      <i className="income-key" />
                      {t("Income recorded")}{" "}
                    </span>
                    <Amount value={s.income} className="positive" />
                  </div>
                  <div>
                    <span>
                      <i className="expense-key" />
                      {t("Expenses recorded")}{" "}
                    </span>
                    <Amount value={s.expenses} />
                  </div>
                  <p className="source">
                    {t(
                      "Unlinked records are assumed BDT. Account-linked records include owned BDT accounts only.",
                    )}{" "}
                  </p>
                </div>
              </section>
              <FinancialContext coverage={s.data_coverage} />
              <div className="dashboard-columns">
                <div>
                  <Section
                    title={t("Make room for your commitments")}
                    link={t("Manage scheduled items")}
                    to="/cashflow"
                  >
                    <div className="commitment-summary">
                      <div>
                        <span className="value-kind scheduled-kind">
                          {t("Scheduled expenses")}{" "}
                        </span>
                        <Amount value={obligations.scheduled_expenses} />
                        <small>
                          {date(obligations.period.start)} {t("to")}{" "}
                          {date(obligations.period.end)}
                        </small>
                      </div>
                      <div>
                        <span className="value-kind scheduled-kind">
                          {t("Expected income")}{" "}
                        </span>
                        <Amount
                          value={obligations.uncertain_scheduled_income}
                        />
                        <small>
                          {t("Uncertain. Not currently available.")}
                        </small>
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
                              {digits(item.due_date.slice(8))}
                            </div>
                            <div>
                              <strong>{item.title}</strong>
                              <small>
                                {date(item.due_date)} {t("/ Scheduled")}{" "}
                                {uiLabel(item.kind)}
                              </small>
                            </div>
                            <Amount value={item.amount} />
                          </div>
                        ))}
                        {obligations.items.length > 4 && (
                          <Link className="text-button" to="/cashflow">
                            {t("Review all")} {digits(obligations.items.length)}{" "}
                            {t("items")}{" "}
                          </Link>
                        )}
                      </div>
                    ) : (
                      <Empty
                        title={t("Give your next month some shape")}
                        action={
                          <Link className="button" to="/cashflow">
                            {t("Schedule a payment")}{" "}
                          </Link>
                        }
                      >
                        {t(
                          "Add upcoming bills and expected income. Plans stay separate from recorded transactions.",
                        )}{" "}
                      </Empty>
                    )}
                    <Notes limitations={obligations.limitations} />
                  </Section>
                  <Section
                    title={t("Recent transactions")}
                    link={t("All transactions")}
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
                    <span className="context">
                      {t("Before your next purchase")}
                    </span>
                    <h2>{t("Leave room for what comes next.")}</h2>
                    <p>
                      {t(
                        "Supply a balance you have checked. Reserve upcoming expenses and a safety buffer before deciding.",
                      )}{" "}
                    </p>
                    <Link className="button primary" to="/cashflow#purchase">
                      {t("Check a purchase")} <ArrowUpRight size={16} />
                    </Link>
                    <small>
                      {t("Expected income is not money available today.")}
                    </small>
                  </section>
                  <Section title={t("Worth your attention")}>
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
                                    ? t("Estimated outlook")
                                    : t("Recorded observation")}
                                </span>
                                <h3>{n.title}</h3>
                                <p>{n.next_action}</p>
                                <Link to="/insights">
                                  {t("Review evidence")}{" "}
                                  <ArrowUpRight size={14} />
                                </Link>
                              </article>
                            ))
                          ) : (
                            <p className="quiet-state">
                              {t(
                                "No supported observations yet. More complete records can make changes easier to identify.",
                              )}{" "}
                            </p>
                          )}
                          <Notes limitations={p.limitations} />
                        </>
                      )}
                    </ResourceView>
                  </Section>
                  <Section title={t("Room to save")}>
                    <ResourceView resource={saving}>
                      {(p) => (
                        <>
                          {p.recommendations.length ? (
                            <>
                              <h3>{p.recommendations[0].title}</h3>
                              <span className="value-kind forecast-kind">
                                {t("Estimated monthly opportunity")}{" "}
                              </span>
                              <Amount
                                value={
                                  p.recommendations[0].estimated_monthly_saving
                                }
                              />
                              <p className="muted">
                                {t(
                                  "A possible reduction to review, not guaranteed savings.",
                                )}{" "}
                              </p>
                              <Link to="/insights">
                                {t("Inspect the comparison")}{" "}
                                <ArrowUpRight size={14} />
                              </Link>
                            </>
                          ) : (
                            <p className="quiet-state">
                              {t(
                                "No saving amount is assumed. Opportunities need observations across three complete calendar months.",
                              )}{" "}
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
        <Section title={t("Recent transactions")}>
          <ResourceView resource={recent}>
            {(p) => <TransactionTable items={p.items} />}
          </ResourceView>
        </Section>
      )}
    </>
  );
}
