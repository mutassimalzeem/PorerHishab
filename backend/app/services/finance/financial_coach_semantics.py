"""Conservative semantic projection of existing coach evidence, never a calculator.

Unclassified numeric assertions fail closed. Facts retain evidence ID, unit and
as-of date; numbers from counts, scores and durations never become money.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from app.schemas.financial_coach import CoachEvidence, EvidenceType

DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
NUMBER = re.compile(r"(?<![\w.])[+-]?[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?(?:(?!\w|\.[0-9])|(?=টি))")
CURRENCY = re.compile(r"bdt|taka|tk\b|টাকা|৳|usd|eur|gbp|[$€£]", re.I)
ESTIMATE = re.compile(r"estimat|project|forecast|potential|average|সম্ভাব্য|আনুমানিক|গড়", re.I)
METRICS = [
    ("emergency_fund", r"emergency (?:fund|reserve)|rainy.day fund|জরুরি (?:তহবিল|সঞ্চয়)"),
    ("optional_reserve", r"unassigned savings reserve|estimated reserve|optional reserve"),
    ("purchase", r"purchase amount|purchase of|proposed purchase"),
    ("available_cash", r"available cash|available funds|available balance|cash available|spendable cash|spendable funds|cash on hand|cash balance|নগদ টাকা|হাতে থাকা টাকা|ব্যবহারযোগ্য (?:নগদ|টাকা)|উপলব্ধ নগদ"),
    ("trusted_cash", r"trusted cash|বিশ্বস্ত নগদ"),
    ("account_balance", r"account balance|bank balance|হিসাবের (?:ব্যালেন্স|স্থিতি)|অ্যাকাউন্ট(?:ের)? ব্যালেন্স"),
    ("projected_balance", r"projected balance|forecast balance"),
    ("remaining_balance", r"remaining balance|অবশিষ্ট ব্যালেন্স"),
    ("starting_balance", r"starting balance|opening balance"),
    ("capacity", r"contribution capacity|savings capacity|monthly capacity"),
    ("obligations", r"outstanding obligations|scheduled expenses|scheduled expense|expense reserve|দায়|নির্ধারিত ব্যয়"),
    ("surplus", r"surplus|উদ্বৃত্ত"),
    ("income", r"income|আয়|আয়"),
    ("expenses", r"expenses?|spending|spent|largest category|খরচ|ব্যয়|ব্যয়"),
    ("savings", r"savings?|saved|সঞ্চয়|সঞ্চয়"),
    ("balance", r"balance|ব্যালেন্স|স্থিতি"),
    ("available_cash", r"\bcash\b|নগদ"),
    ("unclassified_money", r"nest egg|cushion|purchasing power|wealth|\bfunds?\b|\bmoney\b|\bbudget\b"),
]


def metric(text: str) -> str | None:
    text = text.lower().replace("_", " ")
    return next((name for name, pattern in METRICS if re.search(pattern, text)), None)


@dataclass(frozen=True)
class FinancialFact:
    evidence: CoachEvidence
    metric: str
    value: Decimal
    category: str | None = None


def financial_facts(evidence: list[CoachEvidence]) -> list[FinancialFact]:
    facts = []
    ids = Counter(ev.evidence_id for ev in evidence)
    for ev in evidence:
        if (ids[ev.evidence_id] != 1 or not ev.evidence_id.strip()
                or not ev.source.strip() or ev.as_of_date is None):
            continue
        # These fields are producer-supplied metadata, not authenticated provenance.
        # The caller must supply a tenant-scoped package from the assembler.
        # AI-16's existing planner adapter wraps a BDT recommendation without
        # repeating its unit. Recognize that exact producer, never arbitrary dicts.
        planner_bdt = (ev.evidence_id.startswith("ev_plan_recommendation_")
                       and ev.source == "financial_runway"
                       and ev.label == "Consider an unassigned savings reserve")
        if ev.unit not in {"BDT", "USD", "EUR", "GBP"} and not planner_bdt:
            continue
        id_metric = metric(ev.evidence_id)
        label_metric = metric(ev.label)
        if id_metric and label_metric and id_metric != label_metric:
            continue
        identity = id_metric or label_metric
        if ev.evidence_type == EvidenceType.INTERPRETATION and ev.evidence_id != "ev_spending_top_category":
            continue
        if identity in {None, "unclassified_money"}:
            continue
        values = [(ev.value, None)]
        if isinstance(ev.value, dict):
            if "amount" in ev.value:
                values = [(ev.value["amount"], ev.value.get("category"))]
            elif ev.evidence_id == "ev_spending_categories":
                values = list(ev.value.items())
                values = [(value, category) for category, value in values]
            else:
                # Do not recursively bless percentages or arbitrary nested numbers.
                values = []
        for value, category in values:
            if category is not None and not isinstance(category, str):
                continue
            if value is None or isinstance(value, bool):
                continue
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError):
                continue
            if number.is_finite():
                facts.append(FinancialFact(ev, identity, number, category))
    return facts


def nearest_metric(text: str) -> str | None:
    matches = []
    for rank, (name, pattern) in enumerate(METRICS):
        for match in re.finditer(pattern, text, re.I):
            if any(start <= match.start() and end >= match.end() for start, end, _, _ in matches):
                continue
            matches.append((match.start(), match.end(), rank, name))
    return max(matches, key=lambda item: (item[1], -item[2]))[3] if matches else None


ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
NON_MONEY_UNIT = re.compile(
    r"\s*(?:%|percent\b|points?\b|(?:-?\s*)(?:days?|months?|years?)\b|"
    r"(?:active\s+|saved\s+|financial\s+)*(?:transactions?|goals?|alerts?|scenarios?)\b|"
    r"(?:potential\s+savings\s+)?opportunities\b|areas?\b|টি\s*(?:লেনদেন|লক্ষ্য|সতর্কতা)|দিন|মাস|শতাংশ)", re.I,
)
MONEY_EQUATION = re.compile(r"(?:is|are|equals?|was|were|হলো|হল|:)\s*$", re.I)


def _non_money_number(before: str, after: str, clause: str, identity: str | None) -> bool:
    # Dimensions are classified before money. This preserves ordinary counts,
    # percentages, durations and score ratios without turning them into currency.
    dimension = NON_MONEY_UNIT.match(after)
    duration_range = re.match(r"\s*(?:to|-)\s*\d+\s*(?:days?|months?|years?)\b", after, re.I)
    score_ratio = re.search(r"\bscore\b", clause, re.I) and re.match(r"\s*/\s*100\b", after)
    if not (dimension or duration_range or score_ratio):
        return False
    # A monetary equation cannot evade checking by changing only its unit.
    monetary_equation = identity and MONEY_EQUATION.search(before)
    return not monetary_equation


def unsupported_financial_text(text: str, evidence: list[CoachEvidence], as_of: date) -> bool:
    """Bind monetary prose to supplied evidence; never attest its database origin.

    Every numeric token must be a date, a nonmoney dimension or a supported money
    assertion. No currency marker is required to trigger validation. Source/ID
    membership is checked by the caller; the evidence contract cannot authenticate
    source names, tenant ownership or upstream calculations on its own.
    """
    from app.services.finance.financial_coach_validator import contains_unverified_spelled_money

    if contains_unverified_spelled_money(text):
        return True

    facts = financial_facts(evidence)
    text = text.translate(DIGITS)
    clauses = re.split(r"(?<![0-9])[.;!?।]|[;!?।]|\n|\band\b|\bwhile\b|,(?![0-9])|(?<![0-9]),", text, flags=re.I)
    for clause in clauses:
        currencies = CURRENCY.findall(clause)
        numeric_clause = CURRENCY.sub(lambda match: " " * len(match.group()), clause)
        numbers = list(NUMBER.finditer(numeric_clause))
        if re.search(r"[0-9]", clause) and not numbers:
            return True
        if not numbers:
            continue
        if re.search(r"\bor\b|অথবা", clause, re.I):
            identities = {name for name, pattern in METRICS
                          if name != "unclassified_money" and re.search(pattern, clause, re.I)}
            if len(identities) > 1:
                return True
        if re.search(r"\b(?:INR|AUD|CAD|JPY|CNY|SAR|AED)\b", clause, re.I):
            return True
        dates = list(ISO_DATE.finditer(clause))
        try:
            for stamp in dates:
                date.fromisoformat(stamp.group())
        except ValueError:
            return True
        for match in numbers:
            if any(stamp.start() <= match.start() < stamp.end() for stamp in dates):
                continue
            before, after = clause[:match.start()], clause[match.end():]
            identity = nearest_metric(before)
            marker_before = re.search(r"(?:bdt|taka|tk|টাকা|৳|usd|eur|gbp|[$€£])\s*$", before, re.I)
            marker_after = re.match(r"\s*(?:bdt|taka|tk\b|টাকা|৳|usd|eur|gbp|[$€£])", after, re.I)
            if not (marker_before or marker_after):
                if _non_money_number(before, after, clause, nearest_metric(before)):
                    continue
                # This is the existing educational ratio, not an amount. Its
                # dedicated evidence must be present; arbitrary ratios fail closed.
                if any(ev.evidence_id == "ev_general_budgeting_rule" and ev.unit == "%" for ev in evidence):
                    ratio = re.search(r"50/30/20", clause)
                    if ratio and ratio.start() <= match.start() < ratio.end():
                        continue
            value = Decimal(match.group().replace(",", ""))
            # Malformed grouping and sign-before-currency cannot lose information.
            if (match.start() and numeric_clause[match.start()-1] in ",.") or (
                match.end() < len(numeric_clause) and numeric_clause[match.end()] == ","
            ):
                return True
            if marker_before and re.search(r"-\s*$", before[:marker_before.start()]):
                value = -value
            if identity is None:
                terse = NUMBER.sub("", CURRENCY.sub("", clause)).strip(" :.,").lower()
                if terse in {"total", "total is", "total was"}:
                    identity = "expenses"
                elif re.match(r"\s*with\b", clause, re.I) and any(
                    f.category and f.category.lower() in clause.lower() for f in facts
                ):
                    identity = "expenses"
                else:
                    return True
            if identity == "unclassified_money":
                return True
            following_number = NUMBER.search(CURRENCY.sub(lambda token: " " * len(token.group()), after))
            following_words = after[:following_number.start()] if following_number else after
            following_identity = metric(following_words)
            if following_identity and following_identity != identity:
                return True
            # Unknown ISO-like currency codes are never silently treated as BDT.
            if re.search(r"\b(?!BDT\b|USD\b|EUR\b|GBP\b)[A-Z]{3}\b", clause):
                return True
            if re.search(r"not |never |unknown|unavailable|decreased by|increased by|fell by|rose by|কমেছে|বেড়েছে", clause, re.I):
                return True
            currency = "BDT"  # The existing app's implicit money unit.
            mentioned = set()
            currency_names = {"bdt": "BDT", "taka": "BDT", "tk": "BDT", "টাকা": "BDT", "৳": "BDT",
                              "usd": "USD", "$": "USD", "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP"}
            for token in currencies:
                mentioned.add(currency_names[token.lower()])
            if len(mentioned) > 1:
                return True
            if mentioned:
                currency = mentioned.pop()
            supported = False
            for fact in facts:
                ev = fact.evidence
                if fact.metric != identity or fact.value != value or (ev.unit or "BDT") != currency:
                    continue
                explicit_dates = [stamp.group() for stamp in dates]
                if ev.as_of_date != as_of and str(ev.as_of_date) not in explicit_dates:
                    continue
                if explicit_dates and str(ev.as_of_date) not in explicit_dates:
                    continue
                if ev.as_of_date != as_of and re.search(r"today|current|এখন|আজ", clause, re.I):
                    continue
                estimated = bool(ESTIMATE.search(clause))
                if ev.evidence_type == EvidenceType.ESTIMATE:
                    if not estimated or re.search(r"recorded|derived|নথিভুক্ত", clause, re.I):
                        continue
                elif estimated:
                    continue
                if ev.evidence_type == EvidenceType.RAW_DATA and re.search(r"\bderived\b", clause, re.I):
                    continue
                if fact.category and fact.category.lower() not in clause.lower():
                    continue
                supported = True
                break
            if not supported:
                return True
    return False
