import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../components/FinancialCoaching", () => ({
  FeedbackControls: ({
    id,
    refresh,
  }: {
    id: string;
    refresh: () => Promise<void>;
  }) => (
    <div data-testid="feedback-control" data-recommendation-id={id}>
      <button type="button" onClick={() => void refresh()}>
        Refresh {id}
      </button>
    </div>
  ),
}));

import { FinancialReviewFeedback } from "../components/FinancialReviewFeedback";

describe("FinancialReviewFeedback", () => {
  it("renders controls for supported coaching recommendation IDs", () => {
    render(
      <FinancialReviewFeedback
        sourceActionIds={[
          "cash_risk:account:123",
          "goal_risk:goal:456",
        ]}
        refresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const controls = screen.getAllByTestId("feedback-control");

    expect(controls).toHaveLength(2);
    expect(controls[0].getAttribute("data-recommendation-id")).toBe(
      "cash_risk:account:123",
    );
    expect(controls[1].getAttribute("data-recommendation-id")).toBe(
      "goal_risk:goal:456",
    );
  });

  it("does not render controls for synthetic planning IDs", () => {
    const { container } = render(
      <FinancialReviewFeedback
        sourceActionIds={[
          "plan:goal:123",
          "plan:cashflow:456",
        ]}
        refresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it("filters synthetic IDs while preserving supported recommendations", () => {
    render(
      <FinancialReviewFeedback
        sourceActionIds={[
          "plan:goal:123",
          "cash_risk:account:123",
          "plan:cashflow:456",
        ]}
        refresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const controls = screen.getAllByTestId("feedback-control");

    expect(controls).toHaveLength(1);
    expect(controls[0].getAttribute("data-recommendation-id")).toBe(
      "cash_risk:account:123",
    );
  });

  it("does not render duplicate controls for the same recommendation", () => {
    render(
      <FinancialReviewFeedback
        sourceActionIds={[
          "cash_risk:account:123",
          "cash_risk:account:123",
        ]}
        refresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getAllByTestId("feedback-control")).toHaveLength(1);
  });

  it("refreshes the review after feedback controls request a refresh", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);

    render(
      <FinancialReviewFeedback
        sourceActionIds={["cash_risk:account:123"]}
        refresh={refresh}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    await waitFor(() => {
      expect(refresh).toHaveBeenCalledTimes(1);
    });
  });

  it("links supported recommendations to the existing outcome section", () => {
  render(
    <FinancialReviewFeedback
      sourceActionIds={["cash_risk:account:123"]}
      refresh={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  expect(
    screen.getByRole("link", { name: /track reported outcomes/i }),
  ).toHaveAttribute("href", "#action-outcomes");
});

});