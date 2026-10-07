import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from clickup_mcp_server.env_maps import parse_task_types, parse_team_labels


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False)

    clickup_api_token: str

    workspace_id: str
    development_space_id: str = ""
    sprints_folder_id: str = ""

    component_team_field_id: str = ""

    api_base_url: str = "https://api.clickup.com/api/v2"
    api_v3_base_url: str = "https://api.clickup.com/api/v3"
    request_timeout: float = 15.0
    max_retries: int = 3


settings = Settings()  # type: ignore[call-arg]

# ClickUp v3 Docs API parent-location type codes (POST .../workspaces/{id}/docs).
DOC_PARENT_TYPES: dict[str, int] = {
    "space": 4,
    "folder": 5,
    "list": 6,
    "everything": 7,
    "workspace": 12,
}

DOC_PARENT_TYPE_NAMES: dict[int, str] = {v: k for k, v in DOC_PARENT_TYPES.items()}

DOC_VISIBILITY_VALUES = ("PUBLIC", "PRIVATE", "PERSONAL", "HIDDEN")


def _load_team_labels() -> dict[str, str]:
    return parse_team_labels(os.environ.get("CLICKUP_TEAM_LABELS", "")) or {}


TEAM_LABELS: dict[str, str] = _load_team_labels()


def _load_task_types() -> dict[str, int]:
    """Task type names -> ClickUp custom_item_id, from GET /team/{id}/custom_item."""
    return parse_task_types(os.environ.get("CLICKUP_TASK_TYPES", "")) or {}


TASK_TYPES: dict[str, int] = _load_task_types()
TASK_TYPE_NAMES: dict[int, str] = {v: k for k, v in TASK_TYPES.items()}
