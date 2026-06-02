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
    """Projects to load catalog lints for, from `--project X` (repeatable, or
    `--project=X`). None = all projects (backward-compatible default). The Klik
    `/production-rules-checker` passes `--project klik` so EVE/Owl/owl-backend
    lints never load into the Klik gate."""
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


# Files/patterns to always exclude from validation
GLOBAL_EXCLUDES = [
    "validate_production_rules.py",  # This script contains patterns
    "CLAUDE.md",  # Documentation may contain anti-pattern examples
    "full_rules.md",  # Reference doc contains anti-pattern examples
]


# Patterns for each rule category
RULES = {
    # === RULE 14: ERROR CODE & WIRE FORMAT COMPLIANCE ===
    # All error responses must use the KLIK 5-char error code + wire format.
    # Registry: docs/error-codes.md | Base: KLIK 错误码注册表
    "ERROR_CODE_COMPLIANCE": {
        "patterns": [
            # Plain-string HTTPException detail bypasses the wire format entirely
            (
                r'raise\s+HTTPException\s*\(\s*status_code\s*=\s*\d+\s*,\s*detail\s*=\s*["\']',
                'HTTPException with plain string detail — wrap in error object: '
                'JSONResponse(content={"error":{"error_code":"Xxxxx","error_message":"...","user_tip":"...","stack_trace":""}})',
            ),
            # error_code values that don't match <Source><CC><SS> format
            (
                r'"error_code"\s*:\s*"(?![ABC]\d{4})',
                "error_code does not match <Source><CC><SS> 5-char format (e.g. A0101) — register in docs/error-codes.md first",
            ),
            # Ad-hoc shorthand error strings used as error codes
            (
                r'"error"\s*:\s*"[a-z_]{3,}(?:_error|_failed|_invalid)"',
                "ad-hoc error string — use registered 5-char error_code in KLIK wire format instead",
            ),
        ],
        "file_types": [".py"],
        "exclude_files": ["test_", "_test.py", "tests/", "conftest.py", "validate_production_rules.py"],
    },
    # === RULE 15: STACK TRACE DISCIPLINE ===
    # stack_trace must only be populated for B02xx (internal/panic) error codes.
    "STACK_TRACE_DISCIPLINE": {
        "patterns": [
            # stack_trace filled via traceback.format_exc() or sys.exc_info()
            (
                r'"stack_trace"\s*:\s*traceback',
                "stack_trace filled outside B02xx — only B02xx (internal/panic) may populate stack_trace; set \"\" for all other codes",
            ),
            (
                r'"stack_trace"\s*:\s*format_exc',
                "stack_trace filled outside B02xx — only B02xx (internal/panic) may populate stack_trace; set \"\" for all other codes",
            ),
        ],
        "file_types": [".py"],
        "exclude_files": ["test_", "_test.py", "tests/", "conftest.py"],
    },
    # === RULE 14 (Kotlin): ERROR CODE & WIRE FORMAT COMPLIANCE ===
    "KT_ERROR_CODE_COMPLIANCE": {
        "patterns": [
            # Any hardcoded non-5-char error code string in Kotlin responses
            (
                r'"error_code"\s*:\s*"(?![ABC]\d{4})',
                "error_code does not match <Source><CC><SS> 5-char format — register in docs/error-codes.md first",
            ),
        ],
        "file_types": [".kt"],
        "exclude_files": ["test/", "Test.kt", "androidTest/"],
    },
    # === EXISTING RULES (Python) ===
    "NO_FALLBACKS": {
        "patterns": [
            (r'os\.getenv\s*\(\s*["\'][^"\']+["\']\s*,', "os.getenv with default value - use os.environ[] to fail explicitly"),
            (r'os\.environ\.get\s*\(\s*["\'][^"\']+["\']\s*,', "os.environ.get with default value - use os.environ[] to fail explicitly"),
            (r"except\s*:\s*\n\s*pass", "silent exception swallowing - handle or re-raise"),
            (r"_fallback\s*=", "fallback variable - fail explicitly instead"),
            (r"_default\s*=", "default variable - fail explicitly instead"),
            (r"_graceful", "graceful degradation - fail explicitly instead"),
        ],
        "file_types": [".py"],
    },
    "NO_HARDCODED_PATHS": {
        "patterns": [
            (r'["\']/root/', "hardcoded /root path - use env vars or config"),
            (r'["\']/home/\w+', "hardcoded /home path - use env vars or config"),
            (r'["\']localhost["\']', "hardcoded localhost - use config"),
            (r'(?<!_LOOPBACK_HOST = )["\']127\.0\.0\.1["\'](?!.*# noqa)', "hardcoded 127.0.0.1 - use config"),
        ],
        "file_types": [".py", ".sh", ".bash", ".yaml", ".yml"],
    },
    "NO_MOCK_DATA": {
        "patterns": [
            (r"mock_data\s*=", "mock data in production code"),
            (r"fake_\w+\s*=", "fake data in production code"),
            (r"dummy_\w+\s*=", "dummy data in production code"),
            (r"placeholder\s*=", "placeholder in production code"),
            (r"sample_data\s*=", "sample data in production code"),
        ],
        "file_types": [".py"],
        "exclude_files": ["test_", "_test.py", "tests/", "conftest.py"],
    },
    "NO_BACKWARD_COMPAT": {
        "patterns": [
            (r"legacy_\w+", "legacy code - delete or modernize"),
            (r"_deprecated", "deprecated code - delete completely"),
            (r"backward_compat", "backward compatibility code - delete old code"),
            (r"backwards_compat", "backward compatibility code - delete old code"),
            (r"#\s*removed", "removed marker - delete the code"),
            (r"#\s*old version", "old version marker - delete"),
        ],
        "file_types": [".py"],
        "exclude_files": ["migrations/", "alembic/"],
    },

    # === KOTLIN RULES ===
    # Rule: NO_COMPAT_PATCHES - 不允许兼容性或补丁性方案
    "NO_COMPAT_PATCHES": {
        "patterns": [
            (r"//\s*TODO.*compat", "compatibility TODO - implement properly, no compat patches"),
            (r"//\s*HACK", "HACK comment - implement properly, no patches"),
            (r"//\s*FIXME.*workaround", "workaround FIXME - implement the real fix"),
            (r"//\s*temp(orary)?\s*(fix|patch|workaround|hack)", "temporary fix - implement the real solution"),
            (r"@Suppress\s*\(\s*\"DEPRECATION\"\s*\)", "@Suppress(DEPRECATION) - migrate to the new API"),
            (r"@Deprecated", "@Deprecated code in production - delete and use replacement"),
            (r"backward[sS]?[cC]ompat", "backward compatibility code - delete old code"),
            (r"legacy[A-Z]\w+", "legacy-prefixed identifier - delete or modernize"),
        ],
        "file_types": [".kt"],
        "exclude_files": ["test/", "Test.kt", "androidTest/"],
    },

    # Rule: NO_OVERENGINEERING - 不允许过度设计，保持最短路径实现
    "NO_OVERENGINEERING": {
        "patterns": [
            (r"interface\s+\w+Strategy", "Strategy interface - use direct implementation unless multiple strategies exist now"),
            (r"abstract\s+class\s+\w+Factory", "abstract Factory - use direct constructor unless multiple factories exist now"),
            (r"object\s+\w+Registry\s*\{", "Registry pattern - use direct references unless dynamic registration is needed now"),
            (r"class\s+\w+Builder\s*[({]", "Builder pattern - use constructor with defaults unless 5+ optional params exist now"),
            (r"//\s*TODO.*future", "future TODO - do not design for hypothetical requirements"),
            (r"//\s*TODO.*later", "deferred TODO - implement now or delete"),
            (r"//\s*TODO.*eventually", "deferred TODO - implement now or delete"),
            (r"(?<![A-Za-z])FeatureFlag(?!s?Dto)(?![A-Za-z])", "FeatureFlag in production - remove flag and use the active code path"),
        ],
        "file_types": [".kt"],
        "exclude_files": ["test/", "Test.kt"],
    },

    # Rule: NO_UNSOLICITED_FALLBACKS - 不允许自行给出需求以外的兜底和降级方案
    "NO_UNSOLICITED_FALLBACKS": {
        "patterns": [
            (r"catch\s*\(\s*_\s*:\s*Exception\s*\)\s*\{?\s*\}", "empty catch block - handle error explicitly or remove try/catch"),
            (r'catch\s*\(\s*_\s*:\s*\w*[eE]xception\s*\)\s*\{\s*\}', "empty catch block - handle error explicitly or remove try/catch"),
            (r"\.getOrDefault\s*\(", "getOrDefault - fail explicitly, do not silently substitute"),
            (r"\.getOrElse\s*\{[^}]*emptyList\s*\(\s*\)", "getOrElse{emptyList()} - propagate the error, do not hide failures"),
            (r"\.getOrElse\s*\{[^}]*emptyMap\s*\(\s*\)", "getOrElse{emptyMap()} - propagate the error, do not hide failures"),
            (r"\.getOrElse\s*\{[^}]*null\s*\}", "getOrElse{null} - propagate the error, do not hide failures"),
            (r'\.getOrElse\s*\{[^}]*""[^}]*\}', "getOrElse{\"\"} - propagate the error, do not hide failures"),
            (r'runCatching\s*\{', "runCatching - use try/catch with explicit error handling, do not silently absorb"),
            (r"//\s*[Ff]allback", "fallback comment - fail explicitly, do not degrade"),
            (r"//\s*[Gg]raceful", "graceful degradation comment - fail explicitly, do not degrade"),
            (r"//\s*[Bb]est.?effort", "best-effort comment - this is production, not best-effort"),
            (r'message\s*=\s*".*[Mm]ock\s*data', "mock data in error message - use accurate error messages"),
            (r"//\s*[Ii]n production", "\"in production\" comment - this IS production, implement it"),
            (r"//\s*[Ff]or now", "\"for now\" comment - implement the real solution"),
            (r"//\s*[Pp]laceholder", "placeholder comment - implement the real logic"),
        ],
        "file_types": [".kt"],
        "exclude_files": ["test/", "Test.kt"],
    },

    # Rule: NO_BROKEN_CHAIN - 全链路逻辑必须正确（检测断链信号）
    "NO_BROKEN_CHAIN": {
        "patterns": [
            (r"TODO\s*\(\s*\)", "empty TODO() call - will crash at runtime, implement the logic"),
            (r"throw\s+NotImplementedError", "NotImplementedError - implement the logic before committing"),
            (r"throw\s+UnsupportedOperationException\s*\(\s*\)", "UnsupportedOperationException - implement the logic"),
            (r"return\s+null\s*//", "return null with comment - suspicious incomplete implementation"),
            (r"suspend fun \w+\([^)]*\)\s*\{\s*\}", "empty suspend function body - implement the logic"),
            (r"fun \w+\([^)]*\)\s*\{\s*\}", "empty function body - implement the logic"),
            (r"override fun \w+\([^)]*\)\s*\{\s*\}", "empty override body - implement the logic"),
        ],
        "file_types": [".kt"],
        "exclude_files": ["test/", "Test.kt"],
    },

    # Regression rules from ~/.claude/skills/bug-regression-catalog/catalog.yaml
    # are merged in below (see _load_catalog_rules at the bottom of this file).
    # Do NOT add inline regression rules here — every regression rule must
    # live in the catalog so it has a paired chaos runner and observability
    # signal. The catalog is the single source of truth.

    # Rule: Kotlin hardcoded values (extend existing Python rule to Kotlin)
    "KT_NO_HARDCODED": {
        "patterns": [
            (r'private\s+const\s+val\s+\w*(API_KEY|SECRET|TOKEN|PASSWORD)\w*\s*=\s*"[^"]{8,}"', "hardcoded secret in const - move to Environment config"),
            (r'private\s+const\s+val\s+\w*ENDPOINT\w*\s*=\s*"https?://', "hardcoded URL in const - move to Environment/ApiConfig"),
            (r'"https?://\d+\.\d+\.\d+\.\d+', "hardcoded IP in URL - use Environment config"),
            (r'const\s+val\s+IS_DEBUG\w*\s*=\s*true', "debug flag in production - remove or use build config"),
        ],
        "file_types": [".kt"],
        "exclude_files": ["test/", "Test.kt", "Environment.kt", "ApiConfig.kt"],
    },

    # === RULE 1: NO ENV FILES — env must be pre-loaded by systemd/shell, never from .env ===
    "NO_ENV_FILES": {
        "patterns": [
            (r"\bload_dotenv\s*\(", "load_dotenv() - env must be pre-loaded by systemd/shell, not loaded from a .env file"),
            (r"\bfrom\s+dotenv\s+import\b", "dotenv import - env must be pre-loaded by systemd/shell, not from a .env file"),
            (r"^\s*import\s+dotenv\b", "import dotenv - env must be pre-loaded by systemd/shell, not from a .env file"),
            (r"source\s+\S*\.env\b", "source .env - env must be pre-loaded by systemd/shell, not sourced from a file"),
        ],
        "file_types": [".py", ".sh", ".bash"],
        "exclude_files": ["test_", "_test.py", "tests/", "test/"],
    },

    # === RULE 13: NO RAW SCHEMA DDL IN APP — schema goes through Alembic in klik-infra ===
    "NO_SCHEMA_DDL_IN_APP": {
        "patterns": [
            (r"(?i)\bCREATE\s+TABLE\b", "raw CREATE TABLE in app code - DB schema changes go through Alembic in klik-infra (direct port 5432), not app code"),
            (r"(?i)\bALTER\s+TABLE\b", "raw ALTER TABLE in app code - DB schema changes go through Alembic in klik-infra (direct port 5432), not app code"),
            (r"(?i)\bDROP\s+TABLE\b", "raw DROP TABLE in app code - DB schema changes go through Alembic in klik-infra, not app code"),
        ],
        "file_types": [".py"],
        "exclude_files": ["alembic/", "migrations/", "migrations-archive/", "klik-infra", "init/", "test_", "_test.py", "tests/", "conftest.py"],
    },
}


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

        for pattern, message in config["patterns"]:
            regex = re.compile(pattern)
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    stripped = line.strip()

                    # For rules that specifically CHECK comments, don't skip
                    comment_check_categories = {
                        "NO_BACKWARD_COMPAT",
                        "NO_COMPAT_PATCHES",
                        "NO_OVERENGINEERING",
                        "NO_UNSOLICITED_FALLBACKS",
                        "NO_BROKEN_CHAIN",
                    }

                    # Skip pure comment lines for non-comment-checking rules
                    if category not in comment_check_categories:
                        if is_comment_line(line, file_ext):
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


# Apply catalog rules at import time so every CLI invocation picks them up.
_load_catalog_rules()


if __name__ == "__main__":
    sys.exit(main())
