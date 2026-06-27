#!/usr/bin/env python3
"""Trip-wire for the producer-gate lint (policy/08 §4 enforcement arm).

Proves the lint BOTH directions — it must pass on a conforming producer AND fire on
a non-conforming one — and that it leaves non-producers alone. A lint that can only
pass is false-green; these cases plant real violations and assert detection.

Run:  python3 scripts/test_check_producer_gates.py   (no deps beyond PyYAML)
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_producer_gates import check_root, check_skill


def _write(d: Path, name: str, frontmatter: str, body: str = "# body\n") -> Path:
    skill_dir = d / name
    skill_dir.mkdir(parents=True)
    md = skill_dir / "SKILL.md"
    md.write_text(f"---\n{frontmatter}\n---\n\n{body}")
    return md


class ProducerGateLint(unittest.TestCase):
    def test_producer_without_gates_fails(self):
        with tempfile.TemporaryDirectory() as t:
            md = _write(Path(t), "p", "name: p\ndescription: d\ntier: producer")
            self.assertIsNotNone(check_skill(md))

    def test_producer_with_empty_gates_fails(self):
        with tempfile.TemporaryDirectory() as t:
            md = _write(Path(t), "p", "name: p\ndescription: d\ntier: producer\ngates: []")
            self.assertIsNotNone(check_skill(md))

    def test_producer_with_gates_passes(self):
        with tempfile.TemporaryDirectory() as t:
            md = _write(
                Path(t), "p",
                "name: p\ndescription: d\ntier: producer\ngates:\n  - repo-guards\n  - commit-policy",
            )
            self.assertIsNone(check_skill(md))

    def test_analyzer_without_gates_passes(self):
        with tempfile.TemporaryDirectory() as t:
            md = _write(Path(t), "a", "name: a\ndescription: d\ntier: analyzer")
            self.assertIsNone(check_skill(md))

    def test_no_tier_passes(self):
        with tempfile.TemporaryDirectory() as t:
            md = _write(Path(t), "n", "name: n\ndescription: d")
            self.assertIsNone(check_skill(md))

    def test_no_frontmatter_passes(self):
        with tempfile.TemporaryDirectory() as t:
            skill_dir = Path(t) / "x"
            skill_dir.mkdir()
            md = skill_dir / "SKILL.md"
            md.write_text("# just a heading, no frontmatter\n")
            self.assertIsNone(check_skill(md))

    def test_check_root_collects_only_violations(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            _write(d, "good", "name: good\ndescription: d\ntier: producer\ngates:\n  - x")
            _write(d, "bad", "name: bad\ndescription: d\ntier: producer")
            _write(d, "analyzer", "name: an\ndescription: d\ntier: analyzer")
            violations = check_root(d)
            self.assertEqual(len(violations), 1)
            self.assertIn("bad", violations[0])

    def test_repo_itself_conforms(self):
        """The live repo must pass — every producer here declares its gates."""
        repo_root = Path(__file__).resolve().parent.parent
        self.assertEqual(check_root(repo_root), [])


if __name__ == "__main__":
    unittest.main()
