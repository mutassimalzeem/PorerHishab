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
import { api } from "../lib/api";
import { errorMessage, money } from "../lib/format";
import { ErrorNotice } from "./ui";
import type {
  CoachAction,
  CoachClaim,
  CoachConversationSummary,
  CoachEvidence,
  CoachResponse,
  CoachWarning,
} from "../domain";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: "pending" | "failed" | "success";
  intent?: string;
  summary?: string | null;
  claims?: CoachClaim[];
  evidence?: CoachEvidence[];
  actions?: CoachAction[];
  warnings?: CoachWarning[];
  limitations?: string[];
  isClarification?: boolean;
}

const STARTERS = [
  "Where did my money go this month?",
  "What is my cashflow and future balance?",
  "Can I afford to purchase 15,000 BDT?",
  "Where can I save more money?",
  "How is my savings goal progress?",
  "How healthy are my finances?",
];

export function FinancialCoach() {
  const { language } = useLanguage();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuestion, setInputQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string>("");
  const [expandedEvidence, setExpandedEvidence] = useState<Record<string, boolean>>({});
  const [conversations, setConversations] = useState<CoachConversationSummary[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const busyRef = useRef(false);
  const activeRequestIdRef = useRef<number>(0);

  // Load user's conversations list on mount
  useEffect(() => {
    loadConversations();
  }, []);

  // Scroll to bottom when messages update
  useEffect(() => {
    if (
      messagesEndRef.current &&
      typeof messagesEndRef.current.scrollIntoView === "function"
    ) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, busy]);

  async function loadConversations() {
    try {
      const page = await api.coachConversations(10);
      setConversations(page.items);
    } catch {
      // Non-critical; history can be retried
    }
  }

  async function selectConversation(id: string) {
    activeRequestIdRef.current++;
    busyRef.current = false;
    setBusy(true);
    setError(null);
    try {
      const detail = await api.coachConversationDetail(id);
      setConversationId(detail.id);
      const loaded: ChatMessage[] = (detail.messages || []).map((m) => ({
        id: `msg_${m.id}`,
        role: m.role as "user" | "assistant",
        text: m.content,
        status: "success",
        intent: m.intent || undefined,
        summary: m.summary || null,
        claims: m.claims_json as CoachClaim[] | undefined,
        actions: m.actions_json as CoachAction[] | undefined,
        evidence: m.evidence_json as CoachEvidence[] | undefined,
        warnings: m.warnings_json as CoachWarning[] | undefined,
        limitations: m.limitations_json || [],
      }));
      setMessages(loaded);
      setShowHistory(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function startNewConversation() {
    activeRequestIdRef.current++;
    busyRef.current = false;
    setBusy(false);
    setConversationId(null);
    setMessages([]);
    setInputQuestion("");
    setError(null);
    setShowHistory(false);
    textareaRef.current?.focus();
  }

  async function handleSubmit(e?: FormEvent, overrideQuestion?: string) {
    if (e) e.preventDefault();
    if (busy || busyRef.current) return;
    const q = (overrideQuestion ?? inputQuestion).trim();
    if (!q) return;

    busyRef.current = true;
    setBusy(true);
    setError(null);
    setLastQuestion(q);

    const isRetry = Boolean(overrideQuestion);
    let targetMsgId: string;

    if (isRetry) {
      // Find the last user message to update instead of appending duplicate
      const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
      if (lastUserMsg) {
        targetMsgId = lastUserMsg.id;
        setMessages((prev) =>
          prev.map((m) => (m.id === targetMsgId ? { ...m, status: "pending" as const } : m)),
        );
      } else {
        targetMsgId = `user_${Date.now()}`;
        setMessages((prev) => [
          ...prev,
          { id: targetMsgId, role: "user", text: q, status: "pending" as const },
        ]);
      }
    } else {
      targetMsgId = `user_${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        { id: targetMsgId, role: "user", text: q, status: "pending" as const },
      ]);
      setInputQuestion("");
    }

    const currentReqId = ++activeRequestIdRef.current;

    try {
      const resp: CoachResponse = await api.coachAsk(
        {
          message: q,
          conversation_id: conversationId || undefined,
        },
        language === "bn" ? "bn" : "en",
      );

      // If user switched conversations while request was in-flight, discard
      if (currentReqId !== activeRequestIdRef.current) {
        return;
      }

      if (resp.conversation_id && resp.conversation_id !== conversationId) {
        setConversationId(resp.conversation_id);
        loadConversations();
      }

      // Mark the user message as successfully submitted
      setMessages((prev) =>
        prev.map((m) => (m.id === targetMsgId ? { ...m, status: "success" as const } : m)),
      );

      const asstMessage: ChatMessage = {
        id: `asst_${Date.now()}`,
        role: "assistant",
        text: resp.answer,
        status: "success",
        intent: resp.intent,
        summary: resp.summary,
        claims: resp.claims,
        evidence: resp.evidence,
        actions: resp.actions,
        warnings: resp.warnings,
        limitations: resp.limitations,
        isClarification:
          resp.intent === "unknown" ||
          (resp.warnings || []).some((w) => w.code === "CLARIFICATION_REQUIRED"),
      };

      setMessages((prev) => [...prev, asstMessage]);
    } catch (err) {
      if (currentReqId !== activeRequestIdRef.current) {
        return;
      }
      // Mark the user message as failed
      setMessages((prev) =>
        prev.map((m) => (m.id === targetMsgId ? { ...m, status: "failed" as const } : m)),
      );
      setError(errorMessage(err));
    } finally {
      if (currentReqId === activeRequestIdRef.current) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function retryLast() {
    if (!lastQuestion) return;
    handleSubmit(undefined, lastQuestion);
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
        <div className="coach-history-drawer" role="region" aria-label={t("Saved chats")}>
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
                  onClick={() => selectConversation(c.id)}
                >
                  <span className="coach-history-title">{c.title}</span>
                  <span className="coach-history-date">
                    {new Date(c.updated_at).toLocaleDateString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
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

            <div className={`coach-bubble ${m.role === "user" ? "user-bubble" : "asst-bubble"} ${m.status === "failed" ? "msg-failed" : ""}`}>
              {/* Message Role Label */}
              <div className="coach-bubble-author">
                <strong>{m.role === "user" ? t("You") : t("Financial Coach")}</strong>
                {m.status === "failed" && (
                  <span className="coach-status-tag failed" style={{ marginLeft: "8px", color: "var(--danger, #e53e3e)", fontSize: "0.75rem" }}>
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
                    <span className="coach-actions-title">{t("Suggested Next Steps")}</span>
                    <small className="coach-disclaimer-sub">
                      {t("(Suggestions for review; not executed transactions)")}
                    </small>
                  </div>
                  <div className="coach-action-items">
                    {m.actions.map((act) => (
                      <div key={act.action_id} className="coach-action-card">
                        <div className="coach-action-badge">P{act.priority}</div>
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
                        <div key={ev.evidence_id} className="coach-evidence-card">
                          <div className="coach-evidence-meta">
                            <span className="coach-evidence-label">{ev.label}</span>
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
                            {ev.unit && <small className="unit">{ev.unit}</small>}
                          </div>
                          <div className="coach-evidence-source">
                            <small>{t("Source")}: {ev.source}</small>
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
            <div className="coach-bubble asst-bubble coach-loading-bubble" role="status">
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
          <ErrorNotice message={error} retry={retryLast} />
        </div>
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
            disabled={busy}
            placeholder={t(
              "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
            )}
            aria-label={t("Ask your financial coach")}
          />
          <button
            type="submit"
            className="primary coach-send-btn"
            disabled={busy || !inputQuestion.trim()}
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
