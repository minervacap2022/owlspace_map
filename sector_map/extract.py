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
        return sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


def _py_symbols(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, OSError):
        return []
    return [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not n.name.startswith("_")]


def _py_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, OSError):
        return []
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module.split(".")[0])
    return mods


def _kt_symbols(path: Path) -> list[str]:
    try:
        return [m.group(2) for m in KT_SYM.finditer(path.read_text(encoding="utf-8", errors="ignore"))]
    except OSError:
        return []


def _kt_imports(path: Path) -> list[str]:
    try:
        return KT_IMP.findall(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return []


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
            "boundaries_global": [], "boundaries_by_sector": {}, "deploy_symlinks": True}


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

    sym_fn = _kt_symbols if is_kt else _py_symbols
    imp_fn = _kt_imports if is_kt else _py_imports
    code_suffix = ".kt" if is_kt else ".py"

    # gather per sector
    raw: dict[str, dict] = {}
    for s in prof["sectors"]:
        d = src_base / s["root"]
        files = _walk(d)
        code = [f for f in files if f.suffix == code_suffix]
        symbols, imps = [], []
        for f in code:
            symbols += sym_fn(f)
            imps += imp_fn(f)
        # tests
        tfiles, tcount = [], 0
        if is_kt and test_base:
            td = test_base / s["root"]
            tks = [f for f in _walk(td) if f.suffix == ".kt"]
            tfiles = [str(f.relative_to(repo)) for f in tks]
            tcount = sum(len(re.findall(r"@Test", f.read_text(encoding="utf-8", errors="ignore"))) for f in tks)
        else:
            tks = [f for f in files if f.name.startswith("test_") and f.suffix == ".py"]
            tfiles = [str(f.relative_to(repo)) for f in tks]
            for t in tks:
                tcount += sum(1 for n in ast.walk(ast.parse(t.read_text(errors="ignore")))
                              if isinstance(n, ast.FunctionDef) and n.name.startswith("test")) if t.exists() else 0
        raw[s["id"]] = dict(files=files, code=code, symbols=symbols, imps=imps,
                            loc=sum(_loc(f) for f in files), tfiles=tfiles, tcount=tcount, dir=d)

    # import → sector resolution
    stem_map = {f.stem: sid for sid, r in raw.items() for f in r["code"]}
    roots = sorted(((s["id"], s["root"].replace("/", ".")) for s in prof["sectors"]),
                   key=lambda x: -len(x[1]))

    def resolve(imp: str) -> str | None:
        if is_kt:
            if prefix and imp.startswith(prefix):
                suf = imp[len(prefix):]
                for sid, rd in roots:
                    if suf == rd or suf.startswith(rd + "."):
                        return sid
            return None
        return stem_map.get(imp)

    hard: dict[tuple[str, str], int] = {}
    for sid, r in raw.items():
        for imp in r["imps"]:
            b = resolve(imp)
            if b and b != sid:
                hard[(sid, b)] = hard.get((sid, b), 0) + 1

    edges = [{"src": a, "dst": b, "weight": w, "kind": "depends_on"} for (a, b), w in hard.items()]
    if not is_kt:  # prose references only meaningful for the doc repo
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

    sectors_meta = []
    for s in prof["sectors"]:
        sid, r = s["id"], raw[s["id"]]
        blob = _blob(r["code"], {code_suffix})
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

        covered = r["tcount"] > 0
        uncovered = [] if covered else r["symbols"][:14]
        cov_label = (f"{r['tcount']} tests" if covered
                     else ("UNCOVERED" if r["code"] else "n/a (no code)"))
        kind = ("code+data" if r["code"] and any(f.suffix in {".yaml", ".yml"} for f in r["files"])
                else "kotlin" if is_kt and r["code"] else "code" if r["code"] else "docs")

        sectors_meta.append({
            "id": sid, "kind": kind, "loc": r["loc"], "file_count": len(r["files"]),
            "dimensions": {
                "structure": {"files": sorted(str(f.relative_to(repo)) for f in r["files"])[:60],
                              "loc": r["loc"], "symbols": sorted(set(r["symbols"]))[:40],
                              "depends_on": deps},
                "behavior": {"invariants": invariants},
                "context": {"deploy": deploy, "deps": deps_used},
                "boundaries": {"external": boundaries_ext, "cross_project": crossproject},
                "intent_history": {"total_commits": total_commits, "recent": recent,
                                   "past_incidents": sector_incidents},
                "change_safety": {"blast_radius": blast, "blast_count": len(blast),
                                  "cycles": cyc,
                                  "observability": ("unit tests + guards" if covered
                                                    else "guards only" if invariants else "none")},
                "tests_coverage": {"test_files": r["tfiles"], "test_count": r["tcount"],
                                   "covered": covered, "coverage_label": cov_label,
                                   "uncovered_surface": uncovered},
            },
        })

    return {"repo": prof.get("label", repo.name), "repo_path": str(repo),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "remote": remote, "sectors": sectors_meta, "edges": edges}


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
