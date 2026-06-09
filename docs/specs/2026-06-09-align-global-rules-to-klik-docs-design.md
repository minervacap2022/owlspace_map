# Design: Align global anti-regression artifacts to the latest Klik source-of-truth docs

**Date:** 2026-06-09
**Author:** Chroma (for Wilson Xu)
**Status:** awaiting review

## Problem

Five canonical Klik docs in the Feishu wiki (space `7641518835173952479`, all children of the
index node `X7WV…`) are the **source of truth**. Three local artifacts have drifted from them and,
worse, the docs have drifted from **each other**. The ask: distill the *generalizable* lessons into
the **GLOBAL** artifacts (`/no-new-bugs`, the sector-map) without making them Klik-specific, AND
align the **Klik-instance** gate (`/production-rules-checker`) to today's truth — fixing the source
docs where they are internally stale.

Ruling from the owner (load-bearing for every edit below): **the monorepo index doc
(`Klik开发项目约定`, edited 2026-06-09) is the singular truth.** Where other docs disagree
(migration tool, repo topology, logger import), the index doc wins; the divergent material is
*flagged at source*, never preserved in the gate.

### The 4 canonical docs (5th = repo-inventory Base, treated as stale-side evidence)

| Doc | wiki token | role |
|---|---|---|
| `Klik开发项目约定` (index, monorepo) | `X7WVwNea4i4kavkF8e9cUcs8nqg` | **TRUTH** |
| `错误码注册表` (Base, table `tblvh8MdlMseI05D`) | `I7XqwORteiMUdyk4DtJcBwWrntg` | truth (error codes) |
| `002 · 测试规范` | `MH4AwL4L0iB3RdkTehycibRqn7c` | truth + has 2 stale refs (fix in-place) |
| `KLIK 分层架构与服务管理说明` | `R72lwdCgKiV6QXkqA8ncNXGcnjf` | truth for systemd/observability; **stale** on migration/topology |
| `KLIK 仓库清单` (Base) | `CNbZwUohEikjulkLYENcrAGgnwg` | stale-side evidence (6-repo split) |

## Lark-doc investigation findings (go into the GitHub issue, §D)

| # | Finding | Sev |
|---|---|---|
| A | **Migration contradicts on 3 axes**: index = `golang-migrate` / `Klik/db/migrations/` / **PgBouncer**; layering = `Alembic` / `klik-infra` repo / **direct 5432**. | high |
| B | **Monorepo vs 6-repo split**: index = "单仓库(monorepo)" with `db/` inside; layering + repo-inventory Base = 6 repos incl. `klik-infra` holding schema/migrations. | high |
| C | **Logger import**: index + layering = `from KK_logger import get_logger` (own repo, "零 KK_common 依赖"); **002 testing doc still says `KK_common/logger`** (stale). | med |
| D | **Orphaned numbering**: "002 · 测试规范" cites "001 · 错误码注册"; no `001`/`000` doc exists. | low |
| E | **Registry lifecycle**: 17 / 32 error codes still `proposed` (= "not usable" by the docs' own rule), incl. `permission_denied`, `resource_not_found`. Data itself clean (no dupes/malformed; `B02xx⇔stack_trace` invariant holds). | med |
| F | **Soundness**: `golang-migrate` over PgBouncer is self-suspect — golang-migrate holds a session-scoped `pg_advisory_lock` across a migration, which transaction-pooling (the same mode the layering doc says "breaks multi-statement DDL") does not preserve. Team should confirm session-mode or direct 5432. | med |

---

## Section A — GLOBAL: `no-new-bugs/SKILL.md` (6 distilled patterns, stack-agnostic)

Each edit is a durable principle; every concrete example stays labeled "instance/illustration."

### A1 — Completeness/enumeration guard (the headline nugget)
**Where:** step (5) "Guard against recurrence", new bullet after the CODEOWNERS bullet.
**Add:**
> - **Make "I did X everywhere" a verified invariant — not a claim.** When a fix means applying
>   the same property to *every* member of a set (every service registers the handler, every route
>   emits a coded error, every DTO field is wired onto the request), the regression is the *next*
>   member added without it. Write a guard that **enumerates the set and asserts the property on
>   each**, so a new member missing it fails loud. "All N wired" stops being a sentence you wrote
>   once and becomes a check that re-proves itself on every change. *(Instance: a test that
>   discovers every FastAPI app object and asserts each one installed the shared exception handler —
>   a service created without it turns the suite red.)*

### A2 — In-memory fake > mock
**Where:** the false-green paragraph in "THE ANTI-REGRESSION RULES" ("Mock only true external
boundaries, never the system under test, and assert on observable output.").
**Append:**
> Prefer an **in-memory implementation of your own port** (a real `InMemoryFooRepository`
> satisfying the same interface the production code depends on) over a hand-set mock: it exercises
> real logic and, because it implements the contract, it cannot drift the way a mock's fabricated
> return can — the third trap above (a mock auto-fabricating a field the code reads) is impossible
> when the test double is bound by the same typed interface.

### A3 — Assert the richest observable, not the coarsest
**Where:** step (4) verification, after "assert on observable output … never on 'it ran' or a count."
**Add sentence:**
> When a **structured** signal exists (a registered error code, a correlation-id log line), assert
> on **it**, not just a coarse proxy like an HTTP status — a test that asserts only `403` passes for
> the *wrong* 403; asserting the error code pins the actual cause and is what lets a failure be
> traced by *code + log line* later.

### A4 — One name, one schema (Principle 0 at the data layer)
**Where:** Principle 0 "Proof, in generic shapes" list, new bullet.
**Add:**
> - **One name, one schema →** the same identifier carrying two shapes is duplication-drift at the
>   data layer: one metric name emitted with two different label sets, or one DTO field serialized
>   two ways on two code paths. One identifier must mean one schema everywhere, or every consumer
>   joins across the variants by hand.

### A5 — Layering = "contracts-not-guts" made structural
**Where:** Principle 0 part 4 (the "contract or guts?" discriminator), appended sentence.
**Add:**
> A **layered** architecture (domain ← application ← infrastructure; resource-vs-ops;
> library-vs-consumer) is exactly this rule made physical: inner layers expose contracts, outer
> layers depend inward only — so "depend on contracts, never on guts" becomes a *directory
> invariant* a guard can grep (e.g. the domain layer importing the web framework is a violation you
> can detect mechanically).

### A6 — Pre-push hook = the floor when CI is unavailable
**Where:** verification ladder, rung 2 ("CI = A FREE FOREIGN MACHINE"), appended.
**Add:**
> When CI is genuinely unavailable (private repo, no paid runner), the floor is a **committed
> pre-push hook running the same suite** — slower, and skippable with `--no-verify`, but it keeps
> the loop *committed and runnable from a clean checkout*, which is what this rung is really about.
> An **uncommitted** local hook is not a feedback loop (the prevention system itself once fell to a
> guard authored but never committed).

---

## Section B — GLOBAL: `no-new-bugs/references/sector-map.md` (test-maturity matrix overlay)

**Where:** under "## What it shows: the seven dimensions", after the numbered list.
**Add subsection:**
> ### Overlay: the test-maturity matrix (dimensions #4 × #7)
> For any contract with **parallel implementations** (dimension #4 — client↔server, an
> `expect`/`actual` pair, two SDKs of one API), the Tests overlay (#7) is best rendered as a grid:
> *(each side of the boundary)* × *(unit · integration · e2e)*, each cell carrying a maturity mark
> (✅ ready · ⚠️ thin · ❌ missing) plus an explicit **gap list**. This makes the uncovered surface
> of a *cross-boundary* change visible at a glance and turns "is the **other** side tested too?"
> into a rendered cell instead of a thing you must remember to ask — the same invariant guarded on
> only one side of a client↔server pair is a half-built guard, and the grid shows the hole.
> *(Instance: a 2-client × 3-layer grid where the client↔backend integration cell is ⚠️ "contract
> test only, no hermetic client↔real-backend layer" — a real gap surfaced as a cell.)*

---

## Section C — KLIK INSTANCE: align the gate + SKILL Klik facts to the index doc

### C1 — `production-rules-checker/references/full_rules.md` Rule 13 (rewrite stale facts)
- Sources line: drop the 错误码/分层 wiki framing that asserts 2-repo; keep the index doc as truth.
- "three layers across **two repos**" → "a **monorepo** (`Klik/`: `KK_*` modules + `db/` + `deploy/`),
  with infrastructure/observability/logging/integrations split into satellite repos."
- Migration: `Alembic` / `klik-infra` / "direct port 5432" → **`golang-migrate`, SQL files in
  `db/migrations/`**, DB URL from `config/secrets/database.yaml → postgresql.dev_url` (**PgBouncer**);
  `db/migrations/` and `Scripts/sql_lint/schema_columns.yaml` committed together.
- Keep the stable invariants verbatim: no raw DDL in app code; services via systemd
  (`deploy/services/<svc>.env` + `install-systemd.sh`), never `restart_*.sh`/watchdog; app code
  knows only a connection address, no embedded DB password/host-version.

### C2 — `full_rules.md` Rule 10 (logger import)
- `from KK_common.logger import LogManager` / `LogManager.setup_logging(...)`
  → `from KK_logger import get_logger` / `logger = get_logger(__name__)`.
- Add one line: `KK_logger` is its own repo (ECS format, **zero `KK_common` dependency**); `print()`
  in ship-path code is forbidden.

### C3 — `production-rules-checker/rules/klik.yaml` `NO_SCHEMA_DDL_IN_APP` (messages only; regex unchanged)
- All 3 messages: "DB schema changes go through Alembic in klik-infra (direct port 5432)"
  → "DB schema changes go through the migration system in `db/migrations/` (golang-migrate)".
- `exclude_files`: keep `migrations/`; the `alembic/` and `klik-infra` excludes are now dead but are
  pre-existing — **leave them, note in issue** (removing them is unrelated cleanup, not this change).

### C4 — `klik.yaml` NEW rule `LOGGER_USAGE` (the "enforced lint" the owner approved)
```yaml
  LOGGER_USAGE:
    file_types: [.py]
    exclude_files: [test_, _test.py, tests/, conftest.py, scripts/, __main__.py]
    patterns:
    - pattern: \bfrom\s+KK_common\.logger\s+import\b
      message: KK_common.logger is gone — klik-logger is its own repo; use `from KK_logger import get_logger`
    - pattern: \bLogManager\.setup_logging\s*\(
      message: LogManager.setup_logging is the pre-split logger — use `get_logger(__name__)` from KK_logger
    - pattern: (?<![\w.])print\s*\(
      message: print() in ship-path code — use the structured logger (get_logger from KK_logger)
```
- **No catalog entry required** (verified: forbidden-pattern rules load from `klik.yaml`
  independently; only *presence* guards go through `required_guards`/catalog). This is a
  package-move alignment, not a logged incident.

### C5 — `~/.claude/commands/production-rules-checker.md` (mirror C1–C4)
- Step 4 "Service & infrastructure topology": Alembic/klik-infra/5432 → golang-migrate/`db/migrations`/PgBouncer; monorepo framing.
- Rules-Reference quick summary: Rule 10 → `KK_logger`; Rule 13 text → monorepo + golang-migrate; add `LOGGER_USAGE` to the list.

### C6 — `no-new-bugs/SKILL.md` "CONCRETE FEEDBACK LOOPS — Klik" (align stale instance facts)
- Any `KK_common/logger` mention → `KK_logger`.
- Migration/`klik-infra` references → monorepo + `db/migrations`.
- The `docker/infra/init/…` schema path is **ambiguous** vs the layering doc's `klik-infra/init/` —
  do **not** guess; leave as-is and flag in the issue (finding, not fix).

---

## Section L — LARK SOURCE DOC: fix the 2 stale refs in `002 · 测试规范` (owner-authorized)

In-place edits to wiki `MH4AwL4L0iB3RdkTehycibRqn7c` via `lark-cli docs +update --api-version v2`:
- **L1:** "后端 `KK_common/logger`" → "后端 `KK_logger`(`get_logger`)". (definitive)
- **L2:** the "001 · 错误码注册 / 错误码 Base" reference → point at the real **错误码注册表 Base**
  (`I7XqwORteiMUdyk4DtJcBwWrntg`), dropping the non-existent "001 ·" number.
- **Leave** the `docker/infra/init/` path (ambiguous → issue only).
- Edit via precise `str_replace` (XML, `--doc-format xml`), not a rewrite — surgical, minimal diff to the shared doc.

---

## Section D — One consolidated GitHub issue → `minervacap2022/Klik`

Via `file-github-issue`. Title: **"Dev-convention docs out of sync — migration tool, repo topology,
logger import (+ numbering / registry hygiene)"**. Body = findings A–F as a table, each with the doc
link and the two contradicting values, stating which side was treated as truth (index doc, per owner
ruling) so the gate change is traceable. Notes the residual `docker/infra/init` vs `klik-infra/init`
path ambiguity and the `alembic/` dead exclude.

---

## Section E — Separate isolated commit: repair the broken foreign `catalog.yaml`

**Pre-existing foreign WIP**, not mine (mtimes Jun 4/8). It reformatted the catalog (HEAD nests
under `bugs:`, worktree flattened) **and added entries** (55→68), but **20/68 entries are missing
required fields** (`lint`/`chaos`/`observable_signal`) → the loader's 8 invariant tests go red →
`/production-rules-checker` emits `CATALOG_LOAD_FAILED` for every project.

- **Commit ordering:** Sections A–C + L land first (my surgical work, green). **Then** a *second,
  isolated* commit fills the 20 missing fields so the loader passes again. Per owner's "fix it as a
  separate commit."
- **Verify after:** `cd bug-regression-catalog && python3 scripts/test_load_catalog.py` green; the
  chaos guard `catalog_no_lying_guards.sh` green.
- **The 20 entries** get correct `observable_signal`/`lint`/`chaos` derived from each entry's
  existing description (where a real guard/grep exists, cite it; where none, `chaos: null` +
  an honest `observable_signal`, per the catalog's own schema rules — never a lying guard).

## Files touched — and explicitly NOT touched

**Commit 1 (alignment):** `no-new-bugs/SKILL.md`, `no-new-bugs/references/sector-map.md`,
`production-rules-checker/references/full_rules.md`, `production-rules-checker/rules/klik.yaml`,
`~/.claude/commands/production-rules-checker.md` (outside repo — separate concern, committed nowhere;
it's a user dotfile). Lark doc `MH4Aw…` edited in-place (not a git file).

**Commit 2 (catalog repair):** `bug-regression-catalog/catalog.yaml` only.

**NEVER touched (foreign WIP):** `sector_map/profiles/klik.json`, `sector_map/server.py`. The
`alembic/` dead exclude in klik.yaml — left, flagged.

## Verification plan

1. `python3 production-rules-checker/scripts/validate_production_rules.py --project klik --help` loads klik.yaml (incl. new `LOGGER_USAGE`) without YAML error.
2. Hand-craft a fixture `.py` with `from KK_common.logger import LogManager` and `print(` → validator flags both; a `tests/` file with the same → not flagged (exclude works).
3. `cd bug-regression-catalog && python3 scripts/test_load_catalog.py` green after Commit 2.
4. `sector_map` engine/CLI tests still green (untouched, but the global self-CI must stay green): `cd sector_map && python3 test_extract.py && python3 test_cli.py`.
5. Lark doc: re-fetch `MH4Aw…`, confirm `KK_logger` present and `KK_common/logger` gone; the 错误码注册表 link resolves.
6. GH issue created, URL captured.
