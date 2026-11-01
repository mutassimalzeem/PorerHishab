import { test, expect } from "@playwright/test";
import {
  healthFixture,
  emptyHealth,
} from "../src/test/financial-health.fixture";
import { bn } from "../src/lib/translations";
for (const empty of [false, true])
  test(`financial health authenticated bilingual experience (${empty ? "empty" : "recorded"})`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    let evaluations = 0;
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname.replace("/api", "");
      let body: unknown = {};
      if (path === "/login") body = { access_token: "health-test-token" };
      else if (path === "/me")
        body = { id: 1, email: "health@example.com", full_name: "Health User" };
      else if (path.includes("unread-count")) body = { unread_count: 0 };
      else if (path === "/finance/health/evaluate") {
        evaluations++;
        body = empty ? emptyHealth : healthFixture;
      } else if (path === "/finance/health/history")
        body = empty ? [] : [healthFixture];
      else if (path === "/finance/health/trend") body = healthFixture.trend;
      else if (path === "/finance/health")
        body = empty ? emptyHealth : healthFixture;
      await route.fulfill({ json: body });
    });
    await page.goto("/health");
    await expect(page.getByLabel("Email address")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Current financial profile" }),
    ).toHaveCount(0);
    await page.getByLabel("Email address").fill("health@example.com");
    await page.getByLabel("Password", { exact: true }).fill("test-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Financial Health", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Current financial profile" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "liquidity", exact: true }),
    ).toBeVisible();
    await page.getByText("Health evidence", { exact: true }).first().click();
    await expect(
      page.getByRole("heading", { name: "Health trend" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Health history" }),
    ).toBeVisible();
    if (empty)
      await expect(page.getByText("No health snapshots yet")).toBeVisible();
    else await expect(page.getByRole("table")).toBeVisible();
    await page
      .getByRole("button", { name: "Evaluate financial health", exact: true })
      .click();
    await expect.poll(() => evaluations).toBe(1);
    await page.evaluate(() => {
      localStorage.setItem("porerhishab.language", "bn");
    });
    await page.reload();
    await page.getByLabel(bn["Email address"]).fill("health@example.com");
    await page.getByLabel(bn.Password, { exact: true }).fill("test-password");
    await page
      .getByRole("button", { name: bn["Sign in"], exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: bn["Financial Health"], exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: bn.liquidity, exact: true }),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
