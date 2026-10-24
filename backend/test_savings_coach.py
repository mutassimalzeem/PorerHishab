
from decimal import Decimal
from unittest.mock import patch

from app.schemas.planner import SavingsPlanResponse, SavingsRecommendation
from app.schemas.savings_coach import SavingsAction, SavingsActionDrafts
from app.services.ai.savings_coach import generate_savings_actions


def sample_plan():
    return SavingsPlanResponse(
        goal_amount=Decimal("60000"),
        current_saved=Decimal("0"),
        remaining_goal=Decimal("60000"),
        target_date="2026-12-31",
        months_remaining=3,
        required_monthly_saving=Decimal("20000"),
        estimated_monthly_income=Decimal("50000"),
        estimated_monthly_spending=Decimal("45000"),
        estimated_monthly_surplus=Decimal("5000"),
        recommended_monthly_cut=Decimal("15000"),
        projected_monthly_saving=Decimal("20000"),
        status="at_risk",
        recommendations=[
            SavingsRecommendation(
                category="Food",
                monthly_spending=Decimal("20000"),
                suggested_cut=Decimal("4000"),
            )
        ],
    )


def test_savings_actions_reject_unsupported_categories():
    drafts = SavingsActionDrafts(
        actions=[
            SavingsAction(
                title="Plan food spending",
                category="Food",
                action="Set a weekly food budget and review it regularly.",
                reason="Food is listed in your plan's spending-cut recommendations.",
                priority="high",
            ),
            SavingsAction(
                title="Cut travel spending",
                category="Travel",
                action="Reduce travel spending to meet your savings target.",
                reason="This category was not supplied by the deterministic plan.",
                priority="medium",
            ),
        ]
    )

    with patch(
        "app.services.ai.savings_coach.ChatOpenAI",
        create=True,
    ):
        pass

    with patch(
        "app.services.ai.savings_coach.settings"
    ) as mock_settings:
        mock_settings.OPENAI_KEY = "test-key"
        mock_settings.OPENAI_CHAT_MODEL = "test-model"
        mock_settings.OPENAI_BASE_URL = None

        with patch(
            "langchain_openai.ChatOpenAI",
            create=True,
        ) as mock_llm:
            mock_llm.return_value.with_structured_output.return_value.invoke.return_value = drafts
            result = generate_savings_actions(sample_plan())

    assert len(result) == 1
    assert result[0].category == "Food"
