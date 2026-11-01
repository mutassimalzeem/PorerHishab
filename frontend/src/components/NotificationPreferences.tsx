import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { t } from "../lib/locale";
import type { NotificationPreference } from "../domain";
import { Section } from "./ui";

export function NotificationPreferences() {
  const [, setPref] = useState<NotificationPreference | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [loadRevision, setLoadRevision] = useState(0);

  // Form states
  const [inAppEnabled, setInAppEnabled] = useState(true);
  const [inAppMinSeverity, setInAppMinSeverity] = useState<"info" | "warning" | "critical">("info");
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [emailConsent, setEmailConsent] = useState(false);
  const [emailMinSeverity, setEmailMinSeverity] = useState<"info" | "warning" | "critical">("warning");
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietHoursStart, setQuietHoursStart] = useState("22:00");
  const [quietHoursEnd, setQuietHoursEnd] = useState("07:00");
  const [timezone, setTimezone] = useState("Asia/Dhaka");
  const [frequencyMode, setFrequencyMode] = useState<"immediate" | "daily_digest" | "off">("immediate");
  const [immediateEnabled, setImmediateEnabled] = useState(true);
  const [dailyDigestEnabled, setDailyDigestEnabled] = useState(false);
  const [dailyDigestTime, setDailyDigestTime] = useState("20:00");

  useEffect(() => {
    let active = true;
    api
      .notificationPreferences()
      .then((data) => {
        if (!active) return;
        setPref(data);
        setInAppEnabled(Boolean(data.in_app_enabled));
        setInAppMinSeverity(
          data.in_app_min_severity === "critical"
            ? "critical"
            : data.in_app_min_severity === "warning" || data.in_app_min_severity === "medium" || data.in_app_min_severity === "high"
            ? "warning"
            : "info"
        );
        setEmailEnabled(Boolean(data.email_enabled));
        setEmailConsent(Boolean(data.email_consent));
        setEmailMinSeverity(
          data.email_min_severity === "critical"
            ? "critical"
            : data.email_min_severity === "warning" || data.email_min_severity === "medium" || data.email_min_severity === "high"
            ? "warning"
            : "info"
        );
        setQuietHoursEnabled(Boolean(data.quiet_hours_enabled));
        setQuietHoursStart(data.quiet_hours_start || "22:00");
        setQuietHoursEnd(data.quiet_hours_end || "07:00");
        setTimezone(data.timezone || "Asia/Dhaka");
        setFrequencyMode(
          data.frequency_mode === "daily_digest"
            ? "daily_digest"
            : data.frequency_mode === "off"
            ? "off"
            : "immediate"
        );
        setImmediateEnabled(data.immediate_enabled !== undefined ? Boolean(data.immediate_enabled) : true);
        setDailyDigestEnabled(Boolean(data.daily_digest_enabled));
        setDailyDigestTime(data.daily_digest_time || "20:00");
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setError(t("Could not load notification preferences. Please try again."));
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadRevision]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSavedSuccess(false);

    try {
      const updated = await api.updateNotificationPreferences({
        in_app_enabled: inAppEnabled,
        in_app_min_severity: inAppMinSeverity,
        email_enabled: emailEnabled,
        email_consent: emailConsent,
        email_min_severity: emailMinSeverity,
        quiet_hours_enabled: quietHoursEnabled,
        quiet_hours_start: quietHoursStart,
        quiet_hours_end: quietHoursEnd,
        timezone,
        frequency_mode: frequencyMode,
        immediate_enabled: immediateEnabled,
        daily_digest_enabled: dailyDigestEnabled,
        daily_digest_time: dailyDigestTime,
      });
      setPref(updated);
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 4000);
    } catch {
      setError(t("Could not save preferences. Please try again."));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Section title={t("Notification preferences")}>
        <p className="muted">{t("Reading notification preferences...")}</p>
      </Section>
    );
  }

  return (
    <Section title={t("Notification preferences")}>
      {error && (
        <div style={{ marginBottom: "16px" }}>
          <p className="error" style={{ color: "#b91c1c", marginBottom: "8px" }}>
            {error}
          </p>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setLoading(true);
              setError(null);
              setLoadRevision((r) => r + 1);
            }}
          >
            {t("Retry")}
          </button>
        </div>
      )}

      {savedSuccess && (
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
          {t("Preferences saved successfully.")}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <dl className="form-grid">
          {/* In-App Notifications */}
          <div>
            <dt>
              <label htmlFor="pref-in-app">{t("In-app notifications")}</label>
            </dt>
            <dd>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <input
                  type="checkbox"
                  id="pref-in-app"
                  checked={inAppEnabled}
                  onChange={(e) => setInAppEnabled(e.target.checked)}
                />
                <label htmlFor="pref-in-app">
                  {t("Show alerts in your notification center")}
                </label>
              </div>
            </dd>
          </div>

          {/* In-App Severity */}
          <div>
            <dt>
              <label htmlFor="pref-in-app-sev">{t("Minimum in-app severity")}</label>
            </dt>
            <dd>
              <select
                id="pref-in-app-sev"
                value={inAppMinSeverity}
                onChange={(e) =>
                  setInAppMinSeverity(e.target.value as "info" | "warning" | "critical")
                }
                disabled={!inAppEnabled}
                style={{ maxWidth: "200px" }}
              >
                <option value="info">{t("Info")}</option>
                <option value="warning">{t("Warning")}</option>
                <option value="critical">{t("Critical")}</option>
              </select>
            </dd>
          </div>

          {/* Email Notifications */}
          <div>
            <dt>
              <label htmlFor="pref-email">{t("Email notifications")}</label>
            </dt>
            <dd>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <input
                  type="checkbox"
                  id="pref-email"
                  checked={emailEnabled}
                  onChange={(e) => setEmailEnabled(e.target.checked)}
                />
                <label htmlFor="pref-email">
                  {t("Send alert notifications to your registered email")}
                </label>
              </div>
            </dd>
          </div>

          {/* Email consent */}
          <div>
            <dt>
              <label htmlFor="pref-email-consent">{t("Email consent")}</label>
            </dt>
            <dd>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
                  <input
                    type="checkbox"
                    id="pref-email-consent"
                    checked={emailConsent}
                    onChange={(e) => setEmailConsent(e.target.checked)}
                    style={{ marginTop: "3px" }}
                  />
                  <label htmlFor="pref-email-consent" style={{ fontSize: "0.85rem", lineHeight: "1.5" }}>
                    {t(
                      "I consent to receiving security and financial alert notifications at my registered email address. PorerHishab will never send marketing or promotional emails."
                    )}
                  </label>
                </div>
                {emailEnabled && !emailConsent && (
                  <p className="muted" style={{ color: "#b91c1c", fontSize: "0.8rem", margin: "4px 0 0 0" }}>
                    {t("Consent is required before email notifications can be sent.")}
                  </p>
                )}
              </div>
            </dd>
          </div>

          {/* Minimum email severity */}
          <div>
            <dt>
              <label htmlFor="pref-email-sev">{t("Minimum email severity")}</label>
            </dt>
            <dd>
              <select
                id="pref-email-sev"
                value={emailMinSeverity}
                onChange={(e) =>
                  setEmailMinSeverity(e.target.value as "info" | "warning" | "critical")
                }
                disabled={!emailEnabled}
                style={{ maxWidth: "200px" }}
              >
                <option value="info">{t("Info")}</option>
                <option value="warning">{t("Warning")}</option>
                <option value="critical">{t("Critical")}</option>
              </select>
            </dd>
          </div>

          {/* Immediate alerts toggle */}
          <div>
            <dt>
              <label htmlFor="pref-immediate">{t("Immediate alerts")}</label>
            </dt>
            <dd>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <input
                    type="checkbox"
                    id="pref-immediate"
                    checked={immediateEnabled}
                    onChange={(e) => setImmediateEnabled(e.target.checked)}
                  />
                  <label htmlFor="pref-immediate">
                    {t("Receive important financial alerts as they happen")}
                  </label>
                </div>
                <p className="muted" style={{ fontSize: "0.8rem", margin: 0 }}>
                  {t("Critical financial safety alerts may still be delivered immediately even if paused.")}
                </p>
              </div>
            </dd>
          </div>

          {/* Daily digest toggle & time */}
          <div>
            <dt>
              <label htmlFor="pref-daily-digest">{t("Daily digest")}</label>
            </dt>
            <dd>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <input
                    type="checkbox"
                    id="pref-daily-digest"
                    checked={dailyDigestEnabled}
                    onChange={(e) => setDailyDigestEnabled(e.target.checked)}
                  />
                  <label htmlFor="pref-daily-digest">
                    {t("Receive one daily summary instead of multiple emails")}
                  </label>
                </div>
                {dailyDigestEnabled && (
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "4px" }}>
                    <label htmlFor="pref-digest-time" style={{ fontSize: "0.85rem" }}>
                      {t("Digest time")}:
                    </label>
                    <input
                      type="text"
                      id="pref-digest-time"
                      value={dailyDigestTime}
                      onChange={(e) => setDailyDigestTime(e.target.value)}
                      placeholder="20:00"
                      style={{ width: "90px" }}
                    />
                    <span className="muted" style={{ fontSize: "0.8rem" }}>
                      ({timezone})
                    </span>
                  </div>
                )}
              </div>
            </dd>
          </div>

          {/* Quiet hours */}
          <div>
            <dt>
              <label htmlFor="pref-quiet-hours">{t("Quiet hours")}</label>
            </dt>
            <dd>
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <input
                    type="checkbox"
                    id="pref-quiet-hours"
                    checked={quietHoursEnabled}
                    onChange={(e) => setQuietHoursEnabled(e.target.checked)}
                  />
                  <label htmlFor="pref-quiet-hours">
                    {t("Pause non-critical notifications during quiet hours")}
                  </label>
                </div>

                {quietHoursEnabled && (
                  <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                      <label htmlFor="pref-quiet-start" style={{ fontSize: "0.8rem" }}>
                        {t("Start time")}
                      </label>
                      <input
                        type="text"
                        id="pref-quiet-start"
                        value={quietHoursStart}
                        onChange={(e) => setQuietHoursStart(e.target.value)}
                        style={{ width: "120px" }}
                      />
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                      <label htmlFor="pref-quiet-end" style={{ fontSize: "0.8rem" }}>
                        {t("End time")}
                      </label>
                      <input
                        type="text"
                        id="pref-quiet-end"
                        value={quietHoursEnd}
                        onChange={(e) => setQuietHoursEnd(e.target.value)}
                        style={{ width: "120px" }}
                      />
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                      <label htmlFor="pref-timezone" style={{ fontSize: "0.8rem" }}>
                        {t("Timezone")}
                      </label>
                      <input
                        type="text"
                        id="pref-timezone"
                        value={timezone}
                        onChange={(e) => setTimezone(e.target.value)}
                        style={{ width: "160px" }}
                      />
                    </div>
                  </div>
                )}
                <p className="muted" style={{ fontSize: "0.8rem", margin: 0 }}>
                  {t("Critical alerts bypass quiet hours to protect your finances.")}
                </p>
              </div>
            </dd>
          </div>

          {/* Legacy Frequency dropdown */}
          <div>
            <dt>
              <label htmlFor="pref-frequency">{t("Notification frequency")}</label>
            </dt>
            <dd>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                <select
                  id="pref-frequency"
                  value={frequencyMode}
                  onChange={(e) =>
                    setFrequencyMode(e.target.value as "immediate" | "daily_digest" | "off")
                  }
                  style={{ maxWidth: "200px" }}
                >
                  <option value="immediate">{t("Immediate")}</option>
                  <option value="daily_digest">{t("Daily digest")}</option>
                  <option value="off">{t("Off")}</option>
                </select>
              </div>
            </dd>
          </div>
        </dl>

        <div style={{ marginTop: "24px" }}>
          <button type="submit" disabled={saving} aria-busy={saving}>
            {saving ? t("Saving preferences...") : t("Save preferences")}
          </button>
        </div>
      </form>
    </Section>
  );
}
