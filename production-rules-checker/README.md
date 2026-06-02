# production-rules-checker — the KLIK instance

This is **Klik's** instance of a per-project production-rules gate, kept here as the
reference implementation. **It is not a global component** — don't read it as "this whole
repo is Klik tooling." The global, reusable system lives in
[`../no-new-bugs`](../no-new-bugs) and [`../bug-regression-catalog`](../bug-regression-catalog).

## What's global vs Klik-specific here

| | |
|---|---|
| **Global / reusable** | The validator **engine** (`scripts/validate_production_rules.py`) and its `--project <name>` filter over the shared `../bug-regression-catalog`. The catalog, the loader, and the project isolation are project-agnostic. |
| **Klik-specific** | `references/full_rules.md` and the built-in `RULES` (KLIK 5-char error codes + wire format, `KK_common/logger`, klik-infra/Alembic on port 5432, the three KLIK Feishu specs). These are *rule text for one project*, not the framework. |

## How another project gets its own gate

Same engine, shared catalog, your own rules:

```bash
# Owl's gate, say — only Owl's catalog lints load; Klik/EVE never bleed in:
validate_production_rules.py --project owl <files...>
```

Then supply your project's own rules reference (the analogue of `full_rules.md`). The
catalog `--project` mechanism guarantees one project's lint can never fire on another's
file. Only the rule text is ever per-project.
