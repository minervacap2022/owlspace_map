# Code-graph tools vs the sector map — verified comparison

Cloned and **run** (not assumed) on 2026-06: GitNexus, graphify, Understand-Anything.
GraphReAct is a research *paper* — only empty stub repos exist, so it's excluded.

## What each one is

| Tool | What it is | Parse | License |
|---|---|---|---|
| **GitNexus** (`abhigyanpatwari/GitNexus`, 41k⭐) | Knowledge graph for AI agents — WebUI + CLI + **MCP**; "zero-server" (in-browser store `lbug`) | tree-sitter, 12 langs | **PolyForm Noncommercial** |
| **graphify** (`safishamsi/graphify`, YC S26) | `{nodes, edges}` + clustering + **multimodal** (code/docs/images/video) → exports `graph.json`/html/svg/Obsidian; ships as an agent skill + query CLI (`path`, `explain`) | tree-sitter, 12 langs | **MIT** (PyPI `graphifyy`) |
| **Understand-Anything** (`Lum1104/Understand-Anything`) | Interactive web app — explore / search / ask a graph (d3 + react-flow) | tree-sitter, 12 langs | **MIT** |
| **GraphReAct** | A reasoning *paper*; no real tool repo | — | — |

## The graphs (granularity + model)

| | Granularity | Node types | Edge types | Confidence | Dims 2–7? |
|---|---|---|---|---|---|
| **GitNexus** | symbol / call | **50+**: Class·Function·Method·Interface·Module·**Route·Tool·Process**·Community·CodeEmbedding | CALLS·IMPORTS·EXTENDS·IMPLEMENTS·OVERRIDES·**HANDLES_ROUTE·STEP_IN_PROCESS·ENTRY_POINT_OF** | — | ✗ |
| **graphify** | file / symbol | file + qualified symbol (`load()`, `L30`) | imports·calls·contains·references·**rationale_for** | **EXTRACTED / INFERRED / AMBIGUOUS** | ✗ |
| **Understand-Anything** | symbol | symbol | imports·calls | — | ✗ |
| **sector map (ours)** | **sector** → drill to symbol/call | Sector + Symbol | depends_on·references·**call** | (SCIP exact / graphify-tagged / heuristic) | **✓ all seven** |

Measured: graphify on 2 files → 23 nodes / 56 edges with `{source, target, relation, confidence}`. GitNexus's graph is the **richest structure** (framework-aware Routes/Tools/Processes). **Confirmed directly from their code: none of the three computes dimensions 2–7** — the "coverage/test" hits in their repos were their *own* test files, not coverage-ingestion / deploy-parity / bug-catalog features.

## Compatibility

| | License | Ingestible into our map | Use as our structure layer |
|---|---|---|---|
| **GitNexus** | ❌ Noncommercial | hard (custom in-browser `lbug` store) | No (license) — though it's the structure gold-standard |
| **graphify** | ✅ MIT, PyPI | ✅ **yes** — qualified symbols + `calls` edges + confidence | ✅ **adopted natively** (see below) |
| **Understand-Anything** | ✅ MIT | standalone web app, not a library | No |
| **GraphReAct** | — | — | — (a paper) |

## Verdict
- **They beat us on pure structure** (GitNexus especially: more node/edge types, framework-aware, mature viz). Ours is coarser there (sector-level), though we drill down + resolve calls.
- **We're the only one with dimensions 2–7** — Behavior (guards), Context (deploy-parity), Boundaries, Intent (the bug catalog), Change-safety, and **real test-coverage**. That is the whole reason the map exists, verified by reading their code rather than assuming.
- **Complementary, not competitors** → so we **integrated graphify natively** as a structure/call provider.

## What we did about it (native graphify integration)
`sector_map/graphify_ingest.py` imports graphify **as a library** (not a shell-out) and maps its
`{nodes, edges}` into the engine's `(syms, call_edges, sector_calls)` shape. The engine now has
three native call-graph providers, in order of precision, all emitting the same shape and labeled
in `call_resolution`:

1. **SCIP** (`scip (type-precise)`) — when an `index.scip` is present (type-checker-resolved).
2. **graphify** (`graphify (tree-sitter, confidence-tagged)`) — opt-in via the profile `"call_graph": "graphify"`; tree-sitter calls with EXTRACTED/INFERRED confidence.
3. **heuristic** (`heuristic (name-level)`) — the dependency-free default.

Interesting result on owlspace_map: **graphify caught cross-sector calls SCIP missed** — our scripts
import each other through `sys.path.insert` runtime hacks that the SCIP type-checker can't follow, but
graphify's name-based resolution links them. Different providers, different blind spots — which is why
the engine keeps all three and labels which one produced the graph.
