import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Accounts } from "../pages/Accounts";
import { Dashboard } from "../pages/Dashboard";
import { Cashflow } from "../pages/Cashflow";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import {
  mockAccountOverview,
  mockEmptyAccountOverview,
  mockUnavailableAccountOverview,
} from "./accounts.fixture";
import { emptyIntelligence } from "./intelligence.fixture";

const testUser = { id: 1, email: "tester@example.com", full_name: "Test User" };

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
});

describe("Accounts page", () => {
  it("renders total trusted BDT position with contributing accounts and account list", async () => {
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);

    render(
      <MemoryRouter>
        <Accounts />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Total trusted BDT position")).toBeInTheDocument();
    expect(screen.getByText("৳55,000.00")).toBeInTheDocument();
    expect(screen.getByTestId("account-card-1")).toBeInTheDocument();
    expect(screen.getByTestId("account-card-2")).toBeInTheDocument();
    expect(screen.getByTestId("account-card-3")).toBeInTheDocument();
    expect(screen.getByTestId("account-card-4")).toBeInTheDocument();

    // Accounts list items
    const checkingCard = screen.getByTestId("account-card-1");
    expect(within(checkingCard).getByText("Main Checking")).toBeInTheDocument();
    expect(within(checkingCard).getByText("Reconciled")).toBeInTheDocument();

    // Mismatch / review badge for Daily Cash
    const cashCard = screen.getByTestId("account-card-3");
    expect(within(cashCard).getByText("Daily Cash")).toBeInTheDocument();
    expect(within(cashCard).getByText("Needs review")).toBeInTheDocument();
    expect(within(cashCard).getByText(/difference/i)).toBeInTheDocument();
    expect(within(cashCard).getByText("৳500.00")).toBeInTheDocument();

    // Foreign currency callout for USD Freelance
    const usdCard = screen.getByTestId("account-card-4");
    expect(within(usdCard).getByText("USD Freelance")).toBeInTheDocument();
    expect(
      within(usdCard).getByText("Not included in trusted BDT position"),
    ).toBeInTheDocument();
  });

  it("renders empty state when no accounts exist", async () => {
    vi.spyOn(api, "accounts").mockResolvedValue(mockEmptyAccountOverview);

    render(
      <MemoryRouter>
        <Accounts />
      </MemoryRouter>,
    );

    expect(await screen.findByText("No accounts yet")).toBeInTheDocument();
    expect(screen.getByText("Not available yet")).toBeInTheDocument();
  });

  it("renders unavailable trusted position when no trusted accounts exist", async () => {
    vi.spyOn(api, "accounts").mockResolvedValue(mockUnavailableAccountOverview);

    render(
      <MemoryRouter>
        <Accounts />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Not available yet")).toBeInTheDocument();
    // Must NOT manufacture ৳0.00
    expect(screen.queryByText("৳0.00")).not.toBeInTheDocument();
  });

  it("expands reconciliation details on user click", async () => {
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);

    render(
      <MemoryRouter>
        <Accounts />
      </MemoryRouter>,
    );

    const checkingCard = await screen.findByTestId("account-card-1");
    const detailsButton = within(checkingCard).getByRole("button", {
      name: /reconciliation details/i,
    });
    expect(detailsButton).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(detailsButton);
    expect(detailsButton).toHaveAttribute("aria-expanded", "true");
    expect(within(checkingCard).getByText("Opening balance")).toBeInTheDocument();
    expect(within(checkingCard).getByText("Derived balance")).toBeInTheDocument();
    expect(within(checkingCard).getByText("Transactions recorded")).toBeInTheDocument();
  });

  it("submits new account dialog", async () => {
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);
    const addAccountSpy = vi.spyOn(api, "addAccount").mockResolvedValue({
      id: 5,
      name: "New Bank",
      source: "Manual",
      account_type: "bank",
      currency: "BDT",
      current_balance: null,
      balance_source: null,
      balance_as_of: null,
      opening_balance: "1000.00",
      opening_balance_date: "2026-11-01",
      reconciliation: {
        status: "unreconciled",
        derived_balance: null,
        difference: null,
        transaction_count: 0,
        confidence: "insufficient_data",
      },
      position_status: "insufficient_data",
      is_eligible_for_bdt_aggregate: false,
    });

    render(
      <MemoryRouter>
        <Accounts />
      </MemoryRouter>,
    );

    await screen.findByTestId("account-card-1");
    await userEvent.click(screen.getByRole("button", { name: /add account/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/account name/i), "New Bank");
    await userEvent.type(within(dialog).getByLabelText(/^opening balance$/i), "1000");

    await userEvent.click(within(dialog).getByRole("button", { name: /save account/i }));

    expect(addAccountSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "New Bank",
        account_type: "bank",
        currency: "BDT",
        opening_balance: "1000",
      }),
    );
  });

  it("submits update current balance dialog", async () => {
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);
    const updateBalanceSpy = vi.spyOn(api, "updateBalance").mockResolvedValue({
      account_id: 1,
      account_name: "Main Checking",
      currency: "BDT",
      reported_balance: "40000.00",
      reported_balance_as_of: "2026-11-01T12:00:00+06:00",
      balance_source: "manual",
      opening_balance: "30000.00",
      opening_balance_date: "2026-10-01",
      latest_transaction_date: null,
      latest_transaction_balance: null,
      difference: "0.00",
      derived_balance: "40000.00",
      status: "reconciled",
      confidence: "high",
      transaction_count: 15,
      message: "Reconciled",
    });

    render(
      <MemoryRouter>
        <Accounts />
      </MemoryRouter>,
    );

    const checkingCard = await screen.findByTestId("account-card-1");
    await userEvent.click(within(checkingCard).getByRole("button", { name: /update balance/i }));

    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText(/current balance/i);
    await userEvent.clear(input);
    await userEvent.type(input, "40000");

    await userEvent.click(within(dialog).getByRole("button", { name: /save balance/i }));

    expect(updateBalanceSpy).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        current_balance: "40000",
        balance_source: "manual",
      }),
    );
  });

  it("submits update opening balance dialog", async () => {
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);
    const updateOpeningSpy = vi.spyOn(api, "updateOpeningBalance").mockResolvedValue({
      account_id: 1,
      account_name: "Main Checking",
      currency: "BDT",
      reported_balance: "35000.00",
      reported_balance_as_of: "2026-11-01T10:00:00+06:00",
      balance_source: "manual",
      opening_balance: "32000.00",
      opening_balance_date: "2026-10-01",
      latest_transaction_date: null,
      latest_transaction_balance: null,
      difference: "0.00",
      derived_balance: "35000.00",
      status: "reconciled",
      confidence: "high",
      transaction_count: 15,
      message: "Reconciled",
    });

    render(
      <MemoryRouter>
        <Accounts />
      </MemoryRouter>,
    );

    const checkingCard = await screen.findByTestId("account-card-1");
    await userEvent.click(within(checkingCard).getByRole("button", { name: /opening balance/i }));

    const dialog = screen.getByRole("dialog");
    const amountInput = within(dialog).getByLabelText(/opening balance \(bdt\)/i);
    await userEvent.clear(amountInput);
    await userEvent.type(amountInput, "32000");

    await userEvent.click(within(dialog).getByRole("button", { name: /save balance/i }));

    expect(updateOpeningSpy).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        opening_balance: "32000",
        opening_balance_date: "2026-10-01",
      }),
    );
  });

  it("localizes properly in Bengali", async () => {
    setLanguage("bn");
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);

    render(
      <MemoryRouter>
        <Accounts />
      </MemoryRouter>,
    );

    expect(await screen.findByText(t("Total trusted BDT position"))).toBeInTheDocument();
    const checkingCard = screen.getByTestId("account-card-1");
    expect(within(checkingCard).getByText(t("Reconciled"))).toBeInTheDocument();

    const cashCard = screen.getByTestId("account-card-3");
    expect(within(cashCard).getByText(t("Needs review"))).toBeInTheDocument();
  });
});

describe("Dashboard account position card", () => {
  it("renders trusted account position on dashboard when available", async () => {
    vi.spyOn(api, "intelligence").mockResolvedValue(emptyIntelligence);
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);
    vi.spyOn(api, "transactions").mockResolvedValue({ items: [], total: 0, limit: 5, offset: 0 });
    vi.spyOn(api, "recommendations").mockResolvedValue({ coverage: { start_date: "", end_date: "", transaction_count: 0, first_transaction_date: null, last_transaction_date: null, limitations: [] }, recommendations: [], limitations: [] });
    vi.spyOn(api, "nudges").mockResolvedValue({ as_of_date: "2026-11-01", insights: [], limitations: [] });

    render(
      <MemoryRouter>
        <Dashboard user={testUser} />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("dashboard-account-position")).toBeInTheDocument();
    const card = screen.getByTestId("dashboard-account-position");
    expect(within(card).getByText("Account position")).toBeInTheDocument();
    expect(within(card).getByText("৳55,000.00")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /view accounts/i })).toHaveAttribute("href", "/accounts");

    // Recorded net activity is also present and separate
    expect(screen.getByText("Recorded net activity")).toBeInTheDocument();
    expect(screen.getByText(/income minus expenses in your bdt records/i)).toBeInTheDocument();
  });

  it("renders Not available yet on dashboard when unavailable without manufacturing 0", async () => {
    vi.spyOn(api, "intelligence").mockResolvedValue(emptyIntelligence);
    vi.spyOn(api, "accounts").mockResolvedValue(mockUnavailableAccountOverview);
    vi.spyOn(api, "transactions").mockResolvedValue({ items: [], total: 0, limit: 5, offset: 0 });
    vi.spyOn(api, "recommendations").mockResolvedValue({ coverage: { start_date: "", end_date: "", transaction_count: 0, first_transaction_date: null, last_transaction_date: null, limitations: [] }, recommendations: [], limitations: [] });
    vi.spyOn(api, "nudges").mockResolvedValue({ as_of_date: "2026-11-01", insights: [], limitations: [] });

    render(
      <MemoryRouter>
        <Dashboard user={testUser} />
      </MemoryRouter>,
    );

    const card = await screen.findByTestId("dashboard-account-position");
    expect(within(card).getByText("Not available yet")).toBeInTheDocument();
    expect(within(card).queryByText("৳0.00")).not.toBeInTheDocument();
  });
});

describe("Cashflow account-backed integration", () => {
  it("allows selecting trusted account position for cashflow outlook", async () => {
    vi.spyOn(api, "scheduled").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);
    const cashflowSpy = vi.spyOn(api, "cashflow").mockResolvedValue({
      as_of_date: "2026-11-01",
      starting_balance: "55000.00",
      balance_source: "account_position",
      months: [],
      coverage: {
        start_date: "2026-08-01",
        end_date: "2026-10-31",
        transaction_count: 20,
        first_transaction_date: "2026-08-05",
        last_transaction_date: "2026-10-30",
        limitations: [],
      },
      assumptions: [],
      limitations: [],
    });

    render(
      <MemoryRouter>
        <Cashflow />
      </MemoryRouter>,
    );

    const radioGroup = await screen.findByRole("radiogroup", { name: "Starting balance source" });
    const trustedRadio = within(radioGroup).getByRole("radio", { name: /use trusted account position/i });
    expect(trustedRadio).not.toBeDisabled();

    await userEvent.click(trustedRadio);

    // Shows contributing accounts
    expect(screen.getByText(/main checking, city savings/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /build outlook/i }));

    expect(cashflowSpy).toHaveBeenCalledWith({
      use_account_position: true,
      months_ahead: 3,
    });

    expect(await screen.findByText(/starting balance from trusted accounts:/i)).toBeInTheDocument();
  });

  it("allows selecting trusted account position for purchase decision", async () => {
    vi.spyOn(api, "scheduled").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    vi.spyOn(api, "accounts").mockResolvedValue(mockAccountOverview);
    const decisionSpy = vi.spyOn(api, "decision").mockResolvedValue({
      status: "safe",
      purchase_amount: "15000.00",
      scheduled_expense_reserve: "10000.00",
      remaining_after_purchase_and_reserve: "30000.00",
      uncertain_scheduled_income: "0.00",
      horizon_end: "2026-12-01",
      balance_source: "account_position",
      assumptions: [],
      warnings: [],
    });

    render(
      <MemoryRouter>
        <Cashflow />
      </MemoryRouter>,
    );

    const purchaseSection = document.getElementById("purchase")!;
    const radioGroup = within(purchaseSection).getByRole("radiogroup", { name: "Available balance source" });
    const trustedRadio = within(radioGroup).getByRole("radio", { name: /use trusted account position/i });
    await userEvent.click(trustedRadio);

    await userEvent.type(within(purchaseSection).getByLabelText(/purchase amount/i), "15000");
    await userEvent.type(within(purchaseSection).getByLabelText(/safety buffer/i), "5000");

    await userEvent.click(within(purchaseSection).getByRole("button", { name: /assess purchase/i }));

    expect(decisionSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        use_account_position: true,
        purchase_amount: "15000",
        safety_buffer: "5000",
        horizon_days: 30,
      }),
    );

    expect(await screen.findByText("Using trusted account position")).toBeInTheDocument();
  });
});
