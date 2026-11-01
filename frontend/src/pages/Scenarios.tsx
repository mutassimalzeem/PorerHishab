import { ScenarioLibrary } from "../components/ScenarioLibrary";
import { useCallback, useRef, useState } from "react";
import type { ApiSchemas } from "../generated/api";
import { request } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useLanguage } from "../lib/useLanguage";
import { date, errorMessage, today } from "../lib/format";
import { digits, uiLabel } from "../lib/locale";
import {
  ErrorNotice,
  PageHeading,
  ResourceView,
  Section,
} from "../components/ui";

type Change = ApiSchemas["ScenarioChange-Input"];
type Result = ApiSchemas["ScenarioResult"];
type Scenario = ApiSchemas["ScenarioRead"];
const types: Change["change_type"][] = [
  "income_adjustment",
  "recurring_expense_adjustment",
  "one_time_expense",
  "one_time_income",
  "savings_contribution_adjustment",
  "goal_target_date_adjustment",
  "goal_target_amount_adjustment",
  "goal_commitment_adjustment",
];
const send = <T,>(path: string, body: unknown = {}) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export function Scenarios() {
  useLanguage();
  const label = uiLabel;
  const [revision, setRevision] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const baseline = useResource(
    useCallback(
      () =>
        request<Result>(
          `/finance/scenarios/baseline?schedules_confirmed=${confirmed}`,
        ),
      [confirmed],
    ),
    revision,
  );
  const [selected, setSelected] = useState<Scenario | null>(null);
  const [changes, setChanges] = useState<Change[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<Change["change_type"]>(
    "recurring_expense_adjustment",
  );
  const [amount, setAmount] = useState("");
  const [effective, setEffective] = useState(today());
  const [until, setUntil] = useState("");
  const [goal, setGoal] = useState("");
  const [deadline, setDeadline] = useState("");
  const [note, setNote] = useState("");
  const [horizon, setHorizon] = useState("120");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const flight = useRef(0);
  const retryKey = useRef<{ signature: string; key: string } | null>(null);
  const recurring = [
    "income_adjustment",
    "recurring_expense_adjustment",
    "savings_contribution_adjustment",
  ].includes(kind);
  const goalChange = kind.startsWith("goal_");
  const frozen = !selected || selected.status === "archived";
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function choose(id: string) {
    const ticket = ++flight.current;
    setSelected(null);
    setResult(null);
    setChanges([]);
    retryKey.current = null;
    if (!id) return;
    await act(async () => {
      const scenario = await request<Scenario>(`/finance/scenarios/${id}`);
      if (ticket !== flight.current) return;
      setSelected(scenario);
      setChanges(scenario.changes);
      try {
        const latest = await request<Result>(`/finance/scenarios/${id}/result`);
        if (ticket === flight.current) setResult(latest);
      } catch (e) {
        if (!(e instanceof Error) || !("status" in e) || e.status !== 404)
          throw e;
      }
    });
  }
  async function run() {
    if (!selected) return;
    await act(async () => {
      let scenario = selected;
      if (JSON.stringify(changes) !== JSON.stringify(selected.changes)) {
        scenario = await send<Scenario>(
          `/finance/scenarios/${selected.id}/changes`,
          { changes },
        );
        setSelected(scenario);
        setChanges(scenario.changes);
      }
      const signature = JSON.stringify([
        scenario.id,
        scenario.revision,
        confirmed,
        horizon,
      ]);
      if (retryKey.current?.signature !== signature)
        retryKey.current = { signature, key: crypto.randomUUID() };
      setResult(
        await send<Result>(`/finance/scenarios/${scenario.id}/simulate`, {
          idempotency_key: retryKey.current.key,
          schedules_confirmed: confirmed,
          horizon_days: Number(horizon),
        }),
      );
      setRevision((v) => v + 1);
    });
  }
  function table(value: Result, currentOnly = false) {
    return (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{label("Metric")}</th>
              <th>{label("Baseline")}</th>
              {!currentOnly && (
                <>
                  <th>{label("Scenario")}</th>
                  <th>{label("Difference")}</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {value.comparisons
              .filter((m) => !m.metric.startsWith("goal_"))
              .map((m) => (
                <tr key={m.metric}>
                  <th scope="row">{label(m.metric)}</th>
                  <td>
                    {m.baseline_value == null
                      ? label("Unavailable")
                      : digits(m.baseline_value)}
                  </td>
                  {!currentOnly && (
                    <>
                      <td>
                        {m.scenario_value == null
                          ? label(m.status)
                          : digits(m.scenario_value)}
                      </td>
                      <td>
                        {m.absolute_delta == null
                          ? label("Unavailable")
                          : `${digits(m.absolute_delta)} (${label(m.direction)})`}
                        {m.percentage_delta != null &&
                          ` / ${digits(m.percentage_delta)}%`}
                        {m.reason && (
                          <details>
                            <summary>{label("Limitations")}</summary>
                            <p lang="en">{m.reason}</p>
                          </details>
                        )}
                      </td>
                    </>
                  )}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <>
      <PageHeading
        title={label("What if?")}
        description={label(
          "Test assumptions without changing your real finances.",
        )}
      />
      {error && <ErrorNotice message={error} />}
      <Section title={label("YOUR CURRENT FINANCES")}>
        <p className="eyebrow">{label("REAL FINANCIAL DATA")}</p>
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
            disabled={busy}
          />
          {label("I have recorded all known expense schedules")}
        </label>
        <ResourceView resource={baseline}>{(b) => table(b, true)}</ResourceView>
      </Section>
      <Section title={label("Create scenario")}>
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              const s = await send<Scenario>("/finance/scenarios", {
                name,
                description,
              });
              ++flight.current;
              setSelected(s);
              setChanges([]);
              setResult(null);
              setName("");
              setDescription("");
              setRevision((v) => v + 1);
            });
          }}
        >
          <label>
            {label("Name")}
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={120}
              disabled={busy}
            />
          </label>
          <label>
            {label("Description")}
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={1000}
              disabled={busy}
            />
          </label>
          <button className="button" disabled={busy}>
            {label("Create scenario")}
          </button>
        </form>
      </Section>
      <ScenarioLibrary
        revision={revision}
        selectedId={selected?.id}
        disabled={busy}
        onOpen={(id) => void choose(id)}
        onChange={(s) => {
          if (s.id === selected?.id) setSelected(s);
        }}
        onRefresh={() => setRevision((v) => v + 1)}
      />
      {selected && (
        <Section
          title={`${label("WHAT IF \u2014 NOT REAL DATA")} / ${selected.name}`}
        >
          <p>
            {label(
              "Changes are signed deltas; goal amounts and commitments replace the selected value.",
            )}
          </p>
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              setChanges((v) => [
                ...v,
                {
                  change_type: kind,
                  amount:
                    kind === "goal_target_date_adjustment" ? null : amount,
                  currency: "BDT",
                  effective_date: effective,
                  end_date: recurring && until ? until : null,
                  frequency: recurring ? "monthly" : null,
                  target_id: goalChange ? Number(goal) : null,
                  target_date:
                    kind === "goal_target_date_adjustment" ? deadline : null,
                  description: note,
                },
              ]);
              setAmount("");
              setNote("");
            }}
          >
            <label>
              {label("Change type")}
              <select
                value={kind}
                onChange={(e) =>
                  setKind(e.target.value as Change["change_type"])
                }
                disabled={frozen || busy}
              >
                {types.map((type) => (
                  <option key={type} value={type}>
                    {label(type)}
                  </option>
                ))}
              </select>
            </label>
            {kind !== "goal_target_date_adjustment" && (
              <label>
                {label("Amount (BDT)")}
                <input
                  type="number"
                  step="0.01"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                  disabled={frozen || busy}
                />
              </label>
            )}
            <label>
              {label("Effective date")}
              <input
                type="date"
                value={effective}
                onChange={(e) => setEffective(e.target.value)}
                required
                disabled={frozen || busy}
              />
            </label>
            {recurring && (
              <label>
                {label("End date (optional)")}
                <input
                  type="date"
                  value={until}
                  min={effective}
                  onChange={(e) => setUntil(e.target.value)}
                  disabled={frozen || busy}
                />
              </label>
            )}
            {goalChange && (
              <label>
                {label("Goal")}
                <select
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  required
                  disabled={frozen || busy}
                >
                  <option value="">{label("Goal")}</option>
                  {baseline.data?.baseline_goals.map((g) => (
                    <option key={String(g.goal_id)} value={String(g.goal_id)}>
                      {String(g.name)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {kind === "goal_target_date_adjustment" && (
              <label>
                {label("Target date")}
                <input
                  type="date"
                  value={deadline}
                  min={effective}
                  onChange={(e) => setDeadline(e.target.value)}
                  required
                  disabled={frozen || busy}
                />
              </label>
            )}
            <label>
              {label("Description")}
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={500}
                disabled={frozen || busy}
              />
            </label>
            <button
              className="button secondary"
              disabled={frozen || busy || changes.length >= 50}
            >
              {label("Add change")}
            </button>
          </form>
          <h3>{label("Hypothetical changes")}</h3>
          {changes.length === 0 ? (
            <p>{label("No changes yet")}</p>
          ) : (
            <ul>
              {changes.map((c, i) => (
                <li key={i}>
                  {label(c.change_type)} {" / "}
                  {c.target_date ||
                    (c.percentage != null
                      ? `${digits(c.percentage)}%`
                      : digits(c.amount || ""))}{" "}
                  {" / "}
                  {date(c.effective_date)}{" "}
                  {c.end_date && `to ${date(c.end_date)}`} {c.description}
                  <button
                    className="text-button"
                    disabled={frozen || busy}
                    onClick={() =>
                      setChanges((v) => v.filter((_, j) => i !== j))
                    }
                  >
                    {label("Remove")}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <label>
            {label("Horizon (days, 1\u2013366)")}
            <input
              type="number"
              min={1}
              max={366}
              value={horizon}
              onChange={(e) => setHorizon(e.target.value)}
              disabled={busy || frozen}
            />
          </label>
          <div className="form-actions">
            <button
              className="button"
              disabled={frozen || busy || !horizon}
              onClick={() => void run()}
            >
              {label(busy ? "Working\u2026" : "Run scenario")}
            </button>
            <button
              className="button secondary"
              disabled={frozen || busy}
              onClick={() =>
                void act(async () => {
                  let s = selected;
                  if (JSON.stringify(changes) !== JSON.stringify(s.changes))
                    s = await send<Scenario>(
                      `/finance/scenarios/${s.id}/changes`,
                      { changes },
                    );
                  const saved = await send<Scenario>(
                    `/finance/scenarios/${s.id}/save`,
                  );
                  setSelected(saved);
                  setChanges(saved.changes);
                  setRevision((v) => v + 1);
                })
              }
            >
              {label("Save scenario")}
            </button>
            <button
              className="text-button"
              disabled={frozen || busy}
              onClick={() =>
                void act(async () => {
                  setSelected(
                    await send<Scenario>(
                      `/finance/scenarios/${selected.id}/archive`,
                    ),
                  );
                  setRevision((v) => v + 1);
                })
              }
            >
              {label("Archive scenario")}
            </button>
          </div>
        </Section>
      )}
      {result && (
        <Section title={label("WHAT IF \u2014 NOT REAL DATA")}>
          <p role="status">
            {label(
              "This is a scenario based on the assumptions you selected, not a guaranteed future outcome.",
            )}
          </p>
          <p>
            {label(
              "Result uses the saved assumptions below. Run again after editing.",
            )}{" "}
            {date(result.baseline_snapshot_date)} / {date(result.horizon_end)}
          </p>
          {table(result)}
          {result.affordability && (
            <p>
              {label("Affordability")}: {label(result.affordability)}
            </p>
          )}
          <h3>{label("Goal comparison")}</h3>
          {result.scenario_goals.map((g, i) => (
            <article key={String(g.goal_id)}>
              <h4>{String(g.name)}</h4>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{label("Metric")}</th>
                      <th>{label("Baseline")}</th>
                      <th>{label("Scenario")}</th>
                      <th>{label("Difference")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ["target_amount", "Target amount"],
                        ["target_date", "Target date"],
                        ["required_contribution", "Required contribution"],
                        [
                          "projected_contribution_capacity",
                          "Contribution capacity",
                        ],
                        ["accepted_commitment", "Accepted commitment"],
                        ["feasibility", "Feasibility"],
                      ] as const
                    ).map(([key, title]) => {
                      const before = result.baseline_goals[i]?.[key];
                      const after = g[key];
                      const comparison = result.comparisons.find(
                        (m) =>
                          m.metric ===
                          `goal_${g.goal_id}_${key === "target_date" ? "days_to_target" : key}`,
                      );
                      const show = (v: unknown) =>
                        v == null
                          ? label("Unavailable")
                          : key === "feasibility"
                            ? uiLabel(String(v))
                            : digits(String(v));
                      return (
                        <tr key={key}>
                          <th scope="row">{label(title)}</th>
                          <td>{show(before)}</td>
                          <td>{show(after)}</td>
                          <td>
                            {comparison?.absolute_delta == null
                              ? label("Unavailable")
                              : digits(comparison.absolute_delta)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </article>
          ))}
          <h3>{label("Assumptions")}</h3>
          <ul>
            {result.assumptions.map((c, i) => (
              <li key={i}>
                {label(c.change_type)} {" / "}
                {c.target_date ||
                  (c.percentage != null
                    ? `${digits(c.percentage)}%`
                    : digits(c.amount || ""))}{" "}
                {" / "}
                {date(c.effective_date)}{" "}
                {c.end_date && `to ${date(c.end_date)}`} {c.description}
              </li>
            ))}
          </ul>
          <h3>{label("Limitations")}</h3>
          <p>
            {label(
              "Monthly history is an estimate. Goals use protected capacity and compete for it. Future income is uncertain; monthly runway cannot give an exact depletion date. Health cannot be simulated.",
            )}
          </p>
          <details>
            <summary>{label("See recorded evidence in English")}</summary>
            <ul lang="en">
              {result.limitations.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
            <small>
              {result.calculation_version} {" / "}
              {result.baseline_snapshot_reference}
            </small>
          </details>
        </Section>
      )}
    </>
  );
}
