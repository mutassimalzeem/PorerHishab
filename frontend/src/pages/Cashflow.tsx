import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import { Plus } from "lucide-react";
import type { Cashflow as CashflowData, Decision, Scheduled } from "../domain";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { date, errorMessage, today } from "../lib/format";
import {
  Amount,
  Empty,
  ErrorNotice,
  Field,
  Notes,
  PageHeading,
  Pager,
  ResourceView,
  Section,
} from "../components/ui";
import { CashflowChart } from "../components/CashflowChart";
export function Cashflow() {
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState("scheduled");
  const [revision, setRevision] = useState(0);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [scenario, setScenario] = useState<CashflowData | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const scheduled = useResource(
    useCallback(
      () => api.scheduled({ status: filter, limit: 20, offset }),
      [filter, offset],
    ),
    revision,
  );
  async function run(
    e: FormEvent<HTMLFormElement>,
    kind: "schedule" | "scenario" | "purchase",
  ) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    setBusy(true);
    setError(null);
    if (kind === "scenario") setScenario(null);
    if (kind === "purchase") setDecision(null);
    try {
      if (kind === "schedule") {
        await api.addScheduled({
          title: String(f.get("title")),
          kind: String(f.get("kind")) as "income" | "expense",
          amount: String(f.get("amount")),
          due_date: String(f.get("due_date")),
        });
        setAdding(false);
        setRevision((v) => v + 1);
        setNotice("Scheduled item saved. No actual transaction was created.");
      }
      if (kind === "scenario")
        setScenario(
          await api.cashflow(
            String(f.get("starting_balance")),
            Number(f.get("months_ahead")),
          ),
        );
      if (kind === "purchase")
        setDecision(
          await api.decision({
            starting_balance: String(f.get("starting_balance")),
            purchase_amount: String(f.get("purchase_amount")),
            safety_buffer: String(f.get("safety_buffer")),
            horizon_days: Number(f.get("horizon_days")),
          }),
        );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function update(item: Scheduled, status: Scheduled["status"]) {
    setBusy(true);
    setError(null);
    try {
      await api.updateScheduled(item.id, status);
      setRevision((v) => v + 1);
      setScenario(null);
      setDecision(null);
      setNotice(
        `Marked ${status}. This does not create an actual transaction.`,
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
        title="Make room for what comes next."
        description="Recorded money, scheduled commitments and estimates each tell a different story."
        action={
          <button className="primary" onClick={() => setAdding(!adding)}>
            <Plus size={17} />
            Schedule an item
          </button>
        }
      />
      <div className="meaning-strip">
        <span>
          <b>Actual</b> Already recorded
        </span>
        <span>
          <b>Scheduled</b> A future plan
        </span>
        <span>
          <b>Forecast</b> A historical estimate
        </span>
      </div>
      {notice && (
        <p role="status" className="success">
          {notice}
        </p>
      )}
      {error && <ErrorNotice message={error} />}
      <Section title="Upcoming & scheduled">
        <label className="inline-form">
          Show{" "}
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="scheduled">Scheduled (including overdue)</option>
            <option value="paid">Paid</option>
            <option value="cancelled">Cancelled</option>
            <option value="">All statuses</option>
          </select>
        </label>
        {adding && (
          <form
            className="editor form-grid"
            onSubmit={(e) => run(e, "schedule")}
          >
            <Field
              name="title"
              label="What is it for?"
              required
              maxLength={160}
            />
            <label className="field">
              <span>Kind</span>
              <select name="kind">
                <option value="expense">Planned expense</option>
                <option value="income">Expected income</option>
              </select>
            </label>
            <Field
              label="Amount (BDT)"
              name="amount"
              type="number"
              min="0.01"
              step="0.01"
              required
            />
            <Field
              label="Due date"
              name="due_date"
              type="date"
              required
              defaultValue={today()}
            />
            <button className="primary form-end" disabled={busy}>
              Save scheduled item
            </button>
          </form>
        )}
        <ResourceView resource={scheduled}>
          {(p) => (
            <>
              {p.items.length ? (
                <div className="schedule-list">
                  {p.items.map((item) => (
                    <div className="schedule-row" key={item.id}>
                      <div className="date-tile">{item.due_date.slice(8)}</div>
                      <div>
                        <strong>{item.title}</strong>
                        <small>
                          {date(item.due_date)} / {item.kind} / {item.status}
                          {item.status === "scheduled" &&
                          item.due_date < today()
                            ? " / Overdue - excluded from future scenarios"
                            : ""}
                        </small>
                        {item.kind === "income" && (
                          <small>
                            Expected income; not currently available.
                          </small>
                        )}
                      </div>
                      <Amount value={item.amount} />
                      {item.status === "scheduled" && (
                        <div className="actions">
                          <button
                            disabled={busy}
                            onClick={() => update(item, "paid")}
                          >
                            Mark paid
                          </button>
                          <button
                            disabled={busy}
                            className="text-button"
                            onClick={() => update(item, "cancelled")}
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <Empty title="No items in this view">
                  Schedule a bill or expected income to see it here.
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
      </Section>
      <Section title="Your cashflow outlook">
        <p className="muted">
          Enter a balance you have checked yourself. We do not infer an account
          balance from transaction history.
        </p>
        <form className="inline-form" onSubmit={(e) => run(e, "scenario")}>
          <Field
            label="Starting balance (BDT)"
            name="starting_balance"
            type="number"
            min="0"
            step="0.01"
            required
          />
          <label className="field">
            <span>Look ahead</span>
            <select name="months_ahead" defaultValue="3">
              <option value="3">3 months</option>
              <option value="6">6 months</option>
              <option value="12">12 months</option>
            </select>
          </label>
          <button className="primary form-end" disabled={busy}>
            {busy ? "Working..." : "Build outlook"}
          </button>
        </form>
        {!scenario && (
          <p className="callout">
            Your outlook will appear here after you supply a starting balance.
            Estimates may be unavailable when recorded history is too short.
          </p>
        )}
        {scenario && (
          <div aria-live="polite">
            <p className="source">
              As of {date(scenario.as_of_date)}. User-supplied starting balance:{" "}
              <Amount value={scenario.starting_balance} />.{" "}
              {scenario.coverage.transaction_count} observed records in the
              coverage window.
            </p>
            <CashflowChart months={scenario.months} />
            <div
              className="table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Monthly cashflow scenario details"
            >
              <table>
                <caption>
                  Monthly scenarios, in BDT. Scheduled income remains uncertain.
                </caption>
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Scheduled expenses</th>
                    <th>Expected income (uncertain)</th>
                    <th>Estimated balance</th>
                    <th>Without future income</th>
                  </tr>
                </thead>
                <tbody>
                  {scenario.months.map((m) => (
                    <tr key={m.month}>
                      <th>{m.month}</th>
                      <td>
                        <Amount value={m.scheduled_expenses} />
                      </td>
                      <td>
                        <Amount value={m.uncertain_scheduled_income} />
                      </td>
                      <td>
                        <Amount value={m.projected_balance} />
                      </td>
                      <td>
                        <Amount value={m.balance_without_future_income} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {scenario.months.some((m) => m.projected_balance === null) && (
              <p className="callout">
                Recorded history is insufficient for a reliable projection. The
                known-obligation scenario is still available.
              </p>
            )}
            <Notes
              assumptions={scenario.assumptions}
              limitations={[
                ...scenario.limitations,
                ...scenario.coverage.limitations,
              ]}
            />
          </div>
        )}
      </Section>
      <section id="purchase" className="section">
        <h2>Can this purchase fit?</h2>
        <p className="muted">
          This check reserves upcoming scheduled expenses and your safety
          buffer. It excludes future income.
        </p>
        <form className="form-grid" onSubmit={(e) => run(e, "purchase")}>
          <Field
            label="Available balance (BDT)"
            name="starting_balance"
            type="number"
            min="0"
            step="0.01"
            required
          />
          <Field
            label="Purchase amount (BDT)"
            name="purchase_amount"
            type="number"
            min="0.01"
            step="0.01"
            required
          />
          <Field
            label="Safety buffer (BDT)"
            name="safety_buffer"
            type="number"
            min="0"
            step="0.01"
            required
          />
          <Field
            label="Days ahead"
            name="horizon_days"
            type="number"
            min="1"
            max="366"
            required
            defaultValue="30"
          />
          <button className="primary form-end" disabled={busy}>
            Assess purchase
          </button>
        </form>
        {decision && (
          <div className="decision-result" aria-live="polite">
            <h3>
              {
                {
                  safe: "Fits this supplied scenario",
                  caution: "Leave more room for uncertainty",
                  not_recommended: "This purchase would leave too little room",
                  insufficient_data: "More information is needed",
                }[decision.status]
              }
            </h3>
            <p>
              After the purchase and scheduled expense reserve:{" "}
              <Amount value={decision.remaining_after_purchase_and_reserve} />
            </p>
            <p>
              Reserved scheduled expenses:{" "}
              <Amount value={decision.scheduled_expense_reserve} />. Horizon
              ends {date(decision.horizon_end)}.
            </p>
            <Notes
              assumptions={decision.assumptions}
              limitations={decision.warnings}
            />
          </div>
        )}
      </section>
    </>
  );
}
