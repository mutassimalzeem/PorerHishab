import { useCallback, useState } from "react";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useLanguage } from "../lib/useLanguage";
import { t, uiLabel, digits } from "../lib/locale";
import { date, errorMessage } from "../lib/format";
import { Amount, ErrorNotice, ResourceView } from "./ui";

const cents = (value: string) =>
  BigInt(
    (value.split(".")[0] || "0") + (value.split(".")[1] || "").padEnd(2, "0"),
  );

export function ObligationMatches({
  itemId,
  onChange,
}: {
  itemId: number;
  onChange: () => void;
}) {
  useLanguage();
  const [open, setOpen] = useState(false);
  return (
    <div className="obligation-matches">
      <button aria-expanded={open} onClick={() => setOpen(!open)}>
        {t("Review transaction matches")}
      </button>
      {open && <MatchDetails itemId={itemId} onChange={onChange} />}
    </div>
  );
}
function MatchDetails({
  itemId,
  onChange,
}: {
  itemId: number;
  onChange: () => void;
}) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resource = useResource(
    useCallback(() => api.obligationMatches(itemId), [itemId]),
    revision,
  );
  async function change(
    transactionId: number,
    action: "confirm" | "settle" | "remove",
  ) {
    setBusy(true);
    setError(null);
    try {
      if (action === "remove")
        await api.removeAllocation(itemId, transactionId);
      else
        await api.confirmAllocation(itemId, transactionId, action === "settle");
      setRevision((v) => v + 1);
      onChange();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="reconciliation-detail">
      {error && <ErrorNotice message={error} />}
      <ResourceView
        resource={resource}
        label={t("Reading transaction matches...")}
      >
        {(r) => (
          <>
            <p>
              <strong>{uiLabel(r.status)}</strong> &middot; {uiLabel(r.timing)}
            </p>
            <p>
              {t("Allocated")} <Amount value={r.allocated_amount} /> /{" "}
              <Amount value={r.original_amount} /> &middot; {t("Remaining")}{" "}
              <Amount value={r.remaining_amount} />
            </p>
            <progress
              aria-label={t("Allocated")}
              max={10000}
              value={Number(
                (cents(r.allocated_amount) * 10000n) / cents(r.original_amount),
              )}
            />
            <p className="source">
              {t("Principal only; separate fees are excluded.")}
            </p>
            <p className="source">
              {t(
                "Suggestions require review. Amount and date alone do not prove payment.",
              )}
            </p>
            <p className="source">
              {t("Date tolerance (days)")}: {digits(r.date_tolerance_days)}{" "}
              &middot; {t("Amount tolerance")}:{" "}
              <Amount value={r.amount_tolerance} />
            </p>
            {r.ambiguous && (
              <p className="callout">
                {t(
                  "Several transactions may match. Review each before confirming.",
                )}
              </p>
            )}
            {r.allocations
              .filter((a) => a.active)
              .map((a) => (
                <div key={a.id} className="reconciliation-entry">
                  <span>
                    {t("Confirmed transaction")} #{digits(a.transaction_id)}{" "}
                    &middot; <Amount value={a.amount} />
                  </span>
                  <button
                    disabled={busy}
                    onClick={() => change(a.transaction_id, "remove")}
                  >
                    {t("Remove allocation")}
                  </button>
                  {cents(r.remaining_amount) === 0n && r.status !== "paid" && (
                    <button
                      disabled={busy}
                      onClick={() => change(a.transaction_id, "settle")}
                    >
                      {t("Confirm fully paid")}
                    </button>
                  )}
                </div>
              ))}
            {!r.candidates.length && (
              <p>{t("No candidate transactions in this window.")}</p>
            )}
            {r.candidates.map((c) => (
              <div key={c.transaction_id} className="reconciliation-entry">
                <p>
                  #{digits(c.transaction_id)} &middot; {date(c.date)} &middot;{" "}
                  <Amount value={c.amount} /> &middot;{" "}
                  {c.merchant || c.description}
                </p>
                <p className="source">
                  {uiLabel(c.amount_signal)} &middot; {t("Days from due date")}:{" "}
                  {digits(c.date_distance_days)} &middot;{" "}
                  {t("Amount difference")}:{" "}
                  <Amount value={c.amount_difference} /> &middot;{" "}
                  {t("Confidence")}: {uiLabel(c.confidence)}
                </p>
                <p className="source">
                  {t("Category evidence")}:{" "}
                  {uiLabel(c.category_match ? "yes" : "no")} &middot;{" "}
                  {t("Description evidence")}:{" "}
                  {uiLabel(c.text_overlap ? "yes" : "no")}
                </p>
                {cents(c.amount) > cents(r.remaining_amount) && (
                  <p className="callout">
                    {t(
                      "This transaction exceeds the remaining amount and cannot be allocated.",
                    )}
                  </p>
                )}
                <button
                  disabled={
                    busy ||
                    (c.amount_signal === "within_tolerance" &&
                      cents(c.amount) > cents(r.remaining_amount))
                  }
                  onClick={() => change(c.transaction_id, "confirm")}
                >
                  {t("Confirm allocation")}
                </button>
                {cents(c.amount) === cents(r.remaining_amount) && (
                  <button
                    disabled={busy}
                    onClick={() => change(c.transaction_id, "settle")}
                  >
                    {t("Confirm allocation and mark paid")}
                  </button>
                )}
              </div>
            ))}
          </>
        )}
      </ResourceView>
    </div>
  );
}
