import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ActionPlan } from "../components/ActionPlan";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import { actionPlanFixture, emptyActionPlan } from "./action-plan.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});
function view(revision = 0) {
  return (
    <MemoryRouter>
      <ActionPlan revision={revision} />
    </MemoryRouter>
  );
}
it("renders server order, amounts and existing destinations", async () => {
  vi.spyOn(api, "actionPlan").mockResolvedValue(actionPlanFixture);
  render(view());
  const actions = await screen.findAllByRole("article");
  expect(actions).toHaveLength(2);
  expect(
    within(actions[0]).getByRole("heading", { level: 3 }),
  ).toHaveTextContent("1. Prepare for a possible cash shortfall");
  expect(within(actions[1]).getByText("High")).toBeInTheDocument();
  expect(within(actions[0]).getByRole("link")).toHaveAttribute(
    "href",
    "/cashflow",
  );
});
it.each(["critical", "high", "medium", "low"] as const)(
  "labels %s priority",
  async (priority) => {
    vi.spyOn(api, "actionPlan").mockResolvedValue({
      ...actionPlanFixture,
      actions: [{ ...actionPlanFixture.actions[0], priority }],
    });
    render(view());
    expect(
      await screen.findByText(priority[0].toUpperCase() + priority.slice(1)),
    ).toBeInTheDocument();
  },
);
it.each(["en", "bn"] as const)(
  "shows empty and reported-done state in %s",
  async (language) => {
    setLanguage(language);
    vi.spyOn(api, "actionPlan").mockResolvedValue({
      ...emptyActionPlan,
      completed_count: 1,
    });
    render(view());
    expect(
      await screen.findByText(t("No active actions right now.")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(t("Reported done"))),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        t(
          "Feedback records your report and does not verify a financial action.",
        ),
      ),
    ).toBeInTheDocument();
  },
);
it("announces loading and supports keyboard retry after an API error", async () => {
  const request = vi
    .spyOn(api, "actionPlan")
    .mockRejectedValueOnce(new Error("Unavailable"))
    .mockResolvedValueOnce(actionPlanFixture);
  render(view());
  expect(screen.getByRole("status")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  const retry = screen.getByRole("button", { name: "Try again" });
  retry.focus();
  await userEvent.keyboard("{Enter}");
  const link = (await screen.findAllByRole("link"))[0];
  link.focus();
  expect(link).toHaveFocus();
  expect(request).toHaveBeenCalledTimes(2);
});
it("refreshes when coaching feedback changes", async () => {
  const request = vi
    .spyOn(api, "actionPlan")
    .mockResolvedValueOnce(actionPlanFixture)
    .mockResolvedValueOnce(emptyActionPlan);
  const rendered = render(view());
  await screen.findAllByRole("article");
  rendered.rerender(view(1));
  expect(
    await screen.findByText("No active actions right now."),
  ).toBeInTheDocument();
  expect(request).toHaveBeenCalledTimes(2);
});
it.each([
  ["goal_risk", "/plans"],
  ["savings_opportunity", "/plans"],
  ["spending_spike", "/insights"],
  ["repeated_spending", "/insights"],
] as const)("links %s to %s", async (type, destination) => {
  vi.spyOn(api, "actionPlan").mockResolvedValue({
    ...actionPlanFixture,
    actions: [{ ...actionPlanFixture.actions[0], type }],
  });
  render(view());
  expect(await screen.findByRole("link")).toHaveAttribute("href", destination);
});
