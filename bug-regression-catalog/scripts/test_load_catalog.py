#!/usr/bin/env python3
"""Standing trip-wire for the catalog loader.

This file exists because the loader has TWICE been the meta-bug: it silently
crashed on a dict-shaped lint entry and returned 0 lints (lying green), and it
silently dropped a mis-classified entry under the project filter. Every check
below was once a throwaway `python3 -c` one-liner that protected nothing; here
they are committed so the day a fresh edit breaks a settled invariant, this goes
red instead of the catalog going quietly dead.

Run:  python3 test_load_catalog.py    (no deps beyond PyYAML)
"""
from __future__ import annotations

import unittest

from load_catalog import (
    load, lint_patterns, required_guards,
    _globs_of, _lint_project,
)


class CatalogLoaderInvariants(unittest.TestCase):
    def test_load_does_not_crash_and_is_nonempty(self):
        bugs = load()
        self.assertGreater(len(bugs), 0, "catalog loaded zero entries")

    def test_ids_are_unique(self):
        ids = [b["id"] for b in load()]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dups, [], f"duplicate catalog ids (the single key): {dups}")

    def test_minted_ids_are_unique_and_well_formed(self):
        # new_bug_id.py must mint collision-free ids (random, not sequential) so
        # concurrent appenders never need to coordinate. Prove: well-formed, never
        # collides with an existing id, and 200 draws are all distinct.
        from new_bug_id import mint, _existing_ids
        existing = _existing_ids()
        minted = {mint("2026-06-02") for _ in range(200)}
        self.assertEqual(len(minted), 200, "minted ids collided with each other")
        self.assertTrue(minted.isdisjoint(existing), "a minted id already exists in the catalog")
        for bid in minted:
            self.assertRegex(bid, r"^BUG-2026-06-02-[0-9a-f]{6}$", f"malformed minted id: {bid}")

    def test_forbidden_lints_load_nonzero(self):
        # The original silent-crash returned 0 here while the catalog looked fine.
        self.assertGreater(len(lint_patterns()), 0, "0 forbidden lints — loader is lying green")

    def test_required_guards_load_nonzero(self):
        self.assertGreater(len(required_guards()), 0, "0 required guards loaded")

    def test_every_rule_bearing_entry_classifies_to_a_known_project(self):
        # An 'unknown' project = silently dropped under --project <x>. Catch it here.
        unknown = []
        for bug in load():
            lint = bug.get("lint")
            for entry in (lint if isinstance(lint, list) else [lint]) if lint else []:
                if not isinstance(entry, dict) or "rule" not in entry:
                    continue
                if _lint_project(_globs_of(entry), bug.get("source_files")) == "unknown":
                    unknown.append((bug["id"], entry["rule"]))
        self.assertEqual(unknown, [], f"lints with no derivable project (silently dropped under filter): {unknown}")

    def test_project_filter_keeps_klik_drops_foreign(self):
        klik_req = {r for r, *_ in required_guards({"klik"})}
        all_req = {r for r, *_ in required_guards()}
        klik_forb = {r for r, *_ in lint_patterns({"klik"})}
        all_forb = {r for r, *_ in lint_patterns()}
        # A Klik firmware guard stays under --project klik...
        self.assertIn("AXP192_MUST_POWER_LDOIO0_FOR_MIC", klik_req)
        # ...an EVE guard is present unfiltered but drops under --project klik.
        self.assertIn("AUTO_EXEC_WORKERS_MUST_GATE_ON_FLAG", all_req)
        self.assertNotIn("AUTO_EXEC_WORKERS_MUST_GATE_ON_FLAG", klik_req)
        # Same for a forbidden Owl lint.
        self.assertIn("OWL_CLAUDECMD_NO_RAW_RESOLVE", all_forb)
        self.assertNotIn("OWL_CLAUDECMD_NO_RAW_RESOLVE", klik_forb)


if __name__ == "__main__":
    unittest.main(verbosity=2)
