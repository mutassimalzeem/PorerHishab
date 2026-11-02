"""Deterministic evidence-grounded response validation service (AI-15S-E).

This service verifies that generated coach responses adhere strictly to verified evidence.
Any unsupported claims, non-existent evidence IDs, numerical contradictions, or
misleading financial language are filtered, repaired, or replaced with safe fallbacks.
No LLM is used for validation; all checks are deterministic.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.financial_coach import (
    CoachAction,
    CoachClaim,
    CoachEvidence,
    CoachResponse,
    CoachWarning,
)
from app.services.finance.financial_coach_evidence import EvidencePackage
from app.services.finance.financial_coach_generator import DeterministicFallbackGenerator

logger = logging.getLogger(__name__)

# Patterns for prohibited financial phrasing
GUARANTEE_PATTERN = re.compile(
    r"\b(guarantee|guaranteed|will definitely|100% certainty|risk-free|promised return)\b",
    re.IGNORECASE,
)

EXECUTED_ACTION_PATTERN = re.compile(
    r"\b(i have paid|i have transferred|i have sent|i transferred|i completed the transaction|"
    r"i executed|bill has been paid|money was sent|account has been debited|we deducted)\b",
    re.IGNORECASE,
)

# Number extraction from text
CURRENCY_NUMBER_PATTERN = re.compile(
    r"(?:৳|bdt\s*)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)"
    r"|([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)\s*(?:bdt|taka|tk)\b",
    re.IGNORECASE,
)


@dataclass
class ValidationReport:
    """Audit report for response validation."""

    is_valid: bool
    repaired: bool
    issues: list[str] = field(default_factory=list)
    dropped_claims_count: int = 0
    dropped_actions_count: int = 0


def _extract_all_evidence_numbers(evidence_list: list[CoachEvidence]) -> set[Decimal]:
    """Gather all numeric values present in the evidence package."""
    numbers: set[Decimal] = set()

    def add_val(val: Any) -> None:
        if isinstance(val, (int, float, Decimal)):
            try:
                d = Decimal(str(val))
                numbers.add(d)
                # Also allow truncated integer if decimal has .00
                if d == d.to_integral_value():
                    numbers.add(d.to_integral_value())
            except (InvalidOperation, TypeError):
                pass
        elif isinstance(val, dict):
            for v in val.values():
                add_val(v)
        elif isinstance(val, (list, tuple)):
            for v in val:
                add_val(v)

    for ev in evidence_list:
        add_val(ev.value)

    return numbers


def _extract_text_amounts(text: str) -> list[Decimal]:
    """Extract all explicit BDT/monetary figures mentioned in text."""
    amounts: list[Decimal] = []
    for match in CURRENCY_NUMBER_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            try:
                amt = Decimal(raw.replace(",", ""))
                amounts.append(amt)
            except (InvalidOperation, TypeError):
                continue
    return amounts


class FinancialCoachValidator:
    """Validates and enforces deterministic grounding on CoachResponses."""

    def __init__(self, package: EvidencePackage, language: str = "en") -> None:
        self.package = package
        self.language = language
        self.valid_evidence_ids = package.evidence_ids
        self.valid_evidence_numbers = _extract_all_evidence_numbers(package.evidence)

    def validate(self, response: CoachResponse) -> tuple[CoachResponse, ValidationReport]:
        """Validate response against evidence; return sanitized response and report."""
        report = ValidationReport(is_valid=True, repaired=False)
        issues: list[str] = []

        # 1. Prohibited execution phrasing in answer
        if EXECUTED_ACTION_PATTERN.search(response.answer):
            issues.append("Answer claims to have executed a financial transaction or payment.")
            logger.warning("Validation failure: execution language detected in answer.")
            fallback = DeterministicFallbackGenerator.generate(
                self.package, "fallback", self.language
            )
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

        # 2. Prohibited guarantee phrasing
        if GUARANTEE_PATTERN.search(response.answer):
            issues.append("Answer contains prohibited guarantee phrasing.")
            logger.warning("Validation warning: guarantee phrasing detected.")
            # We can flag a warning rather than discarding if claims are sound, or add caveat
            response.warnings.append(
                CoachWarning(
                    code="UNSUPPORTED_GUARANTEE_CAVEAT",
                    message="Projections and estimates are informative and not guaranteed financial outcomes.",
                )
            )
            report.repaired = True

        # 3. Validate claims
        valid_claims: list[CoachClaim] = []
        for claim in response.claims:
            # Check 3a: Claim must reference at least one evidence ID
            if not claim.evidence_ids:
                issues.append(f"Claim '{claim.claim_id}' has no referenced evidence IDs.")
                report.dropped_claims_count += 1
                continue

            # Check 3b: All referenced evidence IDs must exist in package
            unknown_ids = [eid for eid in claim.evidence_ids if eid not in self.valid_evidence_ids]
            if unknown_ids:
                issues.append(f"Claim '{claim.claim_id}' references unknown evidence IDs: {unknown_ids}.")
                report.dropped_claims_count += 1
                continue

            # Check 3c: Numerical grounding in claim text
            claim_amounts = _extract_text_amounts(claim.text)
            contradiction_found = False
            for amt in claim_amounts:
                # If an explicit monetary amount is cited, verify it matches evidence values
                # Allow minor tolerance or exact match
                matched = any(
                    amt == ev_num or abs(amt - ev_num) < Decimal("0.01")
                    for ev_num in self.valid_evidence_numbers
                )
                if not matched:
                    issues.append(
                        f"Claim '{claim.claim_id}' cites {amt} BDT which is not supported by structured evidence."
                    )
                    contradiction_found = True
                    break

            if contradiction_found:
                report.dropped_claims_count += 1
                continue

            valid_claims.append(claim)

        # 4. Validate actions
        valid_actions: list[CoachAction] = []
        for action in response.actions:
            # Action must not contain execution phrasing
            if EXECUTED_ACTION_PATTERN.search(action.title) or EXECUTED_ACTION_PATTERN.search(action.description):
                issues.append(f"Action '{action.action_id}' implies executed transactions.")
                report.dropped_actions_count += 1
                continue

            # If action makes personalized recommendations citing evidence, verify IDs
            unknown_ids = [eid for eid in action.evidence_ids if eid not in self.valid_evidence_ids]
            if unknown_ids:
                issues.append(f"Action '{action.action_id}' references unknown evidence IDs: {unknown_ids}.")
                # Filter out unknown IDs but keep action if general, or drop if personalized
                action.evidence_ids = [eid for eid in action.evidence_ids if eid in self.valid_evidence_ids]

            valid_actions.append(action)

        # If too many claims were dropped or if answer had contradictions
        if len(response.claims) > 0 and len(valid_claims) == 0:
            issues.append("All claims failed evidence grounding; falling back to deterministic answer.")
            fallback = DeterministicFallbackGenerator.generate(
                self.package, "fallback", self.language
            )
            fallback.conversation_id = response.conversation_id
            fallback.warnings.extend(response.warnings)
            return fallback, ValidationReport(
                is_valid=False,
                repaired=True,
                issues=issues,
                dropped_claims_count=report.dropped_claims_count,
            )

        report.issues = issues
        if report.dropped_claims_count > 0 or report.dropped_actions_count > 0:
            report.repaired = True

        response.claims = valid_claims
        response.actions = valid_actions

        return response, report


def validate_coach_response(
    response: CoachResponse,
    package: EvidencePackage,
    language: str = "en",
) -> tuple[CoachResponse, ValidationReport]:
    """Convenience functional interface for validating a coach response."""
    validator = FinancialCoachValidator(package, language)
    return validator.validate(response)
