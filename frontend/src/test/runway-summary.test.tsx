import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RunwaySummary } from "../components/RunwaySummary";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import { unknownRunway, populatedRunway } from "./runway.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});
describe("account runway summary", () => {
  it("loads on request and preserves unknowns instead of showing zero", async () => {
    const read = vi.spyOn(api, "runway").mockResolvedValue(unknownRunway);
    render(<RunwaySummary />);
    expect(read).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: "Check account runway" }),
    );
    expect(await screen.findByText("insufficient data")).toBeInTheDocument();
    expect(screen.getAllByText("Not available")).toHaveLength(3);
    expect(screen.getByText(/Monthly estimates cannot/)).toBeInTheDocument();
  });
  it("renders populated cash and refreshes without retaining stale results", async () => {
    vi.spyOn(api, "runway")
      .mockResolvedValueOnce(populatedRunway)
      .mockResolvedValueOnce(unknownRunway);
    render(<RunwaySummary />);
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Check account runway" }),
    );
    expect(await screen.findByText("positive")).toBeInTheDocument();
    expect(screen.queryByText("Not available")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Refresh account runway" }),
    );
    expect(await screen.findByText("insufficient data")).toBeInTheDocument();
    expect(screen.queryByText("positive")).not.toBeInTheDocument();
  });
  it("localizes the summary and unknown values in Bengali", async () => {
    setLanguage("bn");
    vi.spyOn(api, "runway").mockResolvedValue(unknownRunway);
    render(<RunwaySummary />);
    await userEvent.click(
      screen.getByRole("button", { name: t("Check account runway") }),
    );
    expect(await screen.findAllByText(t("Not available"))).toHaveLength(3);
    expect(screen.getByText(t("Account cash & runway"))).toBeInTheDocument();
    expect(t("Check account runway")).not.toMatch(/\?/);
  });
  it("shows request failure without fabricating a cash position", async () => {
    vi.spyOn(api, "runway").mockRejectedValue(new Error("Runway unavailable"));
    render(<RunwaySummary />);
    await userEvent.click(
      screen.getByRole("button", { name: "Check account runway" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Runway unavailable",
    );
    expect(screen.queryByText("positive")).not.toBeInTheDocument();
  });
});
