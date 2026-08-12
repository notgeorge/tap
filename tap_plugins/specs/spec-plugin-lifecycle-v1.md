# DRAFT — Plugin Load/Update Lifecycle v1 — Transactional, Reconciled Specification

> **Status: DRAFT for review (2026-08-11).** Successor to `spec-plugin-load-lifecycle-v0.md`,
> which defined the *load contract* (what a plugin declares + startup behavior) and explicitly
> deferred install, update, dependency orchestration, enablement state, and migration
> orchestration (`req-plugin-load-v0-nongoals`). This spec takes those on: the **transactional,
> race-free, extensible install/update orchestration** around plugin load. It is the direct
> response to the plugin-loading race (2026-08-11) and the "derive-the-same-fact-twice" audit.

## Philosophy

Loading or updating a plugin is a **multi-phase state transition** — install the package,
migrate its schema, register its types, seed its reference data, register its collectors, mount
its pages — and today that transition is an imperative sequence spread across more than one
process. That is a race generator: the migrate process and a sibling boot process independently
derived the plugin set and disagreed (`importlib.metadata`'s mtime cache), leaving a registered
type with no migrated table — fatal on a fresh database, invisible on a long-lived one. The
race-kill (TAP_PLUGINS authoritative, one resolver) removed that specific divergence; this spec
removes the **class** and makes the transition sound as moving parts multiply.

**Grid integrity is sacrosanct** (the standing operating principle): a plugin transition must
either complete coherently or halt loudly, and must NEVER leave the grid in a state where a
registered type lacks its table, a seed references an unmigrated model, or the runtime disagrees
with the schema. Coherence of the grid is the entire reason the system exists.

The design is drawn from convergent prior art (Odoo's single-cursor module load + `ir.module.module`
state registry; Django's single-`INSTALLED_APPS` discipline; Flyway/Rails' advisory-lock migration
serialization; Kubernetes' level-triggered reconciliation; Helm's ordered weighted phases;
PostgreSQL's transactional DDL and `EXTENSION` version model). The shape they all converge on:
**one authoritative desired state, one persisted actual state, one serialized writer, ordered
idempotent phases, wrapped in the transaction the database already gives us for free.**

## The three-state model (the core clarification)

The audit found that "the plugin set" was really three *distinct* concepts that had been
conflated and independently re-derived. This spec names them and keeps them separate:

| Concept | What it is | Where it lives | Authority for |
| --- | --- | --- | --- |
| **Desired state** | What the operator *requests* should run | the **boot profile** (`boot/*.boot.json`, a file) | the input to reconciliation — NOT "what's real" |
| **Persisted actual state** | What is *really* installed, at what version, with lifecycle history | a **DB registry table** (new) | the single source of truth for "what's installed"; the runtime derives from it |
| **Runtime-loaded state** | What *this process* loaded into `INSTALLED_APPS` | the Django app registry | this process's view; must be derived from persisted-actual, never re-discovered |

Desired + persisted-actual is exactly the desired-vs-observed split of the reconciliation model:
**reconcile drives `profile (desired) → DB registry (actual)`; every runtime process derives its
set from the DB registry, never from live discovery.** The homegrown in-process registries are
caches of "what loaded" — they grew to paper over the absence of a persisted-actual record.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | **Single authority per concept** | Desired (profile), actual (DB registry), runtime (app registry) — each derived one way, never re-implemented. |
| 2. | **Serialized, race-free transition** | One writer at a time (advisory lock); concurrent transitions block or loud-fail, never interleave. |
| 3. | **Transactional core** | The DB-resident phases (migrate + register + seed) commit or roll back as one unit — free on Postgres. |
| 4. | **Ordered, idempotent, extensible phases** | Phases declare order + are convergent ("ensure", not "do"); a new phase slots in without reintroducing races. |
| 5. | **Fail loud, no auto-rollback (v1)** | Any phase error halts with the phase named and the grid coherent; automated rollback of committed installs is a named non-goal. |
| 6. | **Persisted lifecycle history** | The DB registry records install/upgrade/version-flip/status over time — the plugin lifecycle is itself tracked. |

## Requirements (DRAFT — for review, RIDs provisional)

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-plugin-lifecycle-v1-registry | DB registry as persisted-actual authority | Proposed | New table: one row per plugin — slug, installed version, source, status, timestamps; the single source of truth for "what's installed". Written at successful transition, not from the profile. |
| req-plugin-lifecycle-v1-registry-history | Registry carries lifecycle history | Proposed | Version-flips/install/upgrade/status transitions are recorded over time (candidate: ride the grid's own history/provenance — a plugin-lifecycle record is arguably a first-class grid citizen). |
| req-plugin-lifecycle-v1-single-authority | One derivation of the runtime set | Proposed | The race-kill (`preboot.resolved_plugin_app_configs`, TAP_PLUGINS authoritative) is the v1 stepping-stone; the DB registry becomes the durable authority. Collapse remaining re-derivations (audit inventory). |
| req-plugin-lifecycle-v1-serialize | Advisory-lock serialization | Proposed | `pg_advisory_xact_lock` on a stable key (optionally namespaced by grid id) around the whole transition; concurrent transitions block or loud-fail (Flyway/Rails pattern). Not the Liquibase lock-table (stale-lock hazard). PgBouncer caveat: direct/session-pooled connection. |
| req-plugin-lifecycle-v1-transaction | Transactional DB-resident core | Proposed | migrate + register + seed run in one `transaction.atomic()` under the lock; Postgres DDL rolls back atomically. `CREATE INDEX CONCURRENTLY` (if any) stays in an `atomic=False` migration, outside the block. |
| req-plugin-lifecycle-v1-phases | Ordered idempotent phases | Proposed | `resolve/install → migrate → register types → seed → schedule collectors → mount pages`, each convergent ("ensure X"), declared order (Helm-weight style), phase N+1 gated on N observably complete. |
| req-plugin-lifecycle-v1-grid-invariant | Fail-closed grid-integrity check | Proposed | Before any grid mutation, assert every registered TAP-managed type has its backing table; abort with a legible "type X registered, table absent — schema/registry divergence" instead of a raw psycopg error. Mechanizes the sacrosanct principle. |
| req-plugin-lifecycle-v1-grid-tables-single-source | Collapse the two grid-table derivations | Satisfied | **Satisfied by PR #49; superseded by `req-grid-table-classification.sec` (tap_grid/specs/spec-grid-security.md, Implemented) — do not double-build.** Landed shape: a `GRID_TABLE_ROLE` classification declared on the models (`"domain"` once on `BaseModel`, inherited; `"spine"` only on Entity/EntityType), one derivation module `tap_grid/grid_tables.py` consumed by both `read_guard` and `search_role`, an `__init_subclass__` guard so a BaseModel subclass can never declare a role, a fail-closed core-only rule for explicit declarers (security Flaw on violation), and provision-time reconciliation against `pg_tables` (classified-but-absent tables loudly skipped, never a boot abort). The grant/guard consumer relationship (grant = guarded ∪ {tap_entity}) is pinned by test. |
| req-plugin-lifecycle-v1-external-boundary | Name the non-transactional seam | Proposed | The pip/filesystem install and external side effects (collector scheduling) sit OUTSIDE the DB transaction. Order them first + idempotent; document them as the phases a future rollback would need to compensate. |
| req-plugin-lifecycle-v1-profile-drift | Profile vs actual on long-lived instances | Proposed | **OPEN DESIGN QUESTION.** In-place upgrades advance the DB registry (actual) past the boot profile (desired). Define what is authoritative for "what should run" after drift: does the profile stay the desired-state input (operator re-issues it), does an in-place upgrade rewrite/annotate the profile, or does the registry become desired+actual? Reconciliation says desired drives, actual records — but the *source* of desired on a long-lived instance needs a decision. |
| req-plugin-lifecycle-v1-nongoals | v1 non-goals | Proposed | Automated rollback of committed installs / downgrade paths (Erlang-OTP compensation); Nix-style multi-generation time-travel; continuous background reconciliation (v1 reconciles on load/update/boot, not a watch loop); saga/2PC coordination. Deferred deliberately, not by oversight. |

## Prior-art basis (for the review discussion)

- **Odoo** — the closest analog (Python + ORM tables + seed data): single-cursor module install/upgrade
  where table-creation and type-registration happen in the same pass (cannot diverge); `ir.module.module`
  state table as the single "installed set"; DB-signaling to keep workers' registries coherent; a
  `reset_modules_state()` reconcile-repair. Confirms the DB-registry + single-transaction + reconcile shape.
- **PostgreSQL transactional DDL + Django migrations** — each migration is atomic on Postgres for free;
  the whole `migrate` run is NOT one transaction (Django #24535) and Django takes no cross-process lock —
  so whole-transition atomicity + serialization is what we add.
- **Flyway / Rails** — `pg_advisory_lock` around migration as the standard concurrent-runner guard;
  **Liquibase's lock-table is the anti-pattern** (stale lock on crash; advisory locks auto-release).
- **PostgreSQL `EXTENSION`** — the north-star model for "plugin schema as a versioned, transactional,
  upgradable unit": a manifest with `requires` ordering, versioned delta scripts, `ALTER EXTENSION … UPDATE`
  chaining, the whole version-bump one transaction. Borrow the shape (manifest + version + atomic bump);
  keep Django migrations as delivery.
- **Kubernetes reconciliation** — level-triggered single-writer convergence structurally eliminates the
  interleaving race (one hand on the wheel).
- **Helm** — ordered, weighted, named phases + wait-gates; hooks-not-rollback-tracked shows external
  side effects aren't covered by the transactional core.

## Relationship to existing specs

- **Extends** `spec-plugin-load-lifecycle-v0.md` (the load contract) by taking on its deferred non-goals.
- **Consumes** `spec-plugin-dependency-resolution.md` (depends_on ordering feeds phase ordering).
- **Feeds** `spec-dev-validation.md` (the fail-closed grid invariant + a migration-path CI discipline:
  exercise fresh-install AND upgrade-from-vN and assert schema convergence).
- **Security posture**: the grid-table single-source (req-…-grid-tables-single-source) closed audit
  finding #1 (read_guard vs search_role divergence) — landed via PR #49 as
  `req-grid-table-classification.sec` in `tap_grid/specs/spec-grid-security.md`. Any table-scoped
  guard this lifecycle adds (including the future traversal-exec table guard, now spec-bound there)
  MUST consume `tap_grid/grid_tables.py`, never re-derive the table set.
