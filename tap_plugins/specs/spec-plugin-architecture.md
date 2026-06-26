# Plugins Architecture Specification

## Philosophy

TAP plugins are the primary mechanism for introducing domain-specific behavior without weakening TAP's core graph and service-layer contracts. A plugin should be easy to review, easy to scaffold, and easy to validate. In v0, that means the plugin's architecture should stay small, explicit, and manifest-driven.

This specification is intentionally broader than the manifest specification and intentionally lighter than a full lifecycle or packaging spec. Its job is to answer a practical authoring question: what are the core pieces a TAP plugin is expected to contain, and how should those pieces fit together?

The guiding principle is that a plugin's TAP-facing load surface should be inspectable before reading arbitrary implementation code. The manifest is therefore central, but the plugin also includes code, assets, data, specs, skills, and tests organized by clear conventions.

Plugins may be developed as standalone git repositories and integrated into TAP as git submodules under `plugins/`. Everything needed to understand, validate, test, and maintain the plugin should live inside the plugin directory, but the TAP plugin contract should not depend on when that repo/submodule boundary is established.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Simple        | A new plugin author can understand the minimum plugin shape quickly |
| 2. | Inspectable   | The plugin's TAP-facing contract is declared in one manifest-driven architecture |
| 3. | Self-Contained | Each plugin is a complete git repo with code, specs, skills, icons, tests, and CI |
| 4. | Consistent    | Plugins use the same package structure and extension points across domains |
| 5. | Testable      | Every plugin includes both structural validation and plugin-specific behavior tests |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-plugin-arch-scope | [Plugin Scope](#plugin-scope) | Implemented | Defines what a TAP plugin is architecturally |
| req-plugin-arch-django | [Django App Foundation](#django-app-foundation) | Implemented | Every plugin is a Django app using `TapPluginConfig` |
| req-plugin-arch-manifest | [Manifest Contract](#manifest-contract) | Implemented | Every plugin has a manifest conforming to the manifest spec |
| req-plugin-arch-surfaces | [Declared TAP Surfaces](#declared-tap-surfaces) | Implemented | Models, edges, editors, searches, and GRIFT are manifest-declared |
| req-plugin-arch-layout | [Package Layout](#package-layout) | Implemented | Core files, convention directories, and self-contained repo structure |
| req-plugin-arch-repo | [Repository Structure](#repository-structure) | Implemented | Plugins are self-contained git repos integrated as submodules |
| req-plugin-arch-install-registry | [Install Resolution And Plugin Registry](#install-resolution-and-plugin-registry) | Proposed | Plugin-refactor direction: boot profile desired state, uv lockfile resolution, package entry point discovery, TAP registry/report truth |
| req-plugin-arch-skills | [Plugin Skills](#plugin-skills) | Implemented | Plugins may ship Claude Code skills for plugin-specific automation |
| req-plugin-arch-runtime | [Runtime Boundaries](#runtime-boundaries) | Implemented | TAP-facing startup behavior flows through the plugin contract |
| req-plugin-arch-tests | [Testing Requirements](#testing-requirements) | Implemented | Plugins include plugin-specific tests and participate in shared validation |
| req-plugin-arch-iterative-dev | [Iterative Development](#iterative-development) | Implemented | Canonical patterns for revising GRIFT content during and after initial import |
| req-plugin-arch-python-deps | [Plugin Python Dependencies](#plugin-python-dependencies) | Implemented | uv workspace seam wired at root; first plugin proof is `github_core` (PyYAML resolves into root `uv.lock`) |
| req-plugin-arch-isolation | [Plugin Type Ownership & DB Isolation](#plugin-type-ownership--db-isolation) | Proposed | Plugin-refactor pickup: owner-namespaced types + hard-included per-plugin DB guards |
| req-plugin-arch-hooks | [Plugin Hook System](#plugin-hook-system) | Backlog | Future Simon Willison DJP/pluggy-style hook surface for plugin injection points throughout TAP |
| req-plugin-arch-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Explicitly deferred concerns |

### Plugin Scope
----
RID: `req-plugin-arch-scope`
Status: `Implemented`

A TAP plugin is a Django app package that contributes domain-specific TAP behavior.

#### Implementation

Architecturally, a plugin may contribute:

- TAP-managed model types
- edge types
- editor descriptors
- search runners
- bundled GRIFT data
- optional API routes and web assets layered on top of those TAP-managed surfaces

A plugin is not just an arbitrary Django app dropped into `INSTALLED_APPS`. To count as a TAP plugin, it must follow the TAP plugin contract and publish its TAP-facing shape through the manifest and plugin conventions.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-scope-1 | TAP Extension Unit | Implemented | A plugin is the standard TAP unit for domain-specific extension. | |
| req-plugin-arch-scope-2 | TAP Contract Required | Implemented | A Django app is only a TAP plugin if it follows the TAP plugin contract. | |
| req-plugin-arch-scope-3 | Domain-Specific Surface | Implemented | Plugins contribute domain-specific types, behaviors, data, or presentation. | |

### Django App Foundation
----
RID: `req-plugin-arch-django`
Status: `Implemented`

Every TAP plugin is a Django app built on `TapPluginConfig`.

#### Implementation

In v0:

- the plugin is a Python package
- `apps.py` contains exactly one subclass of `tap_plugins.base.TapPluginConfig`
- that subclass should remain minimal and normally use `pass`
- the plugin is installed through Django's normal `INSTALLED_APPS` mechanism

This keeps plugin discovery aligned with Django rather than inventing a separate registry mechanism.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-django-1 | Django App Package | Implemented | Every plugin is a Django app package. | |
| req-plugin-arch-django-2 | TapPluginConfig Base | Implemented | `apps.py` defines exactly one `TapPluginConfig` subclass. | |
| req-plugin-arch-django-3 | Standard Installation | Implemented | Plugins are discovered through `INSTALLED_APPS`. | |
| req-plugin-arch-django-4 | Minimal AppConfig Body | Implemented | The plugin `AppConfig` should normally be declarative and minimal. | |

### Manifest Contract
----
RID: `req-plugin-arch-manifest`
Status: `Implemented`

Every plugin has a manifest that conforms to the manifest specification.

#### Implementation

The plugin root must contain `tap-plugin.toml`. That file is the canonical declaration of the plugin's TAP-facing load surface and must conform to [`spec-plugin-manifest-v0.md`](/Users/george/Documents/code/tap/tap_plugins/specs/spec-plugin-manifest-v0.md).

At minimum, the architecture requires:

- a manifest file at the plugin root
- manifest identity fields that name the plugin
- manifest-declared TAP surfaces rather than hidden one-off registration
- strict validation against the manifest rules

This requirement is architecture-specific because the manifest is not just one file among many. It is the plugin's reviewable contract with TAP.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-manifest-1 | Manifest Required | Implemented | Every plugin has `tap-plugin.toml` at the plugin root. | |
| req-plugin-arch-manifest-2 | Manifest Spec Compliance | Implemented | The manifest conforms to the plugin manifest specification. | |
| req-plugin-arch-manifest-3 | Canonical TAP Declaration | Implemented | The manifest is the canonical declaration of the plugin's TAP-facing surfaces. | |

### Declared TAP Surfaces
----
RID: `req-plugin-arch-surfaces`
Status: `Implemented`

Plugins publish TAP-facing capabilities through explicit declared surfaces.

#### Implementation

In v0, the canonical declared surfaces are:

- `models`: TAP-managed model types
- `edges`: edge type definitions
- `editors`: typed editor descriptors
- `searches`: search runner callables
- `grift`: bundled GRIFT assets

These surfaces are optional individually, but if a plugin contributes one of them, it should do so through the manifest and the associated conventions/specifications.

API routers, templates, static assets, and other implementation files may also exist, but they are supporting implementation details rather than the primary TAP declaration surface.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-surfaces-1 | Canonical Surface Set | Implemented | v0 architecture recognizes models, edges, editors, searches, and GRIFT as the canonical TAP surfaces. | |
| req-plugin-arch-surfaces-2 | Explicit Declaration | Implemented | Contributed TAP surfaces are declared explicitly rather than inferred from arbitrary files. | |
| req-plugin-arch-surfaces-3 | Optional By Need | Implemented | A plugin may omit any canonical surface it does not use. | |

### Package Layout
----
RID: `req-plugin-arch-layout`
Status: `Implemented`

Plugins are self-contained packages with a required core shape plus convention directories for optional surfaces.

#### Implementation

Every plugin must contain:

- `__init__.py`
- `apps.py`
- `tap-plugin.toml`
- `tests/`

Every plugin should contain:

- `specs/` — plugin-specific specifications documenting architecture, decisions, and future plans
- `static/<plugin_label>/icons/` — SVG icons for declared entity types (per `spec-grid-icon.md`)

Depending on what the plugin contributes, it may also contain:

- `models/` — TAP-managed model types (required when `[models]` declared)
- `edges/` — edge definition files (required when `[edges]` declared)
- `editors/` — editor descriptors
- `searches/` — search runner callables
- `grift/` — bundled GRIFT seed data (required when `[grift]` declared)
- `templates/` — Django templates
- `api/` — API router modules
- `skills/` — Claude Code skills for plugin-specific automation (see `req-plugin-arch-skills`)
- `migrations/` — Django migrations for plugin models

Convention directories improve readability, but they are not themselves the load contract. Only declared manifest entries and TAP extension hooks define what TAP loads.

The plugin directory is the complete, self-contained unit. Everything needed to understand, validate, test, and maintain the plugin lives inside it — code, specs, skills, icons, seed data, and CI configuration — whether the plugin is still being developed in-tree or has already been split into its own repository.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-layout-1 | Core Required Files | Implemented | Every plugin includes `__init__.py`, `apps.py`, `tap-plugin.toml`, and `tests/`. | |
| req-plugin-arch-layout-2 | Convention Directories Allowed | Implemented | Plugins may organize optional surfaces under standard directories such as `models/`, `edges/`, `editors/`, `searches/`, and `grift/`. | |
| req-plugin-arch-layout-3 | Conventions Do Not Auto-Load | Implemented | Directory presence alone does not define plugin load behavior. | |
| req-plugin-arch-layout-4 | Self-Contained Unit | Implemented | The plugin directory contains everything needed to understand, validate, test, and maintain the plugin. | |
| req-plugin-arch-layout-5 | Specs Directory Expected | Implemented | Plugins should include a `specs/` directory with plugin-specific specifications. | |

### Repository Structure
----
RID: `req-plugin-arch-repo`
Status: `Implemented`

Plugins support a standalone-repository workflow and integrate into a TAP installation as git submodules.

#### Implementation

Each plugin may live in its own git repository. When it does, the plugin repo is the single source of truth for all plugin-owned assets: code, specs, skills, icons, seed data, tests, and CI configuration.

TAP installations integrate plugins by adding them as git submodules under the `plugins/` directory:

```bash
git submodule add <plugin-repo-url> plugins/<plugin_label>
```

This preserves the existing development workflow — plugins appear as local directories under `plugins/`, `INSTALLED_APPS` references them by path, Docker bind-mounts work, and `pytest` discovers their tests — while also supporting an independent plugin version history, CI pipeline, and release cadence when the standalone repo shape is used.

The plugin repo does not need to be a pip-installable package in v0. It is a Django app package that lives on the Python path via the TAP project's directory structure. If a plugin needs its own dependencies (e.g. `boto3`), it may declare them in a `pyproject.toml` and be added as a path dependency in TAP's `pyproject.toml`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-repo-1 | Standalone Repo Supported | Implemented | A plugin may live in its own git repository. | |
| req-plugin-arch-repo-2 | Submodule Integration | Implemented | TAP installations may integrate plugins as git submodules under `plugins/`. | |
| req-plugin-arch-repo-3 | No Pip Package Required | Implemented | Plugins are Django app packages on the Python path; pip packaging is not required in v0. | |
| req-plugin-arch-repo-4 | Independent Version History | Implemented | When a plugin uses its own repository, it has commit history independent of the TAP host repo. | |

#### Future

Later work may define plugin dependency resolution, version compatibility constraints between plugins and TAP core, and automated plugin discovery beyond manual submodule addition.

### Install Resolution And Plugin Registry
----
RID: `req-plugin-arch-install-registry`
Status: `Proposed`

The plugin refactor separates TAP plugin desired state, Python package
resolution, installed-plugin discovery, and TAP runtime registry/reporting into
distinct layers. This prevents uv's package-management metadata from becoming a
surrogate for TAP's plugin model while still using uv for the work it is good at:
repeatable Python dependency resolution and installation.

#### Implementation Direction

The proposed install architecture has four layers:

1. **Boot profile desired state.** The boot profile is the authored source of
   truth for an instance. Its plugin section declares which TAP plugin slugs the
   instance wants, where they may be obtained from, which credential reference is
   used for private sources, which surfaces are enabled, and whether the plugin
   is loaded in checkout/development mode or package/production mode.
2. **uv package resolution.** uv owns Python package resolution and installation.
   The root `pyproject.toml` and `uv.lock` describe the Python environment.
   `uv.lock` records the exact resolved package graph for reproducible installs;
   it does not answer TAP-domain questions such as plugin slugs, enabled
   surfaces, migration status, or health.
3. **Python package discovery.** Installed TAP plugin packages advertise
   themselves through Python package metadata, preferably a `tap.plugins` entry
   point group read with `importlib.metadata.entry_points()`. This discovers
   installed plugin-capable packages without requiring TAP to scan arbitrary
   `site-packages` paths.
4. **TAP plugin registry and reports.** TAP owns the runtime registry/report:
   slug, package/distribution name, resolved version or commit, `app_config`,
   manifest path, requested and loaded surfaces, install mode, provenance,
   generated settings contribution, migration/static outcomes, and load health.
   This registry/report is the auditable source of what TAP attempted, what it
   resolved, what it loaded, and why startup failed if it failed.

The four layers are intentionally not interchangeable. A package may be present
in `uv.lock` without being an enabled TAP plugin. A TAP plugin may be declared in
the boot profile but fail to resolve or load. The registry/report is where those
states become visible to humans and future AI operators.

#### MVP Direction

The installable-plugin MVP targets package/production mode first. TAP should make
uv-backed package installation work end-to-end, then add or refine
checkout/development mode once the production path is proven. Checkout mode
remains important for plugin authoring, debugging, and rapid edits, but it should
not delay the package-mode shape.

In package mode, a plugin is a real Python package with package metadata,
package data for plugin-owned assets, and a `tap.plugins` entry point. The entry
point key must equal the TAP plugin `slug`; this is the simplest validation path
and reinforces that `slug` is the ecosystem identity. The entry point target,
plugin manifest, and generated registry record must agree on slug and
`app_config` before the plugin is added to generated settings.

#### Canonical Plugin Home

TAP should continue to guarantee a stable inspection path at:

```text
plugins/<slug>/
```

In checkout/development mode this path may be a real working tree. In
package/production mode it may be generated state, including a symlink to the
installed package payload inside the active Python environment. That symlink
shape should be spiked before implementation is finalized:

- install a package with uv in the standard way
- locate the installed plugin payload through package metadata
- create or refresh `plugins/<slug>` as a symlink to that payload
- verify Django can load the declared `app_config`
- verify plugin-owned assets such as `tap-plugin.toml`, `grift/`, `skills/`,
  `static/`, and `specs/` remain inspectable from `plugins/<slug>`

The symlink is disposable generated state. If the environment is rebuilt, the
pre-Django boot/install wrapper recreates it from the boot profile, package
metadata, and install report. Provenance lives in the registry/report, not in
`.git` metadata under `plugins/<slug>` for package-mode installs.

Generated plugin-home state needs a dedicated implementation spec before code
lands. At minimum, that spec should define how stale symlinks are detected, when
they are replaced, what happens if a real directory already exists at
`plugins/<slug>`, and how checkout-mode working trees are protected from
package-mode regeneration.

#### Identity Boundaries

TAP plugin identity remains distinct from Python packaging identity:

- `slug` is the globally unique TAP plugin identity.
- Python distribution/package names are uv/PyPA identities and may differ from
  `slug`.
- `app_config` is the Django import path TAP adds to generated settings.
- source URL plus resolved revision/version is provenance, not TAP identity.
- `plugins/<slug>` is a local inspection/materialization path, not necessarily
  the import root in every install mode.

This preserves the existing slug-centered TAP model while allowing production
package installs to use normal Python packaging conventions.

#### Generated Settings

The pre-Django install/boot wrapper writes generated plugin settings before
Django imports project settings. The target setting names are:

- `TAP_PLUGINS`: ordered plugin `app_config` entries generated from the resolved
  boot profile and registry/discovery result
- `TAP_PLUGIN_CONFIG`: plugin-scoped configuration values, initially generated
  as an empty mapping until plugin-specific configuration is specified

`TAP_PLUGINS` is the settings-time bridge into `INSTALLED_APPS`.
`TAP_PLUGIN_CONFIG` reserves the NetBox-like configuration shape without forcing
plugin-specific config into shared infrastructure.

#### Discussion Outcomes (2026-06-26)

Refinements from a George ↔ Claude review of this Codex-authored draft, recorded
inline so the thinking is in one place for a Monday three-way review (Codex's
draft, George reading, these edits). They sharpen the four-layer direction
without changing its shape.

- **Install source: github-first is uv git-source, which *is* package mode —
  not git submodules.** "github-first" must mean a plugin installed as a real
  package from a git URL (`<dist> @ git+https://…@<rev>`), which uv clones to its
  cache, builds, and installs into the venv. It is emphatically **not**
  `git submodule add` (source vendored into the host tree — the prior dependency
  nightmare). Because a uv git-source install and a PyPI install are the *same*
  mechanism (same wheel, same `tap.plugins` entry point, same generated-settings
  path) differing only in the source URL, github-first is strictly **on the
  glide-path**: graduating a plugin to an index is a one-line source change with
  zero rework. The thing proven first is therefore the *packaging shape* (a
  wheel-buildable package + entry point installed from git), not publishing.
  Dev/checkout mode is a uv **path/editable** install of the plugin under active
  edit — distinct from the git-source consume path, and why checkout mode does
  not need the `plugins/<slug>` symlink gymnastics. The spec should say "uv
  git-source install" and explicitly disclaim submodules so the pattern is not
  reintroduced by habit.
- **The running-plugin registry/report is the inspection surface — which weakens
  the `plugins/<slug>` symlink case.** If the authoritative "what is installed /
  enabled + its config + load health" is a queryable report (layer 4 — a
  `manage.py plugins`-style command / generated report now; plugins-as-grid-
  entities, Gryphon-queryable, later), then the filesystem symlink at
  `plugins/<slug>` loses most of its justification: it shrinks to "tooling that
  hardcodes that path" (pytest discovery, bind mounts), solvable without a
  load-bearing symlink-materialization spec. Treat the registry/report as a
  first-class deliverable, not a single ACID line; converge it with `/healthz`
  and the deferred boot report (`req-boot-report`) — all three are "observable
  assembled-instance truth" and should share a shape.
- **The pre-Django install wrapper's home is `docker/entrypoint.sh`.** It is the
  only process-launch slot that runs before Django imports settings, and it
  already hosts `uv sync` + `migrate`. The *logic* is a settings-free Python
  module the entrypoint calls (not bash, not `manage.py` — which would need the
  settings it is generating); it must run **before `migrate`** (so plugin
  migrations apply) and be **idempotent / fast on reboot** (the "reboot just
  works" requirement — already-installed plugins are a no-op, no re-pull). This
  is the next entry in the one-canonical-provisioning-sequence the 2026-06-26
  health/provisioning AAR established (`specs/spec-tap-health-v0.md`,
  `docs/aar/2026-06-26-tap-cache-latent-provisioning.md`).
- **Plugin config is deliberately deferred.** Keep the reserved
  `TAP_PLUGIN_CONFIG` seam empty; samsite continues to carry config in collector
  secrets under `TAP_SECRETS_ROOT`. A formal plugin-config mechanism is its own
  future spec (`spec-plugin-config-v0`), demand-triggered by the first plugin
  whose config genuinely cannot be a secret (e.g. a Google Workspace/IdP plugin
  or per-customer instance config). Reserve the seam; do not fill it now.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-install-registry-1 | Four Layers Defined | Proposed | The architecture distinguishes boot profile desired state, uv package resolution, Python package discovery, and TAP registry/reporting. | |
| req-plugin-arch-install-registry-2 | uv Boundary | Proposed | `uv.lock` is treated as the Python package resolution record, not the TAP plugin registry. | |
| req-plugin-arch-install-registry-3 | TAP Registry Boundary | Proposed | TAP owns the auditable record of plugin slug, package, app config, manifest, surfaces, provenance, generated settings, and load health. | |
| req-plugin-arch-install-registry-4 | Entry Point Discovery | Proposed | Package-mode plugins advertise themselves through a `tap.plugins` Python package entry point whose key equals the TAP plugin slug. | |
| req-plugin-arch-install-registry-5 | Stable Plugin Home | Proposed | TAP guarantees a stable `plugins/<slug>` inspection path across checkout and package install modes. | |
| req-plugin-arch-install-registry-6 | Symlink Spike | Proposed | The refactor spikes package-mode symlinks from `plugins/<slug>` to the installed package payload before finalizing the install shape. | |
| req-plugin-arch-install-registry-7 | Identity Separation | Proposed | The spec keeps TAP slug, Python distribution/package name, Django `app_config`, source provenance, and local install path as separate concepts. | |
| req-plugin-arch-install-registry-8 | Generated Settings Names | Proposed | The generated settings bridge uses `TAP_PLUGINS` and `TAP_PLUGIN_CONFIG`. | |
| req-plugin-arch-install-registry-9 | Package Mode First | Proposed | The MVP proves uv-backed package-mode install before refining checkout/development mode. | |
| req-plugin-arch-install-registry-10 | Generated Home Lifecycle Spec | Proposed | Generated `plugins/<slug>` symlink behavior is specified before implementation, including stale links, existing directories, and checkout-mode protection. | |

### Plugin Skills
----
RID: `req-plugin-arch-skills`
Status: `Implemented`

Plugins may ship Claude Code skills for plugin-specific automation.

#### Implementation

Skills are Claude Code instruction files that automate plugin-specific tasks such as catalog refresh, data collection, or code generation. A plugin's skills live inside the plugin directory at:

```
skills/<skill-name>/SKILL.md
```

Skills ship with the plugin and are part of the plugin's self-contained repo. The plugin author is responsible for skill content and maintenance.

Plugin skills are not automatically discovered by the TAP host's Claude Code session. Plugin authors and users invoke them by directing Claude to read and follow the skill file, or by configuring their own discovery mechanism. TAP does not maintain symlinks, copies, or other indirection between plugin skills and the host project's `skills/` directory.

Skills should reference TAP specs and schemas by path rather than embedding format knowledge, to prevent drift between the skill's instructions and TAP's authoritative format definitions.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-skills-1 | Skills Directory Convention | Implemented | Plugin skills live at `skills/<skill-name>/SKILL.md` inside the plugin directory. | |
| req-plugin-arch-skills-2 | Self-Contained | Implemented | Skills ship with the plugin repo; no host-level indirection required. | |
| req-plugin-arch-skills-3 | No Auto-Discovery Guarantee | Implemented | TAP does not guarantee automatic skill discovery from plugin subdirectories. | |
| req-plugin-arch-skills-4 | Reference By Path | Implemented | Skills reference TAP specs and schemas by path, not embedded format knowledge. | |

#### Future

If Claude Code adds deeper nested skill discovery, plugin skills may become automatically available. Until then, invocation is the plugin author's responsibility.

### Runtime Boundaries
----
RID: `req-plugin-arch-runtime`
Status: `Implemented`

Plugin startup should be contract-driven rather than ad hoc.

#### Implementation

The plugin architecture expects TAP-facing registration to flow through `TapPluginConfig` and the manifest-backed loader behavior. Plugin authors should not rely on hidden side effects in arbitrary module import paths to publish TAP-managed types or other plugin-owned surfaces.

This does not forbid ordinary Python implementation code. It does mean that the plugin's TAP contract should remain inspectable and that startup behavior should preserve the boundaries established by the plugin infrastructure.

A plugin's *configuration* is part of this boundary. A plugin must not place its configuration in `docker-compose.yml`, core settings, or other shared infrastructure — that couples the plugin to the host and breaks the self-contained-unit shape (`req-plugin-arch-layout-4`). Plugins self-configure through plugin-owned mechanisms; in v0 this is on-disk secrets discovered under `TAP_SECRETS_ROOT` (e.g. the AWS Steampipe collector resolving a well-known `SecretRef`). A durable on-grid plugin-configuration model is future work; the removed `AWS_CORE_STEAMPIPE_COLLECTOR` compose entry was this anti-pattern.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-runtime-1 | Contract-Driven Startup | Implemented | TAP-facing startup behavior flows through the plugin contract rather than arbitrary side effects. | |
| req-plugin-arch-runtime-2 | Implementation Still Allowed | Implemented | Plugins may include ordinary implementation code behind the declared contract. | |
| req-plugin-arch-runtime-3 | Inspectable Load Shape | Implemented | A reviewer can understand the plugin's TAP-facing load shape without reading arbitrary startup logic. | |
| req-plugin-arch-runtime-4 | Self-Contained Configuration | Implemented | A plugin's configuration does not live in `docker-compose.yml`, core settings, or other shared infrastructure; plugins self-configure through plugin-owned mechanisms (v0: on-disk secrets under `TAP_SECRETS_ROOT`). | Durable on-grid plugin config is future work. |

### Plugin Type Ownership & DB Isolation
----
RID: `req-plugin-arch-isolation`
Status: `Proposed`

The plugin refactor adopts owner-namespaced plugin types **and** hard-includes per-plugin database-level guards built on that naming. This requirement exists so the refactor *picks both up* rather than rediscovering them.

#### Implementation

- **Type ownership (pick up in the refactor).** Every plugin-contributed type carries its owning plugin's slug inside the identifier string — plugin node types and tables prefixed `<slug>__<name>`, plugin edge types suffixed `<NAME>__<slug>`, core types unqualified. The full design — the plugin-slug traction point (slugs are already unique via Django app-label), the placement rationale, collision-as-loud-lint, reuse-by-qualified-reference, display-strip, and the verbose-explicit-names doctrine — is specified in [`spec-plugin-type-ownership-v0.md`](spec-plugin-type-ownership-v0.md). The refactor is the implementing vehicle; this is the load-bearing cross-reference so it is not forgotten.
- **DB isolation is hard-included, not optional.** The `<slug>__*` table-naming foundation (`req-plugin-type-db-affordance`) MUST be paired in the refactor with actual per-plugin DB-level guards on plugin actions — least-privilege so a malicious or over-reaching plugin cannot directly read/write outside its own namespace and the sanctioned core read surface. This is a deliberate **security edge taken because the cost is near-zero on a surface we are already rewriting** (`spec-security-posture.md`, `req-sec-cheap-edges`): the naming foundation is free during the rename, and it makes per-plugin grants/RLS a configuration concern rather than a future migration. The *naming foundation* is the non-negotiable, build-once part; the *enforcement mechanism* (table-prefix grants/RLS now, Postgres schemas later) may land incrementally, but the refactor must not ship the type rename without laying the guard foundation it enables.
- This sits alongside the standing reality (`req-plugin-arch-runtime`, `req-plugin-arch-nongoals`) that v0 plugins still have broad in-process execution leeway — an honestly-accepted risk (`spec-security-posture.md`, `req-sec-honest-risk`). The DB guard is one cheap, foundational layer of defense-in-depth against that leeway, not a claim of full plugin sandboxing.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-isolation-1 | Type Ownership Adopted | Proposed | The refactor adopts owner-namespaced plugin types per `spec-plugin-type-ownership-v0.md`. | |
| req-plugin-arch-isolation-2 | DB Guard Foundation Laid | Proposed | The `<slug>__*` table-naming foundation is laid in the refactor (non-negotiable, build-once). | |
| req-plugin-arch-isolation-3 | Per-Plugin DB Guards | Proposed | Per-plugin DB-level least-privilege guards are built on that foundation (mechanism may land incrementally; the foundation may not be skipped). | |

### Testing Requirements
----
RID: `req-plugin-arch-tests`
Status: `Implemented`

Every plugin includes tests, including plugin-specific tests for plugin-owned behavior.

#### Implementation

The plugin architecture requires a `tests/` directory in the plugin package and expects authors to include plugin-specific tests consistent with [`spec-plugin-testing.md`](/Users/george/Documents/code/tap/tap_plugins/specs/spec-plugin-testing.md).

Architecturally this means:

- plugins participate in shared plugin validation and framework-level checks
- plugin authors add hand-written tests for plugin-specific behavior
- plugin tests live with the plugin so they evolve with the plugin's domain logic

This requirement exists even for simple plugins. A lightweight plugin may only need a small number of tests, but it should still prove its domain-specific behavior and structural correctness.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-tests-1 | Tests Directory Required | Implemented | Every plugin includes a `tests/` directory. | |
| req-plugin-arch-tests-2 | Plugin-Specific Tests Required | Implemented | Plugin authors include plugin-specific tests for plugin-owned behavior. | |
| req-plugin-arch-tests-3 | Testing Spec Alignment | Implemented | Plugin tests follow the plugin testing specification. | |

### Iterative Development
----
RID: `req-plugin-arch-iterative-dev`
Status: `Implemented`

GRIFT content is versioned and idempotent. Once a batch has been imported, editing the file in place and re-running the importer does nothing — the importer skips batches whose `batch_entity.entity_id` it has already seen (`req-grid-import-grift-identity`). Plugins must therefore pick one of two canonical paths when revising GRIFT content, and must never rely on silent re-import of edited content.

#### Implementation

**Path 1 — Version bump (durable, always valid).**

Create a new batch to carry the change. The batch's `batch_entity.entity_id` is fresh (new UUID, commonly `uuid4()` or `uuid7()`), its name reflects the version (`"<topic> v0.5.0"` → `"<topic> v0.6.0"`), and its description names what changed in this revision. Node and edge `entity_id` values inside the batch stay stable — those are the TAP identities the importer upserts on. The new batch co-exists with the prior batch(es) in the grid's batch history; node/edge changes apply via upsert.

This is the path for:

- Every change that ships in a plugin release.
- Recurring importers that pull authoritative data on a schedule (in which case a stable `batch_entity.entity_id` per source + force re-import on each pull, per the Future note in `spec-grid-import-grift.md`, handles absences as deletions).
- Any environment where `DEBUG=False`.

**Path 2 — Force re-import (dev iteration only, DEBUG-gated).**

For rapid iteration on grift content during active development, the importer exposes `--force-batches=<id>[,<id>...]` to re-execute a batch whose id already exists locally. This is formally specified in `req-grid-import-grift-force-reimport` and its companion requirements:

- `--force-batches=<id>` — re-apply the named batch. Upserts new/changed nodes and edges; leaves unchanged content untouched.
- `--force-batches=<id> --sweep-strict` — only execute if the sweep can run cleanly (`req-grid-import-grift-batch-scoped-sweep` Strict Mode). Aborts before any writes if any candidate would be skipped by guardrails.
- `--force-batches=<id> --purge` — hard-delete swept entities and their batch-scoped history rows instead of tombstoning (`req-grid-import-grift-sweep-purge`). Use when accumulated tombstones from rapid iteration would obscure rather than document the grid.
- Combined: `--force-batches=<id> --sweep-strict --purge` — clean hard-delete or nothing.

All four forms are permitted if and only if `DEBUG=True`. There is no alternate flag, override, settings key, environment variable, or command-line argument that enables force re-import, sweep purge, or their strict variant in any other configuration. The gate prevents dev ergonomics from leaking into production deploys; it is not a security boundary and is not a substitute for deployment discipline.

#### Development

The version-bump path is the answer for nearly every real change. Force re-import exists solely to remove the friction of generating a new UUID and bumping names twenty times an hour while authoring a grift file. Once content stabilizes, the final state should land as a durable version-bumped batch so the grid's batch history reads as a coherent release progression rather than a series of force overwrites.

A common grift-authoring flow:

1. Write the initial `plugins/<name>/grift/<topic>.grift.json` with a v0.1.0 batch.
2. Import once to establish baseline.
3. Iterate: edit content, `import_plugin_grift <name> --force-batches=<id>` (or add `--purge` if orphans accumulate) until the content settles.
4. When done iterating, leave the batch's id alone if the content matches what will ship; otherwise, bump the batch's id + name for the next development wave.

Avoid these patterns:

- **Silent edits without a path**: editing grift content and re-running the importer with no flags. The edit will be ignored and the divergence will cause confusion an hour later. Always pick either path explicitly.
- **Force re-import as a normal operation**: force re-import is a development tool, not a release mechanism. If the change needs to ship, it wants a version-bumped batch with a coherent name and description.
- **Cross-plugin force re-import**: `--force-batches` names specific batch ids; there is no flag to force an entire plugin or file, by design. Don't synthesize one.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-iterative-dev-1 | Version Bump Documented | Implemented | Plugin authors must be able to find canonical guidance that a version-bumped batch is the durable path for revising grift content. | |
| req-plugin-arch-iterative-dev-2 | Force Re-Import Documented | Implemented | Plugin authors must be able to find canonical guidance that `--force-batches` is the dev iteration path, DEBUG-gated, and scoped to specific batch ids. | |
| req-plugin-arch-iterative-dev-3 | Sweep Semantics Named | Implemented | Plugin-scoped guidance references `req-grid-import-grift-batch-scoped-sweep` and its strict/purge variants rather than restating them. | Keeps one authoritative home for sweep rules |
| req-plugin-arch-iterative-dev-4 | Anti-Pattern Called Out | Implemented | Plugin guidance explicitly warns against silent-edit-no-path and against force re-import as a release mechanism. | |


### Plugin Python Dependencies
----
RID: `req-plugin-arch-python-deps`
Status: `Implemented`

Plugins may need third-party Python packages that are not required by TAP core. Examples include cloud SDKs for collectors, service-specific API clients, file parsers, or emitter transports.

The shape is plugin-local dependency ownership without fragmenting a TAP deployment into unrelated Python environments. TAP uses uv workspace support to provide this seam.

Under this shape:

- the root TAP `pyproject.toml` remains the workspace root and owns TAP core dependencies
- the root TAP `pyproject.toml` declares plugin workspace members explicitly (`members = ["plugins/<slug>", ...]`), naming only plugins that carry a `pyproject.toml`
- each plugin that needs Python dependencies may include its own `pyproject.toml`
- plugin-local `pyproject.toml` files declare ordinary Python package dependencies for that plugin
- the root `uv.lock` records one resolved environment for the full TAP installation
- plugin `tap-plugin.toml` continues to declare TAP-facing surfaces such as models, edges, searches, and GRIFT; it does not become a Python package manager manifest

This keeps plugin directories self-contained enough to be split back into standalone repositories later. A plugin-local `pyproject.toml` can move with the plugin repo, while the TAP installation can consume it as a uv workspace member, path dependency, or git dependency depending on the deployment shape.

This requirement provides dependency declaration and lockfile ownership, not runtime import isolation. Python does not prevent one installed package from importing another package present in the same environment. TAP may add validation or linting later to detect undeclared imports, but uv workspace membership alone is not a security boundary.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-python-deps-1 | Workspace Root | Implemented | TAP's root `pyproject.toml` declares a uv workspace whose `members` list names every plugin directory that carries a `pyproject.toml`. | Explicit list (not glob): uv errors when a glob match lacks a `pyproject.toml`. Plugins without local deps stay out of the list. |
| req-plugin-arch-python-deps-2 | Plugin Local pyproject | Implemented | A plugin that needs third-party Python packages declares them in `plugins/<slug>/pyproject.toml`. | Plugin-local dependency metadata moves with a future standalone plugin repo. First proof: `plugins/github_core/pyproject.toml` declaring `PyYAML`. |
| req-plugin-arch-python-deps-3 | Shared Lockfile | Implemented | Plugin dependencies resolve into the root `uv.lock` so a TAP installation has one reproducible Python environment. | `docker/entrypoint.sh` runs `uv sync --all-packages` so workspace member deps land in the runtime venv. |
| req-plugin-arch-python-deps-4 | Manifest Separation | Implemented | `tap-plugin.toml` does not declare uv-installable Python package dependencies; Python dependencies stay in `pyproject.toml`. | The TAP manifest remains the TAP-facing load contract. |
| req-plugin-arch-python-deps-5 | No Isolation Claim | Implemented | The spec explicitly states that uv workspaces do not enforce runtime import isolation between plugins. | Future linting may detect undeclared imports. |
| req-plugin-arch-python-deps-6 | Standalone Repo Compatible | Implemented | The dependency shape works whether a plugin is in-tree, a git submodule, a path dependency, or a standalone repository. | |


### Plugin Hook System
----
RID: `req-plugin-arch-hooks`
Status: `Backlog`

TAP should eventually support a general plugin hook system: explicit extension
points throughout the application where plugins can inject behavior, presentation,
validation, commands, routing, or other narrowly-scoped contributions without
requiring TAP core to know each plugin's implementation details.

This is **not** part of the installable-plugin MVP. It is a named backlog target
so the current packaging/refactor work does not accidentally foreclose it, and so
future demand signals can graduate it into a dedicated spec rather than another
round of ad hoc registries.

#### Prior Art

The target shape is informed by:

- **Simon Willison's DJP plugin system for Django.** DJP is the direct prior art:
  a Django plugin mechanism built on `pluggy`. A Django project configures DJP
  once in `settings.py` (`djp.settings(globals())`) and `urls.py`
  (`djp.urlpatterns()`), after which installed DJP-enabled packages can
  contribute Django settings changes, `INSTALLED_APPS`, middleware, URL
  patterns, and other hook-backed behavior without each plugin requiring custom
  project edits. DJP plugins implement hooks with `@djp.hookimpl` and are
  discovered through Python package entry points.
- **Datasette / LLM plugin lineage.** DJP inherits lessons from Simon Willison's
  broader plugin work: broad documented hook catalogs, tiny hook implementation
  modules, separate plugin packages, and plugin templates / testing patterns that
  make publishing many small plugins practical.
- **NetBox plugin architecture.** NetBox is the closest domain/platform neighbor:
  a Django-based platform for network/infrastructure systems management whose
  plugins are packaged Django apps. NetBox plugins can add models, URLs/views,
  template content injections, navigation items, middleware, plugin-scoped
  configuration, and NetBox-version compatibility limits. Its install path is
  deliberately operational rather than hot-load magic: install the Python package,
  add the plugin to configuration, provide plugin config, run migrations, collect
  static assets, then restart WSGI/workers. Its restrictions are equally useful:
  plugins may not modify core models, register URLs outside `/plugins`, override
  core templates, modify core settings, or disable core components. TAP/Rampart
  is broader and graph-native, but NetBox is a high-value prior-art target for
  both what to adapt and what boundaries to keep.
- **pluggy / pytest-style hooks.** pluggy formalizes the split between hook
  specifications (`hookspec`) and hook implementations (`hookimpl`), validates
  implementations against specifications, supports opt-in arguments so specs can
  evolve without breaking existing implementations, and offers call-order/result
  controls such as first-result hooks.
- **Ushahidi-style application hooks.** The historical value is the product
  capability: hooks placed throughout the app let plugins participate in real
  workflows and UI seams, not only declare data types at startup.

This prior art is inspiration only. TAP should not copy upstream code into the
repository. If `pluggy` itself becomes the chosen implementation dependency, that
requires the normal explicit dependency approval at implementation time.

#### Implementation Direction

A future hook system should have these properties:

- Core TAP apps define named hook specifications at intentional extension points.
- Hook specifications are documented and versioned as part of the owning app's
  spec, not invented by individual plugins.
- Plugins declare hook implementations through an inspectable manifest surface or
  a clearly-named convention module; arbitrary import side effects are not enough.
- Hook invocation is explicit at the callsite: a reader should be able to see
  where plugin behavior may enter a workflow.
- Hook behavior must respect existing TAP boundaries: graph writes still go
  through the service layer, boot remains explicit, and security-sensitive hooks
  require a source-material security pass before implementation.
- Hook failures have defined behavior per hook: fail-loud, collect warnings,
  first-result fallback, or ignore-`None`; no silent catch-all swallowing.
- Hook ordering and result-composition semantics are declared by the hook spec,
  not by plugin load accidents.
- Hook registration and invocation are observable enough for debugging and future
  Paladin-style health checks.

#### Demand Triggers

This backlog item should graduate when TAP has at least one concrete extension
point that is awkward to model with the existing manifest surfaces and registries.
Likely triggers include:

- multiple plugins wanting to contribute to the same page, panel, menu, or action
  surface
- plugin-specific validation or transformation around a shared workflow
- plugin-owned collector lifecycle participation beyond today's explicit boot
  steps
- customer/plugin code needing to add commands, routes, permission checks, or UI
  affordances without modifying TAP core

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-hooks-1 | Backlog Target Named | Backlog | The plugin architecture records a future general hook system as a deliberate target, not an oversight. | |
| req-plugin-arch-hooks-2 | MVP Boundary Preserved | Backlog | The hook system is explicitly outside the installable-plugin MVP. | |
| req-plugin-arch-hooks-3 | Prior Art Captured | Backlog | The future design references DJP/pluggy-style Django hooks, NetBox's Django infrastructure plugin model, and Ushahidi-style app injection points as prior art. | |
| req-plugin-arch-hooks-4 | Explicit Hook Specs | Backlog | Future hooks are owned by core apps as named, documented hook specifications with declared ordering/result/failure semantics. | |
| req-plugin-arch-hooks-5 | No Ad Hoc Side Effects | Backlog | Plugin hook implementations are declared through an inspectable surface or clear convention rather than hidden import side effects. | |
| req-plugin-arch-hooks-6 | Service And Security Boundaries | Backlog | Hook implementations do not bypass TAP service-layer, boot, auth, or security-sensitive boundaries. | |


### v0 Non-Goals
----
RID: `req-plugin-arch-nongoals`
Status: `Proposed`

The current implemented v0 plugin architecture does not yet define or ship:

- plugin dependency resolution or version compatibility constraints
- concrete package-mode install, update, or uninstall workflows
- plugin enablement state or marketplace concepts
- non-Python runtime packaging such as containers
- security review or permission declarations for plugin code
- automatic skill discovery from plugin subdirectories
- general hook/injection points beyond the current manifest-declared surfaces

Those concerns may become future plugin architecture layers, but they are intentionally outside this authoring spec.

#### Future

- Define how TAP handles plugin-declared model types whose Python classes import correctly but whose backing database tables or migration state are not present.
- Define version compatibility constraints between plugins and TAP core.
- Define plugin dependency resolution when plugins depend on other plugins.
- Implement package-mode uv installation, package entry point discovery, generated plugin settings, and the TAP registry/report shape (`req-plugin-arch-install-registry`).
- Define a general hook/injection system once real extension-point demand exists (`req-plugin-arch-hooks`).
