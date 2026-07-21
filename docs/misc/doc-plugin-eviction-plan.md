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

1. **The authed git-source install path is now BUILT** (2026-07-03). `req-plugin-arch-source-secret`
   (all six sub-reqs) and the auth half of `req-plugin-arch-sources-2` are **Implemented**:
   `tap/plugin_source_auth.py` resolves a `github_pat` source secret in pre-boot via
   `tap/runtime_secrets` and feeds it to git through `GIT_ASKPASS` (never token-in-URL), with per-source
   `credential` selection. Every plugin today still uses `source: {type: editable, path: plugins/<slug>}`;
   the move is now flipping that entry to `{type: git, url, rev, credential}` — a config change, no
   longer a build. (Still Proposed: the formal source **strategy registry** `-1` and the `index`/`wheelhouse`
   durable paths — none of which the git-pilot needs.)
2. **The type sweep must land first.** Phase 2 of the close-out is a wide, corpus-validated string
   rewrite across every plugin's types/tables/GRIFT. Doing it while all plugins are co-located in one
   repo is one atomic pass. Once a plugin lives in its own repo, that same rename becomes cross-repo
   coordination. **Do not begin eviction until the type sweep is on `main`.**
3. **Pilot-first, not fleet-first.** Prove the entire path — repo → authed source → PAT → standalone
   version → standalone CI green → boots into a real instance — on **one** low-risk plugin before
   touching the other ten. The monorepo is the fallback the whole time (editable ↔ git-source is a
   per-plugin, reversible flip).

## Precondition checklist (do not start until all true)

- [x] Type-ownership sweep (`doc-plugin-type-sweep-runbook.md`) complete and on `origin/main` — Phase 2, tip `c762a0c9`.
- [x] Baseline flip (Phase 3) landed — Phase 3A, tip `460a2933` (`base → test_all` / default `→ core_dev`).
- [x] The authed git-source install path built — `req-plugin-arch-source-secret` Implemented 2026-07-03.
- [ ] The plugin repos exist under a decided home, and a PAT minted with least-privilege read on them
      (this is the `github_pat` the secret consumes). **In progress:** repos already exist under
      `github.com/notgeorge/tap-plugin-*` (submodule era); George minting a fine-grained
      `Contents: Read-only` PAT scoped to those six repos.

## Build prerequisite — the authed git-source install path — ✅ BUILT (2026-07-03)

The spec's design is now implemented. Both halves are **pre-boot** work
(`tap/plugin_source_auth.py` + `tap/preboot.py` + `tap/runtime_secrets`), settings-free, app-neutral.
Recorded here as the reference for what exists; the sub-points below are the as-built contract.

1. **Git bootstrap source** (`req-plugin-arch-sources-2`, `-4`) — ✅ `uv_install_args` builds the
   `tap-plugin-<slug> @ git+<url>@<rev>` spec (`test_uv_install_args_git`), and the auth wiring now
   feeds the credential via `GIT_ASKPASS` — **never a token in the URL** (it leaks into the venv's
   `direct_url.json`). Still Proposed: the formal strategy-registry shape (`-1`) — today it's the
   if/elif in `uv_install_args`, which the pilot doesn't need.
2. **`github_pat` source secret** (`req-plugin-arch-source-secret`, all sub-reqs) — ✅ built in
   `tap/plugin_source_auth.py`:
   - `kind: github_pat` with its own boot `data_schema` (`token`/`host`/`username`) at
     `tap/schemas/github_pat_source_secret.schema.json` — `additionalProperties:false` rejects the
     github_core collector's `repos`-bearing schema (`-1`).
   - Scope `tap_plugins.source` (the install *system*), never `tap_plugin/<slug>/…` (`-2`).
   - Resolved via `tap/runtime_secrets` in pre-boot, the same resolver `tap_auth` uses — **not**
     `tap_cares` (`-3`).
   - Fed to git via `GIT_ASKPASS`, never interpolated into the URL; `GIT_TERMINAL_PROMPT=0` forbids an
     interactive hang (`-4`).
   - **Conditionally necessary** (`-5`): enforced at pre-boot resolve time — a git source that declares
     a `credential` requires it (missing/absent-store ⇒ `PrebootError`); a git source with no `credential`
     is public (no auth). No implicit default key. Not a `tap_cares` health probe (pre-boot is
     settings-free); the `credential` ref IS the declaration.
3. **Per-source credential selection** (`-6`, George 2026-07-02) — ✅ the git source entry carries an
   optional `credential` (a descriptive secret *key* under scope `tap_plugins.source`, e.g.
   `{type: git, url: ..., rev: ..., credential: "github-plugins-ro"}`); pre-boot resolves it and feeds
   the matching token to `GIT_ASKPASS` for that source only. No `credential` ⇒ public (no auth); a
   repo's PAT never sees another repo. No vague fleet default — each private repo names its credential.
4. **Prove it against a real repo** — the remaining step. Push the pilot's current tree to
   `notgeorge/tap-plugin-fedramp-20x-ksi`, tag `v0.1.0`, drop the read-only PAT under `TAP_SECRETS_ROOT`
   (`tap_plugins.source` scope), flip the pilot's install entry to the git source, and boot it — ideally
   through `scripts/gate-lean` (own compose project, fresh venv) so a bad credential/source fast-fails
   via the ABORT signal instead of hanging. This de-risks the fleet for the cost of one repo.

### Pilot result — ✅ PROVEN 2026-07-03

`fedramp_20x_ksi` extracted to a standalone tree (deleted the `root = "../.."` hatch override — the one
documented extraction edit), force-pushed to `github.com/notgeorge/tap-plugin-fedramp-20x-ksi` at tag
`v0.1.0` (commit `dae4682`). `hatch-vcs` derives `0.1.0` from the tag; the wheel ships the
`tap_plugin/fedramp_20x_ksi` namespace package + `tap-plugin.toml` + collectors/edges + entry point.
End-to-end install proof (isolated venv, real `github-plugins-ro` PAT): **control** (no creds) → private
repo refuses the anon clone; **treatment** (our `GIT_ASKPASS` path) → installs `0.1.0`, `direct_url.json`
pins `commit_id dae4682` / `requested_revision v0.1.0`. Both leak invariants held: **no token in the
install args, none in `direct_url.json`**. The credentialed-install mechanism is done; what remains per
plugin is the recipe below (standalone CI, then flip its *committed* profile entry editable → git).

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

## Addendum (2026-07-09): the unified eviction wave — `aws_secrets_source` + the two repoless substrate plugins

Since this doc was written, the fanout (steps 4–5) reshaped into **one coordinated wave**
owned by session/plugins, bundled with the migration squash (task #16) — one fresh-DB event,
not several. Three additions:

**Two new substrate plugins with no repos yet.** `compliance_core` and `identity_core` (both
extracted 2026-07-08) are `*_core` substrate leaves that several evicted plugins now depend on
(`samsite`, `fedramp_20x_ksi`, `github_core`, `sigstore_core`). Neither has a
`github.com/notgeorge/tap-plugin-*` repo. Until they do, their **reverse-dependency closure
forces most of the set to stay `editable`** — which is why `boot/samsite.boot.json` is
currently all-editable (interim, landed `1d5b9b7c`), and why a git-sourced boot of that profile
fails resolving `tap-plugin-compliance-core` off the index. **Cut these two repos first in the
wave** (clean substrate leaves — `identity_core` has no `root = "../.."` override to strip;
verify `compliance_core`), tag `v0.1.0`; then the dependents re-release at `v0.2.0` git tags and
the profile flips back to git.

**`aws_secrets_source` — the bootstrap secret-source provider — evicts differently.** It is
**not a grid plugin**: flat `aws_secrets_source/` package (not `tap_plugin.<slug>`), `boto3`-only,
registers one `tap.secret_sources` entry point, no `BaseModel`/migrations/collectors, and **no
`boot/*.json` entry**. Already extraction-ready as a distribution (no `root = "../.."` override,
self-contained hatch build). Its eviction is a **build-time bake**, not a boot-time git source,
because it sits *below* the PAT resolution it enables — it must be importable before boot can
resolve `github-plugins-ro`:

1. **Cut a private repo** `notgeorge/tap-plugin-aws-secrets-source`; push the tree, tag `v0.1.0`.
   Nothing to strip.
2. **Extend the read-only `github-plugins-ro` PAT scope** to include that repo (`Contents:
   Read-only`). **Not** the write-capable CodeConnections "AWS Connector" App — that App's
   `Administration:write`/`hooks:write` is runner+webhook plumbing for the *workflow-hosting*
   repo only; the plugin repo hosts no workflow.
3. **Install it at build time from its repo, not the monorepo path.** In the CI image build:
   `ambient IAM → aws secretsmanager get-secret-value --secret-id tap-ci/github-plugins-ro`
   (aws-cli, **not** the provider seam → no bootstrap recursion) `→ git clone` `→ uv pip install`
   into the base image. Then **drop** the `TAP_SECRET_SOURCE_DISTS=/app/plugins/aws_secrets_source`
   monorepo pointer (`.github/workflows/product-lines.yml`) and the entrypoint's monorepo-path
   install (`docker/entrypoint.sh`).
4. **Runtime unchanged:** the baked provider resolves the same PAT via the seam to git-install the
   other private plugins at boot.

Release-tracking gotcha: absent from every `boot/*.json`, so there's no boot `rev` to bump — its
version pin lives entirely in the Dockerfile/build step. Pin explicitly (`@v0.1.0`) and track it
there, or it silently drifts stale.

**Ownership split for this wave.** The github-actions session lands its `aws_secrets_source` CI
wiring on the **monorepo path** (correct pre-eviction) and merges to `main`; session/plugins then
pulls that down and executes the git-from-own-repo flip **here, as part of this wave** — the
provider is not made eviction-ready upstream, only here, so the flip happens once alongside the
rest. Migration squash (#16) rides the same wave: core-app migrations squash to one `0001_initial`
in the monorepo, plugin migrations squash in-repo and re-release with the wheels;
`aws_secrets_source` has no migrations, so it sits out the squash.

## Execution Runbook (2026-07-21, DECIDED — run in a FRESH session spawned from main)

Three decisions locked with George 2026-07-21 that **reshape** the 2026-07-09 addendum's "one
coordinated wave":

1. **Squash DECOUPLED from eviction.** The 2026-07-09 plan folded the migration squash in "to avoid
   double-release." But measurement shows **11 of 14 plugins are already released with their tests
   shipped in-package** (`tap_plugin/<slug>/tests/`, e.g. aws_core carries 18 tests in its wheel), so
   git-sourcing `test_all` covers their tests **without any re-release**. Folding the squash back in
   is the *only* thing that would force re-releasing everything — so we **defer the squash** to a
   separate later clean-base pass. Eviction proper needs no re-releases.
2. **Evict aws_core too** — `session/aws-cloud` is done, so the "don't touch aws_core while it's live"
   hazard is lifted. No straggler; git-source aws_core at its existing `v0.2.0` and delete its copy.
3. **Fresh dedicated session** for the wave (clean context; the earlier plan). Spawn from current main.

Concrete state (measured 2026-07-21): stragglers needing action = **samsite** (no repo yet; strip its
`root = "../.."` at `pyproject.toml:63` on extraction), **administrivia** (repo exists, no tag → first
release), **lotr** (repo exists, no tag → retire). `lotr` core-debt is **cosmetic**: the only refs are
a `help_text` example string (`tap_web/models.py:142` + its baked copy in `tap_web/migrations/0001_initial.py`
+ `tap/settings.py:166` comment + a few specs) — swap the example to `grid_fixtures`, no structural
change. `test_all.boot.json` = all 13 editable (THE blocker); `samsite.boot.json` = 4 editable
(administrivia, lotr, samsite, grid_fixtures) + 8 git; `all-plugins.yml` = still v1.

### Ordered sequence (each step gates the next; deletion is the point of no return)

1. **Retire lotr** — swap the `help_text` example → `grid_fixtures` in `tap_web/models.py` (generates a
   trivial help_text migration), fix the `tap/settings.py:166` comment + specs, remove lotr from
   `test_all.boot.json` + `samsite.boot.json`. Mark the lotr repo deprecated. (Leave the historical
   `0001_initial.py` help_text as-is — it's frozen migration state.)
2. **Release the two stragglers** (via `scripts/release-plugin.sh`, built this session):
   - `administrivia` → `release-plugin administrivia 0.1.0` (repo exists).
   - `samsite` → `gh repo create notgeorge/tap-plugin-samsite --private`, strip `root = "../.."`, push,
     then `release-plugin samsite 0.1.0`.
3. **Flip all boot sources → git** at released tags: `test_all.boot.json` (all 13, incl aws_core v0.2.0,
   new administrivia/samsite v0.1.0, grid_fixtures v0.1.0), `samsite.boot.json` (the 4 editable),
   `core_dev.boot.json` (grid_fixtures), and `all-plugins.yml` v1 → v2 (git-sourced test_all).
4. **VERIFY GREEN — the safety rail before deletion:** boot the git-sourced `test_all` in a scratch
   instance + full lane green; `all-plugins` CI green. Do NOT proceed to step 5 until both are green.
5. **Delete monorepo copies (IRREVERSIBLE):** `rm -r plugins/<slug>/` for all 13 evicted; core-only
   repo. Handle `aws_secrets_source` separately (build-time bake — drop the `TAP_SECRET_SOURCE_DISTS`
   monorepo pointer in `product-lines.yml` + the entrypoint's monorepo install; it has no boot entry).
6. **Extend core install-awareness** so core-app tests/mypy/guards that hardcode plugin paths stay
   green without the monorepo copies (the focused-session promote gap) — else the promote reds.
7. **Promote** the wave (FULL CI gate — this is code, needs the real lane, not a docs bypass).
8. **DEFERRED:** migration squash, as a later clean-base pass on the evicted fleet.

### Coordination with the passkey chainguard/FIPS cutover (in parallel, not yet on main)
- The crypto artifacts this touches (uuid5=SHA-1 ids, SHA-256 boot digests) are **FIPS-invariant**
  (both approved; FIPS changes what's *allowed*, not approved-algo output) — so eviction under the
  current `python:3.14-slim` base mints byte-identical ids to what it would under chainguard. No need
  to wait; no double-mint.
- **Watch points when both land:** `all-plugins.yml`/`product-lines.yml` and `docker/entrypoint.sh` —
  the eviction edits sources/triggers there; the cutover edits the base/entrypoint. Expect a
  resolvable merge, not a surprise. Whichever promotes second merges the first.

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
