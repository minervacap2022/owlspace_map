---
name: no-new-bugs
description: >-
  Prevents introducing new bugs and regressions whenever you change code. Fuses
  the whole anti-regression discipline into one spine: know-before-you-code
  (investigate + spec-driven-development), feedback-loop-first (a failing test or
  runnable repro BEFORE the change), surgical change against a single source of
  truth, clean-slate verification in the REAL target environment (e2e + the 6-rung
  ladder), and guard-against-recurrence (turn prose-landmines into checks, catalog
  the bug, wire CODEOWNERS + scheduled tests). Built on one opinionated core —
  couple MAXIMALLY to shared TYPED/TESTED CONTRACTS, single source of truth, the
  enemy is duplication-drift, depend on contracts not guts. Reach for it at the
  START of and THROUGHOUT any feature, fix, or refactor — and before ever saying
  "done / works / fixed".
---

# No New Bugs

The dominant failure mode of fast code-change is **re-introducing bugs**: a fix
reveals the next bug, an invariant written only in prose gets re-violated, a green
test was lying, a thing that "works" only works on the tree/machine/process you are
holding. This skill is the floor that stops that. It is structural, not heroic — you
do not prevent regressions by adding more reviewers; you shape the change so its
blast radius is **small, visible, and caught at change-time**.

**This is a GLOBAL protocol — every project, every language, every future change.** The
principles here are universal; the concrete examples (drawn from one project, Klik) only
*illustrate* them — substitute your stack's equivalents (`./gradlew` → your build;
`klik-deploy-parity` → your deploy-parity check; `@Serializable`/Pydantic → your schema type).
The protocol has two arms: this **discipline** (how you change code) and its **tooling** — the
*sector map*, a live per-sector view of the seven know-before-you-code dimensions, instantiable
in any repo (see [`references/sector-map.md`](references/sector-map.md); Klik is instance #1).
Goal for every future change: ship **bugless** — or, honestly, force any bug to defeat a
*visible, enforced* signal instead of slipping past an *invisible* one.

---

## PRINCIPLE 0 — Couple to ONE source of truth; the enemy is duplication-drift

This is the opinionated core, and it is the **opposite** of the textbook "decouple
everything" reflex. **Do not preach generic decoupling — anywhere.**

A bug is born the moment the *same fact* — a validation rule, a schema, a constant,
a behavior — exists in two places. Now every change is a manual join across N copies:
fix one, forget the other four, ship a bug. "Loose coupling" by *copying* the fact
into each module hasn't removed the dependency; it has removed the **compiler's
knowledge** of it — strictly worse. You still must "change one, then change all the
others," only now nothing tells you the others exist.

So the rule inverts:

1. **One fact, one home.** Every rule/schema/constant/behavior has exactly **one
   canonical definition**; everyone who needs it depends on that one. Change it once →
   it propagates everywhere. This is DRY, and it is **maximal coupling on purpose**.
2. **If a fact lives in two places, that IS the bug — delete one.** Don't reconcile
   copies; collapse them. Duplication is the defect; the fix is unification, not sync.
3. **Make heavy coupling safe with a typed, tested contract.** The blast-radius fear
   ("if everyone depends on it, one change breaks everyone") is answered *without*
   decoupling: the shared thing is a **typed/tested interface**, so a breaking change
   **fails loud in every consumer at change-time** — compile error, red test, not a
   silent runtime surprise three weeks later. That turns the dependency graph into an
   **early-warning system**. That is the feature, not the liability.
4. **The discriminator — "contract or guts?"** The only coupling worth fearing is
   coupling to **internals**: private state, side-effects, call-order, timing,
   undocumented behavior. Those are invisible to types and tests, so depending on them
   is the true domino collapse — change a private detail, break a distant caller,
   nothing warns you. Before depending on anything, ask: *"a stated contract, or
   someone's guts?"* Couple freely to **contracts**. Never couple to **guts**.
5. **Partition along the contract seams — this is DB normal forms.** Deciding *where
   to cut* (what becomes its own table/module/service, what narrow key joins them) is
   the design act that makes "one fact, one home" achievable. Normalize = each fact
   stored **once**, referenced by a narrow key, joined on that key. Cut badly and you
   manufacture the duplication you then can't avoid; cut along the contracts and every
   fact lands in exactly one partition.

**One line:** *Couple everything to one canonical, typed, tested definition; duplicate
nothing; depend on contracts, never on guts.*

Proof from our own bugs:
- **Under-coupling →** `subscription_api` crash-loop (BUG-2026-05-31-G): launcher didn't
  source `KK_common/scripts/common.sh`+`setup_paths`, so `${KK_SUBSCRIPTION_PORT}` was
  unset → `/health` 500 → probe kills it → flap. A missing env it silently depended on.
- **Duplication-drift →** a leftover `kk-suggest.service` ran the *same*
  `uvicorn KK_suggest.suggest_api --port 8342` as the new `klik@suggest_api`; the two
  fought over 8342 AND double-fired rules (a real data bug). Two copies of one fact.
- **Drift at repo scope →** Klik_one ↔ Klik_newandroid are sibling forks, not mirrors;
  every invariant must be enforced **twice** or it drifts.

---

## THE CHANGE LOOP (the spine)

Run these five steps in order, every feature/fix/refactor. Each names the deeper skill.

### (1) Know-before-you-code  → `investigate`, `agent-skills:spec-driven-development`, `brainstorming`
State assumptions explicitly ("I'm assuming X, Y, Z — correct me or I proceed"); silently
filling ambiguous requirements is the most dangerous failure. If multiple interpretations
exist, surface them. Reframe vague asks into a **measurable** done-criterion ("faster" →
"LCP < 2.5s on 4G"). For a bug, this is the Iron Law: **no fix without a confirmed root
cause** — and if each fix reveals a new break, you are at the wrong layer (the 7-bug klik
chain was the price of skipping this, found one TestFlight build at a time).

**Inputs you must know for the partition you are about to touch:**
- **Schema** — its data shapes + invariants. *Source:* Kotlin `@Serializable` / `data
  class` DTO; DB via `ssh gcp psql … \dt` + the migration files; API via the OpenAPI /
  contract doc.
- **The contract** — read the `interface` / `expect`-`actual` decl and its KDoc; for a
  service, the route signatures in its `*_api.py` plus the DTOs in `data/network/`.
- **Dependency graph** — who it depends on, and *critically* **who depends on it** = the
  real blast radius. `git grep`, import graph, `./gradlew :x:dependencies`.
- **The OWNER** — derive from git, don't build a system: `git log -- <file>` /
  `git blame -L <lines> <file>`. When you touch someone's code, consult them — the owner
  is the live oracle for the slice of the contract not yet captured by types or tests.
  This is CODEOWNERS-by-git: the **human** tier of single-source-of-truth (route the
  change through the one canonical authority on that partition).

**Those four are STRUCTURE — parseable from code, and the *cheap* half. Regressions live in
six dimensions a parser CANNOT see; know these too, or you will confidently break what you
can't see:**
- **Behavior** — invariants ("always/never" rules), real runtime data + edge cases
  (falsy-zero), concurrency/ordering, failure semantics (what throws vs. is silently
  swallowed). → the `encodeDefaults` 403; the VAD falsy-zero; the liquid-ancestor SIGSEGV.
- **Context** — env/config/secrets the sector resolves and how they differ dev→prod;
  deploy state vs. git; resource ownership (ports/files/singletons); infra/routing config.
  → `subscription_api` bare-env; server-on-wrong-branch; duplicate `kk-suggest` unit; the
  nginx avatar-proxy regex.
- **Boundaries** — parallel implementations that must stay in sync (forks, client↔server
  DTOs, iOS↔Android) and external-system contracts + their failure modes (DB, hardware,
  Brevo). → the two-fork drift; the unpowered mic rail.
- **Intent & History** — the *why* / ADR, past bugs here + why prior fixes failed (the
  catalog, `git log`), non-code constraints (BIPA, COPPA-13, `user_id` isolation, perf
  SLAs, the production rules), and the spec's "done". → re-introduced fixed bugs; the BIPA fix.
- **Change-safety** — true blast radius (runtime paths + cross-repo consumers + migrations),
  observability (how you'd KNOW it broke in prod).
- **Tests & Coverage** — which tests cover this (own + consumers'), coverage % + pass/fail,
  and especially the **uncovered surface** you're about to touch. A parser sees test *files*;
  it does NOT see what they *cover*, whether they *pass*, or the gap. Run the covering tests
  green *before* you touch anything; if the path is uncovered, write the test FIRST. → the
  missing/lying feedback loop behind the whole recurring-bug class; the ~5%-coverage areas.

Structure goes in the sector graph; these six mostly do NOT — anchor them as guards, the
parity gate, `CONTEXT.md` / ADRs, the catalog, and a coverage/test map, or the agent never sees them.

### (2) Feedback-loop-first  → `systematic-debugging`, `test-driven-development`
**Before changing code, establish a fast pass/fail signal — a failing test, a runnable
repro, or a guard.** Never edit blind and hope. This is THE skill; everything else is
mechanical once you have a fast/deterministic/agent-runnable loop. A 2s deterministic
loop beats a 30s flaky one.

- Try loop types in order: failing test → curl → CLI+fixture diff → headless browser →
  replay a captured trace → throwaway harness → fuzz → `git bisect` → differential →
  human-in-the-loop. If you genuinely cannot build a loop, **STOP and say so**.
- **RED first.** Feature: the test fails before the code exists. Bug: Prove-It — write a
  test that **reproduces the bug and fails** *before* fixing; passing then proves the fix
  AND guards regression. A test that passes on first run proves nothing.
- Generate **3–5 ranked falsifiable hypotheses** before testing any ("if X is the cause,
  changing Y kills it"); show the ranked list — domain knowledge re-ranks instantly. One
  variable per probe; tag every debug log `[DEBUG-a4f2]` so cleanup is one grep.
- For non-deterministic bugs, **raise the repro rate** (loop 100×, add stress/sleeps);
  50% is debuggable, 1% isn't.

### (3) Surgical change against the single source of truth  → Principle 0, `review`
Touch **only** what the task needs; every changed line traces directly to the request.
Change the **one** canonical definition — never add a second copy to "avoid touching" the
shared one (that is how duplication-drift starts).
- Don't "improve" adjacent code/comments/formatting. Don't refactor what isn't broken.
  Match existing style. Separate refactor commits from feature commits.
- Remove imports/vars/functions **your** change orphaned. Pre-existing dead code →
  mention, don't delete (ASK first).
- Prefer the minimum: 200 lines that should be 50 → rewrite. No speculative
  flexibility/config/error-handling for impossible scenarios.
- **Shrink the blast radius — decompose the God-file.** An oversized unit *is* a bug
  factory: `MainApp.kt` at 3,785 LOC was touched 61× and bred regressions because every
  change reached too far. When the partition you must touch is too big to reason about,
  split it along the contracts (step 1 / Principle 0 part 5) so each future change is
  scope-locked. Big-and-tangled is itself the defect.

### (4) Verify from a CLEAN slate in the REAL target env  → `e2e-test`, `klik-ios-e2e-test`, `full-stack-test`, the ladder below
"Works" means reproducible **from a fresh `git clone` + clean build + clean-environment
run** — *not* from the state you are holding. Local-green is rung 1 of 6; climb the ladder
(next section). "Proven end-to-end" means **every entry path**, not the happy one — assert
on observable output (return value, HTTP status, file on disk, rendered result), never on
"it ran" or a count. For THIS repo the clean run is non-trivial: rung 1's `git worktree`
command → `./gradlew :samples:composeApp:linkDebugFrameworkIosSimulatorArm64` →
`xcodebuild` → `simctl install/launch` (see CLAUDE.md Build Commands). Use
`klik-ios-e2e-test` (iOS↔backend) or `full-stack-test` (3+ services).

### (5) Guard against recurrence  → `/production-rules-checker`, `production-code-audit`, `review`
A fix is not done when it's green; it's done when it **can't silently come back**, and the
window matters: a bug caught at change-time costs ~nothing, the same bug caught by a human
on a TestFlight build days later is the expensive failure mode. Shorten the detection
latency to pre-merge.
- **Turn the prose-landmine into a CHECK.** When a bug class recurs, or a doc says
  "always/never X", add a guard/test that fails loudly. Universal starter:
  `~/.claude/lib/guards/repo-guards.sh` — the **script** (copy into the repo's `scripts/`,
  add project-specific checks, wire into CI), *not* the `repo-guards` skill. Klik example:
  `k1-guards.sh` turns "no Material3 in `ui/klikone/`", "`k1Clickable` not raw
  `.clickable`", and the `encodeDefaults=false` 403 landmine (`age_confirmed_over_13`
  carries no default) into a blocking grep check.
- **Catalog the bug** in `~/.claude/skills/bug-regression-catalog/catalog.yaml`: `id` /
  `user_visible_symptom` / `lint` (regex rule) / `chaos` (runner or `null`) /
  `observable_signal` (the grep/curl that tells you in prod whether the fix holds).
  Removing an entry requires a note on what observability replaced it.
- **Wire CODEOWNERS + a scheduled run.** Put it at `Klik_one/.github/CODEOWNERS`, e.g.
  `ui/klikone/  @owner` — note the `liquid/.github` tree is dormant; root `.github` is
  the live one. Core logic gets unit tests that run on a **schedule**: add
  `on: schedule: - cron:` to a workflow under `Klik_one/.github/workflows/` (copy the
  shape of `k1-guards.yml`). **Old tests are the trip-wire** — new changes continuously
  monitor old behavior, so the day a fresh edit silently breaks settled behavior, CI goes
  red. A test that doesn't *run* isn't protection. And a feedback loop that isn't
  committed and wired into CI is **not a feedback loop** — the prevention system itself
  once fell to this meta-bug (authored, never committed: BUG-2026-05-31-A). This standing,
  self-running alarm is exactly what makes Principle 0's aggressive coupling safe.

*(Reaching for `production-code-audit`: verify every auto-fix — it violates surgical-diff
by default.)*

---

## THE VERIFICATION LADDER (cheapest → strongest; each rung names a real bug it catches)

1. **FRESH CLONE / WORKTREE** — build + run from scratch, **never your working tree**.
   *Catches:* uncommitted files, "works only on my dirty tree."
   ```bash
   git worktree add /tmp/verify-XYZ HEAD && cd /tmp/verify-XYZ && <clean build> && <run>
   ```
2. **CI = A FREE FOREIGN MACHINE** — wire CI on every push and **watch it go green**.
   Different machine/region/clean checkout. *Catches:* machine/region-specific assumptions
   (hardcoded paths, regional mirrors). CI's whole value is the fresh checkout that exposes
   every implicit local assumption — that is why you watch it go green, not why you skip it.
3. **PIN + DECLARE THE ENV** — tool versions (`toolchain`/`.tool-versions`/Docker), deps in
   a **lockfile**, ZERO machine-specific paths/mirrors in the repo (those live in
   `~/.gradle` etc.). Makes "their env" == "my env". *Catches:* the absolute
   `org.gradle.java.home` pin, the region mirror ahead of Central.
4. **TEST THE ACTUAL TARGET ENV** — run against the real deploy target (systemd/prod), not
   a local proxy. *Catches:* env-divergence (worked on `nohup`, died on systemd).
5. **SIMULATE THE TARGET'S CONSTRAINTS** when you can't get the env — strip local
   conveniences: bare env vars, target's tool versions, no regional mirror. *Catches:*
   prod-only paths.
6. **STANDING PARITY CHECK** — assert "running reality == declared model" on a schedule:
   `/opt/Klik/deploy/scripts/klik-deploy-parity.sh` (server-side, `ssh gcp`; scheduled by
   `klik-parity.service` + `klik-parity.timer`; READ-ONLY — it reports, never restarts).
   *Catches:* drift after the fact — the one class unit tests structurally cannot see,
   because they run from the same local state whose divergence IS the bug.

**Can't answer yes to rungs 1–4 → you verified "works on my side," not "works elsewhere."**

---

## THE ANTI-REGRESSION RULES (the ones not already above)

The change loop and ladder cover feedback-loop-first, confidence=coverage, no-false-green,
trace-before-patch, invariants→checks, and clean-slate. These three are the rest:

- **Surface foreign state** — `git status` before editing; never bundle, "fix", or commit
  pre-existing uncommitted changes you didn't make. Call them out so the human stays in
  control of their own diff.
- **Don't auto-fix what you can't verify** — if a change alters behavior you can't
  build/run/test here (firmware, native, prod-only), **propose** it, don't ship it blind.
  Over-correction is itself a bug source.
- **On migration/replacement, reap the old — disabled ≠ gone** — remove what you supersede
  AND the state that escaped (running children of a stopped service, duplicate units,
  machine-specific values in shared config, un-reaped cgroups). Installed-alongside = two
  things fighting over one port/file; the bug looks new but is old state never cleaned up.

On false-green specifically (the worst sub-cause), three real traps: loadtest fixtures fed
**silent audio**; `full-stack-test` asserted session **count** not transcript **content**;
a `MagicMock` auto-fabricated `cumulative_timestamp_ms` so prod 500'd while CI stayed
green. Mock only true external boundaries, never the system under test, and assert on
observable output.

---

## WHEN TO REACH FOR THE DEEPER SKILL

| Situation | Reach for |
|---|---|
| Vague request; need a precise, testable, owned spec before any code | `agent-skills:spec-driven-development` (assumptions-surfacing: `brainstorming`) |
| A bug with no confirmed root cause (whack-a-mole risk) | `investigate` |
| Any bug/test-fail/perf-regression — build the loop, rank hypotheses, fix root, lock with a correct-seam test | `systematic-debugging` (absorbs `diagnose`, `debugging-strategies`) |
| Writing the feature/fix test-first (RED→GREEN→refactor, Prove-It) | `test-driven-development` |
| Verify the change end-to-end in the real target, from clean | `e2e-test`, `klik-ios-e2e-test`, `full-stack-test` |
| Klik production-rules gate (no hardcode/fallback/mock/backward-compat/overengineering, no silent catch) | `/production-rules-checker` (slash-command; runs the Python validator) |
| Whole-codebase security/perf/architecture deep-scan (SQLi, secrets, N+1, god classes) — **verify each auto-fix, it's aggressive** | `production-code-audit` |
| Pre-landing structural review (scope-drift, trust boundaries, plan-completion honesty) against `git merge-base`, not raw HEAD | `review` |
| Land pipeline (tests, coverage gate, bump, PR) — re-runs the WHOLE checklist every time | `ship` |

---

## CODE IS CRAFT, NOT A CHECKLIST

These rules are the **floor**, made mechanical precisely so human attention is freed for
what can't be mechanized: taste and judgment about how to factor a problem, where to draw
a boundary, what the right contract even *is*. **The discipline is the floor; judgment is
the building.**
