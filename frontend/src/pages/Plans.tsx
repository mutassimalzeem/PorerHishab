import { useLanguage } from "../lib/useLanguage";
import { t, uiLabel, percent } from "../lib/locale";
import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import { Plus, Pencil, Target } from "lucide-react";
import type { Goal, GoalUpdate } from "../domain";
import { api } from "../lib/api";
import { date, errorMessage, today } from "../lib/format";
import { useResource } from "../lib/useResource";
import {
  Amount,
  Empty,
  ErrorNotice,
  Field,
  Notes,
  PageHeading,
  Pager,
  ResourceView,
} from "../components/ui";
import { Dialog } from "../components/Dialog";
function GoalDetail({ goal, onEdit }: { goal: Goal; onEdit: () => void }) {
  useLanguage();
  const plan = useResource(
    useCallback(() => api.goalPlan(goal.id), [goal.id]),
    `${goal.current_saved}:${goal.target_date}:${goal.target_amount}:${goal.status}`,
  );
  const [cadence, setCadence] = useState<"monthly" | "weekly">("monthly");
  const saved = goal.current_saved;
  const progress =
    saved === null
      ? null
      : Math.min(100, (Number(saved) / Number(goal.target_amount)) * 100);
  return (
    <article className="goal">
      <div className="section-heading">
        <span className="goal-icon">
          <Target size={20} />
        </span>
        <span className={`status-label status-${goal.status}`}>
          {uiLabel(goal.status)}
        </span>
        <button
          className="text-button"
          onClick={onEdit}
          aria-label={t("Edit") + " " + goal.name}
        >
          <Pencil size={15} />
          {t("Edit")}{" "}
        </button>
      </div>
      <h2>{goal.name}</h2>
      {goal.description && <p>{goal.description}</p>}
      <div className="goal-numbers">
        <div>
          <small>{t("Self-reported savings")}</small>
          <Amount value={saved} />
        </div>
        <div>
          <small>
            {t("Target by")} {date(goal.target_date)}
          </small>
          <Amount value={goal.target_amount} />
        </div>
      </div>
      {progress === null ? (
        <p className="callout">
          {t(
            "Savings are unknown. Report an amount to calculate contributions.",
          )}{" "}
        </p>
      ) : (
        <>
          <progress
            aria-label={goal.name + " " + uiLabel("progress")}
            value={progress}
            max="100"
          />
          <p className="progress-label">
            <strong>{percent(progress)}</strong>{" "}
            {t("of target, based on your reported amount.")}{" "}
          </p>
        </>
      )}
      <ResourceView resource={plan} label={t("Checking contribution needs...")}>
        {(p) => (
          <>
            <div className="contribution-plan">
              <div className="section-heading">
                <span className="value-kind">{t("Required contribution")}</span>
                <div
                  className="segmented"
                  role="group"
                  aria-label={goal.name + " " + uiLabel("contribution period")}
                >
                  <button
                    aria-pressed={cadence === "monthly"}
                    onClick={() => setCadence("monthly")}
                  >
                    {t("Monthly")}{" "}
                  </button>
                  <button
                    aria-pressed={cadence === "weekly"}
                    onClick={() => setCadence("weekly")}
                  >
                    {t("Weekly")}{" "}
                  </button>
                </div>
              </div>
              <Amount
                value={
                  cadence === "monthly" ? p.required_monthly : p.required_weekly
                }
              />
              <small>
                {t("To reach the target by")} {date(goal.target_date)}.
              </small>
            </div>
            <div className="capacity-line">
              <span>{t("Estimated monthly capacity")}</span>
              <Amount value={p.estimated_monthly_capacity} />
            </div>
            <p className={`assessment assessment-${p.affordability}`}>
              {
                {
                  unknown: t("Capacity is not established"),
                  appears_feasible: t("Appears feasible from recorded history"),
                  at_risk: t("The target may need more room"),
                  completed: t("Target reported as complete"),
                  cancelled: t("This plan is cancelled"),
                  overdue: t("The target date has passed"),
                }[p.affordability]
              }
            </p>
            <p className="source">
              {t("As of")} {date(p.as_of_date)}
              {t(". Estimates are not a guaranteed timeline.")}{" "}
            </p>
            <Notes assumptions={p.assumptions} limitations={p.limitations} />
          </>
        )}
      </ResourceView>
    </article>
  );
}
export function Plans() {
  useLanguage();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Goal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const goals = useResource(
    useCallback(() => api.goals(offset), [offset]),
    revision,
  );
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    const values = {
      name: String(f.get("name")).trim(),
      target_amount: String(f.get("target_amount")),
      current_saved: f.get("current_saved")
        ? String(f.get("current_saved"))
        : null,
      target_date: String(f.get("target_date")),
    };
    try {
      if (editing) {
        const changes: GoalUpdate = {};
        if (values.name !== editing.name) changes.name = values.name;
        if (values.target_amount !== editing.target_amount)
          changes.target_amount = values.target_amount;
        if (values.current_saved !== editing.current_saved)
          changes.current_saved = values.current_saved;
        if (values.target_date !== editing.target_date)
          changes.target_date = values.target_date;
        const status = f.get("status") as Goal["status"];
        if (status && status !== editing.status) changes.status = status;
        await api.editGoal(editing.id, changes);
      } else await api.addGoal(values);
      setAdding(false);
      setEditing(null);
      setRevision((v) => v + 1);
      setNotice(
        editing
          ? t(
              "Goal updated. Reported savings remain separate from account balances.",
            )
          : t("Goal created. Savings are self-reported."),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title={t("Give your savings a purpose.")}
        description={t(
          "A clear target, a realistic contribution, and room for your commitments.",
        )}
        action={
          <button
            className="primary"
            onClick={() => {
              setEditing(null);
              setAdding(true);
              setError(null);
            }}
          >
            <Plus size={17} />
            {t("New goal")}{" "}
          </button>
        }
      />
      <div className="planning-guidance">
        <Target size={22} />
        <p>
          <strong>{t("A plan, not a money transfer.")}</strong>{" "}
          {t(
            "Savings are self-reported. The contribution assessment accounts for recorded history and scheduled obligations.",
          )}{" "}
        </p>
      </div>
      {notice && (
        <p role="status" className="success">
          {uiLabel(notice)}
        </p>
      )}
      <Dialog
        open={adding}
        title={editing ? t("Edit savings goal") : t("Create a savings goal")}
        description={t(
          "Set the target and report what you have saved. Leave savings blank when unknown.",
        )}
        busy={busy}
        onClose={() => {
          setAdding(false);
          setEditing(null);
          setError(null);
        }}
      >
        {error && <ErrorNotice message={error} />}
        <form className="form-grid" onSubmit={save}>
          <Field
            label={t("Goal name")}
            name="name"
            required
            maxLength={160}
            defaultValue={editing?.name ?? ""}
          />
          <Field
            label={t("Target amount (BDT)")}
            name="target_amount"
            type="number"
            min="0.01"
            step="0.01"
            required
            defaultValue={editing?.target_amount ?? ""}
          />
          <Field
            label={t("Already saved (optional)")}
            name="current_saved"
            type="number"
            min="0"
            step="0.01"
            hint={t("Blank means unknown, not zero.")}
            defaultValue={editing?.current_saved ?? ""}
          />
          <Field
            label={t("Target date")}
            name="target_date"
            type="date"
            min={editing ? undefined : today()}
            required
            defaultValue={editing?.target_date ?? ""}
          />
          {editing && (
            <label className="field">
              <span>{t("Goal status")}</span>
              <select name="status" defaultValue={editing.status}>
                {editing.status === "active" ? (
                  <>
                    <option value="active">{t("Active")}</option>
                    <option value="completed">{t("Completed")}</option>
                    <option value="cancelled">{t("Cancelled")}</option>
                  </>
                ) : (
                  <option value={editing.status}>
                    {uiLabel(editing.status)}
                  </option>
                )}
              </select>
              <small>
                {t(
                  "Completing requires reported savings at least equal to the target. Completed and cancelled goals cannot reopen.",
                )}{" "}
              </small>
            </label>
          )}
          <div className="dialog-actions">
            <button
              type="button"
              disabled={busy}
              onClick={() => setAdding(false)}
            >
              {t("Keep existing records")}{" "}
            </button>
            <button className="primary" disabled={busy}>
              {busy
                ? t("Saving...")
                : editing
                  ? t("Save goal changes")
                  : t("Create goal")}
            </button>
          </div>
        </form>
      </Dialog>
      <ResourceView resource={goals} label={t("Reading your savings plans...")}>
        {(p) => (
          <>
            {p.items.length ? (
              <div className="goal-grid">
                {p.items.map((goal) => (
                  <GoalDetail
                    key={goal.id}
                    goal={goal}
                    onEdit={() => {
                      setEditing(goal);
                      setAdding(true);
                      setError(null);
                    }}
                  />
                ))}
              </div>
            ) : (
              <Empty
                title={t("What are you saving for?")}
                action={
                  <button className="primary" onClick={() => setAdding(true)}>
                    {t("Create your first goal")}{" "}
                  </button>
                }
              >
                {t(
                  "An emergency buffer, education, or a planned purchase. Start with a target and a date.",
                )}{" "}
              </Empty>
            )}
            <Pager
              offset={offset}
              total={p.total}
              limit={20}
              onChange={setOffset}
            />
          </>
        )}
      </ResourceView>
    </>
  );
}
