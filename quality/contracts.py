from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class EvaluationResult:
    metrics: dict[str, Any]
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "PASSED"


class Evaluator(Protocol):
    def evaluate(self, run) -> EvaluationResult: ...

