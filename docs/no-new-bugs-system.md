# PRD — No-New-Bugs Development System (codename **Sentinel**)

| | |
|---|---|
| **Status** | Draft v1.2 |
| **Related** | `ADR-0001` (sector-map design) · `no-new-bugs` skill (the discipline) · code-graph tool research |
| **One-liner** | A system that makes the **seven dimensions of "what you must know before changing code"** both **visible** (a live per-sector graph) and **enforced** (automatic gates), for a human developer *and* an AI agent — so that changing code stops silently introducing regressions. |

> **Scope note.** This is a **stack-agnostic** design. The worked examples below (and the
> v1 reference instantiation — a Kotlin-Multiplatform frontend + a multi-service Python
> backend) are illustrative; any project swaps in its own parsers, gates, and coverage
> sources. Nothing here is specific to one project.

---

## 1. Summary

Modern software is built fast — by humans and by AI agents, often across multiple languages
and services. The dominant failure mode of that speed is **re-introducing bugs**: a fix
reveals the next bug, an invariant written only in prose gets re-violated, a green test was
lying, a thing that "works" works only on the machine it was built on.

The root cause is that safely changing a piece of code ("a **sector**" — a module or
service) requires knowing **seven dimensions** of it, but only the first is fully visible in
the code; the rest live invisibly in people's heads, in the service manager, in prose docs,
in a bug catalog nobody opens, and in test suites no one mapped to what they actually cover.
**Sentinel** surfaces all seven on one graph (the **Map**), turns the invisible ones into
loud automatic checks (the **Gates**), and wires both into every change (the **Loop**) —
kept current in real time by a background watcher, and served to the human as a **live
dashboard** and to the agent as a **CLI**.

---

## 2. Problem / Background

To change a sector without breaking something, you must know:

| # | Dimension | Where it lives today | A real bug from *not* seeing it |
|---|---|---|---|
| 1 | **Structure** — responsibilities, schema, file tree, dependencies | the code (parseable) | — (the visible half) |
| 2 | **Behavior** — invariants, real runtime data/edge-cases, concurrency, failure modes | runtime + people's heads | a serialization-default dropped a required field → 403 |
| 3 | **Context** — env/config, deploy-state-vs-git, resource ownership, infra/routing | the service manager, the reverse proxy, the server | a bare-env launcher crash-loop |
| 4 | **Boundaries** — forks/parallel impls that must sync, external systems | tribal knowledge | the two-fork drift; an unpowered hardware rail |
| 5 | **Intent & History** — the *why*, past bugs + why fixes failed, constraints (privacy law, isolation) | ADRs, git, a catalog | re-introduced already-fixed bugs |
| 6 | **Change-safety** — true blast radius, observability (how you'd know it broke in prod) | nowhere | the missing/lying feedback loop |
| 7 | **Tests & Coverage** — does this sector have unit tests, what they cover, pass/fail, **which tests cover a change (own + consumers')**, and the **uncovered surface** you're about to touch | test files + coverage reports + CI results (rarely mapped to sectors) | a change to an **untested path** shipped silently (a low-coverage area) |

**Only dimension #1 is fully parseable from code.** Off-the-shelf code-graph tools (graphify,
GitNexus, Understand-Anything) draw #1 and stop — so the regressions keep coming from #2–#7,
which no parser surfaces. Notably, **none of them maps tests to what they cover or shows the
uncovered surface** (#7) — the single most important thing for *preventing* a regression.
"It works" too often means "works on the one tree / machine / process I'm holding," not
"reproducible from a clean checkout, with the covering tests green."

This is not a tooling gap alone; it is the reason a team keeps paying the same bug tax.
Sentinel exists to close it.

---

## 3. Goals / Non-Goals

### Goals
- **G1** — Make all seven dimensions of any sector visible on **one surface**, for the human (live dashboard) and the agent (CLI).
- **G2** — Turn the invisible dimensions into **loud, automatic gates**, so a regression in a *known class* is caught at change-time, pre-merge.
- **G3** — Integrate Map + Gates into **every change** (the Loop): know-before-you-code → feedback-loop-first → surgical change → clean-slate verify → guard-against-recurrence.
- **G4** — Drive the **bug-introduction rate** down: known classes → ~0 reaching prod; unknown classes → shrunk and faster-caught.
- **G5** — Make the **test safety net visible per sector** — coverage, pass/fail, and especially the *uncovered surface* — so neither human nor agent changes an untested path unknowingly.

### Non-Goals
- **NG1** — Not a promise of *literally zero* bugs. The honest target: introducing a bug must require **actively defeating a visible, enforced signal**, instead of silently slipping past invisible ones.
- **NG2** — Not a replacement for tests, CI, or review — it makes them **targeted** (blast-radius), **complete** (consumers' tests), and **visible** (coverage per sector), not redundant.
- **NG3** — Not a general code-search / RAG tool, not a multimodal docs/knowledge tool.
- **NG4** — Per instantiation, the parser set is bounded (the reference v1 targets two languages); the *design* is language-agnostic — add a parser to add a language.

---

## 4. Users & Personas

**P1 — Human developer.** Before touching a sector, needs to *see* its responsibilities, schema, dependencies, **who depends on it + which of their tests cover it**, its test coverage + the uncovered surface, its live deploy state, the *why*, and its past bugs — without spelunking many separate systems. Primary surface: a **live, always-current dashboard** that pushes updates as code changes (no manual refresh).

**P2 — AI coding agent (Claude Code et al.).** Same need, but **machine-readable and queried automatically the moment it's about to edit**, so it does not confidently break what it cannot see. Primary surface: a **CLI** run via Bash (it *pulls* on demand — the freshest possible moment; it does not want push). **Decided: CLI. MCP is not planned for v1** (an optional later wrapper over the same engine, only if a multi-client agent fleet ever needs auto-discovery).

Both run on the **same** underlying graph + gates — one source of truth, two faces.

---

## 5. Core Concept — Map + Gates + Loop

Sentinel is three layers, not one tool:

1. **The Map** — a live graph of the codebase as **sectors**, each carrying the seven dimensions (structure as nodes/edges; the invisible ones anchored as attributes, links, overlays, and a test panel), kept current by a background **watcher**. *To build.*
2. **The Gates** — guards / CI / the deploy-parity gate / the bug catalog / import-linter that make the invisible dimensions **fail loud and automatically**. *Often mostly built already.*
3. **The Loop** — the no-new-bugs discipline that *consumes* Map + Gates before, during, and after every change. *Codified as the `no-new-bugs` skill; needs wiring to the Map.*

**Graph model (the Map's backbone):**
```
Nodes:  Sector · File · Symbol · Schema · Contract · Test · ExternalSystem · Resource(port/file/singleton)
Edges:  CONTAINS · IMPORTS/CALLS · DEFINES · TESTS · COVERS · DEPENDS_ON · IMPLEMENTS/CONSUMES
        · MIRRORS(cross-repo) · TALKS_TO(external) · OWNS(resource)
```
`TESTS`/`COVERS` edges (test → the symbols it exercises) power dimension #7. The invisible dimensions attach to this backbone (see FR-M6, FR-M11).

**Data flow (where "real-time" comes from):**
```
[ file save / git commit / test run / CI result ]
        │  watcher daemon (fswatch / watchman / chokidar) — re-extract changed file + ingest coverage/CI, upsert (~seconds)
        ▼
   Neo4j  ── always-current graph ──┬──(emit "changed")──► dashboard server ──websocket──► browser re-renders the sector LIVE
                                    └── CLI reads on demand (agent via Bash + human terminal)
```

---

## 6. User Stories

- **US1 (blast radius)** — *As a dev*, before I edit a shared auth module, I see the services + client call-sites that depend on it **and the tests that cover them**, so I run those first.
- **US2 (context)** — *As a dev*, I see a sector go **red (deploy-state ≠ git / unhealthy)** on the dashboard the moment it happens, before I build on top of it.
- **US3 (intent & history)** — *As a dev*, I see this sector previously had a serialization-default 403 bug, with the guard that now prevents it, so I don't re-open it.
- **US4 (agent loop)** — *As the agent*, before my `Edit` on a sector, I run the CLI, receive its **seven-dimension brief + blast radius + covering tests**, and run those tests automatically.
- **US5 (boundaries)** — *As the agent*, I'm warned this sector has a **twin in the other repo** that must stay in sync, so I port the change to the right layer.
- **US6 (tests & coverage)** — *As either*, the dashboard shows this sector at **X% coverage**, the exact tests covering the line I'm about to change, and a **red "uncovered" badge** if the path I'm touching has no test — so I write one *first*.
- **US7 (recurrence)** — *As either*, when a new bug class appears, it becomes a **new gate + catalog entry**, so it can't silently return.

---

## 7. Functional Requirements

### The Map (FR-M)
- **FR-M1** — Build and maintain a graph of **sectors** with the node/edge model above.
- **FR-M2** — Parse the project's languages: files, imports, classes/functions, **schema** (typed DTOs / Pydantic / SQL DDL), and **tests**. (Reference v1: a statically-typed frontend language + a typed backend language.)
- **FR-M3 — Blast-radius query**: given a symbol/sector, return everything that depends on it (transitively) = the real change surface.
- **FR-M4 — Consumers'-tests query** *(keystone)*: the tests — own **and dependents'** — that cover a given change.
- **FR-M5 — Schema extraction** from typed DTOs / Pydantic / SQL DDL.
- **FR-M6 — Anchor the invisible dimensions**: Context (deploy-state + health overlay, `OWNS(port)` edges), Boundaries (`MIRRORS` fork-drift, `TALKS_TO` externals), Intent & History (links to ADR/`CONTEXT.md`/catalog/`git log`), Behavior (guard/lint links on schema & contract nodes), Change-safety (blast-radius + observable-signal flags).
- **FR-M7 — Real-time freshness (the engine)**: a background **watcher daemon** (file-watch + commit hook + coverage/CI ingest) re-extracts changed files and upserts the graph within seconds. This is the single source of "real-time"; every surface reads this always-current graph.
- **FR-M8 — Agent surface = CLI**: a CLI the agent runs via Bash and the human runs in a terminal (`sectormap brief / blast-radius / consumers-tests / coverage <sector>`, `--json`), reading the current graph each call. **CLI is the decided surface; MCP is not planned for v1.**
- **FR-M9 — Human surface = LIVE dashboard (MUST)**: a dashboard that **pushes** changes to the browser (websocket/SSE) and re-renders the affected sector **live, without a manual refresh**, within seconds of a code / deploy-state / test-result change. A React-Flow (or equivalent) card-per-sector view of all seven dimensions, with the Context overlay (green/red) **and the Tests panel** updating in real time.
- **FR-M10 — Span multiple repos** (e.g. a frontend repo + a backend repo) in one map.
- **FR-M11 — Tests & Coverage dimension (MUST)**: for every sector, surface (a) its unit-test inventory, (b) **coverage %** and pass/fail (ingested from coverage reports and the latest CI/test run), (c) the **test→target mapping** (`TESTS`/`COVERS` edges), and (d) the **uncovered surface** of a pending change (the symbols a change touches that no test exercises). Available on both the CLI and the live dashboard; the dashboard MUST render a per-sector **Tests panel** (coverage, pass/fail, covering tests own + consumers', uncovered badge).

### The Gates (FR-G) — *often largely exist; integrate them*
- **FR-G1** — Every known bug-class has a loud automatic check (the shared bug catalog's lints; the project's design-system / convention guards).
- **FR-G2** — Deploy-parity gate: running stack == committed model (a scheduled read-only check) — feeds the dashboard's Context overlay.
- **FR-G3** — Service-contract enforcement: an import-linter for service layers (fail CI on violation).
- **FR-G4** — Clean-slate verification: CI builds + tests from a fresh checkout on every push; results feed dimension #7.
- **FR-G5** — Recurrence guard: every recurred bug becomes a check + an `observable_signal`.

### The Loop (FR-L)
- **FR-L1** — Before editing a sector, surface its **seven-dimension brief + blast radius + covering tests / uncovered surface** (agent: automatically via the **CLI in a PreToolUse hook**; human: the **live dashboard**).
- **FR-L2** — Feedback-loop-first: if the path being changed is in the **uncovered surface** (#7), write a failing test *before* the change.
- **FR-L3** — Run **consumers' tests** before and after the change.
- **FR-L4** — Guard-against-recurrence: a new bug class → a new gate + catalog entry, automatically prompted.

---

## 8. Non-Functional Requirements

- **NFR1 — Languages**: at least the project's frontend + backend languages, both first-class; pluggable parsers for more.
- **NFR2 — Real-time**: a background **watcher** reflects a saved change (and a new coverage/CI result) in the graph within seconds; the **live dashboard pushes that update to the browser with no manual refresh** (websocket/SSE); the deploy-state overlay refreshes within the parity-gate cadence.
- **NFR3 — Local & private**: code parsing happens offline; **no code leaves the machine**. **License permissive (MIT/Apache)** — no Noncommercial/AGPL blockers (rules out GitNexus as the engine).
- **NFR4 — Dual-consumable**: a **CLI** for the agent (pull at edit-time) and a **live dashboard** for the human (push), over one graph. No MCP in v1.
- **NFR5 — Trustworthy accuracy**: blast-radius and coverage must not **silently** under-report; where edges are heuristic (no name-resolution in v1) or coverage is stale, the map must **say so** rather than imply completeness.
- **NFR6 — Low friction**: must not slow the change loop; the watcher auto-refreshes, no manual rebuild step.
- **NFR7 — Maintainable foundation**: no archived/abandoned core dependencies (→ **Neo4j**, not an archived embedded store).

---

## 9. Success Metrics

- **M1 — Bug-introduction rate**: known-class regressions caught **pre-merge** vs. reaching prod (target: known classes ≈ 0 reach prod).
- **M2 — Agent-consults-first rate**: % of agent changes where the seven-dimension brief / blast-radius / coverage was queried **before** the edit (target ≈ 100%).
- **M3 — Blast-radius completeness**: of post-merge regressions, the % the map's consumers'-tests *would* have flagged (target: high; misses become map improvements).
- **M4 — Re-introduced-bug count**: previously-closed catalog bugs that recur (target: **0**).
- **M5 — Uncovered-change rate**: % of changes that touched the **uncovered surface** without adding a test first (target → 0).
- **M6 — Time-to-understand a sector** (human): seconds to answer "what depends on this + what tests cover it," vs. ~hours today.

---

## 10. Scope

**In — v1 (the backbone):** structural map (the project's languages → Neo4j) · the **watcher daemon** (real-time freshness, incl. coverage/CI ingest) · blast-radius + consumers'-tests + schema + **coverage** queries · the **Tests & Coverage dimension (MUST)** · the **CLI** · the **LIVE dashboard (MUST)** with push + the **Tests panel** · one sector end-to-end → then repo-wide · wire the existing gates (parity / catalog / convention-guards) as the Context & Behavior overlays.

**In — v2 (the full surface):** the remaining overlays (Boundaries, Intent & History) · import-linter contracts · the automatic agent pre-edit hook.

**Out:** any zero-bug guarantee · replacing CI / tests / review · general code search or RAG · multimodal docs · an MCP server (deferred indefinitely; CLI is the decided agent surface).

---

## 11. Constraints, Dependencies & Risks

- **Build the glue, adopt the hard parts.** Backbone + CLI ≈ **8–13 focused build-days**; the **LIVE dashboard adds ~3–5 days** (React Flow + a small websocket/SSE server); the **Tests & Coverage dimension adds ~2–3 days** (parse coverage reports + map tests→targets + ingest CI results). Parse with `tree-sitter` grammars (structure only — **no name resolution**) + each language's AST; optionally ingest **SCIP**/`CodeQL` for precise cross-symbol edges. Store in **Neo4j** (maintained) — not an archived embedded store.
- **Two background processes**: the **watcher** (graph + coverage freshness) and the **dashboard server** (browser push). Both small and local; neither is MCP.
- **Coverage source**: dimension #7 depends on the repos emitting coverage and CI publishing test results; where absent, the sector shows "coverage unknown" (honest, per NFR5) — and that's itself a useful signal.
- **GitNexus** is the closest off-the-shelf fit but is **PolyForm Noncommercial** → **blocked** for commercial use. **graphify** (MIT) is viable for a quick structural v0.
- **Multiple repos**: a separate backend repo may not be in the frontend checkout — the map must index both.
- **Risk — cross-language precision**: language indexers pin to specific compiler majors and have monorepo/source-set friction; v1 edges may be import-level + heuristic (acceptable for ~80% of blast-radius, but must be labeled — NFR5).

---

## 12. Open Questions

- **Sector boundary**: service-level (backend) vs. module/package (frontend) vs. feature — likely both, defined per-repo. Needs a concrete rule.
- **v0 path**: adopt graphify for the structural layer first, or go straight to the custom backbone?
- **Loop automation**: a hard PreToolUse hook (blocks the edit until the brief is consulted) vs. the skill prompting the agent — how forcing should it be?
- **Coverage granularity**: line-level vs. symbol/function-level "uncovered surface" — line-level is more precise but heavier to map to the graph.

*(Settled: agent surface = CLI, not MCP. Dashboard = live/push, a MUST. Tests & Coverage = dimension #7, a MUST.)*

---

## 13. References

- `ADR-0001` — real-time sector-map design (graph model, tech choices, build plan).
- `no-new-bugs` skill — the discipline + the know-before-you-code dimensions (canonical source of truth).
- Code-graph tool research — graphify / GitNexus / Understand-Anything verdicts + sources.
