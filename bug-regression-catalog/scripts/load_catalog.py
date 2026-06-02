#!/usr/bin/env python3
"""Single loader for catalog.yaml. Every consumer (validator, chaos
runners, hook reminder) goes through here so the catalog schema is
enforced in exactly one place."""
from __future__ import annotations

import sys
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog.yaml"

REQUIRED_FIELDS = (
    "id", "title", "date", "surface", "source_files",
    "user_visible_symptom", "observable_signal",
)


def _import_yaml():
    try:
        import yaml  # noqa
        return yaml
    except ImportError:
        sys.stderr.write(
            "bug-regression-catalog: PyYAML required.\n"
            "Install with: python3 -m pip install pyyaml\n"
        )
        sys.exit(2)


def load() -> list[dict]:
    yaml = _import_yaml()
    if not CATALOG_PATH.exists():
        return []
    data = yaml.safe_load(CATALOG_PATH.read_text()) or {}
    bugs = data.get("bugs", [])
    for bug in bugs:
        missing = [f for f in REQUIRED_FIELDS if f not in bug]
        if missing:
            raise ValueError(
                f"catalog entry {bug.get('id', '<no-id>')} missing fields: {missing}"
            )
    # The id is the single key — for cross-refs, dedup, and the "removing an entry
    # requires a note" rule. A duplicate id is duplication-drift (two bugs claiming
    # one key); fail loud here so every consumer is protected, not just one test.
    seen: dict[str, int] = {}
    for bug in bugs:
        seen[bug["id"]] = seen.get(bug["id"], 0) + 1
    dups = sorted(i for i, n in seen.items() if n > 1)
    if dups:
        raise ValueError(f"catalog has duplicate id(s) — each must be unique: {dups}")
    return bugs


def _globs_of(entry: dict) -> list[str]:
    """Path globs that scope a lint to specific file(s). Accepts `globs` (str or
    list) or the single-path `path` dialect; [] means unscoped (broad)."""
    g = entry.get("globs")
    if isinstance(g, str):
        return [g]
    if isinstance(g, list):
        return [str(x) for x in g]
    p = entry.get("path")
    return [str(p)] if isinstance(p, str) else []


def _intent(entry: dict) -> str:
    """forbidden (pattern present = bug) vs required (pattern absent = bug).
    Explicit `presence` wins; else inferred from the `NO_` naming convention."""
    return entry.get("presence") or (
        "forbidden" if str(entry.get("rule", "")).startswith("NO_") else "required"
    )


# Project membership is DERIVED from a lint's own paths (its `globs`, else the
# bug's `source_files`) so a project-scoped checker (e.g. Klik's
# /production-rules-checker) loads ONLY its project's lints and an EVE/Owl lint
# can never apply to a Klik file. Single source of truth = the paths the lint
# already references — no separate `project:` field to drift.
_PROJECT_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("eve", ("/opt/eve", "eve-db", "shadow_runner", "evolution/", "auto_execute",
             "intraday_risk", "midsession_reweight")),
    ("owl-backend", ("owl-backend",)),
    ("owl", ("Owlspace_re", "owl-agent", "apps/owlspace", "packages/owl", "/stoat/",
             "/Owl/", "Owl/Sources", "Owl-Info")),
    ("klik", ("Klik_one", "Klik_newandroid", "klik_esp32", "klik_", "/opt/Klik",
              "KK_", "klik-", "klikone", "kk-execution", "liquid/samples/composeApp",
              "AndroidKmp", "deploy/")),
]


def project_of(paths) -> str:
    """Derive a lint's owning project from its paths; 'unknown' if no marker hits."""
    blob = " ".join(str(p) for p in (paths or []))
    for proj, markers in _PROJECT_MARKERS:
        if any(m in blob for m in markers):
            return proj
    return "unknown"


def _lint_project(globs, source_files) -> str:
    """A lint's project: prefer its (specific) globs; fall back to the bug's
    source_files only when the glob carries no marker (e.g. a bare `**/file.c`)."""
    proj = project_of(globs)
    return proj if proj != "unknown" else project_of(source_files)


def lint_patterns(projects=None) -> list[tuple[str, str, str, list[str], list[str], list[str]]]:
    """Yield (rule, pattern, message, file_types, exclude_files, globs) for every
    FORBIDDEN-PATTERN lint — one whose pattern appearing in scope IS the
    violation. `globs`, when set, narrows the lint to specific files (a pattern
    forbidden only in one file); otherwise file_types/exclude_files apply broadly.

    `projects` (a set) filters to lints owned by those projects, derived per-lint
    from its globs / the bug's source_files; None = all. This is what keeps a
    project-specific checker from loading another project's lints.

    REQUIRED / presence guards (pattern must be PRESENT — absence is the bug) are
    NOT returned here; loading them as forbidden would flag the *healthy* code.
    See `required_guards()`. Intent = explicit `presence` else inferred from `NO_`.

    Robust by contract: `lint` may be absent, a single mapping, or a list of
    mappings; one malformed entry must NEVER abort the load (the original bug — a
    dict-shaped lint crashed `entry["rule"]` and silently disabled the catalog)."""
    out: list[tuple[str, str, str, list[str], list[str], list[str]]] = []
    not_forbidden: set[str] = set()
    dropped_unknown: set[str] = set()
    for bug in load():
        lint = bug.get("lint")
        if not lint:
            continue
        for entry in (lint if isinstance(lint, list) else [lint]):
            if not (isinstance(entry, dict) and all(k in entry for k in ("rule", "pattern", "message"))):
                not_forbidden.add(str(bug.get("id", "<no-id>")))  # presence-guard dialect / malformed
                continue
            if _intent(entry) != "forbidden":
                not_forbidden.add(str(bug.get("id", "<no-id>")))  # required/presence guard
                continue
            globs = _globs_of(entry)
            if projects is not None:
                proj = _lint_project(globs, bug.get("source_files"))
                if proj not in projects:
                    if proj == "unknown":
                        dropped_unknown.add(str(bug.get("id", "<no-id>")))
                    continue
            file_types = entry.get("file_types") or ([] if globs else [".py"])
            out.append((
                entry["rule"], entry["pattern"], entry["message"],
                file_types, entry.get("exclude_files", []), globs,
            ))
    if not_forbidden:
        n = len(not_forbidden)
        sys.stderr.write(
            f"bug-regression-catalog: {n} entr{'y' if n == 1 else 'ies'} are "
            f"required/presence guards — enforced via required_guards(), not the "
            f"forbidden-pattern path.\n"
        )
    if dropped_unknown:
        sys.stderr.write(
            f"bug-regression-catalog: {len(dropped_unknown)} forbidden lint(s) have "
            f"an UNKNOWN project (no path marker matched) and were NOT loaded under "
            f"the project filter — add a marker in _PROJECT_MARKERS: "
            f"{', '.join(sorted(dropped_unknown))}\n"
        )
    return out


def required_guards(projects=None) -> list[tuple[str, str, str, list[str]]]:
    """Yield (rule, pattern, message, globs) for every REQUIRED presence guard:
    the pattern MUST be present in the target file(s); its ABSENCE is the bug.
    ONLY entries with an explicit `presence: required` AND a `globs`/`path` target
    are returned — we never *infer* a presence guard, because mis-classifying a
    forbidden lint as required would silently stop enforcing it. `projects` filters
    to lints owned by those projects (derived from the globs); None = all."""
    out: list[tuple[str, str, str, list[str]]] = []
    for bug in load():
        lint = bug.get("lint")
        if not lint:
            continue
        for entry in (lint if isinstance(lint, list) else [lint]):
            if not isinstance(entry, dict) or entry.get("presence") != "required":
                continue
            rule = entry.get("rule")
            pattern = entry.get("pattern")
            globs = _globs_of(entry)
            if not (rule and pattern and globs):
                continue
            if projects is not None and _lint_project(globs, bug.get("source_files")) not in projects:
                continue
            out.append((str(rule), str(pattern), str(entry.get("message") or entry.get("description") or ""), globs))
    return out


def chaos_runners() -> list[tuple[str, str, str]]:
    """Yield (bug_id, runner_path, description) for each catalog entry
    whose `chaos.runner` is set. Consumed by run_chaos_phase.sh."""
    out = []
    base = Path(__file__).resolve().parent
    for bug in load():
        chaos = bug.get("chaos") or {}
        runner = chaos.get("runner")
        if not runner:
            continue
        runner_path = base / runner
        out.append((bug["id"], str(runner_path), chaos.get("description", "")))
    return out


if __name__ == "__main__":
    # CLI for the hook: prints a Markdown summary of all bugs so the
    # SessionEnd hook can echo it back to Claude as a reminder of what
    # patterns are already covered (avoid duplicates).
    bugs = load()
    print(f"# Bug regression catalog — {len(bugs)} entries\n")
    for b in bugs:
        print(f"- **{b['id']}** ({b['date']}, {b['surface']}): {b['title']}")
