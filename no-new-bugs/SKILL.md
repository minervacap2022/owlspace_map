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

> **Step 0 — self-update (always run first).** Before doing anything else with
> this skill, run `bash "$(dirname "$0")/self_update.sh"` from this skill's
> directory — i.e. `bash <this-skill-dir>/self_update.sh`. It pulls the latest
> version of this skill from its GitHub origin when the checkout is clean and on
> the default branch (offline → it silently uses the local copy). If it reports
> new commits it could **not** auto-pull (dirty tree or a feature branch),
> surface that to the user and continue with the local copy. If it reports it
> **pulled** changes, re-read this SKILL.md before proceeding — you may be on an
> older version. This keeps the skill current everywhere it is installed, with
> zero local hooks or config.

The dominant failure mode of fast code-change is **re-introducing bugs**: a fix
reveals the next bug, an invariant written only in prose gets re-violated, a green
test was lying, a thing that "works" only works on the tree/machine/process you are
holding. This skill is the floor that stops that. It is structural, not heroic — you
do not prevent regressions by adding more reviewers; you shape the change so its
blast radius is **small, visible, and caught at change-time**.

**This is a GLOBAL protocol — every project, every language, every future change.** The
principles are universal and the worked examples below are deliberately **generic** —
substitute your stack's equivalents (your build tool, your schema type, your deploy-parity
check, your e2e harness). The protocol has two arms: this **discipline** (how you change
code) and its **tooling** — the *sector map*, a live per-sector view of the seven
know-before-you-code dimensions, instantiable in any repo (see
[`references/sector-map.md`](references/sector-map.md)). Goal for every future change: ship
**bugless** — or, honestly, force any bug to defeat a *visible, enforced* signal instead of
slipping past an *invisible* one.

> **Design-time companion: `no-bugs-first`.** This skill is the *change-time* floor (don't
> regress this edit). When the unit of work is a **whole repo** — starting a new service or
> refactoring/redesigning an existing one — reach for **`no-bugs-first`** instead: it applies
> this same doctrine at repo scale (impose the layered structure, lay the guard + `ci-success`
> spine, ship a validated `.sectormap.json` so the repo maps cleanly). Same doctrine, two entry
> points; that skill *invokes* these principles rather than copying them.

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
   someone's guts?"* Couple freely to **contracts**. Never couple to **guts**. A
   **layered** architecture (domain ← application ← infrastructure; resource-vs-ops;
   library-vs-consumer) is this rule made *physical*: inner layers expose contracts,
   outer layers depend inward only — so "depend on contracts, never on guts" becomes a
   *directory invariant* a guard can grep (the domain layer importing the web framework
   is a violation you can detect mechanically).
5. **Partition along the contract seams — this is DB normal forms.** Deciding *where
   to cut* (what becomes its own table/module/service, what narrow key joins them) is
   the design act that makes "one fact, one home" achievable. Normalize = each fact
   stored **once**, referenced by a narrow key, joined on that key. Cut badly and you
   manufacture the duplication you then can't avoid; cut along the contracts and every
   fact lands in exactly one partition.

**One line:** *Couple everything to one canonical, typed, tested definition; duplicate
nothing; depend on contracts, never on guts.*

Proof, in generic shapes you will recognize:
- **Under-coupling →** a service launcher didn't source its shared env-setup, so a
  required `${PORT}` it silently depended on was unset → `/health` 500 → the liveness
  probe kills it → crash-loop. A dependency that lived only in an assumption.
- **Duplication-drift →** a leftover service unit ran the *same* process on the *same*
  port as its replacement; the two fought over the port AND double-fired the work. Two
  copies of one fact.
- **Drift across parallel implementations →** a client↔server contract (a DTO) defined
  twice, once on each side, silently diverges; one shared, typed schema removes the
  second copy so a breaking change fails loud instead of drifting.
- **One name, one schema →** the same identifier carrying two shapes is duplication-drift
  at the data layer: one metric name emitted with two different label sets, or one DTO
  field serialized two ways on two code paths. One identifier must mean **one schema
  everywhere**, or every consumer joins across the variants by hand.

---

## THE CHANGE LOOP (the spine)

Run these five steps in order, every feature/fix/refactor. Each names the deeper skill.

### (1) Know-before-you-code  → `investigate`, `agent-skills:spec-driven-development`, `brainstorming`
State assumptions explicitly ("I'm assuming X, Y, Z — correct me or I proceed"); silently
filling ambiguous requirements is the most dangerous failure. If multiple interpretations
exist, surface them. Reframe vague asks into a **measurable** done-criterion ("faster" →
"LCP < 2.5s on 4G"). For a bug, this is the Iron Law: **no fix without a confirmed root
cause** — and if each fix reveals a new break, you are at the wrong layer (a multi-bug
whack-a-mole chain, discovered one release build at a time, is the price of skipping this).

**Inputs you must know for the partition you are about to touch:**
- **Schema** — its data shapes + invariants. *Source:* your language's schema type
  (a `@Serializable`/`data class` DTO, a Pydantic model, a struct + tags); the DB via
  `psql … \dt` + the migration files; the API via its OpenAPI / contract doc.
- **The contract** — read the `interface` / declaration and its doc comment; for a
  service, its route signatures plus the request/response DTOs.
- **Dependency graph** — who it depends on, and *critically* **who depends on it** = the
  real blast radius. `git grep`, the import graph, the build's dependency query
  (`./gradlew :x:dependencies`, `npm ls`, …).
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
  swallowed). → a serialization-default that silently drops a required field → 403; a
  falsy-zero treated as "absent" at a boundary; a library-misuse crash (SIGSEGV).
- **Context** — env/config/secrets the sector resolves and how they differ dev→prod;
  deploy state vs. git; resource ownership (ports/files/singletons); infra/routing config.
  → a bare-env launcher; a server running the wrong branch; a duplicate service unit; an
  nginx longest-prefix `location` regex preempting the route you expected.
- **Boundaries** — parallel implementations that must stay in sync (client↔server DTOs,
  a platform's `expect`/`actual` pair) and external-system contracts + their failure modes
  (DB, hardware, an email/SMS provider). → a client↔server DTO mismatch; an unpowered
  hardware rail returning garbage.
- **Intent & History** — the *why* / ADR, past bugs here + why prior fixes failed (the
  catalog, `git log`), non-code constraints (privacy law e.g. BIPA/COPPA-13, per-user
  data isolation, perf SLAs, the production rules), and the spec's "done". → a re-introduced
  fixed bug; a compliance fix that must not be undone.
- **Change-safety** — true blast radius (runtime paths + consumers + migrations),
  observability (how you'd KNOW it broke in prod).
- **Tests & Coverage** — which tests cover this (own + consumers'), coverage % + pass/fail,
  and especially the **uncovered surface** you're about to touch. A parser sees test *files*;
  it does NOT see what they *cover*, whether they *pass*, or the gap. Run the covering tests
  green *before* you touch anything; if the path is uncovered, write the test FIRST. → the
  missing/lying feedback loop behind a whole recurring-bug class; the low-coverage areas. A
  test is done when it is **captured**, not merely green: if the project ships per-test
  telemetry to a dashboard, confirm the run still emits it (a passing-but-invisible test is a
  blind spot). *KLIK instance:* the emitter→otel→ES→Grafana chain governed by
  `nexora-policy/policy/02-testing.md` (Test visibility); see `Klik:docs/testing/running-and-monitoring.md`.

Structure goes in the sector graph; these six mostly do NOT — anchor them as guards, a
deploy-parity gate, `CONTEXT.md` / ADRs, the catalog, and a coverage/test map, or the agent
never sees them.

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
  factory: a 3,785-LOC god-file touched 61× bred regressions because every change reached
  too far. When the partition you must touch is too big to reason about, split it along the
  contracts (step 1 / Principle 0 part 5) so each future change is scope-locked.
  Big-and-tangled is itself the defect.

### (4) Verify from a CLEAN slate in the REAL target env  → `e2e-test`, `full-stack-test`, the ladder below
"Works" means reproducible **from a fresh `git clone` + clean build + clean-environment
run** — *not* from the state you are holding. Local-green is rung 1 of 6; climb the ladder
(next section). "Proven end-to-end" means **every entry path**, not the happy one — assert
on observable output (return value, HTTP status, file on disk, rendered result), never on
"it ran" or a count. When a **structured** signal exists (a registered error code, a
correlation-id log line), assert on **it**, not just a coarse proxy like an HTTP status: a
test that asserts only `403` passes for the *wrong* 403; asserting the error code pins the
actual cause and is what lets a failure be traced by *code + log line* later. The clean run
is often multi-step (worktree → build → install → launch) — script it. Use an e2e harness
for client↔backend and a full-stack harness for 3+ services.

### (5) Guard against recurrence  → `repo-guards`, `production-code-audit`, `review` (+ your project's hard-rules gate)
A fix is not done when it's green; it's done when it **can't silently come back**, and the
window matters: a bug caught at change-time costs ~nothing, the same bug caught by a human
on a release build days later is the expensive failure mode. Shorten the detection
latency to pre-merge.

> **Generic principle (every project):** a project's coding rules have **one canonical home**
> (a policy doc / a guards script), and the rule is enforced by an **executable arm** that encodes
> it as a runnable check. Reference that home; never paraphrase a rule into a third copy
> (duplication-drift, Principle 0). When a rule changes, change the canonical home and its check
> **in the same change**. `repo-guards` (`~/.claude/lib/guards/repo-guards.sh`) is the
> stack-agnostic starter for this.
>
> *Instance #1 — KLIK:* the canonical home is `nexora-policy/policy/` (`policy/01` fail-fast,
> `policy/05` commit gates, `policy/07` service layout, `policy/08` skills-system); the executable
> arm is the **KLIK-only** `production-rules-checker` skill, which encodes them as categories
> (including the `policy/07` layering gates `DDD_DOMAIN_PURITY` / `DDD_APP_BOUNDARY` /
> `DB_ONLY_IN_REPOS` / `SERVICE_INSTRUMENTED` / `DEPLOY_PARITY`). On a non-KLIK repo, the *shape*
> is the same but the home and the gate are that project's own.
- **Keep the architecture map honest — a structural change updates the model in the SAME commit.**
  If the repo has a committed architecture profile (`.sectormap.json` feeding the sector/context
  map), a change that adds a module, moves a package, or creates a cross-context dependency must
  update the profile in the same commit and keep the map's findings at zero (no cycle, no stale
  declared edge, no fallback render). The profile and the code are one fact — letting them drift is
  the duplication-drift Principle 0 forbids. Generic rule in `nexora-policy/policy/09-map-hygiene.md`;
  the *KLIK instance* of the gate is `Scripts/check_map_hygiene.sh` in `ci-success`. Reach zero by
  honest bounded-context grouping, never by hiding a real cycle.
- **Turn the prose-landmine into a CHECK.** When a bug class recurs, or a doc says
  "always/never X", add a guard/test that fails loudly. Universal starter:
  `~/.claude/lib/guards/repo-guards.sh` — the **script** (copy into the repo's `scripts/`,
  add project-specific checks, wire into CI), *not* the `repo-guards` skill. Example: a
  guards script that turns "no legacy UI framework in the new design-system dir", "use the
  wrapper, not the raw API", and a serialization-default landmine (a required field must
  carry no default, or it's dropped on the wire → 403) into a blocking grep check.
- **Catalog the bug** in the shared bug catalog (`bug-regression-catalog/catalog.yaml`):
  `id` / `user_visible_symptom` / `lint` (regex rule) / `chaos` (runner or `null`) /
  `observable_signal` (the grep/curl that tells you in prod whether the fix holds).
  Removing an entry requires a note on what observability replaced it.
- **Wire CODEOWNERS + a scheduled run.** Put it at your repo's `.github/CODEOWNERS`, e.g.
  `src/feature/  @owner`. Core logic gets unit tests that run on a **schedule**: add
  `on: schedule: - cron:` to a workflow under `.github/workflows/`. **Old tests are the
  trip-wire** — new changes continuously monitor old behavior, so the day a fresh edit
  silently breaks settled behavior, CI goes red. A test that doesn't *run* isn't protection.
  And a feedback loop that isn't committed and wired into CI is **not a feedback loop** —
  the prevention system itself once fell to this meta-bug (a guard authored but never
  committed). This standing, self-running alarm is exactly what makes Principle 0's
  aggressive coupling safe.
- **Make "I did X everywhere" a verified invariant — not a claim.** When a fix means
  applying the same property to *every* member of a set (every service registers the shared
  handler, every route emits a coded error, every DTO field is wired onto the request), the
  regression is the *next* member added without it. Write a guard that **enumerates the set
  and asserts the property on each**, so a new member missing it fails loud — "all N wired"
  stops being a sentence you wrote once and becomes a check that re-proves itself on every
  change. *(Instance, illustration only: a test that discovers every web-app object at import
  and asserts each one installed the shared exception handler — a service created without it
  turns the suite red.)*

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
   When CI is genuinely unavailable (private repo, no paid runner), the floor is a
   **committed pre-push hook running the same suite** — slower, and skippable with
   `--no-verify`, but it keeps the loop *committed and runnable from a clean checkout*, which
   is what this rung is really about. An **uncommitted** local hook is not a feedback loop.
3. **PIN + DECLARE THE ENV** — tool versions (`toolchain`/`.tool-versions`/Docker), deps in
   a **lockfile**, ZERO machine-specific paths/mirrors in the repo (those live in the user's
   home config). Makes "their env" == "my env". *Catches:* an absolute toolchain-home pin, a
   regional package mirror ahead of the default registry.
4. **TEST THE ACTUAL TARGET ENV** — run against the real deploy target (the service
   manager / prod), not a local proxy. *Catches:* env-divergence (worked as a bare
   process, died under the service manager).
5. **SIMULATE THE TARGET'S CONSTRAINTS** when you can't get the env — strip local
   conveniences: bare env vars, target's tool versions, no regional mirror. *Catches:*
   prod-only paths.
6. **STANDING PARITY CHECK** — assert "running reality == declared model" on a schedule:
   a server-side deploy-parity check, scheduled by a timer, **READ-ONLY** (it reports, never
   restarts). *Catches:* drift after the fact — the one class unit tests structurally cannot
   see, because they run from the same local state whose divergence IS the bug.

**Can't answer yes to rungs 1–4 → you verified "works on my side," not "works elsewhere."**

---

## CONCRETE FEEDBACK LOOPS — Klik (instance #1)

Two professional, **hermetic** test layers exist (built 2026-06-03) — reach for these as the fast
pass/fail signal before touching the relevant code, and *extend* them rather than re-deriving:

- **Backend isolated-DB integration** — per-module `KK_*/tests/integration` (repo
  `minervacap2022/Klik`) run against ONE shared throwaway `pgvector/pgvector:pg16` container. The
  harness `Scripts/inttest/start-db.sh` bootstraps the *authoritative* schema
  (`db/migrations/000001_baseline.up.sql` + later migrations + `Scripts/inttest/seed.sql` reference
  data) and redirects the whole stack's `db_manager` via a **guarded `KLIK_TEST_DB_URL`** override in
  `KK_db/config.py` (the session guard in `KK_common/testing/fixtures/inttest_db.py` ABORTS unless it
  resolved to the container — these tests never touch prod). Clean slate per test. A module opts in
  with `pytest_plugins = ["KK_common.testing.fixtures.inttest_db"]`. Run:
  `eval "$(bash Scripts/inttest/start-db.sh)"; uv run pytest KK_*/tests/integration -m integration`
  (needs Docker). Cross-service contract tests (error envelope/registry/emitter) live in
  `KK_common/tests/contract` with `@pytest.mark.contract` (hermetic, no Docker).
- **Frontend client wire-contracts** — `BackendAuthApiContractTest` drives the real request DTOs
  through the real `encodeDefaults=false` Json via an injected fake transport, pinning the 403
  landmine (`age_confirmed_over_13` / `accept_biometric_consent` must stay on the `/register` wire).
  Runs on `iosSimulatorArm64Test` (Klik_one) and `testDebugUnitTest` (Klik_newandroid). The SAME
  guard lives on BOTH client forks — duplication-drift is the enemy (Principle 0). Seam: an
  injectable `BackendAuthApi` (transport + device getters, with production defaults).
- **Unit suites** + how to run each: project memory `project_test_loops`. Catalog id for the 403
  landmine: `BUG-2026-06-03-6f9f53`.
- **Enforcement is LOCAL** — no GitHub CI for the new integration tests (private repos, no paid
  plan): a **pre-push hook** runs the suite (`scripts/install-git-hooks.sh` in each repo). The
  backend uses a hook, NOT a server systemd timer.

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

On false-green specifically (the worst sub-cause), three real traps: a loadtest fed
**silent/empty input**; an e2e asserted a row **count** not the **content**; a mock
auto-fabricated a field the code read, so prod 500'd while CI stayed green. Mock only true
external boundaries, never the system under test, and assert on observable output. And
prefer an **in-memory implementation of your own port** (a real `InMemoryFooRepository`
satisfying the same interface the production code depends on) over a hand-set mock: it
exercises real logic and, because it implements the contract, **cannot drift** the way a
mock's fabricated return can — the third trap above is impossible when the test double is
bound by the same typed interface as the real one.

---

## WHEN TO REACH FOR THE DEEPER SKILL

| Situation | Reach for |
|---|---|
| Vague request; need a precise, testable, owned spec before any code | `agent-skills:spec-driven-development` (assumptions-surfacing: `brainstorming`) |
| A bug with no confirmed root cause (whack-a-mole risk) | `investigate` |
| Any bug/test-fail/perf-regression — build the loop, rank hypotheses, fix root, lock with a correct-seam test | `systematic-debugging` (absorbs `diagnose`, `debugging-strategies`) |
| Writing the feature/fix test-first (RED→GREEN→refactor, Prove-It) | `test-driven-development` |
| Verify the change end-to-end in the real target, from clean | `e2e-test`, `full-stack-test` |
| Turn a recurring invariant into a project-agnostic pre-merge guard wired into CI | `repo-guards` (`~/.claude/lib/guards/repo-guards.sh`; prove it BOTH directions — passes clean, fails on a planted violation) |
| Your project's hard-rules gate (no hardcode/fallback/mock/backward-compat/overengineering, no silent catch, layering) | the project's own validator. *KLIK-only instance:* `production-rules-checker` (`--staged`/`--full-scan`/`--category`/`--json`), the executable arm of `nexora-policy`. On other repos, use that repo's equivalent. |
| Whole-codebase security/perf/architecture deep-scan (SQLi, secrets, N+1, god classes) — **verify each auto-fix, it's aggressive** | `production-code-audit` |
| Pre-landing structural review (scope-drift, trust boundaries, plan-completion honesty) against `git merge-base`, not raw HEAD | `review` |
| Land pipeline (tests, coverage gate, bump, PR) — re-runs the WHOLE checklist every time | `ship` |

---

## CODE IS CRAFT, NOT A CHECKLIST

These rules are the **floor**, made mechanical precisely so human attention is freed for
what can't be mechanized: taste and judgment about how to factor a problem, where to draw
a boundary, what the right contract even *is*. **The discipline is the floor; judgment is
the building.**
