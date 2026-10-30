import { getLanguage, t, uiLabel } from "./locale";
import type {
  Answer,
  Intelligence,
  GoalUpdate,
  ScheduledUpdate,
  Cashflow,
  Decision,
  Goal,
  GoalCreate,
  GoalPlan,
  Monthly,
  Nudges,
  Page,
  Recommendations,
  Scheduled,
  ScheduledCreate,
  Summary,
  Tokens,
  Transaction,
  TransactionCreate,
  User,
  CSVUpload,
} from "../domain";
const base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
let tokens: Tokens | null = null;
let refreshFlight: Promise<boolean> | null = null;
let sessionVersion = 0;
export function setSession(value: Tokens | null) {
  tokens = value;
  sessionVersion += 1;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
function detail(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value))
    return value
      .map((v) =>
        typeof v === "object" && v && "msg" in v
          ? String(v.msg)
          : "Invalid input",
      )
      .join("; ");
  return "The request could not be completed. Please try again.";
}
async function refresh(): Promise<boolean> {
  if (!tokens?.refresh_token) return false;
  const version = sessionVersion;
  const previous = tokens;
  try {
    const response = await fetch(`${base}/refresh`, {
      method: "POST",
      body: new URLSearchParams({ refresh_token: previous.refresh_token! }),
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) return false;
    const next: Tokens = await response.json();
    if (version !== sessionVersion) return false;
    tokens = { ...previous, access_token: next.access_token };
    return true;
  } catch {
    return false;
  }
}
export async function request<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const version = sessionVersion;
  const headers = new Headers(init.headers);
  if (tokens) headers.set("Authorization", `Bearer ${tokens.access_token}`);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      ...init,
      headers,
      signal: init.signal ?? AbortSignal.timeout(30000),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      0,
      t(
        "Could not reach PorerHishab. Check your connection and that the API is running.",
      ),
    );
  }
  if (response.status === 401 && tokens && version === sessionVersion) {
    if (retry) {
      refreshFlight ??= refresh().finally(() => {
        refreshFlight = null;
      });
      if (await refreshFlight) return request<T>(path, init, false);
    }
    if (version === sessionVersion) {
      setSession(null);
      window.dispatchEvent(new Event("session-expired"));
    }
  }
  if (!response.ok) {
    let message = "The service is unavailable. Try again.";
    try {
      message = detail((await response.json()).detail);
    } catch {
      /* Non-JSON upstream failure. */
    }
    if (getLanguage() === "bn") {
      const known = uiLabel(message);
      message =
        known !== message
          ? known
          : response.status === 401
            ? t("Please sign in again to continue.")
            : response.status === 403
              ? t("You do not have access to this action.")
              : response.status === 404
                ? t("The requested record was not found.")
                : response.status === 422
                  ? t("Please check the form and try again.")
                  : t("The request could not be completed. Please try again.");
    }
    throw new ApiError(response.status, message);
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}
function post<T>(path: string, body: unknown) {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}
export function query(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return `?${params}`;
}
export const api = {
  login: (email: string, password: string) =>
    post<Tokens>("/login", { email, password }),
  register: (email: string, password: string, full_name: string) =>
    post<Tokens>("/register", { email, password, full_name }),
  me: () => request<User>("/me"),
  intelligence: () => request<Intelligence>("/finance/intelligence"),
  editGoal: (id: number, body: GoalUpdate) =>
    request<Goal>(`/finance/goals/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  editScheduled: (id: number, body: ScheduledUpdate) =>
    request<Scheduled>(`/finance/scheduled-cashflow/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  summary: (period: Record<string, string>) =>
    request<Summary>(`/insights/summary${query(period)}`),
  transactions: (filters: Record<string, string | number | undefined>) =>
    request<Page<Transaction>>(`/transactions${query(filters)}`),
  addTransaction: (body: TransactionCreate) =>
    post<Transaction>("/transactions", body),
  correctCategory: (id: number, category: string) =>
    request<Transaction>(`/transactions/${id}/category`, {
      method: "PATCH",
      body: JSON.stringify({ category }),
    }),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<CSVUpload>("/upload-csv", { method: "POST", body });
  },
  scheduled: (filters: Record<string, string | number | undefined> = {}) =>
    request<Page<Scheduled>>(`/finance/scheduled-cashflow${query(filters)}`),
  addScheduled: (body: ScheduledCreate) =>
    post<Scheduled>("/finance/scheduled-cashflow", body),
  updateScheduled: (id: number, status: Scheduled["status"]) =>
    request<Scheduled>(`/finance/scheduled-cashflow/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  goals: (offset = 0) =>
    request<Page<Goal>>(`/finance/goals?limit=20&offset=${offset}`),
  addGoal: (body: GoalCreate) => post<Goal>("/finance/goals", body),
  updateGoal: (id: number, current_saved: string | null) =>
    request<Goal>(`/finance/goals/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ current_saved }),
    }),
  goalPlan: (id: number) => request<GoalPlan>(`/finance/goals/${id}/plan`),
  nudges: () => request<Nudges>("/insights/proactive"),
  recommendations: () =>
    request<Recommendations>("/finance/savings/recommendations"),
  cashflow: (starting_balance: string, months_ahead: number) =>
    post<Cashflow>("/finance/coach/cashflow", {
      starting_balance,
      months_ahead,
    }),
  decision: (body: {
    starting_balance: string;
    purchase_amount: string;
    safety_buffer: string;
    horizon_days: number;
  }) => post<Decision>("/finance/coach/spending-decision", body),
  ask: (body: {
    question: string;
    starting_balance?: string;
    purchase_amount?: string;
    safety_buffer?: string;
  }) => post<Answer>("/chat/ask", body),
  monthly: (period: Record<string, string>) =>
    request<Monthly[]>(`/insights/monthly${query(period)}`),
};
