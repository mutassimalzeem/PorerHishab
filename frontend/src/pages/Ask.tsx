import { useLanguage } from "../lib/useLanguage";
import { t, uiLabel } from "../lib/locale";
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
  useLanguage();
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
        title={t("A question worth asking.")}
        description={t(
          "Get answers from your recorded finances, with the calculation in reach.",
        )}
      />
      <div className="ask-layout">
        <section>
          <div className="ask-intro">
            <CornerDownLeft size={30} />
            <h2>{t("What would help you decide?")}</h2>
            <p>
              {t(
                "Ask about a period, a spending category, your upcoming bills, or a possible purchase.",
              )}{" "}
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
                {uiLabel(s)}
                <ArrowUpRight size={16} />
              </button>
            ))}
          </div>
          <form className="ask-form" onSubmit={submit}>
            <label htmlFor="question">{t("Your financial question")}</label>
            <textarea
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              maxLength={1000}
              required
              rows={3}
              placeholder={t("How much did I spend on food last month?")}
            />
            <details
              className="notes"
              open={question.toLowerCase().includes("afford")}
            >
              <summary>{t("Purchase or cashflow context (optional)")}</summary>
              <div className="form-grid">
                <Field
                  label={t("Available balance (BDT)")}
                  name="starting_balance"
                  type="number"
                  min="0"
                  step="0.01"
                />
                <Field
                  label={t("Purchase amount (BDT)")}
                  name="purchase_amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                />
                <Field
                  label={t("Safety buffer (BDT)")}
                  name="safety_buffer"
                  type="number"
                  min="0"
                  step="0.01"
                />
              </div>
            </details>
            <button className="primary" disabled={busy || !question.trim()}>
              {busy ? t("Reading your records...") : t("Ask PorerHishab")}
              <ArrowUpRight size={16} />
            </button>
          </form>
          {busy && (
            <p role="status" className="callout">
              {t("Checking the question against your records...")}{" "}
            </p>
          )}
          {error && <ErrorNotice message={error} />}{" "}
          {answer && (
            <article className="answer" aria-live="polite">
              <span className="context">{uiLabel(answer.status)}</span>
              <h2>{asked}</h2>
              <p className="answer-text">{answer.answer}</p>
              {answer.date_range && (
                <Evidence label={t("Period used")} value={answer.date_range} />
              )}
              <Evidence
                label={t("Inspect calculation")}
                value={answer.calculation}
              />
              <Evidence label={t("Observed sources")} value={answer.sources} />
              <Evidence label={t("Data coverage")} value={answer.coverage} />
              <Notes
                assumptions={answer.assumptions}
                limitations={answer.limitations}
              />
            </article>
          )}
        </section>
        <aside className="ask-aside">
          <h3>{t("Clarity includes the limits.")}</h3>
          <p>
            {t(
              "Answers use your recorded data. Missing records can change the picture.",
            )}{" "}
          </p>
          <p>
            {t(
              "Observed amounts, scheduled plans, and estimates are separate. A projection is not a promise.",
            )}{" "}
          </p>
          <p>
            {t(
              "English questions are supported today. Merchant names and descriptions can include Bangla.",
            )}{" "}
          </p>
          <small>
            {t("Nothing here connects to your bank or moves your money.")}
          </small>
        </aside>
      </div>
    </>
  );
}
