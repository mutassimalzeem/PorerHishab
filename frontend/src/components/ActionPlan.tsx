import { useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useLanguage } from "../lib/useLanguage";
import { digits, t, uiLabel } from "../lib/locale";
import { Amount, Notes, ResourceView, Section } from "./ui";

export function ActionPlan({ revision = 0 }: { revision?: number }) {
  useLanguage();
  const resource = useResource(
    useCallback(() => api.actionPlan(), []),
    revision,
  );
  return (
    <Section title={t("Your next actions")}>
      <ResourceView
        resource={resource}
        label={t("Reading your action plan...")}
      >
        {(plan) => (
          <>
            {plan.actions.length ? (
              <ol className="action-plan-list">
                {plan.actions.map((action) => (
                  <li key={action.id}>
                    <article
                      className={`coaching-card coaching-${action.priority}`}
                    >
                      <p className="context">
                        <strong>
                          {uiLabel(
                            action.priority[0].toUpperCase() +
                              action.priority.slice(1),
                          )}
                        </strong>
                      </p>
                      <h3>
                        {digits(action.rank)}. {uiLabel(action.title)}
                      </h3>
                      {action.subject && (
                        <p>
                          {action.type === "spending_spike" ||
                          action.type === "repeated_spending"
                            ? uiLabel(action.subject)
                            : action.subject}
                        </p>
                      )}
                      <p>{uiLabel(action.description)}</p>
                      <p>{uiLabel(action.recommended_action)}</p>
                      {action.amount !== null && (
                        <Amount value={action.amount} />
                      )}
                      <Link
                        to={
                          action.type === "goal_risk" ||
                          action.type === "savings_opportunity"
                            ? "/plans"
                            : action.type === "spending_spike" ||
                                action.type === "repeated_spending"
                              ? "/insights"
                              : "/cashflow"
                        }
                      >
                        {t("Review related records")}
                      </Link>
                      <Notes
                        assumptions={action.assumptions.map(uiLabel)}
                        limitations={action.limitations.map(uiLabel)}
                      />
                    </article>
                  </li>
                ))}
              </ol>
            ) : (
              <p>{t("No active actions right now.")}</p>
            )}
            {plan.completed_count > 0 && (
              <p>
                {t("Reported done")}: {digits(plan.completed_count)}
              </p>
            )}
            <p className="source">
              {t(
                "Feedback records your report and does not verify a financial action.",
              )}
            </p>
            <Notes
              assumptions={plan.assumptions.map(uiLabel)}
              limitations={plan.limitations.map(uiLabel)}
            />
          </>
        )}
      </ResourceView>
    </Section>
  );
}
