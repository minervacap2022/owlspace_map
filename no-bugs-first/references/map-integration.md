# Making the repo render cleanly on the OwlSpace Map

The OwlSpace Map (explore-pane **Map** tab) renders a repo by running the vendored sector-map
engine at `~/Owlspace_re/apps/owlspace/resources/sector_map/`. A repo appears **cleanly** only
when it ships a committed **`.sectormap.json`** that tells the engine its real sectors, language,
and invariants. Without one, the engine falls back to "top-level dirs, dominant language" — which
renders *something*, but not your intended architecture. **That fallback IS the failure signal.**

## How the engine picks a profile (precedence)

`build_graph(repo)` in `extract.py`:
1. explicit `--profile <file>` arg, else
2. committed **`<repo>/.sectormap.json`** (the bound profile — what you write), else
3. `default_profile` (top-level dirs + dominant language).

A malformed `.sectormap.json` warns to stderr and **silently falls through to #3**. So "it
renders" is not proof; you must confirm it renders YOUR sectors.

## The profile schema (every field the engine reads)

Required: `label`, `lang`, `sectors`. The rest tune precision; omit and they default.

```json
{
  "label": "MyService (backend · bun/TS)",
  "lang": "ts",
  "git_root": ".",
  "src_base": "src",
  "test_base": "test",
  "import_prefix": "",
  "resolve": "kt_pkg",
  "catalog_project": "myservice",
  "deploy_symlinks": false,
  "sectors": [
    {"id": "domain",         "root": "domain"},
    {"id": "application",    "root": "application"},
    {"id": "infrastructure", "root": "infrastructure"},
    {"id": "routers",        "root": "routers"}
  ],
  "behavior": [
    ["process\\.env\\.[A-Z_]+\\s*\\?\\?", "⚠ env fallback default — forbidden (fail-fast, no-fallback)"],
    ["z\\.object|@Serializable|interface ", "typed wire contract (single source of truth)"],
    ["throw new .*Error", "explicit error surface (no silent catch)"]
  ],
  "boundaries_global": ["client↔server DTO contract lives in shared/contracts — one copy only"],
  "boundaries_by_sector": {"infrastructure": ["Postgres :5432 · Redis :6379"]}
}
```

Field notes (verified against `extract.py`):
- **`lang`** — `py | ts | kt | java | go | js | rust | …` (suffix→lang map in `_LANG_BY_SUFFIX`).
  Picks the resolve mode: `py` → `py_stem` (flat-stem matching); everything else → `kt_pkg`
  (package-prefix). Relative imports (TS `./`, C `#include`) resolve regardless.
- **`src_base` / `test_base`** — repo-relative roots; sector `root` is resolved under `src_base`.
  Leave `src_base:""` if sectors are top-level. `test_base` only needed for the kt split-tree
  convention; other langs auto-detect test files by name under the sector.
- **`import_prefix`** — your package prefix (e.g. `io.github.app.` or `@myorg/`) so cross-sector
  dependency edges are precise. Empty is fine for relative-import codebases.
- **`resolve`** — usually leave to the lang default. Override to `kt_pkg` for package-rooted TS.
- **`sectors`** — `[{id, root}]`. **These are your architecture layers/features**, NOT every
  directory. id is the display name (may contain `/` for nesting, e.g. `ui/components`).
  **`root` must be a DIRECTORY** resolved under `src_base` — the engine walks it as a tree.
  A `root` pointing at a single file (`auth.ts`) renders the sector **empty** (loc 0, 0 symbols).
  If your layers are single files in one dir, either set the sector to that dir, or split the
  files into per-layer subdirectories first (the cleaner fix — and what the layered layout gives
  you anyway). Verified gotcha: file-level `root` → empty sector.
- **`behavior`** — `[[regex, description], …]`. Each regex that matches a sector's source renders
  as an **invariant** on dimension #2. **This is where you encode this repo's GUARD_SIGNS** — the
  same invariants your `repo-guards.sh` enforces, surfaced on the map. Prefix forbidden patterns
  with `⚠`.
- **`catalog_project`** — links the repo to its `bug-regression-catalog` project so past bugs
  render on dimension #5 (Intent & History).
- **`boundaries_global` / `boundaries_by_sector`** — free-text strings for dimension #4
  (parallel impls + external systems): the sibling client fork, the DB ports, the native bridges.

## Reference: the klik profile (real, in-repo ground truth)

`~/owlspace_map/sector_map/profiles/klik.json` is the worked example for a KMP/Kotlin frontend —
copy its shape. Its `behavior` array is the model for encoding wire-contract + design-token +
expect/actual invariants. Mirror that density.

## Validate before you commit (mandatory — clean-slate rung 1 for the map)

```bash
ENGINE=~/Owlspace_re/apps/owlspace/resources/sector_map
# 1. profile parses + sectors resolve (NOT the default fallback):
python3 "$ENGINE/cli.py" list --repo <REPO> --json
# 2. each sector's 7-dimension brief renders with real symbols/deps/tests:
python3 "$ENGINE/cli.py" brief <sector> --repo <REPO> --json
```

Acceptance:
- `list` shows **your** sector ids, not your top-level directory names (if they differ).
- `brief` shows non-zero symbols, `depends_on` edges where imports exist, the test panel
  reflecting your real test files, and your `behavior` invariants under dimension #2.
- No `[sectormap] ignoring malformed …` on stderr.

If `list` shows the default top-level dirs instead of your sectors, the profile was rejected or
missing — fix and re-run. Do not call the map step done until `brief` renders the intended shape.

## Why this is part of "no bugs first"

The map is the **tooling arm** of the bugless protocol (see `no-new-bugs/references/sector-map.md`):
it makes the six invisible dimensions queryable for the next agent that touches the repo. A repo
that ships a correct `.sectormap.json` from day one means every future change starts with the
seven-dimension brief already accurate — the blast radius and uncovered surface are visible
*before* the edit, which is exactly how `no-new-bugs` prevents the regression. Setting it up at
design time is cheaper and cleaner than retrofitting it onto a tangled repo later.
