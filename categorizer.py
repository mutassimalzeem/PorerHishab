"""it contains rule-based categorization helpers."""
# categorizer.py
# categorizer.py
import re

# Add / tweak rules as you wish
RULES = [
    (r"\b(starbucks|coffee|cafe)\b", "Coffee"),
    (r"\b(uber|lyft|taxi|ride|cab)\b", "Transport"),
    (r"\b(walmart|aldi|whole\s*foods|grocery|grocer)\b", "Groceries"),
    (r"\b(rent|landlord|apartment)\b", "Rent"),
    (r"\b(salary|payroll|employer|stipend|pay)\b", "Income"),
    (r"\b(netflix|amazon\s*prime|disney\+|hotstar|movie|cinema|spotify)\b", "Entertainment"),
    (r"\b(hospital|clinic|doctor|pharmacy|medicine|meds)\b", "Health"),
    (r"\b(internet|utility|utilities|electric|electricity|water|gas|bill)\b", "Utilities"),
    (r"\b(gym|membership|fitness|workout)\b", "Fitness"),
    (r"\b(airline|flight|hotel|booking|train|bus)\b", "Travel"),
    (r"\b(restaurant|diner|lunch|dinner|food|pizza|burger)\b", "Food"),
    (r"\b(shopping|mall|clothes|apparel)\b", "Shopping"),
]

COMPILED = [(re.compile(pat, re.I), cat) for pat, cat in RULES]

def categorize_text(text: str) -> str:
    if not text:
        return "Other"
    for pat, cat in COMPILED:
        if pat.search(text):
            return cat
    return "Other"
