import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Auth } from "../pages/Auth";
import { Dashboard } from "../pages/Dashboard";
import { Ask } from "../pages/Ask";
import { Amount } from "../components/ui";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useCallback } from "react";
import { ResourceView } from "../components/ui";
const wrap = (node: React.ReactNode) =>
  render(<MemoryRouter>{node}</MemoryRouter>);
describe("trustworthy financial experiences", () => {
  it("renders unknown distinctly from zero", () => {
    render(
      <>
        <Amount value={null} />
        <Amount value="0.00" />
      </>,
    );
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText(/0.00/)).toBeInTheDocument();
  });
  it("shows a recoverable login failure and retains input", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new Error("Invalid credentials"));
    const user = userEvent.setup();
    wrap(<Auth onLogin={vi.fn()} expired={false} />);
    await user.type(screen.getByLabelText("Email address"), "a@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid credentials",
    );
    expect(screen.getByLabelText("Email address")).toHaveValue("a@example.com");
  });
  it("uses real empty states and never calls an empty history an available balance", async () => {
    vi.spyOn(api, "summary").mockResolvedValue({
      transaction_count: 0,
      total_income: "0",
      total_expenses: "0",
      net: "0",
      savings_rate: null,
    });
    vi.spyOn(api, "transactions").mockResolvedValue({
      items: [],
      total: 0,
      limit: 5,
      offset: 0,
    });
    vi.spyOn(api, "scheduled").mockResolvedValue({
      items: [],
      total: 0,
      limit: 4,
      offset: 0,
    });
    vi.spyOn(api, "nudges").mockResolvedValue({
      as_of_date: "2026-10-25",
      insights: [],
      limitations: ["History incomplete"],
    });
    vi.spyOn(api, "recommendations").mockResolvedValue({
      coverage: {
        start_date: "2026-07-01",
        end_date: "2026-09-30",
        transaction_count: 0,
        first_transaction_date: null,
        last_transaction_date: null,
        limitations: [],
      },
      recommendations: [],
      limitations: [],
    });
    wrap(
      <Dashboard user={{ id: 1, email: "a@example.com", full_name: null }} />,
    );
    expect(
      await screen.findByText("Recorded net activity"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Not available")).toHaveLength(3);
    expect(
      await screen.findByText("Give your next month some shape"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/This is not your account balance/),
    ).toBeInTheDocument();
  });
  it("shows insufficient Ask answers with inspectable limitations", async () => {
    vi.spyOn(api, "ask").mockResolvedValue({
      answer: "Your records are too short.",
      intent: "savings",
      sources: [],
      calculation: { total: null },
      coverage: null,
      date_range: null,
      assumptions: [],
      limitations: ["No complete months"],
      status: "insufficient_data",
    });
    const user = userEvent.setup();
    wrap(<Ask />);
    await user.click(
      screen.getByRole("button", { name: "How much can I save this month?" }),
    );
    await user.click(screen.getByRole("button", { name: "Ask PorerHishab" }));
    expect(
      await screen.findByText("Your records are too short."),
    ).toBeInTheDocument();
    expect(screen.getByText("insufficient data")).toBeInTheDocument();
    await user.click(screen.getByText("Assumptions & data limitations"));
    expect(screen.getByText("No complete months")).toBeVisible();
  });
  it("supports retry and prevents stale period responses from winning", async () => {
    let resolveOld: (value: string) => void = () => {};
    const old = new Promise<string>((resolve) => {
      resolveOld = resolve;
    });
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error("Offline"))
      .mockResolvedValue("Recovered");
    function Probe({ version }: { version: number }) {
      const resource = useResource<string>(
        useCallback(() => (version === 1 ? old : loader()), [version]),
      );
      return (
        <ResourceView resource={resource}>
          {(value) => <p>{value}</p>}
        </ResourceView>
      );
    }
    const user = userEvent.setup();
    const view = render(<Probe version={1} />);
    view.rerender(<Probe version={2} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Recovered")).toBeInTheDocument();
    resolveOld("Stale");
    await waitFor(() =>
      expect(screen.queryByText("Stale")).not.toBeInTheDocument(),
    );
  });
});
