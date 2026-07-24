#!/usr/bin/env python3
"""Both-direction tests for core skill routing to canonical Policy 13."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_simulation_contract_skill_refs import REQUIRED_FILES, REQUIRED_TEXT, check_root


class SimulationContractSkillRefsTest(unittest.TestCase):
    def write_fixture(self, root: Path, content: str) -> None:
        for relative in REQUIRED_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def test_complete_references_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_fixture(root, "\n".join(REQUIRED_TEXT))
            self.assertEqual(check_root(root), [])

    def test_missing_canonical_policy_reference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = "\n".join(text for text in REQUIRED_TEXT if "policy/13" not in text)
            self.write_fixture(root, content)
            violations = check_root(root)
            self.assertEqual(len(violations), 2)
            self.assertTrue(all("policy/13" in violation for violation in violations))

    def test_legacy_prompt_variables_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = "\n".join(REQUIRED_TEXT) + "\nLegacy `variables` remain admitted."
            self.write_fixture(root, content)
            violations = check_root(root)
            self.assertEqual(len(violations), 2)
            self.assertTrue(all("variables" in violation for violation in violations))

    def test_partial_prompt_owner_migration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = "\n".join(REQUIRED_TEXT) + "\nPartial migration remains admitted."
            self.write_fixture(root, content)
            violations = check_root(root)
            self.assertEqual(len(violations), 2)
            self.assertTrue(all("partial migration" in violation.lower() for violation in violations))

    def test_live_skills_conform(self) -> None:
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(check_root(root), [])


if __name__ == "__main__":
    unittest.main()
