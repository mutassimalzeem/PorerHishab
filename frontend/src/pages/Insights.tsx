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
  const intelligence = useResource(useCallback(() => api.intelligence(), []));
  const nudges = useResource(useCallback(() => api.nudges(), []));
  const recommendations = useResource(
    useCallback(() => api.recommendations(), []),
  );
  const [hidden, setHidden] = useState<string[]>([]);
  return (
    <>
      <PageHeading
        title="The changes that deserve a look."
        description="A few grounded observations, with the evidence behind each one."
      />
      <Section title="Worth your attention">
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
                            ? "Observation"
                            : "Needs attention"}{" "}
                          / {n.type.replaceAll("_", " ")}
                        </span>
                        <button
                          className="text-button"
                          onClick={() => setHidden((v) => [...v, n.key])}
                        >
                          Hide for this visit
                        </button>
                      </div>
                      <h3>{n.title}</h3>
                      <p>{n.next_action}</p>
                      <small>
                        {date(n.period_start)} to {date(n.period_end)}
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
                        Review related records
                      </Link>
                    </article>
                  ))
              ) : (
                <Empty title="Nothing else to review right now">
                  Observations appear when your records support a useful
                  comparison. A quiet view does not establish that your finances
                  are healthy.
                </Empty>
              )}
              {hidden.length > 0 && (
                <button className="text-button" onClick={() => setHidden([])}>
                  Restore hidden observations
                </button>
              )}
              <Notes limitations={p.limitations} />
            </>
          )}
        </ResourceView>
      </Section>
      <Section title="Possible savings, grounded in your history">
        <ResourceView resource={recommendations}>
          {(p) => (
            <>
              <p className="source">
                Coverage: {date(p.coverage.start_date)} to{" "}
                {date(p.coverage.end_date)} / {p.coverage.transaction_count}{" "}
                records.
              </p>
              {p.recommendations.length ? (
                p.recommendations.map((r) => (
                  <article className="recommendation" key={r.id}>
                    <span className="context">
                      Recommended review / {r.category}
                    </span>
                    <h3>{r.title}</h3>
                    <div className="goal-numbers">
                      <div>
                        <small>Estimated monthly reduction</small>
                        <Amount value={r.estimated_monthly_saving} />
                      </div>
                      <div>
                        <small>Annual estimate, if sustained</small>
                        <Amount value={r.estimated_annual_saving} />
                      </div>
                    </div>
                    <p className="muted">
                      Confidence: {r.confidence}. An opportunity to review, not
                      guaranteed savings.
                    </p>
                    <Evidence value={r.evidence} />
                    <Notes assumptions={r.assumptions} />
                  </article>
                ))
              ) : (
                <Empty title="A little more history first">
                  Recommendations need observations across three complete
                  calendar months. No saving amount is assumed when history is
                  insufficient.
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
        label="Reading your history and coverage..."
      >
        {(data) => <IntelligencePanels data={data} />}
      </ResourceView>
    </>
  );
}
