import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Scenarios } from "../pages/Scenarios";
import { setLanguage } from "../lib/locale";
import { scenarioFixture, scenarioResultFixture } from "./scenarios.fixture";
let posts: string[];
beforeEach(() => {
  posts = [];
  setLanguage("en");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).split("?")[0];
      if (init?.method === "POST") posts.push(path);
      const body =
        path.endsWith("/baseline") ||
        path.endsWith("/result") ||
        path.endsWith("/simulate")
          ? scenarioResultFixture
          : path.endsWith("/scenarios") && !init?.method
            ? { items: [scenarioFixture], total: 1, limit: 12, offset: 0 }
            : path.endsWith("/archive")
              ? { ...scenarioFixture, status: "archived" }
              : scenarioFixture;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  setLanguage("en");
});
it("creates, edits, runs, saves, and archives without client arithmetic", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <Scenarios />
    </MemoryRouter>,
  );
  await screen.findByRole("table");
  await user.type(screen.getByLabelText("Name"), "Rent test");
  await user.click(screen.getByRole("button", { name: "Create scenario" }));
  await screen.findByRole("heading", { name: /WHAT IF.*Rent test/ });
  await user.type(screen.getByLabelText("Amount (BDT)"), "2000");
  await user.click(screen.getByRole("button", { name: "Add change" }));
  await user.click(screen.getByRole("button", { name: "Run scenario" }));
  await screen.findByText(
    "This is a scenario based on the assumptions you selected, not a guaranteed future outcome.",
  );
  expect(screen.getByText(/2000.00 \(increased\)/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Save scenario" }));
  await user.click(screen.getByRole("button", { name: "Archive scenario" }));
  expect(screen.getByRole("button", { name: "Run scenario" })).toBeDisabled();
  expect(posts).toContain("/api/finance/scenarios/1/changes");
});
it("renders Bengali labels and unknown data", async () => {
  setLanguage("bn");
  render(
    <MemoryRouter>
      <Scenarios />
    </MemoryRouter>,
  );
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "\u09af\u09a6\u09bf",
  );
  await screen.findByRole("table");
});
it("shows failures and retry", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(
    <MemoryRouter>
      <Scenarios />
    </MemoryRouter>,
  );
  expect((await screen.findAllByRole("alert")).length).toBeGreaterThan(0);
  expect(
    screen.getAllByRole("button", { name: "Try again" }).length,
  ).toBeGreaterThan(0);
});
