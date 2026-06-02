#!/usr/bin/env python3
"""Committed tests for the sector-map extractor — so the tool clears its OWN bar
(dimension #7). Covers: universal multi-language parsing, the name-resolved call
graph, blast radius / cycles end-to-end, and the self-map invariants.

Run:  python3 test_extract.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract  # noqa: E402


def _write(files: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return d


class UniversalParsing(unittest.TestCase):
    def test_symbols_across_languages(self):
        cases = {
            "a.py": ("def foo(): pass\nclass Bar: pass", {"foo", "Bar"}),
            "a.kt": ("class Foo\nfun baz(){}", {"Foo", "baz"}),
            "a.go": ("package m\nfunc F(){}\ntype T struct{}", {"F", "T"}),
            "a.ts": ("export function f(){}\nexport class C{}", {"f", "C"}),
            "a.rs": ("fn f(){}\nstruct S;", {"f", "S"}),
            "a.java": ("class K {}", {"K"}),
        }
        for fn, (src, expect) in cases.items():
            d = _write({fn: src})
            got = set(extract._symbols(d / fn))
            self.assertTrue(expect.issubset(got), f"{fn}: expected {expect} ⊆ {got}")

    def test_imports_across_languages(self):
        d = _write({"a.kt": "import a.b.C\nclass X", "a.go": 'package m\nimport "x/y"',
                    "a.py": "from a.b import c"})
        self.assertIn("a.b.C", extract._imports(d / "a.kt"))
        self.assertIn("x/y", extract._imports(d / "a.go"))
        self.assertIn("a.b", extract._imports(d / "a.py"))


class CallGraph(unittest.TestCase):
    def test_calls_resolve_with_in_out_and_coupling(self):
        d = _write({
            "core/util.py": "def helper(): return 1",
            "api/svc.py": "from core.util import helper\ndef serve():\n helper()\n local()\ndef local(): return 2",
        })
        raw = {"core": {"code": [d / "core/util.py"]}, "api": {"code": [d / "api/svc.py"]}}
        syms, edges, sec = extract._symbol_graph(raw, d)
        by_name = {s["name"]: s for s in syms.values()}
        self.assertEqual(by_name["helper"]["inc"], 1, "helper called once")
        self.assertEqual(by_name["local"]["inc"], 1, "local called once")
        out = {syms[o]["name"] for o in by_name["serve"]["out"]}
        self.assertEqual(out, {"helper", "local"}, "serve calls both")
        self.assertEqual(sec.get(("api", "core")), 1, "api→core call coupling counted")


class EndToEnd(unittest.TestCase):
    def test_go_blast_and_leaf(self):
        d = _write({
            "core/t.go": "package core\ntype A struct{}\nfunc New() *A { return &A{} }",
            "api/c.go": 'package api\nimport "demo/core"\nfunc Fetch() *core.A { return core.New() }',
            "ui/v.go": 'package ui\nimport ("demo/api"; "demo/core")\nfunc V(a *core.A) { api.Fetch() }',
        })
        prof = {"label": "go", "lang": "go", "git_root": ".", "src_base": "", "test_base": "",
                "import_prefix": "demo/", "resolve": "kt_pkg", "catalog_project": None,
                "deploy_symlinks": False, "behavior": [], "boundaries_global": [],
                "boundaries_by_sector": {}, "sectors": [{"id": "api", "root": "api"},
                {"id": "core", "root": "core"}, {"id": "ui", "root": "ui"}]}
        g = extract.build_graph(d, prof)
        cs = {s["id"]: s["dimensions"]["change_safety"] for s in g["sectors"]}
        self.assertEqual(set(cs["core"]["blast_radius"]), {"api", "ui"}, "core is foundational")
        self.assertEqual(cs["ui"]["blast_radius"], [], "ui is a leaf")

    def test_cycle_is_detected(self):
        d = _write({
            "a/x.go": 'package a\nimport "m/b"\nfunc Ax() { b.Bx() }',
            "b/y.go": 'package b\nimport "m/a"\nfunc Bx() { a.Ax() }',
        })
        prof = {"label": "cyc", "lang": "go", "git_root": ".", "src_base": "", "test_base": "",
                "import_prefix": "m/", "resolve": "kt_pkg", "catalog_project": None,
                "deploy_symlinks": False, "behavior": [], "boundaries_global": [],
                "boundaries_by_sector": {}, "sectors": [{"id": "a", "root": "a"}, {"id": "b", "root": "b"}]}
        g = extract.build_graph(d, prof)
        cyc = {s["id"]: s["dimensions"]["change_safety"]["cycles"] for s in g["sectors"]}
        self.assertEqual(cyc["a"], ["b"])
        self.assertEqual(cyc["b"], ["a"])


def _prof(lang, prefix, sectors):
    return {"label": lang, "lang": lang, "git_root": ".", "src_base": "", "test_base": "",
            "import_prefix": prefix, "resolve": "kt_pkg", "catalog_project": None,
            "deploy_symlinks": False, "behavior": [], "boundaries_global": [],
            "boundaries_by_sector": {}, "sectors": [{"id": s, "root": s} for s in sectors]}


def _dep_edges(g):
    return {(e["src"], e["dst"]) for e in g["edges"] if e["kind"] == "depends_on"}


class MultiLangEdges(unittest.TestCase):
    def test_ts_relative_imports_resolve(self):
        d = _write({"core/t.ts": "export class T{}",
                    "ui/v.ts": 'import {T} from "../core/t"; export function v(){}'})
        self.assertIn(("ui", "core"), _dep_edges(extract.build_graph(d, _prof("ts", "", ["core", "ui"]))))

    def test_c_include_resolves(self):
        d = _write({"core/core.h": "int f();",
                    "app/main.c": '#include "../core/core.h"\nint main(){ return f(); }'})
        self.assertIn(("app", "core"), _dep_edges(extract.build_graph(d, _prof("c", "", ["core", "app"]))))

    def test_per_language_test_detection(self):
        d = _write({"pkg/m.go": "package pkg\nfunc F(){}",
                    "pkg/m_test.go": "package pkg\nimport \"testing\"\nfunc TestF(t *testing.T){}"})
        g = extract.build_graph(d, _prof("go", "", ["pkg"]))
        cov = g["sectors"][0]["dimensions"]["tests_coverage"]
        self.assertTrue(cov["covered"], "Go *_test.go should count as covered")
        self.assertEqual(cov["test_count"], 1)


class Coverage(unittest.TestCase):
    def test_real_line_coverage_ingested(self):
        d = _write({
            "core/a.py": "def f():\n    return 1\ndef g():\n    return 2",
            "coverage.xml": '<coverage><packages><package><classes>'
            '<class filename="core/a.py"><lines>'
            '<line number="1" hits="1"/><line number="2" hits="1"/>'
            '<line number="3" hits="0"/><line number="4" hits="0"/>'
            '</lines></class></classes></package></packages></coverage>'})
        prof = _prof("py", "", ["core"])
        prof["resolve"] = "py_stem"
        tc = extract.build_graph(d, prof)["sectors"][0]["dimensions"]["tests_coverage"]
        self.assertEqual(tc["coverage_pct"], 50, "2 of 4 lines covered")
        self.assertTrue(any(u.startswith("g (") for u in tc["uncovered_surface"]),
                        f"def g (line 3, 0 hits) should be uncovered: {tc['uncovered_surface']}")


class SelfMap(unittest.TestCase):
    def test_owlspace_self_map_invariants(self):
        g = extract.build_graph()  # no profile → maps owlspace_map itself
        ids = {s["id"] for s in g["sectors"]}
        self.assertIn("bug-regression-catalog", ids)
        cat = next(s for s in g["sectors"] if s["id"] == "bug-regression-catalog")
        self.assertEqual(set(cat["dimensions"]["change_safety"]["blast_radius"]),
                         {"production-rules-checker", "sector_map"}, "catalog is foundational")
        self.assertGreater(len(g["symbols"]), 0, "symbol graph non-empty")

    def test_every_sector_has_all_seven_dimensions(self):
        g = extract.build_graph()
        seven = {"structure", "behavior", "context", "boundaries",
                 "intent_history", "change_safety", "tests_coverage"}
        for s in g["sectors"]:
            self.assertEqual(set(s["dimensions"]) & seven, seven, f"{s['id']} missing a dimension")


if __name__ == "__main__":
    unittest.main(verbosity=2)
