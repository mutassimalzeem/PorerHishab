import { beforeEach, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { FinancialCoaching } from "../components/FinancialCoaching";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import { coachingFixture } from "./coaching.fixture";
import type { ApiSchemas } from "../generated/api";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});
const item = coachingFixture.recommendations[0];
const record: ApiSchemas["CoachingFeedbackRecord"] = {
  recommendation_id: item.id,
  status: "dismissed",
  snoozed_until: null,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
  is_current: true,
  is_hidden: true,
};
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
function card() {
  return screen.getByText(item.title).closest("article")!;
}

it.each([
  ["Mark as done", "acted_on"],
  ["Dismiss", "dismissed"],
  ["Not relevant", "not_relevant"],
] as const)("records %s, refreshes and restores", async (label, status) => {
  vi.spyOn(api, "coaching")
    .mockResolvedValueOnce(coachingFixture)
    .mockResolvedValueOnce({
      ...coachingFixture,
      recommendations: [],
      feedback: [{ ...record, status }],
    })
    .mockResolvedValueOnce(coachingFixture);
  const put = vi
    .spyOn(api, "coachingFeedback")
    .mockResolvedValue({ ...record, status });
  const restore = vi.spyOn(api, "restoreCoaching").mockResolvedValue();
  view();
  await load();
  await userEvent.click(within(card()).getByRole("button", { name: label }));
  expect(put).toHaveBeenCalledWith(item.id, { status, snoozed_until: null });
  expect(
    await screen.findByText("Feedback saved. Financial records are unchanged."),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByText("Coaching feedback history"));
  await userEvent.click(
    screen.getByRole("button", { name: "Restore recommendation" }),
  );
  expect(restore).toHaveBeenCalledWith(item.id);
  expect(await screen.findByText(item.title)).toBeInTheDocument();
});
it("keeps other cards available while saving one recommendation", async () => {
  vi.spyOn(api, "coaching").mockResolvedValue(coachingFixture);
  let finish!: (value: typeof record) => void;
  vi.spyOn(api, "coachingFeedback").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  view();
  await load();
  const first = card();
  await userEvent.click(within(first).getByRole("button", { name: "Dismiss" }));
  expect(within(first).getByText("Saving feedback...")).toHaveAttribute(
    "role",
    "status",
  );
  expect(
    within(first).getByRole("button", { name: "Mark as done" }),
  ).toBeDisabled();
  expect(
    within(screen.getAllByRole("article")[1]).getByRole("button", {
      name: "Mark as done",
    }),
  ).toBeEnabled();
  finish(record);
  expect(
    await screen.findByText("Feedback saved. Financial records are unchanged."),
  ).toBeInTheDocument();
});
it("announces failure and retries the same feedback", async () => {
  vi.spyOn(api, "coaching").mockResolvedValue(coachingFixture);
  const put = vi
    .spyOn(api, "coachingFeedback")
    .mockRejectedValueOnce(new Error("Connection failed"))
    .mockResolvedValue(record);
  view();
  await load();
  await userEvent.click(
    within(card()).getByRole("button", { name: "Dismiss" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Connection failed",
  );
  await userEvent.click(screen.getByRole("button", { name: "Retry feedback" }));
  expect(put).toHaveBeenCalledTimes(2);
  expect(
    await screen.findByText("Feedback saved. Financial records are unchanged."),
  ).toBeInTheDocument();
});
it("supports a labeled snooze date and keyboard submission", async () => {
  vi.spyOn(api, "coaching").mockResolvedValue(coachingFixture);
  const put = vi
    .spyOn(api, "coachingFeedback")
    .mockResolvedValue({ ...record, status: "snoozed" });
  view();
  await load();
  const snooze = within(card()).getByRole("button", {
    name: "Snooze",
  });
  snooze.focus();
  await userEvent.keyboard("{Enter}");
  const input = screen.getByLabelText("Snooze until");
  const tomorrow = input.getAttribute("min")!;
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.change(input, { target: { value: tomorrow } });
  screen.getByRole("button", { name: "Save snooze" }).focus();
  await userEvent.keyboard("{Enter}");
  expect(put).toHaveBeenCalledWith(item.id, {
    status: "snoozed",
    snoozed_until: tomorrow,
  });
});
it.each(["en", "bn"] as const)(
  "localizes feedback controls and empty history in %s",
  async (language) => {
    setLanguage(language);
    vi.spyOn(api, "coaching").mockResolvedValue(coachingFixture);
    view();
    await load();
    expect(
      screen.getAllByRole("button", { name: t("Mark as done") }),
    ).toHaveLength(2);
    await userEvent.click(screen.getByText(t("Coaching feedback history")));
    expect(
      screen.getByText(t("No coaching feedback yet.")),
    ).toBeInTheDocument();
  },
);
it("shows stale and expired feedback and permits clearing history", async () => {
  vi.spyOn(api, "coaching").mockResolvedValue({
    ...coachingFixture,
    feedback: [
      { ...record, is_current: false, is_hidden: false },
      {
        ...record,
        recommendation_id: "older",
        status: "snoozed",
        is_hidden: false,
        snoozed_until: "2026-10-29",
      },
    ],
  });
  view();
  await load();
  await userEvent.click(screen.getByText("Coaching feedback history"));
  expect(
    screen.getByText(
      "This recommendation has changed or is no longer current.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByText("Snooze expired")).toBeInTheDocument();
  expect(
    screen.getAllByRole("button", { name: "Restore recommendation" }),
  ).toHaveLength(2);
});
