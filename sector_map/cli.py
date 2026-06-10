#!/usr/bin/env python3
"""sectormap CLI — the PRD's keystone queries over the live graph.

The agent runs this via Bash *before* an edit (pull at the freshest moment); the
human runs it in a terminal. Each call re-reads the current repo, so it's never stale.

    sectormap.py init  [--repo DIR] [--out FILE]   # initiate the map: detect sectors → write a profile
    sectormap.py serve [--repo DIR] [--profile F]  # launch the live dashboard (http://127.0.0.1:8765)
    sectormap.py list
    sectormap.py brief <sector | path/to/File.kt>          # 7-dimension briefing; sector OR a file path
    sectormap.py blast-radius <sector | path>
    sectormap.py consumers-tests <sector | path>   # uncovered consumers first, then tests to run before/after
    sectormap.py coverage
    sectormap.py uncovered <sector | path>
  add --json for machine output.  --repo / --profile select the target repo (default: this one).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from extract import DEFAULT_REPO, build_graph, default_profile


def _find(g, name):
    return next((s for s in g["sectors"] if s["id"] == name), None)


def _resolve_sector(g, name):
    """Accept a sector id OR a file path (what an agent actually holds) → sector id.
    A path matches the sector whose files include it (full relative path or bare name)."""
    if not name:
        return None
    if _find(g, name):
        return name
    q = name.replace("\\", "/").lstrip("./")
    for s in g["sectors"]:
        for f in s["dimensions"]["structure"]["files"]:
            if f == q or f.endswith("/" + q):
                return s["id"]
    return None


def brief(g, name):
    sid = _resolve_sector(g, name)
    s = _find(g, sid)
    if not s:
        return {"error": f"no sector or file {name!r}; sectors: {[x['id'] for x in g['sectors']]}"}
    d = s["dimensions"]
    return {
        "sector": sid, "kind": s["kind"], "loc": s["loc"], "files": s["file_count"],
        "1_structure": {"depends_on": d["structure"]["depends_on"],
                         "symbols": len(d["structure"]["symbols"])},
        "2_behavior": d["behavior"]["invariants"],
        "3_context": d["context"],
        "4_boundaries": d["boundaries"],
        "5_intent_history": d["intent_history"],
        "6_change_safety": d["change_safety"],
        "7_tests_coverage": {k: d["tests_coverage"][k]
                             for k in ("coverage_label", "covered", "test_count", "uncovered_surface")},
    }


def blast_radius(g, name):
    sid = _resolve_sector(g, name)
    s = _find(g, sid)
    if not s:
        return {"error": f"no sector or file {name!r}"}
    return {"sector": sid, "blast_radius": s["dimensions"]["change_safety"]["blast_radius"]}


def consumers_tests(g, name):
    sid = _resolve_sector(g, name)
    s = _find(g, sid)
    if not s:
        return {"error": f"no sector or file {name!r}"}
    blast = s["dimensions"]["change_safety"]["blast_radius"]
    tests, uncovered = {}, []
    for c in [sid, *blast]:
        tf = _find(g, c)["dimensions"]["tests_coverage"]["test_files"]
        tests[c] = tf or []
        if not tf and c != sid:
            uncovered.append(c)                  # a consumer with NO test → silent-break risk
    # the RISK leads; the bulky per-sector test list follows.
    return {"sector": sid, "blast_radius": blast,
            "uncovered_consumers": uncovered,
            "tests_to_run_before_and_after": tests}


def coverage(g, _):
    return {s["id"]: s["dimensions"]["tests_coverage"]["coverage_label"] for s in g["sectors"]}


def uncovered(g, name):
    sid = _resolve_sector(g, name)
    s = _find(g, sid)
    if not s:
        return {"error": f"no sector or file {name!r}"}
    return {"sector": sid, "uncovered_surface": s["dimensions"]["tests_coverage"]["uncovered_surface"]}


def init(argv):
    """Bootstrap the map for any repo: auto-detect top-level dirs as sectors and write
    a starter profile you can then tune. This is how you 'initiate the map' on a new repo."""
    repo = Path(argv[argv.index("--repo") + 1]).resolve() if "--repo" in argv else DEFAULT_REPO
    prof = default_profile(repo)
    # Default home is the working-dir-bound file <repo>/.sectormap.json — committed with
    # the code so the tuned profile travels with every clone (NOT a per-machine cache).
    out = (Path(argv[argv.index("--out") + 1]) if "--out" in argv
           else repo / ".sectormap.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(prof, indent=2))
    return {"initiated": str(repo), "profile": str(out),
            "sectors_detected": [s["id"] for s in prof["sectors"]],
            "next": [f"python3 cli.py list  --repo {repo} --profile {out}",
                     f"python3 server.py    --repo {repo} --profile {out}   # live dashboard :8765"]}


CMDS = {
    "list": lambda g, _: [s["id"] for s in g["sectors"]],
    "brief": brief, "blast-radius": blast_radius, "consumers-tests": consumers_tests,
    "coverage": coverage, "uncovered": uncovered,
}


def _print_human(cmd, result):
    if isinstance(result, dict) and "error" in result:
        print("✗", result["error"]); return
    print(f"\n  ── sectormap {cmd} ──")
    if isinstance(result, list):
        for x in result:
            print(f"   • {x}")
    else:
        for k, v in result.items():
            if isinstance(v, (dict, list)) and v:
                print(f"   {k}:")
                body = v.items() if isinstance(v, dict) else enumerate(v)
                for kk, vv in body:
                    print(f"      {kk if isinstance(v, dict) else '•'} {vv}")
            else:
                print(f"   {k}: {v}")
    print()


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    # actions that don't query an existing graph (init writes config; serve launches the UI)
    if argv and argv[0] == "init":
        result = init(argv)
        print(json.dumps(result, indent=2)) if as_json else _print_human("init", result)
        return
    if argv and argv[0] == "serve":
        import os
        argv.remove("serve")
        server = Path(__file__).resolve().parent / "server.py"
        os.execv(sys.executable, [sys.executable, str(server), *argv])  # passes --repo/--profile/--port
    repo = profile = None
    if "--repo" in argv:
        repo = argv[argv.index("--repo") + 1]
    if "--profile" in argv:
        profile = json.loads(Path(argv[argv.index("--profile") + 1]).read_text())
    # strip flags + their values, leaving positional cmd/sector
    args, skip = [], False
    for a in argv:
        if skip:
            skip = False; continue
        if a in ("--repo", "--profile"):
            skip = True; continue
        if a == "--json":
            continue
        args.append(a)
    if not args or args[0] not in CMDS:
        print(__doc__); sys.exit(0 if not args else 2)
    cmd = args[0]
    name = args[1] if len(args) > 1 else None
    g = build_graph(repo, profile)
    result = CMDS[cmd](g, name)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(cmd, result)


if __name__ == "__main__":
    main()
