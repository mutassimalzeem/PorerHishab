import { useCallback, useState, type Dispatch, type SetStateAction } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useLanguage } from "../lib/useLanguage";
import { t, uiLabel } from "../lib/locale";
import { date } from "../lib/format";
import type { ApiSchemas } from "../generated/api";
import { Amount, Evidence, Notes, ResourceView, Section } from "./ui";
import { FinancialReviewFeedback } from "./FinancialReviewFeedback";

function stable(value: unknown): string {
  return JSON.stringify(value, (key, item) =>
    key === "observed_at"
      ? undefined
      : item && typeof item === "object" && !Array.isArray(item)
        ? Object.fromEntries(
            Object.entries(item).sort(([a], [b]) => a.localeCompare(b)),
          )
        : item,
  );
}

type Review = ApiSchemas["FinancialReview"];

function ReviewExplanation({ review }: { review: Review }) {
  const { language } = useLanguage();
  const resource = useResource(
    useCallback(
      () =>
        api.coachAsk(
          {
            message: "Explain my financial review",
            schedules_confirmed: review.schedules_confirmed,
          },
          language,
        ),
      [review, language],
    ),
  );
  return (
    <ResourceView resource={resource}>
      {(response) => {
        const horizon = (response.evidence ?? []).find(
          (e) => e.evidence_id === "ev_review_horizon",
        );
        const priorities = (response.evidence ?? []).find(
          (e) => e.evidence_id === "ev_review_priorities",
        );
        const steps = (response.evidence ?? []).find(
          (e) => e.evidence_id === "ev_review_execution_steps",
        );
        const source = (response.evidence ?? []).find(
          (e) => e.evidence_id === "ev_review_source",
        );
        const matching =
          horizon?.as_of_date === review.plan.as_of_date &&
          stable(horizon.value) === stable(review.plan.planning_horizon) &&
          stable(priorities?.value) ===
            stable(review.decisions.priorities ?? []) &&
          stable(steps?.value) === stable(review.execution_plan.steps) &&
          stable(source?.value) ===
            stable({
              evidence: review.decisions.evidence,
              capacity: review.plan.goal_planning?.capacity ?? null,
              schedules_confirmed: review.schedules_confirmed,
              data_status: review.plan.data_status,
            });
        return (
          <div role="status">
            {matching ? (
              <>
                <p style={{ whiteSpace: "pre-line" }}>{response.answer}</p>
                {(response.warnings ?? []).map((warning, i) => (
                  <p key={i}>{warning.message}</p>
                ))}
                <Notes limitations={response.limitations} />
              </>
            ) : (
              <p>
                {t(
                  "The review has changed. Refresh before requesting another explanation.",
                )}
              </p>
            )}
          </div>
        );
      }}
    </ResourceView>
  );
}

function ReviewContents({
  review,
  setRefresh,
}: {
  review: Review;
  setRefresh: Dispatch<SetStateAction<number>>;
}) {
  const [explain, setExplain] = useState(false);
  const refreshAfterFeedback = async () => {
    setRefresh((prev) => prev + 1);
  };
  const { plan, decisions, execution_plan: execution } = review;
  const priorities = new Map(
    (decisions.priorities ?? []).map((p) => [p.priority_id, p]),
  );
  return (
    <>
      <p>
        {t("Review date")}: {date(plan.as_of_date)}
      </p>
      <p>
        {t("Reporting horizon")}: {date(plan.planning_horizon.start)} {t("to")}{" "}
        {date(plan.planning_horizon.end)}
      </p>
      {plan.goal_planning && (
        <div className="goal-numbers">
          <div>
            <small>{uiLabel("Trusted cash")}</small>
            <Amount value={plan.goal_planning.capacity.trusted_cash} />
          </div>
          <div>
            <small>{t("Conservative monthly capacity")}</small>
            <Amount
              value={plan.goal_planning.capacity.conservative_monthly_capacity}
            />
          </div>
        </div>
      )}
      <p role="status">
        {t("Plan status")}: {uiLabel(plan.data_status)}
      </p>
      <p>
        {t(
          "Review only. Ready means ready for review; no financial action is authorized or executed.",
        )}
      </p>
      <p>
        {t(
          "Feedback records your report and does not verify a financial action.",
        )}
      </p>
      {[
        ...(plan.warnings ?? []),
        ...(decisions.warnings ?? []),
        ...(execution.warnings ?? []),
      ].map((w, i) => (
        <p key={i}>{w.message}</p>
      ))}
      {!(decisions.priorities ?? []).length && (
        <p>
          {t(
            "No priorities to review. Missing information may still limit this review.",
          )}
        </p>
      )}
      <ol className="action-plan-list">
        {(decisions.priorities ?? []).map((priority) => (
          <li key={priority.priority_id}>
            <article className={`coaching-card coaching-${priority.level}`}>
              <h3>{uiLabel(priority.title)}</h3>
              <p>
                {uiLabel(priority.level)} / {uiLabel(priority.reason)}
              </p>
              <p>
                {t("Evidence quality")}: {uiLabel(priority.evidence_quality)}
              </p>
              <Notes
                assumptions={priority.assumptions}
                limitations={priority.limitations}
              />
              <Evidence
                value={(decisions.evidence ?? []).filter((e) =>
                  priority.evidence_ids.includes(e.evidence_id),
                )}
              />
            </article>
          </li>
        ))}
      </ol>
      <h3>{t("Your next actions")}</h3>
      {!(execution.steps ?? []).length && <p>{t("No steps to review")}</p>}
      <ol className="action-plan-list">
        {(execution.steps ?? []).map((step) => (
          <li key={step.step_id}>
            <article className={`coaching-card coaching-${step.level}`}>
              <h4>{uiLabel(step.title)}</h4>
              <p>
                {step.state === "blocked"
                  ? t("Blocked for review")
                  : t("Ready for review")}
              </p>
              <p>{uiLabel(step.description)}</p>
              {!!(
                (step.blocking_priority_ids ?? []).length ||
                (step.blocking_factors ?? []).length
              ) && (
                <>
                  <h4>{t("Prerequisites")}</h4>
                  <ul>
                    {(step.blocking_priority_ids ?? []).map((id) => (
                      <li key={id}>{priorities.get(id)?.title ?? id}</li>
                    ))}
                    {(step.blocking_factors ?? []).map((factor) => (
                      <li key={factor}>
                        {factor === "goal_capacity_unknown"
                          ? t("Capacity is unknown")
                          : t("Goal is not feasible under current assumptions")}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <Link
                to={
                  step.kind.includes("goal")
                    ? "/plans"
                    : step.kind === "review_liquidity"
                      ? "/accounts"
                      : step.kind === "review_spending" ||
                          step.kind === "review_savings"
                        ? "/transactions"
                        : "/cashflow"
                }
              >
                {t("Review related records")}
              </Link>
              <Notes
                assumptions={step.assumptions}
                limitations={step.limitations}
              />
              <FinancialReviewFeedback
                sourceActionIds={step.source_action_ids ?? []}
                refresh={refreshAfterFeedback}
              />
            </article>
          </li>
        ))}
      </ol>
      <Notes
        assumptions={plan.assumptions}
        limitations={[
          ...(plan.limitations ?? []),
          ...(decisions.limitations ?? []),
          ...(execution.limitations ?? []),
        ]}
      />
      <Evidence value={plan.evidence} />
      <button
        className="text-button"
        onClick={() => setExplain(true)}
        disabled={explain}
      >
        {t("Explain this review")}
      </button>
      {explain && <ReviewExplanation review={review} />}
    </>
  );
}

export function FinancialReview({ revision = 0 }: { revision?: number }) {
  useLanguage();
  const [confirmed, setConfirmed] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const resource = useResource(
    useCallback(() => api.financialReview(confirmed), [confirmed]),
    `${revision}:${refresh}`,
  );
  return (
    <Section title={t("Financial review")}>
      <label>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        {t("Recorded expense schedules are complete")}
      </label>
      <button className="text-button" onClick={() => setRefresh((v) => v + 1)}>
        {t("Refresh review")}
      </button>
      <ResourceView resource={resource}>
        {(review) => (
          <ReviewContents setRefresh={setRefresh}
            key={`${revision}:${refresh}:${confirmed}`}
            review={review}
          />
        )}
      </ResourceView>
    </Section>
  );
}
