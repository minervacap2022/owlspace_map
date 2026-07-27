#!/usr/bin/env python3
"""Require doctrine skills to route LLM onboarding to canonical Policy 12."""

from __future__ import annotations

import sys
from pathlib import Path


REQUIRED_FILES = ("no-bugs-first/SKILL.md", "no-new-bugs/SKILL.md")
REQUIRED_TEXT = (
    "LLM Provider Admission",
    "nexora-policy/policy/12-infrastructure.md",
    "LLM_PROVIDER_ADMISSION_REQUIRED",
)


def check_root(root: Path) -> list[str]:
    violations: list[str] = []
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            violations.append(f"missing governed skill: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        for required in REQUIRED_TEXT:
            if required not in content:
                violations.append(f"{relative} must reference {required}")
    return violations


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    violations = check_root(root)
    if violations:
        print("LLM Provider Admission skill routing: FAILED", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("LLM Provider Admission skill routing: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
