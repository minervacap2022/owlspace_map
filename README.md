# owlspace_map

The **agent-development operating system** — a GLOBAL, project-agnostic, stack-agnostic
discipline + tooling so that **every agent, on every project, in every language, ships
bugless changes**.

Nothing here is Klik-specific *by design*. Klik, Owlspace, EVE, owl-backend are just
**instances** that plug into the same global core. (Klik shows up most in the data only
because it's the most-worked project so far — that's incident history, not scope.)

## Global core — use on any project, any language

| Dir | What | Global because |
|---|---|---|
| [`no-new-bugs/`](no-new-bugs/) | The protocol (skill): Principle 0 (couple to one source of truth), the change loop, the verification ladder, and the **seven know-before-you-code dimensions** — Structure · Behavior · Context · Boundaries · Intent&History · Change-safety · Tests&Coverage. | Stack-agnostic by construction; every concrete example is explicitly labelled "instance, illustration only." |
| [`bug-regression-catalog/`](bug-regression-catalog/) | The **one** multi-project incident catalog (`catalog.yaml`) + a single loader that enforces id-uniqueness and **auto-derives each lint's project from its paths** so cross-project bleed is impossible. | One catalog, all projects. Loader markers: `klik · owl · owl-backend · eve` (add more freely). A lint tagged `owl` can never fire on a Klik file, and vice-versa. |
| [`docs/`](docs/) | The **sector-map** design — the live per-sector view of the seven dimensions (CLI + dashboard + Neo4j knowledge graph). PRD + ADR-0001. | Instantiable in any repo; the design names projects only as examples. |

## Per-project instances — examples, not the product

| Dir | What |
|---|---|
| [`production-rules-checker/`](production-rules-checker/) | **Klik's** instance of a per-project gate, kept as the reference implementation. The *reusable* part is the validator **engine** + the catalog `--project` filter; the *Klik-specific* part is its rule text. Owl/EVE/any project stand up their own gate the same way — see that dir's README. |

## How ANY agent/project adopts this

1. **Use the protocol** — `no-new-bugs/` is already global; nothing to configure.
2. **Log incidents to the shared catalog**, tagged by your project's paths. The loader
   derives the project; `--project <you>` isolates your lints from everyone else's.
3. **(optional) Stand up a gate** for your project by pointing the reference engine at the
   shared catalog with `--project <you>` and your own rules reference.

The catalog, the loader, the `--project` isolation, and the protocol are **global**. Only
a gate's *rule text* is ever per-project.

## Local wiring — single source of truth, no drift

This repo is the one home; the tool locations are symlinks into it:

- `~/.claude/skills/no-new-bugs` → `no-new-bugs/`
- `~/.claude/skills/bug-regression-catalog` → `bug-regression-catalog/`
- `~/.git-hooks/production-rules-checker` → `production-rules-checker/`
