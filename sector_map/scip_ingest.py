#!/usr/bin/env python3
"""Type-precise call graph from a SCIP index (Sourcegraph Code Intelligence
Protocol), produced by scip-python / scip-typescript / scip-kotlin / scip-go etc.

Why this over the name-level heuristic: a SCIP symbol is GLOBALLY UNIQUE (module-
qualified, resolved by the language's type checker), so a call to `helper()`
resolves to the *exact* `helper` — overloads and same-name functions in different
modules are disambiguated. The heuristic can only guess by name.

Dependency-free: a tiny protobuf wire-decoder reads just the SCIP subset we need
(no `protobuf` runtime / `protoc` gencode, so no version coupling with the rest of
the system). Fields (from scip.proto): Index.documents=2; Document{relative_path=1,
occurrences=2}; Occurrence{range=1, symbol=2, symbol_roles=3, enclosing_range=7}.
SymbolRole.Definition = 0x1.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


# ── minimal protobuf wire decoder (varint + length-delimited only) ────────────
def _varint(buf: bytes, i: int):
    result = shift = 0
    while True:
        b = buf[i]; i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7


def _fields(buf: bytes):
    i, n = 0, len(buf)
    while i < n:
        tag, i = _varint(buf, i)
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            val, i = _varint(buf, i); yield fn, wt, val
        elif wt == 2:
            ln, i = _varint(buf, i); yield fn, wt, buf[i:i + ln]; i += ln
        elif wt == 1:
            i += 8
        elif wt == 5:
            i += 4
        else:
            raise ValueError(f"bad wire type {wt}")


def _packed(buf: bytes):
    out, i = [], 0
    while i < len(buf):
        v, i = _varint(buf, i); out.append(v)
    return out


def _occurrence(buf: bytes):
    rng, sym, roles, enc = [], None, 0, []
    for fn, wt, val in _fields(buf):
        if fn == 1 and wt == 2:
            rng = _packed(val)
        elif fn == 2 and wt == 2:
            sym = val.decode("utf-8", "ignore")
        elif fn == 3 and wt == 0:
            roles = val
        elif fn == 7 and wt == 2:
            enc = _packed(val)
    return {"range": rng, "symbol": sym, "roles": roles, "enc": enc}


def _document(buf: bytes):
    rel, occ = None, []
    for fn, wt, val in _fields(buf):
        if fn == 1 and wt == 2:
            rel = val.decode("utf-8", "ignore")
        elif fn == 2 and wt == 2:
            occ.append(_occurrence(val))
    return {"path": rel, "occ": occ}


def decode_scip(data: bytes) -> list[dict]:
    """The SCIP index → [{path, occ:[{range, symbol, roles, enc}]}]."""
    return [_document(val) for fn, wt, val in _fields(data) if fn == 2 and wt == 2]


# ── SCIP → precise call graph in our sector shape ─────────────────────────────
def _name(sym: str) -> str:
    tail = re.split(r"[ /#]", sym.strip())[-1]
    return re.sub(r"[().#]+$", "", tail)


def _is_fn(sym: str) -> bool:
    return sym.endswith("().") or "().)" in sym  # function/method descriptor


def precise_call_graph(index_path: Path, repo: Path, scip_root: str, file_sector):
    """(syms, call_edges, sector_calls) computed from a SCIP index, matching the
    shape of extract._symbol_graph. `file_sector(repo_rel)` → sector id or None.
    `scip_root` is the dir (relative to repo) where the indexer ran."""
    docs = decode_scip(Path(index_path).read_bytes())

    def repo_rel(p):
        if not p:
            return None
        return os.path.normpath(os.path.join(scip_root, p)).replace("\\", "/") if scip_root not in ("", ".") else p

    # function definitions: symbol → (repo_rel, name, def_line, enclosing body span)
    def_loc: dict[str, dict] = {}
    for d in docs:
        rel = repo_rel(d["path"])
        if rel is None:
            continue
        sec = file_sector(rel)
        if sec is None:
            continue
        for o in d["occ"]:
            if (o["roles"] & 1) and o["symbol"] and _is_fn(o["symbol"]) and o["enc"]:
                line = (o["range"] or [o["enc"][0]])[0] + 1
                def_loc[o["symbol"]] = {"file": rel, "sector": sec, "name": _name(o["symbol"]),
                                        "line": line, "enc": o["enc"]}

    syms: dict[str, dict] = {}
    for s, m in def_loc.items():
        sid = f"{m['sector']}::{m['file']}::{m['name']}:{m['line']}"
        syms[sid] = {"id": sid, "name": m["name"], "kind": "function", "sector": m["sector"],
                     "file": m["file"], "line": m["line"], "inc": 0, "out": set(), "_scip": s}
    scip_to_id = {m_s: f"{m['sector']}::{m['file']}::{m['name']}:{m['line']}"
                  for m_s, m in def_loc.items()}

    # references to functions → resolve enclosing caller, link to precise callee
    call_edges = []
    for d in docs:
        rel = repo_rel(d["path"])
        if rel is None or file_sector(rel) is None:
            continue
        local_defs = [m for m in def_loc.values() if m["file"] == rel]
        for o in d["occ"]:
            if (o["roles"] & 1) or not o["symbol"] or not _is_fn(o["symbol"]):
                continue
            callee = scip_to_id.get(o["symbol"])
            if not callee or not o["range"]:
                continue  # external symbol (stdlib/3rd-party) — not an internal edge
            ref_line = o["range"][0] + 1
            caller_m = next((m for m in local_defs
                             if m["enc"] and m["enc"][0] + 1 <= ref_line <= m["enc"][2] + 1), None)
            caller = (f"{caller_m['sector']}::{caller_m['file']}::{caller_m['name']}:{caller_m['line']}"
                      if caller_m else None)
            if caller == callee:
                continue
            call_edges.append({"src": caller, "dst": callee, "callee": syms[callee]["name"]})
            syms[callee]["inc"] += 1
            if caller and caller in syms:
                syms[caller]["out"].add(callee)

    sector_calls: dict[tuple, int] = {}
    for e in call_edges:
        src_sec = syms[e["src"]]["sector"] if e["src"] in syms else None
        dst_sec = syms[e["dst"]]["sector"]
        if src_sec and src_sec != dst_sec:
            sector_calls[(src_sec, dst_sec)] = sector_calls.get((src_sec, dst_sec), 0) + 1
    for s in syms.values():
        s["out"] = sorted(s["out"]); s.pop("_scip", None)
    return syms, call_edges, sector_calls
