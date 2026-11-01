import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Alerts } from "../pages/Alerts";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import {
  mockAlertCritical,
  mockAlertDismissed,
  mockAlertHigh,
  mockAlertList,
} from "./alerts.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});

function renderAlerts(onAlertChange?: () => void) {
  return render(
    <MemoryRouter>
      <Alerts onAlertChange={onAlertChange} />
    </MemoryRouter>,
  );
}

it("renders alerts list with severity badges, timestamps, and action links", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);

  renderAlerts();

  expect(await screen.findByText(mockAlertCritical.title)).toBeInTheDocument();
  expect(screen.getByText(mockAlertHigh.title)).toBeInTheDocument();
  expect(screen.getByText(mockAlertDismissed.title)).toBeInTheDocument();

  // Severity badges
  expect(screen.getByLabelText("Critical")).toBeInTheDocument();
  expect(screen.getByLabelText("High")).toBeInTheDocument();

  // Occurrence badge
  expect(screen.getByText(/Detected 2 times/i)).toBeInTheDocument();

  // Recommended action and links
  expect(screen.getByText(mockAlertCritical.recommended_action)).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Open Cashflow/i }).length).toBeGreaterThan(0);
});

it("toggles evidence snapshot drawer with disclaimer", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);

  renderAlerts();

  const toggleButtons = await screen.findAllByRole("button", {
    name: /Evidence snapshot/i,
  });
  expect(toggleButtons.length).toBeGreaterThan(0);

  // Click first evidence toggle
  await userEvent.click(toggleButtons[0]);

  // Evidence disclaimer and values should appear
  expect(
    screen.getByText(
      /This snapshot reflects conditions observed during the latest evaluation, not a live bank balance/i,
    ),
  ).toBeInTheDocument();
  expect(screen.getByText("minimum projected balance:")).toBeInTheDocument();
  expect(screen.getByText("-1500.00")).toBeInTheDocument();

  // Toggle off
  await userEvent.click(toggleButtons[0]);
  expect(
    screen.queryByText(
      /This snapshot reflects conditions observed during the latest evaluation, not a live bank balance/i,
    ),
  ).not.toBeInTheDocument();
});

it("filters by status and severity tabs", async () => {
  const alertsSpy = vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);

  renderAlerts();
  await screen.findByText(mockAlertCritical.title);

  // Click Unread tab
  await userEvent.click(screen.getByRole("tab", { name: t("Unread") }));
  expect(alertsSpy).toHaveBeenCalledWith(
    expect.objectContaining({ unread_only: true }),
  );

  // Click Critical severity pill
  await userEvent.click(screen.getByRole("button", { name: t("Critical") }));
  expect(alertsSpy).toHaveBeenCalledWith(
    expect.objectContaining({ severity: "critical" }),
  );
});

it("marks an alert as read and notifies parent", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);
  const readSpy = vi.spyOn(api, "readAlert").mockResolvedValue({
    ...mockAlertCritical,
    is_read: true,
    read_at: "2026-11-01T11:00:00Z",
  });
  const onChange = vi.fn();

  renderAlerts(onChange);

  const card = (await screen.findByText(mockAlertCritical.title)).closest(
    "article",
  )!;
  const markReadBtn = within(card).getByRole("button", { name: t("Mark as read") });
  await userEvent.click(markReadBtn);

  expect(readSpy).toHaveBeenCalledWith(mockAlertCritical.id);
  expect(onChange).toHaveBeenCalled();
});

it("dismisses an active alert", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);
  const dismissSpy = vi.spyOn(api, "dismissAlert").mockResolvedValue({
    ...mockAlertCritical,
    status: "dismissed",
    dismissed_at: "2026-11-01T11:00:00Z",
  });
  const onChange = vi.fn();

  renderAlerts(onChange);

  const card = (await screen.findByText(mockAlertCritical.title)).closest(
    "article",
  )!;
  const dismissBtn = within(card).getByRole("button", { name: t("Dismiss") });
  await userEvent.click(dismissBtn);

  expect(dismissSpy).toHaveBeenCalledWith(mockAlertCritical.id);
  expect(onChange).toHaveBeenCalled();
});

it("marks an alert as actioned with disclaimer", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);
  const actionSpy = vi.spyOn(api, "actionAlert").mockResolvedValue({
    ...mockAlertCritical,
    actioned_at: "2026-11-01T11:00:00Z",
  });
  const onChange = vi.fn();

  renderAlerts(onChange);

  const card = (await screen.findByText(mockAlertCritical.title)).closest(
    "article",
  )!;
  const actionBtn = within(card).getByRole("button", {
    name: t("I took this action"),
  });
  await userEvent.click(actionBtn);

  expect(actionSpy).toHaveBeenCalledWith(mockAlertCritical.id);
  expect(onChange).toHaveBeenCalled();
});

it("restores a dismissed alert", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);
  const restoreSpy = vi.spyOn(api, "restoreAlert").mockResolvedValue({
    ...mockAlertDismissed,
    status: "active",
    dismissed_at: null,
  });
  const onChange = vi.fn();

  renderAlerts(onChange);

  const card = (await screen.findByText(mockAlertDismissed.title)).closest(
    "article",
  )!;
  const restoreBtn = within(card).getByRole("button", { name: t("Restore") });
  await userEvent.click(restoreBtn);

  expect(restoreSpy).toHaveBeenCalledWith(mockAlertDismissed.id);
  expect(onChange).toHaveBeenCalled();
});

it("triggers alert evaluation on demand", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);
  const evalSpy = vi.spyOn(api, "evaluateAlerts").mockResolvedValue({
    created: 1,
    updated: 0,
    resolved: 0,
    unchanged: 2,
    evaluated_at: "2026-11-01T12:00:00Z",
  });
  const onChange = vi.fn();

  renderAlerts(onChange);

  const evalBtn = await screen.findByRole("button", {
    name: t("Evaluate alerts"),
  });
  await userEvent.click(evalBtn);

  expect(evalSpy).toHaveBeenCalled();
  expect(onChange).toHaveBeenCalled();
});

it("renders empty state correctly when there are no alerts", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  });

  renderAlerts();

  expect(await screen.findByText(t("No alerts found"))).toBeInTheDocument();
  expect(
    screen.getByText(
      t("No active alerts. Your financial position has no critical warnings."),
    ),
  ).toBeInTheDocument();
});

it("renders properly in Bengali", async () => {
  setLanguage("bn");
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);

  renderAlerts();

  expect(await screen.findByText(t("Financial Alerts"))).toBeInTheDocument();
  expect(screen.getByText(t("Evaluate alerts"))).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: t("All") })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: t("Unread") })).toBeInTheDocument();
});

it("switches to notification history view and renders deliveries", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);
  const historySpy = vi.spyOn(api, "notificationHistory").mockResolvedValue({
    items: [
      {
        id: 1,
        user_id: 101,
        channel: "email",
        notification_event: "DAILY_DIGEST",
        status: "SENT",
        alert_id: null,
        digest_id: 10,
        delivered_at: "2026-11-01T20:00:00Z",
        created_at: "2026-11-01T20:00:00Z",
        failure_reason: null,
      },
      {
        id: 2,
        user_id: 101,
        channel: "in_app",
        notification_event: "ALERT_CREATED",
        status: "SENT",
        alert_id: 42,
        digest_id: null,
        delivered_at: "2026-11-01T10:00:00Z",
        created_at: "2026-11-01T10:00:00Z",
        failure_reason: null,
      },
    ],
    total: 2,
    limit: 50,
    offset: 0,
  });

  renderAlerts();

  const historyTab = await screen.findByRole("button", {
    name: t("Notification history"),
  });
  await userEvent.click(historyTab);

  expect(historySpy).toHaveBeenCalled();
  expect(await screen.findByText(t("Daily digest"))).toBeInTheDocument();
  expect(screen.getByText("ALERT_CREATED")).toBeInTheDocument();
});

it("evaluates daily digest on demand from notification history view", async () => {
  vi.spyOn(api, "alerts").mockResolvedValue(mockAlertList);
  vi.spyOn(api, "notificationHistory").mockResolvedValue({
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  });
  const digestEvalSpy = vi.spyOn(api, "evaluateDailyDigest").mockResolvedValue({
    status: "generated",
    digest_id: 12,
    item_count: 2,
    local_date: "2026-11-01",
    message: "Daily digest generated with 2 alerts.",
  });

  renderAlerts();

  const historyTab = await screen.findByRole("button", {
    name: t("Notification history"),
  });
  await userEvent.click(historyTab);

  const evalDigestBtn = await screen.findByRole("button", {
    name: t("Evaluate daily digest"),
  });
  await userEvent.click(evalDigestBtn);

  expect(digestEvalSpy).toHaveBeenCalled();
  expect(
    await screen.findByText("Daily digest generated with 2 alerts."),
  ).toBeInTheDocument();
});
