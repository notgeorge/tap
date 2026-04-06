# Plugin Manifest v0 Specification

## Philosophy

The plugin manifest exists so a TAP plugin can declare its load surface in a way that is inspectable before arbitrary Python startup logic runs. In v0 the manifest should be concrete enough for humans and loaders to rely on, but small enough that it does not become a second programming language.

The manifest is not a general package descriptor. It is TAP-specific metadata for TAP plugin loading. Its job is to answer a narrow set of questions consistently:

- what plugin is this
- what TAP-managed model types does it contribute
- what bundled GRIFT files does it publish

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Concrete      | The manifest defines exact v0 fields rather than high-level intent only |
| 2. | Strict        | Unknown keys and malformed entries are rejected                 |
| 3. | Declarative   | The manifest describes plugin surfaces without embedding loader logic |
| 4. | Reviewable    | A human can understand a plugin's TAP load surface from one file |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-plugin-manifest-v0-file | [Manifest File And Format](#manifest-file-and-format) | Implemented | Fixed file name and TOML format |
| req-plugin-manifest-v0-top | [Top-Level Fields](#top-level-fields) | Implemented | Exact required and optional root fields |
| req-plugin-manifest-v0-models | [Model Entries](#model-entries) | Implemented | Exact fields for declared TAP model types |
| req-plugin-manifest-v0-grift | [GRIFT Entries](#grift-entries) | Implemented | Exact fields for declared GRIFT bundles |
| req-plugin-manifest-v0-paths | [Path Rules And Conventions](#path-rules-and-conventions) | Implemented | Required directories, relative paths, data/ subdirectory support |
| req-plugin-manifest-v0-validation | [Validation Rules](#validation-rules) | Implemented | Strict validation and loader checks |
| req-plugin-manifest-v0-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Explicitly deferred manifest concerns |

### Manifest File And Format
----
RID: `req-plugin-manifest-v0-file`
Status: `Proposed`

The plugin manifest is a TOML file with a fixed name.

#### Status Details
Proposed as the concrete follow-on to the plugin load lifecycle spec.

#### Implementation
In v0:

- the manifest file name is `tap-plugin.toml`
- the file lives at the plugin root
- the manifest format is TOML
- the manifest is purely declarative

The loader reads `tap-plugin.toml` as the canonical declaration file for plugin identity, TAP-managed model declarations, and bundled GRIFT declarations.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-manifest-v0-file-1 | Fixed File Name | Proposed | The plugin manifest file is named `tap-plugin.toml`. | |
| req-plugin-manifest-v0-file-2 | Plugin Root Location | Proposed | The manifest lives at the plugin root. | |
| req-plugin-manifest-v0-file-3 | TOML Format | Proposed | The manifest is encoded as TOML. | |
| req-plugin-manifest-v0-file-4 | Declarative Only | Proposed | The manifest contains declarations only, not loader hooks or executable behavior. | |

#### Future
Later work may define how the plugin root is discovered or whether manifests can be generated, but v0 assumes a direct file at the plugin root.

### Top-Level Fields
----
RID: `req-plugin-manifest-v0-top`
Status: `Proposed`

The v0 manifest has a small, explicit top-level shape.

#### Status Details
Proposed to eliminate ambiguity about required identity and version fields.

#### Implementation
The top-level manifest fields are:

Required:

- `manifest_version`: string
- `plugin_version`: string
- `slug`: string
- `name`: string

Optional:

- `description`: string

Optional sections:

- `models`
- `grift`

Unknown top-level keys are invalid.

The top-level fields mean:

- `manifest_version`: the version of the manifest schema understood by TAP
- `plugin_version`: the version of the plugin itself
- `slug`: the canonical TAP plugin slug
- `name`: the human-readable plugin name
- `description`: optional short human-readable description

In v0, `manifest_version` should be `"0"`.

### Example

```toml
manifest_version = "0"
plugin_version = "0.1.0"
slug = "lotr"
name = "Lord of the Rings"
description = "Middle-earth example plugin."
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-manifest-v0-top-1 | Required Identity Fields | Proposed | The manifest requires `manifest_version`, `plugin_version`, `slug`, and `name`. | |
| req-plugin-manifest-v0-top-2 | Optional Description | Proposed | `description` is optional. | |
| req-plugin-manifest-v0-top-3 | Optional Sections | Proposed | `models` and `grift` sections may be omitted when empty. | |
| req-plugin-manifest-v0-top-4 | Unknown Top-Level Keys Rejected | Proposed | Unknown top-level keys are invalid. | |
| req-plugin-manifest-v0-top-5 | Manifest Version Fixed | Proposed | v0 manifests use `manifest_version = "0"`. | |

#### Future
Later versions may add compatibility ranges, authorship, licensing, dependencies, or capability flags.

### Model Entries
----
RID: `req-plugin-manifest-v0-models`
Status: `Proposed`

The manifest declares TAP-managed plugin model types explicitly.

#### Status Details
Proposed to make model loading TAP-type-oriented rather than module-oriented.

#### Implementation
Model declarations use TOML array-of-table entries:

```toml
[[models]]
slug = "character"
class = "plugins.lotr.models.character.Character"
```

Each `models` entry requires exactly these fields:

- `slug`: string
- `class`: string

Unknown keys inside a `models` entry are invalid.

Field meanings:

- `slug`: the TAP type slug contributed by this model
- `class`: the concrete Python import path for the TAP-managed model class

The loader validates that:

- the class path resolves
- the class is a concrete TAP-managed model class
- the class agrees with the declared `slug`

Duplicate model slugs inside one manifest are invalid.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-manifest-v0-models-1 | Array Of Tables | Proposed | Model declarations use `[[models]]` TOML entries. | |
| req-plugin-manifest-v0-models-2 | Exact Fields | Proposed | Each model entry requires exactly `slug` and `class`. | |
| req-plugin-manifest-v0-models-3 | Unknown Keys Rejected | Proposed | Unknown keys inside a model entry are invalid. | |
| req-plugin-manifest-v0-models-4 | Concrete Class Path | Proposed | `class` names a concrete Python class path, not just a module path. | |
| req-plugin-manifest-v0-models-5 | Loader Validates Class | Proposed | The loader validates that the declared class exists and is a concrete TAP-managed model. | |
| req-plugin-manifest-v0-models-6 | Loader Validates Slug Match | Proposed | The loader validates that the declared class matches the declared TAP type slug. | |
| req-plugin-manifest-v0-models-7 | Duplicate Slugs Invalid | Proposed | Duplicate model slugs in one manifest are invalid. | |

#### Future
Later versions may add optional display metadata here or may source more of that data from the model class itself.

### GRIFT Entries
----
RID: `req-plugin-manifest-v0-grift`
Status: `Proposed`

The manifest declares bundled GRIFT files explicitly.

#### Status Details
Proposed to make data publication explicit and reviewable.

#### Implementation
GRIFT declarations use TOML array-of-table entries:

```toml
[[grift]]
name = "core-data"
path = "data/core-data.grift.json"
```

Each `grift` entry requires exactly these fields:

- `name`: string
- `path`: string

Unknown keys inside a `grift` entry are invalid.

Field meanings:

- `name`: a logical bundle name unique within the plugin
- `path`: the relative path from the plugin root to the GRIFT file

The loader validates at startup that each declared `path` exists.
GRIFT parsing and content validation happen when import is invoked.

Duplicate GRIFT bundle names inside one manifest are invalid.
Duplicate GRIFT paths inside one manifest are invalid.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-manifest-v0-grift-1 | Array Of Tables | Proposed | GRIFT declarations use `[[grift]]` TOML entries. | |
| req-plugin-manifest-v0-grift-2 | Exact Fields | Proposed | Each GRIFT entry requires exactly `name` and `path`. | |
| req-plugin-manifest-v0-grift-3 | Unknown Keys Rejected | Proposed | Unknown keys inside a GRIFT entry are invalid. | |
| req-plugin-manifest-v0-grift-4 | Relative Path | Proposed | `path` is stored relative to the plugin root. | |
| req-plugin-manifest-v0-grift-5 | Startup Path Validation | Proposed | Startup validation confirms that each declared GRIFT path exists. | |
| req-plugin-manifest-v0-grift-6 | Import-Time GRIFT Validation | Proposed | GRIFT parsing and content validation happen when import is invoked. | |
| req-plugin-manifest-v0-grift-7 | Duplicate Names Invalid | Proposed | Duplicate GRIFT bundle names in one manifest are invalid. | |
| req-plugin-manifest-v0-grift-8 | Duplicate Paths Invalid | Proposed | Duplicate GRIFT bundle paths in one manifest are invalid. | |

#### Future
Later versions may add import policy fields, checksums, descriptions, or content categories per bundle.

### Path Rules And Conventions
----
RID: `req-plugin-manifest-v0-paths`
Status: `In Development`

The manifest requires specific directories and supports `data/` subdirectory organization without requiring sub-paths to be declared.

#### Status Details
Updated from Proposed: `models/` is now a required directory, not a convention. `data/` allows optional sub-directories as an organizational convenience that does not change loader semantics.

#### Implementation
In v0:

- `models/` is a **required** directory at the plugin root. TAP-managed model code must live under `models/`. A plugin without a `models/` directory is invalid.
- `data/` is the required directory for GRIFT files. Plugin GRIFT bundles are declared with paths relative to the plugin root (e.g. `data/core-data.grift.json`).

`data/` sub-directories are allowed as a convenience for organizing large or multi-category data sets (e.g. `data/nodes/characters.grift.json`, `data/edges.grift.json`). Sub-directory paths are declared explicitly in the manifest `[[grift]]` entries the same way as top-level paths. TAP does not require that sub-directories be declared separately; only file-level GRIFT entries are declarable.

TAP does not load every file found in `models/` or `data/` automatically. Only manifest-declared entries are part of the plugin load contract.

Manifest-declared paths are evaluated relative to the plugin root.

If files exist in `models/` or `data/` (including sub-directories) but are not declared in the manifest:

- TAP warns that they are undeclared
- TAP does not treat them as loadable plugin surfaces

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-manifest-v0-paths-1 | Required Directories Defined | Implemented | v0 defines `models/` as a required directory and `data/` as the required GRIFT directory. | Changed from convention to required for `models/`. |
| req-plugin-manifest-v0-paths-2 | No Implicit Autoload | Implemented | Files in `models/` or `data/` are not loaded solely because they are present. | |
| req-plugin-manifest-v0-paths-3 | Relative To Plugin Root | Implemented | Manifest paths are resolved relative to the plugin root. | |
| req-plugin-manifest-v0-paths-4 | Undeclared Files Warn | Implemented | Undeclared files in convention directories produce warnings, not startup errors. | |
| req-plugin-manifest-v0-paths-5 | Data Subdirectories Allowed | Implemented | `data/` may contain sub-directories for organizational convenience without requiring sub-path declarations. | |
| req-plugin-manifest-v0-paths-6 | Models Directory Required | Implemented | A plugin missing a `models/` directory at its root is invalid. | |

#### Future
Later tooling may scaffold these directories automatically or offer commands to reconcile undeclared files with manifest entries. Sub-directory conventions within `data/` may be standardized if patterns emerge across plugins.

### Validation Rules
----
RID: `req-plugin-manifest-v0-validation`
Status: `Proposed`

The v0 manifest is intentionally strict.

#### Status Details
Proposed to make the manifest reliable as a loader contract rather than informal documentation.

#### Implementation
General validation rules:

- the manifest must parse as TOML
- all required top-level fields must be present
- unknown keys are rejected at the top level and inside `models` and `grift` entries
- required field values must be strings
- empty strings are invalid for required fields

Model validation rules:

- `slug` values must be unique within `models`
- `class` values should be unique within `models`
- each class path must resolve to a concrete TAP-managed model class
- each resolved class must agree with its declared slug

GRIFT validation rules:

- `name` values must be unique within `grift`
- `path` values must be unique within `grift`
- each `path` must exist at startup
- path traversal outside the plugin root is invalid

The manifest spec is strict by default and does not define a `_reserved` escape hatch in v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-manifest-v0-validation-1 | TOML Parse Required | Proposed | The manifest must parse as valid TOML. | |
| req-plugin-manifest-v0-validation-2 | Required Strings Present | Proposed | Required fields must exist and be non-empty strings. | |
| req-plugin-manifest-v0-validation-3 | Unknown Keys Rejected Everywhere | Proposed | Unknown keys are rejected at the top level and in section entries. | |
| req-plugin-manifest-v0-validation-4 | Plugin-Root Path Safety | Proposed | GRIFT paths may not escape the plugin root. | |
| req-plugin-manifest-v0-validation-5 | Model Resolution Enforced | Proposed | Declared model class paths must resolve to valid concrete TAP-managed model classes. | |
| req-plugin-manifest-v0-validation-6 | Strict By Default | Proposed | v0 does not define a generic reserved or future-extension section. | |

#### Future
If v1 needs smoother evolution, it may introduce controlled extension points after more real plugins exist.

### v0 Non-Goals
----
RID: `req-plugin-manifest-v0-nongoals`
Status: `Proposed`

The v0 manifest intentionally covers only a narrow plugin surface.

#### Status Details
Proposed so the first concrete schema does not grow into a full plugin platform descriptor.

#### Implementation
The v0 manifest does not define:

- plugin dependencies
- API router declarations
- web/editor/panel declarations
- task or job declarations
- install or uninstall metadata
- enablement state
- plugin-defined edge declaration fields
- per-bundle GRIFT import modes

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-manifest-v0-nongoals-1 | Dependencies Deferred | Proposed | v0 does not define dependency fields. | |
| req-plugin-manifest-v0-nongoals-2 | UI And API Surfaces Deferred | Proposed | v0 does not define API, web, or editor declarations. | |
| req-plugin-manifest-v0-nongoals-3 | Edge Fields Deferred | Proposed | v0 does not yet define the manifest fields for plugin-defined edge declarations. | |
| req-plugin-manifest-v0-nongoals-4 | Per-Bundle Import Modes Deferred | Proposed | v0 does not add per-bundle GRIFT import mode fields. | |

#### Future
The next likely addition is an explicit edge declaration mechanism that fits alongside the current `models` and `grift` sections without reintroducing ad hoc Python startup metadata.
