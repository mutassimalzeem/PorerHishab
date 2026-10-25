"""Deterministic rule-based transaction categorization.

Checked *first* in the pipeline so obvious transactions never need an
LLM call.  The rule table is deliberately small: specific merchants and
obvious descriptive words over generic patterns.  Everything the rules
cannot match falls through to the LLM fallback in
:mod:`app.services.categorization.llm`.

Matching is case-insensitive and word-boundary based, and the table is
evaluated top to bottom, so *more specific* keywords (``pathao food``)
must appear before their generic counterparts (``pathao``).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from app.schemas.categorization import CategorizedTransaction


class _Rule(NamedTuple):
    keywords: tuple[str, ...]
    category: str
    confidence: float
    label: str


# High-value merchants / phrases first, generic words last.  Keep this
# short: the goal is "obvious transactions never need an LLM", not a
# perfect classifier.
_RULES: tuple[_Rule, ...] = (
    # -- Subscription (before Shopping so "Amazon Prime" wins over "Amazon") --
    _Rule(
        keywords=("amazon prime",), category="Subscription", confidence=0.95,
        label="Amazon Prime",
    ),
    _Rule(
        keywords=("netflix",), category="Subscription", confidence=0.98,
        label="Netflix",
    ),
    _Rule(
        keywords=("spotify",), category="Subscription", confidence=0.98,
        label="Spotify",
    ),
    _Rule(
        keywords=("youtube premium",), category="Subscription", confidence=0.98,
        label="YouTube Premium",
    ),
    # -- Food --
    _Rule(
        keywords=("foodpanda",), category="Food", confidence=0.98,
        label="Foodpanda",
    ),
    _Rule(
        keywords=("pathao food", "pathao ride food",), category="Food", confidence=0.95,
        label="Pathao Food",
    ),
    _Rule(
        keywords=("kfc", "mcdonald", "pizza hut", "burger king", "starbucks",
                  "subway",), category="Food", confidence=0.95,
        label="Food merchant",
    ),
    _Rule(
        keywords=("restaurant", "lunch", "dinner", "breakfast", "dining",),
        category="Food", confidence=0.85, label="food-related description",
    ),
    # -- Transport --
    _Rule(
        keywords=("uber", "lyft", "pathao", "obhai", "shohoz", "taxi",),
        category="Transport", confidence=0.95, label="Ride-hailing service",
    ),
    # -- Groceries --
    _Rule(
        keywords=("supershop", "supermarket", "grocery", "groceries", "agora",
                  "meena bazar", "shwapno", "swapno", "unimart",),
        category="Groceries", confidence=0.95, label="Grocery store",
    ),
    # -- Shopping --
    _Rule(
        keywords=("daraz", "amazon", "aliexpress", "pickaboo",),
        category="Shopping", confidence=0.95, label="Online marketplace",
    ),
    # -- Bills --
    _Rule(
        keywords=("desco", "dpdc", "wasa", "titas", "grameenphone", "robi",
                  "airtel", "banglalink", "electricity bill", "internet bill",
                  "utility bill",),
        category="Bills", confidence=0.95, label="Utility provider",
    ),
    # -- Salary / income --
    _Rule(
        keywords=("salary", "payroll",), category="Salary", confidence=0.95,
        label="Salary",
    ),
    # -- Transfers --
    _Rule(
        keywords=("fund transfer", "send money", "bank transfer", "npsb",
                  "bkash transfer", "cash out",),
        category="Transfer", confidence=0.9, label="Money transfer",
    ),
    # -- Housing --
    _Rule(
        keywords=("rent", "landlord",), category="Housing", confidence=0.85,
        label="Housing",
    ),
    # -- Healthcare --
    _Rule(
        keywords=("pharmacy", "hospital", "clinic",), category="Healthcare",
        confidence=0.9, label="Healthcare",
    ),
)


# Unicode keyword literals avoid depending on the terminal's output encoding.
_RULES += (
    _Rule(("chaldal", "চালডাল", "স্বপ্ন", "বাজার"), "Groceries", 0.95, "Grocery merchant"),
    _Rule(("খাবার", "ফুডপান্ডা"), "Food", 0.9, "Dining description"),
    _Rule(("বিদ্যুৎ বিল", "গ্যাস বিল", "পানির বিল"), "Bills", 0.95, "Utility description"),
    _Rule(("বেতন",), "Salary", 0.95, "Salary description"),
    _Rule(("tuition", "school fee", "university", "স্কুল ফি"), "Education", 0.9, "Education description"),
    _Rule(("রিকশা", "পাঠাও", "উবার", "বাস ভাড়া"), "Transport", 0.9, "Transport description"),
    _Rule(("বাসা ভাড়া",), "Housing", 0.9, "Housing description"),
    _Rule(("ওষুধ", "হাসপাতাল"), "Healthcare", 0.9, "Healthcare description"),
)

_COMPILED = tuple(
    (re.compile(rf"(?<![\w\u0980-\u09ff]){re.escape(keyword)}(?![\w\u0980-\u09ff])", re.IGNORECASE), rule)
    for rule in _RULES
    for keyword in rule.keywords
)


def match_rules(
    *,
    merchant: str | None = None,
    normalized_merchant: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Match transaction text against the rule table.

    Returns ``{"category", "confidence", "method", "reason"}`` on the
    first match, or ``None`` when nothing matches (which is what sends
    the transaction to the LLM fallback).  Never calls the LLM.
    """
    text = " ".join(
        str(value)
        for value in (merchant, normalized_merchant, description)
        if value
    )

    if not text.strip():
        return None

    from app.core.config import settings
    from app.services.categorization.categories import ALLOWED_CATEGORIES
    for keyword, category in settings.CATEGORY_KEYWORD_RULES.items():
        if keyword.strip() and category in ALLOWED_CATEGORIES and re.search(r"(?<![\w\u0980-\u09ff])" + re.escape(keyword.strip()) + r"(?![\w\u0980-\u09ff])", text, re.IGNORECASE):
            return CategorizedTransaction(category=category, confidence=0.9, method="rule", reason="Matched a configured category keyword.").model_dump()

    for pattern, rule in _COMPILED:
        match = pattern.search(text)
        if match:
            return CategorizedTransaction(
                category=rule.category,
                confidence=rule.confidence,
                method="rule",
                reason=f"Matched merchant keyword {rule.label!r} "
                       f"({match.group(0)!r})",
            ).model_dump()

    return None
