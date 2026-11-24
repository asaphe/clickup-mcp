import json
import re
from unittest.mock import patch

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from tests.conftest import (
    BACKEND_OPTION_ID,
    DATA_PLATFORM_OPTION_ID,
    FRONTEND_OPTION_ID,
    PLATFORM_OPTION_ID,
    RESEARCH_OPTION_ID,
    SAMPLE_TASK_RAW,
)
from tests.helpers import get_tool_text

TEAM_FIELD_ID = "test-field-id"


def _set_aliases(monkeypatch: pytest.MonkeyPatch, aliases: dict[str, str]) -> None:
    monkeypatch.setattr("clickup_mcp_server.team_labels.TEAM_LABELS", aliases)


def _task_with_team(label_id: str, label: str) -> dict[str, object]:
    raw = dict(SAMPLE_TASK_RAW)
    raw["custom_fields"] = [
        {
            "id": TEAM_FIELD_ID,
            "type": "labels",
            "value": [label_id],
            "type_config": {"options": [{"id": label_id, "label": label}]},
        }
    ]
    return raw


class TestResolveTeamLabel:
    @pytest.mark.asyncio
    async def test_resolves_names_from_live_labels(self) -> None:
        from clickup_mcp_server.team_labels import resolve_team_label

        assert await resolve_team_label("Backend") == BACKEND_OPTION_ID
        assert await resolve_team_label("data-platform") == DATA_PLATFORM_OPTION_ID
        assert await resolve_team_label("Data  Platform") == DATA_PLATFORM_OPTION_ID
        assert await resolve_team_label("platform") == PLATFORM_OPTION_ID
        assert await resolve_team_label("frontend-web-squad") == FRONTEND_OPTION_ID

    @pytest.mark.asyncio
    async def test_rejects_a_retired_option(
        self, stub_team_options: dict[str, str]
    ) -> None:
        from clickup_mcp_server.team_labels import resolve_team_label

        del stub_team_options[RESEARCH_OPTION_ID]

        with pytest.raises(ToolError, match="Unknown team 'research'"):
            await resolve_team_label("research")

    @pytest.mark.asyncio
    async def test_option_retired_after_an_earlier_lookup_is_rejected(
        self, stub_team_options: dict[str, str]
    ) -> None:
        from clickup_mcp_server.team_labels import resolve_team_label

        assert await resolve_team_label("research") == RESEARCH_OPTION_ID
        del stub_team_options[RESEARCH_OPTION_ID]

        with pytest.raises(ToolError, match="Unknown team 'research'"):
            await resolve_team_label("research")

    @pytest.mark.asyncio
    async def test_empty_name_is_unknown(self) -> None:
        from clickup_mcp_server.team_labels import resolve_team_label

        with pytest.raises(ToolError, match="Unknown team ''"):
            await resolve_team_label("")


class TestAliases:
    @pytest.mark.asyncio
    async def test_alias_and_live_label_both_resolve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from clickup_mcp_server.team_labels import get_team_labels, resolve_team_label

        _set_aliases(monkeypatch, {"web": FRONTEND_OPTION_ID})

        assert await resolve_team_label("web") == FRONTEND_OPTION_ID
        assert await resolve_team_label("Frontend Web squad") == FRONTEND_OPTION_ID
        labels = await get_team_labels()
        assert labels["web"] == FRONTEND_OPTION_ID
        assert labels["frontend-web-squad"] == FRONTEND_OPTION_ID

    @pytest.mark.asyncio
    async def test_alias_named_like_its_own_label_is_not_ambiguous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from clickup_mcp_server.team_labels import resolve_team_label

        _set_aliases(monkeypatch, {"backend": BACKEND_OPTION_ID})

        assert await resolve_team_label("backend") == BACKEND_OPTION_ID

    @pytest.mark.asyncio
    async def test_alias_matches_caselessly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from clickup_mcp_server.team_labels import resolve_team_label

        _set_aliases(monkeypatch, {"strasse": RESEARCH_OPTION_ID})

        assert await resolve_team_label("Straße") == RESEARCH_OPTION_ID

    @pytest.mark.asyncio
    async def test_alias_resolves_only_while_its_option_is_live(
        self, monkeypatch: pytest.MonkeyPatch, stub_team_options: dict[str, str]
    ) -> None:
        from clickup_mcp_server.team_labels import get_team_labels, resolve_team_label

        _set_aliases(monkeypatch, {"web": FRONTEND_OPTION_ID})
        assert await resolve_team_label("web") == FRONTEND_OPTION_ID

        del stub_team_options[FRONTEND_OPTION_ID]

        with pytest.raises(ToolError, match="Unknown team 'web'"):
            await resolve_team_label("web")
        assert "web" not in await get_team_labels()

    @pytest.mark.asyncio
    async def test_retired_alias_target_never_redirects_to_another_option(
        self, monkeypatch: pytest.MonkeyPatch, stub_team_options: dict[str, str]
    ) -> None:
        from clickup_mcp_server.team_labels import resolve_team_label

        _set_aliases(monkeypatch, {"web": FRONTEND_OPTION_ID})
        del stub_team_options[FRONTEND_OPTION_ID]
        new_id = "00000000-0000-4000-8000-0000000000cc"
        stub_team_options[new_id] = "Web"

        assert await resolve_team_label("web") == new_id

    @pytest.mark.asyncio
    async def test_alias_colliding_with_a_different_live_label_is_ambiguous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from clickup_mcp_server.team_labels import get_team_labels, resolve_team_label

        _set_aliases(monkeypatch, {"research": BACKEND_OPTION_ID})

        with pytest.raises(ToolError, match="matches several live Component/Team"):
            await resolve_team_label("research")
        labels = await get_team_labels()
        assert "research" not in labels
        assert labels["backend"] == BACKEND_OPTION_ID

    @pytest.mark.asyncio
    async def test_no_aliases_configured_still_resolves_live_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from clickup_mcp_server.team_labels import resolve_team_label

        _set_aliases(monkeypatch, {})

        assert await resolve_team_label("research") == RESEARCH_OPTION_ID


class TestAmbiguousAndMissing:
    @pytest.mark.asyncio
    async def test_name_shared_by_two_options_is_rejected_and_unlisted(
        self, stub_team_options: dict[str, str]
    ) -> None:
        from clickup_mcp_server.team_labels import get_team_labels, resolve_team_label

        stub_team_options["00000000-0000-4000-8000-0000000000bb"] = "data  platform"

        with pytest.raises(ToolError, match="matches several live Component/Team"):
            await resolve_team_label("Data Platform")
        assert "data-platform" not in await get_team_labels()
        assert await resolve_team_label("backend") == BACKEND_OPTION_ID

    @pytest.mark.real_team_fetch
    @pytest.mark.asyncio
    async def test_missing_field_is_not_reported_as_unknown_team(self) -> None:
        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.team_labels import resolve_team_label

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return httpx.Response(200, json={"fields": [{"id": "other-field"}]})

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(ToolError, match="Component/Team field .* not found"),
        ):
            await resolve_team_label("backend")

    @pytest.mark.real_team_fetch
    @pytest.mark.asyncio
    async def test_non_list_fields_raises(self) -> None:
        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.team_labels import fetch_team_options

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return httpx.Response(200, json={"fields": {"not": "a list"}})

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            pytest.raises(TypeError, match="expected a list"),
        ):
            await fetch_team_options()

    @pytest.mark.real_team_fetch
    @pytest.mark.asyncio
    async def test_missing_component_team_field_id_raises_its_own_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.team_labels import resolve_team_label

        monkeypatch.setattr(settings, "component_team_field_id", "")

        with (
            patch.object(clickup_client, "get") as mock_get,
            pytest.raises(ToolError, match="COMPONENT_TEAM_FIELD_ID is not configured"),
        ):
            await resolve_team_label("backend")
        mock_get.assert_not_called()

    @pytest.mark.real_team_fetch
    @pytest.mark.asyncio
    async def test_missing_development_space_id_raises_its_own_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.team_labels import resolve_team_label

        monkeypatch.setattr(settings, "development_space_id", "")

        with (
            patch.object(clickup_client, "get") as mock_get,
            pytest.raises(ToolError, match="DEVELOPMENT_SPACE_ID is not configured"),
        ):
            await resolve_team_label("backend")
        mock_get.assert_not_called()


class TestFetchTeamOptions:
    @pytest.mark.real_team_fetch
    @pytest.mark.asyncio
    async def test_reads_labels_and_dropdown_names_from_the_field(self) -> None:
        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.config import settings
        from clickup_mcp_server.team_labels import fetch_team_options

        paths: list[str] = []

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            paths.append(path)
            return httpx.Response(
                200,
                json={
                    "fields": [
                        {"id": "other-field", "type_config": {"options": []}},
                        {
                            "id": settings.component_team_field_id,
                            "type_config": {
                                "options": [
                                    {"id": "opt-platform", "label": "Platform"},
                                    {"id": "opt-legacy", "name": "Legacy"},
                                ]
                            },
                        },
                    ]
                },
            )

        with patch.object(clickup_client, "get", side_effect=mock_get):
            options = await fetch_team_options()

        assert paths == [f"/space/{settings.development_space_id}/field"]
        assert options == {"opt-platform": "Platform", "opt-legacy": "Legacy"}

    @pytest.mark.real_team_fetch
    @pytest.mark.asyncio
    async def test_explicit_space_overrides_the_configured_one(self) -> None:
        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.team_labels import fetch_team_options

        paths: list[str] = []

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            paths.append(path)
            return httpx.Response(
                200,
                json={
                    "fields": [{"id": TEAM_FIELD_ID, "type_config": {"options": []}}]
                },
            )

        with patch.object(clickup_client, "get", side_effect=mock_get):
            assert await fetch_team_options("999") == {}

        assert paths == ["/space/999/field"]


class TestListTeams:
    @pytest.mark.asyncio
    async def test_lists_every_live_option_by_caller_name(self) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.tools.workspace import register_workspace_tools

        server = MCPServer("test")
        register_workspace_tools(server)
        result = await server.call_tool("list_teams", {})

        assert json.loads(get_tool_text(result)) == {
            "backend": BACKEND_OPTION_ID,
            "frontend-web-squad": FRONTEND_OPTION_ID,
            "data-platform": DATA_PLATFORM_OPTION_ID,
            "platform": PLATFORM_OPTION_ID,
            "research": RESEARCH_OPTION_ID,
        }

    @pytest.mark.asyncio
    async def test_includes_live_aliases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.tools.workspace import register_workspace_tools

        _set_aliases(
            monkeypatch,
            {"web": FRONTEND_OPTION_ID, "gone": "00000000-0000-4000-8000-00000000dead"},
        )
        server = MCPServer("test")
        register_workspace_tools(server)
        result = await server.call_tool("list_teams", {})
        teams = json.loads(get_tool_text(result))

        assert teams["web"] == FRONTEND_OPTION_ID
        assert teams["frontend-web-squad"] == FRONTEND_OPTION_ID
        assert "gone" not in teams


class TestMapTaskDetailTeam:
    def test_names_option_from_task_payload(self) -> None:
        from clickup_mcp_server.models import map_task_detail

        raw = _task_with_team(PLATFORM_OPTION_ID, "Platform ")
        assert map_task_detail(raw).team == "platform"

    def test_names_multiword_option_with_hyphens(self) -> None:
        from clickup_mcp_server.models import map_task_detail

        raw = _task_with_team(FRONTEND_OPTION_ID, "Frontend Web squad")
        assert map_task_detail(raw).team == "frontend-web-squad"

    def test_unlabelled_task_has_no_team(self) -> None:
        from clickup_mcp_server.models import map_task_detail

        assert map_task_detail(SAMPLE_TASK_RAW).team is None


class TestTaskTeamIds:
    def _raw(self, value: object) -> dict[str, object]:
        raw = dict(SAMPLE_TASK_RAW)
        raw["custom_fields"] = [{"id": TEAM_FIELD_ID, "value": value}]
        return raw

    def test_reads_every_shape_clickup_returns(self) -> None:
        from clickup_mcp_server.team_labels import task_team_ids, task_team_name

        assert task_team_ids(self._raw([PLATFORM_OPTION_ID])) == [PLATFORM_OPTION_ID]
        assert task_team_ids(self._raw(PLATFORM_OPTION_ID)) == [PLATFORM_OPTION_ID]
        objects = self._raw([{"id": PLATFORM_OPTION_ID, "label": "Platform "}])
        assert task_team_ids(objects) == [PLATFORM_OPTION_ID]
        assert task_team_name(objects) == "platform"
        single = self._raw({"id": PLATFORM_OPTION_ID, "label": "Platform "})
        assert task_team_ids(single) == [PLATFORM_OPTION_ID]
        assert task_team_name(single) == "platform"
        assert task_team_ids(self._raw(None)) == []

    def test_ignores_other_custom_fields(self) -> None:
        from clickup_mcp_server.team_labels import task_team_ids

        raw = dict(SAMPLE_TASK_RAW)
        raw["custom_fields"] = [{"id": "other-field", "value": [PLATFORM_OPTION_ID]}]
        assert task_team_ids(raw) == []


class TestServerRejectsUnknownArguments:
    @pytest.mark.asyncio
    async def test_undeclared_argument_raises_instead_of_being_dropped(self) -> None:
        from clickup_mcp_server.server import mcp_server

        with pytest.raises(ToolError, match="Extra inputs are not permitted"):
            await mcp_server.call_tool(
                "update_task", {"task_id": "DEV-9999", "componet_team": "backend"}
            )

    def test_every_tool_schema_forbids_additional_properties(self) -> None:
        from clickup_mcp_server.server import mcp_server

        tools = mcp_server._tool_manager.list_tools()
        assert len(tools) > 0
        assert all(t.parameters.get("additionalProperties") is False for t in tools)

    def test_update_task_declares_team(self) -> None:
        from clickup_mcp_server.server import mcp_server

        tool = next(
            t for t in mcp_server._tool_manager.list_tools() if t.name == "update_task"
        )
        assert "team" in tool.parameters["properties"]


class TestSprintReportByOptionId:
    @pytest.mark.asyncio
    async def test_matches_second_label_and_id_only_tasks(self) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.models import SprintInfo
        from clickup_mcp_server.tools.reporting import register_reporting_tools

        def task(task_id: str, value: object) -> dict[str, object]:
            raw = dict(SAMPLE_TASK_RAW)
            raw["id"] = task_id
            raw["custom_id"] = f"DEV-{task_id}"
            raw["custom_fields"] = [{"id": TEAM_FIELD_ID, "value": value}]
            return raw

        tasks = [
            task("1", [BACKEND_OPTION_ID, PLATFORM_OPTION_ID]),
            task("2", [PLATFORM_OPTION_ID]),
            task("3", [BACKEND_OPTION_ID]),
        ]

        async def mock_get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return httpx.Response(200, json={"tasks": tasks, "last_page": True})

        server = MCPServer("test")
        register_reporting_tools(server)
        sprint = SprintInfo(list_id="1", name="S", start_date="", end_date="")

        with (
            patch.object(clickup_client, "get", side_effect=mock_get),
            patch(
                "clickup_mcp_server.tools.reporting.get_current_sprint_cached",
                return_value=sprint,
            ),
        ):
            result = await server.call_tool(
                "get_sprint_report", {"team": "platform", "include_pr_links": False}
            )

        found = sorted(set(re.findall(r"DEV-\d+", get_tool_text(result))))
        assert found == ["DEV-1", "DEV-2"]


class TestPostBatchTeamCheck:
    def _counting_fetch(
        self, monkeypatch: pytest.MonkeyPatch, options: dict[str, str]
    ) -> list[int]:
        from clickup_mcp_server import team_labels

        calls: list[int] = []

        async def fetch(space_id: str | None = None) -> dict[str, str]:
            calls.append(1)
            return dict(options)

        monkeypatch.setattr(team_labels, "fetch_team_options", fetch)
        return calls

    async def _bulk(self, options: dict[str, str], retire_on_post: bool) -> str:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        async def ok_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            return httpx.Response(200, json=SAMPLE_TASK_RAW)

        async def post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            if retire_on_post:
                options.pop(PLATFORM_OPTION_ID, None)
            return httpx.Response(200, json={})

        async def resolve(task_id: str) -> str:
            return task_id.lower()

        server = MCPServer("test")
        register_task_tools(server)
        with (
            patch.object(clickup_client, "put", side_effect=ok_put),
            patch.object(clickup_client, "post", side_effect=post),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id", side_effect=resolve
            ),
        ):
            result = await server.call_tool(
                "bulk_update_tasks",
                {
                    "task_ids": ["DEV-1", "DEV-2", "DEV-3"],
                    "status": "done",
                    "team": "platform",
                },
            )
        return get_tool_text(result)

    @pytest.mark.asyncio
    async def test_bulk_reads_options_once_after_the_batch(
        self, monkeypatch: pytest.MonkeyPatch, stub_team_options: dict[str, str]
    ) -> None:
        calls = self._counting_fetch(monkeypatch, stub_team_options)

        data = json.loads(await self._bulk(stub_team_options, retire_on_post=False))

        assert data["updated"] == ["DEV-1", "DEV-2", "DEV-3"]
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_bulk_option_retired_mid_batch_fails_every_team_write(
        self, monkeypatch: pytest.MonkeyPatch, stub_team_options: dict[str, str]
    ) -> None:
        self._counting_fetch(monkeypatch, stub_team_options)

        data = json.loads(await self._bulk(stub_team_options, retire_on_post=True))

        assert data["updated"] == []
        assert [f["task_id"] for f in data["failed"]] == ["DEV-1", "DEV-2", "DEV-3"]
        assert all("retired during the batch" in f["error"] for f in data["failed"])
        assert all("Already applied: status" in f["error"] for f in data["failed"])

    @pytest.mark.asyncio
    async def test_bulk_retired_option_fails_every_occurrence_of_a_repeated_id(
        self, monkeypatch: pytest.MonkeyPatch, stub_team_options: dict[str, str]
    ) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        self._counting_fetch(monkeypatch, stub_team_options)

        async def post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            stub_team_options.pop(PLATFORM_OPTION_ID, None)
            return httpx.Response(200, json={})

        async def resolve(task_id: str) -> str:
            return task_id.lower()

        server = MCPServer("test")
        register_task_tools(server)
        with (
            patch.object(clickup_client, "post", side_effect=post),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id", side_effect=resolve
            ),
        ):
            result = await server.call_tool(
                "bulk_update_tasks",
                {"task_ids": ["DEV-1", "DEV-1"], "team": "platform"},
            )
        data = json.loads(get_tool_text(result))

        assert data["updated"] == []
        assert [f["task_id"] for f in data["failed"]] == ["DEV-1", "DEV-1"]

    @pytest.mark.asyncio
    async def test_bulk_unverifiable_option_fails_team_writes(
        self, monkeypatch: pytest.MonkeyPatch, stub_team_options: dict[str, str]
    ) -> None:
        from clickup_mcp_server import team_labels

        calls: list[int] = []

        async def fetch(space_id: str | None = None) -> dict[str, str]:
            calls.append(1)
            if len(calls) > 1:
                raise RuntimeError("field lookup down")
            return dict(stub_team_options)

        monkeypatch.setattr(team_labels, "fetch_team_options", fetch)

        data = json.loads(await self._bulk(stub_team_options, retire_on_post=False))

        assert data["updated"] == []
        assert all("could not be verified" in f["error"] for f in data["failed"])

    @pytest.mark.asyncio
    async def test_ensure_option_retired_mid_run_is_not_marked_fixed(
        self, monkeypatch: pytest.MonkeyPatch, stub_team_options: dict[str, str]
    ) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        self._counting_fetch(monkeypatch, stub_team_options)
        no_team = dict(SAMPLE_TASK_RAW)
        no_team["custom_fields"] = []

        async def get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return httpx.Response(200, json=no_team)

        async def post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            stub_team_options.pop(PLATFORM_OPTION_ID, None)
            return httpx.Response(200, json={})

        server = MCPServer("test")
        register_task_tools(server)
        with (
            patch.object(clickup_client, "get", side_effect=get),
            patch.object(clickup_client, "post", side_effect=post),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                return_value="abc123",
            ),
        ):
            result = await server.call_tool(
                "ensure_task_fields",
                {
                    "task_ids": ["DEV-1"],
                    "required_fields": ["team"],
                    "fix": True,
                    "default_team": "platform",
                },
            )
        data = json.loads(get_tool_text(result))

        assert data["issues"][0]["fixed"] is False
        assert data["issues"][0]["name"] == "Test task"
        assert "retired during the batch" in data["issues"][0]["error"]
        assert data["all_compliant"] is False

    @pytest.mark.asyncio
    async def test_ensure_failed_team_write_keeps_record_and_names_applied_fix(
        self,
    ) -> None:
        from mcp.server.mcpserver import MCPServer

        from clickup_mcp_server.client import clickup_client
        from clickup_mcp_server.tools.tasks import register_task_tools

        bare = dict(SAMPLE_TASK_RAW)
        bare["custom_fields"] = []
        bare["assignees"] = []

        async def get(
            path: str, params: dict[str, str] | None = None
        ) -> httpx.Response:
            return httpx.Response(200, json=bare)

        async def ok_put(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            return httpx.Response(200, json=bare)

        async def failing_post(
            path: str, json_data: dict[str, object] | None = None
        ) -> httpx.Response:
            return httpx.Response(500, json={"err": "internal-body-detail"})

        server = MCPServer("test")
        register_task_tools(server)
        with (
            patch.object(clickup_client, "get", side_effect=get),
            patch.object(clickup_client, "put", side_effect=ok_put),
            patch.object(clickup_client, "post", side_effect=failing_post),
            patch(
                "clickup_mcp_server.tools.tasks.resolve_task_id",
                return_value="abc123",
            ),
        ):
            result = await server.call_tool(
                "ensure_task_fields",
                {
                    "task_ids": ["DEV-1"],
                    "required_fields": ["assignee", "team"],
                    "fix": True,
                    "default_assignee_id": 42,
                    "default_team": "platform",
                },
            )
        issue = json.loads(get_tool_text(result))["issues"][0]

        assert issue["name"] == "Test task"
        assert issue["missing_fields"] == ["assignee", "team"]
        assert issue["fixed"] is False
        assert "ClickUp API error 500" in issue["error"]
        assert "Already applied: default_assignee_id" in issue["error"]
        assert "internal-body-detail" not in issue["error"]
