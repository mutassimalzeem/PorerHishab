import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GoalPlanner } from "../components/GoalPlanner";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import {
  planningGoalFixture as goal,
  planningOverviewFixture as overview,
  revisedPlanFixture as plan,
  challengingPlanFixture as challenging,
  contributionFixture,
} from "./goal-planning.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
  vi.spyOn(api, "planningGoal").mockResolvedValue(goal);
  vi.spyOn(api, "planningOverview").mockResolvedValue(overview);
  vi.spyOn(api, "personalizedPlans").mockResolvedValue([plan]);
  vi.spyOn(api, "personalizedPlan").mockResolvedValue(plan);
  vi.spyOn(api, "goalEvents").mockResolvedValue([]);
});
it.each(["en", "bn"] as const)(
  "renders explained plan, milestones and commitments in %s",
  async (language) => {
    setLanguage(language);
    render(<GoalPlanner goalId={goal.id} onClose={vi.fn()} />);
    await screen.findByRole("heading", { name: t("Goal feasibility") });
    expect(
      screen.getAllByText(
        t(
          "The required contribution fits the conservative capacity after existing commitments.",
        ),
      )[0],
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: t("Goal milestones") }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: t("Overall goal commitments") }),
    ).toBeVisible();
    await userEvent.click(screen.getByText(t("Plan revision history")));
    expect(
      screen.getByText(t("Plan revision history")).closest("details"),
    ).toHaveAttribute("open");
  },
);
it("creates a plan explicitly, preserves an empty history and reviews schedules", async () => {
  vi.spyOn(api, "personalizedPlans").mockResolvedValue([]);
  const create = vi.spyOn(api, "createGoalPlan").mockResolvedValue(plan);
  render(<GoalPlanner goalId={goal.id} onClose={vi.fn()} />);
  await screen.findByText(
    t("No personalized plan yet. Review your inputs before creating one."),
  );
  expect(create).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.selectOptions(screen.getByRole("combobox"), "weekly");
  await userEvent.click(
    screen.getByRole("button", { name: t("Create personalized plan") }),
  );
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0][1]).toMatchObject({
    cadence: "weekly",
    schedules_confirmed: true,
  });
});
it("does not accept alternatives until explicitly selected", async () => {
  vi.spyOn(api, "personalizedPlan").mockResolvedValue(challenging);
  const replan = vi.spyOn(api, "replanGoal").mockResolvedValue(plan);
  render(<GoalPlanner goalId={goal.id} onClose={vi.fn()} />);
  const accept = (
    await screen.findAllByRole("button", { name: t("Accept this alternative") })
  )[0];
  expect(accept).toBeDisabled();
  expect(replan).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("checkbox"));
  await waitFor(() =>
    expect(
      screen.getAllByRole("button", { name: t("Accept this alternative") })[0],
    ).toBeEnabled(),
  );
  await userEvent.click(
    screen.getAllByRole("button", { name: t("Accept this alternative") })[0],
  );
  await waitFor(() => expect(replan).toHaveBeenCalledOnce());
  expect(replan.mock.calls[0][1].target_date).toBe(
    challenging.alternatives![0].target_date,
  );
});
it("reuses a contribution request key after a failed response", async () => {
  const contribute = vi
    .spyOn(api, "contributeGoal")
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(contributionFixture);
  render(<GoalPlanner goalId={goal.id} onClose={vi.fn()} />);
  await userEvent.type(
    await screen.findByLabelText(t("Reported contribution (BDT)")),
    "15000",
  );
  await userEvent.click(
    screen.getByRole("button", { name: t("Record contribution") }),
  );
  await screen.findByRole("alert");
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: t("Record contribution") }),
    ).toBeEnabled(),
  );
  await userEvent.click(
    screen.getByRole("button", { name: t("Record contribution") }),
  );
  await waitFor(() => expect(contribute).toHaveBeenCalledTimes(2));
  expect(contribute.mock.calls[0][1].idempotency_key).toBe(
    contribute.mock.calls[1][1].idempotency_key,
  );
});
it("shows insufficient capacity without inventing an allocation", async () => {
  vi.spyOn(api, "planningOverview").mockResolvedValue({
    ...overview,
    capacity: {
      ...overview.capacity,
      status: "insufficient_data",
      conservative_monthly_capacity: null,
      explanations: [
        "Every BDT account needs a reconciled balance verified within thirty days.",
      ],
    },
  });
  vi.spyOn(api, "personalizedPlans").mockResolvedValue([]);
  render(<GoalPlanner goalId={goal.id} onClose={vi.fn()} />);
  expect(
    await screen.findByText(
      t(
        "Every BDT account needs a reconciled balance verified within thirty days.",
      ),
    ),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: t("Create personalized plan") }),
  ).toBeEnabled();
});
it("has API error recovery and keyboard-accessible controls", async () => {
  vi.spyOn(api, "planningOverview").mockRejectedValue(new Error("offline"));
  render(<GoalPlanner goalId={goal.id} onClose={vi.fn()} />);
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: t("Try again") })).toBeVisible();
  await userEvent.tab();
  expect(
    screen.getByRole("button", { name: t("Close planner") }),
  ).toHaveFocus();
  await userEvent.tab();
  expect(screen.getByRole("checkbox")).toHaveFocus();
  await userEvent.keyboard(" ");
  expect(screen.getByRole("checkbox")).toBeChecked();
});
it("keeps loading explicit", () => {
  vi.spyOn(api, "planningOverview").mockReturnValue(new Promise(() => {}));
  render(<GoalPlanner goalId={goal.id} onClose={vi.fn()} />);
  expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
});
