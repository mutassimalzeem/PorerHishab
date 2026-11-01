import { test, expect } from "@playwright/test";
import {
  libraryScenarios,
  comparisonFixture,
} from "../src/test/scenario-library.fixture";
import { scenarioResultFixture } from "../src/test/scenarios.fixture";
import { bn } from "../src/lib/translations";

test("library lifecycle, keyboard rename, archived restore and bilingual comparison", async ({
  page,
}) => {
  const records = structuredClone(libraryScenarios.slice(0, 2));
  let simulations = 0;
  const originalChanges = JSON.stringify(records[0].changes);
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname.replace("/api", "");
    let body: unknown = {};
    if (path === "/login")
      body = { access_token: "scenario-library-test-token" };
    else if (path === "/me")
      body = { id: 1, email: "library@example.com", full_name: "Library User" };
    else if (path.includes("unread-count")) body = { unread_count: 0 };
    else if (path.endsWith("/baseline")) body = scenarioResultFixture;
    else if (path === "/finance/scenarios") {
      const status = url.searchParams.get("status") || "saved",
        search = url.searchParams.get("search") || "",
        offset = Number(url.searchParams.get("offset") || 0);
      const rows = records.filter(
        (r) =>
          (status === "all" || r.status === status) &&
          r.name.toLowerCase().includes(search.toLowerCase()),
      );
      body = {
        items: rows.slice(offset, offset + 12),
        total: rows.length,
        limit: 12,
        offset,
      };
    } else if (path === "/finance/scenarios/compare") {
      const ids: number[] = request.postDataJSON().scenario_ids;
      const comparison = comparisonFixture(ids);
      comparison.columns.forEach((col) => {
        col.scenario = records.find((r) => r.id === col.scenario.id)!;
      });
      body = comparison;
    } else {
      const match = path.match(/^\/finance\/scenarios\/(\d+)(?:\/(.*))?$/);
      if (match) {
        const id = Number(match[1]),
          action = match[2],
          s = records.find((r) => r.id === id)!;
        if (!s) {
          await route.fulfill({
            status: 404,
            json: { detail: "Scenario not found" },
          });
          return;
        }
        if (action === "result") {
          if (s.status === "draft") {
            await route.fulfill({
              status: 404,
              json: { detail: "No scenario result yet" },
            });
            return;
          }
          body = { ...scenarioResultFixture, scenario_id: id };
        } else if (action === "duplicate") {
          const copy = {
            ...structuredClone(s),
            id: records.length + 1,
            name: `${s.name} (Copy)`,
            status: "draft" as const,
            result_state: "missing" as const,
            source_scenario_id: id,
            latest_run_id: null,
          };
          records.push(copy);
          body = copy;
        } else if (action === "archive") {
          s.status = "archived";
          body = s;
        } else if (action === "restore") {
          s.status = "saved";
          body = s;
        } else if (action === "simulate") {
          simulations++;
          body = scenarioResultFixture;
        } else if (request.method() === "PATCH") {
          Object.assign(s, request.postDataJSON());
          body = s;
        } else body = s;
      }
    }
    await route.fulfill({ json: body });
  });
  await page.goto("/scenarios");
  await page.getByLabel("Email address").fill("library@example.com");
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const original = page.getByRole("article", {
    name: "Rent plan",
    exact: true,
  });
  await original.getByRole("button", { name: "Rename", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Rename", exact: true });
  await expect(dialog.getByLabel("Scenario name")).toBeFocused();
  await dialog.getByLabel("Scenario name").fill("Rent alternative");
  await dialog.getByRole("button", { name: "Save metadata" }).click();
  await expect(dialog).not.toBeVisible();
  const renamed = page.getByRole("article", {
    name: "Rent alternative",
    exact: true,
  });
  await expect(
    renamed.getByRole("button", { name: "Rename", exact: true }),
  ).toBeFocused();
  await renamed.getByRole("button", { name: "Duplicate", exact: true }).click();
  await expect(
    page.getByRole("article", { name: "Rent alternative (Copy)", exact: true }),
  ).toBeVisible();
  expect(JSON.stringify(records[0].changes)).toBe(originalChanges);
  await page.getByRole("button", { name: "Saved", exact: true }).click();
  await renamed.getByRole("button", { name: /Archive scenario/ }).click();
  await expect(renamed).not.toBeVisible();
  await page.getByRole("button", { name: "Archived", exact: true }).click();
  await renamed.getByRole("button", { name: "Restore", exact: true }).click();
  await page.getByRole("button", { name: "Saved", exact: true }).click();
  await page.getByLabel("Search scenarios").fill("Salary");
  await expect(renamed).not.toBeVisible();
  await page.getByLabel("Search scenarios").clear();
  await page
    .getByLabel("Select for comparison: Rent alternative", { exact: true })
    .check();
  await page
    .getByLabel("Select for comparison: Salary plan", { exact: true })
    .check();
  await page.getByRole("link", { name: "Compare selected" }).click();
  await page
    .getByRole("button", { name: "Compare scenarios", exact: true })
    .click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Assumption differences", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("-15%", { exact: true })).toBeVisible();
  expect(simulations).toBe(0);
  await page
    .getByRole("region", { name: "Financial comparison", exact: true })
    .focus();
  await expect(
    page.getByRole("region", { name: "Financial comparison", exact: true }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => localStorage.setItem("porerhishab.language", "bn"));
  await page.reload();
  await page.getByLabel(bn["Email address"]).fill("library@example.com");
  await page.getByLabel(bn.Password, { exact: true }).fill("test-password");
  await page.getByRole("button", { name: bn["Sign in"], exact: true }).click();
  await page
    .getByRole("button", { name: bn["Compare scenarios"], exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: bn["Assumption differences"],
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(simulations).toBe(0);
});
