"""Deterministic evidence-grounded response validation service (AI-15S-E / AI-15S-K).

This service verifies that generated coach responses adhere strictly to verified evidence.
Any unsupported claims, non-existent evidence IDs, numerical contradictions, or
misleading financial language are filtered, repaired, or replaced with safe fallbacks.
No LLM is used for validation; all checks are deterministic.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.financial_coach import (
    CoachAction,
    CoachClaim,
    CoachEvidence,
    CoachIntent,
    CoachResponse,
    CoachWarning,
    EvidenceType,
)
from app.services.finance.financial_coach_evidence import EvidencePackage
from app.services.finance.financial_coach_generator import DeterministicFallbackGenerator

from app.services.finance.financial_coach_semantics import unsupported_financial_text

logger = logging.getLogger(__name__)

# Patterns for prohibited financial phrasing
GUARANTEE_PATTERN = re.compile(
    r"\b(guarantee|guaranteed|guaranteeing|guarantees|will definitely|100% certainty|100% certain|"
    r"100% guaranteed|risk-free|risk free|promised return|promised returns|promised profit|"
    r"assured return|assured returns|certain outcome|নিশ্চিত|শতভাগ নিশ্চিত|ঝুঁকিমুক্ত)\b",
    re.IGNORECASE,
)

EXECUTED_ACTION_PATTERN = re.compile(
    r"\b(i have paid|i have transferred|i have sent|i transferred|i completed the transaction|"
    r"i executed|bill has been paid|money was sent|account has been debited|we deducted|"
    r"has been transferred|was debited|payment was made|payment completed|transaction completed|"
    r"টাকা পাঠিয়েছি|পরিশোধ করেছি|টাকা কেটে নেওয়া হয়েছে)\b",
    re.IGNORECASE,
)

# Bengali numeral mapping
BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

NUMBER_WORDS = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|"
    r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"lakh|lac|million|crore"
)
SPELLED_MONEY_PATTERN = re.compile(
    rf"\b(?:{NUMBER_WORDS})(?:[\s-]+(?:{NUMBER_WORDS}))*"
    rf"\s+(?:taka|bdt|tk|টাকা)\b",
    re.IGNORECASE,
)


def contains_unverified_spelled_money(text: str) -> bool:
    if not text:
        return False
    if SPELLED_MONEY_PATTERN.search(text):
        return True
    words = rf"(?:{NUMBER_WORDS}|nil|শূন্য|এক|দুই|তিন|চার|পাঁচ|ছয়|ছয়|সাত|আট|নয়|নয়|দশ|বিশ|হাজার|লাখ|কোটি)"
    prefix = rf"(?:৳|\b(?:bdt|taka|tk)|টাকা)\s*[:=]?\s*{words}(?!\w)"
    implicit = (
        rf"(?:cash|balance|income|expenses?|spending|savings|reserve|fund|capacity)"
        rf"\s+(?:is|are|equals?|of|at|:)\s+{words}(?!\w)"
    )
    bengali = rf"{words}[\u0980-\u09ff\s-]*\s+টাকা"
    if re.search(prefix + "|" + implicit + "|" + bengali, text, re.I):
        return True
    # Adverbs and intervening prose must not turn an asserted word amount into
    # an unvalidated claim. Ordinary counts remain nonmonetary.
    assertion = (
        r"\b(?:cash|balance|income|expenses?|spending|savings|reserve|fund|capacity)\b"
        r"|নগদ|ব্যালান্স|সঞ্চয়|সঞ্চয়|আয়|আয়|ব্যয়|ব্যয়|খরচ|তহবিল"
    )
    count_unit = r"\s+(?:transactions?|accounts?|days?|weeks?|months?|years?|goals?|categories?|steps?|ways?)\b"
    for clause in re.split(r"[.;!?।\n]", text):
        if not re.search(assertion, clause, re.I):
            continue
        for number in re.finditer(rf"(?<!\w){words}(?!\w)", clause, re.I):
            if not re.match(count_unit, clause[number.end():], re.I):
                return True
    return False


# Regex to detect explicit BDT / currency amounts without mistaking ordinary numbers
# (e.g. dates like 2026, counts like 12 transactions, percentages like 15%, durations like 3 months)
CURRENCY_NUMBER_PATTERN = re.compile(
    r"(?:৳|bdt|taka|tk|টাকা)\.?\s*([+-]?[0-9০-৯]+(?:,[0-9০-৯]{3})*(?:\.[0-9০-৯]{1,2})?)"
    r"|([+-]?[0-9০-৯]+(?:,[0-9০-৯]{3})*(?:\.[0-9০-৯]{1,2})?)\s*(?:৳|bdt|taka|tk|টাকা)",
    re.IGNORECASE,
)

# Deterministic substitutions for safe repair of guarantee phrasing
GUARANTEE_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(is|are|was|were)\s+guaranteed\s+to\b", re.IGNORECASE), r"\1 projected to"),
    (re.compile(r"\b(you|we|they)\s+will\s+definitely\b", re.IGNORECASE), r"\1 can expect to"),
    (re.compile(r"\b(it|this|that)\s+will\s+definitely\b", re.IGNORECASE), r"\1 is expected to"),
    (re.compile(r"\bwill\s+definitely\b", re.IGNORECASE), "is projected to"),
    (re.compile(r"\b100%\s+certainty\b", re.IGNORECASE), "high likelihood"),
    (re.compile(r"\b100%\s+certain\b", re.IGNORECASE), "expected"),
    (re.compile(r"\b100%\s+guaranteed\b", re.IGNORECASE), "projected"),
    (re.compile(r"\brisk-free\b", re.IGNORECASE), "lower-risk"),
    (re.compile(r"\brisk\s+free\b", re.IGNORECASE), "lower-risk"),
    (re.compile(r"\bpromised\s+returns?\b", re.IGNORECASE), "estimated return"),
    (re.compile(r"\bassured\s+returns?\b", re.IGNORECASE), "estimated return"),
    (re.compile(r"\bguaranteed\b", re.IGNORECASE), "projected"),
    (re.compile(r"\bguarantees\b", re.IGNORECASE), "projects"),
    (re.compile(r"\bguarantee\b", re.IGNORECASE), "estimate"),
    (re.compile(r"\bশতভাগ নিশ্চিত\b", re.IGNORECASE), "সম্ভাব্য"),
    (re.compile(r"\bনিশ্চিত\b", re.IGNORECASE), "সম্ভাব্য"),
    (re.compile(r"\bঝুঁকিমুক্ত\b", re.IGNORECASE), "কম ঝুঁকিপূর্ণ"),
]


@dataclass
class ValidationReport:
    """Audit report for response validation."""

    is_valid: bool
    repaired: bool
    issues: list[str] = field(default_factory=list)
    dropped_claims_count: int = 0
    dropped_actions_count: int = 0


def _extract_text_amounts(text: str) -> list[Decimal]:
    """Extract all explicit BDT/monetary figures mentioned in text."""
    if not text:
        return []
    amounts: list[Decimal] = []
    for match in CURRENCY_NUMBER_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            try:
                cleaned = raw.translate(BENGALI_DIGITS).replace(",", "")
                amt = Decimal(cleaned)
                amounts.append(amt)
            except (InvalidOperation, TypeError):
                continue
    return amounts


def _extract_numbers_from_value(val: Any, numbers: set[Decimal]) -> None:
    """Extract numeric amounts from an evidence value without treating missing data as 0."""
    if val is None:
        return
    if isinstance(val, (int, float, Decimal)):
        try:
            d = Decimal(str(val))
            numbers.add(d)
            if d == d.to_integral_value():
                numbers.add(d.to_integral_value())
        except (InvalidOperation, TypeError):
            pass
    elif isinstance(val, dict):
        for k, v in val.items():
            # Skip non-currency metrics like percentages, counts, days, months
            k_lower = str(k).lower()
            if any(skip in k_lower for skip in ("percentage", "percent", "count", "days", "months", "score")):
                continue
            _extract_numbers_from_value(v, numbers)
    elif isinstance(val, (list, tuple)):
        for v in val:
            _extract_numbers_from_value(v, numbers)


def _extract_evidence_numbers_by_id(evidence_list: list[CoachEvidence]) -> dict[str, set[Decimal]]:
    """Map each evidence item to the set of supported numeric values."""
    mapping: dict[str, set[Decimal]] = {}
    for ev in evidence_list:
        nums: set[Decimal] = set()
        _extract_numbers_from_value(ev.value, nums)
        mapping[ev.evidence_id] = nums
    return mapping


def _extract_all_evidence_numbers(evidence_list: list[CoachEvidence]) -> set[Decimal]:
    """Gather all numeric values present across the evidence package."""
    numbers: set[Decimal] = set()
    for ev in evidence_list:
        _extract_numbers_from_value(ev.value, numbers)
    return numbers


def _repair_guarantee_text(text: str) -> str:
    """Safely replace prohibited guarantee phrasing with projection/estimate wording."""
    res = text
    for pattern, repl in GUARANTEE_REPLACEMENTS:
        res = pattern.sub(repl, res)
    return res


class FinancialCoachValidator:
    """Validates and enforces deterministic grounding on CoachResponses."""

    def __init__(self, package: EvidencePackage, language: str = "en") -> None:
        self.package = package
        self.language = language
        self.valid_evidence_ids = package.evidence_ids
        self.evidence_by_id: dict[str, CoachEvidence] = {
            ev.evidence_id: ev for ev in package.evidence
        }
        self.evidence_numbers_by_id = _extract_evidence_numbers_by_id(package.evidence)
        self.valid_evidence_numbers = _extract_all_evidence_numbers(package.evidence)
        self.missing_data_keys = set(package.missing_data)

    def _safe_fallback(self, response: CoachResponse) -> CoachResponse:
        fallback = DeterministicFallbackGenerator.generate(self.package, "fallback", self.language)
        # Validate every fallback surface with its own references, even when the
        # amount happens to exist elsewhere in the package.
        fallback.claims = [claim for claim in fallback.claims
            if claim.evidence_ids and set(claim.evidence_ids) <= self.valid_evidence_ids
            and not unsupported_financial_text(claim.text,
                [ev for ev in self.package.evidence if ev.evidence_id in claim.evidence_ids], self.package.as_of_date)]
        fallback.actions = [action for action in fallback.actions
            if set(action.evidence_ids) <= self.valid_evidence_ids
            and not unsupported_financial_text(action.title + " " + action.description,
                [ev for ev in self.package.evidence if ev.evidence_id in action.evidence_ids], self.package.as_of_date)]
        for action in fallback.actions:
            action.action_type = "personalized" if action.evidence_ids else "general_guidance"
        if unsupported_financial_text(fallback.answer, self.package.evidence, self.package.as_of_date):
            from app.services.finance.financial_coach_semantics import financial_facts
            lines = ["Required information is unavailable; recorded amounts do not establish available cash."]
            if self.language == "bn":
                lines = ["প্রয়োজনীয় তথ্য অনুপলব্ধ; নথিভুক্ত অঙ্ক থেকে ব্যবহারযোগ্য নগদ জানা যায় না।"]
            for fact in financial_facts(self.package.evidence):
                ev = fact.evidence
                # Fixed metric names, not free-form producer labels, describe the
                # amount. Category data remains explicitly quoted metadata.
                category = f" for category {json.dumps(fact.category, ensure_ascii=False)}" if fact.category else ""
                line = (f"{fact.metric.replace('_', ' ')}{category}: {fact.value} {ev.unit or 'BDT'} "
                        f"({ev.evidence_type.value}; as of {ev.as_of_date}).")
                if not unsupported_financial_text(line, [ev], self.package.as_of_date):
                    lines.append(line)
            fallback.answer = "\n".join(lines)
        if fallback.summary and unsupported_financial_text(fallback.summary, self.package.evidence, self.package.as_of_date):
            fallback.summary = None
        fallback.warnings = [warning for warning in fallback.warnings
            if not unsupported_financial_text(warning.message, self.package.evidence, self.package.as_of_date)]
        fallback.limitations = [text for text in fallback.limitations
            if not unsupported_financial_text(text, self.package.evidence, self.package.as_of_date)]
        fallback.evidence = [ev.model_copy(deep=True) for ev in self.package.evidence]
        fallback.conversation_id = response.conversation_id
        return fallback

    def validate(self, response: CoachResponse) -> tuple[CoachResponse, ValidationReport]:
        """Validate response against evidence; return sanitized response and report.

        Ensures user-visible text (answer, summary, claims, actions) contains only
        verified amounts, distinguishes estimates from historical facts, and rejects
        guarantees and execution claims. Does not mutate the caller's input objects.
        """
        report = ValidationReport(is_valid=True, repaired=False)
        issues: list[str] = []

        # 1. Prohibited execution phrasing in answer or summary
        if EXECUTED_ACTION_PATTERN.search(response.answer) or (
            response.summary and EXECUTED_ACTION_PATTERN.search(response.summary)
        ):
            issues.append("Answer or summary claims to have executed a financial transaction or payment.")
            logger.warning("Validation failure: execution language detected.")
            fallback = self._safe_fallback(response)
            fallback.conversation_id = response.conversation_id
            fallback.warnings.append(
                CoachWarning(
                    code="VALIDATION_REPAIRED_LANGUAGE",
                    message="The assistant cannot execute financial operations; safe guidance is shown.",
                )
            )
            return fallback, ValidationReport(
                is_valid=False,
                repaired=True,
                issues=issues,
            )

        # Clone response to prevent unexpected mutations to caller objects
        resp = response.model_copy(deep=True)
        resp.evidence = [ev.model_copy(deep=True) for ev in self.package.evidence]

        # Review text and every associated surface are canonical projections.
        # Arbitrary model prose cannot establish order, prerequisites or authorization.
        if self.package.intent == CoachIntent.FINANCIAL_REVIEW:
            resp = DeterministicFallbackGenerator.generate(self.package, "review", self.language)
            resp.conversation_id = response.conversation_id

        resp.warnings = [warning for warning in resp.warnings
            if not unsupported_financial_text(warning.message, self.package.evidence, self.package.as_of_date)]
        resp.limitations = [text for text in resp.limitations
            if not unsupported_financial_text(text, self.package.evidence, self.package.as_of_date)]

        # 2. Prohibited guarantee phrasing in answer
        if GUARANTEE_PATTERN.search(resp.answer):
            issues.append("Answer contains prohibited guarantee phrasing.")
            logger.warning("Validation warning: guarantee phrasing detected in answer.")
            repaired_answer = _repair_guarantee_text(resp.answer)
            if GUARANTEE_PATTERN.search(repaired_answer):
                # Unrepairable guarantee language: fall back to safe deterministic response
                issues.append("Guarantee language could not be safely repaired; reverting to deterministic fallback.")
                fallback = self._safe_fallback(response)
                fallback.conversation_id = resp.conversation_id
                fallback.warnings.append(
                    CoachWarning(
                        code="UNSUPPORTED_GUARANTEE_CAVEAT",
                        message="Projections and estimates are informative and not guaranteed financial outcomes.",
                    )
                )
                return fallback, ValidationReport(
                    is_valid=False,
                    repaired=True,
                    issues=issues,
                )
            resp.answer = repaired_answer
            report.repaired = True
            resp.warnings.append(
                CoachWarning(
                    code="UNSUPPORTED_GUARANTEE_CAVEAT",
                    message="Projections and estimates are informative and not guaranteed financial outcomes.",
                )
            )

        # 3. Prohibited guarantee phrasing in summary
        if resp.summary and GUARANTEE_PATTERN.search(resp.summary):
            repaired_sum = _repair_guarantee_text(resp.summary)
            if GUARANTEE_PATTERN.search(repaired_sum):
                resp.summary = None
            else:
                resp.summary = repaired_sum
            report.repaired = True

        # Semantic checks use only the evidence referenced by each item.
        for claim in list(resp.claims):
            if contains_unverified_spelled_money(claim.text):
                resp.claims.remove(claim)
                report.dropped_claims_count += 1
                issues.append(
                    f"Claim '{claim.claim_id}' contains a spelled-out monetary amount "
                    f"that cannot be independently verified."
                )
                continue
            relevant = [ev for ev in self.package.evidence if ev.evidence_id in claim.evidence_ids]
            if unsupported_financial_text(claim.text, relevant, self.package.as_of_date):
                resp.claims.remove(claim)
                report.dropped_claims_count += 1
                issues.append(f"Claim '{claim.claim_id}' has unsupported financial meaning.")
        for action in list(resp.actions):
            action_text = f"{action.title} {action.description}"
            if contains_unverified_spelled_money(action_text):
                resp.actions.remove(action)
                report.dropped_actions_count += 1
                issues.append(
                    f"Action '{action.action_id}' contains a spelled-out monetary amount "
                    f"that cannot be independently verified."
                )
                continue
            relevant = [ev for ev in self.package.evidence if ev.evidence_id in action.evidence_ids]
            if unsupported_financial_text(action_text, relevant, self.package.as_of_date):
                resp.actions.remove(action)
                report.dropped_actions_count += 1
                issues.append(f"Action '{action.action_id}' has unsupported financial meaning.")
        if contains_unverified_spelled_money(resp.answer):
            fallback = self._safe_fallback(response)
            fallback.conversation_id = response.conversation_id
            return fallback, ValidationReport(
                is_valid=False,
                repaired=True,
                issues=[
                    "Answer contains a spelled-out monetary amount "
                    "that cannot be independently verified."
                ],
            )
        if unsupported_financial_text(resp.answer, self.package.evidence, self.package.as_of_date):
            return self._safe_fallback(resp), ValidationReport(
                is_valid=False, repaired=True,
                issues=issues + ["Answer has unsupported financial meaning."],
                dropped_claims_count=report.dropped_claims_count,
                dropped_actions_count=report.dropped_actions_count,
            )
        if resp.summary:
            if contains_unverified_spelled_money(resp.summary):
                issues.append(
                    "Summary contains a spelled-out monetary amount "
                    "that cannot be independently verified."
                )
                resp.summary = None
                report.repaired = True
            elif unsupported_financial_text(resp.summary, self.package.evidence, self.package.as_of_date):
                resp.summary = None
                report.repaired = True
                issues.append("Summary has unsupported financial meaning.")
        if response.claims and not resp.claims:
            return self._safe_fallback(resp), ValidationReport(
                is_valid=False, repaired=True, issues=issues,
                dropped_claims_count=report.dropped_claims_count,
                dropped_actions_count=report.dropped_actions_count,
            )

        # 4. Numerical grounding for explicit BDT amounts in answer
        if contains_unverified_spelled_money(resp.answer):
            fallback = self._safe_fallback(response)
            fallback.conversation_id = response.conversation_id
            return fallback, ValidationReport(
                is_valid=False,
                repaired=True,
                issues=[
                    "Answer contains a spelled-out monetary amount "
                    "that cannot be independently verified."
                ],
            )
        answer_amounts = _extract_text_amounts(resp.answer)
        for amt in answer_amounts:
            matched = any(
                amt == ev_num or abs(amt - ev_num) < Decimal("0.01")
                for ev_num in self.valid_evidence_numbers
            )
            if not matched:
                issues.append(
                    f"Answer cites {amt} BDT which is not supported by structured evidence."
                )
                logger.warning("Validation failure: unsupported amount %s BDT in answer.", amt)
                # An unsupported financial assertion in the primary answer cannot be safely guessed
                fallback = self._safe_fallback(response)
                fallback.conversation_id = resp.conversation_id
                fallback.warnings.extend(resp.warnings)
                return fallback, ValidationReport(
                    is_valid=False,
                    repaired=True,
                    issues=issues,
                )

        # 5. Numerical grounding for explicit BDT amounts in summary
        if resp.summary:
            summary_amounts = _extract_text_amounts(resp.summary)
            summary_has_unsupported = False
            for amt in summary_amounts:
                matched = any(
                    amt == ev_num or abs(amt - ev_num) < Decimal("0.01")
                    for ev_num in self.valid_evidence_numbers
                )
                if not matched:
                    issues.append(
                        f"Summary cites {amt} BDT which is not supported by structured evidence."
                    )
                    summary_has_unsupported = True
                    break
            if summary_has_unsupported:
                # Safely repair by removing misleading summary
                resp.summary = None
                report.repaired = True

        # 6. Validate claims (relevant evidence matching & estimate grounding)
        valid_claims: list[CoachClaim] = []
        for claim in resp.claims:
            claim_copy = claim.model_copy(deep=True)

            # Check 6a: Claim must reference at least one evidence ID
            if not claim_copy.evidence_ids:
                issues.append(f"Claim '{claim_copy.claim_id}' has no referenced evidence IDs.")
                report.dropped_claims_count += 1
                continue

            # Check 6b: All referenced evidence IDs must exist in package
            unknown_ids = [eid for eid in claim_copy.evidence_ids if eid not in self.valid_evidence_ids]
            if unknown_ids:
                issues.append(f"Claim '{claim_copy.claim_id}' references unknown evidence IDs: {unknown_ids}.")
                report.dropped_claims_count += 1
                continue

            # Check 6c: Claim must not contain guarantee or execution phrasing
            if GUARANTEE_PATTERN.search(claim_copy.text) or EXECUTED_ACTION_PATTERN.search(claim_copy.text):
                issues.append(f"Claim '{claim_copy.claim_id}' contains guarantee or execution phrasing.")
                report.dropped_claims_count += 1
                continue

            # Check 6d: Estimate presented as guaranteed fact
            has_estimate = any(
                self.evidence_by_id.get(eid) and self.evidence_by_id[eid].evidence_type == EvidenceType.ESTIMATE
                for eid in claim_copy.evidence_ids
            )
            if has_estimate and GUARANTEE_PATTERN.search(claim_copy.text):
                issues.append(f"Claim '{claim_copy.claim_id}' presents an estimate as a guaranteed fact.")
                report.dropped_claims_count += 1
                continue

            # Check 6e: Spelled-out monetary amount that cannot be independently verified
            if contains_unverified_spelled_money(claim_copy.text):
                issues.append(
                    f"Claim '{claim_copy.claim_id}' contains a spelled-out monetary amount "
                    f"that cannot be independently verified."
                )
                report.dropped_claims_count += 1
                continue

            # Check 6f: Numerical grounding against RELEVANT evidence referenced by this claim
            claim_amounts = _extract_text_amounts(claim_copy.text)
            relevant_numbers: set[Decimal] = set()
            for eid in claim_copy.evidence_ids:
                relevant_numbers.update(self.evidence_numbers_by_id.get(eid, set()))

            contradiction_found = False
            for amt in claim_amounts:
                matched = any(
                    amt == ev_num or abs(amt - ev_num) < Decimal("0.01")
                    for ev_num in relevant_numbers
                )
                if not matched:
                    issues.append(
                        f"Claim '{claim_copy.claim_id}' cites {amt} BDT which is not supported by its referenced evidence."
                    )
                    contradiction_found = True
                    break

            if contradiction_found:
                report.dropped_claims_count += 1
                continue

            valid_claims.append(claim_copy)

        # 7. Validate actions (enforce evidence references and classification)
        valid_actions: list[CoachAction] = []
        for action in resp.actions:
            action_copy = action.model_copy(deep=True)

            # Check 7a: Action must not contain execution phrasing or guarantee language
            if (
                EXECUTED_ACTION_PATTERN.search(action_copy.title)
                or EXECUTED_ACTION_PATTERN.search(action_copy.description)
                or GUARANTEE_PATTERN.search(action_copy.title)
                or GUARANTEE_PATTERN.search(action_copy.description)
            ):
                issues.append(f"Action '{action_copy.action_id}' contains execution or guarantee phrasing.")
                report.dropped_actions_count += 1
                continue

            # Check 7b: Extract any explicit BDT amounts in title or description
            action_text = f"{action_copy.title} {action_copy.description}"
            if contains_unverified_spelled_money(action_text):
                issues.append(
                    f"Action '{action_copy.action_id}' contains a spelled-out monetary amount "
                    f"that cannot be independently verified."
                )
                report.dropped_actions_count += 1
                continue

            action_amounts = _extract_text_amounts(action_text)

            # Case A: Action has evidence references
            if action_copy.evidence_ids:
                # All referenced IDs must be valid
                unknown_ids = [eid for eid in action_copy.evidence_ids if eid not in self.valid_evidence_ids]
                if unknown_ids:
                    issues.append(
                        f"Action '{action_copy.action_id}' references unknown evidence IDs: {unknown_ids}."
                    )
                    report.dropped_actions_count += 1
                    continue

                # Any explicit BDT amounts must match the referenced evidence numbers
                relevant_numbers = set()
                for eid in action_copy.evidence_ids:
                    relevant_numbers.update(self.evidence_numbers_by_id.get(eid, set()))

                unsupported_action_amount = False
                for amt in action_amounts:
                    matched = any(
                        amt == ev_num or abs(amt - ev_num) < Decimal("0.01")
                        for ev_num in relevant_numbers
                    )
                    if not matched:
                        issues.append(
                            f"Action '{action_copy.action_id}' cites unsupported amount {amt} BDT."
                        )
                        unsupported_action_amount = True
                        break

                if unsupported_action_amount:
                    report.dropped_actions_count += 1
                    continue

                action_copy.action_type = "personalized"
                valid_actions.append(action_copy)

            # Case B: Action has NO evidence references
            else:
                if action_amounts:
                    # Action mentions explicit BDT amounts without supporting evidence -> drop
                    issues.append(
                        f"Action '{action_copy.action_id}' cites amounts {action_amounts} without evidence grounding."
                    )
                    report.dropped_actions_count += 1
                    continue

                # Useful general advice without pretending to be personalized -> classify as general_guidance
                action_copy.action_type = "general_guidance"
                valid_actions.append(action_copy)

        # 8. Check claim drop threshold
        if len(resp.claims) > 0 and len(valid_claims) == 0:
            issues.append("All claims failed evidence grounding; falling back to deterministic answer.")
            fallback = self._safe_fallback(response)
            fallback.conversation_id = resp.conversation_id
            fallback.warnings.extend(resp.warnings)
            return fallback, ValidationReport(
                is_valid=False,
                repaired=True,
                issues=issues,
                dropped_claims_count=report.dropped_claims_count,
                dropped_actions_count=report.dropped_actions_count,
            )

        report.issues = issues
        if report.dropped_claims_count > 0 or report.dropped_actions_count > 0:
            report.repaired = True

        resp.claims = valid_claims
        resp.actions = valid_actions

        return resp, report


def validate_coach_response(
    response: CoachResponse,
    package: EvidencePackage,
    language: str = "en",
) -> tuple[CoachResponse, ValidationReport]:
    """Convenience functional interface for validating a coach response."""
    validator = FinancialCoachValidator(package, language)
    return validator.validate(response)
