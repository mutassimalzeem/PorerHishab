"""Read-only observational aggregation over feedback and AI-15I outcomes."""
from collections import Counter
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import get_args

from sqlalchemy.orm import Session

from app.models.coaching_feedback import CoachingFeedback
from app.schemas.coaching import CoachingType
from app.schemas.coaching_effectiveness import (
    CoachingEffectivenessCounts,
    CoachingEffectivenessRates,
    CoachingEffectivenessResponse,
    CoachingEffectivenessTypeBreakdown,
)
from app.services.finance.action_outcome import action_outcomes

PERCENT_QUANT = Decimal("0.01")
COUNT_NAMES = tuple(CoachingEffectivenessCounts.model_fields)
LIMITATIONS = [
    "Outcomes are observational and do not establish causation.",
    "Action completion is based on user-reported feedback.",
    "Totals cover current stored feedback records, not all recommendations ever generated; restored feedback is absent and overwritten feedback has no history.",
    "Some recommendations may have insufficient follow-up data.",
    "Pending or unavailable outcomes count as acted on but are excluded from measurable outcomes and insufficient data.",
]


OUTCOME_LIMITATION_LABELS = {
    "Only acted-on recommendations are normally tracked; dismissed, not-relevant, snoozed and unrated recommendations are excluded.": (
        "Outcome observations normally apply only to acted-on recommendations; dismissed, not-relevant, snoozed and unrated recommendations are excluded from outcome tracking. "
        "Dismissed, not-relevant and snoozed feedback are still included in overall feedback totals."
    ),
}


def percentage(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(
        PERCENT_QUANT, rounding=ROUND_HALF_UP)


class _EffectivenessAccumulator:
    def __init__(self) -> None:
        self.counts = Counter({name: 0 for name in COUNT_NAMES})

    def add_feedback(self, status: str) -> None:
        self.counts["total_recommendations"] += 1
        self.counts[status] += 1

    def add_outcome(self, status: str) -> None:
        if status in {"improved", "unchanged", "worsened"}:
            self.counts[status] += 1
            self.counts["measurable_outcomes"] += 1
        elif status == "insufficient_data":
            self.counts[status] += 1


def _rates(accumulator: _EffectivenessAccumulator) -> CoachingEffectivenessRates:
    counts = accumulator.counts
    return CoachingEffectivenessRates(
        observable_outcome_rate=percentage(counts["measurable_outcomes"], counts["acted_on"]),
        improvement_rate_among_observed=percentage(counts["improved"], counts["measurable_outcomes"]),
        worsening_rate_among_observed=percentage(counts["worsened"], counts["measurable_outcomes"]),
    )


def get_coaching_effectiveness(db: Session, user_id: int, *, as_of: date | None = None) -> CoachingEffectivenessResponse:
    if user_id <= 0:
        raise ValueError("Invalid effectiveness scope")
    report = action_outcomes(db, user_id, as_of=as_of)
    outcomes = {item.recommendation_id: item for item in report.items}
    rows = db.query(CoachingFeedback).filter_by(user_id=user_id).all()
    overall = _EffectivenessAccumulator()
    by_type = {}
    for row in rows:
        recommendation_type = row.recommendation_id.split(":", 1)[0]
        if recommendation_type not in get_args(CoachingType):
            continue
        group = by_type.setdefault(recommendation_type, _EffectivenessAccumulator())
        for accumulator in (overall, group):
            accumulator.add_feedback(row.status)
            outcome = outcomes.get(row.recommendation_id)
            if row.status == "acted_on" and outcome is not None:
                accumulator.add_outcome(outcome.status)
    breakdown = []
    for recommendation_type, accumulator in sorted(by_type.items()):
        counts = {name: value for name, value in accumulator.counts.items()
                  if name in CoachingEffectivenessTypeBreakdown.model_fields}
        breakdown.append(CoachingEffectivenessTypeBreakdown(
            recommendation_type=recommendation_type, **counts, **_rates(accumulator).model_dump()))
    return CoachingEffectivenessResponse(
        counts=CoachingEffectivenessCounts(**overall.counts), rates=_rates(overall),
        by_type=breakdown, causal_claim=False,
        limitations=list(LIMITATIONS) + [
            OUTCOME_LIMITATION_LABELS.get(value, value) for value in report.limitations],
    )
