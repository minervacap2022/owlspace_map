# ADR-0001 — Real-time seven-dimension "sector map" for Klik

- **Status:** Proposed — research complete + **parked 2026-06-01**; build deferred until prioritized. *(Updated 2026-06-01 to match PRD v1.2: seven dimensions, CLI agent surface, live dashboard.)*
- **Deciders:** Wilson (+ agent).
- **Related:** `/no-new-bugs` skill (the seven dimensions) · PRD `docs/prd/no-new-bugs-system.md` (authoritative requirements) · memory `project_code_graph_sector_map.md` (verified tool research + sources — the detail is there, not duplicated here) · `bug-regression-catalog` · the `klik-deploy-parity` gate.

## Context

To stop re-introducing bugs (the `no-new-bugs` discipline), a developer or agent must, *before* touching a **sector** (a module/service), see that sector's full picture. That picture has **seven dimensions** — only the first is fully parseable from code:

1. **Structure** *(parseable)* — responsibilities, schema, file tree, dependencies.
2. **Behavior** — invariants ("always/never"), real runtime data + edge cases, concurrency/ordering, failure semantics (throws vs. silently-swallowed).
3. **Context** — env/config/secrets resolved + dev→prod differences, deploy state vs. git, resource ownership (ports/files/singletons), infra/routing.
4. **Boundaries** — parallel implementations that must stay in sync (forks, client↔server DTOs, iOS↔Android) + external-system contracts & failure modes.
5. **Intent & History** — the *why*/ADR, past bugs here + why prior fixes failed, non-code constraints (BIPA, COPPA-13, `user_id` isolation, perf SLAs, the production rules), the spec's "done".
6. **Change-safety** — true blast radius (runtime paths + cross-repo consumers + migrations), observability.
7. **Tests & Coverage** — which tests cover this (own + consumers'), coverage % + pass/fail, and the **uncovered surface** a change touches.

Every regression in the 2026-05 push traced to a dimension 2–7 factor being invisible at change time: `encodeDefaults` 403 (Behavior); `subscription_api` bare-env (Context); two-fork drift (Boundaries); re-introduced fixed bugs (Intent/History); the missing feedback loop / untested paths (Change-safety + Tests & Coverage).

Verified research (2026-06-01) found **no off-the-shelf tool delivers all seven for a Kotlin-Multiplatform + Python-FastAPI multi-service repo in real time**: graphify (MIT, structure-only ~60–70%, no schema/test-coverage mapping), GitNexus (best fit but **Noncommercial license blocks commercial use**), Understand-Anything (MIT but **does not parse Kotlin**), CodeQL/SCIP (parse both but CI-build-time, no sector view), GraphReAct (real paper, irrelevant). Detail + sources: see the referenced memory.

## Decision

Build a **thin custom indexer**: a parseable **structural backbone**, with the six non-parseable dimensions **anchored** onto it (linked, not re-derived). Adopt the hard parts; build only the glue.

**Graph model (backbone):**
```
Nodes:  Sector · File · Symbol · Schema · Contract · Test · ExternalSystem · Resource(port/file/singleton)
Edges:  CONTAINS · IMPORTS/CALLS · DEFINES · TESTS · COVERS · DEPENDS_ON · IMPLEMENTS/CONSUMES
        · MIRRORS(cross-repo) · TALKS_TO(external) · OWNS(resource)
```

**Dimension → representation (the part no tool does):**

| Dimension | In the graph as | Fed by |
|---|---|---|
| Structure | the nodes + edges above | tree-sitter / `ast` + file-watch |
| Behavior | invariant attrs + **guard-links** on Schema/Contract/Symbol nodes; trace/fixture links | the catalog, fixtures |
| Context | **live overlay** on Sector nodes (env-resolved? live version? health green/red) + `OWNS`→Resource | the **parity gate** + CI + health probes |
| Boundaries | `MIRRORS` edges that flag when out-of-sync; `TALKS_TO`→ExternalSystem w/ failure-mode attrs | a cross-repo diff job |
| Intent & History | Sector **links to** `CONTEXT.md`/ADR, catalog entries, `git log`, constraint tags | git hooks + the catalog |
| Change-safety | computed: **blast-radius** (`reverse IMPORTS`), `observable_signal` | graph queries |
| Tests & Coverage | `COVERS` edges (test→target) + per-sector coverage % / pass-fail + the **uncovered surface** of a change; a **Tests panel** on the dashboard | coverage reports (Kover / coverage.py) + CI results |

**Tech choices:**
- **Parse:** `tree-sitter-kotlin` (fwcd — CST/imports/`@Serializable`, *not* name resolution) + Python `ast`. For accurate cross-symbol edges, ingest **SCIP** (`scip-kotlin` pinned to the exact Kotlin version + `scip-python`) or CodeQL.
- **Store:** **Neo4j** — *not* Kùzu (archived 2025-10). Maintained, mature Cypher + viz.
- **Serve:** a **CLI** (`sectormap brief / blast-radius / consumers-tests / coverage <sector>`) the agent runs via Bash + the human in a terminal, plus a **live dashboard** (websocket/SSE push) for the human. **MCP is deferred** (optional later wrapper; not v1 — CLI is the decided agent surface, see PRD §4).
- **Real-time:** a background **watcher daemon** (file-watch + commit hook + coverage/CI ingest) re-extracts changed files and upserts within seconds; the parity gate + CI feed the Context overlay and the Tests panel; the dashboard pushes live.
- **View:** **React Flow** (card-per-sector, live) or Cytoscape.js.
- **Backend bonus:** **import-linter** for FastAPI service-layer contracts (fail CI) — turns cross-service-coupling prose-rules into a loud guard.

**Rejected:** GitNexus (Noncommercial license blocks commercial Klik — revisit only if a paid Akon Labs license is bought) · Kùzu (archived, unfit as a foundational dep) · Understand-Anything for the Kotlin half (no parser) · writing the parser/DB/call-resolver from scratch (adopt SCIP/CodeQL/Neo4j) · MCP as the v1 agent surface (CLI is decided).

## Consequences

- **Buys:** all seven dimensions on one surface — especially the **consumers'-tests blast-radius**, **schema from `@Serializable`/Pydantic**, and the **uncovered surface** per sector, which no tool provides; a CLI the agent consults pre-change + a live dashboard for the human.
- **Cost:** structural backbone + CLI ≈ **8–13 focused days**; the **live dashboard adds ~3–5 days** (React Flow + websocket); the **Tests & Coverage dimension adds ~2–3 days** (parse coverage + map tests→targets + CI ingest). The invisible-dimension overlays are mostly **wiring to artifacts that already exist** (parity gate, catalog, `CONTEXT.md`, git, coverage reports).
- **Two-repo caveat:** KMP frontend is local (`Klik_one/`, ~232 Kotlin files in `commonMain`); Python backend is `minervacap2022/Klik` / `ssh gcp:/opt/Klik`. The map must index both.
- **Risks:** `scip-kotlin` supports one Kotlin major per release + has KMP source-set friction (pin it; verify `commonMain`/`iosMain`); tree-sitter-kotlin gives no name resolution (v1 uses import-level + heuristic edges — fine for ~80% of blast-radius); coverage absent where a repo emits none (show "coverage unknown" — honest, itself a signal).
- **SSOT alignment:** the map is the single surface that *couples* parseable structure to the non-parseable knowledge, instead of each living in a silo — consistent with the project's couple-to-single-source-of-truth stance.

## Build plan (staged — for the build session)

1. *(optional, ~30 min)* run **graphify** for an immediate structure-only graph, to validate the UX and de-risk before building.
2. **Structural backbone**, tracer-bullet: one sector end-to-end — Kotlin + Python extractors → Neo4j → **CLI** (`blast_radius`, `consumers_tests`, `coverage`).
3. **Live dashboard** (React Flow + websocket), card-per-sector, with the Context overlay + **Tests panel**.
4. **Anchor the overlays:** Context (parity-gate/CI feed) · Tests & Coverage (coverage reports + CI) · Intent/History (link `CONTEXT.md`/ADR/catalog/git) · Boundaries (`MIRRORS` cross-repo diff) · Behavior (guard-links).
5. **import-linter** for the backend service contracts; the **PreToolUse hook** that runs the CLI before an agent edit.

## References

- PRD `docs/prd/no-new-bugs-system.md` — product spec (the authoritative requirements).
- Memory `project_code_graph_sector_map.md` — verified tool research + all sources.
- Skill `~/.claude/skills/no-new-bugs/SKILL.md` — the seven "know-before-you-code" dimensions.
- Precedent: `andrew-hernandez-paragon/code-graph-context` (ts-morph→Neo4j→MCP `blast_radius`, TS-only — proves the shape works + is agent-consumable).
- Tools: `safishamsi/graphify` · `fwcd/tree-sitter-kotlin` · Neo4j · `seddonym/import-linter` · `sourcegraph/scip-kotlin` + `scip-python`.
