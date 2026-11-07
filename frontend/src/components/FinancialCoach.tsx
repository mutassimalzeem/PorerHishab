import { useState, useEffect, useRef } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import {
  ArrowUpRight,
  Bot,
  User as UserIcon,
  PlusCircle,
  AlertTriangle,
  Lightbulb,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  History,
} from "lucide-react";
import { useLanguage } from "../lib/useLanguage";
import { t, uiLabel } from "../lib/locale";
import { useCoachRecovery } from "../lib/useCoachRecovery";
import { money } from "../lib/format";
import { ErrorNotice } from "./ui";

const STARTERS = [
  "Where did my money go this month?",
  "What is my cashflow and future balance?",
  "Can I afford to purchase 15,000 BDT?",
  "Where can I save more money?",
  "How is my savings goal progress?",
  "How healthy are my finances?",
];

export function FinancialCoach({ ownerId }: { ownerId?: number }) {
  const { language } = useLanguage();
  const recovery = useCoachRecovery(language, ownerId);
  const {
    conversationId,
    messages,
    busy,
    error,
    conversations,
    selectConversation,
  } = recovery;
  const [inputQuestion, setInputQuestion] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [expandedEvidence, setExpandedEvidence] = useState<
    Record<string, boolean>
  >({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, busy]);

  async function handleSubmit(e?: FormEvent) {
    e?.preventDefault();
    if (busy || !inputQuestion.trim()) return;
    const question = inputQuestion;
    setInputQuestion("");
    await recovery.submit(question);
  }
  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  }
  function startNewConversation() {
    recovery.startNewConversation();
    setInputQuestion("");
    setShowHistory(false);
    textareaRef.current?.focus();
  }

  function toggleEvidence(msgId: string) {
    setExpandedEvidence((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  }

  function formatEvidenceValue(value: unknown): string {
    if (value === null || value === undefined) return "—";
    if (typeof value === "number" || typeof value === "string") {
      const num = Number(value);
      if (!isNaN(num) && Math.abs(num) >= 1) return money(value);
      return String(value);
    }
    if (typeof value === "object") {
      const entries = Object.entries(value);
      return entries
        .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
        .join(", ");
    }
    return String(value);
  }

  return (
    <div className="coach-container">
      {/* Top Header & Session Controls */}
      <div className="coach-header">
        <div className="coach-header-title">
          <h2>{t("PorerHishab Financial Coach")}</h2>
          <p className="coach-header-sub">
            {t(
              "Personalized, evidence-grounded financial guidance based on your records.",
            )}
          </p>
        </div>

        <div className="coach-header-actions">
          <button
            type="button"
            className="ghost coach-history-btn"
            onClick={() => setShowHistory((prev) => !prev)}
            aria-label={t("Saved chats")}
            title={t("Saved chats")}
          >
            <History size={18} />
            <span>{t("Saved chats")}</span>
          </button>
          <button
            type="button"
            className="secondary coach-new-chat-btn"
            onClick={startNewConversation}
          >
            <PlusCircle size={16} />
            <span>{t("New chat")}</span>
          </button>
        </div>
      </div>

      {/* Conversations Drawer */}
      {showHistory && (
        <div
          className="coach-history-drawer"
          role="region"
          aria-label={t("Saved chats")}
        >
          <div className="coach-history-header">
            <h4>{t("Recent conversations")}</h4>
          </div>
          {conversations.length === 0 && (
            <p className="coach-empty-notice">{t("No conversations found.")}</p>
          )}
          <ul className="coach-history-list">
            {conversations.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={`coach-history-item ${c.id === conversationId ? "active" : ""}`}
                  onClick={() => {
                    void selectConversation(c.id);
                    setShowHistory(false);
                  }}
                >
                  <span className="coach-history-title">{c.title}</span>
                  <span className="coach-history-date">
                    {new Date(c.updated_at).toLocaleDateString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {recovery.moreConversations && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void recovery.loadMoreConversations()}
            >
              {t("Load more conversations")}
            </button>
          )}
        </div>
      )}

      {/* Message Thread */}
      <div
        className="coach-thread"
        role="log"
        aria-live="polite"
        aria-label={t("Conversation messages")}
      >
        {messages.length === 0 && (
          <div className="coach-empty-state">
            <div className="coach-empty-hero">
              <Bot size={40} className="coach-hero-icon" />
              <h3>{t("What would you like to explore?")}</h3>
              <p>
                {t(
                  "Ask questions about your spending, upcoming cashflow, savings targets, or purchasing affordability.",
                )}
              </p>
            </div>
            <div className="coach-starters-grid">
              {STARTERS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="coach-starter-btn"
                  onClick={() => {
                    setInputQuestion(s);
                    textareaRef.current?.focus();
                  }}
                >
                  <span>{uiLabel(s)}</span>
                  <ArrowUpRight size={16} />
                </button>
              ))}
            </div>
          </div>
        )}

        {recovery.hasMore && (
          <button
            type="button"
            disabled={busy || (!!recovery.pending && !recovery.retrySafe)}
            onClick={() => void recovery.loadOlder()}
          >
            {t("Load older messages")}
          </button>
        )}
        {messages.some((m) => m.role === "assistant") && (
          <p className="source">
            {t(
              "Saved answers describe records at the time they were generated. Ask a new question for current finances.",
            )}
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`coach-message-row ${m.role === "user" ? "user-row" : "asst-row"}`}
          >
            <div className="coach-avatar">
              {m.role === "user" ? (
                <UserIcon size={18} aria-hidden="true" />
              ) : (
                <Bot size={18} aria-hidden="true" />
              )}
            </div>

            <div
              className={`coach-bubble ${m.role === "user" ? "user-bubble" : "asst-bubble"} ${m.status === "failed" ? "msg-failed" : ""}`}
            >
              {/* Message Role Label */}
              <div className="coach-bubble-author">
                <strong>
                  {m.role === "user" ? t("You") : t("Financial Coach")}
                </strong>
                {m.status === "pending" && (
                  <span role="status">{t("Still processing")}</span>
                )}
                {m.status === "unknown" && (
                  <span role="status">{t("Status unknown")}</span>
                )}
                {m.status === "failed" && (
                  <span
                    className="coach-status-tag failed"
                    style={{
                      marginLeft: "8px",
                      color: "var(--danger, #e53e3e)",
                      fontSize: "0.75rem",
                    }}
                  >
                    ({t("Failed")})
                  </span>
                )}
                {m.intent && m.intent !== "unknown" && (
                  <span className="coach-intent-pill">{uiLabel(m.intent)}</span>
                )}
              </div>

              {/* Summary pill if available */}
              {m.summary && (
                <div className="coach-summary-badge">
                  <Lightbulb size={14} aria-hidden="true" />
                  <span>{m.summary}</span>
                </div>
              )}

              {/* Main Answer prose */}
              <p className="coach-answer-text">{m.text}</p>

              {/* Warnings / Caveats */}
              {m.warnings && m.warnings.length > 0 && (
                <div className="coach-warnings-list" role="alert">
                  {m.warnings.map((w, idx) => (
                    <div key={idx} className="coach-warning-item">
                      <AlertTriangle size={15} aria-hidden="true" />
                      <span>{w.message}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Suggested Actions */}
              {m.actions && m.actions.length > 0 && (
                <div className="coach-actions-box">
                  <div className="coach-actions-header">
                    <span className="coach-actions-title">
                      {t("Suggested Next Steps")}
                    </span>
                    <small className="coach-disclaimer-sub">
                      {t("(Suggestions for review; not executed transactions)")}
                    </small>
                  </div>
                  <div className="coach-action-items">
                    {m.actions.map((act) => (
                      <div key={act.action_id} className="coach-action-card">
                        <div className="coach-action-badge">
                          P{act.priority}
                        </div>
                        <div className="coach-action-info">
                          <strong>{act.title}</strong>
                          <p>{act.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Verified Evidence Drawer */}
              {m.evidence && m.evidence.length > 0 && (
                <div className="coach-evidence-section">
                  <button
                    type="button"
                    className="coach-evidence-toggle"
                    onClick={() => toggleEvidence(m.id)}
                    aria-expanded={!!expandedEvidence[m.id]}
                  >
                    <span>
                      {t("Verified Evidence used")}{" "}
                      <strong>({m.evidence.length})</strong>
                    </span>
                    {expandedEvidence[m.id] ? (
                      <ChevronUp size={16} />
                    ) : (
                      <ChevronDown size={16} />
                    )}
                  </button>

                  {expandedEvidence[m.id] && (
                    <div className="coach-evidence-grid">
                      {m.evidence.map((ev) => (
                        <div
                          key={ev.evidence_id}
                          className="coach-evidence-card"
                        >
                          <div className="coach-evidence-meta">
                            <span className="coach-evidence-label">
                              {ev.label}
                            </span>
                            <span
                              className={`coach-type-tag ${ev.evidence_type.toLowerCase()}`}
                            >
                              {ev.evidence_type === "estimate"
                                ? t("Estimate")
                                : t("Observed Fact")}
                            </span>
                          </div>
                          <div className="coach-evidence-val">
                            <strong>{formatEvidenceValue(ev.value)}</strong>
                            {ev.unit && (
                              <small className="unit">{ev.unit}</small>
                            )}
                          </div>
                          <div className="coach-evidence-source">
                            <small>
                              {t("Source")}: {ev.source}
                            </small>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Data Limitations */}
              {m.limitations && m.limitations.length > 0 && (
                <details className="coach-limitations-details">
                  <summary>{t("Methodology & Limitations")}</summary>
                  <ul>
                    {m.limitations.map((lim, idx) => (
                      <li key={idx}>{lim}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="coach-message-row asst-row">
            <div className="coach-avatar">
              <Bot size={18} aria-hidden="true" />
            </div>
            <div
              className="coach-bubble asst-bubble coach-loading-bubble"
              role="status"
            >
              <span className="coach-loading-spinner" aria-hidden="true" />
              <span>{t("Analyzing records and verifying evidence...")}</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error Notice */}
      {error && (
        <div className="coach-error-bar">
          <ErrorNotice
            message={error}
            retry={
              recovery.retrySafe && !busy
                ? () => void recovery.submit("", true)
                : undefined
            }
          />
        </div>
      )}

      {recovery.pending && !busy && (
        <button type="button" onClick={() => void recovery.checkStatus()}>
          {t("Check request status")}
        </button>
      )}
      {/* Input Form */}
      <form className="coach-input-form" onSubmit={handleSubmit}>
        <div className="coach-input-wrap">
          <textarea
            ref={textareaRef}
            id="coach-question-input"
            value={inputQuestion}
            onChange={(e) => setInputQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            maxLength={1000}
            disabled={busy || (!!recovery.pending && !recovery.retrySafe)}
            placeholder={t(
              "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
            )}
            aria-label={t("Ask your financial coach")}
          />
          <button
            type="submit"
            className="primary coach-send-btn"
            disabled={
              busy ||
              (!!recovery.pending && !recovery.retrySafe) ||
              !inputQuestion.trim()
            }
            aria-label={t("Send question")}
          >
            <span>{busy ? t("Checking...") : t("Send")}</span>
            <ArrowUpRight size={16} />
          </button>
        </div>
        <div className="coach-input-footer">
          <small className="coach-sub-note">
            <ShieldAlert size={12} aria-hidden="true" />
            {t(
              "Read-only financial guidance grounded in your records. PorerHishab does not execute bank operations.",
            )}
          </small>
        </div>
      </form>
    </div>
  );
}
