import { it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Transactions } from "../pages/Transactions";
import { api } from "../lib/api";

it("reports partial CSV persistence and row errors", async () => {
  vi.spyOn(api, "transactions").mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  });
  vi.spyOn(api, "upload").mockResolvedValue({
    filename: "rows.csv",
    records: 1,
    rows_received: 2,
    rows_persisted: 1,
    rows_rejected: 1,
    rows_skipped: 0,
    errors: [{ row: 3, field: "amount", message: "Invalid or missing amount" }],
    total_income: 0,
    total_expenses: -1,
    balance: -1,
    preview: [],
  });
  render(
    <MemoryRouter>
      <Transactions />
    </MemoryRouter>,
  );
  const user = userEvent.setup();
  await user.upload(
    screen.getByLabelText("Import transaction CSV"),
    new File(["date,amount\n2026-11-01,-1\n2026-11-01,invalid"], "rows.csv", {
      type: "text/csv",
    }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "1 of 2 rows imported; 1 rejected",
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "Row 3: Invalid or missing amount",
  );
});
