import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FinancialHealth } from "../pages/FinancialHealth";
import { api } from "../lib/api";
import { setLanguage, t, digits } from "../lib/locale";
import { healthFixture, emptyHealth } from "./financial-health.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
  vi.spyOn(api, "financialHealth").mockResolvedValue(healthFixture);
  vi.spyOn(api, "financialHealthHistory").mockResolvedValue([healthFixture]);
  vi.spyOn(api, "financialHealthTrend").mockResolvedValue(healthFixture.trend!);
});
it.each(["en", "bn"] as const)(
  "shows scores, coverage, components and trend in %s",
  async (language) => {
    setLanguage(language);
    render(<FinancialHealth />);
    await screen.findByRole("heading", {
      name: t("Current financial profile"),
    });
    expect(screen.getAllByText(new RegExp(digits("85.71") + "%"))[0]).toBeVisible();
    expect(screen.getByRole("heading", { name: t("liquidity") })).toBeVisible();
    expect(screen.getByRole("table")).toBeVisible();
    expect(screen.getAllByText(t("improving")).length).toBeGreaterThan(0);
    await userEvent.click(screen.getAllByText(t("Health evidence"))[0]);
    expect(screen.getAllByText(language === "en" ? "trusted cash" : t("trusted_cash"))[0]).toBeVisible();
  },
);
it("renders insufficient data without a fabricated score", async () => {
  vi.spyOn(api, "financialHealth").mockResolvedValue(emptyHealth);
  vi.spyOn(api, "financialHealthHistory").mockResolvedValue([]);
  render(<FinancialHealth />);
  await screen.findByText(t("Not evaluated yet"), { exact: false });
  expect(screen.getByText(t("No health snapshots yet"))).toBeVisible();
  expect(
    screen.getAllByText(t("insufficient_data"), { exact: false }).length,
  ).toBeGreaterThan(0);
});
it("has loading and API error recovery", async () => {
  vi.spyOn(api, "financialHealth").mockRejectedValue(new Error("unavailable"));
  render(<FinancialHealth />);
  await waitFor(() =>
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0),
  );
  expect(screen.getByRole("button", { name: t("Try again") })).toBeVisible();
});
it("evaluates explicitly and changes comparison window", async () => {
  const evaluate = vi
    .spyOn(api, "evaluateFinancialHealth")
    .mockResolvedValue(healthFixture);
  render(<FinancialHealth />);
  await screen.findByRole("table");
  await userEvent.click(
    screen.getByRole("button", { name: t("Evaluate financial health") }),
  );
  await waitFor(() => expect(evaluate).toHaveBeenCalledOnce());
  await userEvent.selectOptions(screen.getByRole("combobox"), "30");
  await waitFor(() =>
    expect(api.financialHealthTrend).toHaveBeenCalledWith(30),
  );
});
it("shows loading until the current profile arrives", () => {
  vi.spyOn(api, "financialHealth").mockReturnValue(new Promise(() => {}));
  render(<FinancialHealth />);
  expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
});
