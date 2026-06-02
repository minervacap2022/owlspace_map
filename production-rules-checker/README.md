# production-rules-checker — generic engine + per-project rule data

A **project-agnostic** production-rules gate. The engine ships **zero** project
knowledge; every rule is data, loaded per `--project`. Klik is just the first
project with a rules file here.

## Layout

| Path | What | Project-specific? |
|---|---|---|
| `scripts/validate_production_rules.py` | The **engine** — pure mechanism: file selection, glob/exclude matching, line scanning, the catalog `--project` filter, fail-loud on a malformed catalog. Contains no rule text and no project name. | **No — global.** |
| `rules/klik.yaml` | **Klik's** rules as data: patterns, `file_types`, `exclude_files`, `check_comments`, and `global_excludes`. | Yes (Klik). |
| `references/full_rules.md` | Klik's human-readable rules narrative + sources of truth. | Yes (Klik). |

The engine also merges regression lints from the shared
[`../bug-regression-catalog`](../bug-regression-catalog), filtered by the same `--project`.

## Run it

```bash
# Klik gate — loads rules/klik.yaml + klik catalog lints only:
validate_production_rules.py --project klik <files...>
```

## Add your own project (no engine change)

1. Drop a `rules/<project>.yaml` next to `rules/klik.yaml`:
   ```yaml
   global_excludes: [ ... ]      # files to never scan (your docs/fixtures)
   rules:
     YOUR_RULE_NAME:
       file_types: [".py"]
       exclude_files: ["tests/"]
       check_comments: false      # true only if the rule should match comment lines
       patterns:
         - { pattern: 'your-regex', message: 'why it's a violation' }
   ```
2. Run `validate_production_rules.py --project <project> <files...>`.

That's it — the engine loads your rules + your catalog lints, and the `--project`
filter guarantees another project's rule can never fire on your file. Only the rule
**data** is ever per-project; the engine is shared by everyone.
