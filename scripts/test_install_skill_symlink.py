#!/usr/bin/env python3
"""Regression test for skill install dirtiness.

The bug: copying a skill onto an existing symlinked install destination dirties
its source checkout on macOS (`cp -R src dest` follows symlinked dest and creates
`src/basename(src)`). The installer must be symlink-only and idempotent.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "install_skill_symlink.sh"


class InstallSkillSymlink(unittest.TestCase):
    def test_idempotent_install_does_not_create_nested_skill_dir(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            src = root / "repo" / "no-new-bugs"
            src.mkdir(parents=True)
            (src / "SKILL.md").write_text("# No New Bugs\n")
            dest_root = root / "role" / "skills"

            first = subprocess.run(
                [str(SCRIPT), str(src), str(dest_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("linked", first.stdout)
            self.assertTrue((dest_root / "no-new-bugs").is_symlink())

            second = subprocess.run(
                [str(SCRIPT), str(src), str(dest_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("already linked", second.stdout)
            self.assertFalse(
                (src / "no-new-bugs").exists(),
                "idempotent install must not copy the skill into itself",
            )

    def test_indirect_symlink_to_same_source_is_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            src = root / "repo" / "no-bugs-first"
            src.mkdir(parents=True)
            (src / "SKILL.md").write_text("# No Bugs First\n")
            global_root = root / "global" / "skills"
            role_root = root / "role" / "skills"
            global_root.mkdir(parents=True)
            role_root.mkdir(parents=True)
            (global_root / "no-bugs-first").symlink_to(src)
            (role_root / "no-bugs-first").symlink_to(global_root / "no-bugs-first")

            result = subprocess.run(
                [str(SCRIPT), str(src), str(role_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("already linked", result.stdout)
            self.assertFalse((src / "no-bugs-first").exists())

    def test_refuses_to_overwrite_role_local_skill(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            src = root / "repo" / "bug-regression-catalog"
            src.mkdir(parents=True)
            (src / "SKILL.md").write_text("# Catalog\n")
            dest = root / "role" / "skills" / "bug-regression-catalog"
            dest.mkdir(parents=True)
            (dest / "SKILL.md").write_text("# local\n")

            result = subprocess.run(
                [str(SCRIPT), str(src), str(dest.parent)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to overwrite", result.stderr)
            self.assertEqual((dest / "SKILL.md").read_text(), "# local\n")


if __name__ == "__main__":
    unittest.main()
