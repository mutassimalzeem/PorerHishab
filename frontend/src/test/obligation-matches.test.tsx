import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ObligationMatches } from "../components/ObligationMatches";
import { api } from "../lib/api";
import { setLanguage } from "../lib/locale";
import type { ApiSchemas } from "../generated/api";
const result: ApiSchemas["ObligationReconciliation"] = {
  item_id: 1,
  original_amount: "100.00",
  allocated_amount: "0.00",
  remaining_amount: "100.00",
  status: "review_required",
  timing: "due",
  ambiguous: false,
  allocations: [],
  date_tolerance_days: 7,
  amount_tolerance: "0.00",
  limitations: [],
  candidates: [
    {
      transaction_id: 5,
      date: "2026-11-01",
      amount: "100.00",
      description: "Rent",
      merchant: null,
      category: "Housing",
      amount_difference: "0.00",
      date_distance_days: 0,
      amount_signal: "exact",
      category_match: true,
      text_overlap: true,
      confidence: "medium",
      limitations: [],
    },
  ],
};
beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});
describe("obligation reconciliation controls", () => {
  it("requires explicit confirmation and distinguishes allocation from full settlement", async () => {
    vi.spyOn(api, "obligationMatches").mockResolvedValue(result);
    const confirm = vi
      .spyOn(api, "confirmAllocation")
      .mockResolvedValue(result);
    const changed = vi.fn();
    render(<ObligationMatches itemId={1} onChange={changed} />);
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Review transaction matches" }),
    );
    expect(
      await screen.findByText(/Suggestions require review/),
    ).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Confirm allocation" }),
    );
    expect(confirm).toHaveBeenLastCalledWith(1, 5, false);
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: "Confirm allocation and mark paid",
        }),
      ).toBeEnabled(),
    );
    await user.click(
      await screen.findByRole("button", {
        name: "Confirm allocation and mark paid",
      }),
    );
    expect(confirm).toHaveBeenLastCalledWith(1, 5, true);
    expect(changed).toHaveBeenCalledTimes(2);
  });
  it("removes an allocation and reports mutation errors", async () => {
    vi.spyOn(api, "obligationMatches").mockResolvedValue({
      ...result,
      candidates: [],
      allocations: [
        {
          id: 2,
          transaction_id: 5,
          amount: "40.00",
          active: true,
          confirmed_at: "2026-11-01T00:00:00Z",
          revoked_at: null,
        },
      ],
    });
    const remove = vi
      .spyOn(api, "removeAllocation")
      .mockRejectedValue(new Error("Allocation conflict"));
    render(<ObligationMatches itemId={1} onChange={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Review transaction matches" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Remove allocation" }),
    );
    expect(remove).toHaveBeenCalledWith(1, 5);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Allocation conflict",
    );
  });
  it("disables oversized candidates using decimal cents", async () => {
    vi.spyOn(api, "obligationMatches").mockResolvedValue({
      ...result,
      remaining_amount: "9.00",
      candidates: [
        {
          ...result.candidates[0],
          amount: "10.00",
          amount_signal: "within_tolerance",
        },
      ],
    });
    render(<ObligationMatches itemId={1} onChange={vi.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Review transaction matches" }),
    );
    expect(
      await screen.findByRole("button", {
        name: "Confirm allocation",
      }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", {
        name: "Confirm allocation and mark paid",
      }),
    ).not.toBeInTheDocument();
  });
});
