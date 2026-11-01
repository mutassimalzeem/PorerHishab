import type { ApiSchemas } from "../generated/api";
import { scenarioFixture, scenarioResultFixture } from "./scenarios.fixture";
export const libraryScenarios: ApiSchemas["ScenarioRead"][] = Array.from(
  { length: 6 },
  (_, i) => ({
    ...scenarioFixture,
    id: i + 1,
    name: [
      "Rent plan",
      "Salary plan",
      "Laptop plan",
      "Savings plan",
      "Emergency plan",
      "Lower spending",
    ][i],
    description: `Alternative ${i + 1}`,
    status: "saved",
    result_state: "current",
    latest_run_id: i + 1,
    changes: [
      {
        change_type:
          i === 1 ? "income_adjustment" : "recurring_expense_adjustment",
        amount: i === 1 ? null : "2000.00",
        percentage: i === 1 ? "-15" : null,
        currency: "BDT",
        effective_date: "2026-11-01",
        frequency: "monthly",
        description: i === 1 ? "Salary decreases" : "Rent increases",
      },
    ],
  }),
);
export function comparisonFixture(
  ids = [1, 2],
): ApiSchemas["ScenarioLibraryComparison"] {
  const selected = ids.map((id) => libraryScenarios[id - 1]);
  const columns = selected.map((s) => ({
    scenario: s,
    result: {
      ...scenarioResultFixture,
      scenario_id: s.id,
      run_id: s.id,
      assumptions: s.changes,
    },
    assumptions: s.changes.map((change) => ({ change, shared: false })),
  }));
  return {
    columns,
    calculation_version: "ai-15q-v1",
    warnings: ["different_baselines"],
    metrics: scenarioResultFixture.comparisons.map((m) => ({
      metric: m.metric,
      cells: selected.map((s) => ({
        scenario_id: s.id,
        comparison: m,
        status: m.status,
        reason: m.reason,
      })),
    })),
  };
}
