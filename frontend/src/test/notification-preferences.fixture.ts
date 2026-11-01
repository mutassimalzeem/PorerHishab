import type { NotificationPreference } from "../domain";

export const mockDefaultPreferences: NotificationPreference = {
  id: 1,
  user_id: 101,
  in_app_enabled: true,
  in_app_min_severity: "info",
  email_enabled: false,
  email_consent: false,
  email_consent_at: null,
  email_min_severity: "warning",
  quiet_hours_enabled: false,
  quiet_hours_start: "22:00",
  quiet_hours_end: "07:00",
  timezone: "Asia/Dhaka",
  frequency_mode: "immediate",
  created_at: "2026-11-01T08:00:00Z",
  updated_at: "2026-11-01T08:00:00Z",
};

export const mockCustomPreferences: NotificationPreference = {
  id: 1,
  user_id: 101,
  in_app_enabled: true,
  in_app_min_severity: "critical",
  email_enabled: true,
  email_consent: true,
  email_consent_at: "2026-11-01T09:00:00Z",
  email_min_severity: "critical",
  quiet_hours_enabled: true,
  quiet_hours_start: "23:00",
  quiet_hours_end: "08:00",
  timezone: "Asia/Dhaka",
  frequency_mode: "daily_digest",
  created_at: "2026-11-01T08:00:00Z",
  updated_at: "2026-11-01T09:00:00Z",
};
