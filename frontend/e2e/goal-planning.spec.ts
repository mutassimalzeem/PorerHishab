import { test, expect } from "@playwright/test";
import {
  planningGoalFixture,
  planningOverviewFixture,
  challengingPlanFixture,
  revisedPlanFixture,
  contributedPlanFixture,
  contributionFixture,
} from "../src/test/goal-planning.fixture";
import { bn } from "../src/lib/translations";

test("authenticated goal planning: alternatives, milestones, progress, revisions and Bengali", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  let goal = structuredClone(planningGoalFixture);
  let current: typeof revisedPlanFixture | null = null;
  const history: (typeof revisedPlanFixture)[] = [];
  let contributions = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api", "");
    const method = route.request().method();
    let body: unknown = {};
    if (path === "/login") body = { access_token: "test-only-planner-token" };
    else if (path === "/me")
      body = { id: 1, email: "planner@example.com", full_name: "Planner User" };
    else if (path.includes("unread-count")) body = { unread_count: 0 };
    else if (path === "/finance/goals")
      body = { items: [goal], total: 1, limit: 20, offset: 0 };
    else if (path === "/finance/goals/planning/overview")
      body = planningOverviewFixture;
    else if (path === `/finance/goals/${goal.id}/plans`) body = history;
    else if (path === `/finance/goals/${goal.id}/plans/current`) body = current;
    else if (path === `/finance/goals/${goal.id}/events`)
      body = contributions
        ? [
            {
              id: 1,
              goal_id: goal.id,
              kind: "contribution_recorded",
              created_at: "2026-11-01T00:00:00Z",
              details: { amount: "15000" },
            },
          ]
        : [];
    else if (path === `/finance/goals/${goal.id}/plan` && method === "POST") {
      current = challengingPlanFixture;
      history.push(current);
      body = current;
    } else if (path === `/finance/goals/${goal.id}/replan`) {
      // Model a real asynchronous save so assertions cannot rely on the old plan.
      await new Promise((resolve) => setTimeout(resolve, 250));
      current = revisedPlanFixture;
      goal = { ...goal, target_date: current.target_date };
      if (history.length < 2) history.push(current);
      body = current;
    } else if (path === `/finance/goals/${goal.id}/contributions`) {
      contributions++;
      goal = { ...goal, current_saved: "15000" };
      current = contributedPlanFixture;
      body = contributionFixture;
    } else if (path === `/finance/goals/${goal.id}`) {
      if (method === "PATCH")
        goal = { ...goal, ...route.request().postDataJSON() };
      body = goal;
    }
    await route.fulfill({ json: body });
  });
  await page.goto("/plans");
  await expect(
    page.getByRole("button", { name: "Plan milestones" }),
  ).toHaveCount(0);
  await page.getByLabel("Email address").fill("planner@example.com");
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("button", { name: "Plan milestones", exact: true })
    .click();
  const workspace = page.getByRole("region", {
    name: "Personalized goal planning",
  });
  await expect(
    workspace.getByText(
      "No personalized plan yet. Review your inputs before creating one.",
    ),
  ).toBeVisible();
  await workspace.getByRole("checkbox").check();
  await workspace
    .getByRole("button", { name: "Create personalized plan", exact: true })
    .click();
  await expect(
    workspace.getByRole("heading", { name: "Goal feasibility", exact: true }),
  ).toBeVisible();
  await workspace
    .getByRole("button", { name: "Accept this alternative", exact: true })
    .first()
    .click();
  await expect(
    workspace
      .getByText(
        "The required contribution fits the conservative capacity after existing commitments.",
        { exact: true },
      )
      .first(),
  ).toBeVisible();
  await expect(
    workspace.getByRole("heading", { name: "Goal milestones", exact: true }),
  ).toBeVisible();
  // The feasibility text also occurs in the old alternative/overview, and the
  // milestones heading exists even when empty. Wait for the refreshed plan itself.
  await expect(
    workspace.getByLabel("Revised target date (optional)"),
  ).toHaveValue(revisedPlanFixture.target_date ?? "");
  const contribution = workspace.getByLabel("Reported contribution (BDT)");
  await expect(contribution).toBeEnabled();
  await contribution.fill("15000");
  await expect(contribution).toHaveValue("15000");
  await workspace
    .getByRole("button", { name: "Record contribution", exact: true })
    .click();
  await expect.poll(() => contributions).toBe(1);
  await expect(
    page.getByRole("progressbar", { name: "Laptop progress" }),
  ).toHaveAttribute("value", "15");
  await expect(
    workspace.getByText("reported completed", { exact: false }).first(),
  ).toBeVisible();
  await workspace.getByText("Plan revision history", { exact: true }).click();
  await expect(
    workspace
      .getByText("Plan revision history")
      .locator("..")
      .getByRole("listitem"),
  ).toHaveCount(2);
  await workspace
    .getByRole("button", { name: "Recalculate goal plan", exact: true })
    .click();
  await workspace
    .getByRole("button", { name: "Pause goal", exact: true })
    .click();
  await expect(
    workspace.getByRole("button", { name: "Resume goal", exact: true }),
  ).toBeVisible();
  await workspace
    .getByRole("button", { name: "Resume goal", exact: true })
    .click();
  await page.evaluate(() => localStorage.setItem("porerhishab.language", "bn"));
  await page.reload();
  await page.getByLabel(bn["Email address"]).fill("planner@example.com");
  await page.getByLabel(bn.Password, { exact: true }).fill("test-password");
  await page.getByRole("button", { name: bn["Sign in"], exact: true }).click();
  await page
    .getByRole("button", { name: bn["Plan milestones"], exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: bn["Goal feasibility"], exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: bn["Goal milestones"], exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: bn["Overall goal commitments"],
      exact: true,
    }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
