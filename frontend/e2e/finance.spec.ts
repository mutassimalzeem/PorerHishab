import { test, expect } from "@playwright/test";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
// Synthetic test-only contracts. Never bundled into the application or persisted to the API.
const sample = {
  id: 1,
  date: "2026-10-20",
  description: "Weekly groceries",
  merchant: "Local shop",
  amount: "-1500.00",
  category: "Groceries",
  fee: "0.00",
  balance: null,
  source: "manual",
  category_reason: "User supplied category",
};
const coverage = {
  start_date: "2026-07-01",
  end_date: "2026-09-30",
  transaction_count: 0,
  first_transaction_date: null,
  last_transaction_date: null,
  limitations: ["History is incomplete."],
};
async function connect(page: import("@playwright/test").Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname.replace("/api", "");
    let body: unknown = {};
    if (path === "/login") body = { access_token: "test-only-token" };
    else if (path === "/me")
      body = { id: 1, email: "test@example.com", full_name: "Test User" };
    else if (path === "/insights/summary")
      body = {
        transaction_count: 1,
        total_income: "0.00",
        total_expenses: "-1500.00",
        net: "-1500.00",
        savings_rate: null,
      };
    else if (path === "/transactions")
      body = { items: [sample], total: 1, limit: 20, offset: 0 };
    else if (path === "/finance/scheduled-cashflow")
      body = { items: [], total: 0, limit: 20, offset: 0 };
    else if (path === "/finance/goals")
      body = { items: [], total: 0, limit: 20, offset: 0 };
    else if (path === "/insights/proactive")
      body = {
        as_of_date: "2026-10-25",
        insights: [],
        limitations: ["History is incomplete."],
      };
    else if (path === "/finance/savings/recommendations")
      body = {
        coverage,
        recommendations: [],
        limitations: ["Three complete months are required."],
      };
    else if (path === "/chat/ask")
      body = {
        answer: "Recorded history is too short to estimate savings reliably.",
        intent: "savings",
        sources: [],
        calculation: { estimated_savings: null },
        coverage,
        date_range: null,
        assumptions: [],
        limitations: ["Three complete months are required."],
        status: "insufficient_data",
      };
    else if (path === "/finance/coach/cashflow")
      body = {
        as_of_date: "2026-10-25",
        starting_balance: "10000.00",
        months: [
          {
            month: "2026-10",
            historical_income_estimate: null,
            historical_expense_estimate: null,
            scheduled_expenses: "1500.00",
            uncertain_scheduled_income: "0.00",
            reserved_expenses: "1500.00",
            projected_balance: null,
            balance_without_future_income: "8500.00",
          },
        ],
        coverage,
        assumptions: ["Future income is uncertain."],
        limitations: ["Three complete months are required."],
      };
    else
      return route.fulfill({
        status: 404,
        json: { detail: "No test fixture for this endpoint" },
      });
    await route.fulfill({ status: 200, json: body });
  });
  await page.goto("/");
  await page.getByLabel("Email address").fill("test@example.com");
  await page.getByLabel("Password", { exact: true }).fill("test-only-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "A clearer picture, Test." }),
  ).toBeVisible();
}
async function navigate(page: import("@playwright/test").Page, name: string) {
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name, exact: true })
    .click();
}
async function noOverflow(page: import("@playwright/test").Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
}
async function accessible(page: import("@playwright/test").Page) {
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  const violations = await page.evaluate(
    "axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}}).then(r=>r.violations.map(v=>({id:v.id,help:v.help,nodes:v.nodes.map(n=>n.target)})))",
  );
  expect(violations).toEqual([]);
  await page.locator("#main").focus();
}
test("overview, navigation and transaction ledger remain usable", async ({
  page,
}, info) => {
  await connect(page);
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("overview.png"),
    fullPage: true,
  });
  await navigate(page, "Transactions");
  await expect(
    page.getByRole("heading", { name: "Every transaction, in context." }),
  ).toBeVisible();
  await noOverflow(page);
  await page.getByRole("button", { name: "Local shop" }).click();
  await page.getByLabel("Correct category").fill("Food");
  await expect(
    page.getByRole("button", { name: "Save category" }),
  ).toBeVisible();
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("transactions.png"),
    fullPage: true,
  });
});
test("cashflow requires a supplied balance and labels missing projections", async ({
  page,
}, info) => {
  await connect(page);
  await navigate(page, "Cashflow");
  await page
    .getByLabel("Starting balance (BDT)", { exact: true })
    .fill("10000.00");
  await page.getByRole("button", { name: "Build outlook" }).click();
  await expect(
    page.getByText(
      "Recorded history is insufficient for a reliable projection.",
      { exact: false },
    ),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "Not available" })).toBeVisible();
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("cashflow.png"),
    fullPage: true,
  });
});
test("plans, insights, Ask and settings explain limitations", async ({
  page,
}, info) => {
  await connect(page);
  await navigate(page, "Plans");
  await expect(
    page.getByRole("heading", { name: "What are you saving for?" }),
  ).toBeVisible();
  await navigate(page, "Insights");
  await expect(
    page.getByRole("heading", { name: "A little more history first" }),
  ).toBeVisible();
  await navigate(page, "Ask PorerHishab");
  await page
    .getByRole("button", { name: "How much can I save this month?" })
    .click();
  await page
    .getByRole("button", { name: "Ask PorerHishab", exact: true })
    .click();
  await expect(
    page.getByText("insufficient data", { exact: true }),
  ).toBeVisible();
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({ path: info.outputPath("ask.png"), fullPage: true });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your account & preferences." }),
  ).toBeVisible();
  await noOverflow(page);
});
