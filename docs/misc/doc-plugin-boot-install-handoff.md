---
title: Plugin Refactor — Install / Pre-Boot / Snapshot Implementation Handoff
date: 2026-06-30
status: handoff
audience:
  - llm
  - developer
related_docs:
  - docs/misc/doc-plugin-system-refactor-framing.md
  - docs/misc/doc-boot-tap-boot-handoff.md
related_specs:
  - specs/spec-tap-boot-v0.md
  - tap_plugins/specs/spec-plugin-architecture.md
  - tap_plugins/specs/spec-plugin-type-ownership-v0.md
---

# Plugin Refactor — Install / Pre-Boot / Snapshot Implementation Handoff

> **Status: shovel-ready specs, not yet implemented (2026-06-30).** This note hands a fresh
> session the design decisions reached in the `plugins` session so implementation does not
> re-litigate them. All requirements below are `Proposed`. Read the specs first; this is the
> orientation, not the contract.

## What this is

The plugin refactor turns plugins from build-baked Django apps into **installable code** (the
WordPress-style direction in `doc-plugin-system-refactor-framing.md`). Two halves, two prior
owners, now both spec-complete:

1. **Type-ownership slug-rename** (`spec-plugin-type-ownership-v0.md`) — every plugin-owned
   node/edge type carries its slug (`<slug>__name` nodes, `NAME__<slug>` edges); core stays bare.
2. **Install / pre-boot / registry** (`req-plugin-arch-install-registry` + the new boot reqs) —
   uv-package install from a boot profile, executed in a pre-Django pre-boot stage.

## Build order (forced by the type-ownership sequencing)

The slug-rename must land **in-monorepo, before any plugin repo extraction** (a global rename is
far cheaper before plugins split into N repos), and the install work *is* what does extraction. So:

1. **Slug-rename sweep** (proof plugin `gryphon_playground`) — see *Coordination* below; it is
   currently blocked on a parallel session finishing ~45 TCK/Cypher test-gap scenarios.
2. **Install MVP**: package-mode-first via uv git-source → pre-boot stage → samsite boot profile.

The slug-rename and the install work are otherwise independent; do the rename as its own focused
pass, then the install work.

## Coordination — the gryphon_playground rename (read before touching it)

- The rename was run + **verified once** in the `plugins` session (304 tests green, diff confirmed
  rename-only). It is **stashed**, not committed, on branch `session/plugins`:
  `stash@{0}` — "gryphon_playground type-ownership rename (verified, 304 green) — superseded by post-TCK re-sweep".
- It is **stale**: a parallel session is adding ~45 TCK/Cypher scenarios to `gryphon_playground`
  in **bare-name** form. Merging the stash against those new files is the hard way.
- **Do this instead:** once the TCK scenarios land and merge, **drop the stash and re-run the
  mechanical sweep over the unified corpus.** The rename is fully reproducible from
  `spec-plugin-type-ownership-v0.md` (§ "Sweep cost model & proof-plugin selection"); re-running is
  cheaper and safer than reconciling a 200-file diff. Run it wherever the corpus is freshest
  (ideally a continuation of the TCK session).
- Rename method (proven): context-aware rewrite, **not** blind sed. Rewrite only type-slug *values*,
  manifest keys, edge slugs, Gryphon query tokens, data `type` fields, and `db_table` identifiers
  (single→double-underscore). **Leave alone** module paths, filenames, class names, and prose. Add
  a `db_table` rename migration. Regenerate `expected/*` oracles via `GRIDKIN_UPDATE_SNAPSHOTS=1`,
  then verify a clean run **without** the flag. Confirm the oracle diff is rename-only (symmetric
  added/removed line counts = pure 1:1 swaps, no row-set changes).
- After `gryphon_playground` proves the template, the cross-plugin-edge plugins follow
  (`sigstore_core`, `aws_core`, `github_core`, `fedramp_20x_ksi`, `samsite`); `lotr` is the other
  corpus-heavy plugin.

## Install / pre-boot — the decisions, so you don't re-derive them

Spec homes: `spec-tap-boot-v0.md` `req-boot-preboot` / `req-boot-install-section` /
`req-boot-snapshot` / `req-boot-variable-resolution`; `spec-plugin-architecture.md`
`req-plugin-arch-install-registry`.

**Entrypoint order:** `uv sync → pre-boot (install plugins → [switch] snapshot DB → verify) → migrate → manage.py boot (auth → population)`.

1. **Pre-boot is a settings-free stage in `docker/entrypoint.sh`.** It runs before Django reads
   settings (it *generates* `TAP_PLUGINS`), so it cannot be a Django app or `manage.py` command.
   Its logic is a settings-free Python module in **`tap/`** (app-neutral, import-safe), reading the
   boot profile as plain JSON. `tap_boot` owns the *contract* (the profile shape); `tap/` *executes*
   the pre-Django phases. (K8s `initContainers` shape.)
2. **Install MVP = package mode, via uv git-source.** A plugin is a real wheel-buildable package
   with a `tap.plugins` entry point whose key **equals the slug**. "github-first" = `<dist> @ git+https://…@<rev>`, which is the *same* mechanism as a PyPI install (source-URL change only) — **not** a git submodule, **not** vendored source under `plugins/`. Checkout/dev mode (uv path/editable) comes after the package path is proven.
3. **No load-bearing `plugins/<slug>` symlink.** Package-mode code loads from where uv installs it.
   The **registry/report** is the canonical inspection surface (a `manage.py plugins`-style command /
   generated report now; grid-native plugins-as-entities later). Converge its shape with `/healthz`
   and the deferred boot report (`req-boot-report`) — all three are "observable assembled-instance
   truth". Any `plugins/<slug>` pointer is optional tooling-only, specified separately if ever added.
4. **Two profile sections — `install` vs `population`.** `install` = the (reproducible, shared)
   plugin set; `population` = (per-deployment) ordering/seeding/firing. NetBox's
   `local_requirements.txt`-vs-`PLUGINS` split. **Two-layer drift guard:** static profile-coherence
   in pre-boot (every `population` slug is also in `install`; pre-migrate, document-level), plus
   runtime availability in boot pre-population (`req-boot-population-7`, extends the existing
   `req-boot-population-4` in-memory pre-resolution). Both fail loud.
5. **Pre-migrate snapshot, switch defaults true.** Full schema+data snapshot as pre-boot's last act,
   while the DB is **quiescent** (app not started). **Serial + verify before `migrate`** (the
   restore-point guarantee; `pg_dump` ACCESS SHARE vs migrate ACCESS EXCLUSIVE would contend).
   **Restore is a deliberate human action, never auto.** `pg_dump` now; copy-on-write volume
   snapshot is the scale upgrade path. Build it as a **callable primitive in `tap/`** so a later
   periodic snapshot system (concurrent/online, against a live DB) is "call it on a schedule +
   retention". Dev disables via the env override; a skip logs loud (WARNING).
6. **Roll-forward recovery, never roll-back** (`req-boot-idempotent-3`). A migrated-but-unpopulated
   DB is *incomplete, not inconsistent*; recovery is fix-config-and-re-run (`migrate` is
   forward-idempotent). Never reverse-migrate; destructive-migration recovery is snapshot restore.
   **No transaction spans `migrate` + `population`.**
7. **Boot-variable resolution** (`req-boot-variable-resolution`): precedence `flag > env > profile
   > default`; env mapping `TAP_BOOT_<SECTION>__<KEY>` (e.g.
   `TAP_BOOT_INSTALL__SNAPSHOT_BEFORE_MIGRATE`); resolve-once and record effective-value + source in
   the report (so an override is never a silent profile divergence). Settings-free resolver in
   `tap/`. The snapshot switch is the first key; wire env+profile+default now, reserve the flag layer.

## MVP scope vs deferred

- **MVP:** package-mode uv git-source install; pre-boot stage in entrypoint; `install` section +
  both drift guards; pre-migrate snapshot (`pg_dump`, switch+dev-disable); registry/report as
  inspection surface; boot-variable resolver (env+profile+default); samsite boots from a profile.
- **Deferred (named, don't build now):** checkout/dev-mode polish; volume snapshots; periodic
  snapshot scheduler + retention; CLI-flag override layer; plugin config (`TAP_PLUGIN_CONFIG` stays
  an empty reserved seam — samsite keeps config in collector secrets); plugin dependency resolution;
  updates/rollback/enable-disable/signing/grants (the `doc-plugin-system-refactor-framing.md`
  "ecosystem board").

## Also bump

- **The plugin-creation skill** (`doc-plugin-system-refactor-framing.md` "refactor skill") — once
  the install shape is dialed in, update the skill so generated plugins are package-mode-compliant
  (wheel-buildable, `tap.plugins` entry point = slug, slug-namespaced types).

## Validation

- Tests via the containerized stack: `scripts/dc exec -T web uv run pytest …` (multi-session
  worktree — always `scripts/dc`, never raw `docker compose`; host Python is stale).
- Done-test for the install MVP: a fresh instance stands up from a samsite-class boot profile with
  its plugins uv-installed, migrated, seeded, and collected — and a reboot is a fast no-op (no
  re-pull). Promotion is gated on the dev-validation suite (`spec-dev-validation.md`).
