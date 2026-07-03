# Plugin Validation Specification

## Philosophy

Plugin validation is an author-facing TAP capability for confirming that a plugin is structurally sound before the author tries to use it in a live TAP installation. The validator should exercise the same TAP codepaths used by the application wherever possible so that plugin authors do not have to guess whether a passing validation result actually corresponds to real TAP behavior.

In v0, plugin validation is intentionally narrow. It validates one plugin at a time, starting from an explicit plugin root directory, and focuses on structural correctness. This keeps the first version useful for day-to-day plugin authoring without prematurely coupling the validator to full Django startup or runtime execution.

The validator is a TAP feature, not a third-party lint layer. It should live inside `tap_plugins`, share TAP's own manifest and validation code, provide stable machine-readable output, and also be convenient to use from the command line during development and in CI.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Shared Codepaths | Validation reuses TAP's real plugin validation logic wherever possible |
| 2. | Author-Friendly | A plugin author can validate one plugin root directly from the CLI |
| 3. | Machine-Readable | Validation results can be consumed in CI via stable JSON output |
| 4. | Evolvable | The capability starts with structural validation and leaves room for deeper future levels |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-plugin-validate-scope | [Validation Scope](#validation-scope) | Implemented | One plugin root at a time; three validation levels |
| req-plugin-validate-home | [Validation Package Home](#validation-package-home) | Implemented | Capability lives in `tap_plugins/validate/` |
| req-plugin-validate-codepaths | [Shared TAP Codepaths](#shared-tap-codepaths) | Implemented | Reuse TAP manifest and plugin validation logic |
| req-plugin-validate-levels | [Validation Levels](#validation-levels) | Implemented | Three cumulative levels: structure, loads, runs |
| req-plugin-validate-loads | [Loads Level](#loads-level) | Implemented | Class-path validation via Django import system |
| req-plugin-validate-runs | [Runs Level](#runs-level) | Implemented | Service-layer smoke tests with rollback transaction |
| req-plugin-validate-identity | [Identity Coherence](#identity-coherence) | Implemented | Structure check: package-mode identity chain agrees on disk |
| req-plugin-validate-deps | [Declared Dependencies](#declared-dependencies) | Implemented | Structure check: cross-plugin imports are declared in depends_on |
| req-plugin-validate-cli | [Standalone CLI](#standalone-cli) | Implemented | Module-based CLI for structure level; loads/runs via management command |
| req-plugin-validate-mgmt | [Management Command](#management-command) | Implemented | Django management command supporting all levels |
| req-plugin-validate-output | [Validation Output](#validation-output) | Implemented | Human output and structured JSON output |
| req-plugin-validate-schema | [JSON Schema Contract](#json-schema-contract) | Implemented | Result JSON is validated against a schema |
| req-plugin-validate-strict | [Strict Mode](#strict-mode) | Implemented | Warnings may be promoted to failure |
| req-plugin-validate-help | [Help Output](#help-output) | Implemented | `-h` and `--help` provide a man-page-style help screen |
| req-plugin-validate-exit | [Exit Codes](#exit-codes) | Implemented | Stable process exit behavior |
| req-plugin-validate-future | [Future Work](#future-work) | Proposed | Directory-of-plugins mode and richer output deferred |

### Validation Scope
----
RID: `req-plugin-validate-scope`
Status: `Implemented`

Plugin validation validates exactly one plugin root directory at a time.

#### Implementation

In v0, the validator accepts one required filesystem path that must point to the plugin root. The validator does not auto-discover plugin roots from parent directories and does not validate multiple plugins in one invocation.

The implemented validation scope for v0 is structural validation only. This includes:

- manifest parsing
- manifest structural validation
- path and convention checks
- package-mode identity coherence (slug / namespace / distribution / entry-point agree) — req-plugin-validate-identity
- declared-dependency coverage (every cross-plugin import is declared in `depends_on`) — req-plugin-validate-deps
- declared class-path validation where supported by existing TAP manifest validation logic
- warnings for undeclared convention files where TAP already emits them

The validator should use TAP's real validation functions rather than duplicating their logic.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-scope-1 | One Plugin Input | Implemented | The validator accepts exactly one plugin root path per invocation. | |
| req-plugin-validate-scope-2 | Plugin Root Required | Implemented | The input path must point at the plugin root itself. | |
| req-plugin-validate-scope-3 | Structure Level Implemented | Implemented | v0 implements structural validation only. | |

### Validation Package Home
----
RID: `req-plugin-validate-home`
Status: `Implemented`

The validation capability lives in its own package subtree under `tap_plugins/validate/`.

#### Implementation

`tap_plugins/validate/` is the primary home for:

- the shared validation service
- output schema files
- CLI support code
- any package-local helpers required by the validator

The specification document remains under `tap_plugins/specs/`, but runtime validation assets should live with the validation implementation.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-home-1 | Package Locality | Implemented | Runtime validation code lives under `tap_plugins/validate/`. | |
| req-plugin-validate-home-2 | Schema Locality | Implemented | The JSON Schema for validator output lives under `tap_plugins/validate/`. | |

### Shared TAP Codepaths
----
RID: `req-plugin-validate-codepaths`
Status: `Implemented`

The validator reuses TAP's own plugin validation codepaths wherever possible.

#### Implementation

The validator should call the same manifest and structural validation functions used by TAP plugin loading, rather than re-implementing manifest parsing, path checking, or class validation in a separate subsystem.

This is allowed to import TAP modules directly. Independence from Django in v0 means the validator should not require Django app startup for the implemented `structure` level, not that it must avoid TAP imports.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-codepaths-1 | TAP Imports Allowed | Implemented | The validator may import TAP modules directly. | |
| req-plugin-validate-codepaths-2 | Shared Manifest Logic | Implemented | Manifest parsing and validation reuse TAP's real implementation codepaths. | |
| req-plugin-validate-codepaths-3 | No Parallel Validation Logic | Implemented | The validator does not maintain a divergent second copy of manifest validation logic. | |

### Validation Levels
----
RID: `req-plugin-validate-levels`
Status: `Implemented`

Plugin validation defines named levels that progressively exercise more of the plugin's TAP contract.

#### Implementation

The validator defines these level names:

- `structure` — manifest parsing, path checks, edge file validation, package-mode identity coherence (req-plugin-validate-identity), and declared-dependency coverage (req-plugin-validate-deps). No Django required.
- `loads` — all structure checks plus class-path validation via Django's import system. Requires Django app startup.
- `runs` — all loads checks plus service-layer smoke tests (create_node, create_edge, grift_import). Requires Django app startup and a database. Runs inside an atomic transaction that rolls back so no data is persisted.

Each level is a superset of the previous level: `runs` includes everything from `loads`, which includes everything from `structure`.

The default level is `structure`.

`structure` is available from the standalone CLI. `loads` and `runs` require Django and are only available via the management command. The standalone CLI rejects `loads` and `runs` with a message directing the user to the management command.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-levels-1 | Three Level Names | Implemented | The validator defines `structure`, `loads`, and `runs`. | |
| req-plugin-validate-levels-2 | Default Structure Level | Implemented | The default level is `structure`. | |
| req-plugin-validate-levels-3 | Levels Are Cumulative | Implemented | Each level includes all checks from the previous level. | |
| req-plugin-validate-levels-4 | CLI Structure Only | Implemented | The standalone CLI supports `structure` only; `loads` and `runs` direct users to the management command. | |
| req-plugin-validate-levels-5 | Loads Requires Django | Implemented | `loads` requires Django app startup for class-path validation. | |
| req-plugin-validate-levels-6 | Runs Requires Database | Implemented | `runs` requires a database and exercises the service-layer write pipeline. | |
| req-plugin-validate-levels-7 | Runs Rollback Transaction | Implemented | `runs`-level checks execute inside an atomic transaction that rolls back, leaving no persisted data. | |

### Loads Level
----
RID: `req-plugin-validate-loads`
Status: `Implemented`

The `loads` level validates that manifest-declared classes can be imported and pass TAP contract checks.

#### Implementation

`loads` runs all `structure` checks, then additionally:

- imports each declared model class path and verifies `ENTITY_TYPE` matches the manifest slug
- imports each declared editor class path and verifies it is a concrete `EditorDescriptor` with matching entity type
- imports each declared search callable path and verifies it is callable
- for each model with a non-empty `ENTITY_ICON`, validates the icon key is kebab-case and the corresponding SVG file exists in the plugin's static icons directory per `spec-grid-icon.md`

These checks reuse `validate_manifest_classes()` from `tap_plugins/manifest.py` and `validate_icon_key()` from `tap_grid/icon.py`, which are the same codepaths used at startup and render time.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-loads-1 | Model Class Validation | Implemented | Each declared model class imports and has matching ENTITY_TYPE. | |
| req-plugin-validate-loads-2 | Editor Class Validation | Implemented | Each declared editor class imports, instantiates, and matches entity type. | |
| req-plugin-validate-loads-3 | Search Callable Validation | Implemented | Each declared search callable imports and is callable. | |
| req-plugin-validate-loads-4 | Shared Codepath | Implemented | Loads-level class validation reuses TAP's real manifest validation functions. | |
| req-plugin-validate-loads-5 | Icon Validation | Implemented | Models with ENTITY_ICON must have a valid kebab-case key and a corresponding SVG file in the plugin's static icons directory. | |

### Runs Level
----
RID: `req-plugin-validate-runs`
Status: `Implemented`

The `runs` level validates that the plugin's TAP surfaces work through the service-layer write pipeline.

#### Implementation

`runs` runs all `loads` checks, then additionally:

- attempts `create_node` for each declared model type using an auto-generated minimal payload
- attempts `create_edge` for each declared edge type that has explicit sources and targets
- attempts `grift_import` for each declared GRIFT bundle

All `runs`-level checks execute inside an atomic database transaction that rolls back at the end. This exercises the full write pipeline (validation, entity creation, FLIP stamping, history recording) without persisting any data.

**Auto-payload generation:** For each model type, the validator builds a minimal payload from `CREATE_REQUIRED` and `FIELD_CRUD_SCHEMA`. It generates synthetic values by JSON Schema type:

- `"string"` → `"test"` (or `"t" * minLength` if minLength is specified)
- `"integer"` → `1`
- `"boolean"` → `false`
- `"object"` → `{}`
- `"array"` → `[]`
- nullable types (e.g. `["string", "null"]`) → the non-null synthetic value

If `create_node` fails with the auto-generated payload, that is a real validation failure indicating misconfigured schemas or required fields.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-runs-1 | Create Node Smoke Test | Implemented | `create_node` succeeds for each declared model type with an auto-generated payload. | |
| req-plugin-validate-runs-2 | Create Edge Smoke Test | Implemented | `create_edge` succeeds for edge types with explicit source and target constraints. | |
| req-plugin-validate-runs-3 | GRIFT Import Smoke Test | Implemented | `grift_import` succeeds for each declared GRIFT bundle. | |
| req-plugin-validate-runs-4 | Transaction Rollback | Implemented | All runs-level checks execute inside an atomic transaction that rolls back. | |
| req-plugin-validate-runs-5 | Auto Payload Generation | Implemented | Payloads are auto-generated from FIELD_CRUD_SCHEMA and CREATE_REQUIRED without plugin-authored fixtures. | |

### Identity Coherence
----
RID: `req-plugin-validate-identity`
Status: `Implemented`

A structure-level check verifies that a package-mode plugin's identity chain agrees end to end on the source tree.

#### Implementation

`req-plugin-arch-identity` requires a single identity to run unbroken across four surfaces: the manifest `slug`, the namespace package segment (`tap_plugin/<slug>/`), the distribution name (`tap-plugin-<slug>`), and the `tap.plugins` entry-point key. The pre-boot conformance gate (`conformance_gate` in `tap/preboot.py`) enforces this from *installed* distribution metadata. This check enforces the same chain from the *on-disk source tree*, so a drift is caught at author time — before the plugin is ever built or installed.

The `identity-coherence` check (structure level, no Django) verifies, for a package-mode plugin:

- the namespace package directory is `<plugin_root>/tap_plugin/<slug>/` (segment equals the manifest slug);
- `pyproject.toml` exists at the plugin root and its `[project].name` equals `dist_name_for_slug(slug)` (`tap-plugin-<slug-with-dashes>`);
- the `[project.entry-points."tap.plugins"]` table declares exactly one key, equal to the slug, whose target is under the `tap_plugin.<slug>` namespace.

The check reuses `dist_name_for_slug`, `NAMESPACE_PACKAGE`, and `TAP_PLUGINS_ENTRY_POINT_GROUP` from `tap/preboot.py` rather than re-deriving the conventions. Legacy flat plugins (manifest at the plugin root, no `tap_plugin/` namespace and no `pyproject.toml`) predate the identity chain and are reported as *not applicable* (pass) rather than failed.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-identity-1 | Namespace Segment | Implemented | The `tap_plugin/<segment>/` directory name equals the manifest slug. | |
| req-plugin-validate-identity-2 | Distribution Name | Implemented | `pyproject.toml` `[project].name` equals `dist_name_for_slug(slug)`. | |
| req-plugin-validate-identity-3 | Entry-Point Key | Implemented | The `tap.plugins` entry-point group declares exactly one key equal to the slug, targeting the `tap_plugin.<slug>` namespace. | |
| req-plugin-validate-identity-4 | Legacy Flat Inapplicable | Implemented | Flat legacy layouts (no namespace/pyproject) report the check as not applicable rather than failing. | |
| req-plugin-validate-identity-5 | Reuses Pre-Boot Conventions | Implemented | The check imports the naming conventions from `tap/preboot.py` rather than re-deriving them. | |

### Declared Dependencies
----
RID: `req-plugin-validate-deps`
Status: `Implemented`

A structure-level check verifies that every cross-plugin import is declared in the manifest's `depends_on`.

#### Implementation

`req-plugin-arch-dependencies` requires each plugin's manifest `depends_on` to cover every *other* plugin it imports, so the boot install order can satisfy them. The pre-boot dependency-consistency guard (`dependency_consistency_guard` in `tap/preboot.py`) enforces `declared ⊇ observed` across a whole profile. This check applies the same rule to a single plugin at author time.

The `declared-dependencies` check (structure level, no Django) computes:

- `observed` — the set of *other* plugin slugs imported via `tap_plugin.<other>`, from a static AST scan of the plugin's package directory (`tap.plugin_deps.scan_observed_imports`);
- `declared` — the slugs in the manifest's `depends_on` (`tap.plugin_deps.read_declared_depends_on`).

The check fails for each slug in `observed - declared` (an undeclared import). Declared-but-unimported edges (pure data/vocabulary dependencies — e.g. one plugin seeding another plugin's node types by string reference, never importing it) are legitimate and reported as informational, not flagged. The check reuses `tap.plugin_deps` — the same scanner the pre-boot guard uses.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-deps-1 | Undeclared Import Fails | Implemented | Each `tap_plugin.<other>` import with no matching `depends_on` slug fails the check. | |
| req-plugin-validate-deps-2 | Declared Import Passes | Implemented | An imported plugin declared in `depends_on` passes. | |
| req-plugin-validate-deps-3 | Data Dependency Allowed | Implemented | A declared-but-unimported dependency (data/vocabulary) is informational, not a failure. | |
| req-plugin-validate-deps-4 | Reuses Scanner | Implemented | The check reuses `tap.plugin_deps` rather than re-implementing import scanning. | |

### Standalone CLI
----
RID: `req-plugin-validate-cli`
Status: `Implemented`

Plugin validation is available as a standalone module-based CLI.

#### Implementation

The validator is invocable from the command line as:

```bash
python -m tap_plugins.validate_plugin /path/to/plugin
```

The CLI should:

- accept one plugin root path
- default to `structure`
- support `--json`
- support `--strict`
- support future-compatible `--level`
- print human-readable output by default

The CLI is intended for local development and CI use.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-cli-1 | Module Entry Point | Implemented | Validation is runnable via `python -m tap_plugins.validate_plugin`. | |
| req-plugin-validate-cli-2 | Single Path Argument | Implemented | The CLI accepts one required plugin root path. | |
| req-plugin-validate-cli-3 | JSON Mode | Implemented | The CLI supports a machine-readable JSON output mode. | |
| req-plugin-validate-cli-4 | Strict Mode | Implemented | The CLI supports `--strict`. | |

### Management Command
----
RID: `req-plugin-validate-mgmt`
Status: `Implemented`

Plugin validation is also available as a Django management command.

#### Implementation

The management command is invocable as:

```bash
python manage.py validate_plugin /path/to/plugin
```

The management command is a thin wrapper around the shared validation service. It should not contain a second implementation of the validation rules.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-mgmt-1 | Management Command Exists | Implemented | Validation is available as `manage.py validate_plugin`. | |
| req-plugin-validate-mgmt-2 | Thin Wrapper | Implemented | The management command delegates to the shared validation service. | |

### Validation Output
----
RID: `req-plugin-validate-output`
Status: `Implemented`

The validator produces both human-readable and machine-readable output.

#### Implementation

By default, the validator prints human-readable output suitable for a plugin author at a terminal.

With `--json`, the validator emits a structured result document containing:

- top-level run metadata
- overall pass/fail state
- summary counts
- per-check entries
- warnings and errors represented through those entries

The output should be verbose enough for debugging and CI diagnostics. A per-check model is required so callers do not lose detail.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-output-1 | Human Output Default | Implemented | Default output is human-readable. | |
| req-plugin-validate-output-2 | JSON Output Optional | Implemented | `--json` emits structured machine-readable output. | |
| req-plugin-validate-output-3 | Per-Check Entries Required | Implemented | JSON output includes per-check entries, not only rolled-up summaries. | |

### JSON Schema Contract
----
RID: `req-plugin-validate-schema`
Status: `Implemented`

Validator JSON output conforms to a published JSON Schema and is validated against it before emission.

#### Implementation

The validator publishes a JSON Schema under `tap_plugins/validate/` describing the result envelope for `--json` output.

When JSON output is requested:

- the validator constructs the result document
- validates it against the published schema
- emits the validated document

This keeps the validator honest and gives CI consumers a stable contract.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-schema-1 | Schema Published | Implemented | A JSON Schema for validator output exists under `tap_plugins/validate/`. | |
| req-plugin-validate-schema-2 | Output Self-Validated | Implemented | The validator validates its own JSON output against that schema. | |
| req-plugin-validate-schema-3 | Stable Result Shape | Implemented | The schema defines a stable machine-readable result envelope. | |

### Strict Mode
----
RID: `req-plugin-validate-strict`
Status: `Implemented`

Warnings may be promoted to failures.

#### Implementation

In default mode, warnings do not fail the validation run.

With `--strict`, any warning causes the run to fail. This is intended for CI or teams that want convention drift to be treated as a hard error.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-strict-1 | Default Warnings Non-Fatal | Implemented | Warnings do not fail validation by default. | |
| req-plugin-validate-strict-2 | Strict Promotes Warnings | Implemented | `--strict` causes warnings to fail validation. | |

### Help Output
----
RID: `req-plugin-validate-help`
Status: `Implemented`

The validator provides a man-page-style help screen.

#### Implementation

The CLI should support `-h` and `--help` with output that reads like a concise man page, including:

- name
- synopsis
- description
- arguments
- options
- exit status
- examples

The management command should also surface matching option descriptions through Django's normal help system.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-help-1 | CLI Help Exists | Implemented | `-h` and `--help` print a man-page-style help screen. | |
| req-plugin-validate-help-2 | Management Help Exists | Implemented | The management command exposes corresponding help text. | |

### Exit Codes
----
RID: `req-plugin-validate-exit`
Status: `Implemented`

The validator uses stable exit codes.

#### Implementation

In v0:

- `0` means validation succeeded
- `1` means validation failed
- `2` means usage or configuration error

Unsupported future levels should be treated as usage/configuration errors until implemented.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-validate-exit-1 | Success Exit Code | Implemented | Success exits with code `0`. | |
| req-plugin-validate-exit-2 | Validation Failure Exit Code | Implemented | Validation failure exits with code `1`. | |
| req-plugin-validate-exit-3 | Usage Error Exit Code | Implemented | Usage or configuration errors exit with code `2`. | |

### Future Work
----
RID: `req-plugin-validate-future`
Status: `Proposed`

The following items are explicitly deferred:

- validating a directory of plugins in one invocation
- validating that manifest-declared model types have corresponding database tables and migration state required for plugin load
- richer machine-readable output variants beyond the v0 result schema

These are future expansions of the validator, not requirements for the initial authoring workflow.
