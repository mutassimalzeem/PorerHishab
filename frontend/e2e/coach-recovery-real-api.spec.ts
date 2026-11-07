import { test, expect } from "@playwright/test";

test("recovers an interrupted receipt, replays a lost response and restores history", async ({
  page,
  request,
}) => {
  const backend = "http://127.0.0.1:8019";
  const key = "17f00000-0000-4000-8000-000000000001";
  await page.goto("/");
  await page.getByLabel("Email address").fill("review@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Review-E2E-only-123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("link", { name: "Ask PorerHishab", exact: true })
    .click();
  const coach = page.getByRole("region", {
    name: "PorerHishab Financial Coach",
    exact: true,
  });
  await coach.getByRole("button", { name: "Saved chats", exact: true }).click();
  await coach.getByText("Interrupted coach question", { exact: true }).click();
  await expect(coach.getByText("(Failed)", { exact: true })).toBeVisible();
  const completion = page.waitForResponse(
    (r) => r.url().includes("/coach/ask") && r.request().method() === "POST",
  );
  await coach.getByRole("button", { name: "Try again", exact: true }).click();
  const response = await completion;
  expect(response.ok()).toBeTruthy();
  expect(response.request().postDataJSON().request_id).toBe(key);
  const canonical = await response.json();
  await expect(coach.locator(".asst-row .coach-answer-text")).toHaveCount(1);
  await expect(coach.locator(".user-row .coach-answer-text")).toHaveCount(1);

  const login = await request.post(`${backend}/login`, {
    data: { email: "review@example.com", password: "Review-E2E-only-123!" },
  });
  expect(login.ok()).toBeTruthy();
  const headers = {
    Authorization: `Bearer ${(await login.json()).access_token}`,
  };
  const replay = await request.post(`${backend}/coach/ask`, {
    headers,
    data: response.request().postDataJSON(),
  });
  expect(replay.ok()).toBeTruthy();
  expect(await replay.json()).toEqual(canonical);
  const detail = await request.get(
    `${backend}/coach/conversations/${canonical.conversation_id}`,
    { headers },
  );
  expect(
    (await detail.json()).messages.map((m: { role: string }) => m.role),
  ).toEqual(["user", "assistant"]);

  // Drop a response only AFTER the actual backend request has completed. Neither
  // persistence nor recovery endpoints are mocked; this models a lost client read.
  await page.evaluate(() => {
    const original = window.fetch.bind(window);
    let drop = true;
    window.fetch = async (...args: Parameters<typeof fetch>) => {
      const result = await original(...args);
      if (drop && String(args[0]).includes("/coach/ask")) {
        drop = false;
        await result.text();
        throw new TypeError("Simulated lost client response");
      }
      return result;
    };
  });
  await coach
    .getByLabel("Ask your financial coach")
    .fill("What bills are coming up?");
  await coach.getByRole("button", { name: "Send question" }).click();
  await expect(coach.locator(".asst-row .coach-answer-text")).toHaveCount(2);
  await expect(coach.locator(".user-row .coach-answer-text")).toHaveCount(2);
  await expect(coach.getByRole("button", { name: "Try again" })).toHaveCount(0);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page
    .getByRole("link", { name: "Ask PorerHishab", exact: true })
    .click();
  await expect(coach.locator(".asst-row .coach-answer-text")).toHaveCount(2);
  await expect(coach).toContainText("Ask a new question for current finances.");
});
