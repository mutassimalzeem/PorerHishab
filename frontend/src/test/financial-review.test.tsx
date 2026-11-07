import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { FinancialReview } from "../components/FinancialReview";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import type { ApiSchemas } from "../generated/api";
import fixture from "./financial-review.fixture.json";
const review = fixture as unknown as ApiSchemas["FinancialReview"];
beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});
function view() {
  return (
    <MemoryRouter>
      <FinancialReview />
    </MemoryRouter>
  );
}
function explanation(changed = false): ApiSchemas["CoachResponse"] {
  return {
    intent: "financial_review",
    answer: "Canonical explanation",
    evidence: [
      {
        evidence_id: "ev_review_source",
        evidence_type: "interpretation",
        source: "financial_review",
        label: "Source",
        value: {
          evidence: review.decisions.evidence,
          capacity: review.plan.goal_planning?.capacity ?? null,
          schedules_confirmed: review.schedules_confirmed,
          data_status: review.plan.data_status,
        },
      },
      {
        evidence_id: "ev_review_horizon",
        evidence_type: "interpretation",
        source: "financial_review",
        label: "Horizon",
        value: review.plan.planning_horizon,
        as_of_date: changed ? "2000-01-01" : review.plan.as_of_date,
      },
      {
        evidence_id: "ev_review_priorities",
        evidence_type: "interpretation",
        source: "financial_review",
        label: "Priorities",
        value: review.decisions.priorities,
      },
      {
        evidence_id: "ev_review_execution_steps",
        evidence_type: "interpretation",
        source: "financial_review",
        label: "Steps",
        value: review.execution_plan.steps,
      },
    ],
  };
}
it.each(["en", "bn"] as const)(
  "shows canonical order, blockers and safe labels in %s",
  async (language) => {
    setLanguage(language);
    vi.spyOn(api, "financialReview").mockResolvedValue(review);
    render(view());
    await screen.findByRole("heading", {
      level: 3,
      name: review.decisions.priorities![0].title,
    });
    const cards = screen.getAllByRole("article");
    expect(
      within(cards[0]).getByRole("heading", { level: 3 }),
    ).toHaveTextContent(review.decisions.priorities![0].title);
    expect(
      screen.getByText(
        t(
          "Review only. Ready means ready for review; no financial action is authorized or executed.",
        ),
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText(t("Blocked for review")).length).toBeGreaterThan(
      0,
    );
    expect(
      screen
        .getAllByRole("link")
        .every((link) => {const href = link.getAttribute("href");
          return href?.startsWith("/") || href?.startsWith("#");
        }),
    ).toBe(true);
  },
);
it("retries errors by keyboard and sends completeness only", async () => {
  const get = vi
    .spyOn(api, "financialReview")
    .mockRejectedValueOnce(new Error("Unavailable"))
    .mockResolvedValue(review);
  render(view());
  expect(screen.getByRole("status")).toBeInTheDocument();
  await screen.findByRole("alert");
  screen.getByRole("button", { name: "Try again" }).focus();
  await userEvent.keyboard("{Enter}");
  await screen.findByText(t("Plan status") + ": partial");
  await userEvent.click(screen.getByRole("checkbox"));
  expect(get).toHaveBeenLastCalledWith(true);
});
it.each([false, true])(
  "checks canonical context before showing explanation (changed=%s)",
  async (changed) => {
    vi.spyOn(api, "financialReview").mockResolvedValue(review);
    const ask = vi
      .spyOn(api, "coachAsk")
      .mockResolvedValue(explanation(changed));
    render(view());
    await userEvent.click(
      await screen.findByRole("button", { name: "Explain this review" }),
    );
    expect(
      await screen.findByText(
        changed
          ? t(
              "The review has changed. Refresh before requesting another explanation.",
            )
          : "Canonical explanation",
      ),
    ).toBeInTheDocument();
    expect(ask).toHaveBeenCalledWith(
      { message: "Explain my financial review", schedules_confirmed: false },
      "en",
    );
    if (changed)
      expect(
        screen.queryByText("Canonical explanation"),
      ).not.toBeInTheDocument();
  },
);
it("discards an explanation after the review is refreshed", async () => {
  vi.spyOn(api, "financialReview").mockResolvedValue(review);
  let resolve!: (value: ApiSchemas["CoachResponse"]) => void;
  vi.spyOn(api, "coachAsk").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  render(view());
  await userEvent.click(
    await screen.findByRole("button", { name: "Explain this review" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Refresh review" }));
  await act(async () => {
    resolve(explanation());
  });
  expect(screen.queryByText("Canonical explanation")).not.toBeInTheDocument();
});
it("shows an empty review without claiming financial health", async () => {
  vi.spyOn(api, "financialReview").mockResolvedValue({
    ...review,
    decisions: { ...review.decisions, priorities: [] },
    execution_plan: { ...review.execution_plan, steps: [] },
  });
  render(view());
  expect(
    await screen.findByText(
      t(
        "No priorities to review. Missing information may still limit this review.",
      ),
    ),
  ).toBeInTheDocument();
});

it("rejects changed source values even when the date and priorities match", async () => {
  vi.spyOn(api, "financialReview").mockResolvedValue(review);
  const response = explanation();
  response.evidence![0].value = { changed: true };
  vi.spyOn(api, "coachAsk").mockResolvedValue(response);
  render(view());
  await userEvent.click(
    await screen.findByRole("button", { name: "Explain this review" }),
  );
  expect(
    await screen.findByText(
      t(
        "The review has changed. Refresh before requesting another explanation.",
      ),
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText("Canonical explanation")).not.toBeInTheDocument();
});
it.each([null, "0.00"])(
  "distinguishes capacity %s from missing data",
  async (value) => {
    const copy = structuredClone(review);
    copy.plan.goal_planning!.capacity.conservative_monthly_capacity = value;
    vi.spyOn(api, "financialReview").mockResolvedValue(copy);
    render(view());
    const label = await screen.findByText("Conservative monthly capacity");
    const amount = label.parentElement!.querySelector(".amount")!;
    if (value === null) expect(amount).toHaveTextContent(t("Not available"));
    else {
      expect(amount.textContent).toContain("0");
      expect(amount).not.toHaveTextContent(t("Not available"));
    }
  },
);
