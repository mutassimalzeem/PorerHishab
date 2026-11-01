import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Info,
  Mail,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
} from "lucide-react";
import type { FinancialAlert, NotificationHistoryItem } from "../domain";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { date, errorMessage } from "../lib/format";
import { digits, t, uiLabel } from "../lib/locale";
import { useLanguage } from "../lib/useLanguage";
import { Empty, ErrorNotice, PageHeading, ResourceView } from "../components/ui";

interface AlertsProps {
  onAlertChange?: () => void;
}

type StatusFilter = "all" | "unread" | "active" | "dismissed" | "resolved";
type SeverityFilter = "all" | "critical" | "high" | "medium" | "low";
type HistoryChannelFilter = "all" | "in_app" | "email";

export function Alerts({ onAlertChange }: AlertsProps) {
  useLanguage();
  const [viewMode, setViewMode] = useState<"alerts" | "history">("alerts");
  const [revision, setRevision] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [historyChannel, setHistoryChannel] = useState<HistoryChannelFilter>("all");
  const [evaluating, setEvaluating] = useState(false);
  const [evaluatingDigest, setEvaluatingDigest] = useState(false);
  const [digestSuccessMsg, setDigestSuccessMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedEvidence, setExpandedEvidence] = useState<Record<number, boolean>>({});

  const resource = useResource(
    useCallback(async () => {
      const params: Record<string, string | number | boolean | undefined> = {
        limit: 100,
        offset: 0,
      };
      if (statusFilter === "unread") {
        params.unread_only = true;
      } else if (statusFilter !== "all") {
        params.status = statusFilter;
      }
      if (severityFilter !== "all") {
        params.severity = severityFilter;
      }
      return api.alerts(params);
    }, [statusFilter, severityFilter]),
    revision,
  );

  const historyResource = useResource(
    useCallback(async () => {
      const params: Record<string, string | number | boolean | undefined> = {
        limit: 50,
        offset: 0,
      };
      if (historyChannel !== "all") {
        params.channel = historyChannel;
      }
      return api.notificationHistory(params);
    }, [historyChannel]),
    revision,
  );

  async function handleEvaluate() {
    setEvaluating(true);
    setError(null);
    try {
      await api.evaluateAlerts();
      setRevision((r) => r + 1);
      onAlertChange?.();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setEvaluating(false);
    }
  }

  async function handleEvaluateDigest() {
    setEvaluatingDigest(true);
    setError(null);
    setDigestSuccessMsg(null);
    try {
      const res = await api.evaluateDailyDigest();
      setDigestSuccessMsg(res.message);
      setRevision((r) => r + 1);
      setTimeout(() => setDigestSuccessMsg(null), 5000);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setEvaluatingDigest(false);
    }
  }

  async function handleMarkRead(id: number) {
    try {
      await api.readAlert(id);
      setRevision((r) => r + 1);
      onAlertChange?.();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function handleDismiss(id: number) {
    try {
      await api.dismissAlert(id);
      setRevision((r) => r + 1);
      onAlertChange?.();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function handleActioned(id: number) {
    try {
      await api.actionAlert(id);
      setRevision((r) => r + 1);
      onAlertChange?.();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function handleRestore(id: number) {
    try {
      await api.restoreAlert(id);
      setRevision((r) => r + 1);
      onAlertChange?.();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  function toggleEvidence(id: number) {
    setExpandedEvidence((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function getSeverityBadge(severity: string) {
    switch (severity) {
      case "critical":
        return (
          <span className="badge badge-critical" aria-label={t("Critical")}>
            <ShieldAlert size={14} aria-hidden="true" />
            {t("Critical")}
          </span>
        );
      case "high":
        return (
          <span className="badge badge-high" aria-label={t("High")}>
            <AlertTriangle size={14} aria-hidden="true" />
            {t("High")}
          </span>
        );
      case "medium":
        return (
          <span className="badge badge-medium" aria-label={t("Medium")}>
            <AlertCircle size={14} aria-hidden="true" />
            {t("Medium")}
          </span>
        );
      default:
        return (
          <span className="badge badge-low" aria-label={t("Low")}>
            <Info size={14} aria-hidden="true" />
            {t("Low")}
          </span>
        );
    }
  }

  return (
    <div className="alerts-page">
      <PageHeading
        title={t("Financial Alerts")}
        description={t(
          "Proactive notifications highlighting important financial conditions and changes.",
        )}
        action={
          <div style={{ display: "flex", gap: "8px" }}>
            {viewMode === "history" && (
              <button
                type="button"
                className="button secondary"
                onClick={handleEvaluateDigest}
                disabled={evaluatingDigest}
                aria-busy={evaluatingDigest}
              >
                <Mail size={16} aria-hidden="true" />
                <span>
                  {evaluatingDigest ? t("Evaluating digest...") : t("Evaluate daily digest")}
                </span>
              </button>
            )}
            <button
              type="button"
              className="button secondary"
              onClick={handleEvaluate}
              disabled={evaluating}
              aria-busy={evaluating}
            >
              <RefreshCw
                size={16}
                className={evaluating ? "spinner" : ""}
                aria-hidden="true"
              />
              <span>
                {evaluating ? t("Evaluating...") : t("Evaluate alerts")}
              </span>
            </button>
          </div>
        }
      />

      {error && <ErrorNotice message={error} retry={() => setError(null)} />}

      {digestSuccessMsg && (
        <div
          style={{
            backgroundColor: "#f0fdf4",
            border: "1px solid #bbf7d0",
            color: "#166534",
            padding: "10px 14px",
            borderRadius: "6px",
            marginBottom: "16px",
            fontSize: "0.9rem",
          }}
        >
          {digestSuccessMsg}
        </div>
      )}

      {/* View Mode Selector Tabs */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
        <button
          type="button"
          className={`filter-tab ${viewMode === "alerts" ? "active" : ""}`}
          onClick={() => setViewMode("alerts")}
        >
          {t("Alerts")}
        </button>
        <button
          type="button"
          className={`filter-tab ${viewMode === "history" ? "active" : ""}`}
          onClick={() => setViewMode("history")}
        >
          {t("Notification history")}
        </button>
      </div>

      {viewMode === "alerts" ? (
        <>
          <div className="alerts-controls" role="region" aria-label={t("Alerts")}>
            <div className="filter-group" role="tablist" aria-label={t("Status")}>
              {(["all", "unread", "active", "dismissed", "resolved"] as const).map(
                (s) => (
                  <button
                    key={s}
                    role="tab"
                    aria-selected={statusFilter === s}
                    className={`filter-tab ${statusFilter === s ? "active" : ""}`}
                    onClick={() => setStatusFilter(s)}
                  >
                    {s === "all"
                      ? t("All")
                      : s === "unread"
                        ? t("Unread")
                        : s === "active"
                          ? t("Active")
                          : s === "dismissed"
                            ? t("Dismissed")
                            : t("Resolved")}
                  </button>
                ),
              )}
            </div>

            <div className="severity-filter-group" aria-label={t("Severity")}>
              {(["all", "critical", "high", "medium", "low"] as const).map((sev) => (
                <button
                  key={sev}
                  type="button"
                  className={`severity-pill ${severityFilter === sev ? "active" : ""}`}
                  onClick={() => setSeverityFilter(sev)}
                >
                  {sev === "all"
                    ? t("All")
                    : sev === "critical"
                      ? t("Critical")
                      : sev === "high"
                        ? t("High")
                        : sev === "medium"
                          ? t("Medium")
                          : t("Low")}
                </button>
              ))}
            </div>
          </div>

          <ResourceView resource={resource} label={t("Reading alerts...")}>
            {(data) => {
              if (data.items.length === 0) {
                let emptyMsg = t("No alerts match the selected filter.");
                if (statusFilter === "unread") {
                  emptyMsg = t("You're all caught up! No unread financial alerts.");
                } else if (statusFilter === "all" && severityFilter === "all") {
                  emptyMsg = t(
                    "No active alerts. Your financial position has no critical warnings.",
                  );
                }
                return (
                  <Empty title={t("No alerts found")}>
                    {emptyMsg}
                  </Empty>
                );
              }

              return (
                <div className="alerts-list">
                  {data.items.map((alert: FinancialAlert) => (
                    <article
                      key={alert.id}
                      className={`alert-card ${alert.severity} ${!alert.is_read ? "unread" : ""}`}
                    >
                      <header className="alert-card-header">
                        <div className="alert-header-left">
                          {getSeverityBadge(alert.severity)}
                          {!alert.is_read && (
                            <span className="unread-dot-badge">
                              {t("Unread")}
                            </span>
                          )}
                          {(alert.occurrence_count ?? 1) > 1 ? (
                            <span className="occurrence-badge">
                              <Clock size={12} aria-hidden="true" />
                              {t("Detected")}{" "}
                              {digits(alert.occurrence_count ?? 1)}{" "}
                              {(alert.occurrence_count ?? 1) === 1 ? t("time") : t("times")}
                            </span>
                          ) : null}
                        </div>
                        <div className="alert-header-right">
                          <time dateTime={alert.last_detected_at}>
                            {t("Last detected")}: {date(alert.last_detected_at.split("T")[0])}
                          </time>
                          <span className={`status-pill ${alert.status}`}>
                            {alert.status === "active"
                              ? t("Active")
                              : alert.status === "dismissed"
                                ? t("Dismissed")
                                : t("Resolved")}
                          </span>
                        </div>
                      </header>

                      <div className="alert-card-body">
                        <h3 className="alert-title">{uiLabel(alert.title)}</h3>
                        <p className="alert-message">{uiLabel(alert.message)}</p>

                        {alert.recommended_action && (
                          <div className="alert-action-box">
                            <strong>{t("Recommended action")}:</strong>
                            <p>{uiLabel(alert.recommended_action)}</p>
                            {alert.action_url && (
                              <Link
                                to={alert.action_url}
                                className="button secondary small alert-nav-link"
                              >
                                <span>
                                  {alert.action_url === "/cashflow"
                                    ? t("Open Cashflow")
                                    : alert.action_url === "/accounts"
                                      ? t("Open Accounts")
                                      : alert.action_url === "/plans"
                                        ? t("Open Plans")
                                        : alert.action_url === "/transactions"
                                          ? t("Open Transactions")
                                          : t("Open Cashflow")}
                                </span>
                                <ArrowRight size={14} aria-hidden="true" />
                              </Link>
                            )}
                          </div>
                        )}

                        {alert.actioned_at && (
                          <div className="actioned-notice" role="note">
                            <CheckCircle size={14} aria-hidden="true" />
                            <span>
                              {t("Action reported on")}{" "}
                              {date(alert.actioned_at.split("T")[0])}.{" "}
                              {t(
                                "Underlying condition is not automatically verified as resolved.",
                              )}
                            </span>
                          </div>
                        )}

                        {alert.evidence && Object.keys(alert.evidence).length > 0 && (
                          <div className="alert-evidence-section">
                            <button
                              type="button"
                              className="evidence-toggle-button"
                              onClick={() => toggleEvidence(alert.id)}
                              aria-expanded={Boolean(expandedEvidence[alert.id])}
                            >
                              <span>{t("Evidence snapshot")}</span>
                              {expandedEvidence[alert.id] ? (
                                <ChevronUp size={15} aria-hidden="true" />
                              ) : (
                                <ChevronDown size={15} aria-hidden="true" />
                              )}
                            </button>

                            {expandedEvidence[alert.id] && (
                              <div className="evidence-panel">
                                <p className="evidence-disclaimer">
                                  {t(
                                    "This snapshot reflects conditions observed during the latest evaluation, not a live bank balance.",
                                  )}
                                </p>
                                <dl className="evidence-list">
                                  {Object.entries(alert.evidence).map(([k, v]) => (
                                    <div key={k} className="evidence-item">
                                      <dt>{k.replace(/_/g, " ")}:</dt>
                                      <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
                                    </div>
                                  ))}
                                </dl>
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      <footer className="alert-card-footer">
                        <div className="footer-actions">
                          {!alert.is_read && (
                            <button
                              type="button"
                              className="button small secondary"
                              onClick={() => handleMarkRead(alert.id)}
                            >
                              {t("Mark as read")}
                            </button>
                          )}
                          {!alert.actioned_at && alert.status === "active" && (
                            <button
                              type="button"
                              className="button small secondary"
                              onClick={() => handleActioned(alert.id)}
                            >
                              {t("I took this action")}
                            </button>
                          )}
                          {alert.status === "active" && (
                            <button
                              type="button"
                              className="button small tertiary"
                              onClick={() => handleDismiss(alert.id)}
                            >
                              {t("Dismiss")}
                            </button>
                          )}
                          {alert.status === "dismissed" && (
                            <button
                              type="button"
                              className="button small secondary"
                              onClick={() => handleRestore(alert.id)}
                            >
                              <RotateCcw size={14} aria-hidden="true" />
                              {t("Restore")}
                            </button>
                          )}
                        </div>
                      </footer>
                    </article>
                  ))}
                </div>
              );
            }}
          </ResourceView>
        </>
      ) : (
        /* Notification History View */
        <div className="notification-history-view">
          <div className="alerts-controls" role="region" aria-label={t("Notification history")}>
            <div className="filter-group" role="tablist" aria-label={t("Channel")}>
              {(["all", "in_app", "email"] as const).map((ch) => (
                <button
                  key={ch}
                  role="tab"
                  aria-selected={historyChannel === ch}
                  className={`filter-tab ${historyChannel === ch ? "active" : ""}`}
                  onClick={() => setHistoryChannel(ch)}
                >
                  {ch === "all"
                    ? t("All")
                    : ch === "in_app"
                      ? t("In-app")
                      : t("Email")}
                </button>
              ))}
            </div>
          </div>

          <ResourceView resource={historyResource} label={t("Reading notification history...")}>
            {(data) => {
              if (data.items.length === 0) {
                return (
                  <Empty title={t("No notifications found")}>
                    {t("No notification deliveries recorded yet.")}
                  </Empty>
                );
              }

              return (
                <div className="notification-history-list" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  {data.items.map((item: NotificationHistoryItem) => {
                    const statusColor =
                      item.status === "SENT"
                        ? "#16a34a"
                        : item.status === "PENDING" || item.status === "PROCESSING"
                          ? "#ea580c"
                          : item.status === "SUPPRESSED"
                            ? "#64748b"
                            : "#dc2626";

                    return (
                      <div
                        key={item.id}
                        className="notification-item-card"
                        style={{
                          background: "#ffffff",
                          border: "1px solid #e2e8f0",
                          borderRadius: "8px",
                          padding: "14px 18px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          flexWrap: "wrap",
                          gap: "10px",
                        }}
                      >
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                              {item.notification_event === "DAILY_DIGEST"
                                ? t("Daily digest")
                                : item.notification_event}
                            </span>
                            <span className="badge" style={{ fontSize: "0.75rem", textTransform: "uppercase" }}>
                              {item.channel}
                            </span>
                            <span
                              style={{
                                color: statusColor,
                                fontWeight: 600,
                                fontSize: "0.8rem",
                                textTransform: "uppercase",
                              }}
                            >
                              {item.status}
                            </span>
                          </div>
                          {item.failure_reason && (
                            <p style={{ color: "#dc2626", fontSize: "0.8rem", margin: 0 }}>
                              {item.failure_reason}
                            </p>
                          )}
                        </div>

                        <div style={{ fontSize: "0.8rem", color: "#64748b", textAlign: "right" }}>
                          <div>{date(item.created_at)}</div>
                          {item.delivered_at && (
                            <div style={{ color: "#16a34a" }}>
                              {t("Delivered")}: {date(item.delivered_at)}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            }}
          </ResourceView>
        </div>
      )}
    </div>
  );
}
