# The Sector Map — tooling arm of the bugless protocol (stack-agnostic)

The `/no-new-bugs` discipline tells you *how* to change code safely. The **sector map** is the
tool that makes the seven know-before-you-code dimensions **visible and queryable** — for a
human *and* an agent — in **any** project, any language. This file is the universal design;
each project instantiates it.

## The unit: a "sector"
A sector = a module / service / package you reason about as one thing. Pick the boundary per
project (service-level, package-level, or feature-level).

## What it shows: the seven dimensions
1. **Structure** *(parseable)* — responsibilities, schema, file tree, dependencies.
2. **Behavior** — invariants, runtime data + edge cases, concurrency, failure modes.
3. **Context** — env/config, deploy-state-vs-source, resource ownership, infra/routing.
4. **Boundaries** — parallel impls that must stay in sync (client↔server, platform actuals) + external systems.
5. **Intent & History** — the *why*/ADR, past bugs + why fixes failed, non-code constraints.
6. **Change-safety** — blast radius, observability.
7. **Tests & Coverage** — covering tests (own + consumers'), coverage + pass/fail, the **uncovered surface** of a change.

Only #1 is fully parseable; #2–#7 are *anchored* onto the structural backbone as attributes,
links, overlays, and a test panel. **Structure is the cheap half; the regressions live in the
other six** — which is why no off-the-shelf code-graph tool (it draws only #1) is enough.

## Three layers (universal)
- **Map** — a live graph of sectors carrying the seven dimensions.
- **Gates** — checks that make the invisible dimensions fail loud (guards/CI, a deploy-parity check, a bug catalog, contract linters).
- **Loop** — the discipline consuming Map + Gates before / during / after every change.

## Architecture (stack-agnostic)
```
[ file save / commit / test run / CI ]
      │  watcher daemon (file-watch + coverage/CI ingest) — re-extract changed files, upsert (~seconds)   ← real-time
      ▼
   graph DB ──(emit "changed")──► dashboard server ──push──► browser re-renders the sector LIVE   (human)
       └─────────────────────────── CLI reads on demand (agent via shell + human terminal)        (agent)
```
- **Parse:** your languages' parsers (tree-sitter / native AST) → nodes/edges. Add a precise indexer (SCIP / LSIF / CodeQL) only if heuristic edges aren't enough.
- **Store:** a *maintained* graph DB (e.g. Neo4j). Never an archived/abandoned core dependency.
- **Serve:** a **CLI** for the agent (pull at edit-time, via shell) + a **live dashboard** for the human (push, websocket/SSE). **Not MCP by default** — one CLI serves agent + human + the enforcement hook + CI; MCP is an optional later wrapper, never the foundation.
- **Enforce:** a PreToolUse hook runs the CLI before an agent edit and injects the sector's seven-dimension brief + blast radius + uncovered surface. Real-time freshness comes from the *watcher*, not the surface.

## Graph model (template)
```
Nodes:  Sector · File · Symbol · Schema · Contract · Test · ExternalSystem · Resource
Edges:  CONTAINS · IMPORTS/CALLS · DEFINES · TESTS · COVERS · DEPENDS_ON · IMPLEMENTS/CONSUMES
        · TALKS_TO(external) · OWNS(resource)
```
Keystone queries: `blast_radius(symbol)` (who's affected) · `consumers_tests(sector)` (own + dependents' covering tests) · `uncovered_surface(change)` (symbols a change touches that no test exercises).

## To instantiate in a new project
1. Pick the sector boundary.
2. Wire parsers for your languages → the graph.
3. Point the **Context** overlay at your deploy-parity check + CI health.
4. Feed dimension **#7** from your coverage reports + CI results.
5. Link **Intent & History** to your ADRs / CONTEXT.md / bug catalog / git.
6. Stand up the watcher + CLI + live dashboard; add the PreToolUse hook.

## Reference instantiation
A worked example targets a statically-typed frontend language + a typed backend language —
see the PRD ([`../../docs/no-new-bugs-system.md`](../../docs/no-new-bugs-system.md)) and the
design ([`../../docs/0001-realtime-sector-map.md`](../../docs/0001-realtime-sector-map.md)).
Tech: `tree-sitter` grammars + each language's AST → Neo4j → CLI + React-Flow live dashboard.
