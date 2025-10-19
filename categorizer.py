"""it contains rule-based categorization helpers."""
# categorizer.py
import re

RULES = [
    (r"starbucks|coffee", "Coffee"),
    (r"uber|lyft|taxi", "Transport"),
    (r"walmart|grocery|aldi|big bazaar|grocer", "Groceries"),
    (r"rent|apartment|landlord", "Rent"),
    (r"salary|payroll|employer|pay", "Income"),
    (r"netflix|amazon|hotstar|movie", "Entertainment"),
    (r"hospital|clinic|doctor|pharmacy", "Health"),
]

def categorize_text(text: str) -> str:
    if not text:
        return "Other"
    
    text = text.lower()
    
    for pattern, category in RULES:
        if re.search(pattern, text):
            return category
    return "Other"
