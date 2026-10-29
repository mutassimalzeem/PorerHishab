import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CashflowChart } from "../components/CashflowChart";
import { Dialog } from "../components/Dialog";
import { IntelligencePanels } from "../components/IntelligencePanels";
import { Plans } from "../pages/Plans";
import { api } from "../lib/api";
import { emptyIntelligence, richIntelligence } from "./intelligence.fixture";
const wrap = (node: React.ReactNode) =>
  render(<MemoryRouter>{node}</MemoryRouter>);
describe("refined financial interactions", () => {
  it("shows missing months as unknown and hides unsupported estimates", () => {
    wrap(<IntelligencePanels data={emptyIntelligence} />);
    expect(
      screen.getAllByText("No records. Income and expenses are unknown."),
    ).toHaveLength(3);
    expect(screen.getByText("No category comparison yet")).toBeInTheDocument();
    expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(
      3,
    );
  });
  it("exposes category comparisons and recurring patterns from the engine", () => {
    wrap(<IntelligencePanels data={richIntelligence} />);
    expect(screen.getByRole("heading", { name: "Food" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Internet service" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Three complete months contain records"),
    ).toBeInTheDocument();
  });
  it("makes exact chart points keyboard inspectable without inventing a forecast", async () => {
    const user = userEvent.setup();
    render(
      <CashflowChart
        months={[
          {
            month: "2026-10",
            historical_income_estimate: null,
            historical_expense_estimate: null,
            scheduled_expenses: "100",
            uncertain_scheduled_income: "0",
            reserved_expenses: "100",
            projected_balance: null,
            balance_without_future_income: "900",
          },
          {
            month: "2026-11",
            historical_income_estimate: null,
            historical_expense_estimate: null,
            scheduled_expenses: "200",
            uncertain_scheduled_income: "0",
            reserved_expenses: "200",
            projected_balance: null,
            balance_without_future_income: "700",
          },
        ]}
      />,
    );
    expect(
      screen.getByText("Historical estimate unavailable"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "2026-11" }));
    expect(screen.getByRole("button", { name: "2026-11" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByText(/700.00/, { selector: ".amount" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Not available")).toBeInTheDocument();
  });
  it("labels the modal and restores focus when it closes", () => {
    const trigger = document.createElement("button");
    trigger.textContent = "Edit";
    document.body.appendChild(trigger);
    trigger.focus();
    const view = render(
      <Dialog open title="Edit record" onClose={() => {}}>
        Details
      </Dialog>,
    );
    expect(
      screen.getByRole("dialog", { name: "Edit record" }),
    ).toBeInTheDocument();
    view.rerender(
      <Dialog open={false} title="Edit record" onClose={() => {}}>
        Details
      </Dialog>,
    );
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });
  it("edits a real goal payload and preserves unknown savings", async () => {
    const user = userEvent.setup();
    const goal = {
      id: 2,
      name: "Reserve",
      description: null,
      target_amount: "10000.00",
      current_saved: null,
      target_date: "2099-12-31",
      status: "active" as const,
    };
    vi.spyOn(api, "goals").mockResolvedValue({
      items: [goal],
      total: 1,
      limit: 20,
      offset: 0,
    });
    vi.spyOn(api, "goalPlan").mockResolvedValue({
      goal_id: 2,
      as_of_date: "2026-10-25",
      remaining_amount: null,
      required_weekly: null,
      required_monthly: null,
      estimated_monthly_capacity: null,
      affordability: "unknown",
      assumptions: [],
      limitations: [],
    });
    const edit = vi.spyOn(api, "editGoal").mockResolvedValue(goal);
    wrap(<Plans />);
    await user.click(
      await screen.findByRole("button", { name: "Edit Reserve" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Edit savings goal" });
    await user.clear(within(dialog).getByLabelText("Goal name"));
    await user.type(
      within(dialog).getByLabelText("Goal name"),
      "Emergency reserve",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Save goal changes" }),
    );
    expect(edit).toHaveBeenCalledWith(2, { name: "Emergency reserve" });
    expect(await screen.findByRole("status")).toHaveTextContent("Goal updated");
  });
});
