import asyncio
import logging
import re
from urllib.parse import quote

import httpx

from clickup_mcp_server.config import settings

logger = logging.getLogger(__name__)

_CUSTOM_ID_RE = re.compile(r"^[A-Z]+-\d+$", re.IGNORECASE)
_SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]+\Z")
_NUMERIC_ID_RE = re.compile(r"^[0-9]+\Z")


def is_custom_task_id(task_id: str) -> bool:
    return bool(_CUSTOM_ID_RE.match(task_id))


def validate_task_id(task_id: str) -> str:
    """Reject task IDs that could redirect a ClickUp API path."""
    if not _SAFE_TASK_ID_RE.match(task_id):
        raise ValueError(
            f"Invalid task_id {task_id!r}: must contain only letters, digits, "
            "hyphens, or underscores."
        )
    return task_id


def _validate_numeric_id(value: str, label: str) -> str:
    """Reject values that could redirect a ClickUp API path. ClickUp
    space/list/folder/workspace IDs are all numeric, so a digits-only
    allowlist rejects every path-traversal character outright."""
    if not _NUMERIC_ID_RE.match(value):
        raise ValueError(f"Invalid {label} {value!r}: must contain only digits.")
    return value


def validate_list_id(list_id: str) -> str:
    return _validate_numeric_id(list_id, "list_id")


def validate_space_id(space_id: str) -> str:
    return _validate_numeric_id(space_id, "space_id")


def validate_doc_parent_id(parent_id: str) -> str:
    return _validate_numeric_id(parent_id, "parent_id")


def encode_path_segment(value: object) -> str:
    return quote(str(value), safe="")


class ClickUpAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"ClickUp API {status_code}: {message}")


def parse_response(response: httpx.Response) -> dict[str, object]:
    if response.status_code >= 400:
        try:
            body = response.json()
            err_msg = body.get("err", body.get("error", response.text))
        except Exception:
            err_msg = response.text
        raise ClickUpAPIError(response.status_code, str(err_msg))
    if response.status_code == 204 or not response.content:
        if response.status_code != 204:
            logger.warning(
                "Empty body with status %d; returning {}", response.status_code
            )
        return {}
    return response.json()


class ClickUpClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.api_base_url,
                headers={
                    "Authorization": settings.clickup_api_token,
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(settings.request_timeout),
            )
        return self._client

    async def get(
        self,
        path: str,
        params: dict[str, str] | list[tuple[str, str]] | None = None,
    ) -> httpx.Response:
        return await self._request("GET", path, params=params)

    async def post(
        self, path: str, json_data: dict[str, object] | None = None
    ) -> httpx.Response:
        return await self._request("POST", path, json=json_data)

    async def put(
        self, path: str, json_data: dict[str, object] | None = None
    ) -> httpx.Response:
        return await self._request("PUT", path, json=json_data)

    async def delete(self, path: str) -> httpx.Response:
        return await self._request("DELETE", path)

    async def _request(
        self,
        method: str,
        path: str,
        params: httpx.QueryParams
        | dict[str, str]
        | list[tuple[str, str]]
        | None = None,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        for attempt in range(settings.max_retries + 1):
            try:
                response = await self.client.request(
                    method,
                    path,
                    params=params,  # type: ignore[arg-type]
                    json=json,
                )
            except httpx.HTTPError as exc:
                if attempt == settings.max_retries:
                    raise
                logger.warning("Request failed (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(2**attempt)
                continue

            remaining = response.headers.get("x-ratelimit-remaining")
            if remaining and remaining.isdigit() and int(remaining) < 10:
                logger.info(
                    "Rate limit approaching (%s remaining), throttling", remaining
                )
                await asyncio.sleep(1.0)

            if response.status_code != 429:
                return response
            if attempt == settings.max_retries:
                return response

            wait = 2**attempt
            logger.warning("Rate limited (429), retrying in %ds", wait)
            await asyncio.sleep(wait)

        raise RuntimeError("Unreachable")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


clickup_client = ClickUpClient()


async def resolve_task_id(task_id: str) -> str:
    validate_task_id(task_id)
    if not is_custom_task_id(task_id):
        return task_id
    response = await clickup_client.get(
        f"/task/{task_id}",
        params={"custom_task_ids": "true", "team_id": settings.workspace_id},
    )
    data = parse_response(response)
    return validate_task_id(str(data["id"]))
