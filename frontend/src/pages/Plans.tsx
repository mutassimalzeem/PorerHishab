import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import { Plus } from "lucide-react";
import type { Goal } from "../domain";
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
function GoalDetail({ goal, onSaved }: { goal: Goal; onSaved: () => void }) {
  const plan = useResource(
    useCallback(() => api.goalPlan(goal.id), [goal.id]),
    goal.current_saved,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saved = goal.current_saved;
  const progress =
    saved === null
      ? null
      : Math.min(100, (Number(saved) / Number(goal.target_amount)) * 100);
  async function update(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = new FormData(e.currentTarget).get("saved");
    setBusy(true);
    setError(null);
    try {
      await api.updateGoal(goal.id, value ? String(value) : null);
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="goal">
      <div className="section-heading">
        <h2>{goal.name}</h2>
        <span className="status-label">{goal.status}</span>
      </div>
      <p>{goal.description}</p>
      <div className="goal-numbers">
        <div>
          <small>Self-reported savings</small>
          <Amount value={saved} />
        </div>
        <div>
          <small>Target by {date(goal.target_date)}</small>
          <Amount value={goal.target_amount} />
        </div>
      </div>
      {progress !== null ? (
        <>
          <progress
            aria-label={`${goal.name} progress`}
            value={progress}
            max="100"
          />
          <p className="muted">
            {progress.toFixed(0)}% of target, based on your reported amount.
          </p>
        </>
      ) : (
        <p className="callout">
          Savings are unknown. Report an amount to calculate contributions.
        </p>
      )}
      <ResourceView resource={plan}>
        {(p) => (
          <>
            <div className="goal-numbers">
              <div>
                <small>Required monthly contribution</small>
                <Amount value={p.required_monthly} />
              </div>
              <div>
                <small>Estimated monthly capacity</small>
                <Amount value={p.estimated_monthly_capacity} />
              </div>
            </div>
            <p className="muted">
              Assessment: {p.affordability.replaceAll("_", " ")}. Calculated as
              of {date(p.as_of_date)}. This is not a guaranteed timeline.
            </p>
            <Notes assumptions={p.assumptions} limitations={p.limitations} />
          </>
        )}
      </ResourceView>
      <details className="notes">
        <summary>Update reported savings</summary>
        <form className="inline-form" onSubmit={update}>
          <Field
            label="Amount saved (BDT)"
            name="saved"
            type="number"
            min="0"
            step="0.01"
            defaultValue={saved ?? ""}
            hint="Leave blank if unknown. This does not move money."
          />
          <button className="form-end" disabled={busy}>
            Save reported amount
          </button>
        </form>
      </details>
      {error && <ErrorNotice message={error} />}
    </article>
  );
}
export function Plans() {
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const goals = useResource(
    useCallback(() => api.goals(offset), [offset]),
    revision,
  );
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api.addGoal({
        name: String(f.get("name")),
        target_amount: String(f.get("target_amount")),
        current_saved: f.get("current_saved")
          ? String(f.get("current_saved"))
          : null,
        target_date: String(f.get("target_date")),
      });
      setAdding(false);
      setRevision((v) => v + 1);
      setNotice("Goal created. Savings are self-reported.");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="Give your savings a purpose."
        description="Set a target. See the contribution it needs. Keep the assumptions in view."
        action={
          <button className="primary" onClick={() => setAdding(!adding)}>
            <Plus size={17} />
            New goal
          </button>
        }
      />
      <p className="callout">
        Goals are planning records. Reported savings are not reconciled with
        accounts, and contributions do not move money. Upcoming obligations are
        included in the backend affordability assessment.
      </p>
      {error && <ErrorNotice message={error} />}{" "}
      {notice && (
        <p role="status" className="success">
          {notice}
        </p>
      )}
      {adding && (
        <form className="editor form-grid" onSubmit={create}>
          <Field label="Goal name" name="name" required maxLength={160} />
          <Field
            label="Target amount (BDT)"
            name="target_amount"
            type="number"
            min="0.01"
            step="0.01"
            required
          />
          <Field
            label="Already saved (optional)"
            name="current_saved"
            type="number"
            min="0"
            step="0.01"
            hint="Blank means unknown, not zero."
          />
          <Field
            label="Target date"
            name="target_date"
            type="date"
            min={today()}
            required
          />
          <button className="primary form-end" disabled={busy}>
            Create goal
          </button>
        </form>
      )}
      <ResourceView resource={goals}>
        {(p) => (
          <>
            {p.items.length ? (
              <div className="goal-grid">
                {p.items.map((g) => (
                  <GoalDetail
                    key={g.id}
                    goal={g}
                    onSaved={() => {
                      setRevision((v) => v + 1);
                      setNotice("Reported savings updated.");
                    }}
                  />
                ))}
              </div>
            ) : (
              <Empty
                title="What are you saving for?"
                action={
                  <button onClick={() => setAdding(true)}>
                    Create your first goal
                  </button>
                }
              >
                An emergency buffer, education, or a planned purchase. Start
                with a target and a date.
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
