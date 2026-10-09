"""Parsing for the JSON-valued env maps, shared by config and the setup wizard.

Dependency-free on purpose: config builds Settings at import, which the wizard must not trigger.
"""

import json


def _as_item_id(value: object) -> int:
    # bool is an int subclass and int(1.5) truncates — neither is a type id
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError(f"not an integer id: {value!r}")
    return int(value)


def _unique_names(pairs: list[tuple[str, object]]) -> dict[str, object]:
    # json.loads keeps the last of two equal keys, which would leave the winner to key order.
    names = [k.casefold() for k, _ in pairs]
    if len(set(names)) != len(names):
        raise ValueError("a name is given twice, ignoring case")
    return {name: v for name, (_, v) in zip(names, pairs, strict=True)}


def parse_task_types(raw: str) -> dict[str, int] | None:
    """Task type names -> custom_item_id; None when raw is not a JSON object of integer IDs,
    or gives one name twice ignoring case."""
    try:
        types = json.loads(raw, object_pairs_hook=_unique_names)
        if isinstance(types, dict):
            return {k: _as_item_id(v) for k, v in types.items()}
    except (TypeError, ValueError):  # JSONDecodeError is a ValueError
        pass
    return None


def parse_team_labels(raw: str) -> dict[str, str] | None:
    """Team names -> label IDs; None when raw is not a JSON object of non-blank strings or integers,
    or gives one name twice ignoring case."""
    try:
        labels = json.loads(raw, object_pairs_hook=_unique_names)
        if isinstance(labels, dict) and all(
            (isinstance(v, str) and v.strip())
            or (isinstance(v, int) and not isinstance(v, bool))
            for v in labels.values()
        ):
            return {k: str(v) for k, v in labels.items()}
    except (TypeError, ValueError):
        pass
    return None
