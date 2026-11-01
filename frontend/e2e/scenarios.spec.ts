import { test, expect } from "@playwright/test";
import {
  scenarioFixture,
  scenarioResultFixture,
} from "../src/test/scenarios.fixture";
test("scenario workspace isolates hypothetical changes and supports save/archive", async ({
  page,
}) => {
  let scenario = structuredClone(scenarioFixture);
  let created = false;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api", "");
    const method = route.request().method();
    let body: unknown = {};
    if (path === "/login") body = { access_token: "test-scenario-token" };
    else if (path === "/me")
      body = {
        id: 1,
        email: "scenario@example.com",
        full_name: "Scenario User",
      };
    else if (path.includes("unread-count")) body = { unread_count: 0 };
    else if (path.endsWith("/baseline") || path.endsWith("/simulate"))
      body = { ...scenarioResultFixture, assumptions: scenario.changes };
    else if (path === "/finance/scenarios") {
      if (method === "POST") created = true;
      body = method === "POST" ? scenario : created ? [scenario] : [];
    } else if (path.endsWith("/changes")) {
      scenario = {
        ...scenario,
        changes: route.request().postDataJSON().changes,
        revision: 2,
      };
      body = scenario;
    } else if (path.endsWith("/save")) {
      scenario.status = "saved";
      body = scenario;
    } else if (path.endsWith("/archive")) {
      scenario.status = "archived";
      body = scenario;
    } else if (path === "/finance/scenarios/1") body = scenario;
    await route.fulfill({ json: body });
  });
  await page.goto("/scenarios");
  await page.getByLabel("Email address").fill("scenario@example.com");
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "YOUR CURRENT FINANCES" }),
  ).toBeVisible();
  await page.getByLabel("Name", { exact: true }).fill("Rent test");
  await page
    .getByRole("button", { name: "Create scenario", exact: true })
    .click();
  await page.getByLabel("Amount (BDT)").fill("2000");
  await page.getByRole("button", { name: "Add change", exact: true }).click();
  await page.getByRole("button", { name: "Run scenario", exact: true }).click();
  await expect(page.getByText(/2000.00 \(increased\)/)).toBeVisible();
  await page
    .getByRole("button", { name: "Save scenario", exact: true })
    .click();
  await expect(page.getByLabel("Choose scenario")).toContainText("saved");
  await page
    .getByRole("button", { name: "Archive scenario", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Run scenario", exact: true }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
