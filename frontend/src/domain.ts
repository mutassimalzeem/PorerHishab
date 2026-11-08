import type { ApiSchemas, ApiOperations } from "./generated/api";
// Backend Decimal values stay strings; convert only for display and chart geometry.
export type Money = string;
export interface User {
  id: number;
  email: string;
  full_name: string | null;
  email_verified?: boolean;
}

export type Tokens = ApiSchemas["RegisterTokenResponse"] & {
  refresh_token?: ApiSchemas["LoginTokenResponse"]["refresh_token"];
};

export type CSVUpload = ApiSchemas["CSVUploadResponse"];

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
> &
  Partial<Pick<ApiSchemas["GoalRead"], "goal_type" | "priority" | "currency">>;
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
> & {
  balance_source?: string;
};
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
> & {
  balance_source?: string;
};
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

export type AccountPositionItem = ApiSchemas["AccountPositionItem"];
export type AccountOverviewResponse = ApiSchemas["AccountOverviewResponse"];
export type TrustedBdtPosition = ApiSchemas["TrustedBdtPosition"];
export type AccountCreate = ApiSchemas["AccountCreate"];
export type AccountBalanceUpdate = ApiSchemas["AccountBalanceUpdate"];
export type OpeningBalanceUpdate = ApiSchemas["OpeningBalanceUpdate"];
export type AccountBalanceReconciliation =
  ApiSchemas["AccountBalanceReconciliation"];

export type FinancialAlert = ApiSchemas["FinancialAlertResponse"];
export type AlertEvaluationSummary = ApiSchemas["AlertEvaluationSummary"];
export type AlertUnreadCount = ApiSchemas["AlertUnreadCountResponse"];
export type AlertList = ApiSchemas["AlertListResponse"];

export type NotificationPreference =
  ApiSchemas["NotificationPreferenceResponse"];
export type NotificationPreferenceUpdate =
  ApiSchemas["NotificationPreferenceUpdate"];
export type NotificationDelivery = ApiSchemas["NotificationDeliveryResponse"];
export type NotificationDeliveryList =
  ApiSchemas["NotificationDeliveryListResponse"];
export type NotificationHistoryItem =
  ApiSchemas["NotificationHistoryItemResponse"];
export type NotificationHistoryList =
  ApiSchemas["NotificationHistoryListResponse"];
export type NotificationDigest = ApiSchemas["NotificationDigestResponse"];
export type DigestEvaluation = ApiSchemas["DigestEvaluationResponse"];

export type CoachResponse = ApiSchemas["CoachResponse"];
export type CoachRequest = ApiSchemas["CoachRequest"];
export type CoachClaim = ApiSchemas["CoachClaim"];
export type CoachEvidence = ApiSchemas["CoachEvidence"];
export type CoachAction = ApiSchemas["CoachAction"];
export type CoachWarning = ApiSchemas["CoachWarning"];
export type CoachConversationSummary = ApiSchemas["CoachConversationSummary"];
export type CoachConversationPage = ApiSchemas["CoachConversationPage"];
export type CoachConversationDetail = ApiSchemas["CoachConversationDetail"];
export type CoachMessageRead = ApiSchemas["CoachMessageRead"];
