import { useCallback, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, Search, Upload } from "lucide-react";
import type { Transaction } from "../domain";
import { api } from "../lib/api";
import { errorMessage, today } from "../lib/format";
import { useResource } from "../lib/useResource";
import {
  Amount,
  ErrorNotice,
  Field,
  PageHeading,
  Pager,
  ResourceView,
} from "../components/ui";
import { Dialog } from "../components/Dialog";
import { TransactionTable } from "../components/TransactionTable";
export function Transactions() {
  const [params, setParams] = useSearchParams();
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<Transaction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const key = params.toString();
  const records = useResource(
    useCallback(
      () =>
        api.transactions({
          ...Object.fromEntries(new URLSearchParams(key)),
          add: undefined,
          limit: 20,
          offset,
          sort: "desc",
        }),
      [key, offset],
    ),
    revision,
  );
  function refresh() {
    setRevision((v) => v + 1);
  }
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const f = new FormData(e.currentTarget);
    try {
      await api.addTransaction({
        date: String(f.get("date")),
        description: String(f.get("description")),
        merchant: String(f.get("merchant")) || undefined,
        amount: String(f.get("amount")),
        category: String(f.get("category")) || undefined,
      });
      setParams({});
      setNotice("Transaction recorded.");
      refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function correct(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await api.correctCategory(
        selected.id,
        String(new FormData(e.currentTarget).get("category")),
      );
      setSelected(null);
      setNotice("Category updated.");
      refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="Every transaction, in context."
        description="Search your records, review a detail, or correct a category."
        action={
          <div className="actions">
            <button onClick={() => file.current?.click()} disabled={busy}>
              <Upload size={16} />
              Import CSV
            </button>
            <button
              className="primary"
              onClick={() => {
                setError(null);
                setParams({ ...Object.fromEntries(params), add: "1" });
              }}
            >
              <Plus size={16} />
              Add transaction
            </button>
          </div>
        }
      />
      <input
        type="file"
        accept=".csv,text/csv"
        ref={file}
        className="sr-only"
        aria-label="Import transaction CSV"
        onChange={async (e) => {
          const chosen = e.target.files?.[0];
          if (!chosen) return;
          const input = e.target;
          setBusy(true);
          setError(null);
          try {
            await api.upload(chosen);
            setNotice("CSV processed. Review your transactions below.");
            refresh();
          } catch (e) {
            setError(errorMessage(e));
          } finally {
            setBusy(false);
            input.value = "";
          }
        }}
      />
      <p className="muted">
        CSV: date and amount required; description, merchant and category
        supported. Positive amounts are income; negative amounts are expenses.
      </p>
      {notice && (
        <p role="status" className="success">
          {notice}
        </p>
      )}
      {error && !selected && params.get("add") !== "1" && (
        <ErrorNotice message={error} />
      )}
      <Dialog
        open={params.get("add") === "1"}
        title="Record a transaction"
        description="Record money that has already occurred. Use negative amounts for expenses."
        busy={busy}
        onClose={() => {
          const next = new URLSearchParams(params);
          next.delete("add");
          setParams(next);
          setError(null);
        }}
      >
        {error && <ErrorNotice message={error} />}
        <form onSubmit={create} className="form-grid">
          <Field
            label="Description"
            name="description"
            required
            maxLength={1000}
          />
          <Field label="Merchant (optional)" name="merchant" maxLength={255} />
          <Field
            label="Date"
            name="date"
            type="date"
            required
            defaultValue={today()}
          />
          <Field
            label="Signed amount (BDT)"
            name="amount"
            type="number"
            step="0.01"
            required
            hint="Use a negative amount for an expense."
          />
          <Field label="Category (optional)" name="category" maxLength={100} />
          <button className="primary form-end" disabled={busy}>
            {busy ? "Saving..." : "Record transaction"}
          </button>
        </form>
      </Dialog>
      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const next = new URLSearchParams();
          f.forEach((value, key) => {
            if (value) next.set(key, String(value));
          });
          const kind = String(f.get("kind"));
          next.delete("kind");
          if (kind === "income") next.set("min_amount", "0.01");
          if (kind === "expense") next.set("max_amount", "-0.01");
          setParams(next);
        }}
        key={key}
      >
        <label className="field search">
          <span>
            <Search size={15} />
            Search
          </span>
          <input
            name="q"
            placeholder="Merchant or description"
            defaultValue={params.get("q") || ""}
          />
        </label>
        <Field
          label="From"
          name="start_date"
          type="date"
          defaultValue={params.get("start_date") || ""}
        />
        <Field
          label="To"
          name="end_date"
          type="date"
          defaultValue={params.get("end_date") || ""}
        />
        <Field
          label="Category"
          name="category"
          defaultValue={params.get("category") || ""}
        />
        <label className="field">
          <span>Type</span>
          <select
            name="kind"
            defaultValue={
              params.has("min_amount")
                ? "income"
                : params.has("max_amount")
                  ? "expense"
                  : ""
            }
          >
            <option value="">All activity</option>
            <option value="income">Income</option>
            <option value="expense">Expenses</option>
          </select>
        </label>
        <button className="form-end">Apply filters</button>
        <button
          type="button"
          className="text-button form-end"
          onClick={() => setParams({})}
        >
          Reset
        </button>
      </form>
      <ResourceView resource={records}>
        {(p) => (
          <>
            <TransactionTable
              items={p.items}
              onSelect={(t) => {
                setSelected(t);
                setError(null);
              }}
            />
            <Pager
              offset={offset}
              total={p.total}
              limit={20}
              onChange={(n) =>
                setParams({ ...Object.fromEntries(params), offset: String(n) })
              }
            />
          </>
        )}
      </ResourceView>
      <Dialog
        open={selected !== null}
        title="Transaction details"
        description="Review the recorded amount and the reason for its category."
        drawer
        busy={busy}
        onClose={() => {
          setSelected(null);
          setError(null);
        }}
      >
        {selected && (
          <>
            <h3>
              {selected.merchant || selected.description || "Transaction"}
            </h3>
            {error && <ErrorNotice message={error} />}
            <Amount value={selected.amount} />
            <p>{selected.description}</p>
            <p className="muted">
              Source: {selected.source || "Not supplied"} / Fee:{" "}
              <Amount value={selected.fee} />
            </p>
            <p>
              {selected.category_reason ||
                "No categorization explanation supplied."}
            </p>
            <form onSubmit={correct} className="inline-form">
              <Field
                label="Correct category"
                name="category"
                required
                maxLength={100}
                defaultValue={selected.category || ""}
              />
              <button className="primary form-end" disabled={busy}>
                Save category
              </button>
            </form>
          </>
        )}
      </Dialog>
    </>
  );
}
