# Sector-map improvement plan — close the gap to "everything a maintainer must know per working directory"

Date: 2026-06-10 · Status: proposed · Scope: GLOBAL (all projects, all languages). Klik artifacts
(KK_auth, Feishu docs) are **references only**; every improvement below ships as generic mechanism +
per-project data, never as Klik logic in the engine.

## Inputs investigated

1. **Current engine** — `sector_map/extract.py` (one builder, tree-sitter multi-language, 7-dimension
   output), `cli.py` (brief/blast-radius/consumers-tests/coverage/uncovered), `server.py` (SSE live
   dashboard), `profiles/klik.json`. Vendored copy in `Owlspace_re/apps/owlspace/resources/sector_map`
   (Map tab, `map-server-manager.ts`).
2. **KK_auth reference** (`gcp:/opt/Klik/KK_auth`) — per-module `CLAUDE.md` is a hand-curated "sector
   card": one-line purpose · Components (file→responsibility) · DB Models · Flow · API Endpoints ·
   Config (env vars, "required, NO fallback") · Dependencies (internal/external) · Anti-Patterns
   (forbidden/required) · Read pointers. Plus `DDD_DESIGN.md` (bounded contexts inside one module) and
   `tests/{identity,integration,profile,compliance,import_code}` mirroring contexts.
3. **The 8 things a maintainer must know per working dir** (the user's purpose list): 目录结构 ·
   依赖链 · 局部约束 · 全局约束(incl. 部署) · 局部数据 schema · 修改历史 · 三类测试覆盖 · 目标和动机.
4. **ddd-crew/context-mapping + ContextMapper DSL** — 9 relationship patterns (OHS, ACL, Conformist,
   Shared Kernel, Partnership, Customer/Supplier, Published Language, Separate Ways, BBOM) + 3 team
   relationships (mutually-dependent, upstream/downstream, free); "small maps for explicit questions".
5. **Klik Feishu policies** — 开发项目约定 (DDD layering with KK_auth as reference impl, config
   precedence, migrations+schema_columns.yaml same-commit, ports.md registry), 测试规范 (the 2×3
   unit/integration/e2e × frontend/backend matrix, hermetic-vs-live, error-code assertions), 分层架构
   (infra/app/deploy-orchestration separation, repo map).
6. **/no-new-bugs** (`references/sector-map.md` — the seven dimensions + test-maturity matrix overlay)
   and **/production-rules-checker** (generic engine + `rules/<project>.yaml` data).

## Gap analysis (current map vs the 8 must-knows)

| # | Must-know | Today | Gap |
|---|---|---|---|
| 1 | 目录结构 | ✅ files/LOC/symbols per sector | minor: no responsibilities text |
| 2 | 依赖链 | ✅ import edges + call graph (scip>graphify>heuristic), cycles, blast radius | edges carry no *semantics* (see #G5) |
| 3 | 局部约束 | ⚠ regex `behavior` patterns in profile | default profile uses owlspace_map's own GUARD_SIGNS → noise on other repos (G1); no forbidden/required structure (G2) |
| 4 | 全局约束/部署 | ⚠ static `boundaries_global` strings; `deploy_symlinks` checks `~/.claude/skills/<sector>` (owlspace_map-only) | no generic deploy/config/ports/env extraction (G3); production-rules-checker rules not surfaced on the map (G4) |
| 5 | 局部数据 schema | ❌ none | PRD FR-M5 unimplemented: no DTO/dataclass/SQL-DDL extraction (G6) |
| 6 | 修改历史 | ⚠ `git log -5` + catalog incidents (path match `app/<root>/` = Klik-shaped) | no why/ADR/doc links; incident matching generic-path needed (G7) |
| 7 | 三类测试覆盖 | ⚠ unit-test counting + Cobertura line coverage | no unit/integration/e2e **classification**, no test-maturity matrix (sector-map.md describes it; nothing renders it), no CI pass/fail ingest (G8) |
| 8 | 目标和动机 | ❌ none | no purpose field anywhere (G9) |

**Engine hygiene gaps:**
- **G10 — SSOT drift**: the vendored `Owlspace_re/resources/sector_map` has `bound_profile()`
  (`.sectormap.json` discovery) that the source repo `owlspace_map/sector_map` **does not** — the
  upstream is behind its own vendored copy. Violates the repo's own anti-regression rule #8/#9.
- **G11 — `is_kt` two-mode special-casing** in `build_graph` (deps_used heuristics hardcoded to
  PyYAML/kotlinx; `crossproject` hardcoded to sector ids `bug-regression-catalog` /
  `production-rules-checker`). Not language-agnostic, it's "py-or-kt".
- **G12** — Klik's profile lives at `owlspace_map/sector_map/profiles/klik.json`, not as a committed
  `.sectormap.json` in the Klik repos; contradicts the working-dir-binding decision already shipped
  in the app.

## The plan

### P0 — Re-converge the SSOT (½ day)
- Port `bound_profile()` / `profile_source` (and any other vendored-only deltas) **back into
  `owlspace_map/sector_map`**; make the repo the single source and the app's `resources/sector_map`
  a build-time sync (script that copies + checks `diff` in CI, or a git subtree). Add a guard:
  CI fails when vendored copy ≠ repo copy.
- Move `profiles/klik.json` content into the Klik frontend repo as committed `.sectormap.json`
  (PR there); keep `profiles/` only as examples.

### P1 — Profile schema v2: the "sector card" (1–2 days)
Generalize the KK_auth CLAUDE.md shape into the profile/`.sectormap.json` schema — all optional,
all data, zero engine logic:
```jsonc
{
  "purpose": "one-liner for the repo",            // must-know #8
  "sectors": [{
    "id": "auth", "root": "src/auth",
    "purpose": "JWT tokens, password reset, OAuth",   // #8 per sector
    "constraints": {                                   // #3 structured, not regex-only
      "forbidden": ["default user IDs (fallback auth)", ...],
      "required":  ["all endpoints verify authentication", ...]
    },
    "schema_sources": ["src/auth/models.py", "db/migrations/*.sql"],  // #5 hint
    "docs": ["src/auth/CLAUDE.md", "docs/adr/0007-auth.md"],          // #6 why-links
    "config": ["JWT_SECRET_KEY", "SMTP_*"]                            // #4
  }],
  "edges": [                                          // G5: context-map semantics
    {"src": "auth", "dst": "common", "pattern": "shared-kernel"},
    {"src": "client", "dst": "auth", "pattern": "customer-supplier", "direction": "U/D"}
  ],
  "deploy": {"ports_registry": "deploy/ports.md", "unit_glob": "deploy/services/*.env"},
  "tests": {                                          // #7 classification rules
    "unit": {"markers": ["unit"], "dirs": ["tests/unit"]},
    "integration": {"markers": ["integration"], "dirs": ["KK_inttest"]},
    "e2e": {"dirs": ["e2e", "tests/e2e"], "name_contains": [".e2e."]}
  }
}
```
- **Auto-ingest per-sector docs**: when a sector root contains `CLAUDE.md`/`README.md`, take the
  first paragraph as `purpose` and surface the doc link under Intent&History — works for any repo
  that follows the KK_auth convention, no config needed.

### P2 — New language-agnostic collectors (2–4 days)
- **Schema (#5, G6)**: tree-sitter already parses every language — extract *data-shape* defs
  (`class_definition` with only fields / `data class` / `interface`+`type_alias` / `struct` /
  `@dataclass`/`@Serializable` decorated) into a `schema` list per sector; plus a SQL-DDL scanner
  for `*.sql` (`CREATE TABLE` → table+columns). Render as the sector's "局部数据 schema" panel.
- **Context/deploy (#4, G3)**: generic extractors — env-var reads per language
  (`os.environ[...]`/`process.env.X`/`System.getenv`), config files under the sector, port literals
  + URL literals → `TALKS_TO` boundary entries; parse a `ports_registry`/`unit_glob` when the
  profile names them. Replace `deploy_symlinks` + `deps_used` heuristics with this (kill the
  `is_kt` branches, G11).
- **Test classification (#7, G8)**: classify each detected test file into unit/integration/e2e via
  profile rules with sane defaults (path contains `e2e`/`integration`; pytest markers; everything
  else unit). Output per sector: the **maturity matrix** — rows = sides (profile-declared parallel
  impls, default 1) × columns = unit/int/e2e, cells = count + ✅/⚠️/❌. CI pass/fail ingest: read an
  optional junit-xml path like coverage.xml is read today.
- **Incidents (#6, G7)**: generalize catalog matching from `app/<root>/` to "any source_file path
  under the sector root" so non-Klik projects' incidents anchor correctly.

### P3 — Context-map semantics on the graph (1–2 days)
- Type the edges: keep parsed `depends_on` weights, overlay profile-declared DDD patterns (the
  ddd-crew nine); auto-derive **upstream/downstream** from import direction and **mutually-dependent**
  from existing cycle detection; flag cycles as **Big-Ball-of-Mud risk** in the brief.
- `sectormap contextmap` CLI: emit the typed map; optional **CML export** (ContextMapper format) so
  teams can use Context Mapper's generators — export only, never a dependency.
- Dashboard + brief honor "small maps for explicit questions": filter the map by question
  (`--question deps|contracts|tests`).

### P4 — Surface parity (1 day)
- `brief` gains `purpose`, `constraints` (forbidden/required), `schema`, `test_matrix` keys; the
  Owlspace Map tab SectorDetail renders them (it renders dimensions generically, so mostly engine
  JSON + small UI additions).
- Wire **production-rules-checker** (G4): when `rules/<project>.yaml` exists for the repo, list the
  rule ids/titles that path-match each sector under Behavior — the gate becomes visible on the map,
  as the PRD always intended (Gates feed Map).

### P5 — De-self defaults (½ day)
- `default_profile` must stop shipping owlspace_map's `GUARD_SIGNS` as universal "behavior" (G1):
  default `behavior: []`; keep GUARD_SIGNS only in this repo's own `.sectormap.json`.
- Remove hardcoded sector-id checks (`bug-regression-catalog`, `production-rules-checker`) from
  `build_graph`; express them via this repo's own profile.

### Ordering & verification
P0 → P1 → P2 (schema first, tests second, context third) → P4 → P3 → P5 can interleave.
Every phase: failing test first (`test_extract.py` fixtures for a fake polyglot repo), chaos check
in `bug-regression-catalog/scripts/chaos/` for each new collector ("schema extractor finds the
CREATE TABLE", "default profile emits no GUARD_SIGNS noise"), and the existing CI gate green.
