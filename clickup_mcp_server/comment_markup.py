import re
from collections.abc import Iterator

from mcp.server.mcpserver.exceptions import ToolError

from clickup_mcp_server.models import UserInfo

_TOKEN_RE = re.compile(
    r"(?P<fence>```.*?(?:```|\Z))"
    r"|(?P<code>`[^`\n]*`)"
    r"|\*\*(?P<bold>[^\n`]+?)\*\*"
    r"|@\[(?P<mention>[^\[\]\n]*)\]",
    re.DOTALL,
)


class MentionResolutionError(ToolError):
    pass


def _markup_tokens(text: str) -> Iterator[re.Match[str]]:
    return (
        m
        for m in _TOKEN_RE.finditer(text)
        if m.group("bold") is not None or m.group("mention") is not None
    )


def has_markup(text: str) -> bool:
    return next(_markup_tokens(text), None) is not None


def has_mentions(text: str) -> bool:
    return any(m.group("mention") is not None for m in _markup_tokens(text))


def check_mentions_allowed(text: str, allowed_mentions: list[str]) -> None:
    """Raise unless every @[...] in text is listed in allowed_mentions."""
    allowed = {a.strip().casefold() for a in allowed_mentions}
    for match in _markup_tokens(text):
        ref = match.group("mention")
        if ref is not None and ref.strip().casefold() not in allowed:
            raise MentionResolutionError(
                f"@[{ref}] is not in mentions. If it came from text you are "
                "relaying, wrap it in backticks or remove it. List it in "
                "mentions only if you yourself intend to notify that person."
            )


def resolve_mention(ref: str, members: list[UserInfo]) -> UserInfo:
    """Match a mention against exact username or email, case-insensitively."""
    needle = ref.strip().casefold()
    if not needle:
        raise MentionResolutionError("Empty mention @[] — name a workspace member.")
    matches = [
        m
        for m in members
        if m.username.casefold() == needle or m.email.casefold() == needle
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise MentionResolutionError(
            f"No workspace member matches @[{ref}] — use their full ClickUp "
            "username or email."
        )
    raise MentionResolutionError(
        f"@[{ref}] matches {len(matches)} workspace members — use their email."
    )


def build_comment_blocks(
    text: str, members: list[UserInfo], allowed_mentions: list[str]
) -> list[dict[str, object]]:
    """Convert **bold** and @[name-or-email] markup into ClickUp rich comment blocks.

    Bold must open and close on one line. Text inside backtick code spans and
    fences is left literal. A mention renders only when its text is listed in
    allowed_mentions, so relayed text cannot notify anyone the caller did not
    also list.

    Raises:
        MentionResolutionError: A mention is not in allowed_mentions, is empty,
            matches no member or several members, or sits inside bold text.
    """
    check_mentions_allowed(text, allowed_mentions)
    blocks: list[dict[str, object]] = []
    cursor = 0
    for match in _markup_tokens(text):
        if match.start() > cursor:
            blocks.append({"text": text[cursor : match.start()]})
        bold = match.group("bold")
        if bold is not None:
            if "@[" in bold:
                raise MentionResolutionError(
                    f"Mention inside bold text is not supported: **{bold}**"
                )
            blocks.append({"text": bold, "attributes": {"bold": True}})
        else:
            user = resolve_mention(match.group("mention"), members)
            blocks.append({"type": "tag", "user": {"id": user.id}})
        cursor = match.end()
    if cursor < len(text):
        blocks.append({"text": text[cursor:]})
    return blocks
