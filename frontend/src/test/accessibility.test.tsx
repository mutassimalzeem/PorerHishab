import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import axe from "axe-core";
import { Auth } from "../pages/Auth";
import { Ask } from "../pages/Ask";
import { Settings } from "../pages/Settings";
import { CashflowChart } from "../components/CashflowChart";
describe("automated accessibility checks", () => {
  for (const [name, element] of [
    ["authentication", <Auth onLogin={() => {}} expired={false} />],
    ["Ask", <Ask />],
    [
      "settings",
      <Settings
        user={{ id: 1, email: "a@example.com", full_name: "A" }}
        onLogout={() => {}}
      />,
    ],
    [
      "cashflow chart",
      <CashflowChart
        months={[
          {
            month: "2026-10",
            historical_income_estimate: null,
            historical_expense_estimate: null,
            scheduled_expenses: "100",
            uncertain_scheduled_income: "0",
            reserved_expenses: "100",
            projected_balance: null,
            balance_without_future_income: "900",
          },
        ]}
      />,
    ],
  ] as const) {
    it(`${name} has no automatically detected structural violations`, async () => {
      const { container } = render(
        <MemoryRouter>
          {name === "authentication" ? element : <main>{element}</main>}
        </MemoryRouter>,
      );
      const result = await axe.run(container, {
        rules: { "color-contrast": { enabled: false } },
      });
      expect(
        result.violations.map((v) => ({
          id: v.id,
          description: v.description,
        })),
      ).toEqual([]);
    });
  }
});
