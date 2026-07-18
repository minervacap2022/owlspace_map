#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


REQUIRED_PATHS = (
    Path("no-bugs-first/templates/woodpecker-ci.yaml"),
    Path("no-bugs-first/templates/ci-success-bridge.sh"),
)


def check_root(root: Path) -> list[str]:
    violations: list[str] = []
    skill = root / "no-bugs-first/SKILL.md"
    text = skill.read_text()
    change_skill = root / "no-new-bugs/SKILL.md"
    change_text = change_skill.read_text() if change_skill.exists() else ""

    if ".github/workflows" in text:
        violations.append("no-bugs-first must not scaffold GitHub Actions for governed repos")
    if "templates/woodpecker-ci.yaml" not in text:
        violations.append("no-bugs-first must point to the canonical Woodpecker template")
    if "templates/ci-success-bridge.sh" not in text:
        violations.append("no-bugs-first must point to the ci-success bridge template")
    if "enterprise ruleset" in text.lower():
        violations.append("no-bugs-first must not claim an enterprise ruleset enforces ci-success")
    if ".github/workflows" in change_text:
        violations.append("no-new-bugs must not prescribe GitHub Actions for governed scheduled tests")

    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            violations.append(f"missing doctrine CI scaffold artifact: {relative}")

    legacy = root / "no-bugs-first/templates/ci-success.yml"
    if legacy.exists():
        violations.append("legacy GitHub Actions scaffold still exists: no-bugs-first/templates/ci-success.yml")

    return violations


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    violations = check_root(root)
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("doctrine CI scaffold contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
