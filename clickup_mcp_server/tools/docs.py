from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clickup_mcp_server.client import (
    clickup_client,
    parse_response,
    validate_doc_id,
    validate_doc_parent_id,
    validate_page_id,
)
from clickup_mcp_server.config import DOC_PARENT_TYPES, DOC_VISIBILITY_VALUES, settings
from clickup_mcp_server.models import CreateDocResult, UpdateDocPageResult, compact_json

_CONTENT_FORMATS = ("text/md", "text/plain")


def _doc_page_url(doc_id: str, page_id: str) -> str:
    return f"https://app.clickup.com/{settings.workspace_id}/v/dc/{doc_id}/{page_id}"


def register_doc_tools(server: FastMCP) -> None:
    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=False,
            openWorldHint=False,
        )
    )
    async def create_doc(
        name: str,
        content: str,
        parent_id: str | None = None,
        parent_type: str = "space",
        content_format: str = "text/md",
        visibility: str = "PRIVATE",
    ) -> str:
        """Create a native ClickUp Doc with one page of content, and return its URL.

        Use this for shareable reports/RFCs that need real markdown tables and
        headers — a task description degrades tables and isn't a durable
        review surface. The doc is created PRIVATE by default; sharing it with
        specific people or the workspace is a separate step you take in the
        ClickUp UI, not something this tool does.

        Two sequential API calls (create doc, then create its page) with no
        rollback: ClickUp's v3 Docs API exposes no delete endpoint for docs or
        pages, so if the page call fails after the doc call succeeds, an
        empty Doc is left behind — check the workspace for it if this raises.
        For the same reason, correcting a mistake (wrong content, a bad
        title) should use update_doc_page on the existing doc_id/page_id
        rather than calling create_doc again — a second create_doc call
        orphans the first Doc with no way to remove it.

        Args:
            name: Doc title.
            content: Page body. Markdown by default (see content_format).
            parent_id: Space/Folder/List/Workspace ID to create the doc under.
                Defaults to the configured development space — which is a
                Space, so if parent_type is "workspace"/"everything" you must
                pass a matching parent_id explicitly or the doc lands in the
                wrong place.
            parent_type: One of "space", "folder", "list", "everything",
                "workspace" — must match what parent_id actually refers to.
            content_format: "text/md" (default) or "text/plain".
            visibility: "PRIVATE" (default), "PUBLIC", "PERSONAL", or "HIDDEN".
        """
        if parent_type not in DOC_PARENT_TYPES:
            raise ValueError(
                f"Invalid parent_type {parent_type!r}: must be one of "
                f"{sorted(DOC_PARENT_TYPES)}."
            )
        if content_format not in _CONTENT_FORMATS:
            raise ValueError(
                f"Invalid content_format {content_format!r}: must be one of "
                f"{_CONTENT_FORMATS}."
            )
        if visibility not in DOC_VISIBILITY_VALUES:
            raise ValueError(
                f"Invalid visibility {visibility!r}: must be one of "
                f"{DOC_VISIBILITY_VALUES}."
            )

        pid = validate_doc_parent_id(parent_id or settings.development_space_id)

        doc_response = await clickup_client.post(
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}/docs",
            json_data={
                "name": name,
                "create_page": False,
                "parent": {"id": pid, "type": DOC_PARENT_TYPES[parent_type]},
                "visibility": visibility,
            },
        )
        doc_data = parse_response(doc_response)
        doc_id = str(doc_data["id"])

        page_response = await clickup_client.post(
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}"
            f"/docs/{doc_id}/pages",
            json_data={
                "name": name,
                "content": content,
                "content_format": content_format,
            },
        )
        page_data = parse_response(page_response)
        page_id = str(page_data["id"])

        return compact_json(
            CreateDocResult(
                doc_id=doc_id,
                page_id=page_id,
                name=name,
                url=_doc_page_url(doc_id, page_id),
            )
        )

    @server.tool(
        annotations=ToolAnnotations(
            destructiveHint=True,
            openWorldHint=False,
        )
    )
    async def update_doc_page(
        doc_id: str,
        page_id: str,
        content: str,
        name: str | None = None,
        content_format: str = "text/md",
    ) -> str:
        """Overwrite an existing Doc page's content in place, and return its URL.

        Use this to correct a previously published Doc (wrong content, a bad
        title) instead of calling create_doc again — the v3 Docs API has no
        delete endpoint, so a second create_doc call orphans the first Doc
        with no way to remove it. This edits the original doc_id/page_id
        directly, so the existing URL keeps working.

        Always replaces the full page content — the underlying API also
        supports append/prepend edit modes, but this tool doesn't expose
        them: the shared HTTP client retries transport failures, and a retry
        after a lost response (server applied the edit, client never saw it)
        would silently double-apply an append/prepend. A retried replace
        converges to the same content either way, so it's safe.

        Args:
            doc_id: The Doc's ID, as returned by create_doc.
            page_id: The page's ID, as returned by create_doc.
            content: New page content, replacing the page in full.
            name: New page title. Leave unset to keep the existing title.
            content_format: "text/md" (default) or "text/plain".
        """
        validate_doc_id(doc_id)
        validate_page_id(page_id)
        if content_format not in _CONTENT_FORMATS:
            raise ValueError(
                f"Invalid content_format {content_format!r}: must be one of "
                f"{_CONTENT_FORMATS}."
            )

        body: dict[str, object] = {
            "content": content,
            "content_edit_mode": "replace",
            "content_format": content_format,
        }
        if name is not None:
            body["name"] = name

        response = await clickup_client.put(
            f"{settings.api_v3_base_url}/workspaces/{settings.workspace_id}"
            f"/docs/{doc_id}/pages/{page_id}",
            json_data=body,
        )
        parse_response(response)

        return compact_json(
            UpdateDocPageResult(
                doc_id=doc_id,
                page_id=page_id,
                name=name,
                url=_doc_page_url(doc_id, page_id),
            )
        )
