import re

from mcp.server.mcpserver.exceptions import ToolError

from clickup_mcp_server.client import (
    ClickUpInputError,
    clickup_client,
    parse_response,
    validate_space_id,
)
from clickup_mcp_server.config import TEAM_LABELS, settings


def normalize_team_name(label: str) -> str:
    """Turn a ClickUp option label into the lowercase, hyphenated name callers pass."""
    return re.sub(r"\s+", "-", label.strip().lower())


def _alias_key(name: str) -> str:
    return normalize_team_name(name).casefold()


def task_team_ids(raw: dict[str, object]) -> list[str]:
    """Option IDs in a task's Component/Team field, from any shape ClickUp returns.

    The value is a list of option IDs, a list of `{id, label}` objects, or a single
    ID or object.
    """
    custom_fields = raw.get("custom_fields")
    for cf in custom_fields if isinstance(custom_fields, list) else []:
        if not isinstance(cf, dict) or cf.get("id") != settings.component_team_field_id:
            continue
        value = cf.get("value")
        items = value if isinstance(value, list) else [value]
        ids: list[str] = []
        for item in items:
            option_id = item.get("id") if isinstance(item, dict) else item
            if isinstance(option_id, str) and option_id:
                ids.append(option_id)
        return ids
    return []


def task_team_name(raw: dict[str, object]) -> str | None:
    """Name the task's first Component/Team option from the labels in its own payload."""
    ids = task_team_ids(raw)
    if not ids:
        return None
    labels: dict[str, str] = {}
    custom_fields = raw.get("custom_fields")
    for cf in custom_fields if isinstance(custom_fields, list) else []:
        if not isinstance(cf, dict) or cf.get("id") != settings.component_team_field_id:
            continue
        value = cf.get("value")
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and item.get("id"):
                labels[str(item["id"])] = str(
                    item.get("label") or item.get("name") or ""
                )
        type_config = cf.get("type_config")
        options = (
            type_config.get("options", []) if isinstance(type_config, dict) else []
        )
        for opt in options if isinstance(options, list) else []:
            if isinstance(opt, dict) and opt.get("id"):
                labels.setdefault(
                    str(opt["id"]), str(opt.get("label") or opt.get("name") or "")
                )
    label = labels.get(ids[0], "")
    return normalize_team_name(label) if label.strip() else None


async def fetch_team_options(space_id: str | None = None) -> dict[str, str]:
    """Fetch the Component/Team field's live option labels from ClickUp, keyed by ID.

    Raises when the field itself is absent or unconfigured, so a broken field lookup
    is never reported to the caller as an unknown team name.
    """
    if not settings.component_team_field_id:
        raise ToolError(
            "COMPONENT_TEAM_FIELD_ID is not configured; team names cannot be resolved."
        )
    space = space_id or settings.development_space_id
    if not space:
        raise ToolError(
            "DEVELOPMENT_SPACE_ID is not configured; team names cannot be resolved."
        )
    validate_space_id(space)
    response = await clickup_client.get(f"/space/{space}/field")
    data = parse_response(response)
    fields_raw = data.get("fields", [])
    if not isinstance(fields_raw, list):
        raise TypeError(
            f"Unexpected custom-field response for space {space}: "
            f"'fields' was {type(fields_raw).__name__}, expected a list."
        )
    for field in fields_raw:
        if (
            not isinstance(field, dict)
            or field.get("id") != settings.component_team_field_id
        ):
            continue
        type_config = field.get("type_config", {})
        options_raw = (
            type_config.get("options", []) if isinstance(type_config, dict) else []
        )
        # A Labels field names its options `label`; a Dropdown field uses `name`.
        return {
            str(opt["id"]): str(opt.get("label") or opt.get("name") or "")
            for opt in options_raw
            if isinstance(opt, dict) and "id" in opt
        }
    raise ToolError(
        f"Component/Team field {settings.component_team_field_id!r} not found in "
        f"space {space}; check COMPONENT_TEAM_FIELD_ID and DEVELOPMENT_SPACE_ID."
    )


async def team_option_unverified(label_id: str) -> str | None:
    """Why a batch's team writes can't be trusted, or None while the option is still live.

    Option IDs are never reused, so an option live before a batch and after it was live
    for every write in between: one read covers the whole batch.
    """
    try:
        options = await fetch_team_options()
    except Exception as exc:  # noqa: BLE001 — any lookup failure leaves the batch unverified
        return f"team could not be verified after the batch ({type(exc).__name__})"
    if label_id not in options:
        return "team option was retired during the batch; team not applied"
    return None


def live_aliases(options: dict[str, str]) -> dict[str, str]:
    """CLICKUP_TEAM_LABELS aliases whose option ID is still live, keyed by alias name."""
    return {
        _alias_key(name): label_id
        for name, label_id in TEAM_LABELS.items()
        if label_id in options
    }


def _live_index(options: dict[str, str]) -> dict[str, list[str]]:
    """Live option IDs keyed by normalized label; a key with several IDs is ambiguous."""
    index: dict[str, list[str]] = {}
    for label_id, label in options.items():
        if label.strip():
            index.setdefault(normalize_team_name(label), []).append(label_id)
    return index


def _candidates(
    index: dict[str, list[str]], aliases: dict[str, str], team: str
) -> list[str]:
    key = normalize_team_name(team)
    alias_id = aliases.get(key.casefold())
    found = [alias_id] if alias_id else []
    found += [i for i in index.get(key, []) if i not in found]
    return found


def _unambiguous_labels(
    index: dict[str, list[str]], aliases: dict[str, str]
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for name in [*index, *aliases]:
        found = _candidates(index, aliases, name)
        if len(found) == 1:
            labels[name] = found[0]
    return labels


async def get_team_labels() -> dict[str, str]:
    """Map every unambiguous live Component/Team name or alias to its option ID.

    Fetched on every call, never cached: ClickUp drops a write naming a retired option
    without an error, so a write must never use an ID read before the option changed.
    """
    options = await fetch_team_options()
    return _unambiguous_labels(_live_index(options), live_aliases(options))


async def resolve_team_label(team: str) -> str:
    """Return the live option ID for a team name, rejecting unknown and ambiguous names.

    An alias applies only while its option ID is live, so a retired option never
    redirects the alias elsewhere.
    """
    options = await fetch_team_options()
    index = _live_index(options)
    aliases = live_aliases(options)
    found = _candidates(index, aliases, team)
    if len(found) > 1:
        raise ClickUpInputError(
            f"Team {team!r} matches several live Component/Team options "
            f"({', '.join(found)}); rename one in ClickUp or fix CLICKUP_TEAM_LABELS."
        )
    if not found:
        valid = ", ".join(sorted(_unambiguous_labels(index, aliases)))
        raise ClickUpInputError(f"Unknown team {team!r}. Valid: {valid}.")
    return found[0]
