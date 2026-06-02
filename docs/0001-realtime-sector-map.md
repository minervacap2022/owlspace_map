# ADR-0001 — Real-time seven-dimension "sector map"

- **Status:** Proposed — research complete + **parked**; build deferred until prioritized. Matches PRD v1.2: seven dimensions, CLI agent surface, live dashboard.
- **Related:** `no-new-bugs` skill (the seven dimensions) · PRD `docs/no-new-bugs-system.md` (authoritative requirements) · code-graph tool research · `bug-regression-catalog` · the deploy-parity gate.

> **Scope note.** Stack-agnostic design. The concrete tech below is the **reference
> instantiation** (a Kotlin-Multiplatform frontend + a Python backend); any project swaps in
> its own grammars, indexers, and coverage sources. Nothing here is project-specific.

## Context

To stop re-introducing bugs (the `no-new-bugs` discipline), a developer or agent must, *before* touching a **sector** (a module/service), see that sector's full picture. That picture has **seven dimensions** — only the first is fully parseable from code:

1. **Structure** *(parseable)* — responsibilities, schema, file tree, dependencies.
2. **Behavior** — invariants ("always/never"), real runtime data + edge cases, concurrency/ordering, failure semantics (throws vs. silently-swallowed).
3. **Context** — env/config/secrets resolved + dev→prod differences, deploy state vs. git, resource ownership (ports/files/singletons), infra/routing.
4. **Boundaries** — parallel implementations that must stay in sync (client↔server DTOs, a platform's `expect`/`actual` pairs) + external-system contracts & failure modes.
5. **Intent & History** — the *why*/ADR, past bugs here + why prior fixes failed, non-code constraints (privacy law, per-user isolation, perf SLAs, the production rules), the spec's "done".
6. **Change-safety** — true blast radius (runtime paths + consumers + migrations), observability.
7. **Tests & Coverage** — which tests cover this (own + consumers'), coverage % + pass/fail, and the **uncovered surface** a change touches.

Regressions consistently trace to a dimension 2–7 factor being invisible at change time: a serialization-default 403 (Behavior); a bare-env launcher crash-loop (Context); a client↔server DTO mismatch (Boundaries); re-introduced fixed bugs (Intent/History); the missing feedback loop / untested paths (Change-safety + Tests & Coverage).

Verified research found **no off-the-shelf tool delivers all seven for a multi-language, multi-service repo in real time**: graphify (MIT, structure-only ~60–70%, no schema/test-coverage mapping), GitNexus (best fit but **Noncommercial license blocks commercial use**), Understand-Anything (MIT but **does not parse some languages, e.g. Kotlin**), CodeQL/SCIP (parse but CI-build-time, no sector view), GraphReAct (real paper, irrelevant).

## Decision

Build a **thin custom indexer**: a parseable **structural backbone**, with the six non-parseable dimensions **anchored** onto it (linked, not re-derived). Adopt the hard parts; build only the glue.

**Graph model (backbone):**
```
Nodes:  Sector · File · Symbol · Schema · Contract · Test · ExternalSystem · Resource(port/file/singleton)
Edges:  CONTAINS · IMPORTS/CALLS · DEFINES · TESTS · COVERS · DEPENDS_ON · IMPLEMENTS/CONSUMES
        · TALKS_TO(external) · OWNS(resource)
```

**Dimension → representation (the part no tool does):**

| Dimension | In the graph as | Fed by |
|---|---|---|
| Structure | the nodes + edges above | tree-sitter / AST + file-watch |
| Behavior | invariant attrs + **guard-links** on Schema/Contract/Symbol nodes; trace/fixture links | the catalog, fixtures |
| Context | **live overlay** on Sector nodes (env-resolved? live version? health green/red) + `OWNS`→Resource | the **parity gate** + CI + health probes |
| Boundaries | `TALKS_TO`→ExternalSystem w/ failure-mode attrs; contract-diff flags a shared DTO out-of-sync | CI + a schema/contract diff |
| Intent & History | Sector **links to** `CONTEXT.md`/ADR, catalog entries, `git log`, constraint tags | git hooks + the catalog |
| Change-safety | computed: **blast-radius** (`reverse IMPORTS`), `observable_signal` | graph queries |
| Tests & Coverage | `COVERS` edges (test→target) + per-sector coverage % / pass-fail + the **uncovered surface** of a change; a **Tests panel** on the dashboard | coverage reports + CI results |

**Tech choices (reference instantiation):**
- **Parse:** a `tree-sitter` grammar per frontend language (CST/imports/typed-DTO schema, *not* name resolution) + the backend language's AST. For accurate cross-symbol edges, ingest **SCIP** (the language's SCIP indexer, version-pinned) or CodeQL.
- **Store:** **Neo4j** — not an archived embedded store. Maintained, mature Cypher + viz.
- **Serve:** a **CLI** (`sectormap brief / blast-radius / consumers-tests / coverage <sector>`) the agent runs via Bash + the human in a terminal, plus a **live dashboard** (websocket/SSE push) for the human. **MCP is deferred** (optional later wrapper; not v1 — CLI is the decided agent surface, see PRD §4).
- **Real-time:** a background **watcher daemon** (file-watch + commit hook + coverage/CI ingest) re-extracts changed files and upserts within seconds; the parity gate + CI feed the Context overlay and the Tests panel; the dashboard pushes live.
- **View:** **React Flow** (card-per-sector, live) or Cytoscape.js.
- **Backend bonus:** **import-linter** for service-layer contracts (fail CI) — turns cross-service-coupling prose-rules into a loud guard.

**Rejected:** GitNexus (Noncommercial license blocks commercial use — revisit only with a paid license) · an archived embedded graph store · a no-parser tool for a language it can't read · writing the parser/DB/call-resolver from scratch (adopt SCIP/CodeQL/Neo4j) · MCP as the v1 agent surface (CLI is decided).

## Consequences

- **Buys:** all seven dimensions on one surface — especially the **consumers'-tests blast-radius**, **schema from typed DTOs/Pydantic**, and the **uncovered surface** per sector, which no tool provides; a CLI the agent consults pre-change + a live dashboard for the human.
- **Cost:** structural backbone + CLI ≈ **8–13 focused days**; the **live dashboard adds ~3–5 days** (React Flow + websocket); the **Tests & Coverage dimension adds ~2–3 days** (parse coverage + map tests→targets + CI ingest). The invisible-dimension overlays are mostly **wiring to artifacts that already exist** (parity gate, catalog, `CONTEXT.md`, git, coverage reports).
- **Risks:** language SCIP indexers support one compiler major per release + have monorepo/source-set friction (pin them; verify shared source sets); tree-sitter gives no name resolution (v1 uses import-level + heuristic edges — fine for ~80% of blast-radius); coverage absent where a repo emits none (show "coverage unknown" — honest, itself a signal).
- **SSOT alignment:** the map is the single surface that *couples* parseable structure to the non-parseable knowledge, instead of each living in a silo — consistent with the couple-to-single-source-of-truth stance.

## Build plan (staged — for the build session)

1. *(optional, ~30 min)* run **graphify** for an immediate structure-only graph, to validate the UX and de-risk before building.
2. **Structural backbone**, tracer-bullet: one sector end-to-end — frontend + backend extractors → Neo4j → **CLI** (`blast_radius`, `consumers_tests`, `coverage`).
3. **Live dashboard** (React Flow + websocket), card-per-sector, with the Context overlay + **Tests panel**.
4. **Anchor the overlays:** Context (parity-gate/CI feed) · Tests & Coverage (coverage reports + CI) · Intent/History (link `CONTEXT.md`/ADR/catalog/git) · Boundaries (contract-diff on shared DTOs) · Behavior (guard-links).
5. **import-linter** for the backend service contracts; the **PreToolUse hook** that runs the CLI before an agent edit.

## References

- PRD `docs/no-new-bugs-system.md` — product spec (the authoritative requirements).
- Code-graph tool research — verified verdicts + all sources.
- `no-new-bugs` skill — the seven "know-before-you-code" dimensions.
- Precedent: a ts-morph→Neo4j→MCP `blast_radius` graph (TS-only — proves the shape works + is agent-consumable).
- Tools: `safishamsi/graphify` · `fwcd/tree-sitter-kotlin` · Neo4j · `seddonym/import-linter` · SCIP indexers.
