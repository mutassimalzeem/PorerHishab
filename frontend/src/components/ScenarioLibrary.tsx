import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiSchemas } from "../generated/api";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useLanguage } from "../lib/useLanguage";
import { digits, t, uiLabel } from "../lib/locale";
import { date, errorMessage } from "../lib/format";
import { Dialog } from "./Dialog";
import { ErrorNotice, ResourceView, Section } from "./ui";
type Scenario = ApiSchemas["ScenarioRead"];
export function ScenarioLibrary({
  revision,
  selectedId,
  disabled,
  onOpen,
  onChange,
  onRefresh,
}: {
  revision: number;
  selectedId?: number;
  disabled: boolean;
  onOpen: (id: string) => void;
  onChange: (s: Scenario) => void;
  onRefresh: () => void;
}) {
  useLanguage();
  const [status, setStatus] = useState("saved");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Scenario | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const library = useResource(
    useCallback(
      () => api.scenarioLibrary(status, search, offset),
      [status, search, offset],
    ),
    revision,
  );
  const renameButtons = useRef(new Map<number, HTMLButtonElement>());
  const restoreFocus = useRef<number | null>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!library.loading && library.data && restoreFocus.current !== null) {
      (
        renameButtons.current.get(restoreFocus.current) || searchInput.current
      )?.focus();
      restoreFocus.current = null;
    }
  }, [library.data, library.loading]);
  const locked = disabled || busy;
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onRefresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Section title={t("Scenario library")}>
      <p>
        {t(
          "Assumptions are hypothetical. Real financial records remain unchanged.",
        )}
      </p>
      {error && <ErrorNotice message={error} />}
      <div
        className="form-actions"
        role="group"
        aria-label={t("Scenario library")}
      >
        {(
          [
            ["saved", "Saved"],
            ["draft", "Drafts"],
            ["archived", "Archived"],
          ] as const
        ).map(([value, label]) => (
          <button
            type="button"
            className="button secondary"
            key={value}
            aria-pressed={status === value}
            disabled={locked}
            onClick={() => {
              setStatus(value);
              setOffset(0);
            }}
          >
            {t(label)}
          </button>
        ))}
      </div>
      <label className="field">
        {t("Search scenarios")}
        <input
          ref={searchInput}
          type="search"
          value={search}
          maxLength={120}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          disabled={locked}
        />
      </label>
      <p aria-live="polite">
        {t("Selected scenarios")}: {digits(picked.length)} / {digits(5)}
      </p>
      {picked.length >= 2 ? (
        <Link
          className="button secondary"
          to={`/scenarios/compare?ids=${picked.join(",")}`}
        >
          {t("Compare selected")}
        </Link>
      ) : (
        <p>{t("Select two to five scenarios.")}</p>
      )}
      <ResourceView resource={library}>
        {(page) => (
          <>
            <label className="field">
              {t("Choose scenario")}
              <select
                value={
                  page.items.some((s) => s.id === selectedId) ? selectedId : ""
                }
                disabled={locked}
                onChange={(e) => onOpen(e.target.value)}
              >
                <option value="">{t("Choose scenario")}</option>
                {page.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} / {uiLabel(s.status)}
                  </option>
                ))}
              </select>
            </label>
            {page.items.length === 0 && <p>{t("No scenarios yet")}</p>}
            <div className="scenario-library-grid">
              {page.items.map((s) => (
                <article
                  className="scenario-card"
                  key={s.id}
                  aria-label={s.name}
                >
                  <p className="eyebrow">
                    {t("WHAT-IF SCENARIO")} / {uiLabel(s.status)}
                  </p>
                  <h3>{s.name}</h3>
                  {s.description && <p>{s.description}</p>}
                  <p>
                    {t("Changes")}: {digits(s.changes.length)} / {t("Updated")}:{" "}
                    {date(s.updated_at)}
                  </p>
                  <p>
                    {t("Result status")}: {uiLabel(s.result_state || "missing")}
                  </p>
                  <label>
                    <input
                      type="checkbox"
                      aria-label={`${t("Select for comparison")}: ${s.name}`}
                      checked={picked.includes(s.id)}
                      disabled={
                        locked || (!picked.includes(s.id) && picked.length >= 5)
                      }
                      onChange={(e) =>
                        setPicked((v) =>
                          e.target.checked
                            ? [...v, s.id]
                            : v.filter((id) => id !== s.id),
                        )
                      }
                    />
                    {t("Select for comparison")}
                  </label>
                  <div className="form-actions">
                    <button
                      type="button"
                      className="button secondary"
                      disabled={locked}
                      onClick={() => onOpen(String(s.id))}
                    >
                      {t("Open")}
                    </button>
                    {s.status !== "archived" && (
                      <>
                        <button
                          type="button"
                          className="text-button"
                          disabled={locked}
                          ref={(node) => {
                            if (node) renameButtons.current.set(s.id, node);
                            else renameButtons.current.delete(s.id);
                          }}
                          onClick={() => {
                            setEditing(s);
                            setName(s.name);
                            setDescription(s.description);
                          }}
                        >
                          {t("Rename")}
                        </button>
                        <button
                          type="button"
                          className="text-button"
                          aria-label={`${t("Archive scenario")}: ${s.name}`}
                          disabled={locked}
                          onClick={() =>
                            void act(async () => {
                              onChange(await api.archiveScenario(s.id));
                            })
                          }
                        >
                          {t("Archive scenario")}
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      className="text-button"
                      disabled={locked}
                      onClick={() =>
                        void act(async () => {
                          const copy = await api.duplicateScenario(s.id);
                          setStatus("draft");
                          setOffset(0);
                          onOpen(String(copy.id));
                        })
                      }
                    >
                      {t("Duplicate")}
                    </button>
                    {s.status === "archived" && (
                      <button
                        type="button"
                        className="button secondary"
                        disabled={locked}
                        onClick={() =>
                          void act(async () => {
                            onChange(await api.restoreScenario(s.id));
                          })
                        }
                      >
                        {t("Restore")}
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                disabled={locked || offset === 0}
                onClick={() => setOffset((v) => Math.max(0, v - page.limit))}
              >
                {t("Previous")}
              </button>
              <span>
                {digits(page.total)} {t("Scenarios")}
              </span>
              <button
                type="button"
                className="button secondary"
                disabled={locked || offset + page.limit >= page.total}
                onClick={() => setOffset((v) => v + page.limit)}
              >
                {t("Next")}
              </button>
            </div>
          </>
        )}
      </ResourceView>
      <Dialog
        open={editing !== null}
        title={t("Rename")}
        busy={busy}
        onClose={() => setEditing(null)}
      >
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            if (editing)
              void act(async () => {
                onChange(
                  await api.renameScenario(editing.id, { name, description }),
                );
                restoreFocus.current = editing.id;
                setEditing(null);
              });
          }}
        >
          <label className="field">
            {t("Scenario name")}
            <input
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={busy}
            />
          </label>
          <label className="field">
            {t("Scenario description")}
            <textarea
              maxLength={1000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={busy}
            />
          </label>
          <button className="button" disabled={busy || !name.trim()}>
            {t("Save metadata")}
          </button>
        </form>
      </Dialog>
    </Section>
  );
}
