from __future__ import annotations

ALLOWED_CATEGORIES = {
    "Food",
    "Groceries",
    "Transport",
    "Shopping",
    "Bills",
    "Entertainment",
    "Healthcare",
    "Education",
    "Housing",
    "Travel",
    "Salary",
    "Transfer",
    "Investment",
    "Subscription",
    "Other",
    "Uncategorized",
}

#: Safe fallback when neither rules nor the LLM produce a valid category.
UNCATEGORIZED: str = "Uncategorized"

#   We can expand later