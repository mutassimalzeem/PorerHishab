import { test, expect } from "@playwright/test";

test("shows worker acceptance and terminal failure through authenticated notification history", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Email address").fill("review@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Review-E2E-only-123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Alerts", exact: true })
    .click();
  const history = page.waitForResponse(
    (r) => r.url().includes("/finance/notifications/history") && r.ok(),
  );
  await page
    .getByRole("button", { name: "Notification history", exact: true })
    .click();
  const payload = await (await history).json();
  expect(
    payload.items.filter((item: { status: string }) => item.status === "SENT"),
  ).toHaveLength(2);
  expect(
    payload.items.filter(
      (item: { status: string }) => item.status === "DEAD_LETTER",
    ),
  ).toHaveLength(1);
  await expect(page.locator(".notification-item-card")).toHaveCount(3);
  await expect(
    page.locator(".notification-item-card").filter({ hasText: "SENT" }),
  ).toHaveCount(2);
  await expect(
    page.locator(".notification-item-card").filter({ hasText: "DEAD_LETTER" }),
  ).toHaveCount(1);
});
