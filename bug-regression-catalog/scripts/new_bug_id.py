#!/usr/bin/env python3
"""Mint a GENUINELY-unique catalog bug id.

    BUG-<date>-<rand>      e.g.  BUG-2026-06-02-a3f9c1

Why random, not the old sequential `BUG-<date>-A/B/C…`: a sequential suffix means
"pick the next free letter", which *requires coordination* — two agents appending
concurrently both read the same catalog and both pick the same next letter, so they
collide and break the catalog (the loader's id-uniqueness guard then fails loud).
A random token needs no coordination: independent minters draw from a 16.7M space,
so a clash is astronomically unlikely, and we additionally re-draw on the off chance
the token already exists. This removes the collision class at the source; the loader
guard stays as defense-in-depth.

Reads the catalog WITHOUT validating it (raw YAML), so it still mints a fresh id
even when the catalog is momentarily broken (e.g. mid-collision).

Usage:
    python3 scripts/new_bug_id.py            # date = today
    python3 scripts/new_bug_id.py --date 2026-06-02
"""
from __future__ import annotations

import secrets
import sys
from datetime import date
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog.yaml"


def _existing_ids() -> set[str]:
    """All ids currently in the catalog, read raw (no dup-validation) so the
    minter works even if the catalog is temporarily malformed."""
    try:
        import yaml  # noqa
    except ImportError:
        return set()
    if not CATALOG_PATH.exists():
        return set()
    data = yaml.safe_load(CATALOG_PATH.read_text()) or {}
    return {b.get("id") for b in data.get("bugs", []) if isinstance(b, dict) and b.get("id")}


def mint(on_date: str | None = None) -> str:
    d = on_date or date.today().isoformat()
    existing = _existing_ids()
    for _ in range(10_000):
        candidate = f"BUG-{d}-{secrets.token_hex(3)}"  # 6 hex chars
        if candidate not in existing:
            return candidate
    raise RuntimeError("could not mint a unique bug id (catalog implausibly large)")


if __name__ == "__main__":
    args = sys.argv[1:]
    on_date = None
    if "--date" in args:
        i = args.index("--date")
        if i + 1 < len(args):
            on_date = args[i + 1]
    print(mint(on_date))
