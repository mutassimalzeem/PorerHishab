import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FinancialTimeline } from "../components/FinancialTimeline";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import {
  emptyTimeline,
  timelineFixture,
  timelineEvent,
} from "./timeline.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});
describe("financial timeline", () => {
  it("renders unique actual, payment, scheduled, estimated and uncertain events with separate cash scopes", async () => {
    vi.spyOn(api, "timeline").mockResolvedValue(timelineFixture);
    render(<FinancialTimeline />);
    await userEvent.click(
      screen.getByRole("button", { name: "Load timeline" }),
    );
    const list = await screen.findByRole("list", {
      name: "Financial timeline",
    });
    expect(within(list).getAllByRole("listitem")).toHaveLength(7);
    for (const label of [
      "Actual",
      "Confirmed",
      "Scheduled",
      "Estimated",
      "Uncertain",
    ]) {
      expect(within(list).getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(within(list).getByText(/Historical movement/)).toBeInTheDocument();
    expect(within(list).getByText("Groceries")).toBeInTheDocument();
    expect(screen.getAllByText("Not available")).toHaveLength(2);
    const payment = within(list).getByText("Rent payment").closest("li")!;
    expect(within(payment).getAllByText("Context only").length).toBeGreaterThan(
      0,
    );
    expect(within(payment).getByText(/Transaction 1/)).toBeInTheDocument();
  });
  it("shows empty data without fabricated events", async () => {
    vi.spyOn(api, "timeline").mockResolvedValue(emptyTimeline);
    render(<FinancialTimeline />);
    await userEvent.click(
      screen.getByRole("button", { name: "Load timeline" }),
    );
    expect(await screen.findByText("No timeline events")).toBeInTheDocument();
    expect(
      screen.queryByRole("list", { name: "Financial timeline" }),
    ).not.toBeInTheDocument();
  });
  it("announces loading and disables duplicate requests", async () => {
    vi.spyOn(api, "timeline").mockImplementation(() => new Promise(() => {}));
    render(<FinancialTimeline />);
    await userEvent.click(
      screen.getByRole("button", { name: "Load timeline" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent("Loading timeline...");
    expect(
      screen.getByRole("button", { name: "Load timeline" }),
    ).toBeDisabled();
  });
  it("reports API errors and can retry", async () => {
    vi.spyOn(api, "timeline")
      .mockRejectedValueOnce(new Error("Timeline unavailable"))
      .mockResolvedValueOnce(emptyTimeline);
    render(<FinancialTimeline />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Load timeline" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Timeline unavailable",
    );
    await user.click(screen.getByRole("button", { name: "Load timeline" }));
    expect(await screen.findByText("No timeline events")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("uses Bengali labels and keeps user titles unchanged", async () => {
    setLanguage("bn");
    vi.spyOn(api, "timeline").mockResolvedValue(timelineFixture);
    render(<FinancialTimeline />);
    await userEvent.click(
      screen.getByRole("button", { name: t("Load timeline") }),
    );
    expect(
      await screen.findByRole("list", { name: t("Financial timeline") }),
    ).toBeInTheDocument();
    expect(screen.getByText("Groceries")).toBeInTheDocument();
    expect(screen.getByText(t("Uncertain"))).toBeInTheDocument();
  });
  it("reveals additional events without duplicates and refreshes stale data", async () => {
    const events = Array.from({ length: 23 }, (_, i) =>
      timelineEvent(`tx:${i}`, "transaction", "actual", `Merchant ${i}`),
    );
    vi.spyOn(api, "timeline")
      .mockResolvedValueOnce({ ...timelineFixture, events })
      .mockResolvedValueOnce(emptyTimeline);
    render(<FinancialTimeline />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Load timeline" }));
    const list = await screen.findByRole("list", {
      name: "Financial timeline",
    });
    expect(within(list).getAllByRole("listitem")).toHaveLength(20);
    await user.click(screen.getByRole("button", { name: "Show more events" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(23);
    await user.click(screen.getByRole("button", { name: "Refresh timeline" }));
    expect(await screen.findByText("No timeline events")).toBeInTheDocument();
    expect(screen.queryByText("Merchant 1")).not.toBeInTheDocument();
  });
});
