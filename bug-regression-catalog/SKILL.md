---
name: bug-regression-catalog
description: Single source of truth for every production bug shipped across all projects. The validator (the production-rules gate), the chaos phases of `/full-stack-test` and a client↔backend e2e test, and the SessionEnd hook all read from this catalog. Adding a bug means appending ONE entry to catalog.yaml; nothing is duplicated across tools. Use when a new bug is found and fixed, or when you need to verify regression coverage.
---

# Bug Regression Catalog

One file. Three consumers. Zero duplication.

## The architecture

```
~/.claude/skills/bug-regression-catalog/
├── catalog.yaml                          ← single source of truth
├── scripts/
│   ├── load_catalog.py                   ← shared loader
│   ├── emit_lint_rules.py                ← consumed by validate_production_rules.py
│   ├── run_chaos_phase.sh                ← consumed by /full-stack-test phase_21
│   │                                       and a client↔backend e2e test
│   └── chaos/<bug-id>.sh                 ← one runner per bug with `chaos.runner` set
└── SKILL.md                              ← this file
```

### Consumers

| Tool | How it consumes the catalog |
|------|-----------------------------|
| `/production-rules-checker` | `validate_production_rules.py` imports `emit_lint_rules.py` and merges catalog patterns into its `RULES` dict. |
| `/full-stack-test` | `phase_21_regression_catalog` invokes `scripts/run_chaos_phase.sh`, which iterates catalog entries and runs each `chaos.runner` against the live stack. |
| a client↔backend e2e test | invokes the same `scripts/run_chaos_phase.sh` with an `--edge` filter (public-edge-visible bugs only). |
| `SessionEnd` hook | When a commit message contains `fix` plus a bug keyword, reminds Claude to append a catalog entry. |

## Adding a bug

1. Identify the bug class. Is it:
   - **Static** — code shape that can be caught with regex? → fill `lint:` block, set `chaos.runner: null`.
   - **Behavioral** — only manifests when something upstream fails? → write a chaos runner under `scripts/chaos/<id>.sh`.
   - **Both** (most cases) — fill both.

2. **Mint a collision-free id** — `python3 scripts/new_bug_id.py` (prints
   `BUG-<date>-<rand>`). It's **random, not sequential** — never hand-pick the
   "next letter": sequential ids collide when agents append concurrently (both
   read the same catalog and pick the same letter). Then append to `catalog.yaml`:
   ```yaml
   - id: BUG-YYYY-MM-DD-xxxxxx     # from scripts/new_bug_id.py — do not hand-pick
     title: One-line summary
     date: YYYY-MM-DD
     surface: backend | ios | frontend
     source_files: [list of files where the bug lived]
     user_visible_symptom: |
       What did the user see? (Multi-line ok.)
     lint:
       - rule: RULE_NAME_IN_CAPS
         pattern: 'regex'
         message: 'lint message — why this pattern is forbidden'
         file_types: [".py"]
         exclude_files: ["test/", "_test.py"]
     chaos:
       runner: chaos/<id>.sh    # or null if static-only
       description: What does the runner force, and what must hold true?
     observable_signal: |
       The grep / curl / SQL that tells you whether the guard is still
       working in production. This is what you check during incident
       response.
   ```

3. If you set a `chaos.runner`, write `scripts/chaos/<id>.sh`. The runner takes one arg, `--base-url`, and exits 0 on PASS, non-zero on FAIL. It must be idempotent — full-stack-test reruns it on every smoke.

4. Run `python3 scripts/emit_lint_rules.py --self-test` to verify the regex actually matches a pre-fix fixture.

5. Commit the catalog entry in the SAME PR as the bug fix. The validator blocks the commit if you fixed code under a `source_files:` path without updating the catalog.

## Removing a bug

Don't, unless an alternative observability path (alert, runtime check) has been verified in production for ≥ 30 days. Add a `superseded_by:` field explaining what replaced the entry. Silence is how the same shape gets re-debugged.

## Why one catalog instead of three configs

Because before this skill, the same bug knowledge lived in:
- Inline regex in `validate_production_rules.py`
- Phase 6/7 wiring inside `full-stack-test/run_all.sh`
- Assertions inside a client↔backend e2e test's flow script

Three places to update for one bug. So nobody updated all three. So regression coverage rotted.

One YAML, three readers. Update once.
