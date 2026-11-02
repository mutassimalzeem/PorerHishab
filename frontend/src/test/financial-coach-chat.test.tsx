import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { FinancialCoach } from "../components/FinancialCoach";
import { api } from "../lib/api";
import { setLanguage } from "../lib/locale";
import type { CoachResponse, CoachConversationPage } from "../domain";

const mockResponse: CoachResponse = {
  conversation_id: "conv_test_123",
  intent: "spending_analysis",
  answer: "In October, your total spending was 18,500 BDT across 12 transactions.",
  summary: "Total spending was 18,500 BDT.",
  claims: [
    {
      claim_id: "cl_1",
      text: "Total recorded spending was 18,500 BDT.",
      evidence_ids: ["ev_spending_total_expenses"],
    },
  ],
  evidence: [
    {
      evidence_id: "ev_spending_total_expenses",
      evidence_type: "derived_fact",
      source: "intelligence_facts.totals",
      label: "Total expenses",
      value: "18500.00",
      unit: "BDT",
    },
    {
      evidence_id: "ev_spending_baseline_monthly_expenses",
      evidence_type: "estimate",
      source: "intelligence_snapshot.monthly_history",
      label: "Historical average expenses",
      value: "16000.00",
      unit: "BDT",
    },
  ],
  actions: [
    {
      action_id: "act_1",
      title: "Review dining budget",
      description: "Examine restaurant spending to reduce costs.",
      priority: 2,
      evidence_ids: ["ev_spending_total_expenses"],
    },
  ],
  warnings: [],
  limitations: ["Recorded transactions in PorerHishab only."],
};

const mockEmptyConversations: CoachConversationPage = {
  items: [],
  total: 0,
  limit: 10,
  offset: 0,
};

beforeEach(() => {
  vi.restoreAllMocks();
  setLanguage("en");
  vi.spyOn(api, "coachConversations").mockResolvedValue(mockEmptyConversations);
});

function renderCoach() {
  render(
    <MemoryRouter>
      <FinancialCoach />
    </MemoryRouter>,
  );
}

describe("FinancialCoach frontend component", () => {
  it("renders empty state with starters and input field", async () => {
    renderCoach();
    expect(
      screen.getByText("What would you like to explore?"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Where did my money go this month?"),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
      ),
    ).toBeInTheDocument();
  });

  it("clicking a starter populates the input textarea", async () => {
    renderCoach();
    const starterBtn = screen.getByText("Where did my money go this month?");
    await userEvent.click(starterBtn);

    const textarea = screen.getByPlaceholderText(
      "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
    ) as HTMLTextAreaElement;
    expect(textarea.value).toBe("Where did my money go this month?");
  });

  it("submits question and renders structured answer, evidence, and actions", async () => {
    const askSpy = vi.spyOn(api, "coachAsk").mockResolvedValue(mockResponse);
    renderCoach();

    const textarea = screen.getByPlaceholderText(
      "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
    );
    await userEvent.type(textarea, "How much did I spend?");
    const sendBtn = screen.getByRole("button", { name: "Send question" });
    await userEvent.click(sendBtn);

    expect(askSpy).toHaveBeenCalledWith(
      { message: "How much did I spend?", conversation_id: undefined },
      "en",
    );

    // Verify response prose and summary
    expect(
      await screen.findByText(
        "In October, your total spending was 18,500 BDT across 12 transactions.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Total spending was 18,500 BDT."),
    ).toBeInTheDocument();

    // Verify actions and advisory disclaimer
    expect(screen.getByText("Review dining budget")).toBeInTheDocument();
    expect(
      screen.getByText("(Suggestions for review; not executed transactions)"),
    ).toBeInTheDocument();

    // Expand evidence drawer
    const evidenceToggle = screen.getByRole("button", {
      name: /Verified Evidence used/i,
    });
    await userEvent.click(evidenceToggle);

    expect(screen.getByText("Observed Fact")).toBeInTheDocument();
    expect(screen.getByText("Estimate")).toBeInTheDocument();
    expect(screen.getByText("Total expenses")).toBeInTheDocument();
  });

  it("displays error notice and supports retry on request failure", async () => {
    const askSpy = vi
      .spyOn(api, "coachAsk")
      .mockRejectedValueOnce(new Error("Network gateway timeout"))
      .mockResolvedValueOnce(mockResponse);

    renderCoach();

    const textarea = screen.getByPlaceholderText(
      "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
    );
    await userEvent.type(textarea, "Where did my money go?");
    const sendBtn = screen.getByRole("button", { name: "Send question" });
    await userEvent.click(sendBtn);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Try again")).toBeInTheDocument();

    // Click retry
    const retryBtn = screen.getByText("Try again");
    await userEvent.click(retryBtn);

    expect(askSpy).toHaveBeenCalledTimes(2);
    expect(
      await screen.findByText(
        "In October, your total spending was 18,500 BDT across 12 transactions.",
      ),
    ).toBeInTheDocument();
  });

  it("supports starting a new conversation to clear the thread", async () => {
    vi.spyOn(api, "coachAsk").mockResolvedValue(mockResponse);
    renderCoach();

    const textarea = screen.getByPlaceholderText(
      "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
    );
    await userEvent.type(textarea, "Hello coach");
    await userEvent.click(screen.getByRole("button", { name: "Send question" }));

    expect(
      await screen.findByText(
        "In October, your total spending was 18,500 BDT across 12 transactions.",
      ),
    ).toBeInTheDocument();

    // Click New Chat
    const newChatBtn = screen.getByRole("button", { name: "New chat" });
    await userEvent.click(newChatBtn);

    // Thread is cleared back to empty state
    expect(
      screen.getByText("What would you like to explore?"),
    ).toBeInTheDocument();
  });

  it("localizes headings when language is switched to Bengali", async () => {
    setLanguage("bn");
    renderCoach();

    expect(
      screen.getByText("পরের হিসাব আর্থিক কোচ"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("নতুন আলোচনা"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("আপনি কী জানতে চান?"),
    ).toBeInTheDocument();
  });
});

