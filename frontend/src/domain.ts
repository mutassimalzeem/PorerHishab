import type { ApiSchemas, ApiOperations } from "./generated/api";
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
export type Transaction = Required<
  Pick<
    ApiSchemas["TransactionRead"],
    | "id"
    | "date"
    | "description"
    | "merchant"
    | "amount"
    | "category"
    | "fee"
    | "balance"
    | "source"
    | "category_reason"
  >
>;
export interface TransactionCreate {
  date: string;
  description: string;
  merchant?: string;
  amount: Money;
  category?: string;
}
export type Summary = Required<
  Pick<
    ApiSchemas["SummaryInsight"],
    | "transaction_count"
    | "total_income"
    | "total_expenses"
    | "net"
    | "savings_rate"
  >
>;
export type Scheduled = Required<
  Pick<
    ApiSchemas["ScheduledCashflowRead"],
    | "id"
    | "title"
    | "kind"
    | "amount"
    | "due_date"
    | "status"
    | "category"
    | "notes"
  >
>;
export type ScheduledCreate = Pick<
  Scheduled,
  "title" | "kind" | "amount" | "due_date"
>;
export type Goal = Required<
  Pick<
    ApiSchemas["GoalRead"],
    | "id"
    | "name"
    | "description"
    | "target_amount"
    | "current_saved"
    | "target_date"
    | "status"
  >
>;
export type GoalCreate = Pick<
  Goal,
  "name" | "target_amount" | "current_saved" | "target_date"
>;
export type GoalPlan = Required<
  Pick<
    ApiSchemas["GoalPlan"],
    | "goal_id"
    | "as_of_date"
    | "remaining_amount"
    | "required_weekly"
    | "required_monthly"
    | "estimated_monthly_capacity"
    | "affordability"
    | "assumptions"
    | "limitations"
  >
>;
export type Coverage = Required<
  Pick<
    ApiSchemas["Coverage"],
    | "start_date"
    | "end_date"
    | "transaction_count"
    | "first_transaction_date"
    | "last_transaction_date"
    | "limitations"
  >
>;
export type Recommendation = Required<
  Pick<
    ApiSchemas["Recommendation"],
    | "id"
    | "category"
    | "title"
    | "evidence"
    | "estimated_monthly_saving"
    | "estimated_annual_saving"
    | "confidence"
    | "assumptions"
  >
>;
export type Recommendations = Required<
  Pick<
    ApiSchemas["RecommendationPage"],
    "coverage" | "recommendations" | "limitations"
  >
>;
export type Nudge = Required<
  Pick<
    ApiSchemas["Nudge"],
    | "key"
    | "type"
    | "severity"
    | "title"
    | "evidence"
    | "period_start"
    | "period_end"
    | "next_action"
  >
>;
export type Nudges = Required<
  Pick<ApiSchemas["NudgePage"], "as_of_date" | "insights" | "limitations">
>;
export type CoachMonth = Required<
  Pick<
    ApiSchemas["CoachMonth"],
    | "month"
    | "historical_income_estimate"
    | "historical_expense_estimate"
    | "scheduled_expenses"
    | "uncertain_scheduled_income"
    | "reserved_expenses"
    | "projected_balance"
    | "balance_without_future_income"
  >
>;
export type Cashflow = Required<
  Pick<
    ApiSchemas["CoachCashflowResponse"],
    | "as_of_date"
    | "starting_balance"
    | "months"
    | "coverage"
    | "assumptions"
    | "limitations"
  >
>;
export type Decision = Required<
  Pick<
    ApiSchemas["CoachPurchaseResponse"],
    | "status"
    | "purchase_amount"
    | "scheduled_expense_reserve"
    | "remaining_after_purchase_and_reserve"
    | "uncertain_scheduled_income"
    | "horizon_end"
    | "assumptions"
    | "warnings"
  >
>;
export type Answer = Required<
  Pick<
    ApiSchemas["FinanceQuestionResponse"],
    | "answer"
    | "intent"
    | "sources"
    | "calculation"
    | "date_range"
    | "coverage"
    | "assumptions"
    | "limitations"
    | "status"
  >
>;
export type Monthly = Required<
  Pick<ApiSchemas["MonthlyInsight"], "month" | "income" | "expenses" | "net">
>;

export type Intelligence = ApiSchemas["IntelligenceResponse"];
export type TransactionFilters = ApiOperations["GET /transactions"]["query"];
export type GoalUpdate = ApiSchemas["GoalUpdate"];
export type ScheduledUpdate = ApiSchemas["ScheduledCashflowUpdate"];
