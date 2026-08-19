REQUIRED_INPUT_FIELDS = {"project_id", "rule_id", "rule_version", "input"}
REQUIRED_OUTPUT_FIELDS = {"status", "events", "metrics"}


def validate_rule_input(message):
    missing = REQUIRED_INPUT_FIELDS - set(message)
    if missing:
        raise ValueError(f"Rule input thiếu field: {', '.join(sorted(missing))}.")


def validate_rule_output(message):
    missing = REQUIRED_OUTPUT_FIELDS - set(message)
    if missing:
        raise ValueError(f"Rule output thiếu field: {', '.join(sorted(missing))}.")
