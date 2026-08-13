from collections import Counter

from .contracts import EvaluationResult


class GroundTruthValidationEvaluator:
    """First runnable evaluator; validates an immutable GT snapshot."""

    def evaluate(self, run):
        release = run.test_case.ground_truth_release
        if release is None:
            return EvaluationResult(
                metrics={},
                assertion_results=[{"name": "gt_release_exists", "passed": False}],
                status="ERROR",
            )

        items = release.items.all()
        labels = Counter(items.values_list("label", flat=True))
        frame_count = items.values("frame_index").distinct().count()
        metrics = {
            "annotation_count": items.count(),
            "annotated_frame_count": frame_count,
            "label_counts": dict(labels),
            "coverage": release.coverage,
        }
        assertions = run.test_case.assertions or []
        results = []
        for assertion in assertions:
            metric = assertion.get("metric")
            operator = assertion.get("operator", ">=")
            expected = assertion.get("value")
            actual = metrics.get(metric)
            passed = _compare(actual, operator, expected)
            results.append({**assertion, "actual": actual, "passed": passed})

        status = "PASSED" if all(item["passed"] for item in results) else "FAILED"
        return EvaluationResult(metrics=metrics, assertion_results=results, status=status)


def _compare(actual, operator, expected):
    if actual is None or expected is None:
        return False
    operations = {
        ">=": lambda: actual >= expected,
        ">": lambda: actual > expected,
        "<=": lambda: actual <= expected,
        "<": lambda: actual < expected,
        "==": lambda: actual == expected,
    }
    return operations.get(operator, lambda: False)()


EVALUATORS = {"GT_VALIDATION": GroundTruthValidationEvaluator}

