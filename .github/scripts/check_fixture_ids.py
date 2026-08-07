#!/usr/bin/env python3
"""Fail CI when a test fixture carries a real-looking ClickUp identifier.

Fixtures must use synthetic placeholders: a real workspace, folder or list id
committed here would be published permanently and irrevocably.

Real ClickUp ids are 9-12 digits beginning with 9.
Epoch timestamps in these fixtures begin with 1, so keying on the leading 9
separates identifiers from timestamps without a length heuristic.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TESTS = Path("tests")

CLICKUP_ID = re.compile(r"(?<!\d)(9\d{8,11})(?!\d)")

ALLOWED: set[str] = set()


def offenders() -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for path in sorted(TESTS.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for value in CLICKUP_ID.findall(line):
                if len(set(value)) == 1 or value in ALLOWED:
                    continue
                found.append((path, lineno, value))
    return found


def main() -> int:
    if not TESTS.is_dir():
        print(
            f"error: {TESTS}/ not found - run from the repository root", file=sys.stderr
        )
        return 2

    files = list(TESTS.rglob("*.py"))
    if not files:
        print(
            f"error: no test files under {TESTS}/ - refusing to report a vacuous pass",
            file=sys.stderr,
        )
        return 2

    found = offenders()
    if not found:
        print(f"fixture hygiene: {len(files)} test files clean")
        return 0

    print(
        "fixture hygiene FAILED - real-looking ClickUp ids in fixtures:\n",
        file=sys.stderr,
    )
    for path, lineno, value in found:
        masked = value[:2] + "*" * (len(value) - 2)
        print(f"  {path}:{lineno}  {masked} ({len(value)} digits)", file=sys.stderr)
    print(
        "\nUse a synthetic placeholder instead - a repdigit such as 222222222.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
