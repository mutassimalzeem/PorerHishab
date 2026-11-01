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
const scenarioCopy: Record<string, string> = {
  "Accepted commitment":
    "\u0997\u09c3\u09b9\u09c0\u09a4 \u09aa\u09cd\u09b0\u09a4\u09bf\u09b6\u09cd\u09b0\u09c1\u09a4\u09bf",
  Feasibility: "\u09b8\u09ae\u09cd\u09ad\u09be\u09ac\u09cd\u09af\u09a4\u09be",
  Scenarios:
    "\u09ac\u09bf\u0995\u09b2\u09cd\u09aa \u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be",
  "What if?": "\u09af\u09a6\u09bf \u098f\u09ae\u09a8 \u09b9\u09af\u09bc?",
  "Test assumptions without changing your real finances.":
    "\u09aa\u09cd\u09b0\u0995\u09c3\u09a4 \u0986\u09b0\u09cd\u09a5\u09bf\u0995 \u09a4\u09a5\u09cd\u09af \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8 \u09a8\u09be \u0995\u09b0\u09c7 \u09ac\u09bf\u0995\u09b2\u09cd\u09aa \u09af\u09be\u099a\u09be\u0987 \u0995\u09b0\u09c1\u09a8\u0964",
  "YOUR CURRENT FINANCES":
    "\u0986\u09aa\u09a8\u09be\u09b0 \u09ac\u09b0\u09cd\u09a4\u09ae\u09be\u09a8 \u0986\u09b0\u09cd\u09a5\u09bf\u0995 \u0985\u09ac\u09b8\u09cd\u09a5\u09be",
  "WHAT IF \u2014 NOT REAL DATA":
    "\u09af\u09a6\u09bf \u098f\u09ae\u09a8 \u09b9\u09af\u09bc \u2014 \u09aa\u09cd\u09b0\u0995\u09c3\u09a4 \u09a4\u09a5\u09cd\u09af \u09a8\u09af\u09bc",
  Name: "\u09a8\u09be\u09ae",
  Description: "\u09ac\u09bf\u09ac\u09b0\u09a3",
  "Create scenario":
    "\u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be \u09a4\u09c8\u09b0\u09bf \u0995\u09b0\u09c1\u09a8",
  "Saved scenarios":
    "\u09b8\u0982\u09b0\u0995\u09cd\u09b7\u09bf\u09a4 \u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be",
  "Choose scenario":
    "\u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be \u09ac\u09c7\u099b\u09c7 \u09a8\u09bf\u09a8",
  "Hypothetical changes":
    "\u0995\u09be\u09b2\u09cd\u09aa\u09a8\u09bf\u0995 \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8",
  "Change type":
    "\u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8\u09c7\u09b0 \u09a7\u09b0\u09a8",
  "Amount (BDT)":
    "\u09aa\u09b0\u09bf\u09ae\u09be\u09a3 (\u099f\u09be\u0995\u09be)",
  "Effective date":
    "\u0995\u09be\u09b0\u09cd\u09af\u0995\u09b0 \u09a4\u09be\u09b0\u09bf\u0996",
  "End date (optional)":
    "\u09b6\u09c7\u09b7 \u09a4\u09be\u09b0\u09bf\u0996 (\u0990\u099a\u09cd\u099b\u09bf\u0995)",
  Goal: "\u09b2\u0995\u09cd\u09b7\u09cd\u09af",
  "Target date":
    "\u09b2\u0995\u09cd\u09b7\u09cd\u09af\u09c7\u09b0 \u09a4\u09be\u09b0\u09bf\u0996",
  "Add change":
    "\u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8 \u09af\u09cb\u0997 \u0995\u09b0\u09c1\u09a8",
  Remove: "\u09b8\u09b0\u09be\u09a8",
  "Run scenario":
    "\u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be \u09af\u09be\u099a\u09be\u0987 \u0995\u09b0\u09c1\u09a8",
  "Save scenario":
    "\u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be \u09b8\u0982\u09b0\u0995\u09cd\u09b7\u09a3 \u0995\u09b0\u09c1\u09a8",
  "Archive scenario":
    "\u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be \u0986\u09b0\u09cd\u0995\u09be\u0987\u09ad \u0995\u09b0\u09c1\u09a8",
  "I have recorded all known expense schedules":
    "\u0986\u09ae\u09bf \u09b8\u09ac \u099c\u09be\u09a8\u09be \u09ac\u09cd\u09af\u09af\u09bc\u09c7\u09b0 \u09b8\u09ae\u09af\u09bc\u09b8\u09c2\u099a\u09bf \u09a8\u09a5\u09bf\u09ad\u09c1\u0995\u09cd\u09a4 \u0995\u09b0\u09c7\u099b\u09bf",
  "Horizon (days, 1\u2013366)":
    "\u09b8\u09ae\u09af\u09bc\u09b8\u09c0\u09ae\u09be (\u09a6\u09bf\u09a8, \u09e7\u2013\u09e9\u09ec\u09ec)",
  Metric: "\u09b8\u09c2\u099a\u0995",
  Baseline: "\u09ac\u09b0\u09cd\u09a4\u09ae\u09be\u09a8",
  Scenario: "\u09ac\u09bf\u0995\u09b2\u09cd\u09aa",
  Difference: "\u09aa\u09be\u09b0\u09cd\u09a5\u0995\u09cd\u09af",
  Assumptions: "\u0985\u09a8\u09c1\u09ae\u09be\u09a8\u09b8\u09ae\u09c2\u09b9",
  Limitations: "\u09b8\u09c0\u09ae\u09be\u09ac\u09a6\u09cd\u09a7\u09a4\u09be",
  "Goal comparison":
    "\u09b2\u0995\u09cd\u09b7\u09cd\u09af\u09c7\u09b0 \u09a4\u09c1\u09b2\u09a8\u09be",
  "Working\u2026": "\u0995\u09be\u099c \u099a\u09b2\u099b\u09c7\u2026",
  "Changes are signed deltas; goal amounts and commitments replace the selected value.":
    "\u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8\u09c7 \u09a7\u09a8\u09be\u09a4\u09cd\u09ae\u0995 \u09ac\u09be \u098b\u09a3\u09be\u09a4\u09cd\u09ae\u0995 \u09aa\u09be\u09b0\u09cd\u09a5\u0995\u09cd\u09af \u09a6\u09bf\u09a8; \u09b2\u0995\u09cd\u09b7\u09cd\u09af \u0993 \u09aa\u09cd\u09b0\u09a4\u09bf\u09b6\u09cd\u09b0\u09c1\u09a4\u09bf\u09b0 \u09aa\u09b0\u09bf\u09ae\u09be\u09a3 \u09a8\u09bf\u09b0\u09cd\u09ac\u09be\u099a\u09bf\u09a4 \u09ae\u09be\u09a8 \u09aa\u09cd\u09b0\u09a4\u09bf\u09b8\u09cd\u09a5\u09be\u09aa\u09a8 \u0995\u09b0\u09c7\u0964",
  "This is a scenario based on the assumptions you selected, not a guaranteed future outcome.":
    "\u098f\u099f\u09bf \u0986\u09aa\u09a8\u09be\u09b0 \u09a8\u09bf\u09b0\u09cd\u09ac\u09be\u099a\u09bf\u09a4 \u0985\u09a8\u09c1\u09ae\u09be\u09a8\u09c7\u09b0 \u09ad\u09bf\u09a4\u09cd\u09a4\u09bf\u09a4\u09c7 \u098f\u0995\u099f\u09bf \u09ac\u09bf\u0995\u09b2\u09cd\u09aa \u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be, \u09a8\u09bf\u09b6\u09cd\u099a\u09bf\u09a4 \u09ad\u09ac\u09bf\u09b7\u09cd\u09af\u09ce \u09ab\u09b2\u09be\u09ab\u09b2 \u09a8\u09af\u09bc\u0964",
  "Result uses the saved assumptions below. Run again after editing.":
    "\u09ab\u09b2\u09be\u09ab\u09b2 \u09a8\u09bf\u099a\u09c7\u09b0 \u09b8\u0982\u09b0\u0995\u09cd\u09b7\u09bf\u09a4 \u0985\u09a8\u09c1\u09ae\u09be\u09a8\u09c7\u09b0 \u09ad\u09bf\u09a4\u09cd\u09a4\u09bf\u09a4\u09c7\u0964 \u09b8\u09ae\u09cd\u09aa\u09be\u09a6\u09a8\u09be\u09b0 \u09aa\u09b0\u09c7 \u0986\u09ac\u09be\u09b0 \u09af\u09be\u099a\u09be\u0987 \u0995\u09b0\u09c1\u09a8\u0964",
  Unavailable:
    "\u09a4\u09a5\u09cd\u09af \u0985\u09a8\u09c1\u09aa\u09b2\u09ac\u09cd\u09a7",
  "No changes yet":
    "\u098f\u0996\u09a8\u0993 \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8 \u09a8\u09c7\u0987",
  "No scenarios yet":
    "\u098f\u0996\u09a8\u0993 \u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be \u09a8\u09c7\u0987",
  "Required contribution":
    "\u09aa\u09cd\u09b0\u09af\u09bc\u09cb\u099c\u09a8\u09c0\u09af\u09bc \u0985\u09ac\u09a6\u09be\u09a8",
  "Contribution capacity":
    "\u0985\u09ac\u09a6\u09be\u09a8\u09c7\u09b0 \u09b8\u0995\u09cd\u09b7\u09ae\u09a4\u09be",
  Affordability:
    "\u0995\u09cd\u09b0\u09af\u09bc\u09b8\u0995\u09cd\u09b7\u09ae\u09a4\u09be",
  draft: "\u0996\u09b8\u09a1\u09bc\u09be",
  saved: "\u09b8\u0982\u09b0\u0995\u09cd\u09b7\u09bf\u09a4",
  archived: "\u0986\u09b0\u09cd\u0995\u09be\u0987\u09ad \u0995\u09b0\u09be",
  increased: "\u09ac\u09c7\u09a1\u09bc\u09c7\u099b\u09c7",
  decreased: "\u0995\u09ae\u09c7\u099b\u09c7",
  unchanged: "\u0985\u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09bf\u09a4",
  unknown: "\u0985\u099c\u09be\u09a8\u09be",
  income_adjustment:
    "\u09ae\u09be\u09b8\u09bf\u0995 \u0986\u09af\u09bc\u09c7\u09b0 \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8",
  recurring_expense_adjustment:
    "\u09ae\u09be\u09b8\u09bf\u0995 \u09ac\u09cd\u09af\u09af\u09bc\u09c7\u09b0 \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8",
  one_time_expense:
    "\u098f\u0995\u0995\u09be\u09b2\u09c0\u09a8 \u09ac\u09cd\u09af\u09af\u09bc",
  one_time_income:
    "\u098f\u0995\u0995\u09be\u09b2\u09c0\u09a8 \u0986\u09af\u09bc",
  savings_contribution_adjustment:
    "\u09ae\u09be\u09b8\u09bf\u0995 \u09b8\u099e\u09cd\u099a\u09af\u09bc\u09c7\u09b0 \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8",
  goal_target_date_adjustment:
    "\u09b2\u0995\u09cd\u09b7\u09cd\u09af\u09c7\u09b0 \u09a4\u09be\u09b0\u09bf\u0996 \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8",
  goal_target_amount_adjustment:
    "\u09b2\u0995\u09cd\u09b7\u09cd\u09af\u09c7\u09b0 \u09aa\u09b0\u09bf\u09ae\u09be\u09a3 \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8",
  goal_commitment_adjustment:
    "\u09b2\u0995\u09cd\u09b7\u09cd\u09af\u09c7\u09b0 \u09aa\u09cd\u09b0\u09a4\u09bf\u09b6\u09cd\u09b0\u09c1\u09a4\u09bf \u09aa\u09b0\u09bf\u09ac\u09b0\u09cd\u09a4\u09a8",
  monthly_income: "\u09ae\u09be\u09b8\u09bf\u0995 \u0986\u09af\u09bc",
  monthly_expenses:
    "\u09ae\u09be\u09b8\u09bf\u0995 \u09ac\u09cd\u09af\u09af\u09bc",
  monthly_obligations:
    "\u0986\u0997\u09be\u09ae\u09c0 \u09e9\u09e6 \u09a6\u09bf\u09a8\u09c7\u09b0 \u09a6\u09be\u09af\u09bc",
  monthly_savings_capacity:
    "\u09ae\u09be\u09b8\u09bf\u0995 \u09b8\u099e\u09cd\u099a\u09af\u09bc \u09b8\u0995\u09cd\u09b7\u09ae\u09a4\u09be",
  monthly_free_capacity:
    "\u09ae\u09be\u09b8\u09bf\u0995 \u0985\u09ac\u09b6\u09bf\u09b7\u09cd\u099f \u09b8\u0995\u09cd\u09b7\u09ae\u09a4\u09be",
  monthly_goal_commitments:
    "\u09ae\u09be\u09b8\u09bf\u0995 \u09b2\u0995\u09cd\u09b7\u09cd\u09af\u09c7\u09b0 \u09aa\u09cd\u09b0\u09a4\u09bf\u09b6\u09cd\u09b0\u09c1\u09a4\u09bf",
  monthly_additional_savings:
    "\u0985\u09a4\u09bf\u09b0\u09bf\u0995\u09cd\u09a4 \u09ae\u09be\u09b8\u09bf\u0995 \u09b8\u099e\u09cd\u099a\u09af\u09bc",
  trusted_available_cash:
    "\u09a8\u09bf\u09b0\u09cd\u09ad\u09b0\u09af\u09cb\u0997\u09cd\u09af \u09ac\u09b0\u09cd\u09a4\u09ae\u09be\u09a8 \u09a8\u0997\u09a6",
  projected_end_cash:
    "\u09b8\u09ae\u09af\u09bc\u09b8\u09c0\u09ae\u09be \u09b6\u09c7\u09b7\u09c7 \u0986\u09a8\u09c1\u09ae\u09be\u09a8\u09bf\u0995 \u09a8\u0997\u09a6",
  minimum_projected_cash:
    "\u0986\u09a8\u09c1\u09ae\u09be\u09a8\u09bf\u0995 \u09b8\u09b0\u09cd\u09ac\u09a8\u09bf\u09ae\u09cd\u09a8 \u09a8\u0997\u09a6",
  runway_months:
    "\u09a8\u0997\u09a6 \u09b8\u09cd\u09a5\u09be\u09af\u09bc\u09bf\u09a4\u09cd\u09ac\u09c7\u09b0 \u09ae\u09be\u09b8",
  financial_health:
    "\u0986\u09b0\u09cd\u09a5\u09bf\u0995 \u09b8\u09c1\u09b8\u09cd\u09a5\u09a4\u09be",
  affordable: "\u0995\u09cd\u09b0\u09af\u09bc \u09b8\u09ae\u09cd\u09ad\u09ac",
  affordable_with_adjustments:
    "\u09b8\u09ae\u09a8\u09cd\u09ac\u09af\u09bc\u09c7\u09b0 \u09ae\u09be\u09a7\u09cd\u09af\u09ae\u09c7 \u09b8\u09ae\u09cd\u09ad\u09ac",
  not_affordable:
    "\u0995\u09cd\u09b0\u09af\u09bc\u09b8\u0995\u09cd\u09b7\u09ae\u09a4\u09be\u09b0 \u09ac\u09be\u0987\u09b0\u09c7",
  insufficient_data:
    "\u0985\u09aa\u09b0\u09cd\u09af\u09be\u09aa\u09cd\u09a4 \u09a4\u09a5\u09cd\u09af",
  not_available_for_scenario:
    "\u09ac\u09bf\u0995\u09b2\u09cd\u09aa \u09aa\u09b0\u09bf\u0995\u09b2\u09cd\u09aa\u09a8\u09be\u09af\u09bc \u0985\u09a8\u09c1\u09aa\u09b2\u09ac\u09cd\u09a7",
  "See recorded evidence in English":
    "\u09a8\u09a5\u09bf\u09ad\u09c1\u0995\u09cd\u09a4 \u09aa\u09cd\u09b0\u09ae\u09be\u09a3 \u0987\u0982\u09b0\u09c7\u099c\u09bf\u09a4\u09c7 \u09a6\u09c7\u0996\u09c1\u09a8",
  "Monthly history is an estimate. Goals use protected capacity and compete for it. Future income is uncertain; monthly runway cannot give an exact depletion date. Health cannot be simulated.":
    "\u09ae\u09be\u09b8\u09bf\u0995 \u0987\u09a4\u09bf\u09b9\u09be\u09b8 \u098f\u0995\u099f\u09bf \u0985\u09a8\u09c1\u09ae\u09be\u09a8\u0964 \u09b2\u0995\u09cd\u09b7\u09cd\u09af\u0997\u09c1\u09b2\u09cb \u09b8\u0982\u09b0\u0995\u09cd\u09b7\u09bf\u09a4 \u09b8\u0995\u09cd\u09b7\u09ae\u09a4\u09be \u09ad\u09be\u0997 \u0995\u09b0\u09c7\u0964 \u09ad\u09ac\u09bf\u09b7\u09cd\u09af\u09ce \u0986\u09af\u09bc \u0985\u09a8\u09bf\u09b6\u09cd\u099a\u09bf\u09a4; \u09ae\u09be\u09b8\u09bf\u0995 \u09a8\u0997\u09a6 \u09ac\u09bf\u09b6\u09cd\u09b2\u09c7\u09b7\u09a3 \u09b8\u09a0\u09bf\u0995 \u09b6\u09c7\u09b7 \u09b9\u0993\u09af\u09bc\u09be\u09b0 \u09a4\u09be\u09b0\u09bf\u0996 \u09a6\u09c7\u09af\u09bc \u09a8\u09be\u0964 \u0986\u09b0\u09cd\u09a5\u09bf\u0995 \u09b8\u09c1\u09b8\u09cd\u09a5\u09a4\u09be \u098f\u0996\u09be\u09a8\u09c7 \u0997\u09a3\u09a8\u09be \u0995\u09b0\u09be \u09af\u09be\u09af\u09bc \u09a8\u09be\u0964",
};
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
  const { language } = useLanguage();
  const label = (s: string) =>
    language === "bn" ? scenarioCopy[s] || uiLabel(s) : s.replaceAll("_", " ");
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
  const listing = useResource(
    useCallback(() => request<Scenario[]>("/finance/scenarios"), []),
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
      <Section title={label("Saved scenarios")}>
        <ResourceView resource={listing}>
          {(rows) => (
            <label>
              {label("Choose scenario")}
              <select
                value={selected?.id || ""}
                disabled={busy}
                onChange={(e) => void choose(e.target.value)}
              >
                <option value="">
                  {label(rows.length ? "Choose scenario" : "No scenarios yet")}
                </option>
                {rows.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} / {label(s.status)}
                  </option>
                ))}
              </select>
            </label>
          )}
        </ResourceView>
      </Section>
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
