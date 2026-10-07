"""Parsing for the JSON-valued env maps, shared by config and the setup wizard.

Dependency-free on purpose: config builds Settings at import, which the wizard must not trigger.
"""

import json


def _as_item_id(value: object) -> int:
    # bool is an int subclass and int(1.5) truncates — neither is a type id
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError(f"not an integer id: {value!r}")
    return int(value)


def parse_task_types(raw: str) -> dict[str, int] | None:
    """Task type names -> custom_item_id; None when raw is not a JSON object of integer IDs."""
    try:
        types = json.loads(raw)
        if isinstance(types, dict):
            return {str(k).lower(): _as_item_id(v) for k, v in types.items()}
    except (TypeError, ValueError):  # JSONDecodeError is a ValueError
        pass
    return None


def parse_team_labels(raw: str) -> dict[str, str] | None:
    """Team names -> label IDs; None when raw is not a JSON object of strings or integers."""
    try:
        labels = json.loads(raw)
        if isinstance(labels, dict) and all(
            isinstance(v, str) or (isinstance(v, int) and not isinstance(v, bool))
            for v in labels.values()
        ):
            return {str(k): str(v) for k, v in labels.items()}
    except (TypeError, ValueError):
        pass
    return None
