import { useLanguage } from "../lib/useLanguage";
import { t } from "../lib/locale";
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
  useLanguage();
  if (!items.length)
    return (
      <Empty
        title={t("No transactions in this period")}
        action={
          <Link className="button" to="/transactions?add=1">
            {t("Add a transaction")}{" "}
          </Link>
        }
      >
        {t(
          "Record income and expenses to give your next decisions more context.",
        )}{" "}
      </Empty>
    );
  return (
    <div
      className="table-wrap"
      tabIndex={0}
      role="region"
      aria-label={t("Transaction records")}
    >
      <table className="transaction-table">
        <caption className="sr-only">
          {t(
            "Recorded transactions. Income is positive; expenses are negative.",
          )}{" "}
        </caption>
        <thead>
          <tr>
            <th>{t("Transaction")}</th>
            <th>{t("Date")}</th>
            <th>{t("Category")}</th>
            <th className="numeric">{t("Amount")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((transaction) => (
            <tr key={transaction.id}>
              <td>
                {onSelect ? (
                  <button
                    className="row-link"
                    onClick={() => onSelect(transaction)}
                  >
                    {transaction.merchant ||
                      transaction.description ||
                      t("Unnamed transaction")}
                  </button>
                ) : (
                  <span className="row-title">
                    {transaction.merchant ||
                      transaction.description ||
                      t("Unnamed transaction")}
                  </span>
                )}
                <small>
                  {transaction.description !== transaction.merchant
                    ? transaction.description
                    : null}
                </small>
              </td>
              <td>{date(transaction.date)}</td>
              <td>
                <span className="category">
                  {transaction.category || t("Uncategorized")}
                </span>
              </td>
              <td className="numeric">
                <Amount
                  value={transaction.amount}
                  className={Number(transaction.amount) > 0 ? "positive" : ""}
                />
                <small>
                  {Number(transaction.amount) === 0
                    ? t("No net movement")
                    : Number(transaction.amount) > 0
                      ? t("Income")
                      : t("Expense")}
                </small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
