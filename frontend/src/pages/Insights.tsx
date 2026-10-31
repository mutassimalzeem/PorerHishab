import { ActionOutcomes } from "../components/ActionOutcomes";
import { ActionPlan } from "../components/ActionPlan";
import { FinancialCoaching } from "../components/FinancialCoaching";
import { useLanguage } from "../lib/useLanguage";
import { t, uiLabel, digits } from "../lib/locale";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { IntelligencePanels } from "../components/IntelligencePanels";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { date } from "../lib/format";
import {
  Amount,
  Empty,
  Evidence,
  Notes,
  PageHeading,
  ResourceView,
  Section,
} from "../components/ui";
export function Insights() {
  useLanguage();
  const intelligence = useResource(useCallback(() => api.intelligence(), []));
  const nudges = useResource(useCallback(() => api.nudges(), []));
  const recommendations = useResource(
    useCallback(() => api.recommendations(), []),
  );
  const [planRevision, setPlanRevision] = useState(0);
  const [hidden, setHidden] = useState<string[]>([]);
  return (
    <>
      <PageHeading
        title={t("The changes that deserve a look.")}
        description={t(
          "A few grounded observations, with the evidence behind each one.",
        )}
      />
      <ActionPlan revision={planRevision} />
      <ActionOutcomes revision={planRevision} />
      <FinancialCoaching
        onFeedback={() => setPlanRevision((value) => value + 1)}
      />
      <Section title={t("Worth your attention")}>
        <ResourceView resource={nudges}>
          {(p) => (
            <>
              {p.insights.filter((n) => !hidden.includes(n.key)).length ? (
                p.insights
                  .filter((n) => !hidden.includes(n.key))
                  .map((n) => (
                    <article
                      className={`insight insight-full ${n.severity}`}
                      key={n.key}
                    >
                      <div className="section-heading">
                        <span className="context">
                          {n.severity === "info"
                            ? t("Observation")
                            : t("Needs attention")}{" "}
                          / {uiLabel(n.type)}
                        </span>
                        <button
                          className="text-button"
                          onClick={() => setHidden((v) => [...v, n.key])}
                        >
                          {t("Hide for this visit")}{" "}
                        </button>
                      </div>
                      <h3>{n.title}</h3>
                      <p>{n.next_action}</p>
                      <small>
                        {date(n.period_start)} {t("to")} {date(n.period_end)}
                      </small>
                      <Evidence value={n.evidence} />
                      <Link
                        to={
                          n.type.includes("goal")
                            ? "/plans"
                            : n.type.includes("scheduled")
                              ? "/cashflow"
                              : "/transactions"
                        }
                      >
                        {t("Review related records")}{" "}
                      </Link>
                    </article>
                  ))
              ) : (
                <Empty title={t("Nothing else to review right now")}>
                  {t(
                    "Observations appear when your records support a useful comparison. A quiet view does not establish that your finances are healthy.",
                  )}{" "}
                </Empty>
              )}
              {hidden.length > 0 && (
                <button className="text-button" onClick={() => setHidden([])}>
                  {t("Restore hidden observations")}{" "}
                </button>
              )}
              <Notes limitations={p.limitations} />
            </>
          )}
        </ResourceView>
      </Section>
      <Section title={t("Possible savings, grounded in your history")}>
        <ResourceView resource={recommendations}>
          {(p) => (
            <>
              <p className="source">
                {t("Coverage:")} {date(p.coverage.start_date)} {t("to")}{" "}
                {date(p.coverage.end_date)} /{" "}
                {digits(p.coverage.transaction_count)} {t("records.")}{" "}
              </p>
              {p.recommendations.length ? (
                p.recommendations.map((r) => (
                  <article className="recommendation" key={r.id}>
                    <span className="context">
                      {t("Recommended review /")} {r.category}
                    </span>
                    <h3>{r.title}</h3>
                    <div className="goal-numbers">
                      <div>
                        <small>{t("Estimated monthly reduction")}</small>
                        <Amount value={r.estimated_monthly_saving} />
                      </div>
                      <div>
                        <small>{t("Annual estimate, if sustained")}</small>
                        <Amount value={r.estimated_annual_saving} />
                      </div>
                    </div>
                    <p className="muted">
                      {t("Confidence:")} {uiLabel(r.confidence)}
                      {t(
                        ". An opportunity to review, not guaranteed savings.",
                      )}{" "}
                    </p>
                    <Evidence value={r.evidence} />
                    <Notes assumptions={r.assumptions} />
                  </article>
                ))
              ) : p.limitations.some((limitation) =>
                  limitation.includes(
                    "Three complete calendar months with observed records are required",
                  ),
                ) ? (
                <Empty title={t("A little more history first")}>
                  {t(
                    "Recommendations need observations across three complete calendar months. No saving amount is assumed when history is insufficient.",
                  )}{" "}
                </Empty>
              ) : (
                <Empty title={t("No savings opportunities identified")}>
                  {t(
                    "Your recorded spending does not currently meet the criteria for a savings recommendation. Review again as new transactions are added.",
                  )}{" "}
                </Empty>
              )}
              <Notes
                limitations={[...p.limitations, ...p.coverage.limitations]}
              />
            </>
          )}
        </ResourceView>
      </Section>
      <ResourceView
        resource={intelligence}
        label={t("Reading your history and coverage...")}
      >
        {(data) => <IntelligencePanels data={data} />}
      </ResourceView>
    </>
  );
}
