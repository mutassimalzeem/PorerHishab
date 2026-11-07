
import { FeedbackControls } from "./FinancialCoaching";
import { t } from "../lib/locale";

const SUPPORTED_RECOMMENDATION_TYPES = new Set([
  "cash_risk",
  "upcoming_obligations",
  "spending_spike",
  "repeated_spending",
  "savings_opportunity",
  "goal_risk",
]);

interface Props {
  sourceActionIds: string[];
  refresh: () => Promise<void>;
}

export function FinancialReviewFeedback({
  sourceActionIds,
  refresh,
}: Props) {
  const recommendationIds = [
    ...new Set(
      sourceActionIds.filter((id) =>
        SUPPORTED_RECOMMENDATION_TYPES.has(id.split(":", 1)[0]),
      ),
    ),
  ];

  if (recommendationIds.length === 0) {
    return null;
  }

  return (
    <section className="financial-review-feedback">
      <p className="source">
        {t(
          "You can report what you did for a supported recommendation. This records your report; it does not verify a financial action.",
        )}
      </p>

      {recommendationIds.map((id) => (
        <div key={id} className="financial-review-feedback-item">
          <FeedbackControls id={id} refresh={refresh} />
        </div>
      ))}

      <a href="#action-outcomes">
        {t("Track reported outcomes")}
      </a>
    </section>
  );
}