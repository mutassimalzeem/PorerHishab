import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import { Plus, AlertTriangle, CheckCircle2, HelpCircle } from "lucide-react";
import type { AccountPositionItem } from "../domain";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { date, errorMessage, today } from "../lib/format";
import { digits, t, uiLabel } from "../lib/locale";
import { useLanguage } from "../lib/useLanguage";
import { Dialog } from "../components/Dialog";
import {
  Amount,
  Empty,
  ErrorNotice,
  Field,
  PageHeading,
  ResourceView,
  Section,
} from "../components/ui";

export function Accounts() {
  useLanguage();
  const [revision, setRevision] = useState(0);
  const [adding, setAdding] = useState(false);
  const [editingBalance, setEditingBalance] = useState<AccountPositionItem | null>(null);
  const [editingOpening, setEditingOpening] = useState<AccountPositionItem | null>(null);
  const [details, setDetails] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const overview = useResource(
    useCallback(() => api.accounts(), []),
    revision,
  );

  async function handleAddAccount(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    setBusy(true);
    setError(null);
    try {
      const current_bal = f.get("current_balance");
      const open_bal = f.get("opening_balance");
      const open_date = f.get("opening_balance_date");
      const bal_source = f.get("balance_source");

      await api.addAccount({
        name: String(f.get("name")),
        account_type: String(f.get("account_type")),
        currency: String(f.get("currency") || "BDT").toUpperCase(),
        current_balance: current_bal ? String(current_bal) : undefined,
        balance_source: bal_source ? String(bal_source) : undefined,
        balance_as_of: current_bal ? new Date().toISOString() : undefined,
        opening_balance: open_bal ? String(open_bal) : undefined,
        opening_balance_date: open_date ? String(open_date) : undefined,
      });

      setAdding(false);
      setRevision((v) => v + 1);
      setNotice(t("Account saved successfully."));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdateBalance(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!editingBalance) return;
    const form = e.currentTarget;
    const f = new FormData(form);
    setBusy(true);
    setError(null);
    try {
      const balDate = String(f.get("balance_as_of"));
      const asOf = balDate.includes("T") ? balDate : `${balDate}T12:00:00Z`;

      await api.updateBalance(editingBalance.id, {
        current_balance: String(f.get("current_balance")),
        balance_source: String(f.get("balance_source")),
        balance_as_of: asOf,
      });

      setEditingBalance(null);
      setRevision((v) => v + 1);
      setNotice(t("Balance updated successfully."));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdateOpening(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!editingOpening) return;
    const form = e.currentTarget;
    const f = new FormData(form);
    setBusy(true);
    setError(null);
    try {
      await api.updateOpeningBalance(editingOpening.id, {
        opening_balance: String(f.get("opening_balance")),
        opening_balance_date: String(f.get("opening_balance_date")),
      });

      setEditingOpening(null);
      setRevision((v) => v + 1);
      setNotice(t("Opening balance updated successfully."));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeading
        title={t("Your recorded account position")}
        description={t("Understand what is recorded and how well it reconciles.")}
        action={
          <button
            type="button"
            className="primary"
            onClick={() => {
              setAdding(true);
              setError(null);
            }}
          >
            <Plus size={17} />
            {t("Add account")}
          </button>
        }
      />

      {notice && (
        <p role="status" className="success">
          {uiLabel(notice)}
        </p>
      )}

      {error && !adding && !editingBalance && !editingOpening && (
        <ErrorNotice message={error} retry={() => setRevision((v) => v + 1)} />
      )}

      <ResourceView resource={overview} label={t("Loading your records...")}>
        {(data) => {
          const trusted = data.trusted_bdt_position;
          return (
            <>
              <Section title={t("Total trusted BDT position")}>
                <div className="account-trusted-card">
                  {trusted.total !== null ? (
                    <div>
                      <Amount value={trusted.total} className="account-total-amount" />
                      <p className="source">
                        {t("Based on")} {digits(trusted.eligible_accounts_count)}{" "}
                        {trusted.eligible_accounts_count === 1 ? t("account") : t("accounts")}
                        {trusted.review_accounts_count > 0 && (
                          <span>
                            {" "}• {digits(trusted.review_accounts_count)}{" "}
                            {trusted.review_accounts_count === 1 ? t("account needs review") : t("accounts need review")}
                          </span>
                        )}
                      </p>
                      {(trusted.contributing_account_names || []).length > 0 && (
                        <p className="account-tags">
                          {(trusted.contributing_account_names || []).map((name) => (
                            <span key={name} className="account-pill">
                              {name}
                            </span>
                          ))}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div>
                      <strong className="account-unavailable-label">{t("Not available yet")}</strong>
                      <p className="source">
                        {t("Add or confirm a balance for at least one BDT account.")}
                      </p>
                    </div>
                  )}
                </div>
              </Section>

              <div className="meaning-strip">
                <span>
                  <b>{t("Notice")}</b>{" "}
                  {t("This balance is information you provide. PorerHishab does not verify it against your bank.")}
                </span>
              </div>

              <Section title={t("Accounts")}>
                {data.items.length === 0 ? (
                  <Empty
                    title={t("No accounts yet")}
                    action={
                      <button
                        type="button"
                        className="button primary"
                        onClick={() => {
                          setAdding(true);
                          setError(null);
                        }}
                      >
                        {t("Add account")}
                      </button>
                    }
                  >
                    {t("Add an account or import account-linked transactions to start tracking your position.")}
                  </Empty>
                ) : (
                  <div className="account-list">
                    {data.items.map((acc) => {
                      const isBdt = acc.currency === "BDT";
                      const isDetailsOpen = details === acc.id;
                      const hasDiff =
                        acc.reconciliation.difference !== null &&
                        Number(acc.reconciliation.difference) !== 0;

                      return (
                        <div key={acc.id} className="account-card" data-testid={`account-card-${acc.id}`}>
                          <div className="account-card-header">
                            <div>
                              <h3 className="account-name">{acc.name}</h3>
                              <span className="account-type-badge">
                                {uiLabel(acc.account_type)}
                              </span>
                            </div>
                            <span className="account-currency-badge">{acc.currency}</span>
                          </div>

                          {!isBdt ? (
                            <div className="account-foreign-warning">
                              {acc.current_balance !== null ? (
                                <p className="account-foreign-balance">
                                  <strong>{acc.current_balance} {acc.currency}</strong>
                                </p>
                              ) : null}
                              <p className="source account-excluded-note">
                                <AlertTriangle size={15} />
                                <span>
                                  <strong>{t("Not included in trusted BDT position")}</strong>.{" "}
                                  {t("Currency conversion is not available.")}
                                </span>
                              </p>
                            </div>
                          ) : (
                            <div className="account-body">
                              <div className="account-balance-line">
                                <div>
                                  <span className="muted">{t("Reported balance")}:</span>
                                  {acc.current_balance !== null ? (
                                    <Amount value={acc.current_balance} />
                                  ) : (
                                    <span className="account-empty-balance">
                                      {t("Balance not recorded")}
                                    </span>
                                  )}
                                </div>
                                {acc.balance_as_of && (
                                  <small className="muted">
                                    {t("Reported")} {date(acc.balance_as_of.slice(0, 10))}
                                    {acc.balance_source && ` (${uiLabel(acc.balance_source)})`}
                                  </small>
                                )}
                              </div>

                              <div className="account-status-row">
                                {acc.reconciliation.status === "reconciled" ? (
                                  <span className="badge-status badge-success">
                                    <CheckCircle2 size={14} />
                                    {t("Reconciled")}
                                  </span>
                                ) : acc.reconciliation.status === "mismatch" || hasDiff ? (
                                  <span className="badge-status badge-warning">
                                    <AlertTriangle size={14} />
                                    {t("Needs review")}
                                  </span>
                                ) : acc.reconciliation.status === "derived_from_opening" ? (
                                  <span className="badge-status badge-info">
                                    {t("Derived from opening balance")}
                                  </span>
                                ) : acc.reconciliation.status === "reported_only" ? (
                                  <span className="badge-status badge-neutral">
                                    {t("Reported only")}
                                  </span>
                                ) : (
                                  <span className="badge-status badge-muted">
                                    <HelpCircle size={14} />
                                    {t("Derived balance unavailable")}
                                  </span>
                                )}

                                {acc.reconciliation.difference !== null && (
                                  <span className="account-diff-label">
                                    {t("Difference")}: <Amount value={acc.reconciliation.difference} />
                                  </span>
                                )}
                              </div>

                              {(acc.reconciliation.status === "mismatch" || hasDiff) && (
                                <p className="account-mismatch-warning">
                                  {t("Reported balance and recorded activity do not currently match.")}
                                </p>
                              )}
                            </div>
                          )}

                          <div className="account-actions">
                            <button
                              type="button"
                              onClick={() => {
                                setEditingBalance(acc);
                                setError(null);
                              }}
                            >
                              {t("Update balance")}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingOpening(acc);
                                setError(null);
                              }}
                            >
                              {t("Update opening balance")}
                            </button>
                            <button
                              type="button"
                              className="text-button"
                              aria-expanded={isDetailsOpen}
                              onClick={() => setDetails(isDetailsOpen ? null : acc.id)}
                            >
                              {t("Reconciliation details")}
                            </button>
                          </div>

                          {isDetailsOpen && (
                            <div className="account-details-panel" data-testid={`account-details-${acc.id}`}>
                              <h4>{t("Reconciliation details")}</h4>
                              <dl className="account-detail-list">
                                <div>
                                  <dt>{t("Reported balance")}</dt>
                                  <dd>
                                    {acc.current_balance !== null ? (
                                      <Amount value={acc.current_balance} />
                                    ) : (
                                      t("Balance not recorded")
                                    )}
                                  </dd>
                                </div>
                                <div>
                                  <dt>{t("Balance source")}</dt>
                                  <dd>{acc.balance_source ? uiLabel(acc.balance_source) : "-"}</dd>
                                </div>
                                <div>
                                  <dt>{t("Balance as of")}</dt>
                                  <dd>{acc.balance_as_of ? date(acc.balance_as_of.slice(0, 10)) : "-"}</dd>
                                </div>
                                <div>
                                  <dt>{t("Opening balance")}</dt>
                                  <dd>
                                    {acc.opening_balance !== null ? (
                                      <Amount value={acc.opening_balance} />
                                    ) : (
                                      "-"
                                    )}
                                  </dd>
                                </div>
                                <div>
                                  <dt>{t("Opening balance date")}</dt>
                                  <dd>{acc.opening_balance_date ? date(acc.opening_balance_date) : "-"}</dd>
                                </div>
                                <div>
                                  <dt>{t("Derived balance")}</dt>
                                  <dd>
                                    {acc.reconciliation.derived_balance !== null ? (
                                      <Amount value={acc.reconciliation.derived_balance} />
                                    ) : (
                                      <span>
                                        {t("Derived balance unavailable")}{" "}
                                        <small className="muted">
                                          ({t("A known opening balance and transaction history are required to derive this value.")})
                                        </small>
                                      </span>
                                    )}
                                  </dd>
                                </div>
                                <div>
                                  <dt>{t("Difference")}</dt>
                                  <dd>
                                    {acc.reconciliation.difference !== null ? (
                                      <Amount value={acc.reconciliation.difference} />
                                    ) : (
                                      "-"
                                    )}
                                  </dd>
                                </div>
                                <div>
                                  <dt>{t("Transactions recorded")}</dt>
                                  <dd>{digits(acc.reconciliation.transaction_count ?? 0)}</dd>
                                </div>
                              </dl>

                              {(acc.reconciliation.status === "mismatch" || hasDiff) && (
                                <div className="callout">
                                  <strong>{t("Possible explanations for differences:")}</strong>{" "}
                                  {t("Missing transactions, duplicate records, incorrect amounts, incorrect opening balance, or timing differences.")}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </Section>
            </>
          );
        }}
      </ResourceView>

      {/* Add Account Dialog */}
      <Dialog
        open={adding}
        title={t("New account")}
        description={t("Add an account to track its position.")}
        busy={busy}
        onClose={() => {
          setAdding(false);
          setError(null);
        }}
      >
        {error && <ErrorNotice message={error} />}
        <form className="form-grid" onSubmit={handleAddAccount}>
          <Field
            name="name"
            label={t("Account name")}
            required
            maxLength={100}
            placeholder="e.g. City Bank, bKash, Cash Wallet"
          />

          <label className="field">
            <span>{t("Account type")}</span>
            <select name="account_type" defaultValue="bank">
              <option value="bank">{t("Bank")}</option>
              <option value="cash">{t("Cash")}</option>
              <option value="mobile_wallet">{t("Mobile wallet")}</option>
              <option value="credit">{t("Credit")}</option>
              <option value="other">{t("Other")}</option>
            </select>
          </label>

          <Field
            name="currency"
            label={t("Currency")}
            defaultValue="BDT"
            maxLength={3}
            required
          />

          <Field
            name="current_balance"
            label={t("Current balance")}
            type="number"
            step="0.01"
            placeholder="Optional"
          />

          <label className="field">
            <span>{t("Balance source")}</span>
            <select name="balance_source" defaultValue="manual">
              <option value="manual">{t("Manual")}</option>
              <option value="statement">{t("Statement")}</option>
              <option value="app">{t("Mobile app")}</option>
            </select>
          </label>

          <Field
            name="opening_balance"
            label={t("Opening balance")}
            type="number"
            step="0.01"
            placeholder="Optional"
          />

          <Field
            name="opening_balance_date"
            label={t("Opening balance date")}
            type="date"
            defaultValue={today()}
          />

          <button className="primary form-end" disabled={busy}>
            {busy ? t("Working...") : t("Save account")}
          </button>
        </form>
      </Dialog>

      {/* Update Current Balance Dialog */}
      <Dialog
        open={editingBalance !== null}
        title={t("Update balance")}
        description={t("This balance is information you provide. PorerHishab does not verify it against your bank.")}
        busy={busy}
        onClose={() => {
          setEditingBalance(null);
          setError(null);
        }}
      >
        {error && <ErrorNotice message={error} />}
        {editingBalance && (
          <form className="form-grid" onSubmit={handleUpdateBalance}>
            <Field
              name="current_balance"
              label={`${t("Current balance")} (${editingBalance.currency})`}
              type="number"
              step="0.01"
              required
              defaultValue={editingBalance.current_balance ?? ""}
            />

            <label className="field">
              <span>{t("Balance source")}</span>
              <select name="balance_source" defaultValue={editingBalance.balance_source || "manual"}>
                <option value="manual">{t("Manual")}</option>
                <option value="statement">{t("Statement")}</option>
                <option value="app">{t("Mobile app")}</option>
              </select>
            </label>

            <Field
              name="balance_as_of"
              label={t("Balance as of")}
              type="date"
              required
              defaultValue={
                editingBalance.balance_as_of
                  ? editingBalance.balance_as_of.slice(0, 10)
                  : today()
              }
            />

            <button className="primary form-end" disabled={busy}>
              {busy ? t("Working...") : t("Save balance")}
            </button>
          </form>
        )}
      </Dialog>

      {/* Update Opening Balance Dialog */}
      <Dialog
        open={editingOpening !== null}
        title={t("Update opening balance")}
        description={t("A known opening balance and transaction history are required to derive this value.")}
        busy={busy}
        onClose={() => {
          setEditingOpening(null);
          setError(null);
        }}
      >
        {error && <ErrorNotice message={error} />}
        {editingOpening && (
          <form className="form-grid" onSubmit={handleUpdateOpening}>
            <Field
              name="opening_balance"
              label={`${t("Opening balance")} (${editingOpening.currency})`}
              type="number"
              step="0.01"
              required
              defaultValue={editingOpening.opening_balance ?? ""}
            />

            <Field
              name="opening_balance_date"
              label={t("Opening balance date")}
              type="date"
              required
              defaultValue={editingOpening.opening_balance_date || today()}
            />

            <button className="primary form-end" disabled={busy}>
              {busy ? t("Working...") : t("Save balance")}
            </button>
          </form>
        )}
      </Dialog>
    </>
  );
}
