import { beforeEach, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CoachingEffectiveness } from "../components/CoachingEffectiveness";
import { api, setSession } from "../lib/api";
import { digits, setLanguage } from "../lib/locale";
import { bn } from "../lib/translations";
import {
  effectivenessFixture as fixture,
  emptyEffectiveness,
} from "./coaching-effectiveness.fixture";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  setLanguage("en");
  setSession(null);
});
it.each(["en", "bn"] as const)(
  "renders every metric, type and rate in %s",
  async (language) => {
    setLanguage(language);
    vi.spyOn(api, "coachingEffectiveness").mockResolvedValue(fixture);
    render(<CoachingEffectiveness />);
    const label = (key: keyof typeof bn) => (language === "en" ? key : bn[key]);
    await screen.findAllByText(label("Recommendations with feedback"));
    const labels = [
      "Recommendations with feedback",
      "Reported acted on",
      "Dismissed",
      "Not relevant",
      "Snoozed",
      "Measurable outcomes",
      "Improved",
      "Unchanged",
      "Worsened",
      "Insufficient-data outcomes",
    ] as const;
    const values = [7, 4, 1, 1, 1, 3, 1, 2, 0, 1];
    labels.forEach((key, i) =>
      expect(
        screen.getAllByText(label(key))[0].closest("div")?.querySelector("dd"),
      ).toHaveTextContent(digits(values[i])),
    );
    const breakdown = screen.getByRole("list", {
      name: label("By recommendation type"),
    });
    expect(within(breakdown).getByRole("heading")).toHaveTextContent(
      label("Review a category spending increase"),
    );
    expect(screen.getAllByText(`${digits("75.00")}%`)).toHaveLength(2);
    expect(screen.getAllByText(`${digits("0.00")}%`)).toHaveLength(2);
    expect(
      screen.getByText(
        label(
          "Observed changes do not prove that coaching caused them. Acting on a recommendation is self-reported.",
        ),
      ),
    ).toBeVisible();
    await userEvent.click(
      screen.getByText(label("Assumptions & data limitations")),
    );
    expect(
      screen.getByText(
        label("Outcomes are observational and do not establish causation."),
      ),
    ).toBeVisible();
  },
);
it("distinguishes null and missing percentages from a genuine zero", async () => {
  vi.spyOn(api, "coachingEffectiveness").mockResolvedValue({
    ...fixture,
    by_type: [],
    rates: {
      observable_outcome_rate: null,
      worsening_rate_among_observed: "0.00",
    },
  });
  render(<CoachingEffectiveness />);
  expect(await screen.findAllByText("Not enough data")).toHaveLength(2);
  expect(screen.getByText("0.00%")).toBeVisible();
  expect(
    screen.getByText("No recommendation-type breakdown yet."),
  ).toBeVisible();
  expect(screen.queryByText(/NaN|Infinity/)).not.toBeInTheDocument();
});
it.each(["en", "bn"] as const)(
  "renders an honest empty state in %s",
  async (language) => {
    setLanguage(language);
    vi.spyOn(api, "coachingEffectiveness").mockResolvedValue(
      emptyEffectiveness,
    );
    render(<CoachingEffectiveness />);
    const key = "No coaching feedback yet.";
    expect(
      await screen.findByText(language === "en" ? key : bn[key]),
    ).toBeVisible();
    expect(
      document.querySelectorAll(".effectiveness-counts, .effectiveness-rates"),
    ).toHaveLength(0);
  },
);
it.each(["en", "bn"] as const)(
  "announces loading and localized error with keyboard retry in %s",
  async (language) => {
    setLanguage(language);
    const request = vi
      .spyOn(api, "coachingEffectiveness")
      .mockRejectedValueOnce(new Error("Unavailable"))
      .mockResolvedValueOnce(fixture);
    render(<CoachingEffectiveness />);
    const label = (key: keyof typeof bn) => (language === "en" ? key : bn[key]);
    expect(screen.getByRole("status")).toHaveTextContent(
      label("Reading coaching effectiveness..."),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      label("Could not load coaching effectiveness. Please try again."),
    );
    expect(document.querySelector(".effectiveness-counts")).toBeNull();
    const retry = screen.getByRole("button", { name: label("Try again") });
    retry.focus();
    await userEvent.keyboard("{Enter}");
    await screen.findAllByText(label("Recommendations with feedback"));
    expect(request).toHaveBeenCalledTimes(2);
  },
);
it("refreshes on feedback revision, but not on a language change", async () => {
  const request = vi
    .spyOn(api, "coachingEffectiveness")
    .mockResolvedValue(fixture);
  const view = render(<CoachingEffectiveness revision={0} />);
  await screen.findAllByText("Recommendations with feedback");
  act(() => setLanguage("bn"));
  expect(
    screen.getByRole("heading", { name: bn["Coaching effectiveness"] }),
  ).toBeVisible();
  expect(request).toHaveBeenCalledTimes(1);
  view.rerender(<CoachingEffectiveness revision={1} />);
  await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
});
it("uses the authenticated GET endpoint without a user ID or another outcome request", async () => {
  setSession({ access_token: "test-token", token_type: "bearer" });
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify(fixture), { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  await api.coachingEffectiveness();
  expect(fetcher).toHaveBeenCalledTimes(1);
  const [url, init] = fetcher.mock.calls[0];
  expect(url).toBe("/api/finance/coaching/effectiveness");
  expect(new Headers(init.headers).get("Authorization")).toBe(
    "Bearer test-token",
  );
  expect(init.body).toBeUndefined();
});

it.each(["en", "bn"] as const)(
  "checks distinct type counts and improvement rates independently in %s",
  async (language) => {
    setLanguage(language);
    const distinct = {
      ...fixture,
      counts: {
        total_recommendations: 9,
        acted_on: 6,
        dismissed: 1,
        not_relevant: 1,
        snoozed: 1,
        measurable_outcomes: 4,
        improved: 2,
        unchanged: 1,
        worsened: 1,
        insufficient_data: 1,
      },
      rates: {
        observable_outcome_rate: "66.67",
        improvement_rate_among_observed: "50.00",
        worsening_rate_among_observed: "25.00",
      },
      by_type: [
        {
          recommendation_type: "spending_spike" as const,
          total_recommendations: 5,
          acted_on: 4,
          measurable_outcomes: 3,
          improved: 2,
          unchanged: 0,
          worsened: 1,
          insufficient_data: 1,
          observable_outcome_rate: "75.00",
          improvement_rate_among_observed: "66.67",
          worsening_rate_among_observed: "33.33",
        },
        {
          recommendation_type: "cash_risk" as const,
          total_recommendations: 4,
          acted_on: 2,
          measurable_outcomes: 1,
          improved: 0,
          unchanged: 1,
          worsened: 0,
          insufficient_data: 0,
          observable_outcome_rate: "50.00",
          improvement_rate_among_observed: "0.00",
          worsening_rate_among_observed: "0.00",
        },
      ],
    };
    vi.spyOn(api, "coachingEffectiveness").mockResolvedValue(distinct);
    render(<CoachingEffectiveness />);
    const label = (key: keyof typeof bn) => (language === "en" ? key : bn[key]);
    const list = await screen.findByRole("list", {
      name: label("By recommendation type"),
    });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    const cases = [
      {
        title: "Review a category spending increase" as const,
        counts: [5, 4, 3, 2, 0, 1, 1],
        rates: ["75.00", "66.67", "33.33"],
      },
      {
        title: "Prepare for a possible cash shortfall" as const,
        counts: [4, 2, 1, 0, 1, 0, 0],
        rates: ["50.00", "0.00", "0.00"],
      },
    ];
    for (const expected of cases) {
      const row = within(list)
        .getByRole("heading", { name: label(expected.title) })
        .closest("li")!;
      const keys = [
        "Recommendations with feedback",
        "Reported acted on",
        "Measurable outcomes",
        "Improved",
        "Unchanged",
        "Worsened",
        "Insufficient-data outcomes",
      ] as const;
      keys.forEach((key, i) =>
        expect(
          within(row).getByText(label(key)).nextElementSibling,
        ).toHaveTextContent(new RegExp(`^${digits(expected.counts[i])}$`)),
      );
      const rates = [
        "Observable outcome rate",
        "Improvement rate among observed",
        "Worsening rate among observed",
      ] as const;
      rates.forEach((key, i) =>
        expect(
          within(row).getByText(label(key)).nextElementSibling?.textContent,
        ).toBe(`${digits(expected.rates[i])}%`),
      );
    }
  },
);

it("keeps the observational disclaimer and limitations when causal_claim is omitted", async () => {
  const withoutFlag = { ...fixture };
  delete withoutFlag.causal_claim;
  vi.spyOn(api, "coachingEffectiveness").mockResolvedValue(withoutFlag);
  render(<CoachingEffectiveness />);
  expect(
    await screen.findByText(
      "Observed changes do not prove that coaching caused them. Acting on a recommendation is self-reported.",
    ),
  ).toBeVisible();
  await userEvent.click(screen.getByText("Assumptions & data limitations"));
  for (const limitation of fixture.limitations) {
    expect(screen.getByText(limitation)).toBeVisible();
  }
});
