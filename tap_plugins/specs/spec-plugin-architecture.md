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
| req-plugin-arch-skills | [Plugin Skills](#plugin-skills) | Implemented | Plugins may ship Claude Code skills for plugin-specific automation |
| req-plugin-arch-runtime | [Runtime Boundaries](#runtime-boundaries) | Implemented | TAP-facing startup behavior flows through the plugin contract |
| req-plugin-arch-tests | [Testing Requirements](#testing-requirements) | Implemented | Plugins include plugin-specific tests and participate in shared validation |
| req-plugin-arch-iterative-dev | [Iterative Development](#iterative-development) | Implemented | Canonical patterns for revising GRIFT content during and after initial import |
| req-plugin-arch-python-deps | [Plugin Python Dependencies](#plugin-python-dependencies) | Backlog | Future uv workspace shape for plugin-local Python dependency declarations |
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

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-runtime-1 | Contract-Driven Startup | Implemented | TAP-facing startup behavior flows through the plugin contract rather than arbitrary side effects. | |
| req-plugin-arch-runtime-2 | Implementation Still Allowed | Implemented | Plugins may include ordinary implementation code behind the declared contract. | |
| req-plugin-arch-runtime-3 | Inspectable Load Shape | Implemented | A reviewer can understand the plugin's TAP-facing load shape without reading arbitrary startup logic. | |

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
Status: `Backlog`

Plugins may eventually need third-party Python packages that are not required by TAP core. Examples include cloud SDKs for collectors, service-specific API clients, file parsers, or emitter transports.

The desired shape is plugin-local dependency ownership without fragmenting a TAP deployment into unrelated Python environments. TAP should use uv workspace support for this once plugin-specific dependencies become concrete enough to justify the extra metadata.

Under that future shape:

- the root TAP `pyproject.toml` remains the workspace root and owns TAP core dependencies
- the root TAP `pyproject.toml` declares plugin workspace members, likely with a glob such as `plugins/*`
- each plugin that needs Python dependencies may include its own `pyproject.toml`
- plugin-local `pyproject.toml` files declare ordinary Python package dependencies for that plugin
- the root `uv.lock` records one resolved environment for the full TAP installation
- plugin `tap-plugin.toml` continues to declare TAP-facing surfaces such as models, edges, searches, and GRIFT; it does not become a Python package manager manifest

This keeps plugin directories self-contained enough to be split back into standalone repositories later. A plugin-local `pyproject.toml` can move with the plugin repo, while the TAP installation can consume it as a uv workspace member, path dependency, or git dependency depending on the deployment shape.

This requirement provides dependency declaration and lockfile ownership, not runtime import isolation. Python does not prevent one installed package from importing another package present in the same environment. TAP may add validation or linting later to detect undeclared imports, but uv workspace membership alone is not a security boundary.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-arch-python-deps-1 | Workspace Root | Backlog | TAP's root `pyproject.toml` declares a uv workspace that can include plugin directories as members. | Likely `plugins/*`; exact glob depends on which plugin dirs carry `pyproject.toml`. |
| req-plugin-arch-python-deps-2 | Plugin Local pyproject | Backlog | A plugin that needs third-party Python packages may declare them in `plugins/<slug>/pyproject.toml`. | Plugin-local dependency metadata moves with a future standalone plugin repo. |
| req-plugin-arch-python-deps-3 | Shared Lockfile | Backlog | Plugin dependencies resolve into the root `uv.lock` so a TAP installation has one reproducible Python environment. | |
| req-plugin-arch-python-deps-4 | Manifest Separation | Backlog | `tap-plugin.toml` does not declare uv-installable Python package dependencies; Python dependencies stay in `pyproject.toml`. | The TAP manifest remains the TAP-facing load contract. |
| req-plugin-arch-python-deps-5 | No Isolation Claim | Backlog | The spec explicitly states that uv workspaces do not enforce runtime import isolation between plugins. | Future linting may detect undeclared imports. |
| req-plugin-arch-python-deps-6 | Standalone Repo Compatible | Backlog | The dependency shape works whether a plugin is in-tree, a git submodule, a path dependency, or a standalone repository. | |


### v0 Non-Goals
----
RID: `req-plugin-arch-nongoals`
Status: `Proposed`

This specification does not define:

- plugin dependency resolution or version compatibility constraints
- install or uninstall workflows beyond git submodule add/remove
- plugin enablement state or marketplace concepts
- non-Python runtime packaging such as containers
- security review or permission declarations for plugin code
- automatic skill discovery from plugin subdirectories
- implementation of plugin-local Python dependency resolution

Those concerns may become future plugin architecture layers, but they are intentionally outside this authoring spec.

#### Future

- Define how TAP handles plugin-declared model types whose Python classes import correctly but whose backing database tables or migration state are not present.
- Define version compatibility constraints between plugins and TAP core.
- Define plugin dependency resolution when plugins depend on other plugins.
- Define the uv workspace implementation for plugin-local Python dependencies once the first plugin requires packages not otherwise needed by TAP core.
- Define automated plugin discovery beyond manual submodule addition and `INSTALLED_APPS` registration.
