import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { errorMessage } from "./format";
import type { ApiSchemas } from "../generated/api";
import type {
  CoachResponse,
  CoachRequest,
  CoachConversationSummary,
} from "../domain";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: "pending" | "failed" | "success" | "unknown";
  requestId?: string | null;
  intent?: string;
  summary?: string | null;
  claims?: CoachResponse["claims"];
  evidence?: CoachResponse["evidence"];
  actions?: CoachResponse["actions"];
  warnings?: CoachResponse["warnings"];
  limitations?: string[];
}
type Pending = { body: CoachRequest; language: string };
type Detail = ApiSchemas["CoachConversationDetail"];

function savedMessage(m: NonNullable<Detail["messages"]>[number]): ChatMessage {
  return {
    id: `msg_${m.id}`,
    role: m.role as "user" | "assistant",
    text: m.content,
    requestId: m.request_id,
    status:
      m.turn_status === "failed" || m.turn_status === "interrupted"
        ? "failed"
        : m.turn_status === "processing"
          ? "pending"
          : "success",
    intent: m.intent ?? undefined,
    summary: m.summary,
    claims: m.response?.claims ?? (m.claims_json as CoachResponse["claims"]),
    evidence:
      m.response?.evidence ?? (m.evidence_json as CoachResponse["evidence"]),
    actions:
      m.response?.actions ?? (m.actions_json as CoachResponse["actions"]),
    warnings:
      m.response?.warnings ?? (m.warnings_json as CoachResponse["warnings"]),
    limitations: m.response?.limitations ?? m.limitations_json ?? [],
  };
}

export function useCoachRecovery(language: string, ownerId?: number) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrySafe, setRetrySafe] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [conversations, setConversations] = useState<
    CoachConversationSummary[]
  >([]);
  const [moreConversations, setMoreConversations] = useState(false);
  const [beforeId, setBeforeId] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const active = useRef(0);
  const locked = useRef(false);
  const storageKey =
    ownerId === undefined ? null : `porerhishab.coach.${ownerId}`;

  function remember(conv: string | null, requestId?: string | null) {
    if (!storageKey) return;
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({ conversationId: conv, requestId }),
      );
    } catch {
      /* storage is optional */
    }
  }
  async function loadConversations(offset = 0) {
    try {
      const page = await api.coachConversations(10, offset);
      setConversations((prev) =>
        offset
          ? [
              ...prev,
              ...page.items.filter(
                (item) => !prev.some((p) => p.id === item.id),
              ),
            ]
          : page.items,
      );
      setMoreConversations(offset + page.items.length < page.total);
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  function applyDetail(detail: Detail, older = false) {
    setConversationId(detail.id);
    setBeforeId(detail.next_before_id ?? null);
    setHasMore(detail.has_more ?? false);
    const loaded = (detail.messages ?? []).map(savedMessage);
    const last = loaded.at(-1);
    if (!older && last?.role === "user" && !last.requestId)
      last.status = "unknown";
    setMessages((prev) => (older ? [...loaded, ...prev] : loaded));
  }
  async function selectConversation(id: string, older = false) {
    const version = ++active.current;
    locked.current = true;
    setBusy(true);
    setError(null);
    try {
      const detail = await api.coachConversationDetail(
        id,
        older ? (beforeId ?? undefined) : undefined,
      );
      if (version !== active.current) return;
      applyDetail(detail, older);
      if (!older) {
        setPending(null);
        setRetrySafe(false);
        remember(id);
        const incomplete = [...(detail.messages ?? [])]
          .reverse()
          .find((m) => m.role === "user");
        if (incomplete?.request_id && incomplete.turn_status !== "completed")
          await recover(incomplete.request_id, version);
      }
    } catch (e) {
      if (version === active.current) setError(errorMessage(e));
    } finally {
      if (version === active.current) {
        locked.current = false;
        setBusy(false);
      }
    }
  }
  function adopt(response: CoachResponse, question: string, key: string) {
    const conv = response.conversation_id ?? conversationId;
    setConversationId(conv);
    remember(conv);
    setMessages((prev) => {
      const without = prev.filter((m) => m.requestId !== key);
      return [
        ...without,
        {
          id: `${key}:user`,
          requestId: key,
          role: "user",
          text: question,
          status: "success",
        },
        {
          id: `${key}:assistant`,
          requestId: key,
          role: "assistant",
          text: response.answer,
          status: "success",
          intent: response.intent,
          summary: response.summary,
          claims: response.claims,
          evidence: response.evidence,
          actions: response.actions,
          warnings: response.warnings,
          limitations: response.limitations,
        },
      ];
    });
    setPending(null);
    setRetrySafe(false);
    setError(null);
    void loadConversations();
  }
  async function recover(
    key: string,
    version = active.current,
    original?: Pending,
  ) {
    try {
      const turn = await api.coachRequestStatus(key);
      if (version !== active.current) return;
      if (!original) {
        try {
          const detail = await api.coachConversationDetail(
            turn.conversation_id,
          );
          if (version !== active.current) return;
          applyDetail(detail);
        } catch {
          /* The canonical turn is still recoverable if older history is unavailable. */
        }
      }
      setConversationId(turn.conversation_id);
      if (turn.status === "completed" && turn.response) {
        adopt(turn.response, turn.message, key);
        return;
      }
      const next: Pending = {
        body: {
          request_id: key,
          conversation_id: turn.conversation_id,
          message: turn.message,
          schedules_confirmed: turn.schedules_confirmed,
        },
        language: turn.language,
      };
      setPending(next);
      setRetrySafe(turn.retry_safe);
      remember(turn.conversation_id, key);
      setMessages((prev) =>
        prev.some((m) => m.requestId === key)
          ? prev.map((m) =>
              m.requestId === key
                ? {
                    ...m,
                    status: turn.status === "processing" ? "pending" : "failed",
                  }
                : m,
            )
          : [
              ...prev,
              {
                id: `${key}:user`,
                requestId: key,
                role: "user",
                text: turn.message,
                status: turn.status === "processing" ? "pending" : "failed",
              },
            ],
      );
      setError(
        turn.status === "processing"
          ? null
          : "The question is incomplete. No completed answer is available.",
      );
    } catch (e) {
      if (version !== active.current) return;
      // A confirmed missing receipt can be safely sent with the SAME key. A
      // network failure cannot establish a retry state; offer status checking.
      setRetrySafe(e instanceof ApiError && e.status === 404 && !!original);
      if (original) setPending(original);
      setMessages((prev) =>
        prev.map((m) =>
          m.requestId === key ? { ...m, status: "unknown" } : m,
        ),
      );
      setError(errorMessage(e));
    }
  }
  async function submit(question: string, retry = false) {
    if (
      locked.current ||
      busy ||
      (retry && !retrySafe) ||
      (!retry && pending && !retrySafe)
    )
      return;
    const attempt = retry
      ? pending
      : {
          body: {
            message: question.trim(),
            conversation_id: conversationId ?? undefined,
            request_id: crypto.randomUUID(),
          },
          language,
        };
    if (!attempt || !attempt.body.message) return;
    const key = attempt.body.request_id!;
    const version = ++active.current;
    locked.current = true;
    setBusy(true);
    setRetrySafe(false);
    setError(null);
    setPending(attempt);
    remember(conversationId, key);
    setMessages((prev) => [
      ...prev.filter((m) => m.requestId !== key),
      {
        id: `${key}:user`,
        requestId: key,
        role: "user",
        text: attempt.body.message,
        status: "pending",
      },
    ]);
    try {
      const response = await api.coachAsk(attempt.body, attempt.language);
      if (version === active.current)
        adopt(response, attempt.body.message, key);
      else void loadConversations();
    } catch (e) {
      if (version === active.current) {
        setError(errorMessage(e));
        await recover(key, version, attempt);
      } else void loadConversations();
    } finally {
      if (version === active.current) {
        locked.current = false;
        setBusy(false);
      }
    }
  }
  function startNewConversation() {
    active.current++;
    locked.current = false;
    setBusy(false);
    setPending(null);
    setRetrySafe(false);
    setConversationId(null);
    setMessages([]);
    setError(null);
    setBeforeId(null);
    setHasMore(false);
    remember(null);
  }
  useEffect(() => {
    let mounted = true;
    void Promise.resolve().then(async () => {
      if (!mounted) return;
      void loadConversations();
      if (storageKey) {
        try {
          const saved = JSON.parse(
            sessionStorage.getItem(storageKey) ?? "null",
          );
          if (saved?.requestId) {
            const version = ++active.current;
            locked.current = true;
            setBusy(true);
            try {
              await recover(saved.requestId, version);
            } finally {
              if (version === active.current) {
                locked.current = false;
                setBusy(false);
              }
            }
          } else if (saved?.conversationId)
            void selectConversation(saved.conversationId);
        } catch {
          /* malformed or disabled storage */
        }
      }
    });
    const requests = active;
    return () => {
      mounted = false;
      requests.current++;
    };
    // The authenticated owner defines the lifetime; handlers read current props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  return {
    conversationId,
    messages,
    busy,
    error,
    retrySafe,
    pending,
    conversations,
    moreConversations,
    hasMore,
    submit,
    selectConversation,
    startNewConversation,
    loadMoreConversations: () => loadConversations(conversations.length),
    loadOlder: () => conversationId && selectConversation(conversationId, true),
    checkStatus: () =>
      pending?.body.request_id &&
      recover(pending.body.request_id, active.current, pending),
  };
}
