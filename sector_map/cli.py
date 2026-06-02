#!/usr/bin/env python3
"""sectormap CLI — the PRD's keystone queries over the live graph.

The agent runs this via Bash *before* an edit (pull at the freshest moment); the
human runs it in a terminal. Each call re-reads the current repo, so it's never stale.

    sectormap.py list
    sectormap.py brief <sector>
    sectormap.py blast-radius <sector>
    sectormap.py consumers-tests <sector>     # the tests to run before AND after a change
    sectormap.py coverage
    sectormap.py uncovered <sector>
  add --json for machine output.
"""
from __future__ import annotations

import json
import sys

from extract import build_graph


def _find(g, name):
    return next((s for s in g["sectors"] if s["id"] == name), None)


def brief(g, name):
    s = _find(g, name)
    if not s:
        return {"error": f"no sector {name!r}; try: {[x['id'] for x in g['sectors']]}"}
    d = s["dimensions"]
    return {
        "sector": name, "kind": s["kind"], "loc": s["loc"], "files": s["file_count"],
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
    s = _find(g, name)
    if not s:
        return {"error": f"no sector {name!r}"}
    return {"sector": name, "blast_radius": s["dimensions"]["change_safety"]["blast_radius"]}


def consumers_tests(g, name):
    s = _find(g, name)
    if not s:
        return {"error": f"no sector {name!r}"}
    blast = s["dimensions"]["change_safety"]["blast_radius"]
    run = {}
    for c in [name, *blast]:
        cs = _find(g, c)
        run[c] = cs["dimensions"]["tests_coverage"]["test_files"] or ["(no tests — uncovered)"]
    return {"sector": name, "run_before_and_after": run}


def coverage(g, _):
    return {s["id"]: s["dimensions"]["tests_coverage"]["coverage_label"] for s in g["sectors"]}


def uncovered(g, name):
    s = _find(g, name)
    if not s:
        return {"error": f"no sector {name!r}"}
    return {"sector": name, "uncovered_surface": s["dimensions"]["tests_coverage"]["uncovered_surface"]}


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
    from pathlib import Path
    argv = sys.argv[1:]
    as_json = "--json" in argv
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
