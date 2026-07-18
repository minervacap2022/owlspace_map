#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATERS = (
    ROOT / "no-bugs-first/self_update.sh",
    ROOT / "no-new-bugs/self_update.sh",
)


FAKE_GIT = r"""#!/usr/bin/env bash
set -u
printf '%s\n' "$*" >> "$FAKE_GIT_LOG"
args="$*"
case "$args" in
  *"rev-parse --show-toplevel"*) printf '%s\n' "$FAKE_REPO" ;;
  *"remote get-url origin"*) printf '%s\n' "$FAKE_ORIGIN" ;;
  *"ls-remote --symref origin HEAD"*)
    if [ "$FAKE_REMOTE_HEAD" = offline ]; then exit 2; fi
    printf 'ref: refs/heads/%s\tHEAD\n' "$FAKE_REMOTE_HEAD"
    printf 'deadbeef\tHEAD\n'
    ;;
  *"fetch --quiet origin main"*) exit "${FAKE_FETCH_EXIT:-0}" ;;
  *"diff --quiet origin/main --"*) exit "${FAKE_UP_TO_DATE:-1}" ;;
  *"diff --quiet HEAD --"*) exit "${FAKE_LOCAL_DIRTY:-0}" ;;
  *"ls-files --others --exclude-standard --"*) printf '%s' "${FAKE_UNTRACKED:-}" ;;
  *"log --format=%H origin/main..HEAD --"*) printf '%s' "${FAKE_LOCAL_COMMITS:-}" ;;
  *"rev-list --count HEAD..origin/main --"*) printf '1\n' ;;
  *"restore --source origin/main --worktree --"*) touch "$FAKE_RESTORE_MARKER" ;;
  *"symbolic-ref"*) printf 'origin/evil\n' ;;
  *) printf 'unexpected fake git call: %s\n' "$args" >&2; exit 97 ;;
esac
"""


class DoctrineSelfUpdateTrustTest(unittest.TestCase):
    def run_updater(self, updater: Path, **overrides: str) -> tuple[subprocess.CompletedProcess[str], Path, str]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        repo = root / "repo"
        skill_dir = repo / updater.parent.name
        skill_dir.mkdir(parents=True)
        copied = skill_dir / "self_update.sh"
        shutil.copy2(updater, copied)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(FAKE_GIT)
        fake_git.chmod(0o755)
        marker = root / "restored"
        log = root / "git.log"
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fake_bin}:{env['PATH']}",
                "FAKE_GIT_LOG": str(log),
                "FAKE_REPO": str(repo),
                "FAKE_ORIGIN": "https://github.com/minervacap2022/owlspace_map.git",
                "FAKE_REMOTE_HEAD": "main",
                "FAKE_RESTORE_MARKER": str(marker),
            }
        )
        env.update(overrides)
        result = subprocess.run(["bash", str(copied)], text=True, capture_output=True, env=env)
        return result, marker, log.read_text()

    def for_each_updater(self):
        return self.subTest

    def test_canonical_origin_and_server_main_are_accepted(self):
        for updater in UPDATERS:
            with self.subTest(updater=updater.parent.name):
                result, marker, log = self.run_updater(updater)
                self.assertEqual(result.returncode, 0)
                self.assertTrue(marker.exists())
                self.assertIn("ls-remote --symref origin HEAD", log)
                self.assertNotIn("symbolic-ref", log)

    def test_repointed_origin_is_rejected(self):
        for updater in UPDATERS:
            with self.subTest(updater=updater.parent.name):
                result, marker, log = self.run_updater(updater, FAKE_ORIGIN="https://example.com/fork.git")
                self.assertEqual(result.returncode, 0)
                self.assertFalse(marker.exists())
                self.assertNotIn("ls-remote", log)
                self.assertIn("unverified remote", result.stdout)

    def test_server_default_ref_must_be_main(self):
        for updater in UPDATERS:
            with self.subTest(updater=updater.parent.name):
                result, marker, _ = self.run_updater(updater, FAKE_REMOTE_HEAD="develop")
                self.assertEqual(result.returncode, 0)
                self.assertFalse(marker.exists())
                self.assertIn("canonical ref", result.stdout)

    def test_local_skill_edits_still_block_overwrite(self):
        for updater in UPDATERS:
            with self.subTest(updater=updater.parent.name):
                result, marker, _ = self.run_updater(updater, FAKE_LOCAL_DIRTY="1")
                self.assertEqual(result.returncode, 0)
                self.assertFalse(marker.exists())
                self.assertIn("local edits", result.stdout)

    def test_offline_server_check_remains_fail_soft(self):
        for updater in UPDATERS:
            with self.subTest(updater=updater.parent.name):
                result, marker, _ = self.run_updater(updater, FAKE_REMOTE_HEAD="offline")
                self.assertEqual(result.returncode, 0)
                self.assertFalse(marker.exists())
                self.assertIn("using local copy", result.stdout)


if __name__ == "__main__":
    unittest.main()
