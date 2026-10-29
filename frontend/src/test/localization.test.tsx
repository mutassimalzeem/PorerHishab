import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../lib/Language";
import {
  digits,
  getLanguage,
  languageStorageKey,
  percent,
  readLanguage,
  setLanguage,
  t,
} from "../lib/locale";
import { bn } from "../lib/translations";
import { date, money, today } from "../lib/format";
import { Auth } from "../pages/Auth";
import { Ask } from "../pages/Ask";
import { Plans } from "../pages/Plans";
import { TransactionTable } from "../components/TransactionTable";
import { api } from "../lib/api";
import { richIntelligence } from "./intelligence.fixture";
beforeEach(() => {
  act(() => setLanguage("en"));
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  setLanguage("en");
  localStorage.clear();
});
describe("English and Bengali interface", () => {
  it("switches immediately, retains authentication input, and persists the explicit preference", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LanguageProvider>
          <Auth onLogin={vi.fn()} expired={false} />
        </LanguageProvider>
      </MemoryRouter>,
    );
    await user.type(
      screen.getByLabelText("Email address"),
      "reader@example.com",
    );
    await user.type(screen.getByLabelText("Password"), "unchanged-password");
    await user.click(
      screen.getByRole("button", { name: "\u09ac\u09be\u0982\u09b2\u09be" }),
    );
    expect(document.documentElement.lang).toBe("bn");
    expect(document.title).toBe(bn["Sign in"] + " | PorerHishab");
    expect(screen.getByLabelText(bn["Email address"])).toHaveValue(
      "reader@example.com",
    );
    expect(screen.getByLabelText(bn.Password)).toHaveValue(
      "unchanged-password",
    );
    expect(localStorage.getItem(languageStorageKey)).toBe("bn");
    expect(readLanguage()).toBe("bn");
    await user.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByLabelText("Email address")).toHaveValue(
      "reader@example.com",
    );
    expect(document.documentElement.lang).toBe("en");
  });
  it("formats Bengali money, dates, counts and percentages without changing canonical dates or unknown values", () => {
    const canonical = today();
    setLanguage("bn");
    expect(money("1234.50")).toMatch(/[\u09e6-\u09ef]/);
    expect(money(null)).toBe(bn["Not available"]);
    expect(money("0.00")).not.toBe(money(null));
    expect(date("2026-10-29")).toMatch(/[\u09e6-\u09ef]/);
    expect(digits(123)).toBe("\u09e7\u09e8\u09e9");
    expect(percent(25)).toContain("\u09e8\u09eb");
    expect(today()).toBe(canonical);
    expect(today()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
  it("continues switching when browser storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readLanguage()).toBe("en");
    expect(() => setLanguage("bn")).not.toThrow();
    expect(getLanguage()).toBe("bn");
    expect(t("Overview")).toBe(bn.Overview);
  });
  it("preserves backend explanations and user text even when they match interface dictionary keys", async () => {
    setLanguage("bn");
    const user = userEvent.setup();
    vi.spyOn(api, "ask").mockResolvedValue({
      answer: "Income",
      status: "insufficient_data",
      intent: "savings",
      sources: [],
      calculation: {},
      coverage: null,
      date_range: null,
      assumptions: ["Overview"],
      limitations: ["Backend text stays unchanged."],
    });
    render(
      <MemoryRouter>
        <Ask />
      </MemoryRouter>,
    );
    await user.type(
      screen.getByLabelText(bn["Your financial question"]),
      "How much can I save?",
    );
    await user.click(
      screen.getByRole("button", { name: bn["Ask PorerHishab"] }),
    );
    expect(await screen.findByText("Income")).toBeInTheDocument();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText(bn.insufficient_data)).toBeInTheDocument();
    cleanup();
    render(
      <MemoryRouter>
        <TransactionTable
          items={[
            {
              id: 1,
              merchant: "Overview",
              description: "Income",
              date: "2026-10-29",
              amount: "-12.50",
              category: "Settings",
              fee: "0",
              balance: null,
              source: "manual",
              category_reason: null,
            },
          ]}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Income")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });
  it("switches an open goal editor without losing values or refetching its contribution plan", async () => {
    const goal = richIntelligence.snapshot.goals[0];
    vi.spyOn(api, "goals").mockResolvedValue({
      total: 1,
      limit: 20,
      offset: 0,
      items: [
        {
          id: goal.goal_id,
          name: goal.name,
          description: null,
          target_amount: goal.target_amount,
          target_date: goal.target_date,
          current_saved: goal.current_saved,
          status: goal.status,
        },
      ],
    });
    const plan = vi.spyOn(api, "goalPlan").mockResolvedValue({
      goal_id: goal.goal_id,
      as_of_date: "2026-10-29",
      remaining_amount: "1000",
      required_weekly: "100",
      required_monthly: "400",
      estimated_monthly_capacity: null,
      affordability: "unknown",
      assumptions: [],
      limitations: [],
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LanguageProvider>
          <Plans />
        </LanguageProvider>
      </MemoryRouter>,
    );
    await screen.findByText("Capacity is not established");
    await user.click(screen.getByRole("button", { name: "Edit " + goal.name }));
    await user.clear(screen.getByLabelText("Goal name"));
    await user.type(screen.getByLabelText("Goal name"), "My unchanged draft");
    await user.click(
      screen.getByRole("button", { name: "\u09ac\u09be\u0982\u09b2\u09be" }),
    );
    expect(screen.getByLabelText(bn["Goal name"])).toHaveValue(
      "My unchanged draft",
    );
    expect(screen.getByRole("dialog")).toHaveAttribute("open");
    await waitFor(() => expect(plan).toHaveBeenCalledTimes(1));
  });

  it("localizes an existing failure when switching languages and restores its English detail", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new Error("Invalid credentials"));
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LanguageProvider>
          <Auth onLogin={vi.fn()} expired={false} />
        </LanguageProvider>
      </MemoryRouter>,
    );
    await user.type(
      screen.getByLabelText("Email address"),
      "reader@example.com",
    );
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid credentials",
    );
    await user.click(
      screen.getByRole("button", { name: "\u09ac\u09be\u0982\u09b2\u09be" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      bn["The request could not be completed. Please try again."],
    );
    await user.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid credentials");
  });
});
