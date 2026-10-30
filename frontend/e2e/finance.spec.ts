import { bn } from "../src/lib/translations";
import { timelineFixture } from "../src/test/timeline.fixture";
import { unknownRunway, populatedRunway } from "../src/test/runway.fixture";
import { test, expect } from "@playwright/test";
import {
  emptyIntelligence,
  richIntelligence,
} from "../src/test/intelligence.fixture";
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
async function connect(page: import("@playwright/test").Page, rich = false) {
  const intelligence = rich ? richIntelligence : emptyIntelligence;
  let goals = intelligence.snapshot.goals.map((g) => ({
    id: g.goal_id,
    name: g.name,
    description: null,
    target_amount: g.target_amount,
    current_saved: g.current_saved,
    target_date: g.target_date,
    status: g.status,
  }));
  let schedules = intelligence.snapshot.scheduled_obligations.items.map(
    (i) => ({
      id: i.scheduled_item_id,
      title: i.title,
      kind: i.kind,
      amount: i.amount,
      due_date: i.due_date,
      status: "scheduled",
      category: null,
      notes: null,
    }),
  );

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname.replace("/api", "");
    let body: unknown = {};
    if (path === "/login") body = { access_token: "test-only-token" };
    else if (path === "/me")
      body = { id: 1, email: "test@example.com", full_name: "Test User" };
    else if (path === "/finance/intelligence") body = intelligence;
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
    else if (path === "/finance/scheduled-cashflow") {
      if (route.request().method() === "POST") {
        const item = route.request().postDataJSON();
        schedules.push({
          ...item,
          id: schedules.length + 1,
          status: "scheduled",
          category: null,
          notes: null,
        });
        body = schedules.at(-1);
      } else
        body = {
          items: schedules,
          total: schedules.length,
          limit: 20,
          offset: 0,
        };
    } else if (path.startsWith("/finance/scheduled-cashflow/")) {
      const id = Number(path.split("/").at(-1));
      schedules = schedules.map((item) =>
        item.id === id ? { ...item, ...route.request().postDataJSON() } : item,
      );
      body = schedules.find((item) => item.id === id);
    } else if (path === "/finance/goals") {
      if (route.request().method() === "POST") {
        const item = route.request().postDataJSON();
        goals.push({
          ...item,
          id: goals.length + 1,
          status: "active",
          description: null,
        });
        body = goals.at(-1);
      } else body = { items: goals, total: goals.length, limit: 20, offset: 0 };
    } else if (path.endsWith("/plan") && path.startsWith("/finance/goals/"))
      body = {
        goal_id: Number(path.split("/")[3]),
        as_of_date: "2026-10-25",
        remaining_amount: "45000.00",
        required_weekly: "1285.72",
        required_monthly: "5625.00",
        estimated_monthly_capacity: "23000.00",
        affordability: "appears_feasible",
        assumptions: ["Reported savings are not account allocations."],
        limitations: ["Future contributions are not guaranteed."],
      };
    else if (path.startsWith("/finance/goals/")) {
      const id = Number(path.split("/").at(-1));
      goals = goals.map((goal) =>
        goal.id === id ? { ...goal, ...route.request().postDataJSON() } : goal,
      );
      body = goals.find((goal) => goal.id === id);
    } else if (path === "/insights/proactive")
      body = {
        as_of_date: "2026-10-25",
        insights: [],
        limitations: ["History is incomplete."],
      };
    else if (path === "/finance/savings/recommendations")
      body = {
        coverage,
        recommendations: [],
        limitations: [
          "Three complete calendar months with observed records are required; missing months are unknown.",
        ],
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
  if (
    (await page.getByRole("dialog").count()) === 0 &&
    (await page.locator("#main").count())
  )
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

test("populated intelligence, goal editing and modal keyboard behavior", async ({
  page,
}, info) => {
  await connect(page, true);
  await expect(
    page.getByText("Three complete months contain records"),
  ).toBeVisible();
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("overview-populated.png"),
    fullPage: true,
  });
  await navigate(page, "Insights");
  await expect(
    page.getByRole("heading", { name: "Which categories changed?" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Internet service" }),
  ).toBeVisible();
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("insights-populated.png"),
    fullPage: true,
  });
  await navigate(page, "Plans");
  await page.getByRole("button", { name: "Edit Emergency buffer" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit savings goal" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Goal name")).toBeFocused();
  await dialog.getByLabel("Goal name").fill("Emergency reserve");
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("goal-editor.png"),
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "Save goal changes" }).click();
  await expect(
    page.getByRole("heading", { name: "Emergency reserve" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Weekly" }).click();
  await expect(page.getByRole("button", { name: "Weekly" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await navigate(page, "Cashflow");
  await page.getByRole("button", { name: "Edit", exact: true }).first().click();
  const schedule = page.getByRole("dialog", { name: "Edit scheduled item" });
  await schedule.getByLabel("What is it for?").fill("Updated rent");
  await schedule.getByRole("button", { name: "Save scheduled item" }).click();
  await expect(page.getByText("Updated rent", { exact: true })).toBeVisible();
  await navigate(page, "Transactions");
  await page
    .getByRole("button", { name: "Add transaction", exact: true })
    .click();
  const transaction = page.getByRole("dialog", {
    name: "Record a transaction",
  });
  await expect(transaction).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(transaction).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Add transaction", exact: true }),
  ).toBeFocused();
});

test("mobile navigation contains focus and returns it on Escape", async ({
  page,
}) => {
  await connect(page);
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (!(await toggle.isVisible())) return;
  await toggle.click();
  const dialog = page.getByRole("dialog", { name: "Your workspace" });
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 16; i++) await page.keyboard.press("Tab");
  expect(
    await dialog.evaluate((el) => el.contains(document.activeElement)),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(toggle).toBeFocused();
  await page
    .getByRole("navigation", { name: "Quick navigation" })
    .getByRole("link", { name: "Ask", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "A question worth asking." }),
  ).toBeVisible();
});

async function navigatePath(
  page: import("@playwright/test").Page,
  path: string,
) {
  const toggle = page.locator("#nav-toggle");
  if (await toggle.isVisible()) {
    await toggle.click();
    await page
      .getByRole("dialog")
      .locator('a[href="' + path + '"]')
      .first()
      .click();
  } else
    await page
      .locator('.sidebar a[href="' + path + '"]')
      .first()
      .click();
  await expect(page.locator("#main h1")).toBeVisible();
}
for (const width of [360, 390, 768, 1024, 1440]) {
  test(
    "Khata English/Bengali routes at " + width + "px",
    async ({ page }, info) => {
      test.skip(
        info.project.name === "mobile",
        "The width matrix runs once using the desktop browser; mobile touch flows have separate coverage.",
      );
      test.setTimeout(90000);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await connect(page, true);
      for (const language of ["en", "bn"]) {
        await page.locator('.topbar button[lang="' + language + '"]').click();
        await expect(page.locator("html")).toHaveAttribute("lang", language);
        for (const path of [
          "/",
          "/transactions",
          "/cashflow",
          "/plans",
          "/insights",
          "/ask",
          "/settings",
        ]) {
          await navigatePath(page, path);
          await noOverflow(page);
          await accessible(page);
          if (path === "/" && [390, 1440].includes(width))
            await page.screenshot({
              path: info.outputPath("khata-" + language + "-" + width + ".png"),
              fullPage: true,
            });
        }
      }
      expect(errors).toEqual([]);
    },
  );
}
test("language switching retains an open schedule draft, sends canonical decimal payloads, and survives reload", async ({
  page,
}, info) => {
  await connect(page);
  await navigatePath(page, "/cashflow");
  await page
    .getByRole("button", { name: "Schedule an item", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.locator('input[name="title"]').fill("Original user record");
  await dialog.locator('input[name="amount"]').fill("1234.50");
  await dialog.locator('input[name="due_date"]').fill("2026-11-15");
  await dialog.locator('button[lang="bn"]').click();
  await expect(dialog.locator('input[name="title"]')).toHaveValue(
    "Original user record",
  );
  await expect(dialog.locator('input[name="amount"]')).toHaveValue("1234.50");
  await expect(dialog).toBeVisible();
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("khata-bn-schedule-editor.png"),
    fullPage: true,
  });
  const sent = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().endsWith("/finance/scheduled-cashflow"),
  );
  await dialog.locator('button[type="submit"], form button.primary').click();
  expect((await sent).postDataJSON()).toEqual({
    title: "Original user record",
    kind: "expense",
    amount: "1234.50",
    due_date: "2026-11-15",
  });
  await expect(dialog).not.toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "bn");
  await expect(page.locator('input[name="email"]')).toBeVisible();
  await expect(page.locator('.auth button[lang="bn"]')).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await noOverflow(page);
  await accessible(page);
});
test("authentication language switching preserves input and localizes validation", async ({
  page,
}, info) => {
  await page.goto("/login");
  await page.locator('input[name="email"]').fill("draft@example.com");
  await page.locator('input[name="password"]').fill("draft-password");
  await page.locator('.auth button[lang="bn"]').click();
  await expect(page.locator('input[name="email"]')).toHaveValue(
    "draft@example.com",
  );
  await expect(page.locator('input[name="password"]')).toHaveValue(
    "draft-password",
  );
  await page.locator('input[name="email"]').fill("");
  await page.locator("form button").click();
  expect(
    await page
      .locator('input[name="email"]')
      .evaluate((node: HTMLInputElement) => node.validationMessage),
  ).toMatch(/[\u0980-\u09ff]/);
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("khata-bn-auth.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "bn");
});

test("review and explicitly confirm or remove obligation allocations", async ({
  page,
}, info) => {
  await connect(page, true);
  let allocated = false;
  await page.route(
    "**/api/finance/scheduled-cashflow/1/matches**",
    async (route) => {
      const request = route.request();
      if (request.method() === "POST") {
        expect(request.postDataJSON()).toEqual({
          confirm_full_settlement: false,
        });
        allocated = true;
      }
      if (request.method() === "DELETE") allocated = false;
      await route.fulfill({
        json: {
          item_id: 1,
          original_amount: "12000.00",
          allocated_amount: allocated ? "4000.00" : "0.00",
          remaining_amount: allocated ? "8000.00" : "12000.00",
          status: allocated ? "partial" : "review_required",
          timing: "not_due",
          ambiguous: false,
          date_tolerance_days: 7,
          amount_tolerance: "0.00",
          limitations: [],
          allocations: allocated
            ? [
                {
                  id: 1,
                  transaction_id: 9,
                  amount: "4000.00",
                  active: true,
                  confirmed_at: "2026-10-30T00:00:00Z",
                  revoked_at: null,
                },
              ]
            : [],
          candidates: allocated
            ? []
            : [
                {
                  transaction_id: 9,
                  date: "2026-11-01",
                  amount: "4000.00",
                  description: "Rent installment",
                  merchant: null,
                  category: "Housing",
                  amount_difference: "8000.00",
                  date_distance_days: 0,
                  amount_signal: "partial",
                  category_match: true,
                  text_overlap: true,
                  confidence: "low",
                  limitations: [],
                },
              ],
        },
      });
    },
  );
  await navigate(page, "Cashflow");
  await page
    .getByRole("button", { name: "Review transaction matches" })
    .first()
    .click();
  await expect(
    page.getByText("Rent installment", { exact: false }),
  ).toBeVisible();
  expect(allocated).toBe(false);
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: info.outputPath("obligation-matches.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Confirm allocation", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Allocation updated." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Review transaction matches" })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Remove allocation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Remove allocation" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Allocation updated." }),
  ).toBeVisible();
  expect(allocated).toBe(false);
});

test("account runway preserves unknown cash and renders an updated projection", async ({
  page,
}) => {
  await connect(page);
  let populated = false;
  await page.route("**/api/finance/runway", async (route) => {
    await route.fulfill({ json: populated ? populatedRunway : unknownRunway });
  });
  await navigate(page, "Cashflow");
  await page.getByRole("button", { name: "Check account runway" }).click();
  await expect(
    page.getByText("insufficient data", { exact: true }),
  ).toBeVisible();
  const summary = page.locator(".runway-summary");
  await expect(summary.getByText("Not available")).toHaveCount(3);
  populated = true;
  await page.getByRole("button", { name: "Refresh account runway" }).click();
  await expect(page.getByText("positive", { exact: true })).toBeVisible();
  await expect(summary.getByText("Not available")).toHaveCount(0);
  await accessible(page);
  await expect(
    page.getByText(
      "Monthly estimates cannot establish an exact depletion day.",
    ),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("financial timeline separates cash scopes and supports bilingual accessible mobile reading", async ({
  page,
}) => {
  await connect(page);
  await page.route("**/api/finance/timeline", async (route) => {
    await route.fulfill({ json: timelineFixture });
  });
  await navigate(page, "Cashflow");
  await page.getByRole("button", { name: "Load timeline" }).click();
  const list = page.getByRole("list", {
    name: "Financial timeline",
    exact: true,
  });
  await expect(list.getByRole("listitem")).toHaveCount(7);
  await expect(list.getByText("Groceries", { exact: true })).toBeVisible();
  await expect(list.getByText("Uncertain", { exact: true })).toBeVisible();
  await expect(list.getByText("Confirmed", { exact: true })).toBeVisible();
  await accessible(page);
  await noOverflow(page);
  await page.locator('.topbar button[lang="bn"]').click();
  const bengaliList = page.getByRole("list", {
    name: bn["Financial timeline"],
    exact: true,
  });
  await expect(bengaliList.getByRole("listitem")).toHaveCount(7);
  await expect(
    bengaliList.getByText(bn.Uncertain, { exact: true }),
  ).toBeVisible();
  await expect(
    bengaliList.getByText("Groceries", { exact: true }),
  ).toBeVisible();
  // Audit settled colors rather than the language buttons' 140ms crossfade.
  await page.locator(".topbar .language-switcher").evaluate(async (element) => {
    element.getBoundingClientRect();
    await Promise.all(
      element
        .getAnimations({ subtree: true })
        .map((animation) => animation.finished.catch(() => {})),
    );
  });
  await accessible(page);
  await noOverflow(page);
});
