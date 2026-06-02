#!/usr/bin/env python3
"""Native graphify integration — use graphify's tree-sitter graph as our structure
+ call backbone.

graphify (MIT, github.com/safishamsi/graphify) emits qualified SYMBOL nodes +
`calls` edges (tree-sitter parse + a second call-graph pass) with EXTRACTED /
INFERRED / AMBIGUOUS confidence — richer and more reliable than the name-level
heuristic. We import it as a LIBRARY (native, not a shell-out) and map its
{nodes, edges} into the same (syms, call_edges, sector_calls) shape the engine
uses everywhere, so the CLI/dashboard are unchanged. Degrades to None if graphify
isn't installed, so it's a true optional provider (like the SCIP path).
"""
from __future__ import annotations

import re
from pathlib import Path

_CODE_EXT = (".py", ".kt", ".kts", ".java", ".go", ".ts", ".tsx", ".js", ".jsx",
             ".rs", ".rb", ".c", ".h", ".cc", ".cpp", ".hpp", ".swift", ".php")


def available() -> bool:
    try:
        import graphify.extract  # noqa
        return True
    except Exception:
        return False


def _is_symbol(label: str) -> bool:
    """A graphify symbol node (function/method/class) — not a file or a docstring."""
    if not label or label.endswith(_CODE_EXT):           # file node
        return False
    if len(label) > 48 or " " in label.strip():          # rationale/docstring node
        return False
    return label.endswith("()") or label[:1].isupper()   # function/method, or a Class


def graphify_graph(code_files: list[Path], repo: Path, file_sector):
    """(syms, call_edges, sector_calls) from graphify, or None if unavailable.
    `file_sector(repo_relative_path)` → sector id or None."""
    try:
        import graphify.extract as gex
    except Exception:
        return None
    g = gex.extract([str(f) for f in code_files]) or {}

    # graphify reports source_file as a BASENAME (drops the dir) → map it back to
    # our repo-relative files; skip a basename that's ambiguous across sectors.
    name_map: dict[str, list] = {}
    for f in code_files:
        try:
            rel = str(f.resolve().relative_to(repo))
        except ValueError:
            rel = str(f)
        sec = file_sector(rel)
        if sec is not None:
            name_map.setdefault(f.name, []).append((rel, sec))

    syms: dict[str, dict] = {}
    gid_to_sym: dict[str, str] = {}
    for n in g.get("nodes", []):
        label = n.get("label", "")
        if not _is_symbol(label):
            continue
        sf = n.get("source_file") or ""
        sec = file_sector(sf)               # multi-dir input → repo-relative source_file
        if sec is not None:
            rel = sf
        else:                               # single-dir input → bare basename
            cands = name_map.get(Path(sf).name)
            if not cands or len(cands) > 1:
                continue
            rel, sec = cands[0]
        loc = n.get("source_location", "") or ""
        line = int(loc[1:]) if loc.startswith("L") and loc[1:].isdigit() else 0
        name = re.sub(r"\(\)$", "", label).strip()
        symid = f"{sec}::{rel}::{name}:{line}"
        syms.setdefault(symid, {"id": symid, "name": name, "kind": "function",
                                "sector": sec, "file": rel, "line": line, "inc": 0, "out": set()})
        gid_to_sym[n["id"]] = symid

    call_edges = []
    for e in g.get("edges", []):
        if e.get("relation") != "calls":
            continue
        s = gid_to_sym.get(e.get("source"))
        d = gid_to_sym.get(e.get("target"))
        if not d or s == d:
            continue
        call_edges.append({"src": s, "dst": d, "callee": syms[d]["name"],
                           "confidence": e.get("confidence", "EXTRACTED")})
        syms[d]["inc"] += 1
        if s:
            syms[s]["out"].add(d)

    sector_calls: dict[tuple, int] = {}
    for e in call_edges:
        ss = syms[e["src"]]["sector"] if e["src"] in syms else None
        ds = syms[e["dst"]]["sector"]
        if ss and ss != ds:
            sector_calls[(ss, ds)] = sector_calls.get((ss, ds), 0) + 1
    for s in syms.values():
        s["out"] = sorted(s["out"])
    return syms, call_edges, sector_calls
