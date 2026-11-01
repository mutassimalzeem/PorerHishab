import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationPreferences } from "../components/NotificationPreferences";
import { api } from "../lib/api";
import { setLanguage } from "../lib/locale";
import {
  mockCustomPreferences,
  mockDefaultPreferences,
} from "./notification-preferences.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});

it("renders loading state then populates default preferences", async () => {
  vi.spyOn(api, "notificationPreferences").mockResolvedValue(mockDefaultPreferences);

  render(<NotificationPreferences />);

  expect(screen.getByText("Reading notification preferences...")).toBeInTheDocument();

  expect(await screen.findByRole("heading", { name: "Notification preferences" })).toBeInTheDocument();
  expect(screen.getByLabelText("In-app notifications")).toBeChecked();
  expect(screen.getByLabelText("Email notifications")).not.toBeChecked();
  expect(screen.getByLabelText(/I consent to receiving security and financial alert notifications/i)).not.toBeChecked();
  expect(screen.getByLabelText("Pause non-critical notifications during quiet hours")).not.toBeChecked();
});

it("submits updated preferences and displays success notice", async () => {
  vi.spyOn(api, "notificationPreferences").mockResolvedValue(mockDefaultPreferences);
  const updateSpy = vi
    .spyOn(api, "updateNotificationPreferences")
    .mockResolvedValue(mockCustomPreferences);

  render(<NotificationPreferences />);

  expect(await screen.findByRole("heading", { name: "Notification preferences" })).toBeInTheDocument();

  // Toggle email
  const emailCheckbox = screen.getByLabelText("Email notifications");
  await userEvent.click(emailCheckbox);

  // Toggle email consent
  const consentCheckbox = screen.getByLabelText(/I consent to receiving security and financial alert notifications/i);
  await userEvent.click(consentCheckbox);

  // Submit form
  const saveButton = screen.getByRole("button", { name: "Save preferences" });
  await userEvent.click(saveButton);

  expect(updateSpy).toHaveBeenCalledWith(
    expect.objectContaining({
      email_enabled: true,
      email_consent: true,
    })
  );

  expect(await screen.findByText("Preferences saved successfully.")).toBeInTheDocument();
});

it("warns when email is enabled without explicit consent", async () => {
  vi.spyOn(api, "notificationPreferences").mockResolvedValue(mockDefaultPreferences);

  render(<NotificationPreferences />);

  expect(await screen.findByRole("heading", { name: "Notification preferences" })).toBeInTheDocument();

  // Enable email without checking consent
  const emailCheckbox = screen.getByLabelText("Email notifications");
  await userEvent.click(emailCheckbox);

  expect(
    screen.getByText("Consent is required before email notifications can be sent.")
  ).toBeInTheDocument();
});

it("reveals quiet hours time and timezone inputs when quiet hours is enabled", async () => {
  vi.spyOn(api, "notificationPreferences").mockResolvedValue(mockDefaultPreferences);

  render(<NotificationPreferences />);

  expect(await screen.findByRole("heading", { name: "Notification preferences" })).toBeInTheDocument();

  expect(screen.queryByLabelText("Start time")).not.toBeInTheDocument();

  const quietHoursCheckbox = screen.getByLabelText("Pause non-critical notifications during quiet hours");
  await userEvent.click(quietHoursCheckbox);

  expect(screen.getByLabelText("Start time")).toBeInTheDocument();
  expect(screen.getByLabelText("End time")).toBeInTheDocument();
  expect(screen.getByLabelText("Timezone")).toBeInTheDocument();
});

it("displays error with retry button when initial fetch fails", async () => {
  const fetchSpy = vi
    .spyOn(api, "notificationPreferences")
    .mockRejectedValueOnce(new Error("Network error"))
    .mockResolvedValueOnce(mockDefaultPreferences);

  render(<NotificationPreferences />);

  expect(
    await screen.findByText("Could not load notification preferences. Please try again.")
  ).toBeInTheDocument();

  const retryButton = screen.getByRole("button", { name: "Retry" });
  await userEvent.click(retryButton);

  expect(fetchSpy).toHaveBeenCalledTimes(2);
  expect(await screen.findByLabelText("In-app notifications")).toBeInTheDocument();
});

it("displays error notice when saving fails", async () => {
  vi.spyOn(api, "notificationPreferences").mockResolvedValue(mockDefaultPreferences);
  vi.spyOn(api, "updateNotificationPreferences").mockRejectedValue(new Error("Server error"));

  render(<NotificationPreferences />);

  expect(await screen.findByRole("heading", { name: "Notification preferences" })).toBeInTheDocument();

  const saveButton = screen.getByRole("button", { name: "Save preferences" });
  await userEvent.click(saveButton);

  expect(
    await screen.findByText("Could not save preferences. Please try again.")
  ).toBeInTheDocument();
});

it("renders properly in Bengali when language is changed", async () => {
  setLanguage("bn");
  vi.spyOn(api, "notificationPreferences").mockResolvedValue(mockDefaultPreferences);

  render(<NotificationPreferences />);

  expect(await screen.findByRole("heading", { name: "বিজ্ঞপ্তির পছন্দসমূহ" })).toBeInTheDocument();
  expect(screen.getByLabelText("অ্যাপে বিজ্ঞপ্তি")).toBeInTheDocument();
  expect(screen.getByLabelText("ইমেইল বিজ্ঞপ্তি")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "পছন্দসমূহ সংরক্ষণ করুন" })).toBeInTheDocument();
});
