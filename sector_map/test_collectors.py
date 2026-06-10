#!/usr/bin/env python3
"""Tests for the v2 collectors (spec: docs/specs/2026-06-10-map-improvement-plan.md).
RED-first: written before collectors.py exists. Covers the must-know gaps:
  #5 局部数据 schema · #4 context/env · #7 三类测试分类 · G13 observability ·
  P3 context-map semantics (declared-vs-parsed) · P1 sector-card ingest.

Run:  python3 -m pytest test_collectors.py -q
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collectors  # noqa: E402


def _write(files: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    for rel, c in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(c)
    return d


class SchemaExtraction(unittest.TestCase):
    """#5 — data shapes in any language + SQL DDL, labeled heuristic."""

    def test_python_dataclass_and_pydantic(self):
        d = _write({"m.py": (
            "from dataclasses import dataclass\nfrom pydantic import BaseModel\n"
            "@dataclass\nclass User:\n    user_id: str\n    email: str\n"
            "class LoginReq(BaseModel):\n    email: str\n    password: str\n"
            "class NotASchema:\n    def run(self): pass\n")})
        out = collectors.schema_defs(d / "m.py")
        names = {s["name"]: s for s in out}
        self.assertIn("User", names)
        self.assertIn("LoginReq", names)
        self.assertNotIn("NotASchema", names)
        self.assertEqual(names["User"]["fields"], ["user_id", "email"])

    def test_kotlin_data_class_and_serializable(self):
        d = _write({"m.kt": (
            "@Serializable\ndata class RegisterRequest(val email: String, "
            "val age_confirmed_over_13: Boolean)\n"
            "class PlainService {}\n")})
        out = collectors.schema_defs(d / "m.kt")
        names = {s["name"]: s for s in out}
        self.assertIn("RegisterRequest", names)
        self.assertNotIn("PlainService", names)
        self.assertIn("age_confirmed_over_13", names["RegisterRequest"]["fields"])

    def test_ts_interface_go_struct(self):
        d = _write({
            "a.ts": "export interface Profile { id: string; name: string }\nfunction f(){}",
            "a.go": "package m\ntype Row struct {\n  ID string\n  N int\n}\nfunc F(){}",
        })
        ts = {s["name"] for s in collectors.schema_defs(d / "a.ts")}
        go = {s["name"] for s in collectors.schema_defs(d / "a.go")}
        self.assertIn("Profile", ts)
        self.assertIn("Row", go)

    def test_sql_create_table(self):
        d = _write({"mig.sql": (
            "CREATE TABLE users (\n  id uuid PRIMARY KEY,\n  email text NOT NULL\n);\n"
            "CREATE TABLE IF NOT EXISTS login_history (user_id uuid);\n")})
        out = collectors.schema_defs(d / "mig.sql")
        names = {s["name"]: s for s in out}
        self.assertIn("users", names)
        self.assertIn("login_history", names)
        self.assertIn("email", names["users"]["fields"])


class ContextExtraction(unittest.TestCase):
    """#4 — env vars + config files + outbound URLs, per language, no is_kt branch."""

    def test_env_vars_across_languages(self):
        d = _write({
            "a.py": 'import os\nJWT = os.environ["JWT_SECRET_KEY"]\nX = os.getenv("SMTP_PORT")',
            "a.ts": 'const p = process.env.API_BASE;',
            "a.kt": 'val home = System.getenv("KLIK_HOME")',
        })
        envs = collectors.env_reads([d / "a.py", d / "a.ts", d / "a.kt"])
        self.assertEqual({"JWT_SECRET_KEY", "SMTP_PORT", "API_BASE", "KLIK_HOME"}, set(envs))

    def test_outbound_urls(self):
        d = _write({"a.py": 'BASE = "https://api.example.com/v1"\nlocal = "http://127.0.0.1:8833/auth"'})
        urls = collectors.outbound_urls([d / "a.py"])
        self.assertTrue(any("api.example.com" in u for u in urls))


class TestClassification(unittest.TestCase):
    """#7 — unit/integration/e2e classification with profile override + defaults."""

    def test_default_path_classification(self):
        cls = collectors.classify_test_file
        self.assertEqual(cls("pkg/tests/unit/test_a.py", None), "unit")
        self.assertEqual(cls("KK_inttest/tests/test_db.py", None), "integration")
        self.assertEqual(cls("tests/integration/test_x.py", None), "integration")
        self.assertEqual(cls("e2e/login.spec.ts", None), "e2e")
        self.assertEqual(cls("src/auth/test_login.py", None), "unit")

    def test_contract_counts_as_integration(self):
        self.assertEqual(collectors.classify_test_file(
            "commonTest/contract/BackendAuthApiContractTest.kt", None), "integration")

    def test_profile_rules_override(self):
        rules = {"e2e": {"dirs": ["smoke"]}}
        self.assertEqual(collectors.classify_test_file("smoke/test_a.py", rules), "e2e")

    def test_matrix_shape(self):
        m = collectors.test_matrix(
            ["a/test_u.py", "tests/integration/test_i.py", "e2e/t.spec.ts"], None)
        self.assertEqual((m["unit"]["count"], m["integration"]["count"], m["e2e"]["count"]),
                         (1, 1, 1))
        self.assertEqual(m["unit"]["mark"], "✅")
        # a layer with zero tests is an explicit ❌, not silence
        m2 = collectors.test_matrix(["a/test_u.py"], None)
        self.assertEqual(m2["e2e"]["mark"], "❌")


class Observability(unittest.TestCase):
    """G13 — log-emit surface + error-code cross-ref."""

    def test_log_sites_counted_and_silent_flagged(self):
        d = _write({
            "loud.py": 'from KK_logger import get_logger\nlog = get_logger(__name__)\n'
                       'def f():\n    log.info("hi")\n    log.error("boom")',
            "silent.py": "def g():\n    return 1",
        })
        self.assertGreaterEqual(collectors.log_sites([d / "loud.py"]), 2)
        self.assertEqual(collectors.log_sites([d / "silent.py"]), 0)

    def test_error_codes_raised_vs_asserted(self):
        d = _write({
            "svc.py": 'def f():\n    raise KlikError("A0101")\ndef g():\n    raise KlikError("B0201")',
            "test_svc.py": 'def test_f():\n    assert err.error_code == "A0101"',
        })
        ec = collectors.error_codes(
            code_files=[d / "svc.py"], test_files=[d / "test_svc.py"],
            pattern=r'"([ABC]\d{4})"')
        self.assertEqual(set(ec["raised"]), {"A0101", "B0201"})
        self.assertEqual(ec["unasserted"], ["B0201"])  # raised but no test asserts it


class ContextMapSemantics(unittest.TestCase):
    """P3 — typed edges + declared-vs-parsed mismatch findings."""

    def test_mutual_dependency_is_bbom_risk(self):
        hard = {("a", "b"): 3, ("b", "a"): 1, ("a", "c"): 2}
        out = collectors.typed_edges(hard, declared=[])
        by = {(e["src"], e["dst"]): e for e in out}
        self.assertEqual(by[("a", "b")]["relationship"], "mutually-dependent")
        self.assertEqual(by[("a", "c")]["relationship"], "upstream-downstream")

    def test_declared_pattern_attaches(self):
        hard = {("ui", "core"): 5}
        declared = [{"src": "ui", "dst": "core", "pattern": "conformist"}]
        out = collectors.typed_edges(hard, declared)
        e = next(x for x in out if x["src"] == "ui")
        self.assertEqual(e["pattern"], "conformist")

    def test_separate_ways_violation_found(self):
        hard = {("a", "b"): 2}
        declared = [{"src": "a", "dst": "b", "pattern": "separate-ways"}]
        findings = collectors.contextmap_findings(hard, declared)
        self.assertTrue(any("separate-ways" in f for f in findings))

    def test_declared_edge_never_parsed_is_flagged(self):
        findings = collectors.contextmap_findings(
            {}, [{"src": "x", "dst": "y", "pattern": "customer-supplier"}])
        self.assertTrue(any("never observed" in f for f in findings))


class SectorCardIngest(unittest.TestCase):
    """P1 — purpose auto-ingested from a sector's CLAUDE.md / README.md first paragraph."""

    def test_claude_md_first_paragraph_wins(self):
        d = _write({"auth/CLAUDE.md": "# KK_auth\n\nUser authentication: JWT, OAuth.\n\nMore prose.",
                    "auth/README.md": "# other\n\nwrong one"})
        card = collectors.sector_card(d / "auth")
        self.assertEqual(card["purpose"], "User authentication: JWT, OAuth.")
        self.assertTrue(card["docs"][0].endswith("CLAUDE.md"))

    def test_no_docs_is_empty_not_invented(self):
        d = _write({"bare/x.py": "pass"})
        card = collectors.sector_card(d / "bare")
        self.assertIsNone(card["purpose"])
        self.assertEqual(card["docs"], [])


if __name__ == "__main__":
    unittest.main(verbosity=1)


class BuildGraphIntegration(unittest.TestCase):
    """The collectors wired into build_graph: new keys present on every sector."""

    def _graph(self):
        import extract
        d = _write({
            "auth/CLAUDE.md": "# auth\n\nLogin and tokens.\n",
            "auth/svc.py": ('import os\nfrom KK_logger import get_logger\n'
                            'log = get_logger(__name__)\n'
                            'KEY = os.environ["JWT_SECRET"]\n'
                            'def f():\n    log.info("x")\n    raise KlikError("B0201")\n'),
            "auth/models.py": "from dataclasses import dataclass\n@dataclass\nclass User:\n    uid: str",
            "auth/mig.sql": "CREATE TABLE users (id uuid);",
            "core/util.py": "def helper(): return 1",
            "core/test_util.py": "def test_h(): assert True",
            "e2e/test_flow.py": "def test_flow(): assert True",
        })
        prof = {"label": "toy", "lang": "py", "git_root": ".", "src_base": "", "test_base": "",
                "import_prefix": "", "resolve": "py_stem", "catalog_project": None,
                "deploy_symlinks": False, "behavior": [], "boundaries_global": [],
                "boundaries_by_sector": {}, "error_code_pattern": r'"([ABC]\d{4})"',
                "edges": [{"src": "auth", "dst": "e2e", "pattern": "separate-ways"}],
                "sectors": [
                    {"id": "auth", "root": "auth",
                     "constraints": {"forbidden": ["default user IDs"], "required": ["401 on missing auth"]}},
                    {"id": "core", "root": "core"},
                    {"id": "e2e", "root": "e2e"}]}
        return extract.build_graph(d, prof)

    def test_new_dimensions_present(self):
        g = self._graph()
        auth = next(s for s in g["sectors"] if s["id"] == "auth")
        d = auth["dimensions"]
        self.assertEqual(auth["purpose"], "Login and tokens.")
        self.assertEqual(d["behavior"]["constraints"]["forbidden"], ["default user IDs"])
        schema_names = {x["name"] for x in d["structure"]["schema"]}
        self.assertIn("User", schema_names)
        self.assertIn("users", schema_names)  # SQL DDL
        self.assertIn("JWT_SECRET", d["context"]["env"])
        self.assertGreaterEqual(d["change_safety"]["log_sites"], 1)
        self.assertIn("B0201", d["change_safety"]["error_codes"]["unasserted"])
        core = next(s for s in g["sectors"] if s["id"] == "core")
        self.assertEqual(core["dimensions"]["tests_coverage"]["matrix"]["unit"]["count"], 1)
        self.assertEqual(core["dimensions"]["change_safety"]["log_sites"], 0)

    def test_contextmap_on_graph(self):
        g = self._graph()
        self.assertIn("contextmap", g)
        self.assertTrue(isinstance(g["contextmap"]["findings"], list))
