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
    _globs_of, _lint_project, _intent,
)

# Lying guards that PRE-DATE the routing invariant below: each has a `pattern` but
# is enforced NOWHERE — either no rule+message (so not a forbidden lint), or a
# MUST_/HAS_ rule lacking the explicit `presence: required` (so required_guards()
# won't load it; it never infers, by design). Tracked tech-debt, NOT acceptable
# long-term. This set may only SHRINK: to fix one, add `presence: required` (and
# verify the pattern matches its target file so the guard doesn't false-fail) or
# rule+message, then delete its id here. See BUG-2026-06-03-461e97.
KNOWN_UNENFORCED = frozenset({
    "BUG-2026-05-29-B", "BUG-2026-05-29-D", "BUG-2026-05-29-M",
    "BUG-2026-06-01-E", "BUG-2026-06-02-9c936c", "BUG-2026-06-02-B",
    "BUG-2026-06-02-C", "BUG-2026-06-02-D", "BUG-2026-06-02-E",
    "BUG-2026-06-02-F", "BUG-2026-06-02-H", "BUG-2026-06-02-I",
    "BUG-2026-06-02-J", "BUG-2026-06-02-K", "BUG-2026-06-02-a79689",
})


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

    def test_every_pattern_bearing_lint_is_actually_enforced(self):
        # The THIRD loader meta-bug: a lint that HAS a `pattern` but the wrong key
        # shape routes to NEITHER lint_patterns() (forbidden) NOR required_guards()
        # (presence:required) — a LYING GUARD, enforced nowhere, silently. (Exactly
        # what the BUG-2026-06-03-6f9f53 403 entry was before it was fixed.)
        # This invariant exposed 15 PRE-EXISTING lying guards (see KNOWN_UNENFORCED):
        # a ratchet — the baseline may only SHRINK; a NEW one (or a stale id) fails.
        nowhere = set()
        for bug in load():
            lint = bug.get("lint")
            for entry in (lint if isinstance(lint, list) else [lint]) if lint else []:
                if not (isinstance(entry, dict) and entry.get("pattern")):
                    continue
                forbidden_ok = (all(k in entry for k in ("rule", "pattern", "message"))
                                and _intent(entry) == "forbidden")
                required_ok = (entry.get("presence") == "required"
                               and entry.get("rule") and _globs_of(entry))
                if not (forbidden_ok or required_ok):
                    nowhere.add(bug["id"])
        new = nowhere - KNOWN_UNENFORCED
        self.assertEqual(new, set(), f"NEW lying guard(s) — a lint has a pattern but is enforced NOWHERE; "
                                     f"add `presence: required` or rule+message: {sorted(new)}")
        stale = KNOWN_UNENFORCED - nowhere
        self.assertEqual(stale, set(), f"baseline is STALE — these are now enforced (or removed); "
                                       f"delete them from KNOWN_UNENFORCED so the ratchet tightens: {sorted(stale)}")

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
