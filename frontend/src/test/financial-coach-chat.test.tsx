import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { FinancialCoach } from "../components/FinancialCoach";
import { api, ApiError } from "../lib/api";
import { setLanguage } from "../lib/locale";
import type {
  CoachResponse,
  CoachConversationPage,
  CoachConversationDetail,
} from "../domain";

const mockResponse: CoachResponse = {
  conversation_id: "conv_test_123",
  intent: "spending_analysis",
  answer:
    "In October, your total spending was 18,500 BDT across 12 transactions.",
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
  sessionStorage.clear();
  vi.restoreAllMocks();
  setLanguage("en");
  vi.spyOn(api, "coachConversations").mockResolvedValue(mockEmptyConversations);
  vi.spyOn(api, "coachRequestStatus").mockRejectedValue(
    new ApiError(404, "Request not received"),
  );
});

function renderCoach(ownerId?: number) {
  render(
    <MemoryRouter>
      <FinancialCoach ownerId={ownerId} />
    </MemoryRouter>,
  );
}

describe("FinancialCoach frontend component", () => {
  it("recovers a persisted answer after a lost response without submitting another turn", async () => {
    const ask = vi
      .spyOn(api, "coachAsk")
      .mockRejectedValue(new Error("Lost response"));
    vi.mocked(api.coachRequestStatus).mockImplementation(async (key) => ({
      request_id: key,
      conversation_id: "conv_test_123",
      message: "Lost question",
      language: "en",
      schedules_confirmed: false,
      status: "completed",
      retry_safe: false,
      response: { ...mockResponse, request_id: key },
    }));
    renderCoach();
    await userEvent.type(
      screen.getByLabelText("Ask your financial coach"),
      "Lost question",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Send question" }),
    );
    expect(await screen.findByText(mockResponse.answer)).toBeInTheDocument();
    expect(screen.getAllByText("Lost question")).toHaveLength(1);
    expect(screen.getAllByText(mockResponse.answer)).toHaveLength(1);
    expect(ask).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Try again")).not.toBeInTheDocument();
  });

  it("offers status checks rather than retry while the server is still processing", async () => {
    vi.spyOn(api, "coachAsk").mockRejectedValue(new Error("Timeout"));
    const status = vi
      .mocked(api.coachRequestStatus)
      .mockImplementation(async (key) => ({
        request_id: key,
        conversation_id: "conv_test_123",
        message: "Processing question",
        language: "en",
        schedules_confirmed: false,
        status: "processing",
        retry_safe: false,
        retry_after_seconds: 30,
      }));
    renderCoach();
    await userEvent.type(
      screen.getByLabelText("Ask your financial coach"),
      "Processing question",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Send question" }),
    );
    await screen.findByText("Still processing");
    expect(screen.queryByText("Try again")).not.toBeInTheDocument();
    status.mockImplementation(async (key) => ({
      request_id: key,
      conversation_id: "conv_test_123",
      message: "Processing question",
      language: "en",
      schedules_confirmed: false,
      status: "completed",
      retry_safe: false,
      response: mockResponse,
    }));
    await userEvent.click(
      screen.getByRole("button", { name: "Check request status" }),
    );
    expect(await screen.findByText(mockResponse.answer)).toBeInTheDocument();
  });

  it("does not offer retry when neither the response nor server status is known", async () => {
    vi.spyOn(api, "coachAsk").mockRejectedValue(new Error("Timeout"));
    vi.mocked(api.coachRequestStatus).mockRejectedValue(
      new Error("Status unavailable"),
    );
    renderCoach();
    await userEvent.type(
      screen.getByLabelText("Ask your financial coach"),
      "Unknown question",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Send question" }),
    );
    expect(await screen.findByText("Status unknown")).toBeInTheDocument();
    expect(screen.queryByText("Try again")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Check request status" }),
    ).toBeEnabled();
  });

  it("restores the owner selection and loads earlier messages chronologically", async () => {
    sessionStorage.setItem(
      "porerhishab.coach.99",
      JSON.stringify({ conversationId: "conv_old" }),
    );
    const detail: CoachConversationDetail = {
      id: "conv_old",
      title: "History",
      created_at: "2026-11-01",
      updated_at: "2026-11-01",
      has_more: true,
      next_before_id: 3,
      messages: [
        {
          id: 3,
          conversation_id: "conv_old",
          role: "user",
          content: "Newer question",
          created_at: "2026-11-01",
        },
        {
          id: 4,
          conversation_id: "conv_old",
          role: "assistant",
          content: "Newer answer",
          created_at: "2026-11-01",
        },
      ],
    };
    const load = vi
      .spyOn(api, "coachConversationDetail")
      .mockResolvedValueOnce(detail)
      .mockResolvedValueOnce({
        ...detail,
        has_more: false,
        next_before_id: 1,
        messages: [
          {
            id: 1,
            conversation_id: "conv_old",
            role: "user",
            content: "Older question",
            created_at: "2026-10-01",
          },
          {
            id: 2,
            conversation_id: "conv_old",
            role: "assistant",
            content: "Older answer",
            created_at: "2026-10-01",
          },
        ],
      });
    renderCoach(99);
    expect(await screen.findByText("Newer answer")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Load older messages" }),
    );
    await screen.findByText("Older answer");
    expect(load).toHaveBeenLastCalledWith("conv_old", 3);
    const rows = screen.getByRole("log").querySelectorAll(".coach-answer-text");
    expect([...rows].map((r) => r.textContent)).toEqual([
      "Older question",
      "Older answer",
      "Newer question",
      "Newer answer",
    ]);
  });

  it("loads conversations beyond the initial ten", async () => {
    const items = Array.from({ length: 11 }, (_, i) => ({
      id: `conv_${i}`,
      title: `Thread ${i}`,
      created_at: "2026-11-01",
      updated_at: "2026-11-01",
    }));
    const list = vi
      .mocked(api.coachConversations)
      .mockResolvedValueOnce({
        items: items.slice(0, 10),
        total: 11,
        limit: 10,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: items.slice(10),
        total: 11,
        limit: 10,
        offset: 10,
      });
    renderCoach();
    await userEvent.click(screen.getByRole("button", { name: "Saved chats" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Load more conversations" }),
    );
    await screen.findByText("Thread 10");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(10, 10));
  });

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
      {
        message: "How much did I spend?",
        conversation_id: undefined,
        request_id: expect.any(String),
      },
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

  it("displays error notice and supports retry on request failure without duplicate messages", async () => {
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

    // There must be exactly 1 instance of the user's question rendered
    expect(screen.getAllByText("Where did my money go?").length).toBe(1);

    // Click retry
    const retryBtn = screen.getByText("Try again");
    await userEvent.click(retryBtn);

    expect(askSpy).toHaveBeenCalledTimes(2);
    expect(askSpy.mock.calls[0][0].request_id).toBe(
      askSpy.mock.calls[1][0].request_id,
    );
    expect(
      await screen.findByText(
        "In October, your total spending was 18,500 BDT across 12 transactions.",
      ),
    ).toBeInTheDocument();

    // After retry success, there still must be only 1 user question in the conversation thread
    expect(screen.getAllByText("Where did my money go?").length).toBe(1);
  });

  it("repeated retry retains only one user message across multiple failures", async () => {
    const askSpy = vi
      .spyOn(api, "coachAsk")
      .mockRejectedValueOnce(new Error("Timeout 1"))
      .mockRejectedValueOnce(new Error("Timeout 2"))
      .mockResolvedValueOnce(mockResponse);

    renderCoach();

    const textarea = screen.getByPlaceholderText(
      "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
    );
    await userEvent.type(textarea, "How is my budget?");
    await userEvent.click(
      screen.getByRole("button", { name: "Send question" }),
    );

    // First failure
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getAllByText("How is my budget?").length).toBe(1);

    // First retry -> fails again
    await userEvent.click(screen.getByText("Try again"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getAllByText("How is my budget?").length).toBe(1);

    // Second retry -> succeeds
    await userEvent.click(screen.getByText("Try again"));
    expect(
      await screen.findByText(
        "In October, your total spending was 18,500 BDT across 12 transactions.",
      ),
    ).toBeInTheDocument();

    // Must still have only 1 user message
    expect(screen.getAllByText("How is my budget?").length).toBe(1);
    expect(askSpy).toHaveBeenCalledTimes(3);
  });

  it("prevents double submission on rapid double click", async () => {
    let resolveAsk: (value: CoachResponse) => void = () => {};
    const pendingPromise = new Promise<CoachResponse>((resolve) => {
      resolveAsk = resolve;
    });
    const askSpy = vi.spyOn(api, "coachAsk").mockReturnValue(pendingPromise);

    renderCoach();

    const textarea = screen.getByPlaceholderText(
      "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
    );
    await userEvent.type(textarea, "Can I afford 10000 BDT?");
    const sendBtn = screen.getByRole("button", { name: "Send question" });

    // Double click rapidly
    await userEvent.click(sendBtn);
    await userEvent.click(sendBtn);

    expect(askSpy).toHaveBeenCalledTimes(1);

    resolveAsk(mockResponse);
  });

  it("discards in-flight responses when switching conversations", async () => {
    let resolveFirstAsk: (value: CoachResponse) => void = () => {};
    const firstPromise = new Promise<CoachResponse>((resolve) => {
      resolveFirstAsk = resolve;
    });

    vi.spyOn(api, "coachAsk").mockReturnValue(firstPromise);

    const mockConversationsList: CoachConversationPage = {
      items: [
        {
          id: "conv_archived_99",
          title: "Archived Savings Chat",
          created_at: "2026-10-01T00:00:00Z",
          updated_at: "2026-10-01T00:00:00Z",
        },
      ],
      total: 1,
      limit: 10,
      offset: 0,
    };
    vi.spyOn(api, "coachConversations").mockResolvedValue(
      mockConversationsList,
    );

    const mockDetail: CoachConversationDetail = {
      id: "conv_archived_99",
      title: "Archived Savings Chat",
      created_at: "2026-10-01T00:00:00Z",
      updated_at: "2026-10-01T00:00:00Z",
      messages: [
        {
          id: 1,
          conversation_id: "conv_archived_99",
          role: "assistant",
          content: "Archived conversation historic message.",
          created_at: "2026-10-01T00:00:00Z",
        },
      ],
    };
    vi.spyOn(api, "coachConversationDetail").mockResolvedValue(mockDetail);

    renderCoach();

    // Start a question in thread 1
    const textarea = screen.getByPlaceholderText(
      "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
    );
    await userEvent.type(textarea, "Pending question in thread 1");
    await userEvent.click(
      screen.getByRole("button", { name: "Send question" }),
    );

    // While request is pending, switch to archived chat
    const historyBtn = screen.getByRole("button", { name: "Saved chats" });
    await userEvent.click(historyBtn);
    const itemBtn = await screen.findByText("Archived Savings Chat");
    await userEvent.click(itemBtn);

    // Selected conversation is loaded
    expect(
      await screen.findByText("Archived conversation historic message."),
    ).toBeInTheDocument();

    // Now resolve the in-flight request from previous conversation
    resolveFirstAsk({
      ...mockResponse,
      answer: "Response for abandoned question 1.",
    });

    // The abandoned response must NOT be displayed in this conversation
    expect(
      screen.queryByText("Response for abandoned question 1."),
    ).not.toBeInTheDocument();
  });

  it("supports starting a new conversation to clear the thread", async () => {
    vi.spyOn(api, "coachAsk").mockResolvedValue(mockResponse);
    renderCoach();

    const textarea = screen.getByPlaceholderText(
      "Ask about spending, cashflow, purchases, or goals... (Press Enter to send)",
    );
    await userEvent.type(textarea, "Hello coach");
    await userEvent.click(
      screen.getByRole("button", { name: "Send question" }),
    );

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

    expect(screen.getByText("পরের হিসাব আর্থিক কোচ")).toBeInTheDocument();
    expect(screen.getByText("নতুন আলোচনা")).toBeInTheDocument();
    expect(screen.getByText("আপনি কী জানতে চান?")).toBeInTheDocument();
  });
});
