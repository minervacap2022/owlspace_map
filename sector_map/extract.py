#!/usr/bin/env python3
"""Sector-map extractor — turns a repo into the seven-dimension graph the PRD
describes (docs/no-new-bugs-system.md). Real data only: filesystem, git, the
Python/Kotlin parsers, the bug catalog, and live deploy symlinks. No mock values.

Two modes, one shape:
- no profile  → sectors = top-level dirs, Python parsing (used for owlspace_map).
- a profile   → sectors = configured architecture layers, multi-language parsing
                (e.g. profiles/klik.json maps the KMP/Kotlin Klik frontend).

`build_graph(repo, profile)` returns the dict; both modes emit identical keys so
the CLI and dashboard are language-agnostic.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", "node_modules", "build", "dist"}
TEXT_SUFFIX = {".py", ".md", ".yaml", ".yml", ".sh", ".txt", ".json", ".html", ".kt"}
GUARD_SIGNS = [
    (r"duplicate id", "id-uniqueness guard (raises on a duplicate catalog id)"),
    (r"CATALOG_LOAD_FAILED", "fail-loud: a malformed catalog can't report green"),
    (r"missing fields", "required-fields guard on every catalog entry"),
    (r"presence:\s*forbidden|presence:\s*required", "explicit forbidden/required lint intent"),
    (r"_lint_project|project_of", "per-lint project isolation (no cross-project bleed)"),
    (r"token_hex|collision-free", "collision-free random id minting"),
    (r"assertRegex|assertEqual|assertGreater", "committed unit-test assertions"),
    (r"globs and not any\(matches_glob", "path-scoped lint matching"),
]
KT_SYM = re.compile(r"^(?:public |private |internal |open |abstract |sealed |data |)*"
                    r"(fun|class|object|interface|enum class)\s+([A-Za-z_]\w*)", re.M)
KT_IMP = re.compile(r"^import\s+([\w.]+)", re.M)


# ── low-level helpers ─────────────────────────────────────────────────────────
def _walk(d: Path) -> list[Path]:
    if not d.exists():
        return []
    return [p for p in d.rglob("*")
            if p.is_file() and not any(part in SKIP_DIRS for part in p.parts)
            and p.suffix != ".pyc" and p.name != ".DS_Store"]


def _loc(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _is_test_file(f: Path) -> bool:
    """Language-aware test-file detection (so non-Python/Kotlin repos aren't
    falsely reported uncovered)."""
    n, p = f.name, str(f)
    if f.suffix == ".py":
        return n.startswith("test_") or n.endswith("_test.py")
    if f.suffix == ".go":
        return n.endswith("_test.go")
    if f.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
        return ".test." in n or ".spec." in n or "__tests__" in p
    if f.suffix == ".java":
        return n.endswith("Test.java") or "/test/" in p
    if f.suffix == ".rb":
        return n.endswith("_test.rb") or n.endswith("_spec.rb")
    return False


def _count_tests(f: Path) -> int:
    try:
        txt = f.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    if f.suffix == ".py":
        try:
            return sum(1 for n in ast.walk(ast.parse(txt))
                       if isinstance(n, ast.FunctionDef) and n.name.startswith("test"))
        except SyntaxError:
            return 0
    if f.suffix == ".go":
        return len(re.findall(r"func\s+Test\w+", txt))
    if f.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
        return len(re.findall(r"\b(?:it|test)\s*\(", txt))
    if f.suffix == ".java":
        return len(re.findall(r"@Test", txt))
    if f.suffix == ".rs":
        return len(re.findall(r"#\[test\]", txt))
    return 1


# ── universal parsing via tree-sitter (all languages, one dependency) ─────────
# suffix → (grammar, {top-level definition node types})
LANGS = {
    ".py": ("python", {"function_definition", "class_definition"}),
    ".kt": ("kotlin", {"class_declaration", "function_declaration", "object_declaration", "interface_declaration"}),
    ".kts": ("kotlin", {"class_declaration", "function_declaration", "object_declaration"}),
    ".java": ("java", {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}),
    ".go": ("go", {"function_declaration", "method_declaration", "type_declaration"}),
    ".ts": ("typescript", {"function_declaration", "class_declaration", "interface_declaration", "enum_declaration", "type_alias_declaration"}),
    ".tsx": ("tsx", {"function_declaration", "class_declaration", "interface_declaration", "enum_declaration"}),
    ".js": ("javascript", {"function_declaration", "class_declaration"}),
    ".jsx": ("javascript", {"function_declaration", "class_declaration"}),
    ".mjs": ("javascript", {"function_declaration", "class_declaration"}),
    ".rs": ("rust", {"function_item", "struct_item", "enum_item", "trait_item", "mod_item"}),
    ".rb": ("ruby", {"method", "class", "module"}),
    ".c": ("c", {"function_definition", "struct_specifier"}),
    ".h": ("c", {"function_definition", "struct_specifier"}),
    ".cc": ("cpp", {"function_definition", "class_specifier", "struct_specifier"}),
    ".cpp": ("cpp", {"function_definition", "class_specifier", "struct_specifier"}),
    ".hpp": ("cpp", {"function_definition", "class_specifier", "struct_specifier"}),
    ".swift": ("swift", {"function_declaration", "class_declaration", "protocol_declaration", "struct_declaration"}),
    ".php": ("php", {"function_definition", "class_declaration", "interface_declaration"}),
}
_IMPORT_TYPES = {"import_statement", "import_from_statement", "import_declaration",
                 "import_header", "import_spec", "use_declaration", "preproc_include"}
_parsers: dict = {}


def _get_parser(lang: str):
    if lang not in _parsers:
        try:
            from tree_sitter_language_pack import get_parser
            _parsers[lang] = get_parser(lang)
        except Exception:
            _parsers[lang] = None
    return _parsers[lang]


_tree_cache: dict = {}  # path -> (mtime, (grammar, root_node, def_types))


def _tree(path: Path):
    """(grammar, root_node, def_types) or None. Cached by path+mtime so a file is
    parsed once per build (symbols/imports/calls share it) AND skipped across builds
    when unchanged — this is what keeps the live server cheap on large repos."""
    spec = LANGS.get(path.suffix)
    if not spec:
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _tree_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    parser = _get_parser(spec[0])
    if parser is None:
        return None
    try:
        result = (spec[0], parser.parse(path.read_bytes()).root_node, spec[1])
    except OSError:
        return None
    _tree_cache[str(path)] = (mtime, result)
    return result


def _node_name(n):
    f = n.child_by_field_name("name")
    if f:
        return f.text.decode("utf-8", "ignore")
    for c in n.children:
        if c.type in ("type_spec", "type_alias", "type_alias_declaration"):
            inner = _node_name(c)
            if inner:
                return inner
        if "identifier" in c.type:
            return c.text.decode("utf-8", "ignore")
    return None


def _symbols(path: Path) -> list[str]:
    """Top-level definition names in ANY language (via tree-sitter)."""
    t = _tree(path)
    if not t:
        return _fallback_symbols(path)
    _, root, defs = t
    out = []
    for c in root.children:
        node = c
        if c.type in ("export_statement", "decorated_definition"):  # unwrap ts export / py decorator
            node = next((g for g in c.children if g.type in defs), None)
        if node and node.type in defs:
            nm = _node_name(node)
            if nm:
                out.append(nm)
    return out


def _import_path(node, lang: str):
    txt = node.text.decode("utf-8", "ignore")
    if lang == "kotlin":
        m = txt.replace("import", "", 1).strip()
        return m.split(" as ")[0].strip().rstrip(".*").rstrip(".")
    if lang == "python":
        if node.type == "import_from_statement":
            mn = node.child_by_field_name("module_name")
            return mn.text.decode("utf-8", "ignore") if mn else None
        for c in node.children:
            if c.type == "dotted_name":
                return c.text.decode("utf-8", "ignore")
        return None
    if lang == "go":
        return txt.strip().split()[-1].strip('"`') if node.type == "import_spec" else None
    if lang in ("typescript", "tsx", "javascript"):
        src = node.child_by_field_name("source")
        return src.text.decode("utf-8", "ignore").strip("'\"") if src else None
    if lang == "rust":
        return txt.replace("use", "", 1).strip().rstrip(";").strip()
    if lang == "java":
        return txt.replace("import", "", 1).replace("static", "", 1).strip().rstrip(";").strip()
    if lang == "swift":
        return txt.replace("import", "", 1).strip()
    if lang in ("c", "cpp"):  # #include "foo.h" / <foo.h>
        m = re.search(r'[<"]([^>"]+)[>"]', txt)
        return m.group(1) if m else None
    return None


def _imports(path: Path) -> list[str]:
    """Import paths in ANY language (via tree-sitter)."""
    t = _tree(path)
    if not t:
        return _fallback_imports(path)
    lang, root, _ = t
    out = []
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type in _IMPORT_TYPES:
            p = _import_path(n, lang)
            if p:
                out.append(p)
        stack += list(n.children)
    return out


def _fallback_symbols(path: Path) -> list[str]:  # only if a grammar is missing
    if path.suffix == ".py":
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            return [n.name for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and not n.name.startswith("_")]
        except (SyntaxError, OSError):
            return []
    if path.suffix in (".kt", ".kts") and path.exists():
        return [m.group(2) for m in KT_SYM.finditer(path.read_text(errors="ignore"))]
    return []


def _fallback_imports(path: Path) -> list[str]:
    if path.suffix == ".py":
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            mods = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods += [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
            return mods
        except (SyntaxError, OSError):
            return []
    if path.suffix in (".kt", ".kts") and path.exists():
        return KT_IMP.findall(path.read_text(errors="ignore"))
    return []


# ── drill-down: per-symbol definitions + a name-resolved call graph ───────────
_FUNC_TYPES = {"function_definition", "function_declaration", "function_item",
               "method_declaration", "method", "method_definition", "constructor_declaration"}
_CALL_TYPES = {"call", "call_expression", "method_invocation", "macro_invocation"}


def _callee(node) -> str | None:
    """The bare name of the function/method being called (last identifier segment).
    Name-level (no overload/type resolution) — labeled heuristic, ADR's ~80% tier."""
    fn = node.child_by_field_name("function") or node.child_by_field_name("name")
    if fn is None and node.children:
        fn = node.children[0]
    if fn is None:
        return None
    seg = re.split(r"[.:?!]+", fn.text.decode("utf-8", "ignore").strip())[-1]
    seg = seg.split("(")[0].split("<")[0].split("{")[0].strip()
    return seg if seg.isidentifier() else None


def _defs_calls(path: Path):
    """(defs, calls): defs=[(name, kind, line)] (top-level + nested);
    calls=[(enclosing_function_name | None, callee_name)] within each body."""
    t = _tree(path)
    if not t:
        return [], []
    _, root, def_types = t
    types = def_types | _FUNC_TYPES
    defs, calls = [], []

    def walk(n, enclosing):
        cur = enclosing
        if n.type in types:
            nm = _node_name(n)
            if nm:
                defs.append((nm, n.type, n.start_point[0] + 1))
                if n.type in _FUNC_TYPES:
                    cur = nm
        if n.type in _CALL_TYPES:
            cn = _callee(n)
            if cn:
                calls.append((enclosing, cn))
        for c in n.children:
            walk(c, cur)

    walk(root, None)
    return defs, calls


_extract_cache: dict = {}  # path -> (mtime, {symbols, imports, defs, calls})


def _extract_file(path: Path) -> dict:
    """All per-file extraction (symbols, imports, defs, calls) in ONE pass, cached
    by mtime. A build walks each file once (not 3×), and an unchanged file is
    skipped entirely on the next build — this is the real incremental win."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {"symbols": [], "imports": [], "defs": [], "calls": []}
    cached = _extract_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    defs, calls = _defs_calls(path)
    data = {"symbols": _symbols(path), "imports": _imports(path), "defs": defs, "calls": calls}
    _extract_cache[str(path)] = (mtime, data)
    return data


def _symbol_graph(raw: dict, repo: Path):
    """Build symbol nodes + a name-resolved call graph from the gathered code.
    Resolution prefers same-file → same-sector → global (capped); heuristic by
    construction (no type/overload resolution), so it's labeled, not implied exact."""
    syms: dict[str, dict] = {}
    name_index: dict[str, list[str]] = {}
    file_defs: dict[tuple, list[str]] = {}
    calls_raw = []
    for sid, r in raw.items():
        for f in r["code"]:
            rel = str(f.relative_to(repo))
            ex = _extract_file(f)
            defs, calls = ex["defs"], ex["calls"]
            for nm, kind, line in defs:
                symid = f"{sid}::{rel}::{nm}:{line}"
                syms[symid] = {"id": symid, "name": nm, "kind": kind, "sector": sid,
                               "file": rel, "line": line, "out": set(), "inc": 0}
                name_index.setdefault(nm, []).append(symid)
                file_defs.setdefault((sid, rel), []).append(symid)
            for enc, callee in calls:
                calls_raw.append((sid, rel, enc, callee))

    call_edges = []
    for sid, rel, enc, callee in calls_raw:
        caller = next((cid for cid in file_defs.get((sid, rel), []) if syms[cid]["name"] == enc), None)
        targets = name_index.get(callee, [])
        if not targets:
            continue
        same_file = [t for t in targets if syms[t]["file"] == rel and t != caller]
        same_sec = [t for t in targets if syms[t]["sector"] == sid and t != caller]
        chosen = (same_file or same_sec or [t for t in targets if t != caller])[:3]
        for tgt in chosen:
            call_edges.append({"src": caller, "dst": tgt, "callee": callee})
            syms[tgt]["inc"] += 1
            if caller:
                syms[caller]["out"].add(tgt)

    sector_calls: dict[tuple, int] = {}
    for e in call_edges:
        src_sec = syms[e["src"]]["sector"] if e["src"] else None
        dst_sec = syms[e["dst"]]["sector"]
        if src_sec and src_sec != dst_sec:
            sector_calls[(src_sec, dst_sec)] = sector_calls.get((src_sec, dst_sec), 0) + 1
    for s in syms.values():
        s["out"] = sorted(s["out"])
    return syms, call_edges, sector_calls


def _git(root: Path, args: list[str]) -> str:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _blob(files: list[Path], suffixes: set[str]) -> str:
    out = []
    for f in files:
        if f.suffix in suffixes:
            out.append(f.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(out)


def _behavior(blob: str, patterns) -> list[str]:
    return [desc for pat, desc in patterns if re.search(pat, blob)]


def _catalog_entries(project: str | None) -> list[tuple[str, str, list]]:
    """(id, title, source_files) for catalog entries (optionally one project),
    read raw so a momentarily-broken catalog never blocks the map."""
    cat = DEFAULT_REPO / "bug-regression-catalog" / "catalog.yaml"
    if not cat.exists():
        return []
    try:
        import yaml
        sys.path.insert(0, str(DEFAULT_REPO / "bug-regression-catalog" / "scripts"))
        from load_catalog import project_of  # type: ignore
        data = yaml.safe_load(cat.read_text()) or {}
        out = []
        for b in data.get("bugs", []):
            if not isinstance(b, dict):
                continue
            if project and project_of(b.get("source_files")) != project:
                continue
            out.append((b.get("id"), b.get("title", ""), b.get("source_files") or []))
        return out
    except Exception:
        return []


def _coverage(repo: Path, report_rel: str | None) -> dict:
    """Real per-line coverage from a Cobertura XML report (coverage.py --xml,
    Kover, gcovr, jacoco→cobertura all emit it). {repo-relative-file: {line: hits}}."""
    if not report_rel:
        return {}
    p = repo / report_rel
    if not p.exists():
        return {}
    try:  # defusedxml hardens against XXE / billion-laughs (a report can be untrusted)
        from defusedxml.ElementTree import parse as _xml_parse
    except ImportError:
        from xml.etree.ElementTree import parse as _xml_parse
    try:
        tree = _xml_parse(str(p))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for cls in tree.iter("class"):
        fn = (cls.get("filename") or "").replace("\\", "/")
        if not fn:
            continue
        lines = out.setdefault(fn, {})
        for ln in cls.iter("line"):
            try:
                lines[int(ln.get("number"))] = int(ln.get("hits"))
            except (TypeError, ValueError):
                pass
    return out


def _cov_for(cov: dict, rel: str) -> dict:
    """Line→hits for a repo-relative file, tolerating report roots (suffix match)."""
    if rel in cov:
        return cov[rel]
    for k, v in cov.items():
        if k.endswith("/" + rel) or rel.endswith("/" + k):
            return v
    return {}


def _deploy_symlinks(sector: str, repo: Path) -> list[str]:
    out = []
    for c in (Path.home() / ".claude" / "skills" / sector, Path.home() / ".git-hooks" / sector):
        try:
            if c.is_symlink() and Path(c.resolve()) == (repo / sector).resolve():
                out.append(str(c).replace(str(Path.home()), "~"))
        except OSError:
            pass
    return out


# ── default profile (owlspace_map: top-level dirs, Python) ────────────────────
def default_profile(repo: Path) -> dict:
    sectors = [{"id": p.name, "root": p.name}
               for p in sorted(repo.iterdir())
               if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".")]
    return {"label": repo.name, "lang": "py", "git_root": ".", "src_base": "",
            "test_base": "", "import_prefix": "", "resolve": "py_stem",
            "behavior": GUARD_SIGNS, "catalog_project": None, "sectors": sectors,
            "boundaries_global": [], "boundaries_by_sector": {}, "deploy_symlinks": True,
            "scip_index": "index.scip" if (repo / "index.scip").exists() else None, "scip_root": "."}


# ── the one builder ───────────────────────────────────────────────────────────
def build_graph(repo: Path | str | None = None, profile: dict | None = None) -> dict:
    repo = Path(repo) if repo else DEFAULT_REPO
    prof = profile or default_profile(repo)
    lang = prof.get("lang", "py")
    src_base = repo / prof["src_base"] if prof.get("src_base") else repo
    test_base = repo / prof["test_base"] if prof.get("test_base") else None
    git_root = repo / prof.get("git_root", ".")
    src_rel = Path(prof["src_base"]).relative_to(prof["git_root"]) if prof.get("src_base") else Path(".")
    prefix = prof.get("import_prefix", "")
    is_kt = lang == "kt"

    resolve_mode = prof.get("resolve", "py_stem")        # 'py_stem' | 'kt_pkg' (package prefix)
    prefix_norm = prefix.replace(".", "/").replace("::", "/")

    # gather per sector — UNIVERSAL tree-sitter parsing (any language by suffix)
    raw: dict[str, dict] = {}
    for s in prof["sectors"]:
        d = src_base / s["root"]
        files = _walk(d)
        code = [f for f in files if f.suffix in LANGS]
        symbols, imps, fimps = [], [], []
        for f in code:
            ex = _extract_file(f)
            symbols += ex["symbols"]
            fis = ex["imports"]
            imps += fis
            fimps += [(str(f.relative_to(repo)), imp) for imp in fis]
        # tests (conventions are language-specific → profile-driven)
        tfiles, tcount = [], 0
        if is_kt and test_base:
            td = test_base / s["root"]
            tks = [f for f in _walk(td) if f.suffix == ".kt"]
            tfiles = [str(f.relative_to(repo)) for f in tks]
            tcount = sum(len(re.findall(r"@Test", f.read_text(encoding="utf-8", errors="ignore"))) for f in tks)
        else:
            tks = [f for f in files if _is_test_file(f)]
            tfiles = [str(f.relative_to(repo)) for f in tks]
            tcount = sum(_count_tests(t) for t in tks)
        raw[s["id"]] = dict(files=files, code=code, symbols=symbols, imps=imps, fimps=fimps,
                            loc=sum(_loc(f) for f in files), tfiles=tfiles, tcount=tcount, dir=d)

    # drill-down: per-symbol nodes + the call graph. A SCIP index (scip-python /
    # scip-kotlin / scip-typescript) gives TYPE-PRECISE calls (globally-unique
    # symbols, type-checker-resolved); without one we fall back to the name-level
    # heuristic. Either way the output shape is identical — labeled honestly.
    scip_path = (repo / prof["scip_index"]) if prof.get("scip_index") else None
    if scip_path and scip_path.exists():
        import scip_ingest
        _f2s = {str(f.relative_to(repo)): sid for sid, r in raw.items() for f in r["code"]}

        def _fsec(rel):
            if rel in _f2s:
                return _f2s[rel]
            for k, v in _f2s.items():
                if k.endswith("/" + rel) or rel.endswith("/" + k):
                    return v
            return None
        syms, call_edges, sector_calls = scip_ingest.precise_call_graph(
            scip_path, repo, prof.get("scip_root", "."), _fsec)
        call_resolution = "scip (type-precise)"
    else:
        syms, call_edges, sector_calls = _symbol_graph(raw, repo)
        call_resolution = "heuristic (name-level)"
    sector_syms: dict[str, list] = {}
    for s in syms.values():
        sector_syms.setdefault(s["sector"], []).append(s)

    # import → sector resolution (universal): flat-module stem, or package prefix.
    stem_map = {f.stem: sid for sid, r in raw.items() for f in r["code"]}
    roots = sorted(((s["id"], s["root"]) for s in prof["sectors"]), key=lambda x: -len(x[1]))
    # path (minus extension) → sector, for resolving relative imports / local includes
    file_index = {re.sub(r"\.\w+$", "", str(f.relative_to(repo))): sid
                  for sid, r in raw.items() for f in r["code"]}
    _REL_SUFFIX = {".c", ".h", ".cc", ".cpp", ".hpp"}

    def resolve(imp: str, from_file: str | None = None) -> str | None:
        # JS/TS relative imports (./ ../) and C/C++ local includes resolve against
        # the importing file's directory → a target file → its sector.
        if from_file and (imp.startswith(".") or Path(from_file).suffix in _REL_SUFFIX):
            target = os.path.normpath(os.path.join(os.path.dirname(from_file), imp)).replace("\\", "/")
            cand = re.sub(r"\.\w+$", "", target)
            for key in (cand, cand + "/index", target):
                if key in file_index:
                    return file_index[key]
            return None
        p = imp.replace(".", "/").replace("::", "/")
        if resolve_mode == "py_stem":
            return stem_map.get(p.split("/")[0])
        if prefix_norm and p.startswith(prefix_norm):
            p = p[len(prefix_norm):].lstrip("/")
        for sid, root in roots:
            if p == root or p.startswith(root + "/"):
                return sid
        return None

    hard: dict[tuple[str, str], int] = {}
    for sid, r in raw.items():
        for frel, imp in r["fimps"]:
            b = resolve(imp, frel)
            if b and b != sid:
                hard[(sid, b)] = hard.get((sid, b), 0) + 1

    edges = [{"src": a, "dst": b, "weight": w, "kind": "depends_on"} for (a, b), w in hard.items()]
    if resolve_mode == "py_stem":  # prose references only meaningful for the flat-module doc repo
        blobs = {sid: _blob(r["files"], TEXT_SUFFIX) for sid, r in raw.items()}
        for a in raw:
            for b in raw:
                if a != b and (a, b) not in hard and re.search(re.escape(b), blobs[a]):
                    edges.append({"src": a, "dst": b, "weight": len(re.findall(re.escape(b), blobs[a])),
                                  "kind": "references"})

    def direct_consumers(sid: str) -> list[str]:
        # DIRECT reverse-deps = who breaks first if this changes. Direct (not
        # transitive) on purpose: real layered code has dependency cycles, and a
        # transitive walk over a cycle reports "everything", which is useless.
        return sorted({a for (a, b) in hard if b == sid})

    def cycles_with(sid: str) -> list[str]:
        # sectors this one mutually depends on (a→b AND b→a) — a real
        # clean-architecture violation the map should flag, not hide.
        deps = {b for (a, b) in hard if a == sid}
        return sorted(d for d in deps if (d, sid) in hard)

    incidents = _catalog_entries(prof.get("catalog_project")) if prof.get("catalog_project") else []
    remote = _git(git_root, ["remote", "get-url", "origin"])
    catalog_projects: dict = {}
    if not is_kt:
        from_cat = _catalog_entries(None)
        sys.path.insert(0, str(DEFAULT_REPO / "bug-regression-catalog" / "scripts"))
        try:
            from load_catalog import project_of  # type: ignore
            catalog_projects = dict(sorted(Counter(project_of(s) for _, _, s in from_cat).items(),
                                           key=lambda kv: -kv[1]))
        except Exception:
            catalog_projects = {}

    cov = _coverage(repo, prof.get("coverage_report", "coverage.xml"))  # real line coverage if present

    sectors_meta = []
    for s in prof["sectors"]:
        sid, r = s["id"], raw[s["id"]]
        blob = _blob(r["code"], set(LANGS))
        blast = direct_consumers(sid)
        cyc = cycles_with(sid)
        deps = sorted({b for (a, b) in hard if a == sid})
        rel = str(r["dir"].relative_to(repo)) if r["dir"].exists() else f"{prof.get('src_base','')}/{s['root']}"
        gitpath = str(src_rel / s["root"])
        recent = _git(git_root, ["log", "--oneline", "-5", "--", gitpath]).splitlines()
        total_commits = len(_git(git_root, ["log", "--oneline", "--", gitpath]).splitlines())

        # Behavior
        invariants = _behavior(blob, prof["behavior"])

        # Context
        deploy = _deploy_symlinks(sid, repo) if prof.get("deploy_symlinks") else []
        deps_used = []
        if is_kt:
            if "@Serializable" in blob:
                deps_used.append("kotlinx.serialization")
            if "Environment" in blob or "ApiConfig" in blob:
                deps_used.append("Environment config")
            for plat in ("iosMain", "androidMain"):
                if (repo / prof["src_base"].replace("commonMain", plat) / s["root"]).exists():
                    deps_used.append(f"{plat} actuals")
        else:
            if "import yaml" in blob or "safe_load" in blob:
                deps_used.append("PyYAML")
            if (r["dir"] / ".gitignore").exists():
                deps_used.append(".gitignore")

        # Boundaries
        boundaries_ext = ([f"git remote → {remote}"] if remote else []) + deploy
        boundaries_ext += prof.get("boundaries_by_sector", {}).get(sid, [])
        boundaries_ext += prof.get("boundaries_global", [])
        crossproject = []
        if not is_kt and sid == "bug-regression-catalog" and catalog_projects:
            crossproject = [f"{k}: {v} incidents" for k, v in catalog_projects.items()]
        if not is_kt and sid == "production-rules-checker":
            rd = r["dir"] / "rules"
            crossproject = [f"rules/{p.stem}.yaml" for p in sorted(rd.glob("*.yaml"))] if rd.exists() else []

        # Intent & History: + past incidents from the catalog (KMP mode)
        sector_incidents = [t for (_, t, srcs) in incidents
                            if any(f"app/{s['root']}/" in str(sf) for sf in srcs)]

        # Tests & Coverage: REAL line coverage when a report exists, else test counts.
        lines_total = lines_cov = 0
        cov_pct = None
        precise_uncovered = []
        for f in r["code"]:
            lh = _cov_for(cov, str(f.relative_to(repo)))
            lines_total += len(lh)
            lines_cov += sum(1 for h in lh.values() if h > 0)
        if lines_total:
            cov_pct = round(100 * lines_cov / lines_total)
            for sym in sector_syms.get(sid, []):
                lh = _cov_for(cov, sym["file"])
                if lh and lh.get(sym["line"], 1) == 0:
                    precise_uncovered.append(f"{sym['name']} ({sym['file'].split('/')[-1]}:{sym['line']})")
        covered = (cov_pct is not None and cov_pct > 0) or r["tcount"] > 0
        if cov_pct is not None:
            cov_label = f"{cov_pct}% lines ({lines_cov}/{lines_total}) · {r['tcount']} tests"
            uncovered = precise_uncovered[:14] if cov_pct < 100 else []
        else:
            uncovered = [] if covered else r["symbols"][:14]
            cov_label = (f"{r['tcount']} tests" if r["tcount"] else ("UNCOVERED" if r["code"] else "n/a (no code)"))
        kind = ("code+data" if r["code"] and any(f.suffix in {".yaml", ".yml"} for f in r["files"])
                else "kotlin" if is_kt and r["code"] else "code" if r["code"] else "docs")

        sectors_meta.append({
            "id": sid, "kind": kind, "loc": r["loc"], "file_count": len(r["files"]),
            "dimensions": {
                "structure": {"files": sorted(str(f.relative_to(repo)) for f in r["files"])[:60],
                              "loc": r["loc"], "symbols": sorted(set(r["symbols"]))[:40],
                              "symbol_count": len(sector_syms.get(sid, [])),
                              "hot_symbols": [{"name": x["name"], "file": x["file"], "line": x["line"],
                                               "in": x["inc"], "out": len(x["out"])}
                                              for x in sorted(sector_syms.get(sid, []), key=lambda z: -z["inc"])[:8]],
                              "depends_on": deps},
                "behavior": {"invariants": invariants},
                "context": {"deploy": deploy, "deps": deps_used},
                "boundaries": {"external": boundaries_ext, "cross_project": crossproject},
                "intent_history": {"total_commits": total_commits, "recent": recent,
                                   "past_incidents": sector_incidents},
                "change_safety": {"blast_radius": blast, "blast_count": len(blast),
                                  "cycles": cyc,
                                  "called_by_sectors": sorted({a for (a, b) in sector_calls if b == sid}),
                                  "observability": ("unit tests + guards" if covered
                                                    else "guards only" if invariants else "none")},
                "tests_coverage": {"test_files": r["tfiles"], "test_count": r["tcount"],
                                   "covered": covered, "coverage_label": cov_label,
                                   "coverage_pct": cov_pct, "uncovered_surface": uncovered},
            },
        })

    # symbol nodes + call edges (drill-down). `out` holds resolved callee ids, so
    # the dashboard draws the call graph from these; sector_calls is the aggregate.
    symbols_out = [{"id": x["id"], "name": x["name"], "sector": x["sector"], "file": x["file"],
                    "line": x["line"], "kind": x["kind"], "inc": x["inc"], "out": x["out"]}
                   for x in syms.values()]
    return {"repo": prof.get("label", repo.name), "repo_path": str(repo),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "remote": remote, "sectors": sectors_meta, "edges": edges,
            "symbols": symbols_out, "call_resolution": call_resolution,
            "sector_calls": [{"src": a, "dst": b, "weight": w} for (a, b), w in sector_calls.items()]}


def _from_args():
    repo, profile = None, None
    a = sys.argv
    if "--repo" in a:
        repo = a[a.index("--repo") + 1]
    if "--profile" in a:
        profile = json.loads(Path(a[a.index("--profile") + 1]).read_text())
    return repo, profile


if __name__ == "__main__":
    r, p = _from_args()
    print(json.dumps(build_graph(r, p), indent=2))
