---
title: Plugin Full-Eviction Plan (monorepo → own repos)
spec: tap_plugins/specs/spec-plugin-architecture.md
audience:
  - llm
  - developer
status: plan
---

# Plugin Full-Eviction Plan

The morning handoff for taking plugins the last mile: from **package-mode-in-the-monorepo**
(where they are today — `tap_plugin.<slug>`, own `pyproject.toml`, installed via editable local
source) to **fully evicted** — each plugin in its own git repository, pulled at boot via an authed
git source, versioned standalone, tested standalone.

This is a **supervised, fire-in-the-morning** plan, deliberately NOT part of the overnight close-out
(`doc-plugin-closeout-overnight.md`). It needs live external calls (GitHub pulls), a real PAT secret,
and human eyes on a new install path — none of which belong in an unattended last-session-standing run.

## Why this is separate from tonight, and downstream of the type sweep

1. **Eviction has an unbuilt prerequisite.** `req-plugin-arch-sources` (git bootstrap path) and
   `req-plugin-arch-source-secret` (`github_pat`) are **Proposed, not built**. Every plugin today uses
   `source: {type: editable, path: plugins/<slug>}`. Nothing can *leave* until the authed git-source
   install path exists in pre-boot. That is a build, not a move.
2. **The type sweep must land first.** Phase 2 of the close-out is a wide, corpus-validated string
   rewrite across every plugin's types/tables/GRIFT. Doing it while all plugins are co-located in one
   repo is one atomic pass. Once a plugin lives in its own repo, that same rename becomes cross-repo
   coordination. **Do not begin eviction until the type sweep is on `main`.**
3. **Pilot-first, not fleet-first.** Prove the entire path — repo → authed source → PAT → standalone
   version → standalone CI green → boots into a real instance — on **one** low-risk plugin before
   touching the other ten. The monorepo is the fallback the whole time (editable ↔ git-source is a
   per-plugin, reversible flip).

## Precondition checklist (do not start until all true)

- [ ] Type-ownership sweep (`doc-plugin-type-sweep-runbook.md`) complete and on `origin/main`.
- [ ] Baseline flip (Phase 3) landed, or explicitly deferred — eviction touches profiles and should
      not race the `base → test_all` / default `→ core_dev` rename.
- [ ] A GitHub org/location decided for the plugin repos, and a PAT minted with least-privilege read
      on them (this is the `github_pat` the secret consumes).

## Build prerequisite — the authed git-source install path

Before any plugin moves, build what the spec already designs. Both are **pre-boot** work
(`tap/preboot.py` + `tap/runtime_secrets`), settings-free, app-neutral.

1. **Git bootstrap source** (`req-plugin-arch-sources-1/-2`, `-4`): a source-type strategy for
   `{type: git, url, rev}` (already partly present — `uv_install_args` builds the
   `tap-plugin-<slug> @ git+<url>@<rev>` spec; `test_uv_install_args_git` covers it). What's missing is
   the *auth* wiring and the strategy-registry shape. Private auth via a credential helper fed from
   `TAP_SECRETS_ROOT` — **never a token in the URL** (it leaks into the venv's `direct_url.json`).
2. **`github_pat` source secret** (`req-plugin-arch-source-secret`, all 5 sub-reqs):
   - `kind: github_pat` with its own boot `data_schema` (`token`/`host`/`username`) — do **not** reuse
     the github_core collector's `repos`-bearing schema.
   - Scope `tap_plugins/source` (the install *system*), never `tap_plugin/<slug>/…` — least privilege
     across plugins (`-2`).
   - Resolved via `tap/runtime_secrets` in pre-boot, the same resolver `tap_auth` uses — **not**
     `tap_cares` (that would break the settings-free / no-app-import contract) (`-3`).
   - Fed to git via `GIT_ASKPASS`, never interpolated into the URL (`-4`).
   - **Conditionally necessary** (`-5`): required only when an authed `git` source is declared. Reuse
     the health-probe conditional-validation pattern from the secrets-review work
     (`secrets-conditional-validation`) — necessity is per-consumer probe logic, not a blanket
     `required_for_boot`. Editable/path/public/wheelhouse sources need no credential.
3. **Per-source credential selection** (George 2026-07-02 — multi-repo private sources). A single
   fleet-wide `github_pat` is the v0 floor, but each plugin's `install` section must be able to name
   **which** credential to use, so plugins can be pulled from **different private repos** (different
   orgs/hosts/accounts) in one profile. Concretely: the git source entry carries an optional
   `credential` (a secret *ref*, e.g. `{type: git, url: ..., rev: ..., credential: "acme-plugins-pat"}`);
   pre-boot resolves that ref via `tap/runtime_secrets` and feeds the matching token to `GIT_ASKPASS`
   for that source only. Absent `credential`, fall back to the default `tap_plugins/source` secret
   (back-compat with the single-PAT floor). This keeps least-privilege per source (a repo's PAT never
   sees another repo) and is the natural extension of `req-plugin-arch-source-secret` from one
   credential to a credential *set*. Cheap, foundational edge worth laying when the source-secret
   schema is first built — retrofitting a second credential onto a single-PAT assumption is expensive.
   Needs a spec sub-req (`req-plugin-arch-source-secret-6`?) when the eviction work starts.
4. **Prove it against a throwaway private repo** before touching a real plugin: a git source with the
   PAT, booted in a scratch instance, installs and imports. This de-risks the whole plan for the cost
   of one repo.

## Per-plugin eviction recipe (run once as the pilot, then fan out)

For each plugin `<slug>`:

1. **New repo.** `plugins/<slug>/` → its own git repository (history-preserving `git subtree split`
   or a clean seed — clean is fine; the monorepo history stays authoritative for archaeology).
2. **hatch-vcs standalone** (`req-plugin-arch-versioning-1`): remove the `root = "../.."`
   monorepo-transition override from the plugin's `pyproject.toml` so `hatch-vcs` derives the version
   from *its own* repo's git tags. Tag `v0.1.0` (or similar) so the version isn't the `0.0.0` fallback.
3. **dev-deps** (`req-plugin-arch-dev-deps`): if the plugin predates the scaffold seeding
   (2026-07-02), add the PEP 735 `[dependency-groups] dev` group (pytest/pytest-django/factory-boy +
   any plugin-specific test deps). New plugins are already born with it. **This is the backfill half
   of the cheap edge** — it only becomes load-bearing at eviction (a standalone repo must carry its
   own test closure).
4. **Standalone tests.** The plugin's own suites (`plugins/<slug>/tests/` today) must run against an
   installed TAP core + the plugin, with no sibling plugins present. This is where the
   *suite-tiers* reality bites: some core suites hardcode plugin fixtures, and pytest discovery is
   pure file-path. Resolve per the suite-tiers handoff — the plugin's standalone suite tests the
   plugin; the monorepo `test_all` remains the integration superset.
5. **Standalone CI.** A minimal GitHub Actions workflow in the plugin repo: install TAP core (from
   its published dist or a pinned git rev), install the plugin + its dev group, run the plugin's
   suite. Tag → build wheel (for the future `index`/`wheelhouse` paths, `req-plugin-arch-sources-3/-6`).
6. **Flip the source.** In the deployment profile(s) that install `<slug>`, change
   `source: {type: editable, path: plugins/<slug>}` →
   `source: {type: git, url: <repo>, rev: <tag-or-sha>}`. The dependency-consistency gate + pre-boot
   install exercise the new path.
7. **Boot-verify** in a scratch instance (`spawn --boot-file` a profile that git-installs the plugin);
   confirm health + reconciliation. **Then** remove `plugins/<slug>/` from the monorepo.

## Pilot choice

**`fedramp_20x_ksi`** — first plugin to package-mode, **no cross-plugin import deps** (a clean leaf),
and it carries a real collector (`ksi-catalog`, HTTPS no-creds) that exercises a live boot path without
needing AWS/GitHub credentials. It is the lowest-risk end-to-end proof of the git-source + PAT + tag +
CI + boot chain. (The offline `wheelhouse` pilot in the spec also names `fedramp_20x_ksi` — same
rationale; do the git-source pilot first since git is the bootstrap path.)

**Highest-risk, evict last:** `lotr` (~20 core-suite importers as the demo/test-fixture vocabulary —
must stay editable-installed for the core suite until the suite-tiers story is fully resolved) and
`samsite` (the demo integration surface — imports four sibling plugins and reads a fifth's nodes; its
deployment profile references sibling editable paths that all become git sources at once).

## Sequencing

1. Type sweep on `main` (close-out Phase 2). **Hard gate.**
2. Build the authed git-source path + `github_pat` secret; prove against a throwaway repo.
3. Pilot: evict `fedramp_20x_ksi` end-to-end. Bank it. **Stop and assess** — the pilot teaches where
   the recipe is wrong before it's applied ten times.
4. Fan out to the remaining clean leaves (computing_core, roscale, sigstore_core, github_core,
   aws_core), each its own atomic PR.
5. Evict `samsite` (cross-plugin source flips) and `lotr` (suite-tiers dependent) last.
6. Retire the `editable` local-source path once no profile uses it (or keep it as the
   dev/monorepo-checkout convenience — decide at the end, demand-driven).

## Explicitly out of scope here

- The `index` durable path (`req-plugin-arch-sources-3`) and offline `wheelhouse`
  (`-6`) — demand-gated, downstream of a healthy git-source fleet. Named, not built.
- Core apps as workspace members (`req-plugin-arch-core-packaging`) — orthogonal backlog.
- Grid source (`req-plugin-arch-sources-5`) — reserved, not built.

## Definition of done

- The authed git-source install path + `github_pat` secret built, tested, and the sub-reqs flipped
  `Proposed → Implemented` in `spec-plugin-architecture.md`.
- `fedramp_20x_ksi` living in its own repo, git-installed into a booting instance, standalone CI green.
- The per-plugin recipe proven and documented (this doc, updated with what the pilot taught).
- Remaining leaves fanned out; `samsite`/`lotr` scheduled behind the suite-tiers resolution.
