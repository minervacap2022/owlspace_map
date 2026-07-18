#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_doctrine_ci_scaffold import check_root


class DoctrineCiScaffoldTest(unittest.TestCase):
    def make_root(self, skill_text: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        skill_dir = root / "no-bugs-first"
        templates = skill_dir / "templates"
        templates.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(skill_text)
        change_dir = root / "no-new-bugs"
        change_dir.mkdir()
        (templates / "woodpecker-ci.yaml").write_text("steps:\n")
        (templates / "ci-success-bridge.sh").write_text("#!/usr/bin/env bash\n")
        return root

    def add_change_skill(self, root: Path, text: str) -> None:
        change_dir = root / "no-new-bugs"
        (change_dir / "SKILL.md").write_text(text)

    def test_accepts_canonical_woodpecker_scaffold(self):
        root = self.make_root(
            "Use templates/woodpecker-ci.yaml and templates/ci-success-bridge.sh.\n"
        )
        self.assertEqual(check_root(root), [])

    def test_rejects_github_actions_scaffold(self):
        root = self.make_root(
            "Add .github/workflows/ci.yml. Also see templates/woodpecker-ci.yaml "
            "and templates/ci-success-bridge.sh.\n"
        )
        self.assertIn(
            "no-bugs-first must not scaffold GitHub Actions for governed repos",
            check_root(root),
        )

    def test_rejects_legacy_enterprise_ruleset_claim(self):
        root = self.make_root(
            "The enterprise ruleset requires ci-success. Use templates/woodpecker-ci.yaml "
            "and templates/ci-success-bridge.sh.\n"
        )
        self.assertIn(
            "no-bugs-first must not claim an enterprise ruleset enforces ci-success",
            check_root(root),
        )

    def test_rejects_github_actions_scheduled_test_instruction(self):
        root = self.make_root(
            "Use templates/woodpecker-ci.yaml and templates/ci-success-bridge.sh.\n"
        )
        self.add_change_skill(root, "Put the cron under .github/workflows/tests.yml.\n")
        self.assertIn(
            "no-new-bugs must not prescribe GitHub Actions for governed scheduled tests",
            check_root(root),
        )

    def test_rejects_runtime_self_updater(self):
        root = self.make_root(
            "Use templates/woodpecker-ci.yaml and templates/ci-success-bridge.sh.\n"
        )
        (root / "no-bugs-first/self_update.sh").write_text("git fetch origin main\n")
        self.assertIn(
            "no-bugs-first must not runtime self-update from mutable remote code",
            check_root(root),
        )

    def test_current_repository_conforms(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(check_root(root), [])


if __name__ == "__main__":
    unittest.main()
