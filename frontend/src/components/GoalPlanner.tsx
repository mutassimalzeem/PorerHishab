import { useCallback, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { ApiSchemas } from "../generated/api";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useLanguage } from "../lib/useLanguage";
import { digits, t, uiLabel } from "../lib/locale";
import { date, errorMessage } from "../lib/format";
import { Amount, ErrorNotice, Field, ResourceView, Section } from "./ui";

export function GoalPlanner({
  goalId,
  onClose,
  onSaved,
}: {
  goalId: number;
  onClose: () => void;
  onSaved?: () => void;
}) {
  useLanguage();
  const [revision, setRevision] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const pending = useRef<{ signature: string; key: string } | null>(null);
  const [cadence, setCadence] = useState<"monthly" | "weekly">("monthly");
  const [income, setIncome] = useState("0");
  const [expense, setExpense] = useState("0");
  const bundle = useResource(
    useCallback(async () => {
      const [overview, history, events, goal] = await Promise.all([
        api.planningOverview(confirmed),
        api.personalizedPlans(goalId),
        api.goalEvents(goalId),
        api.planningGoal(goalId),
      ]);
      const current = history.length
        ? await api.personalizedPlan(goalId)
        : null;
      return { overview, history, events, goal, current };
    }, [goalId, confirmed]),
    revision,
  );
  async function perform(
    operation: string,
    body: Record<string, unknown>,
    action: (key: string) => Promise<unknown>,
  ) {
    const signature = JSON.stringify({ operation, body });
    if (pending.current?.signature !== signature)
      pending.current = { signature, key: crypto.randomUUID() };
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action(pending.current.key);
      pending.current = null;
      onSaved?.();
      setNotice(t("Goal planning saved. Progress remains user-reported."));
      setRevision((v) => v + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  function plan(
    replan = false,
    alternative?: ApiSchemas["PlanAlternative"],
    target?: { target_amount: string; target_date: string | null },
  ) {
    const body = {
      schedules_confirmed: confirmed,
      cadence,
      income_change_percent: income,
      expense_change_percent: expense,
      ...(alternative
        ? {
            target_amount: alternative.target_amount,
            target_date: alternative.target_date,
          }
        : {}),
      ...(target ?? {}),
    };
    return perform(replan ? "replan" : "plan", body, (key) =>
      (replan ? api.replanGoal : api.createGoalPlan)(goalId, {
        ...body,
        idempotency_key: key,
      }),
    );
  }
  function contribute(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const amount = String(new FormData(e.currentTarget).get("contribution"));
    void perform("contribute", { amount }, (key) =>
      api.contributeGoal(goalId, { amount, idempotency_key: key }),
    );
  }
  return (
    <section className="section" aria-label={t("Personalized goal planning")}>
      <div className="section-heading">
        <h2>{t("Personalized goal planning")}</h2>
        <button onClick={onClose} disabled={busy}>
          {t("Close planner")}
        </button>
      </div>
      <p>{t("Plans are estimates, not guarantees. No money is moved.")}</p>
      <p>
        {t(
          "Reported progress is unverified. The feasibility calculation protects enough capacity for the full target.",
        )}
      </p>
      <label className="field">
        <span>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />{" "}
          {t("My recorded expense schedules include my known commitments")}
        </span>
      </label>
      <div className="form-grid">
        <label className="field">
          <span>{t("Milestone frequency")}</span>
          <select
            value={cadence}
            onChange={(e) => setCadence(e.target.value as "monthly" | "weekly")}
          >
            <option value="monthly">{t("Monthly")}</option>
            <option value="weekly">{t("Weekly")}</option>
          </select>
        </label>
        <Field
          label={t("Hypothetical income change (%)")}
          type="number"
          min="-80"
          max="50"
          step="0.01"
          value={income}
          onChange={(e) => setIncome(e.target.value)}
        />
        <Field
          label={t("Hypothetical expense change (%)")}
          type="number"
          min="-50"
          max="100"
          step="0.01"
          value={expense}
          onChange={(e) => setExpense(e.target.value)}
        />
      </div>
      {error && <ErrorNotice message={error} />}
      {notice && <p role="status">{uiLabel(notice)}</p>}
      <ResourceView resource={bundle}>
        {({ overview, history, events, goal, current }) => (
          <>
            <h3>{goal.name}</h3>
            <p>
              {t("Conservative monthly savings capacity")}:{" "}
              <Amount value={overview.capacity.conservative_monthly_capacity} />
            </p>
            <p>
              {t("Protected cash reserve")}:{" "}
              <Amount value={overview.capacity.protected_reserve} />
            </p>
            <p>
              {t("Upcoming obligations")}:{" "}
              <Amount value={overview.capacity.upcoming_obligations} />
            </p>
            <p>
              {t("Overdue commitments")}:{" "}
              <Amount value={overview.capacity.overdue_obligations} />
            </p>
            <p>
              {t("Existing goal earmarks")}:{" "}
              <Amount value={overview.capacity.reported_earmarks} />
            </p>
            <p>
              {t("Observation window")}:{" "}
              {date(overview.capacity.observation_start)} &mdash;{" "}
              {date(overview.capacity.observation_end)}
            </p>
            {overview.capacity.explanations.map((x) => (
              <p key={x}>{uiLabel(x)}</p>
            ))}
            <button
              className="primary"
              disabled={
                busy ||
                goal.status === "cancelled" ||
                goal.status === "completed"
              }
              onClick={() => void plan(Boolean(current))}
            >
              {busy
                ? t("Saving...")
                : current
                  ? t("Recalculate goal plan")
                  : t("Create personalized plan")}
            </button>
            {(goal.status === "active" || goal.status === "paused") && (
              <button
                disabled={busy}
                onClick={() =>
                  void perform(
                    "status",
                    { status: goal.status === "paused" ? "active" : "paused" },
                    () =>
                      api.editGoal(goalId, {
                        status: goal.status === "paused" ? "active" : "paused",
                      }),
                  )
                }
              >
                {goal.status === "paused" ? t("Resume goal") : t("Pause goal")}
              </button>
            )}
            {current ? (
              <>
                <Section title={t("Goal feasibility")}>
                  <p>{uiLabel(current.feasibility)}</p>
                  <p>{uiLabel(current.explanation)}</p>
                  <p>
                    {t("Required monthly contribution")}:{" "}
                    <Amount value={current.required_monthly} />
                  </p>
                  <p>
                    {t("Proposed monthly allocation")}:{" "}
                    <Amount value={current.proposed_monthly} />
                  </p>
                  <p>
                    {t("Full target remaining for verification")}:{" "}
                    <Amount value={current.remaining_amount} />
                  </p>
                  <p>
                    {t("Self-reported savings")}:{" "}
                    <Amount value={goal.current_saved} />
                  </p>
                  <p>
                    {t("Plan revision")}: {digits(current.version ?? 0)}{" "}
                    &middot; {date(current.as_of_date)}
                  </p>
                  <p>
                    {t(
                      "Saved plans describe their evaluation date. Recalculate after financial changes.",
                    )}
                  </p>
                  <details>
                    <summary>{t("Review plan assumptions")}</summary>
                    {current.limitations.map((x) => (
                      <p key={x}>{uiLabel(x)}</p>
                    ))}
                    {current.capacity.limitations.map((x, i) => (
                      <p key={i}>{uiLabel(x)}</p>
                    ))}
                  </details>
                </Section>
                <Section title={t("Alternative goal plans")}>
                  {(current.alternatives ?? []).length ? (
                    (current.alternatives ?? []).map((a) => (
                      <article key={a.key} className="insight">
                        <h4>{uiLabel(a.key)}</h4>
                        <p>
                          <Amount value={a.target_amount} /> &middot;{" "}
                          {date(a.target_date)}
                        </p>
                        <p>
                          {t("Required monthly contribution")}:{" "}
                          <Amount value={a.required_monthly} />
                        </p>
                        <p>
                          {uiLabel(a.feasibility)}: {uiLabel(a.explanation)}
                        </p>
                        <button
                          disabled={busy || !confirmed}
                          onClick={() => void plan(true, a)}
                        >
                          {t("Accept this alternative")}
                        </button>
                      </article>
                    ))
                  ) : (
                    <p>
                      {t(
                        "No supported alternative is available from current data.",
                      )}
                    </p>
                  )}
                  <p>
                    {t(
                      "You can review discretionary spending, reduce the target, or explicitly pause a lower-priority goal.",
                    )}
                  </p>
                  <form
                    className="form-grid"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      void plan(true, undefined, {
                        target_amount: String(f.get("revised_amount")),
                        target_date: String(f.get("revised_date")) || null,
                      });
                    }}
                  >
                    <Field
                      label={t("Revised target amount (BDT)")}
                      name="revised_amount"
                      type="number"
                      min="0.01"
                      step="0.01"
                      required
                      defaultValue={current.target_amount}
                    />
                    <Field
                      label={t("Revised target date (optional)")}
                      name="revised_date"
                      type="date"
                      defaultValue={current.target_date ?? ""}
                    />
                    <button disabled={busy || !confirmed}>
                      {t("Accept revised target and replan")}
                    </button>
                  </form>
                </Section>
                <Section title={t("Goal milestones")}>
                  {(current.milestones ?? []).length ? (
                    <ol>
                      {(current.milestones ?? []).map((m) => (
                        <li key={m.id}>
                          <p>
                            {date(m.due_date)} &middot; {uiLabel(m.status)}{" "}
                            &middot; <Amount value={m.target_cumulative} />
                          </p>
                          <p>
                            {t("Expected contribution")}:{" "}
                            <Amount value={m.expected_contribution} />
                          </p>
                          {m.completed_at && (
                            <p>
                              {t("Reported completed on")}:{" "}
                              {date(m.completed_at)}
                            </p>
                          )}
                          {m.status === "missed" && (
                            <button
                              disabled={busy}
                              onClick={() =>
                                void perform(
                                  "milestone",
                                  { id: m.id, status: "missed" },
                                  (key) =>
                                    api.updateGoalMilestone(goalId, m.id, {
                                      status: "missed",
                                      idempotency_key: key,
                                    }),
                                )
                              }
                            >
                              {t("Acknowledge missed milestone")}
                            </button>
                          )}
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p>
                      {t(
                        "A funded, dated plan is required before creating milestones.",
                      )}
                    </p>
                  )}
                </Section>
              </>
            ) : (
              <p>
                {t(
                  "No personalized plan yet. Review your inputs before creating one.",
                )}
              </p>
            )}
            <Section title={t("Record goal progress")}>
              <form onSubmit={contribute} className="form-grid">
                <Field
                  label={t("Reported contribution (BDT)")}
                  name="contribution"
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  disabled={
                    goal.current_saved == null || goal.status !== "active"
                  }
                />
                <button
                  disabled={
                    busy ||
                    goal.current_saved == null ||
                    goal.status !== "active"
                  }
                >
                  {t("Record contribution")}
                </button>
              </form>
              <p>
                {t(
                  "A scheduled contribution is never treated as paid. Reports do not change account balances.",
                )}
              </p>
            </Section>
            <Section title={t("Overall goal commitments")}>
              <p>
                {t("Total accepted monthly commitments")}:{" "}
                <Amount value={overview.total_planned_monthly} />
              </p>
              <p>
                {t("Current proposed allocations")}:{" "}
                <Amount value={overview.total_proposed_monthly} />
              </p>
              <p>
                {t("Capacity utilization")}:{" "}
                {overview.capacity_utilization == null
                  ? t("Not available")
                  : digits(overview.capacity_utilization) + "%"}
              </p>
              {overview.over_capacity && (
                <p role="alert">
                  {t(
                    "Accepted plans exceed current capacity. Review commitments before allocating more.",
                  )}
                </p>
              )}
              <ul>
                {overview.goals.map((g) => (
                  <li key={g.goal_id}>
                    {g.name} &middot; {uiLabel(g.feasibility)}
                    <p>{uiLabel(g.explanation)}</p>
                    <Amount value={g.proposed_monthly} />
                  </li>
                ))}
              </ul>
            </Section>
            <details>
              <summary>{t("Plan revision history")}</summary>
              <ol>
                {history.map((h) => (
                  <li key={h.id}>
                    {digits(h.version ?? 0)} &middot; {date(h.as_of_date)}{" "}
                    &middot; <Amount value={h.target_amount} /> &middot;{" "}
                    {uiLabel(h.feasibility)}
                    <p>{uiLabel(h.explanation)}</p>
                  </li>
                ))}
              </ol>
            </details>
            <details>
              <summary>{t("Goal progress history")}</summary>
              <ol>
                {events.map((e) => (
                  <li key={e.id}>
                    {uiLabel(e.kind)} &middot; {date(e.created_at)}
                    {typeof e.details.amount === "string" && (
                      <Amount value={e.details.amount} />
                    )}
                  </li>
                ))}
              </ol>
            </details>
          </>
        )}
      </ResourceView>
    </section>
  );
}
