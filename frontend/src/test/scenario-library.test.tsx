import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ScenarioLibrary } from "../components/ScenarioLibrary";
import { ScenarioComparison } from "../pages/ScenarioComparison";
import { api } from "../lib/api";
import { setLanguage, t } from "../lib/locale";
import {
  libraryScenarios,
  comparisonFixture,
} from "./scenario-library.fixture";
const open = vi.fn(),
  change = vi.fn(),
  refresh = vi.fn();
beforeEach(() => {
  vi.restoreAllMocks();
  open.mockReset();
  change.mockReset();
  refresh.mockReset();
  setLanguage("en");
  vi.spyOn(api, "scenarioLibrary").mockResolvedValue({
    items: libraryScenarios,
    total: 6,
    limit: 12,
    offset: 0,
  });
});
afterEach(() => setLanguage("en"));
function library() {
  return render(
    <MemoryRouter>
      <ScenarioLibrary
        revision={0}
        disabled={false}
        onOpen={open}
        onChange={change}
        onRefresh={refresh}
      />
    </MemoryRouter>,
  );
}
function compare(route = "/scenarios/compare") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ScenarioComparison />
    </MemoryRouter>,
  );
}
it("lists cards, searches, switches archives and paginates", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "scenarioLibrary").mockImplementation(
    async (status, search, offset) => ({
      items:
        status === "archived"
          ? [{ ...libraryScenarios[2], status: "archived" }]
          : libraryScenarios.filter((s) => s.name.includes(search || "")),
      total: 30,
      limit: 12,
      offset: offset || 0,
    }),
  );
  library();
  const card = await screen.findByRole("article", { name: "Rent plan" });
  expect(within(card).getByText("Alternative 1")).toBeVisible();
  await user.type(screen.getByLabelText("Search scenarios"), "Salary");
  await waitFor(() =>
    expect(api.scenarioLibrary).toHaveBeenLastCalledWith("saved", "Salary", 0),
  );
  await user.click(screen.getByRole("button", { name: "Archived" }));
  await screen.findByRole("button", { name: "Restore" });
  await user.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() =>
    expect(api.scenarioLibrary).toHaveBeenLastCalledWith(
      "archived",
      "Salary",
      12,
    ),
  );
});
it("opens, renames through a dialog, duplicates, archives and restores", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "renameScenario").mockResolvedValue({
    ...libraryScenarios[0],
    name: "New plan",
  });
  vi.spyOn(api, "duplicateScenario").mockResolvedValue({
    ...libraryScenarios[0],
    id: 10,
    status: "draft",
  });
  vi.spyOn(api, "archiveScenario").mockResolvedValue({
    ...libraryScenarios[0],
    status: "archived",
  });
  vi.spyOn(api, "restoreScenario").mockResolvedValue(libraryScenarios[0]);
  library();
  const card = await screen.findByRole("article", { name: "Rent plan" });
  await user.click(within(card).getByRole("button", { name: "Open" }));
  expect(open).toHaveBeenCalledWith("1");
  await user.click(within(card).getByRole("button", { name: "Rename" }));
  const dialog = screen.getByRole("dialog", { name: "Rename" });
  await user.clear(within(dialog).getByLabelText("Scenario name"));
  await user.type(within(dialog).getByLabelText("Scenario name"), "New plan");
  await user.click(
    within(dialog).getByRole("button", { name: "Save metadata" }),
  );
  await waitFor(() =>
    expect(api.renameScenario).toHaveBeenCalledWith(1, {
      name: "New plan",
      description: "Alternative 1",
    }),
  );
  await user.click(within(card).getByRole("button", { name: "Duplicate" }));
  await waitFor(() => expect(open).toHaveBeenCalledWith("10"));
  await user.click(
    within(card).getByRole("button", { name: /Archive scenario/ }),
  );
  await waitFor(() => expect(api.archiveScenario).toHaveBeenCalledWith(1));
  vi.mocked(api.scenarioLibrary).mockResolvedValue({
    items: [{ ...libraryScenarios[0], status: "archived" }],
    total: 1,
    limit: 12,
    offset: 0,
  });
  await user.click(screen.getByRole("button", { name: "Archived" }));
  await user.click(await screen.findByRole("button", { name: "Restore" }));
  await waitFor(() => expect(api.restoreScenario).toHaveBeenCalledWith(1));
});
it("bounds comparison selection and passes selected IDs", async () => {
  const user = userEvent.setup();
  library();
  const boxes = await screen.findAllByRole("checkbox");
  for (const box of boxes.slice(0, 5)) await user.click(box);
  expect(boxes[5]).toBeDisabled();
  expect(
    screen.getByRole("link", { name: "Compare selected" }),
  ).toHaveAttribute("href", "/scenarios/compare?ids=1,2,3,4,5");
});
it.each(["en", "bn"] as const)(
  "renders structured matrix and assumptions in %s",
  async (language) => {
    setLanguage(language);
    const mock = vi
      .spyOn(api, "compareScenarios")
      .mockResolvedValue(comparisonFixture());
    compare("/scenarios/compare?ids=1,2");
    await screen.findByLabelText(`${t("Select for comparison")}: Rent plan`);
    await userEvent.click(
      screen.getByRole("button", { name: t("Compare scenarios") }),
    );
    const table = await screen.findByRole("table");
    expect(mock).toHaveBeenCalledWith([1, 2]);
    expect(
      within(table).getAllByText(
        language === "bn" ? "\u09ed\u09e6\u09e6\u09e6.\u09e6\u09e6" : "7000.00",
      ),
    ).toHaveLength(2);
    expect(
      screen.getByText(
        t(
          "These scenarios have different recorded baselines. Each column shows its own real baseline.",
        ),
      ),
    ).toBeVisible();
    expect(screen.getByText("Salary decreases")).toBeVisible();
    expect(
      screen.getByText(language === "bn" ? "-\u09e7\u09eb%" : "-15%"),
    ).toBeVisible();
    expect(
      within(table).getAllByText(
        t("not_available_for_scenario").replaceAll("_", " "),
      ).length,
    ).toBeGreaterThan(0);
  },
);
it("keeps missing and stale results explicit", async () => {
  const result = comparisonFixture();
  result.columns[1] = {
    ...result.columns[1],
    scenario: { ...result.columns[1].scenario, result_state: "stale" },
    result: null,
  };
  for (const row of result.metrics)
    row.cells[1] = {
      scenario_id: 2,
      comparison: null,
      status: "insufficient_data",
      reason: "Stale result",
    };
  result.warnings = ["stale_results"];
  vi.spyOn(api, "compareScenarios").mockResolvedValue(result);
  compare("/scenarios/compare?ids=1,2");
  await userEvent.click(
    screen.getByRole("button", { name: "Compare scenarios" }),
  );
  await screen.findByText(
    t("Assumptions changed. Open the scenario and rerun it explicitly."),
  );
  expect(screen.getAllByText("insufficient data").length).toBeGreaterThan(0);
});
it("supports loading, request failures and retry", async () => {
  vi.mocked(api.scenarioLibrary).mockReturnValue(new Promise(() => {}));
  library();
  expect(screen.getByRole("status")).toBeVisible();
});
it("renders library errors with retry and comparison errors", async () => {
  vi.mocked(api.scenarioLibrary).mockRejectedValue(new Error("offline"));
  library();
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
});
it("reports incompatible versions without displaying stale money", async () => {
  vi.spyOn(api, "compareScenarios").mockRejectedValue(
    new Error("Incompatible calculation versions"),
  );
  compare("/scenarios/compare?ids=1,2");
  await userEvent.click(
    screen.getByRole("button", { name: "Compare scenarios" }),
  );
  await screen.findByRole("alert");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
