#!/usr/bin/env python3
"""Producer-gate lint — the executable arm of nexora-policy policy/08 §4.

policy/08 §2/§4: a Tier-A *producer* skill (one that writes or changes shippable
artifacts) MUST declare `tier: producer` and a non-empty `gates:` block naming the
real checks its output must pass. "A producer skill with no `gates:` is
non-conforming." §7 step 3 calls for "one lint that fails any producer skill missing
its gate reference" — this is that lint. Until it existed, a non-conforming producer
(no-bugs-first shipped with only name+description) could land unblocked.

Scope: every `*/SKILL.md` in this repo whose frontmatter declares `tier: producer`
must carry a non-empty `gates:` list. A skill that is `tier: analyzer`/`tier: meta`
or declares no tier is out of scope (only producers owe a gates contract, per §4).

This is intentionally a *frontmatter* check, not a behavioural one — the contract
it enforces is a declaration contract. It does not validate that the named gates
exist or run; it enforces that the producer *declares* its gates, which is the
policy/08 §4 requirement and what makes "every producer passes the gate" a single
mechanically-checkable property across many skills.

Run:  python3 scripts/check_producer_gates.py [root]   (default root = repo root)
Exit 0 = all producers conform; exit 1 = at least one non-conforming producer.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml


def _parse_frontmatter(text: str) -> dict | None:
    """Return the YAML frontmatter dict of a SKILL.md, or None if absent/invalid.

    Frontmatter is the block between the first two `---` fences at the top of the
    file. A file with no leading `---` has no frontmatter (returns None). A block
    that does not parse to a mapping returns None (an unparseable producer can't be
    judged a producer, so it's simply out of scope for this lint — a separate
    concern).
    """
    if not text.startswith("---"):
        return None
    # Split on fence lines; the frontmatter is between the 1st and 2nd `---`.
    parts = text.split("\n")
    if parts[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    block = "\n".join(parts[1:end])
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def check_skill(skill_md: Path) -> str | None:
    """Return a violation message if this SKILL.md is a non-conforming producer.

    A producer is non-conforming when `tier == "producer"` but `gates:` is missing,
    empty, or not a non-empty list. Returns None when the skill conforms or is not a
    producer.
    """
    fm = _parse_frontmatter(skill_md.read_text())
    if fm is None:
        return None
    tier = fm.get("tier")
    if tier != "producer":
        return None  # only producers owe a gates contract (policy/08 §4)
    gates = fm.get("gates")
    if not isinstance(gates, list) or len(gates) == 0:
        return (
            f"{skill_md}: declares `tier: producer` but has no non-empty `gates:` "
            f"block. policy/08 §4: a producer skill with no gates is non-conforming "
            f"— add a `gates:` list naming the real checks its output must pass."
        )
    return None


def check_root(root: Path) -> list[str]:
    """Lint every `*/SKILL.md` under root; return the list of violation messages."""
    violations: list[str] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        msg = check_skill(skill_md)
        if msg:
            violations.append(msg)
    return violations


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    violations = check_root(root)
    if violations:
        print("producer-gate lint: FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print("producer-gate lint: OK — every producer skill declares a gates: block")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
