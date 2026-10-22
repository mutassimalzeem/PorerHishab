"""Tests for the deterministic categorization rule engine."""

from app.services.categorization.rules import match_rules


def test_foodpanda_maps_to_food():
    result = match_rules(merchant="Foodpanda", description="ORDER FP-DHAKA")

    assert result is not None
    assert result["category"] == "Food"
    assert result["method"] == "rule"
    assert result["confidence"] >= 0.9


def test_uber_maps_to_transport():
    result = match_rules(merchant="Uber")

    assert result["category"] == "Transport"


def test_netflix_maps_to_subscription():
    result = match_rules(merchant="Netflix", description="NETFLIX MONTHLY")

    assert result["category"] == "Subscription"


def test_daraz_maps_to_shopping():
    result = match_rules(merchant="Daraz", description="DARAZ ORDER 12345")

    assert result["category"] == "Shopping"


def test_pathao_food_beats_generic_pathao():
    """More specific keywords must win: Pathao Food is Food, not Transport."""
    result = match_rules(merchant="Pathao Food")

    assert result["category"] == "Food"


def test_generic_pathao_is_transport():
    result = match_rules(merchant="Pathao")

    assert result["category"] == "Transport"


def test_agora_supershop_maps_to_groceries():
    result = match_rules(
        normalized_merchant="AGORA SUPERSHOP GULSHAN",
        description="AGORA SUPERSHOP GULSHAN",
    )

    assert result["category"] == "Groceries"


def test_matching_is_case_insensitive():
    result = match_rules(description="kfc uttara")

    assert result["category"] == "Food"


def test_salary_description_maps_to_salary():
    result = match_rules(description="MONTHLY SALARY")

    assert result["category"] == "Salary"


def test_unknown_merchant_returns_none():
    """No LLM involvement here: the rule engine simply reports no match."""
    result = match_rules(
        merchant="XYZ RANDOM STORE",
        description="CARD PURCHASE 8823",
    )

    assert result is None


def test_all_fields_missing_returns_none():
    result = match_rules(merchant=None, normalized_merchant=None, description=None)

    assert result is None


def test_word_boundaries_avoid_partial_merchants():
    """'ubershop' must not trigger the Uber ride-hailing rule."""
    result = match_rules(merchant="Ubershop")

    assert result is None


def test_rule_result_is_vocabulary_conformant():
    result = match_rules(merchant="Foodpanda")

    assert set(result) == {"category", "confidence", "method", "reason"}
    assert result["method"] == "rule"
