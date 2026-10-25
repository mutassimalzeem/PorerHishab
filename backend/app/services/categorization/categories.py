from __future__ import annotations

ALLOWED_CATEGORIES = {
    "Food",
    "Groceries",
    "Transport",
    "Shopping",
    "Bills",
    "Business",
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
    # Existing manual-create rule labels are retained for API compatibility.
    "Coffee", "Rent", "Income", "Health", "Utilities", "Fitness",
}

#: Safe fallback when neither rules nor the LLM produce a valid category.
UNCATEGORIZED: str = "Uncategorized"

#   We can expand later
# Extend the vocabulary without changing transaction columns or existing labels.
from app.core.config import settings
ALLOWED_CATEGORIES |= {label.strip() for label in settings.CATEGORY_EXTRA_LABELS if label.strip() and len(label.strip()) <= 100}
