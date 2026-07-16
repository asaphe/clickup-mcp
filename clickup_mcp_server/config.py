import json
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


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

DOC_VISIBILITY_VALUES = ("PUBLIC", "PRIVATE", "PERSONAL", "HIDDEN")


def _load_team_labels() -> dict[str, str]:
    raw = os.environ.get("CLICKUP_TEAM_LABELS", "")
    if not raw:
        return {}
    try:
        labels = json.loads(raw)
        if isinstance(labels, dict):
            return {str(k): str(v) for k, v in labels.items()}
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


TEAM_LABELS: dict[str, str] = _load_team_labels()
