import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { FinancialCoaching } from "../components/FinancialCoaching";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import { coachingFixture, emptyCoaching } from "./coaching.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});
function view() {
  render(
    <MemoryRouter>
      <FinancialCoaching />
    </MemoryRouter>,
  );
}
async function load() {
  await userEvent.click(
    screen.getByRole("button", { name: t("Review financial coaching") }),
  );
}
describe("financial coaching", () => {
  it("renders prioritized actions and expandable evidence without automatic actions", async () => {
    const request = vi
      .spyOn(api, "coaching")
      .mockResolvedValue(coachingFixture);
    view();
    expect(request).not.toHaveBeenCalled();
    await load();
    expect(
      await screen.findByText("Prepare for a possible cash shortfall"),
    ).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    const card = screen
      .getByText("Prepare for a possible cash shortfall")
      .closest("article")!;
    const evidence = within(card).getByText("Why this recommendation?");
    evidence.focus();
    await userEvent.keyboard("{Enter}");
    // jsdom does not implement details keyboard toggling, so use its native click path.
    if (!evidence.closest("details")!.open) await userEvent.click(evidence);
    expect(evidence.closest("details")).toHaveAttribute("open");
    expect(
      within(card).getByText("Known obligations only"),
    ).toBeInTheDocument();
    expect(
      within(card).getByText("Uncertain scheduled income"),
    ).toBeInTheDocument();
    expect(
      within(card).getByRole("link", { name: "Review related records" }),
    ).toHaveAttribute("href", "/cashflow");
    expect(request).toHaveBeenCalledTimes(1);
  });
  it.each(["critical", "high", "medium", "low"] as const)(
    "shows %s priority explicitly",
    async (priority) => {
      vi.spyOn(api, "coaching").mockResolvedValue({
        ...coachingFixture,
        recommendations: [{ ...coachingFixture.recommendations[0], priority }],
      });
      view();
      await load();
      expect(
        await screen.findByText(priority[0].toUpperCase() + priority.slice(1)),
      ).toBeInTheDocument();
    },
  );
  it("distinguishes an empty supported result from insufficient evidence", async () => {
    vi.spyOn(api, "coaching")
      .mockResolvedValueOnce(emptyCoaching)
      .mockResolvedValueOnce({
        ...emptyCoaching,
        data_status: "insufficient_data",
      });
    view();
    await load();
    expect(
      await screen.findByText("No actionable coaching right now"),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh coaching" }),
    );
    expect(
      await screen.findByText("More financial evidence is needed"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Some financial inputs are unavailable/),
    ).toBeInTheDocument();
  });
  it("announces loading and prevents duplicate requests", async () => {
    vi.spyOn(api, "coaching").mockImplementation(() => new Promise(() => {}));
    view();
    await load();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Reading financial coaching...",
    );
    expect(
      screen.getByRole("button", { name: "Review financial coaching" }),
    ).toBeDisabled();
  });
  it("reports errors and allows retry", async () => {
    vi.spyOn(api, "coaching")
      .mockRejectedValueOnce(new Error("Coaching unavailable"))
      .mockResolvedValueOnce(emptyCoaching);
    view();
    await load();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Coaching unavailable",
    );
    await load();
    expect(
      await screen.findByText("No actionable coaching right now"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("localizes backend templates, actions and caveats while preserving user names", async () => {
    setLanguage("bn");
    vi.spyOn(api, "coaching").mockResolvedValue(coachingFixture);
    view();
    await load();
    expect(
      await screen.findByText(t("Prepare for a possible cash shortfall")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        t(
          "Review upcoming commitments and postpone optional spending until the gap is covered.",
        ),
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        t(
          "Scheduled income is uncertain and is excluded from available cash and recommendation amounts.",
        ),
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Rent installment")).toBeInTheDocument();
    expect(
      screen.queryByText("Prepare for a possible cash shortfall"),
    ).not.toBeInTheDocument();
  });
});
