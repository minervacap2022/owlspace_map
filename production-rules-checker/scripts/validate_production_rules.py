#!/usr/bin/env python3
"""
Production Rules Validator

Hard validation gate for production code. Blocks commits until all rules pass.

Usage:
    validate_production_rules.py [--staged] [file1.py file2.py ...]

Options:
    --staged    Check only staged files (git diff --cached)
    files       Check specific files (if not provided, checks all uncommitted changes)

Exit codes:
    0 - All checks passed
    1 - Violations found (commit blocked)
    2 - Error running validation
"""

import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _project_filter():
    """Projects to load rules + catalog lints for, from `--project X` (repeatable,
    or `--project=X`). None = no project rules + all catalog lints (backward-
    compatible default). `--project <name>` loads only that project's rules
    (`rules/<name>.yaml`) and its catalog lints, so one project's rule can never
    fire on another project's file."""
    projs = set()
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--project" and i + 1 < len(argv):
            projs.add(argv[i + 1])
        elif a.startswith("--project="):
            projs.add(a.split("=", 1)[1])
    return projs or None


@dataclass
class Violation:
    file: str
    line: int
    category: str
    message: str
    snippet: str


@dataclass
class ValidationResult:
    violations: list[Violation] = field(default_factory=list)
    files_checked: int = 0


# Rules + excludes are DATA, loaded per-project from rules/<project>.yaml at import
# (see _load_project_rules). The engine itself ships ZERO project knowledge.
GLOBAL_EXCLUDES: list[str] = []
RULES: dict = {}


def get_files_to_check(staged: bool, specific_files: list[str]) -> list[str]:
    """Get list of files to validate."""
    if specific_files:
        return [f for f in specific_files if Path(f).exists()]

    cmd = ["git", "diff", "--name-only"]
    if staged:
        cmd.append("--cached")
    else:
        cmd.append("HEAD")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path.cwd())
    if result.returncode != 0:
        return []

    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return [f for f in files if Path(f).exists()]


def is_globally_excluded(filepath: str) -> bool:
    """Check if file is in global exclusion list."""
    for exclude in GLOBAL_EXCLUDES:
        if exclude in filepath:
            return True
    return False


def matches_glob(filepath: str, glob: str) -> bool:
    """Match a repo-relative path against a glob. Handles exact paths, a leading
    `**/` (suffix match), and fnmatch patterns. Separators are normalized."""
    fp = filepath.replace("\\", "/").lstrip("./")
    g = glob.replace("\\", "/")
    if fp == g:
        return True
    if g.startswith("**/"):
        tail = g[3:]
        return fp == tail or fp.endswith("/" + tail) or fnmatch.fnmatch(fp, "*/" + tail)
    return fnmatch.fnmatch(fp, g) or fp.endswith("/" + g)


def should_check_file(filepath: str, rule_config: dict) -> bool:
    """Determine if file should be checked for this rule."""
    path = Path(filepath)

    # Check global exclusions first
    if is_globally_excluded(filepath):
        return False

    # Path-scoped lints (globs): the file MUST match one of the globs.
    globs = rule_config.get("globs")
    if globs and not any(matches_glob(filepath, g) for g in globs):
        return False

    # Check file type (empty/absent = no suffix filter, e.g. a globs-scoped lint)
    if rule_config.get("file_types"):
        if path.suffix not in rule_config["file_types"]:
            return False

    # Check exclusions
    if "exclude_files" in rule_config:
        for exclusion in rule_config["exclude_files"]:
            if exclusion in filepath:
                return False

    return True


def is_comment_line(line: str, file_ext: str) -> bool:
    """Check if a line is a comment."""
    stripped = line.strip()
    if file_ext == ".py":
        return stripped.startswith("#")
    elif file_ext == ".kt":
        return stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*")
    return False


def check_file(filepath: str) -> list[Violation]:
    """Check a single file against all rules."""
    violations = []
    path = Path(filepath)

    if not path.exists():
        return violations

    try:
        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")
    except (OSError, UnicodeDecodeError):
        return violations

    file_ext = path.suffix

    for category, config in RULES.items():
        if not should_check_file(filepath, config):
            continue

        # Rules that intentionally match COMMENT lines (HACK/TODO/fallback markers)
        # set check_comments: true in their data file; all others skip comment lines.
        check_comments = config.get("check_comments", False)
        for pattern, message in config["patterns"]:
            regex = re.compile(pattern)
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    stripped = line.strip()

                    # Skip pure comment lines unless the rule opts into them.
                    if not check_comments and is_comment_line(line, file_ext):
                        continue

                    violations.append(
                        Violation(
                            file=filepath,
                            line=line_num,
                            category=category,
                            message=message,
                            snippet=stripped[:100],
                        )
                    )

    return violations


def format_violations(result: ValidationResult) -> str:
    """Format violations for output."""
    if not result.violations:
        return f"""
=== PRODUCTION RULES VALIDATION ===
Checked {result.files_checked} files

✅ ALL CHECKS PASSED - Ready to commit
"""

    # Group by category
    by_category: dict[str, list[Violation]] = {}
    for v in result.violations:
        if v.category not in by_category:
            by_category[v.category] = []
        by_category[v.category].append(v)

    output = [
        "",
        "=== PRODUCTION RULES VALIDATION ===",
        f"Checked {result.files_checked} files",
        "",
        "❌ VIOLATIONS FOUND:",
        "",
    ]

    for category, violations in sorted(by_category.items()):
        output.append(f"[{category}]")
        for v in violations:
            output.append(f"  {v.file}:{v.line} - {v.message}")
            output.append(f"    > {v.snippet}")
        output.append("")

    files_with_violations = len(set(v.file for v in result.violations))
    output.append(f"TOTAL: {len(result.violations)} violations in {files_with_violations} files")
    output.append("❌ COMMIT BLOCKED - Fix all violations before committing")
    output.append("")

    return "\n".join(output)


def check_required_guards(files: list[str]) -> list[Violation]:
    """Enforce REQUIRED presence guards from the catalog: a pattern that MUST be
    present in a target file — its ABSENCE is the bug. Fires only when the target
    file is in the validated set and the required pattern is missing, so it
    catches a change that drops required code without blocking unrelated commits."""
    try:
        from load_catalog import required_guards  # type: ignore
    except ImportError:
        return []
    try:
        guards = required_guards(_project_filter())
    except Exception as exc:  # noqa: BLE001
        global _CATALOG_LOAD_ERROR
        _CATALOG_LOAD_ERROR = _CATALOG_LOAD_ERROR or str(exc)
        sys.stderr.write(f"bug-regression-catalog required_guards failed: {exc}\n")
        return []

    violations: list[Violation] = []
    for rule, pattern, message, globs in guards:
        try:
            regex = re.compile(pattern)
        except re.error:
            continue
        for filepath in files:
            if is_globally_excluded(filepath):
                continue
            if not any(matches_glob(filepath, g) for g in globs):
                continue
            p = Path(filepath)
            if not p.exists():
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if not regex.search(content):
                violations.append(Violation(
                    file=filepath, line=0, category=rule,
                    message=f"REQUIRED pattern absent — {message}",
                    snippet=f"(this file must contain /{pattern}/)",
                ))
    return violations


def main() -> int:
    """Main entry point."""
    staged = "--staged" in sys.argv
    specific_files = []
    skip_next = False
    for arg in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if arg == "--project":  # consume its value, not treat it as a file
            skip_next = True
            continue
        if arg.startswith("--"):
            continue
        specific_files.append(arg)

    files = get_files_to_check(staged, specific_files)

    if not files:
        print("No files to check.")
        return 0

    result = ValidationResult(files_checked=len(files))

    for filepath in files:
        result.violations.extend(check_file(filepath))
    result.violations.extend(check_required_guards(files))

    # A malformed catalog silently disables every catalog lint — never report
    # success on it. This is the "lying green" failure mode the catalog exists to
    # prevent, so it must apply to the catalog itself.
    if _CATALOG_LOAD_ERROR:
        result.violations.append(Violation(
            file="<bug-regression-catalog>", line=0, category="CATALOG_LOAD_FAILED",
            message=(f"the regression catalog failed to load ({_CATALOG_LOAD_ERROR}) — "
                     f"ALL catalog lints are DISABLED. Refusing to pass on a broken "
                     f"single source of truth; fix catalog.yaml, then re-run."),
            snippet="catalog.yaml is malformed (e.g. duplicate id / missing field)",
        ))

    print(format_violations(result))

    return 1 if result.violations else 0


# Set when the catalog EXISTS but fails to load (malformed: duplicate id, missing
# field, bad YAML). Distinct from "not installed / unimportable" (legitimate
# degradation). A malformed catalog silently disables ALL catalog lints, so we
# refuse to report success on it — main() turns this into a hard failure.
_CATALOG_LOAD_ERROR: "str | None" = None


def _load_project_rules() -> None:
    """Load `rules/<project>.yaml` for each `--project` into RULES + GLOBAL_EXCLUDES.

    The engine ships ZERO project knowledge — a project's rules (patterns,
    file_types, exclude_files, check_comments) and its global excludes are pure
    data here. Rule files live in `rules/` next to this script's parent. No
    `--project` = no project rules load (only catalog regression lints apply)."""
    projects = _project_filter()
    if not projects:
        return
    rules_dir = Path(__file__).resolve().parent.parent / "rules"
    try:
        import yaml  # type: ignore
    except ImportError:
        sys.stderr.write("production-rules-checker: PyYAML required to load project rules\n")
        return
    for proj in sorted(projects):
        rf = rules_dir / f"{proj}.yaml"
        if not rf.exists():
            continue
        data = yaml.safe_load(rf.read_text()) or {}
        for exc in data.get("global_excludes") or []:
            if exc not in GLOBAL_EXCLUDES:
                GLOBAL_EXCLUDES.append(exc)
        for name, cfg in (data.get("rules") or {}).items():
            block = RULES.setdefault(name, {
                "patterns": [],
                "file_types": list(cfg.get("file_types") or []),
                "exclude_files": list(cfg.get("exclude_files") or []),
                "check_comments": bool(cfg.get("check_comments", False)),
            })
            for pat in cfg.get("patterns") or []:
                block["patterns"].append((pat["pattern"], pat["message"]))


def _load_catalog_rules() -> None:
    """Merge regression rules from the unified bug catalog.

    The catalog at ~/.claude/skills/bug-regression-catalog/catalog.yaml is
    the single source of truth — every regression entry there contributes
    its lint patterns to RULES. Inline regression rules in this file are
    forbidden so the chaos runners and the lint rules stay paired.
    """
    catalog_loader = Path.home() / ".claude" / "skills" / "bug-regression-catalog" / "scripts" / "load_catalog.py"
    if not catalog_loader.exists():
        return  # Catalog not installed yet — that's fine, regression rules just won't apply.

    spec_dir = str(catalog_loader.parent)
    if spec_dir not in sys.path:
        sys.path.insert(0, spec_dir)
    try:
        from load_catalog import lint_patterns  # type: ignore
    except ImportError:
        return
    try:
        entries = lint_patterns(_project_filter())
    except Exception as exc:  # noqa: BLE001
        global _CATALOG_LOAD_ERROR
        _CATALOG_LOAD_ERROR = str(exc)
        sys.stderr.write(f"bug-regression-catalog load failed: {exc}\n")
        return

    for rule_name, pattern, message, file_types, exclude_files, globs in entries:
        block = RULES.setdefault(
            rule_name,
            {"patterns": [], "file_types": file_types, "exclude_files": exclude_files, "globs": globs},
        )
        block["patterns"].append((pattern, message))
        # Union file types / exclusions / globs across entries that share a rule name.
        block["file_types"] = sorted(set(block.get("file_types", []) + file_types))
        block["exclude_files"] = sorted(set(block.get("exclude_files", []) + exclude_files))
        block["globs"] = sorted(set(block.get("globs", []) + globs))


# At import: load this run's per-project rules (data), then merge catalog lints.
_load_project_rules()
_load_catalog_rules()


if __name__ == "__main__":
    sys.exit(main())
