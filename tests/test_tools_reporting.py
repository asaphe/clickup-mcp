from unittest.mock import patch

import httpx
import pytest

from clickup_mcp_server.tools.reporting import _fetch_task_pr_links


def _mock_response(data: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, headers={"x-ratelimit-remaining": "999"})


class TestFetchTaskPrLinks:
    @pytest.mark.asyncio
    async def test_unreadable_comments_return_none_not_empty(self) -> None:
        from clickup_mcp_server.client import clickup_client

        async def boom(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            raise httpx.ConnectError("boom")

        # [] would be reported as "In review but no PR link found".
        with patch.object(clickup_client, "get", side_effect=boom):
            assert await _fetch_task_pr_links("abc123") is None

    @pytest.mark.asyncio
    async def test_readable_comments_without_links_return_empty_list(self) -> None:
        from clickup_mcp_server.client import clickup_client

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(
                {"comments": [{"id": "1", "comment": [{"text": "no links here"}]}]}
            )

        with patch.object(clickup_client, "get", side_effect=mock_get):
            assert await _fetch_task_pr_links("abc123") == []

    @pytest.mark.asyncio
    async def test_links_are_extracted_from_comments(self) -> None:
        from clickup_mcp_server.client import clickup_client

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return _mock_response(
                {
                    "comments": [
                        {
                            "id": "1",
                            "comment": [
                                {"text": "see https://github.com/org/repo/pull/7"}
                            ],
                        }
                    ]
                }
            )

        with patch.object(clickup_client, "get", side_effect=mock_get):
            links = await _fetch_task_pr_links("abc123")

        assert links == ["https://github.com/org/repo/pull/7"]
