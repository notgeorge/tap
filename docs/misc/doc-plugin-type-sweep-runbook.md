---
title: Plugin Type-Ownership Rename Sweep — Runbook & Rename Map
spec: tap_plugins/specs/spec-plugin-type-ownership-v0.md
audience:
  - llm
  - developer
status: runbook
---

# Plugin Type-Ownership Rename Sweep — Runbook & Rename Map

Prep for the deferred `<slug>__<name>` / `<NAME>__<slug>` sweep
(`spec-plugin-type-ownership-v0`, `req-plugin-type-node-prefix` / `-edge-suffix`, both `Proposed`).
Staged now so the sweep is *execution, not design* when it runs. **Run it last-session-standing**
— its body is a wide string-reference rewrite that collides catastrophically with any concurrent
edit to tests/fixtures/GRIFT/queries.

## What this is (and isn't)

- **Is:** a wide, shallow rewrite — plugin node/edge *type values* → their `<slug>__`/`__<slug>` form,
  the backing table renames, and the same substitution in every *string reference* (test corpora,
  GRIFT/fixture/expected JSON, Gryphon query strings, cross-plugin edge endpoints, docs). Per the
  spec, string references are the *dominant* cost, not the model files.
- **Is not** a data migration. *"No data migration semantics beyond table renames; dev resets
  freely."* Table renames are auto-generated Django migrations; the DB is reset in dev.
- **Is safe if validated.** A renamed type with a stale reference **fails loudly** in the suite
  (gridkin corpus, model oracle, gryphon suite, plugin tests). The full-suite gate turns "touched
  everything" into "proved everything."

## Target rules

- **Node types + tables:** `<slug>__<name>` (`req-plugin-type-node-prefix`).
- **Edge types:** `<NAME>__<slug>` (`req-plugin-type-edge-suffix`).
- **Delimiter is `__`** (locked 2026-06-26). Core/platform types stay **bare** —
  `entity, edge, batch, keystone, dimension, search` + core edges — and plugins must not use them.
- **Convergence:** post-sweep, `ENTITY_TYPE == db_table == <slug>__<name>` for every plugin type.
  They diverge today (see `computing_core`/`lotr` below).
- **Verbose-explicit is accepted** (`req-plugin-type-verbose-doctrine`) — long qualified names over
  a resolution layer.

## Scope

| Plugin | Node types | Edge types | Action |
| --- | ---: | ---: | --- |
| `grid_fixtures` | 4 | 4 | **Done** (proof lineage — `a40419ee` on `gryphon_playground`, inherited on extraction). |
| `aws_core` | 41 | 23 | Sweep — uniform `aws_` prefix, clean. |
| `github_core` | 9 | 10 | Sweep — uniform `github_` prefix. |
| `computing_core` | 11 | 10 | Sweep — **bare `ENTITY_TYPE`s** (highest generic-collision risk). |
| `lotr` | 9 | 12 | Sweep — bare `ENTITY_TYPE`, prefixed table (diverged). **`plugin-untangle` landed** (`origin/main` `3ada9642`): core suites migrated off lotr onto `grid_fixtures`, lotr now install-only → ripple collapsed from ~20 core modules to lotr's own tests + **one** residual core ref (see below). |
| `fedramp_20x_ksi` | 14 | 13 | Sweep — **messy** (multi-prefix + bare; strip is unsafe). |
| `sigstore_core` | 2 | 5 | Sweep — two prefixes (`sigstore_`, `rekor_`). |
| `administrivia`, `genericom`, `roscale`, `samsite` | 0 | 0 | No types. **But `samsite` *consumes* others' types by string** → update refs (see Ripple). |

## Decisions to ratify before running

1. **Strip the domain prefix, or keep the full name?** `aws_account` → `aws_core__account` (strip,
   matches the `grid_fixtures` precedent `pg_node`→`grid_fixtures__node`) **vs** `aws_core__aws_account`
   (keep, collision-proof but redundant). **Recommendation:** strip for the *uniform-single-prefix*
   plugins (`aws_`, `github_`); **keep** for the multi-prefix/bare-mixed plugins where stripping
   risks new collisions (see `fedramp`).
2. **`fedramp` bare types** (`evidence`, `finding`, `exception`, `boundary`) — squatting core-ish
   names. They must become `fedramp_20x_ksi__evidence` etc. (prepend, do **not** strip). Confirm the
   plugin genuinely owns these vs. some being intended as core types.
3. **`computing_core` generics** (`user`, `file`, `program`, `port`, `ip_address`, `public_key`, …) —
   these are the exact collision case the spec cites. `computing_core__user`, etc.

## Rename map

### `aws_core` — strip `aws_`, prepend `aws_core__`
`aws_account → aws_core__account`, `aws_ec2_instance → aws_core__ec2_instance`,
`aws_iam_role → aws_core__iam_role`, … (all 41 mechanically; `ENTITY_TYPE == db_table` already, so
one substitution covers both). Edges: `<NAME> → <NAME>__aws_core` (`CONTAINS → CONTAINS__aws_core`,
`PROTECTS → PROTECTS__aws_core`, …).

### `github_core` — strip `github_`, prepend `github_core__`
`github_repository → github_core__repository`, `github_actions_run → github_core__actions_run`, …
Note `oidc_issuer` (no `github_` prefix) → `github_core__oidc_issuer`. Edges → `<NAME>__github_core`.

### `computing_core` — bare `ENTITY_TYPE`, prepend `computing_core__` (HIGH RISK)
`ENTITY_TYPE` is **bare** (`user`, `file`, `program`, `port`, `ip_address`, `network_interface`,
`tcp_connection`, `public_key`, `private_key`, `web_host`, `web_document`) while `db_table` is
`computing_*`. Both converge → `computing_core__user`, `computing_core__file`, … Edges → `<NAME>__computing_core`.

### `lotr` — bare `ENTITY_TYPE`, `lotr_` table; converge to `lotr__`
`ENTITY_TYPE` bare (`character`, `realm`, `race`, `faction`, `location`, `citadel`, `artifact`,
`sentinel`, `wanderer`), `db_table` `lotr_character`. Both → `lotr__character`, … Edges → `<NAME>__lotr`.
**Ripple now low.** `plugin-untangle` landed (`origin/main` `3ada9642`) and moved lotr's fixture role
onto `grid_fixtures` — core suites no longer create lotr types (`_make_wanderer` now returns
`grid_fixtures__unconstrained`, not a lotr wanderer). What remains for lotr's sweep is its **own**
tests/fixtures/GRIFT plus exactly **one** residual core reference:
`tap_web/tests/test_table_panel.py::TestTablePanelIconEnrichment` still seeds lotr `EntityType`s from
the lotr manifest and asserts icon resolution for `character` (`/static/lotr/icons/character.svg`). The
manifest-driven seeding auto-follows the rename; only the hardcoded `"character"` string and the icon
path assertion need the `character → lotr__character` update (~2 lines). *(If `plugin-untangle`
migrates that icon test off lotr in a follow-up, this residual disappears — confirm before sweeping.)*

### `fedramp_20x_ksi` — KEEP names, prepend `fedramp_20x_ksi__` (do NOT strip)
Multi-prefix + bare, and stripping collides (`vdr_finding`→`finding` == bare `finding`). So prepend
the whole current name: `compliance_artifact → fedramp_20x_ksi__compliance_artifact`,
`ksi_signal → fedramp_20x_ksi__ksi_signal`, `vdr_finding → fedramp_20x_ksi__vdr_finding`,
`finding → fedramp_20x_ksi__finding`, `evidence → fedramp_20x_ksi__evidence`, … Edges → `<NAME>__fedramp_20x_ksi`.

### `sigstore_core` — KEEP names, prepend `sigstore_core__`
Two prefixes: `sigstore_ca → sigstore_core__sigstore_ca`, `rekor_log_entry → sigstore_core__rekor_log_entry`.
(Or strip both prefixes → `sigstore_core__ca`, `sigstore_core__log_entry` — cleaner; ratify with #1.)
Edges → `<NAME>__sigstore_core`.

## Collision hotspots (why the sweep matters, not just tidiness)

| Bare identifier | Owned by | Today | After |
| --- | --- | --- | --- |
| `CONTAINS` (edge) | `aws_core` **and** `lotr` | **collide** — same edge type on the grid | `CONTAINS__aws_core` / `CONTAINS__lotr` |
| `PROTECTS` (edge) | `aws_core` **and** `lotr` | **collide** | `PROTECTS__aws_core` / `PROTECTS__lotr` |
| `user`, `file`, `program`, `port` (node) | `computing_core` (bare) | one slug-rename away from colliding with any plugin's `user` | `computing_core__*` |
| `finding`, `evidence` (node) | `fedramp_20x_ksi` (bare) | squat core-ish namespace | `fedramp_20x_ksi__*` |

## Cross-plugin reference ripple

The sweep is **not** cleanly per-plugin: `samsite` (grift-only) consumes `aws_core` / `github_core` /
`sigstore_core` / `roscale` node + edge types **by string** in its GRIFT/fixtures. Renaming those
producers requires updating `samsite`'s references **in the same atomic sweep**. Same for any
cross-plugin edge endpoint and any core-suite reference. `grid_fixtures` consumers (`gryphon_playground`
corpus, `tap_grid/tests/test_gryphon.py`) are already on the new names.

## Context-aware rewrite (NOT a blind sed)

The same token means different things; rewrite **only**:
- `ENTITY_TYPE` / edge `slug` **values**, `db_table` values, `tap-plugin.toml` type/edge keys
- edge-endpoint type references, GRIFT/fixture/expected `type` fields, Gryphon query strings, data
Leave **untouched**: Python module paths + filenames (`models/pg_node.py`), class names (`PgNode`),
and the `db_table` single→double-underscore is a *delimiter* change, not a slug re-prepend.

## Runbook (last session standing)

1. **Confirm you're solo** — `plugin-untangle` **already landed** (`origin/main` `3ada9642`); the remaining gate is `validation-creation` closed/promoted. Then merge fresh `origin/main` into this session and confirm it's synced.
2. **Ratify the three decisions** above (strip-vs-keep, fedramp bare, sigstore strip).
3. **Per producer plugin, in order** (leaves → `samsite`-consumed → `lotr` last): apply the map to model files (`ENTITY_TYPE` + `Meta.db_table` + edge JSON `slug`), then sweep every string reference (its tests, fixtures, GRIFT, expected JSON) **plus** every cross-plugin consumer's reference.
4. **Regenerate migrations** (`makemigrations` → table renames) and **reset the dev DB**.
5. **Full suite** (`scripts/test`) — the corpus is the net; a missed reference fails loudly. Iterate until green.
6. **Flip the lint** `warn-now → fail-CI` (`req-plugin-type-collision-loud`) — the completion signal + anti-regression latch; and set `req-plugin-type-node-prefix`/`-edge-suffix` → `Implemented`.
7. **One atomic promote.** Announce so the other sessions resync from swept `main`.

## Sizing

Wide but mechanical: ~90 node types + ~77 edge types across 6 plugins, dominated by string-reference
substitution the suite validates. With this map pre-built and decisions ratified, it's an evening's
execute-and-validate, not a design marathon — provided it runs uncontended.
