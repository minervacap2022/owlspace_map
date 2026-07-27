#!/usr/bin/env python3
"""Require core producer/change-time skills to route to canonical Policy 13."""

from __future__ import annotations

import sys
from pathlib import Path


REQUIRED_FILES = ("no-bugs-first/SKILL.md", "no-new-bugs/SKILL.md")
REQUIRED_TEXT = (
    "Owner Simulation Contract",
    "nexora-policy/policy/13-simulation-contracts.md",
    "SIMULATION_CONTRACT_REQUIRED",
    "Simulation protocol version `6.0.0`",
    "`klik-simulation-sdk` version `2.0.0`",
    "literal `required_tokens`",
    "same canonical production prompt source",
    "removed `variables` field",
    "Protocol-v5 catalogs",
    "dual-version compatibility",
    "full prompt-owner inventory",
    "partial migration fails admission",
)
FORBIDDEN_TEXT = (
    "Legacy `variables` remain admitted.",
    "Partial migration remains admitted.",
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
        for forbidden in FORBIDDEN_TEXT:
            if forbidden in content:
                violations.append(f"{relative} must not admit {forbidden}")
    return violations


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    violations = check_root(root)
    if violations:
        print("Simulation Contract skill routing: FAILED", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("Simulation Contract skill routing: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
