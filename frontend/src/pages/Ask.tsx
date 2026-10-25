import { useState } from "react";
import type { FormEvent } from "react";
import { ArrowUpRight, CornerDownLeft } from "lucide-react";
import type { Answer } from "../domain";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import {
  ErrorNotice,
  Evidence,
  Field,
  Notes,
  PageHeading,
} from "../components/ui";
const starters = [
  "Can I afford a purchase?",
  "What changed this month?",
  "What bills are coming up?",
  "Where can I reduce spending?",
  "How much did I spend on food?",
  "How much can I save this month?",
];
export function Ask() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    setAnswer(null);
    setAsked(question);
    try {
      setAnswer(
        await api.ask({
          question,
          ...(f.get("starting_balance")
            ? { starting_balance: String(f.get("starting_balance")) }
            : {}),
          ...(f.get("purchase_amount")
            ? { purchase_amount: String(f.get("purchase_amount")) }
            : {}),
          ...(f.get("safety_buffer")
            ? { safety_buffer: String(f.get("safety_buffer")) }
            : {}),
        }),
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
        title="A question worth asking."
        description="Get answers from your recorded finances, with the calculation in reach."
      />
      <div className="ask-layout">
        <section>
          <div className="ask-intro">
            <CornerDownLeft size={30} />
            <h2>What would help you decide?</h2>
            <p>
              Ask about a period, a spending category, your upcoming bills, or a
              possible purchase.
            </p>
          </div>
          <div className="prompt-grid">
            {starters.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setQuestion(s);
                  document.getElementById("question")?.focus();
                }}
              >
                {s}
                <ArrowUpRight size={16} />
              </button>
            ))}
          </div>
          <form className="ask-form" onSubmit={submit}>
            <label htmlFor="question">Your financial question</label>
            <textarea
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              maxLength={1000}
              required
              rows={3}
              placeholder="How much did I spend on food last month?"
            />
            <details
              className="notes"
              open={question.toLowerCase().includes("afford")}
            >
              <summary>Purchase or cashflow context (optional)</summary>
              <div className="form-grid">
                <Field
                  label="Available balance (BDT)"
                  name="starting_balance"
                  type="number"
                  min="0"
                  step="0.01"
                />
                <Field
                  label="Purchase amount (BDT)"
                  name="purchase_amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                />
                <Field
                  label="Safety buffer (BDT)"
                  name="safety_buffer"
                  type="number"
                  min="0"
                  step="0.01"
                />
              </div>
            </details>
            <button className="primary" disabled={busy || !question.trim()}>
              {busy ? "Reading your records..." : "Ask PorerHishab"}
              <ArrowUpRight size={16} />
            </button>
          </form>
          {busy && (
            <p role="status" className="callout">
              Checking the question against your records...
            </p>
          )}
          {error && <ErrorNotice message={error} />}{" "}
          {answer && (
            <article className="answer" aria-live="polite">
              <span className="context">
                {answer.status.replaceAll("_", " ")}
              </span>
              <h2>{asked}</h2>
              <p className="answer-text">{answer.answer}</p>
              {answer.date_range && (
                <Evidence label="Period used" value={answer.date_range} />
              )}
              <Evidence
                label="Inspect calculation"
                value={answer.calculation}
              />
              <Evidence label="Observed sources" value={answer.sources} />
              <Evidence label="Data coverage" value={answer.coverage} />
              <Notes
                assumptions={answer.assumptions}
                limitations={answer.limitations}
              />
            </article>
          )}
        </section>
        <aside className="ask-aside">
          <h3>Clarity includes the limits.</h3>
          <p>
            Answers use your recorded data. Missing records can change the
            picture.
          </p>
          <p>
            Observed amounts, scheduled plans, and estimates are separate. A
            projection is not a promise.
          </p>
          <p>
            English questions are supported today. Merchant names and
            descriptions can include Bangla.
          </p>
          <small>Nothing here connects to your bank or moves your money.</small>
        </aside>
      </div>
    </>
  );
}
