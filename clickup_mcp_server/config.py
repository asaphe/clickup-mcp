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
    request_timeout: float = 15.0
    max_retries: int = 3


settings = Settings()  # type: ignore[call-arg]


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
