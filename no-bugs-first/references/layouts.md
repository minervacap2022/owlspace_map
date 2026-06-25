# Concrete layouts per stack

Principle 0 made physical: inner layers expose **contracts**, outer layers depend **inward only**,
every fact has **one home**. The directory rule is grep-enforceable — that's why we pick layered
layouts. Each tree below maps 1:1 to `.sectormap.json` sectors.

---

## Backend — DDD (reference impl: KK_auth on gcp-root `/opt/Klik/KK_auth`)

```
src/
├── <context>/                 # one bounded context per business capability (auth, billing…)
│   ├── domain/                # PURE: @dataclass / types, invariants, repository INTERFACES.
│   │   │                      #   zero framework imports (no FastAPI/SQLAlchemy/bun:sqlite).
│   │   ├── <aggregate>.py     #   the aggregate root + value objects
│   │   ├── events.py          #   domain events (other contexts subscribe; no direct calls)
│   │   └── repository.py      #   IxxxRepository abstract interface (the contract)
│   ├── application/           # Command + Handler. Depends on domain INTERFACES, not impls.
│   │   └── <use_case>.py      #   one file per use case (register, login, …)
│   └── infrastructure/        # the ONLY place ORM / external SDKs / Redis appear
│       ├── <x>_repo.py        #   concrete IxxxRepository (SQLAlchemy/Drizzle/…)
│       └── <x>_service.py     #   token service, email service (tech, behind an interface)
├── interfaces/ (or routers/)  # thin HTTP layer: param-map → Command → Handler. NO business logic.
└── shared/                    # cross-context contracts ONLY (never business logic)
```

Sectors → `[{id:"<context>/domain"},{id:"<context>/application"},{id:"<context>/infrastructure"},{id:"interfaces"}]`
(or flatten to `domain/application/infrastructure/routers` for a single-context service).

Guard checks for `repo-guards.sh`:
- `domain/` must not import the web framework, ORM, or Redis (grep the layer dir).
- `application/` must not import `infrastructure/` concretely (depend on interfaces).
- no `getenv(…, default)` / `process.env.X ?? "…"` anywhere (fail-fast, no-fallback).
- every service's app registers the shared error handler (enumerate-and-assert guard).

Reference for the prose doctrine: KK_auth `CLAUDE.md` + `DDD_DESIGN.md`.

---

## Frontend — feature-sliced (React / Electron / KMP-Compose)

```
src/
├── shared/                    # the ONE home for cross-cutting facts
│   ├── contracts/             #   client↔server DTOs — ONE typed copy (never duplicated per call site)
│   ├── api/                   #   the ONE configured client (base URL, auth header) — not re-created per feature
│   └── ui/ lib/ config/       #   design tokens, pure helpers, typed env
├── features/<feature>/        # vertical slice; a feature owns its model+ui+api, imports only shared/
│   ├── model/                 #   state, view-models, use-cases (pure, testable)
│   ├── ui/                    #   components for this feature
│   └── api/                   #   feature-specific calls THROUGH shared/api (not a second client)
└── app/                       # composition root: routing, providers, wiring features together
```

Rules:
- A feature imports `shared/` and its own files — **never another feature's internals** (that's
  guts-coupling; route through `shared/` contracts). Grep-enforced.
- DTOs crossing client↔server are defined **once** in `shared/contracts` and imported by both
  sides; if there's a server repo, the contract is generated from / shared with it — never a
  hand-kept second copy (duplication-drift → the silent wire mismatch → 403).
- Required wire fields carry **no serialization default** (the encodeDefaults/encodeDefaults=false
  landmine): a contract test asserts they stay on the wire.

Sectors → one per `features/<x>` + `shared` + `app`. Mirror the klik.json `behavior` array for
design-token / contract / platform invariants.

KMP specifics: `expect`/`actual` pairs are a dimension-#4 boundary — declare them in
`boundaries_by_sector`. A sibling platform fork (iOS↔Android) means every invariant is enforced
**twice or it drifts** — note it in `boundaries_global`.

---

## Picking the sector boundary

A sector = one thing you reason about at once. Too coarse (whole `src` = 1 sector) hides blast
radius; too fine (every file) is noise. Layer-level (backend) or feature-level (frontend) is the
sweet spot. When a would-be sector is a god-file too big to hold in context, that's the signal to
split it along its contracts FIRST (step 2/3), then it becomes its own clean sector.
