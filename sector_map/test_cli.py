#!/usr/bin/env python3
"""Tests for the agent-facing CLI (cli.py) — so the agent's own entrypoint clears
its bar. Covers the three gaps closed in this change:
  1. path→sector resolution (an agent has a FILE path, not a sector name)
  2. consumers-tests surfaces the RISK (uncovered consumers) first, not buried
  3. `init` bootstraps a profile for any repo by auto-detecting sectors

Run:  python3 test_cli.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli  # noqa: E402
import extract  # noqa: E402


def _write(files: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    for rel, c in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(c)
    return d


def _prof(sectors):
    return {"label": "toy", "lang": "py", "git_root": ".", "src_base": "", "test_base": "",
            "import_prefix": "", "resolve": "py_stem", "catalog_project": None,
            "deploy_symlinks": False, "behavior": [], "boundaries_global": [],
            "boundaries_by_sector": {}, "sectors": [{"id": s, "root": s} for s in sectors]}


class ResolveSector(unittest.TestCase):
    """An agent passes a file path; the CLI maps it to the sector it lives in."""

    def setUp(self):
        self.d = _write({
            "core/m.py": "def helper(): return 1",
            "api/svc.py": "from core.m import helper\ndef serve(): return helper()",
        })
        self.g = extract.build_graph(self.d, _prof(["core", "api"]))

    def test_sector_id_resolves_to_itself(self):
        self.assertEqual(cli._resolve_sector(self.g, "api"), "api")

    def test_full_relative_path_resolves(self):
        self.assertEqual(cli._resolve_sector(self.g, "api/svc.py"), "api")

    def test_bare_filename_resolves(self):
        self.assertEqual(cli._resolve_sector(self.g, "svc.py"), "api")

    def test_unknown_returns_none(self):
        self.assertIsNone(cli._resolve_sector(self.g, "nope/x.py"))

    def test_brief_accepts_a_file_path(self):
        self.assertEqual(cli.brief(self.g, "api/svc.py")["sector"], "api")

    def test_blast_radius_accepts_a_file_path(self):
        self.assertEqual(cli.blast_radius(self.g, "core/m.py")["sector"], "core")


class ConsumersRiskFirst(unittest.TestCase):
    """consumers-tests must lead with the uncovered consumers (the silent-break risk)."""

    def test_uncovered_consumer_is_surfaced_and_ordered_first(self):
        d = _write({
            "core/m.py": "def helper(): return 1",
            "core/test_m.py": "from core.m import helper\ndef test_h():\n assert helper() == 1",
            "api/svc.py": "from core.m import helper\ndef serve(): return helper()",
        })
        g = extract.build_graph(d, _prof(["core", "api"]))
        r = cli.consumers_tests(g, "core")
        self.assertIn("api", r["blast_radius"], "api depends on core")
        self.assertEqual(r["uncovered_consumers"], ["api"], "api has no tests → the risk")
        keys = list(r.keys())
        self.assertLess(keys.index("uncovered_consumers"),
                        keys.index("tests_to_run_before_and_after"),
                        "the risk must be surfaced BEFORE the bulky test list")


class Init(unittest.TestCase):
    """`init` materializes a starter profile by auto-detecting top-level dirs."""

    def test_init_writes_profile_with_detected_sectors(self):
        repo = _write({"alpha/a.py": "x=1", "beta/b.py": "y=2"})
        out = repo / "prof.json"
        res = cli.init(["init", "--repo", str(repo), "--out", str(out)])
        self.assertTrue(out.exists(), "profile file written")
        ids = {s["id"] for s in json.loads(out.read_text())["sectors"]}
        self.assertTrue({"alpha", "beta"}.issubset(ids))
        self.assertIn("alpha", res["sectors_detected"])
        self.assertTrue(any("server.py" in n for n in res["next"]), "tells you how to launch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
