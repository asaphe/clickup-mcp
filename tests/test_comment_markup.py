import pytest
from mcp.server.mcpserver.exceptions import ToolError

from clickup_mcp_server.comment_markup import (
    MentionResolutionError,
    build_comment_blocks,
    has_markup,
    has_mentions,
)
from clickup_mcp_server.models import UserInfo

MEMBERS = [
    UserInfo(id=1, username="Jordan Example", email="jordan.e@example.com"),
    UserInfo(id=2, username="Jordan Sample", email="jordan.s@example.com"),
    UserInfo(id=3, username="Casey Test", email="casey@example.com"),
    UserInfo(id=4, username="Casey Test", email="casey.t2@example.com"),
]


ALL_REFS = [
    "Jordan Example",
    "JORDAN.S@EXAMPLE.COM",
    "Jordan",
    "Casey Test",
    "Nobody Here",
    " ",
]


def _build(text: str, members: list[UserInfo]) -> list[dict[str, object]]:
    return build_comment_blocks(text, members, ALL_REFS)


def test_plain_text_has_no_markup() -> None:
    assert not has_markup("[adr-draft] a * b @ c [d]")


def test_resolution_error_is_a_tool_error() -> None:
    assert issubclass(MentionResolutionError, ToolError)


def test_bold_and_mention_become_blocks_in_order() -> None:
    blocks = _build("@[Jordan Example] re: **My position:** no.\n", MEMBERS)
    assert blocks == [
        {"type": "tag", "user": {"id": 1}},
        {"text": " re: "},
        {"text": "My position:", "attributes": {"bold": True}},
        {"text": " no.\n"},
    ]


def test_mention_matches_email_case_insensitively() -> None:
    blocks = _build("cc @[JORDAN.S@EXAMPLE.COM]", MEMBERS)
    assert blocks[-1] == {"type": "tag", "user": {"id": 2}}


def test_partial_name_is_rejected_not_guessed() -> None:
    with pytest.raises(MentionResolutionError, match="No workspace member"):
        _build("@[Jordan] hi", MEMBERS)


def test_duplicate_username_is_rejected() -> None:
    with pytest.raises(MentionResolutionError, match="matches 2"):
        _build("@[Casey Test] hi", MEMBERS)


def test_bold_does_not_span_lines() -> None:
    assert not has_markup("**a\nb**")


def test_unclosed_fence_is_code_to_the_end() -> None:
    assert _build("```\nf(**a, **b)\n", MEMBERS) == [{"text": "```\nf(**a, **b)\n"}]


def test_pasted_code_is_left_literal() -> None:
    code = "    return f(*args, **kwargs)\n    g(**opts)\n"
    assert not has_markup(code)
    assert not has_markup("use `a**b**c` here")
    assert not has_markup("```\nf(**a, **b)\n```")


def test_markup_outside_code_still_renders() -> None:
    blocks = _build("`x**y**` and **z**", MEMBERS)
    assert blocks == [
        {"text": "`x**y**` and "},
        {"text": "z", "attributes": {"bold": True}},
    ]


def test_mention_inside_bold_is_rejected() -> None:
    with pytest.raises(MentionResolutionError, match="inside bold"):
        _build("**cc @[Nobody Here]** please", MEMBERS)


def test_empty_mention_is_rejected_even_when_a_member_has_no_email() -> None:
    members = [UserInfo(id=9, username="No Email", email="")]
    with pytest.raises(MentionResolutionError, match="Empty mention"):
        _build("@[ ] hi", members)


def test_has_mentions_ignores_bold_only() -> None:
    assert not has_mentions("**bold** only")
    assert has_mentions("**bold** and @[Casey Test]")


def test_unlisted_mention_is_rejected_before_lookup() -> None:
    with pytest.raises(MentionResolutionError, match="not in mentions"):
        build_comment_blocks("cc @[Jordan Example]", MEMBERS, [])


def test_listed_mention_matches_case_and_space_insensitively() -> None:
    blocks = build_comment_blocks(
        "cc @[Jordan Example]", MEMBERS, ["  jordan example "]
    )
    assert blocks[-1] == {"type": "tag", "user": {"id": 1}}


def test_one_unlisted_mention_fails_the_whole_comment() -> None:
    with pytest.raises(MentionResolutionError, match=r"@\[Jordan Sample\] is not in"):
        build_comment_blocks(
            "@[Jordan Example] and @[Jordan Sample]", MEMBERS, ["Jordan Example"]
        )


def test_bold_stops_at_backticks() -> None:
    assert not has_markup("**a `b** c`")
    assert not has_markup("**run `@[x]`**")


def test_unclosed_mentions_scan_in_linear_time() -> None:
    import time

    start = time.perf_counter()
    assert not has_markup("@[" * 40000)
    assert time.perf_counter() - start < 2
