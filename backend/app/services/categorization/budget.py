from dataclasses import dataclass

DEFAULT_CATEGORIZATION_BUDGET: int = 5


@dataclass
class CategorizationBudget:
    max_calls: int = DEFAULT_CATEGORIZATION_BUDGET
    calls_used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls - self.calls_used)

    def can_call(self) -> bool:
        return self.remaining > 0

    def consume(self) -> bool:
        if not self.can_call():
            return False
        self.calls_used += 1
        return True
