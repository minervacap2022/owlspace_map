# owlspace_map

The **no-new-bugs system** — a global, stack-agnostic discipline + tooling for shipping
bugless changes across every project and language. One home for all of it.

## Contents

| Dir | What |
|---|---|
| [`no-new-bugs/`](no-new-bugs/) | The protocol (skill). Principle 0 (couple to one source of truth), the change loop, the verification ladder, and the **seven know-before-you-code dimensions**: Structure · Behavior · Context · Boundaries · Intent&History · Change-safety · Tests&Coverage. |
| [`bug-regression-catalog/`](bug-regression-catalog/) | The global multi-project incident catalog (`catalog.yaml`) + a single loader (`scripts/load_catalog.py`) that enforces id-uniqueness and derives each lint's project from its paths, plus a committed loader test and per-bug chaos runners. |
| [`production-rules-checker/`](production-rules-checker/) | The production-rules gate (`scripts/validate_production_rules.py`). Consumes the catalog via `--project <name>` so one project's lint can't fire on another's file; fails loud when the catalog is malformed. |
| [`docs/`](docs/) | The **sector-map** design — the live per-sector view of the seven dimensions (CLI + dashboard + Neo4j knowledge graph). `no-new-bugs-system.md` (PRD) + `0001-realtime-sector-map.md` (ADR). |

## How it's wired locally

The three tool dirs are symlinked from the locations the tooling loads them from, so this
repo is the **single source of truth** (no drift):

- `~/.claude/skills/no-new-bugs` → `no-new-bugs/`
- `~/.claude/skills/bug-regression-catalog` → `bug-regression-catalog/`
- `~/.git-hooks/production-rules-checker` → `production-rules-checker/`
