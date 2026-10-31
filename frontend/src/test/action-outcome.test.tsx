import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ActionOutcomes } from "../components/ActionOutcomes";
import { api } from "../lib/api";
import { setLanguage } from "../lib/locale";
import { bn } from "../lib/translations";
import {
  actionOutcomesFixture,
  emptyActionOutcomes,
} from "./action-outcome.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});
function view(revision = 0) {
  return (
    <MemoryRouter>
      <ActionOutcomes revision={revision} />
    </MemoryRouter>
  );
}
it("renders summary counts and outcome cards with status classes", async () => {
  vi.spyOn(api, "actionOutcomes").mockResolvedValue(actionOutcomesFixture);
  render(view());
  expect(
    await screen.findByText("What changed after reported actions"),
  ).toBeInTheDocument();
  expect(screen.getAllByText("1", { exact: true }).length).toBeGreaterThan(0);
  const cards = await screen.findAllByRole("article");
  expect(cards).toHaveLength(4);
  expect(cards[0]).toHaveClass("outcome-improved");
  expect(cards[1]).toHaveClass("outcome-worsened");
  expect(cards[2]).toHaveClass("outcome-pending");
  expect(cards[3]).toHaveClass("outcome-insufficient_data");
});
it("renders pending and insufficient-data status labels", async () => {
  vi.spyOn(api, "actionOutcomes").mockResolvedValue(actionOutcomesFixture);
  render(view());
  expect(await screen.findAllByText("Pending observation")).toHaveLength(2);
  expect(screen.getAllByText("Insufficient evidence")).toHaveLength(2);
});
it("links each outcome type to its related-records route", async () => {
  vi.spyOn(api, "actionOutcomes").mockResolvedValue(actionOutcomesFixture);
  render(view());
  const links = await screen.findAllByRole("link", {
    name: "Review related records",
  });
  expect(links[0]).toHaveAttribute("href", "/transactions");
  expect(links[1]).toHaveAttribute("href", "/plans");
  expect(links[2]).toHaveAttribute("href", "/cashflow");
  expect(links[3]).toHaveAttribute("href", "/plans");
});
it("renders the empty state when no outcomes exist", async () => {
  vi.spyOn(api, "actionOutcomes").mockResolvedValue(emptyActionOutcomes);
  render(view());
  expect(
    await screen.findByText("No reported action outcomes yet."),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      /Mark a coaching recommendation as done, then return after at least seven days/,
    ),
  ).toBeInTheDocument();
});
it.each(["en", "bn"] as const)(
  "announces the section title in %s",
  async (language) => {
    setLanguage(language);
    vi.spyOn(api, "actionOutcomes").mockResolvedValue(actionOutcomesFixture);
    render(view());
    expect(
      await screen.findByText(
        language === "en"
          ? "What changed after reported actions"
          : bn["What changed after reported actions"],
      ),
    ).toBeInTheDocument();
  },
);
it("announces loading and supports keyboard retry after an API error", async () => {
  const request = vi
    .spyOn(api, "actionOutcomes")
    .mockRejectedValueOnce(new Error("Unavailable"))
    .mockResolvedValueOnce(actionOutcomesFixture);
  render(view());
  expect(screen.getByRole("status")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  const retry = screen.getByRole("button", { name: "Try again" });
  retry.focus();
  await userEvent.keyboard("{Enter}");
  await screen.findAllByRole("article");
  expect(request).toHaveBeenCalledTimes(2);
});
it("reports no causal claim, only an observation", async () => {
  vi.spyOn(api, "actionOutcomes").mockResolvedValue(actionOutcomesFixture);
  render(view());
  const card = (await screen.findAllByRole("article"))[0];
  const detail = within(card).getByText("Outcome evidence") as HTMLElement;
  detail.click();
  expect(
    within(card).getByText("Causal claim").closest("div")?.querySelector("dd"),
  ).toHaveTextContent("No");
});
it("refreshes when the recommendation revision changes", async () => {
  const request = vi
    .spyOn(api, "actionOutcomes")
    .mockResolvedValueOnce(actionOutcomesFixture)
    .mockResolvedValueOnce(emptyActionOutcomes);
  const rendered = render(view());
  await screen.findAllByRole("article");
  rendered.rerender(view(1));
  expect(
    await screen.findByText("No reported action outcomes yet."),
  ).toBeInTheDocument();
  expect(request).toHaveBeenCalledTimes(2);
});

it.each(["en", "bn"] as const)(
  "renders unchanged observations and localized evidence in %s",
  async (language) => {
    setLanguage(language);
    const original = actionOutcomesFixture.items[0];
    vi.spyOn(api, "actionOutcomes").mockResolvedValue({
      ...actionOutcomesFixture,
      items: [
        {
          ...original,
          status: "unchanged",
          interpretation: "unchanged",
          absolute_change: "0.00",
          percentage_change: "0.00",
        },
      ],
    });
    render(view());
    const card = (await screen.findAllByRole("article"))[0];
    expect(card).toHaveClass("outcome-unchanged");
    expect(card).toHaveTextContent(
      language === "en"
        ? "Recorded value is unchanged compared with the baseline."
        : bn["Recorded value is unchanged compared with the baseline."],
    );
    expect(
      within(card).getByText(
        language === "en"
          ? "The user reported acting on this recommendation; the system cannot verify the action itself."
          : bn[
              "The user reported acting on this recommendation; the system cannot verify the action itself."
            ],
      ),
    ).toBeInTheDocument();
  },
);
