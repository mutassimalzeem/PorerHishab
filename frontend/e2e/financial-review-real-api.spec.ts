import { test, expect } from "@playwright/test";

const backend = "http://127.0.0.1:8019";
const password = "Review-E2E-only-123!";

test("real login, review, reported action, isolation and observational outcome", async ({
  page,
  request,
}) => {
  expect((await request.get(`${backend}/finance/review`)).status()).toBe(401);
  const login = await request.post(`${backend}/login`, {
    data: { email: "review@example.com", password },
  });
  expect(login.ok()).toBeTruthy();
  const headers = {
    Authorization: `Bearer ${(await login.json()).access_token}`,
  };
  const read = async (path: string, auth = headers) => {
    const response = await request.get(`${backend}${path}`, { headers: auth });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  };
  const before = await Promise.all([
    read("/accounts"),
    read("/transactions"),
    read("/finance/goals"),
    read("/finance/scheduled-cashflow"),
  ]);
  await page.goto("/");
  await page.getByLabel("Email address").fill("review@example.com");
  await page.getByLabel("Password", { exact: true }).fill(password);
  const browserLogin = page.waitForResponse(
    (r) => r.url().endsWith("/login") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  expect((await browserLogin).ok()).toBeTruthy();
  const reviewResponse = page.waitForResponse(
    (r) => r.url().includes("/finance/review") && r.ok(),
  );
  await page.getByRole("link", { name: "Insights", exact: true }).click();
  const review = await (await reviewResponse).json();
  expect(review.status).toBe("review_only");
  expect(review.execution_plan.steps.length).toBeGreaterThan(0);
  const supported = review.execution_plan.steps
    .flatMap((step: { source_action_ids: string[] }) => step.source_action_ids)
    .filter((id: string) =>
      /^(cash_risk|upcoming_obligations|spending_spike|repeated_spending|savings_opportunity|goal_risk):/.test(
        id,
      ),
    );
  expect(supported.length).toBeGreaterThan(0);
  const section = page
    .locator("section")
    .filter({
      has: page.getByRole("heading", { name: "Financial review", exact: true }),
    })
    .first();
  await expect(
    section.getByRole("heading", { name: "Your next actions" }),
  ).toBeVisible();
  const evidence = section
    .locator("details")
    .filter({ has: page.locator("summary", { hasText: "View evidence" }) })
    .first();
  await evidence.locator("summary").click();
  await expect(evidence).toHaveAttribute("open", "");
  await expect(evidence.locator("dl").first()).toBeVisible();
  const feedbackResponse = page.waitForResponse(
    (r) => r.url().includes("/feedback") && r.request().method() === "PUT",
  );
  const refreshed = page.waitForResponse(
    (r) => r.url().includes("/finance/review") && r.ok(),
  );
  await section
    .getByRole("button", { name: "Mark as done", exact: true })
    .first()
    .click();
  const feedback = await feedbackResponse;
  expect(feedback.ok(), await feedback.text()).toBeTruthy();
  expect(feedback.request().postDataJSON().status).toBe("acted_on");
  const record = await feedback.json();
  expect(supported).toContain(record.recommendation_id);
  expect(record.recommendation_id.startsWith("plan:")).toBe(false);
  await refreshed;
  await page.locator("#action-outcomes").scrollIntoViewIfNeeded();
  await expect(page.locator("#action-outcomes .outcome-card")).toHaveCount(1);
  await expect(page.locator("#action-outcomes")).toContainText(
    "They do not prove that an action caused a change.",
  );
  const outcomes = await read("/finance/action-outcomes");
  expect(outcomes.items).toHaveLength(1);
  expect(outcomes.items[0].recommendation_id).toBe(record.recommendation_id);
  expect(outcomes.items[0].causal_claim).toBe(false);
  expect(["pending", "insufficient_data"]).toContain(outcomes.items[0].status);
  expect(
    await Promise.all([
      read("/accounts"),
      read("/transactions"),
      read("/finance/goals"),
      read("/finance/scheduled-cashflow"),
    ]),
  ).toEqual(before);
  const otherLogin = await request.post(`${backend}/login`, {
    data: { email: "other@example.com", password },
  });
  expect(otherLogin.ok()).toBeTruthy();
  const other = {
    Authorization: `Bearer ${(await otherLogin.json()).access_token}`,
  };
  const otherReview = await read("/finance/review?user_id=1", other);
  expect(JSON.stringify(otherReview)).not.toContain("Synthetic laptop");
  expect(otherReview.plan.goal_planning.goals).toEqual([]);
  expect(await read("/finance/coaching/feedback", other)).toEqual([]);
  expect(
    (
      await request.get(
        `${backend}/finance/action-outcomes?recommendation_id=${encodeURIComponent(record.recommendation_id)}`,
        { headers: other },
      )
    ).status(),
  ).toBe(404);
  expect(
    (
      await request.put(
        `${backend}/finance/coaching/${encodeURIComponent(record.recommendation_id)}/feedback`,
        {
          headers: other,
          data: { status: "acted_on" },
        },
      )
    ).status(),
  ).toBe(404);
});
