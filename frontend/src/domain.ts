// Backend Decimal values stay strings; convert only for display and chart geometry.
export type Money = string;
export interface User {
  id: number;
  email: string;
  full_name: string | null;
}
export interface Tokens {
  access_token: string;
  refresh_token?: string;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more?: boolean;
}
export interface Transaction {
  id: number;
  date: string;
  description: string | null;
  merchant: string | null;
  amount: Money;
  category: string | null;
  fee: Money;
  balance: Money | null;
  source: string | null;
  category_reason: string | null;
}
export interface TransactionCreate {
  date: string;
  description: string;
  merchant?: string;
  amount: Money;
  category?: string;
}
export interface Summary {
  transaction_count: number;
  total_income: Money;
  total_expenses: Money;
  net: Money;
  savings_rate: Money | null;
}
export interface Scheduled {
  id: number;
  title: string;
  kind: "income" | "expense";
  amount: Money;
  due_date: string;
  status: "scheduled" | "paid" | "cancelled";
  category: string | null;
  notes: string | null;
}
export type ScheduledCreate = Pick<
  Scheduled,
  "title" | "kind" | "amount" | "due_date"
>;
export interface Goal {
  id: number;
  name: string;
  description: string | null;
  target_amount: Money;
  current_saved: Money | null;
  target_date: string;
  status: "active" | "completed" | "cancelled";
}
export type GoalCreate = Pick<
  Goal,
  "name" | "target_amount" | "current_saved" | "target_date"
>;
export interface GoalPlan {
  goal_id: number;
  as_of_date: string;
  remaining_amount: Money | null;
  required_weekly: Money | null;
  required_monthly: Money | null;
  estimated_monthly_capacity: Money | null;
  affordability: string;
  assumptions: string[];
  limitations: string[];
}
export interface Coverage {
  start_date: string;
  end_date: string;
  transaction_count: number;
  first_transaction_date: string | null;
  last_transaction_date: string | null;
  limitations: string[];
}
export interface Recommendation {
  id: string;
  category: string;
  title: string;
  evidence: Record<string, unknown>;
  estimated_monthly_saving: Money;
  estimated_annual_saving: Money;
  confidence: "low" | "medium";
  assumptions: string[];
}
export interface Recommendations {
  coverage: Coverage;
  recommendations: Recommendation[];
  limitations: string[];
}
export interface Nudge {
  key: string;
  type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  evidence: Record<string, unknown>;
  period_start: string;
  period_end: string;
  next_action: string;
}
export interface Nudges {
  as_of_date: string;
  insights: Nudge[];
  limitations: string[];
}
export interface CoachMonth {
  month: string;
  historical_income_estimate: Money | null;
  historical_expense_estimate: Money | null;
  scheduled_expenses: Money;
  uncertain_scheduled_income: Money;
  reserved_expenses: Money;
  projected_balance: Money | null;
  balance_without_future_income: Money;
}
export interface Cashflow {
  as_of_date: string;
  starting_balance: Money;
  months: CoachMonth[];
  coverage: Coverage;
  assumptions: string[];
  limitations: string[];
}
export interface Decision {
  status: "safe" | "caution" | "not_recommended" | "insufficient_data";
  purchase_amount: Money;
  scheduled_expense_reserve: Money;
  remaining_after_purchase_and_reserve: Money;
  uncertain_scheduled_income: Money;
  horizon_end: string;
  assumptions: string[];
  warnings: string[];
}
export interface Answer {
  answer: string;
  intent: string;
  sources: Record<string, unknown>[];
  calculation: Record<string, unknown>;
  date_range: Record<string, string> | null;
  coverage: Record<string, unknown> | null;
  assumptions: string[];
  limitations: string[];
  status: string;
}
export interface Monthly {
  month: string;
  income: Money;
  expenses: Money;
  net: Money;
}
