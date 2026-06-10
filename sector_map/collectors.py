#!/usr/bin/env python3
"""v2 collectors — the must-know gaps the base extractor doesn't cover
(spec: docs/specs/2026-06-10-map-improvement-plan.md).

Everything here is LANGUAGE-AGNOSTIC mechanism; project specifics arrive as profile
data. Heuristic where labeled (regex over source), never silently precise.

  schema_defs(path)            #5 局部数据 schema — data shapes + SQL DDL
  env_reads(files)             #4 context — env vars the code resolves
  outbound_urls(files)         #4 boundaries — outbound URL literals
  classify_test_file(rel, rules)  #7 — unit / integration / e2e
  test_matrix(test_files, rules)  #7 — the 3-layer maturity matrix
  log_sites(files)             G13 — log-emit surface
  error_codes(code, tests, pattern)  G13 — raised vs. test-asserted codes
  typed_edges(hard, declared)  P3 — relationship-typed dependency edges
  contextmap_findings(hard, declared)  P3 — declared-vs-parsed mismatches
  sector_card(dir)             P1 — purpose/docs auto-ingest from CLAUDE.md/README
"""
from __future__ import annotations

import re
from pathlib import Path

# ── #5 schema extraction ──────────────────────────────────────────────────────
# Heuristic data-shape detection per language: a "schema" is a type whose body is
# (mostly) field declarations, or one carrying a serialization marker.
_PY_CLASS = re.compile(r"^(?:@(?P<deco>\w+)[^\n]*\n)*class\s+(?P<name>\w+)(?:\((?P<base>[^)]*)\))?:", re.M)
_PY_FIELD = re.compile(r"^\s{4}(\w+)\s*:\s*[^\n=]+(?:=.*)?$", re.M)
_KT_DATA = re.compile(r"(?:@(\w+)\s+)*data class\s+(\w+)\s*\(([^)]*)\)", re.S)
_KT_FIELD = re.compile(r"va[lr]\s+(\w+)\s*:")
_TS_IFACE = re.compile(r"(?:export\s+)?(?:interface|type)\s+(\w+)[^{=]*[{=]([^}]*)", re.S)
_TS_FIELD = re.compile(r"^\s*(\w+)\??\s*:", re.M)
_GO_STRUCT = re.compile(r"type\s+(\w+)\s+struct\s*\{([^}]*)\}", re.S)
_GO_FIELD = re.compile(r"^\s*(\w+)\s+\S+", re.M)
_SQL_TABLE = re.compile(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+[\"`]?(\w+)[\"`]?\s*\(([^;]*?)\)\s*;", re.I | re.S)
_SQL_COL = re.compile(r"^\s*[\"`]?(\w+)[\"`]?\s+\w+", re.M)
_SQL_NOISE = {"primary", "foreign", "unique", "constraint", "check", "index", "key"}
_SCHEMA_DECOS = {"dataclass", "serializable"}
_SCHEMA_BASES = {"basemodel", "typeddict", "namedtuple"}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def schema_defs(path: Path) -> list[dict]:
    """Data-shape definitions in one file: [{name, kind, fields}] — labeled heuristic."""
    txt = _read(path)
    if not txt:
        return []
    out = []
    sfx = path.suffix
    if sfx == ".py":
        for m in _PY_CLASS.finditer(txt):
            deco = (m.group("deco") or "").lower()
            base = (m.group("base") or "").lower()
            is_schema = deco in _SCHEMA_DECOS or any(b in base for b in _SCHEMA_BASES)
            # body = the indented block after the class line
            body = txt[m.end():]
            body = body[:re.search(r"^\S", body, re.M).start()] if re.search(r"^\S", body, re.M) else body
            fields = _PY_FIELD.findall(body)
            if is_schema or (fields and not re.search(r"^\s{4}def\s", body, re.M)):
                out.append({"name": m.group("name"), "kind": "py-class", "fields": fields})
    elif sfx in (".kt", ".kts"):
        for m in _KT_DATA.finditer(txt):
            out.append({"name": m.group(2), "kind": "kt-data-class",
                        "fields": _KT_FIELD.findall(m.group(3))})
    elif sfx in (".ts", ".tsx"):
        for m in _TS_IFACE.finditer(txt):
            fields = _TS_FIELD.findall(m.group(2))
            if fields:
                out.append({"name": m.group(1), "kind": "ts-interface", "fields": fields})
    elif sfx == ".go":
        for m in _GO_STRUCT.finditer(txt):
            out.append({"name": m.group(1), "kind": "go-struct",
                        "fields": _GO_FIELD.findall(m.group(2))})
    elif sfx == ".sql":
        for m in _SQL_TABLE.finditer(txt):
            cols = [c for c in _SQL_COL.findall(m.group(2)) if c.lower() not in _SQL_NOISE]
            out.append({"name": m.group(1), "kind": "sql-table", "fields": cols})
    return out


# ── #4 context: env vars + outbound URLs ──────────────────────────────────────
_ENV_PATTERNS = [
    re.compile(r'os\.environ(?:\.get)?[\[(]\s*["\'](\w+)["\']'),
    re.compile(r'os\.getenv\(\s*["\'](\w+)["\']'),
    re.compile(r'process\.env\.(\w+)'),
    re.compile(r'process\.env\[["\'](\w+)["\']\]'),
    re.compile(r'System\.getenv\(\s*["\'](\w+)["\']'),
    re.compile(r'std::env::var\(\s*"(\w+)"'),
    re.compile(r'\bgetenv\(\s*"(\w+)"'),
    re.compile(r'ENV\[["\'](\w+)["\']\]'),
]
_URL = re.compile(r'["\'](https?://[^"\'\s]+)["\']')


def env_reads(files: list[Path]) -> list[str]:
    """Env-var names the code resolves — the sector's config surface (sorted, unique)."""
    seen = set()
    for f in files:
        txt = _read(f)
        for pat in _ENV_PATTERNS:
            seen.update(pat.findall(txt))
    return sorted(seen)


def outbound_urls(files: list[Path]) -> list[str]:
    """Outbound URL literals — TALKS_TO boundary candidates (sorted, unique)."""
    seen = set()
    for f in files:
        seen.update(_URL.findall(_read(f)))
    return sorted(seen)


# ── #7 test classification + maturity matrix ──────────────────────────────────
_DEFAULT_RULES = {
    "e2e": {"dirs": ["e2e", "endtoend", "end-to-end"], "name_contains": [".e2e.", "_e2e"]},
    "integration": {"dirs": ["integration", "inttest", "contract"],
                    "name_contains": ["integration", "contract", "inttest"]},
}
_LAYERS = ("unit", "integration", "e2e")


def classify_test_file(rel: str, rules: dict | None) -> str:
    """unit | integration | e2e for one test file path. Profile rules extend (not
    replace) the defaults; anything unmatched is unit — the honest floor."""
    p = rel.replace("\\", "/").lower()
    parts = set(p.split("/"))
    name = p.rsplit("/", 1)[-1]
    for layer in ("e2e", "integration"):
        for src in (rules or {}), _DEFAULT_RULES:
            r = src.get(layer) or {}
            # dir match is substring-per-component ("KK_inttest" matches "inttest")
            if any(d.lower() in part for d in r.get("dirs", []) for part in parts):
                return layer
            if any(s.lower() in name for s in r.get("name_contains", [])):
                return layer
    return "unit"


def test_matrix(test_files: list[str], rules: dict | None) -> dict:
    """The 3-layer maturity row: {layer: {count, files, mark}}. A zero layer is an
    explicit ❌ — silence rendered as a hole, not omitted (sector-map.md overlay)."""
    out = {layer: {"count": 0, "files": []} for layer in _LAYERS}
    for tf in test_files:
        layer = classify_test_file(tf, rules)
        out[layer]["count"] += 1
        out[layer]["files"].append(tf)
    for layer, cell in out.items():
        cell["mark"] = "✅" if cell["count"] else "❌"  # presence; pass/fail upgrades later
    return out


# ── G13 observability: log-emit surface + error codes ─────────────────────────
_LOG_PATTERNS = [
    re.compile(r"\b(?:log(?:ger)?|logging)\s*\.\s*(?:debug|info|warning|warn|error|exception|critical|fatal|trace)\s*\("),
    re.compile(r"\bconsole\.(?:log|info|warn|error)\s*\("),
    re.compile(r"\b(?:slog|zap|logrus)\.\w+\("),
    re.compile(r"\btracing::(?:debug|info|warn|error)!"),
    re.compile(r"\bos_log\("),
]


def log_sites(files: list[Path], extra_patterns: list[str] | None = None) -> int:
    """Count of log-call sites = the sector's observable emit surface. 0 on a code
    sector means: if this breaks in prod, nothing tells you."""
    pats = _LOG_PATTERNS + [re.compile(p) for p in (extra_patterns or [])]
    n = 0
    for f in files:
        txt = _read(f)
        n += sum(len(p.findall(txt)) for p in pats)
    return n


def error_codes(code_files: list[Path], test_files: list[Path], pattern: str) -> dict:
    """Cross-ref: codes the sector raises vs. codes its tests assert. `unasserted`
    = failure paths with no guard (render like uncovered_surface). `pattern` comes
    from the profile (e.g. Klik's 5-char '\"([ABC]\\d{4})\"') — data, not engine."""
    pat = re.compile(pattern)
    raised, asserted = set(), set()
    for f in code_files:
        raised.update(pat.findall(_read(f)))
    for f in test_files:
        asserted.update(pat.findall(_read(f)))
    return {"raised": sorted(raised), "asserted": sorted(asserted),
            "unasserted": sorted(raised - asserted)}


# ── P3 context-map semantics ──────────────────────────────────────────────────
DDD_PATTERNS = {"open-host-service", "conformist", "anticorruption-layer", "shared-kernel",
                "partnership", "customer-supplier", "published-language", "separate-ways",
                "big-ball-of-mud"}


def typed_edges(hard: dict, declared: list[dict]) -> list[dict]:
    """Parsed dependency pairs + auto-derived team relationship (ddd-crew's three) +
    the profile-declared DDD pattern when present. hard = {(src,dst): weight}."""
    decl = {(e["src"], e["dst"]): e.get("pattern") for e in declared}
    out = []
    for (a, b), w in hard.items():
        rel = "mutually-dependent" if (b, a) in hard else "upstream-downstream"
        e = {"src": a, "dst": b, "weight": w, "relationship": rel}
        if (a, b) in decl:
            e["pattern"] = decl[(a, b)]
        out.append(e)
    return out


def contextmap_findings(hard: dict, declared: list[dict]) -> list[str]:
    """Declared-vs-parsed mismatches — where context-map semantics become a gate.
    Each declared pattern implies a parseable expectation; violations are findings."""
    findings = []
    for e in declared:
        a, b, pat = e["src"], e["dst"], (e.get("pattern") or "").lower()
        observed = (a, b) in hard or (b, a) in hard
        if pat == "separate-ways" and observed:
            findings.append(
                f"{a}↔{b}: declared separate-ways but {hard.get((a, b), 0) + hard.get((b, a), 0)} "
                f"import edge(s) observed — the contexts are NOT separate")
        elif pat and pat != "separate-ways" and not observed:
            findings.append(
                f"{a}→{b}: declared {pat} but never observed in parsed imports — "
                f"stale declaration or an invisible (runtime-only) dependency")
    for (a, b) in hard:
        if (b, a) in hard and a < b:
            findings.append(
                f"{a}↔{b}: mutual dependency (cycle) — Big-Ball-of-Mud risk; "
                f"declare an owner direction or split the shared part out")
    return findings


# ── P1 sector card: purpose/docs ingest ───────────────────────────────────────
_DOC_NAMES = ("CLAUDE.md", "README.md", "CONTEXT.md")


def sector_card(sector_dir: Path) -> dict:
    """{purpose, docs} from the sector's own docs. First paragraph after the title
    of the first present doc = purpose. None when absent — never invented."""
    docs = [sector_dir / n for n in _DOC_NAMES if (sector_dir / n).is_file()]
    purpose = None
    if docs:
        for block in _read(docs[0]).split("\n\n"):
            line = block.strip()
            if line and not line.startswith("#"):
                purpose = line.splitlines()[0].strip()
                break
    return {"purpose": purpose, "docs": [str(d) for d in docs]}
