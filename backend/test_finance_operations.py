from unittest.mock import Mock, patch

from app.services.finance.operations import (
    get_categories,
    get_monthly,
    get_summary,
    get_top_merchants,
)


def test_get_summary_delegates_to_analytics():
    db = Mock()

    with patch(
        "app.services.finance.operations.get_user_summary",
        return_value={"net": "25000.00"},
    ) as mocked:
        result = get_summary(
            db=db,
            user_id=7,
        )

    assert result == {"net": "25000.00"}

    mocked.assert_called_once_with(
        db,
        7,
        start_date=None,
        end_date=None,
    )


def test_get_categories_delegates_to_analytics():
    db = Mock()

    with patch(
        "app.services.finance.operations.get_user_categories",
        return_value={"expenses_by_category": {}},
    ) as mocked:
        result = get_categories(
            db=db,
            user_id=7,
        )

    assert result == {"expenses_by_category": {}}

    mocked.assert_called_once()


def test_get_monthly_delegates_to_analytics():
    db = Mock()

    with patch(
        "app.services.finance.operations.get_user_monthly",
        return_value=[],
    ) as mocked:
        result = get_monthly(
            db=db,
            user_id=7,
        )

    assert result == []
    mocked.assert_called_once()


def test_get_top_merchants_delegates_to_analytics():
    db = Mock()

    with patch(
        "app.services.finance.operations.get_user_top_merchants",
        return_value=[],
    ) as mocked:
        result = get_top_merchants(
            db=db,
            user_id=7,
            limit=3,
        )

    assert result == []
    mocked.assert_called_once()