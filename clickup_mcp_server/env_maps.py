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
    """Task type names -> custom_item_id; None when raw is not a JSON object of integer IDs,
    or two names differ only in case."""
    try:
        types = json.loads(raw)
        if isinstance(types, dict):
            mapping = {str(k).casefold(): _as_item_id(v) for k, v in types.items()}
            # Two names that differ only in case would leave the winner to key order.
            if len(mapping) == len(types):
                return mapping
    except (TypeError, ValueError):  # JSONDecodeError is a ValueError
        pass
    return None


def parse_team_labels(raw: str) -> dict[str, str] | None:
    """Team names -> label IDs; None when raw is not a JSON object of non-blank strings or integers,
    or two names differ only in case."""
    try:
        labels = json.loads(raw)
        if isinstance(labels, dict) and all(
            (isinstance(v, str) and v.strip())
            or (isinstance(v, int) and not isinstance(v, bool))
            for v in labels.values()
        ):
            # Lookups casefold the caller's team name, so the keys must be casefolded too.
            mapping = {str(k).casefold(): str(v) for k, v in labels.items()}
            if len(mapping) == len(labels):
                return mapping
    except (TypeError, ValueError):
        pass
    return None
