import { Link } from "react-router-dom";
import type { Transaction } from "../domain";
import { Amount, Empty } from "./ui";
import { date } from "../lib/format";
export function TransactionTable({
  items,
  onSelect,
}: {
  items: Transaction[];
  onSelect?: (item: Transaction) => void;
}) {
  if (!items.length)
    return (
      <Empty
        title="No transactions in this period"
        action={
          <Link className="button" to="/transactions?add=1">
            Add a transaction
          </Link>
        }
      >
        Record income and expenses to give your next decisions more context.
      </Empty>
    );
  return (
    <div
      className="table-wrap"
      tabIndex={0}
      role="region"
      aria-label="Transaction records"
    >
      <table className="transaction-table">
        <caption className="sr-only">
          Recorded transactions. Income is positive; expenses are negative.
        </caption>
        <thead>
          <tr>
            <th>Transaction</th>
            <th>Date</th>
            <th>Category</th>
            <th className="numeric">Amount</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id}>
              <td>
                {onSelect ? (
                  <button className="row-link" onClick={() => onSelect(t)}>
                    {t.merchant || t.description || "Unnamed transaction"}
                  </button>
                ) : (
                  <span className="row-title">
                    {t.merchant || t.description || "Unnamed transaction"}
                  </span>
                )}
                <small>
                  {t.description !== t.merchant ? t.description : null}
                </small>
              </td>
              <td>{date(t.date)}</td>
              <td>
                <span className="category">
                  {t.category || "Uncategorized"}
                </span>
              </td>
              <td className="numeric">
                <Amount
                  value={t.amount}
                  className={Number(t.amount) > 0 ? "positive" : ""}
                />
                <small>
                  {Number(t.amount) === 0
                    ? "No net movement"
                    : Number(t.amount) > 0
                      ? "Income"
                      : "Expense"}
                </small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
