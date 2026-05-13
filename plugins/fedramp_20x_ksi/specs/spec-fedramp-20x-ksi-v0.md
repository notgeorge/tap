# FedRAMP 20x KSI Plugin Specification

## Philosophy

The FedRAMP 20x KSI plugin models the Key Security Indicator (KSI) catalog defined by the FedRAMP 20x program. Its job is to make the current KSI themes and individual indicators available as first-class TAP graph nodes so other plugins, dashboards, and analyses can attach evidence, observations, and compliance posture to specific indicators.

The plugin stays narrow on purpose. It is responsible for catalog representation and lifecycle, not for evidence collection, crosswalks to other frameworks, or compliance scoring. Those are deliberately deferred so the v0 catalog can stabilize before downstream consumers depend on richer semantics.

The FedRAMP 20x program is itself evolving on a rolling-release cadence. The plugin treats the machine-readable consolidated rules published by FedRAMP at [github.com/FedRAMP/rules](https://github.com/FedRAMP/rules) as the canonical source of truth. Catalog content enters the grid via two paths: (1) a one-time `grift/ksi-seed.grift.json` snapshot shipped with the plugin to bootstrap fresh installs, and (2) the runtime `KSICollector` registered with `tap_cares`, which fetches the upstream and submits a change-only GRIFT batch when re-run. See `spec-fedramp-20x-ksi-collector.md` for the collector.

The plugin's TAP-managed types use the `compliance: fedramp-20x` default dimension. Framework identity is carried by the dimension rather than by a singleton root model, leaving room for other compliance frameworks (NIST 800-53, ISO 27001, etc.) to coexist later in parallel plugins under the same `compliance` dimension key.

## Vocabulary

FedRAMP 20x introduces new terminology that differs from both the legacy FedRAMP impact-baseline system and early 20x drafts. The plugin uses the current source-authoritative vocabulary throughout:

- **Theme** — a top-level grouping of related security outcomes, identified by a code like `KSI-IAM`. The machine-readable catalog defines 10 themes as of the `2026.0.1.1-wip-preview` rules release.
- **Indicator** — a single measurable security outcome within a theme, identified by a code like `KSI-IAM-MFA`. Each indicator has a requirement statement, applicable FedRAMP Certification Classes, and (optionally) per-class statement variants. Source field `statement` carries the requirement text; source field `varies_by_class` provides class-specific alternative text.
- **Certification Class** — the FedRAMP 20x classification system, values `a`, `b`, `c`, `d`, replacing the legacy Low/Moderate/High impact-baseline system. Approximate legacy mapping:
  - **Class A** — pilot / preparation; replaces the "FedRAMP Ready" designation. Most requirements apply only partially at this class.
  - **Class B** — roughly corresponds to legacy FedRAMP Low / Li-SaaS.
  - **Class C** — roughly corresponds to legacy FedRAMP Moderate.
  - **Class D** — roughly corresponds to legacy FedRAMP High; requires an agency sponsor.
- **Controls** — NIST 800-53 Rev 5 control IDs referenced by an indicator (e.g. `ac-2.2`, `ia-12`). Carried as a simple list in v0; crosswalking them to actual NIST control nodes via graph edges is deferred work tracked in `req-fedramp-20x-ksi-nist-crosswalk`.
- **KSI** — the generic term for the Key Security Indicator program. Used when referring to the program as a whole.

Phases (Phase One, Phase Two) are a program-level concept. The plugin tracks whichever phase is currently authoritative and does not model phase as a field on the catalog itself.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Narrow         | v0 models only KSI themes and indicators; no evidence, scoring, or framework crosswalk edges |
| 2. | Runtime-Collected | Catalog updates land via the `tap_cares` `KSICollector`; the plugin ships a single bootstrap seed |
| 3. | Dimensioned    | Every TAP-managed type uses the `compliance: fedramp-20x` default dimension |
| 4. | Lifecycle-Aware | Indicators carry an explicit status (draft/published/deprecated) so catalog churn is visible |
| 5. | Source-Faithful | Catalog fields preserve the shape published by FedRAMP rather than reinterpreting |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-scope | [Plugin Scope](#plugin-scope) | Implemented | Defines what the plugin covers and excludes |
| req-fedramp-20x-ksi-dimensions | [Dimension Strategy](#dimension-strategy) | Implemented | `compliance: fedramp-20x` default dimensions plus seeded dimension node |
| req-fedramp-20x-ksi-models | [Model Catalog](#model-catalog) | Implemented | `ksi_theme` and `ksi_indicator` |
| req-fedramp-20x-ksi-status | [Indicator Status](#indicator-status) | Implemented | Indicators carry `status` of `draft`, `published`, or `deprecated` |
| req-fedramp-20x-ksi-theme-status | [Theme Status](#theme-status) | Backlog | Capture upstream theme `status` (e.g. `"stable"`) on `KsiTheme` so future theme lifecycle transitions are visible |
| req-fedramp-20x-ksi-classes | [Indicator Certification Classes](#indicator-certification-classes) | Implemented | Indicators carry a `classes` list identifying applicable FedRAMP Certification Classes |
| req-fedramp-20x-ksi-class-variants | [Class-Specific Statement Variants](#class-specific-statement-variants) | Implemented | Indicators preserve source `varies_by_class` shape when present |
| req-fedramp-20x-ksi-controls | [NIST Control References](#nist-control-references) | Implemented | Indicators carry a `controls` list of NIST 800-53 control IDs |
| req-fedramp-20x-ksi-nist-crosswalk | [NIST Control Crosswalk Edges](#nist-control-crosswalk-edges) | Backlog | Promote `controls` list entries to `MAPS_TO_CONTROL` edges once a NIST 800-53 plugin exists |
| req-fedramp-20x-ksi-metadata | [Source Metadata Fields](#source-metadata-fields) | Implemented | Indicators carry `updated_log`, `terms`, `reference`, `reference_url` from source |
| req-fedramp-20x-ksi-edges | [Edge Types](#edge-types) | Implemented | Single `CONTAINS_INDICATOR` edge from theme to indicator |
| req-fedramp-20x-ksi-icons | [Icons](#icons) | Implemented | Generic type-level icons bound to models; 10 per-theme SVGs shipped as static assets |
| req-fedramp-20x-ksi-reference | [Reference Data Distribution](#reference-data-distribution) | Implemented | Plugin ships a single `grift/ksi-seed.grift.json` snapshot; ongoing updates land via the runtime collector |
| req-fedramp-20x-ksi-refresh | [Catalog Refresh Workflow](#catalog-refresh-workflow) | Deprecated | Superseded by runtime `KSICollector` — see `spec-fedramp-20x-ksi-collector.md` |
| req-fedramp-20x-ksi-wave-schema | [Wave Description Schema](#wave-description-schema) | Deprecated | Wave format removed with refresh tooling; runtime batches use `tap.fedramp_20x_ksi.collection-v0` |
| req-fedramp-20x-ksi-safety | [Refresh Safety Model](#refresh-safety-model) | Deprecated | Safety checks reimplemented inside the runtime collector — see `spec-fedramp-20x-ksi-collector.md` |
| req-fedramp-20x-ksi-plugin-validation | [Plugin Validation](#plugin-validation) | Implemented | Structure-level validation passes; loads/runs awaiting INSTALLED_APPS integration |
| req-fedramp-20x-ksi-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Explicitly deferred concerns |

### Plugin Scope
----
RID: `req-fedramp-20x-ksi-scope`
Status: `Implemented`

The plugin models the FedRAMP 20x KSI catalog: themes (e.g. KSI-CNA, KSI-IAM, KSI-MLA) and the individual indicators within each theme.

#### Implementation

The plugin covers:

- KSI themes as first-class TAP nodes
- individual KSI indicators as first-class TAP nodes
- the structural relationship from a theme to its indicators
- the indicator requirement statement (and per-class statement variants when present)
- NIST 800-53 control references carried on each indicator as a list
- indicator source metadata: changelog, term references, external references
- explicit indicator lifecycle status (`draft`, `published`, `deprecated`)
- per-indicator applicable FedRAMP Certification Classes (`a`, `b`, `c`, `d`)

The plugin excludes in v0:

- a `framework` model representing FedRAMP 20x as a node — framework identity is carried by the `compliance: fedramp-20x` dimension instead
- `MAPS_TO_CONTROL` edges from indicators to NIST control nodes (deferred to `req-fedramp-20x-ksi-nist-crosswalk`)
- `REQUIRES_EVIDENCE` edges or modeled evidence-requirement nodes
- compliance scoring, posture, or assessment outcomes
- crosswalks to other frameworks (ISO 27001, SOC 2, etc.)
- assessment-organization-specific data such as 3PAO findings, ATO packages, or POA&Ms
- per-CSP compliance state
- FedRAMP program phase as a modeled field
- `KSI-ABF` (Authorization by FedRAMP) — present in the FedRAMP docs site but not in the machine-readable consolidated rules; handled elsewhere as FRD/FRR material
- FRD (definitions) and FRR (requirements) documents from the consolidated rules — out of scope for v0 KSI plugin

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-scope-1 | Catalog Only | Implemented | v0 covers themes and indicators as catalog data, not evidence or scoring. | |
| req-fedramp-20x-ksi-scope-2 | No Framework Node | Implemented | The plugin does not define a `framework` model in v0; framework identity lives in the dimension. | |
| req-fedramp-20x-ksi-scope-3 | No Crosswalk Edges | Implemented | v0 does not model crosswalk edges to other frameworks; NIST control IDs are preserved as a list field only. | See `req-fedramp-20x-ksi-nist-crosswalk` |
| req-fedramp-20x-ksi-scope-4 | Phase Not Modeled | Implemented | FedRAMP program phase is not a field on catalog entries; the plugin tracks whichever phase is currently authoritative. | |
| req-fedramp-20x-ksi-scope-5 | KSI Only | Implemented | v0 models only the `KSI` section of the consolidated rules; FRD/FRR documents are out of scope. | |

### Dimension Strategy
----
RID: `req-fedramp-20x-ksi-dimensions`
Status: `Implemented`

Every TAP-managed type in the plugin declares `{"compliance": "fedramp-20x"}` as its default dimensions.

#### Implementation

The `compliance` dimension key is intended as the shared root for all compliance-framework plugins. Future plugins for NIST 800-53, ISO 27001, SOC 2, etc. should use the same `compliance` key with their own framework-specific value, e.g. `{"compliance": "nist-800-53-rev5"}`.

This convention keeps dimension-scoped queries useful: a single filter on `compliance` dimension key returns all compliance-framework data regardless of source framework, while filtering on the value scopes to one framework.

The plugin seeds a dimension node for `compliance: fedramp-20x` at `grift/dimension.grift.json`, following the precedent set by `aws_core` (`tap.cloud: aws`) and `genericom` (`tap.env: genericom-prod`). The node carries a human-readable description of what the dimension covers and anchors the dimension as a graph-queryable entity. The dimension node is static plugin-author-authored metadata and is distinct from the catalog waves described in `req-fedramp-20x-ksi-reference` — it ships on day one and does not churn with the KSI catalog.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-dimensions-1 | Default Dimensions Required | Implemented | Each model declares `DEFAULT_DIMENSIONS = {"compliance": "fedramp-20x"}`. | |
| req-fedramp-20x-ksi-dimensions-2 | Edge Default Dimensions Required | Implemented | Each edge definition declares `default_dimensions: {"compliance": "fedramp-20x"}`. | |
| req-fedramp-20x-ksi-dimensions-3 | Shared Compliance Key | Implemented | The `compliance` dimension key is intended as the convention for all future compliance-framework plugins. | |
| req-fedramp-20x-ksi-dimensions-4 | Dimension Node Seeded | Implemented | The plugin seeds a dimension node at `grift/dimension.grift.json` describing `compliance: fedramp-20x`. | Ships on day one; not part of the KSI catalog wave cadence |

### Model Catalog
----
RID: `req-fedramp-20x-ksi-models`
Status: `Implemented`

The plugin declares two TAP-managed models: `ksi_theme` and `ksi_indicator`.

#### Implementation

| Model | Purpose | Fields |
| --- | --- | --- |
| `ksi_theme` | A top-level KSI grouping like KSI-CNA or KSI-IAM | `code`, `name`, `short_name`, `web_name`, `description` |
| `ksi_indicator` | An individual indicator within a theme, e.g. KSI-IAM-MFA | `code`, `name`, `description`, `classes`, `class_variants`, `controls`, `updated_log`, `terms`, `reference`, `reference_url`, `status` |

Field intent:

**`ksi_theme`:**

- **`code`**: source `id` — canonical FedRAMP theme identifier (e.g. `"KSI-IAM"`). Regex `^KSI-[A-Z]{3}$`. Stable across refreshes and used for upsert keys.
- **`name`**: source `name` — human-readable name (e.g. `"Identity and Access Management"`). Canonical entity-metadata field per `req-grid-entity-metadata`.
- **`short_name`**: source `short_name` — three-letter code (e.g. `"IAM"`).
- **`web_name`**: source `web_name` — URL-friendly slug used by fedramp.gov.
- **`description`**: optional TAP-managed description. Not sourced from FedRAMP (themes do not ship descriptions in the consolidated rules); kept for TAP canonical-metadata alignment and future human-authored content.

**`ksi_indicator`:**

- **`code`**: canonical FedRAMP indicator identifier (e.g. `"KSI-IAM-MFA"`). Regex `^KSI-[A-Z]{3}-[A-Z0-9]{3}$`. Stable across refreshes and used for upsert keys.
- **`name`**: source `name` — short title. Canonical entity-metadata field per `req-grid-entity-metadata`.
- **`description`**: maps from source `statement` when the indicator uses the direct statement form. When the indicator uses `varies_by_class` instead, `description` is empty and `class_variants` carries the per-class statements.
- **`classes`**: list of FedRAMP Certification Classes to which the indicator applies. Detailed in `req-fedramp-20x-ksi-classes`.
- **`class_variants`**: source `varies_by_class` preserved verbatim when present, else null. Detailed in `req-fedramp-20x-ksi-class-variants`.
- **`controls`**: list of NIST 800-53 control IDs. Detailed in `req-fedramp-20x-ksi-controls`.
- **`updated_log`**: source `updated` array preserved verbatim. Detailed in `req-fedramp-20x-ksi-metadata`.
- **`terms`**: source `terms` list preserved verbatim. Detailed in `req-fedramp-20x-ksi-metadata`.
- **`reference`**, **`reference_url`**: optional source `reference` and `reference_url` strings.
- **`status`**: indicator lifecycle state. Detailed in `req-fedramp-20x-ksi-status`.

The plugin should not invent validation, naming, or grouping conventions that diverge from what FedRAMP publishes. The refresh workflow is responsible for pulling source into these field shapes; the catalog model stays close to source.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-models-1 | Two Model Set | Implemented | v0 declares exactly two TAP-managed models: `ksi_theme` and `ksi_indicator`. | |
| req-fedramp-20x-ksi-models-2 | Stable Codes For Upsert | Implemented | `code` is the stable identifier used by the refresh workflow for upserts on both models. | Theme regex `^KSI-[A-Z]{3}$`; indicator regex `^KSI-[A-Z]{3}-[A-Z0-9]{3}$` |
| req-fedramp-20x-ksi-models-3 | Source-Faithful Fields | Implemented | Catalog content fields preserve FedRAMP's published shape rather than re-interpreting it. | |

#### Open Questions

- Whether `code` should be enforced unique within `compliance: fedramp-20x` at the database level, or only enforced by the refresh workflow's upsert logic. v0 starts with workflow-level enforcement and may tighten later.

### Indicator Status
----
RID: `req-fedramp-20x-ksi-status`
Status: `Implemented`

Each `ksi_indicator` carries a `status` field with one of three values: `draft`, `published`, `deprecated`.

#### Implementation

The status vocabulary in v0 is intentionally small:

- **`draft`**: the indicator appears in a work-in-progress source release but is not yet part of the stable consolidated rules
- **`published`**: the indicator is current and authoritative in the consolidated rules
- **`deprecated`**: the indicator was previously published but has since been retired or superseded

`status` is a plugin-authored derived field, not a source field. The refresh workflow sets it based on where the indicator appears in source. When an indicator disappears from source between refresh runs, the refresh workflow emits a wave entry marking it `deprecated` rather than deleting it, so historical references in other graph data remain meaningful.

Per-status transition history is not tracked separately by the plugin in v0. Once the TAP history system is wired up for plugin models, indicator history will be captured through the standard mechanism.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-status-1 | Three-Value Status | Implemented | `status` is one of `draft`, `published`, `deprecated`. | Enforced via `FIELD_VALIDATION_SCHEMA` enum |
| req-fedramp-20x-ksi-status-2 | Required On Indicator | Implemented | Every `ksi_indicator` has an explicit `status`; there is no implicit default. | Declared in `CREATE_REQUIRED` |
| req-fedramp-20x-ksi-status-3 | Refresh Marks Removed As Deprecated | Proposed | The refresh workflow marks indicators that disappear from source as `deprecated` rather than deleting them. | Contract declared; implementation lives in the refresh skill |

### Theme Status
----
RID: `req-fedramp-20x-ksi-theme-status`
Status: `Backlog`

Upstream KSI themes carry a `status` field (currently `"stable"` for all eleven themes in the 2026 Public Preview) that we drop on ingest. `KsiTheme` has no `status` column and `_theme_state_from_source` in the KSI collector ignores the upstream value. The moment FedRAMP transitions a theme out of `"stable"` (e.g. marks one `"deprecated"` or `"draft"`) we'd silently keep presenting it as live.

The pinned source schema already declares `status` as an optional string on each theme, so the field is acknowledged but unused. This requirement closes the loop: persist it on `KsiTheme` and surface it on admin/compliance views the way indicator status already is.

#### Implementation (when picked up)

- Add `status: CharField(max_length=16, blank=True, default="")` to `KsiTheme`, with a permissive validation schema (string, optional). The KSI indicator's three-value enum (`draft` / `published` / `deprecated`) is a useful precedent but the theme-side vocabulary should be re-checked against FedRAMP's actual usage at implementation time rather than presumed.
- Extend `_theme_state_from_source` in `plugins/fedramp_20x_ksi/collectors/ksi_catalog.py` to read `theme.get("status", "")` into the source-state dict.
- Add a migration.
- Decide whether the existing CARES admin / KSI compliance surfaces should expose theme status visually (icon, pill, etc.) or just store it as data.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-theme-status-1 | Persisted On Theme | Backlog | `KsiTheme` carries a `status` field populated from upstream `theme.status`. | |
| req-fedramp-20x-ksi-theme-status-2 | Collector Reads Source Field | Backlog | `KSICollector._theme_state_from_source` extracts `status` into the state dict so the diff sees changes. | |
| req-fedramp-20x-ksi-theme-status-3 | Vocabulary Pinned At Implementation | Backlog | The accepted set of theme-status values is declared in the spec when this requirement is picked up — not presumed to match the indicator status enum. | Check FedRAMP usage before pinning |

### Indicator Certification Classes
----
RID: `req-fedramp-20x-ksi-classes`
Status: `Implemented`

Each `ksi_indicator` carries a `classes` list identifying the FedRAMP Certification Classes to which it applies.

#### Implementation

The v0 class vocabulary is:

- `a` — pilot / preparation (replaces legacy "FedRAMP Ready")
- `b` — roughly legacy FedRAMP Low / Li-SaaS
- `c` — roughly legacy FedRAMP Moderate
- `d` — roughly legacy FedRAMP High (requires agency sponsor)

`classes` is a list because indicators commonly apply to multiple classes. The refresh workflow derives this list from source: when an indicator has a direct `statement`, all classes from the theme-level applicability apply; when an indicator has `varies_by_class`, the keys of that object are the applicable classes.

The field is required and must contain at least one value.

Classes are stored as a list field rather than modeled as separate `ksi_class` nodes because:

- the class vocabulary is small, closed, and publisher-controlled
- no per-class metadata beyond the identifier has v0 relevance
- graph traversal on classes is not a v0 use case

A future requirement may promote classes to first-class nodes with `APPLIES_AT_CLASS` edges if cross-plugin class alignment becomes relevant.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-classes-1 | Class List Field | Implemented | `ksi_indicator` declares a `classes` list field. | |
| req-fedramp-20x-ksi-classes-2 | Four-Value Vocabulary | Implemented | v0 class values are `a`, `b`, `c`, `d`; unknown values are rejected. | Enforced via `FIELD_VALIDATION_SCHEMA` enum |
| req-fedramp-20x-ksi-classes-3 | Non-Empty Required | Implemented | Every indicator has at least one class. | Enforced via `minItems: 1` |

#### Future

Promote classes to first-class `ksi_class` nodes with `APPLIES_AT_CLASS` edges if cross-plugin class alignment becomes relevant.

### Class-Specific Statement Variants
----
RID: `req-fedramp-20x-ksi-class-variants`
Status: `Implemented`

Each `ksi_indicator` carries an optional `class_variants` JSON field preserving the source `varies_by_class` structure when present.

#### Implementation

Source indicators come in two shapes:

1. **Direct statement** — the indicator has a single `statement` string applicable to all declared classes. The plugin stores the text in `description` and leaves `class_variants` null.
2. **Varies by class** — the indicator's statement differs per class, carried in source as `varies_by_class: {<class>: {statement: "..."}, ...}`. The plugin stores the source object verbatim in `class_variants` and leaves `description` empty.

The source shape is preserved rather than normalized because the format is still evolving (FedRAMP 20x is in WIP preview) and committing to a derived schema risks drift. Downstream consumers that need a single representative statement resolve it by looking at `description` first and falling back to `class_variants[<preferred-class>].statement`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-class-variants-1 | Source Shape Preserved | Implemented | `class_variants` stores the source `varies_by_class` object verbatim. | |
| req-fedramp-20x-ksi-class-variants-2 | Mutually Exclusive With Description | Implemented | An indicator populates either `description` (direct statement) or `class_variants` (varies by class), not both. | |
| req-fedramp-20x-ksi-class-variants-3 | Optional Field | Implemented | `class_variants` is null when the indicator uses a direct statement. | |

### NIST Control References
----
RID: `req-fedramp-20x-ksi-controls`
Status: `Implemented`

Each `ksi_indicator` carries a `controls` list of NIST 800-53 Rev 5 control IDs referenced by the indicator.

#### Implementation

The field is a list of strings following the source format, e.g. `["ac-2.2", "ac-2.3", "ia-12", "ia-12.2"]`. Empty list is valid when source has no referenced controls.

In v0 the `controls` field is a simple list. The plugin does not create graph edges to NIST control nodes because no NIST control nodes exist in TAP yet. Once a NIST 800-53 plugin lands, those list entries can be promoted to `MAPS_TO_CONTROL` edges without changing the plugin's data model — tracked in `req-fedramp-20x-ksi-nist-crosswalk`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-controls-1 | Controls List Field | Implemented | `ksi_indicator` declares a `controls` list field holding NIST 800-53 control IDs. | |
| req-fedramp-20x-ksi-controls-2 | Source Format Preserved | Implemented | Control IDs are stored in the format used by source (lowercase, dotted, e.g. `ac-2.2`). | |
| req-fedramp-20x-ksi-controls-3 | No Graph Edges In V0 | Implemented | The plugin does not create edges from indicators to NIST control nodes in v0. | See `req-fedramp-20x-ksi-nist-crosswalk` |

### NIST Control Crosswalk Edges
----
RID: `req-fedramp-20x-ksi-nist-crosswalk`
Status: `Backlog`

Promote each `ksi_indicator.controls` entry to a `MAPS_TO_CONTROL` edge from the indicator to an actual NIST 800-53 Rev 5 control node.

#### Status Details

Backlog. Requires a future `nist_800_53` (or similarly-named) plugin to provide NIST control nodes as the edge target. Until then, `controls` stays as a list field carrying source data.

#### Future

Once NIST control nodes exist in TAP:

- define a `MAPS_TO_CONTROL` edge in this plugin (or in a cross-framework crosswalk plugin)
- the refresh workflow creates `MAPS_TO_CONTROL` edges from each indicator to each referenced control node at wave-import time
- the `controls` list field remains as the source-of-truth blob; edges derive from it
- any control ID in the list that does not resolve to an existing NIST control node is logged rather than failing the import

Open questions when this is picked up:

- Does the crosswalk edge live in this plugin, the NIST plugin, or a dedicated crosswalk plugin?
- How are control ID format differences (e.g. `ac-2.2` vs `AC-2(2)`) normalized at edge-creation time?
- What happens when FedRAMP source references a control that has since been removed from NIST Rev 6?

### Source Metadata Fields
----
RID: `req-fedramp-20x-ksi-metadata`
Status: `Implemented`

Each `ksi_indicator` preserves source metadata fields: `updated_log`, `terms`, `reference`, and `reference_url`.

#### Implementation

- **`updated_log`**: JSONField preserving the source `updated` array verbatim. Each entry is `{date: "YYYY-MM-DD", comment: "..."}`. Empty list is valid.
- **`terms`**: list of strings preserving the source `terms` array verbatim. Each string is a term name referenced by the indicator's statement (e.g. `"Information Resource"`, `"Machine-Based (Information Resources)"`). Empty list is valid. Graph edges to TAP term nodes are out of scope for v0 (no term-node model exists yet).
- **`reference`**: optional string preserving the source `reference` field.
- **`reference_url`**: optional URL string preserving the source `reference_url` field.

These fields are preserved rather than parsed or normalized because (1) they are evolving WIP in source, and (2) v0 has no concrete consumer that requires structured access. Downstream consumers can inspect them directly.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-metadata-1 | Updated Log Preserved | Implemented | `updated_log` stores the source `updated` array verbatim. | |
| req-fedramp-20x-ksi-metadata-2 | Terms Preserved | Implemented | `terms` stores the source `terms` list verbatim. | |
| req-fedramp-20x-ksi-metadata-3 | References Preserved | Implemented | `reference` and `reference_url` store source reference fields as optional strings. | |

#### Future

Promote `terms` list entries to `REFERENCES_TERM` edges once a term-node model exists in TAP.

### Edge Types
----
RID: `req-fedramp-20x-ksi-edges`
Status: `Implemented`

The plugin declares one edge type: `CONTAINS_INDICATOR`.

#### Implementation

| Edge | Direction | Description |
| --- | --- | --- |
| `CONTAINS_INDICATOR` | `ksi_theme` → `ksi_indicator` | A theme contains an individual indicator |

The plugin does not define edges for cross-indicator relationships, indicator dependencies, framework-to-theme containment, NIST control crosswalks, or term references in v0. Those are covered by deferred requirements (`req-fedramp-20x-ksi-nist-crosswalk`) or parked in field-level storage until concrete consumers emerge.

If a future `framework` model is introduced (in this plugin or in a future `compliance_core` plugin), a `CONTAINS_THEME` edge would naturally accompany it. Adding that later is non-breaking for `CONTAINS_INDICATOR`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-edges-1 | Single Edge | Implemented | v0 declares exactly one edge type: `CONTAINS_INDICATOR`. | |
| req-fedramp-20x-ksi-edges-2 | Theme To Indicator Direction | Implemented | The edge points from `ksi_theme` to `ksi_indicator`. | |
| req-fedramp-20x-ksi-edges-3 | Dimensioned Edge | Implemented | The edge declares `default_dimensions: {"compliance": "fedramp-20x"}`. | |

### Icons
----
RID: `req-fedramp-20x-ksi-icons`
Status: `Implemented`

The plugin binds one canonical icon to `ksi_theme` and one to `ksi_indicator` for v0, consistent with TAP's v1 type-level icon contract. The full per-theme icon set ships as static assets for use by dashboards and templates that look up icons by theme code, and for future promotion to canonical icons once instance-level icon overrides land in `tap_grid`.

#### Implementation

TAP's v1 icon contract (`spec-grid-icon.md` `req-grid-icon-type`) binds one icon per entity type via the class-level `ENTITY_ICON` attribute. Per-instance icon overrides are tracked as `req-grid-icon-instance` and are currently `Backlog`. Within that constraint, v0 binds:

- `ksi_theme` → `ENTITY_ICON = "ksi-theme"` (one generic theme icon)
- `ksi_indicator` → `ENTITY_ICON = "ksi-indicator"` (one generic indicator icon)

The plugin also ships 10 per-theme SVGs as static assets under the same `static/fedramp_20x_ksi/icons/` directory, matching the theme codes in the machine-readable consolidated rules:

| Icon key | Theme code | Title |
| --- | --- | --- |
| `ksi-cmt.svg` | KSI-CMT | Change Management |
| `ksi-cna.svg` | KSI-CNA | Cloud Native Architecture |
| `ksi-ced.svg` | KSI-CED | Cybersecurity Education |
| `ksi-iam.svg` | KSI-IAM | Identity and Access Management |
| `ksi-inr.svg` | KSI-INR | Incident Response |
| `ksi-mla.svg` | KSI-MLA | Monitoring, Logging, and Auditing |
| `ksi-piy.svg` | KSI-PIY | Policy and Inventory |
| `ksi-rpl.svg` | KSI-RPL | Recovery Planning |
| `ksi-svc.svg` | KSI-SVC | Service Configuration |
| `ksi-scr.svg` | KSI-SCR | Supply Chain Risk |

These 10 files are not bound to any `ENTITY_ICON` in v0. They are available to dashboards and templates that resolve a static URL directly from a theme's `code` field, and are positioned to become canonical per-theme icons without asset-rework once `req-grid-icon-instance` is implemented.

The exact theme set tracks whatever FedRAMP publishes in the machine-readable consolidated rules. If FedRAMP changes theme composition, the icon set and this table update accordingly through the refresh workflow and a spec revision; the list above reflects the `2026.0.1.1-wip-preview` rules release.

Icons follow the TAP `currentColor` convention rather than vendor brand colors. FedRAMP does not publish per-theme iconography; the icons in this plugin are TAP-authored representations.

Known v0 visual limitation: graph views using the default `ENTITY_ICON` resolution path (Cytoscape, etc.) show all themes with the same icon and all indicators with the same icon. Per-theme visual differentiation in v0 requires consumers to look up the appropriate SVG directly by theme `code`. This limitation resolves when `req-grid-icon-instance` is implemented.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-icons-1 | One Type Icon Each | Implemented | `ksi_theme` and `ksi_indicator` each declare one canonical `ENTITY_ICON`. | |
| req-fedramp-20x-ksi-icons-2 | Per-Theme Assets Shipped | Implemented | The 10 per-theme SVGs ship as static assets under `static/fedramp_20x_ksi/icons/`. | Available for template/dashboard lookup by theme code |
| req-fedramp-20x-ksi-icons-3 | CurrentColor Convention | Implemented | Icons use `currentColor` for theming, not vendor brand colors. | |
| req-fedramp-20x-ksi-icons-4 | Ready For Instance Overrides | Implemented | Per-theme SVGs are named and positioned so they become canonical per-theme icons without asset rework once `req-grid-icon-instance` is implemented. | |

#### Future

When `req-grid-icon-instance` is implemented, rebind per-theme icons as instance-level overrides so Cytoscape and other default-icon consumers render each theme with its own icon without dashboards resolving by code.

### Reference Data Distribution
----
RID: `req-fedramp-20x-ksi-reference`
Status: `Implemented`

The plugin ships **one** catalog seed file, `grift/ksi-seed.grift.json`, containing a point-in-time snapshot of themes and indicators with deterministic UUIDv5 entity IDs derived from `code`. The seed bootstraps fresh installs; ongoing updates (additions, modifications, deprecations) flow through the runtime `KSICollector` defined in `spec-fedramp-20x-ksi-collector.md`, which submits a `tap.fedramp_20x_ksi.collection-v0` GRIFT batch per run.

The previous multi-wave distribution scheme (`ksi-initial-YYYY-MM-DD.grift.json` + `ksi-wave-YYYY-MM-DD.grift.json`) has been retired along with the authorship-tooling refresh workflow; the seed file replaces both.

#### Implementation

- Seed filename: `grift/ksi-seed.grift.json`
- Seed `description_json.format = "tap.fedramp_20x_ksi.seed-v0"` with minimal source metadata (upstream repo URL, rules version, commit SHA, content SHA-256, `seeded_at`).
- Entity IDs derive from `uuid5(namespace, f"<entity_type>:{code}")` with the namespace pinned in `collectors/pinned/uuid_namespace.txt`. The same derivation is used by the runtime collector, guaranteeing the seed and collector-emitted batches converge on the same entity rows.
- GRIFT import is idempotent: re-running `import_plugin_grift` is a no-op once the seed has landed.
- Deprecation semantics: when upstream drops an indicator, the runtime collector emits a `status: deprecated` modification rather than a delete — the seed file itself is not amended for ongoing change.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-reference-1 | Single Seed File | Implemented | The plugin ships exactly one catalog seed at `grift/ksi-seed.grift.json`. | |
| req-fedramp-20x-ksi-reference-2 | Seed Format Identifier | Implemented | The seed's batch `description_json.format` is `tap.fedramp_20x_ksi.seed-v0`. | |
| req-fedramp-20x-ksi-reference-3 | Deterministic Entity IDs | Implemented | Seed entities use `uuid5(namespace, f"<entity_type>:{code}")` with the namespace pinned in `collectors/pinned/uuid_namespace.txt`. | Shared with the runtime collector |
| req-fedramp-20x-ksi-reference-4 | Deprecation Via Runtime Collector | Implemented | Ongoing catalog changes (including deprecations) land via `KSICollector`; the seed file is not amended for change. | See `spec-fedramp-20x-ksi-collector.md` |
| req-fedramp-20x-ksi-reference-5 | Idempotent Re-import | Implemented | Re-importing the seed file produces no new entities; GRIFT import is skip-if-exists. | |

### Catalog Refresh Workflow
----
RID: `req-fedramp-20x-ksi-refresh`
Status: `Deprecated`

**Deprecated.** The authorship-tooling refresh workflow (`skills/refresh-ksi-catalog/`, the upstream submodule, and `.github/workflows/refresh-catalog.yml`) has been removed and replaced by the runtime `KSICollector`. See `spec-fedramp-20x-ksi-collector.md` for the canonical design — same upstream, same safety checks, same deterministic UUIDv5 derivation, but executed against a live grid via `tap_cares` rather than authored into wave files at CI time. The historical design below is retained for context only and is not implemented.

The plugin previously kept its catalog current by tracking FedRAMP's machine-readable consolidated rules repo as a git submodule and generating GRIFT waves that captured upstream changes. A deterministic Python tool did the work; Claude's role (when invoked via the skill) was orchestration and summarization, never content interpretation.

#### Trust boundary

The upstream source is authoritative for FedRAMP content but is **not trusted** as input to TAP. The plugin defends against:

- supply-chain compromise of the upstream repo
- prompt-injection payloads embedded in any text field
- URLs or references crafted to lure downstream fetching or rendering
- schema-drift attacks that would let unknown fields flow through our model
- mass-deletion events that could cascade into downstream compliance misreadings
- size-based denial of service

Defenses layer the content through (1) git-native provenance checks on the submodule pointer, (2) byte-exact pinned schema validation, (3) structural caps and character-class gates, (4) content-heuristic safety flags, (5) human review of every generated wave PR.

#### Architecture

- **Upstream tracked as a git submodule** at `skills/refresh-ksi-catalog/upstream/` pointing at `github.com/FedRAMP/rules`, shallow-cloned (`--depth=1`); unshallowed on demand when ancestor-checks require history.
- **Pinned assets** in `skills/refresh-ksi-catalog/pinned/`:
  - `source_origin.json` — expected repo URL, branch, and expected committer email domains. Changes require a separately-reviewed PR.
  - `source_schema.json` — byte-exact pinned copy of FedRAMP's consolidated-rules schema. Any drift from upstream schema aborts the run.
  - `uuid_namespace.txt` — UUIDv5 namespace for deterministic entity ID derivation. Never changes.
  - `wave-v0.schema.json` — JSON Schema for the wave description payload (see `req-fedramp-20x-ksi-wave-schema`).
- **Safety configuration** in `skills/refresh-ksi-catalog/safety/denylist.json` — prompt-injection phrase heuristics, tunable by PR.
- **State manifest** at `skills/refresh-ksi-catalog/state/source-manifest.json` — records last-integrated upstream commit SHA and per-wave metadata. Written only by `refresh.py`; never hand-edited.
- **Deterministic tool** at `skills/refresh-ksi-catalog/refresh.py` — the trust boundary. Everything content-sensitive happens here.
- **Skill wrapper** at `skills/refresh-ksi-catalog/SKILL.md` — Claude-facing orchestration instructions. Claude invokes the tool and interprets its structured output, never reads raw source content.
- **Nightly CI** at `.github/workflows/refresh-catalog.yml` (in the plugin repo) — the canonical refresh path. Runs `refresh.py` headless on a schedule; opens a PR when a wave is produced.

#### Flow

1. **Advance submodule pointer.** `git submodule update --remote` on the upstream submodule. If HEAD unchanged, no-op and exit.
2. **Integrity checks** on the new pointer:
   - Submodule URL matches `pinned/source_origin.json` — else `block`
   - New HEAD is a descendant of last-integrated SHA in `source-manifest.json` — else `block` (`INTEGRITY_REWIND`)
3. **Schema equality.** Submodule's `schemas/fedramp-consolidated-rules.schema.json` must byte-match `pinned/source_schema.json`. Drift → `block` (`SCHEMA_DRIFT`). Human reviews and updates pinned schema if drift is legitimate.
4. **Structural validation.** Parse submodule's `fedramp-consolidated-rules.json`, validate against pinned schema, enforce size caps (total bytes ≤ 10 MB, ≤ 20 themes, ≤ 100 indicators per theme, ≤ 100 KB per string field, ≤ 200 items per array).
5. **Character-class gates.** Reject BiDi override chars and non-`\t\n` control chars in any text field → `block`.
6. **Unknown-field check.** Any key not in pinned schema properties → `block` (`UNKNOWN_FIELD`).
7. **Safety heuristics.** Scan content for denylist phrases, outlier string lengths, unexpected URL schemes (per `req-fedramp-20x-ksi-safety`). Emit flags.
8. **Commit metadata extraction.** For each upstream commit between last-integrated and new HEAD SHA, capture `sha`, `date`, `author_name`, `author_email`, `signed`, `verified`, `message_first_line`. Committer emails outside `@fedramp.gov`/`@gsa.gov` → `warn`. Low-quality commit messages (`^(test|wip|hellow? world|fix|update|.)$` case-insensitive, or length < 10) → `warn`.
9. **Deterministic diff.** Replay existing waves to reconstruct prior catalog state. Compare source KSI against prior state by `code`. Classify each theme/indicator as `new` / `modified` / `removed`. Entity IDs derive from `uuid5(namespace, f"ksi_theme:{code}")` and `uuid5(namespace, f"ksi_indicator:{code}")`.
10. **Deletion ratio guard.** If `indicators_deprecated / catalog_size_before > 0.10` → `block` (`MASS_DELETION`). Protects against cascading downstream breakage.
11. **Emit wave.** Write `grift/ksi-initial-YYYY-MM-DD.grift.json` (if no prior waves) or `grift/ksi-wave-YYYY-MM-DD.grift.json`. Each batch in the wave carries `description_json` conforming to `req-fedramp-20x-ksi-wave-schema`. Update `source-manifest.json`.
12. **Structured output.** Tool prints a JSON result to stdout with counts, flags, and wave filename. Non-zero exit when `block` fires.

#### Operator vs. authoring

This skill is **authorship tooling**. Intended users are the plugin maintainer and the nightly CI job. Operators running TAP installations do not invoke it — they pull the plugin repo (via submodule) and run plugin-standard GRIFT import. No runtime refresh path touches live TAP installations.

#### CI contract

The nightly GitHub Action in the plugin repo:

- runs with minimum permissions: `contents: write` and `pull-requests: write` on a fresh branch only
- uses `GITHUB_TOKEN` scoped by the default workflow permissions
- runs in an ephemeral container; no persistent secrets beyond the workflow token
- advances the submodule, invokes `refresh.py --ci`, and if a wave is produced, commits (submodule bump + wave + state manifest + safety report) to a new branch and opens a PR against `main`
- never auto-merges
- applies the label `needs-safety-review` if any `warn`-level flags are present; PRs with `block` flags are not opened (the job fails loudly instead)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-refresh-1 | Submodule-Tracked Upstream | Deprecated | Upstream is a git submodule at `skills/refresh-ksi-catalog/upstream/`. | Shallow clone; fetch --unshallow in CI when needed |
| req-fedramp-20x-ksi-refresh-2 | Pinned Origin | Deprecated | The expected upstream URL and branch are pinned in `pinned/source_origin.json`; mutations require PR review. | |
| req-fedramp-20x-ksi-refresh-3 | Pinned Schema | Deprecated | The upstream JSON schema is pinned in `pinned/source_schema.json`; schema drift aborts the run. | |
| req-fedramp-20x-ksi-refresh-4 | Deterministic Entity IDs | Deprecated | Entity IDs derive from `uuid5(namespace, f"<kind>:{code}")`. Namespace pinned in `pinned/uuid_namespace.txt`. | |
| req-fedramp-20x-ksi-refresh-5 | History Integrity | Deprecated | The tool aborts when the new submodule HEAD is not a descendant of the last-integrated SHA. | `git merge-base --is-ancestor` |
| req-fedramp-20x-ksi-refresh-6 | Deletion Threshold | Deprecated | Refreshes that would deprecate > 10% of existing indicators in a single wave abort with `MASS_DELETION`. | Protects downstream implementations |
| req-fedramp-20x-ksi-refresh-7 | Authorship Tooling | Deprecated | The skill is authorship tooling for the plugin maintainer and CI; operators do not run it. | |
| req-fedramp-20x-ksi-refresh-8 | Claude Does Not Interpret Content | Deprecated | The SKILL.md instructs Claude to invoke the tool and format output, never to read raw source content as free-form input. | |
| req-fedramp-20x-ksi-refresh-9 | CI-Friendly Structured Output | Deprecated | `refresh.py` emits structured JSON on stdout and a non-zero exit code on any `block` flag. | |
| req-fedramp-20x-ksi-refresh-10 | Nightly GitHub Action | Deprecated | A workflow in the plugin repo runs the tool on a nightly schedule and opens PRs for generated waves. | |
| req-fedramp-20x-ksi-refresh-11 | No URL Following | Deprecated | The tool never fetches URLs found in source content; `reference_url` is stored as string only. | |

### Wave Description Schema
----
RID: `req-fedramp-20x-ksi-wave-schema`
Status: `Deprecated`

**Deprecated.** Wave files and their `tap.fedramp_20x_ksi.wave-v0` description format have been removed. Runtime collector batches use `tap.fedramp_20x_ksi.collection-v0` (pinned in `collectors/pinned/collection-v0.schema.json`); the bootstrap seed uses the simpler `tap.fedramp_20x_ksi.seed-v0` marker described in `req-fedramp-20x-ksi-reference`. The historical wave schema is retained below for context only.

Each wave's batch `description_json` carried structured provenance describing which upstream commits the wave covered, what changed, and what safety flags were raised.

#### Format

`description_json.format == "tap.fedramp_20x_ksi.wave-v0"`

`description_json.data` conforms to the JSON Schema at `skills/refresh-ksi-catalog/pinned/wave-v0.schema.json` and contains:

- **`schema_version`** — string, currently `"v0"`
- **`source`** — repo URL, file path and SHA-256, rules version string, `commit_from`/`commit_to` SHAs, `commit_from_date`/`commit_to_date` timestamps
- **`commits`** — array of `{sha, date, author_name, author_email, signed, verified, message_first_line}` for each upstream commit covered
- **`wave`** — `{index, filename, authored_at, authored_by, is_initial}` describing this wave's position in the sequence
- **`changes`** — counts of themes/indicators added/modified/deprecated plus `catalog_size_before`, `catalog_size_after`, `deletion_ratio`
- **`safety`** — `review_required` boolean plus flags array of `{severity, code, detail}`

#### Integration with the tap_grid importer

`tap_grid/grift/importer.py` preserves the caller format and nests importer metadata under `data._tap_grift_import` per `spec-grid-import-grift.md req-grid-import-grift-provenance`. After import, a wave batch's stored `description_json` is:

```json
{
  "format": "tap.fedramp_20x_ksi.wave-v0",
  "data": {
    "schema_version": "v0",
    "source": { ... },
    "commits": [ ... ],
    "wave": { ... },
    "changes": { ... },
    "safety": { ... },
    "_tap_grift_import": {
      "importer": "grift",
      "grift_version": "0",
      "import_mode": "upsert",
      "imported_at": "..."
    }
  }
}
```

Wave provenance is queryable at `Batch.description_json__data__source__commit_to`, `__changes__indicators_deprecated`, and so on.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-wave-schema-1 | Pinned Schema File | Deprecated | Wave `description_json.data` shape is pinned in `skills/refresh-ksi-catalog/pinned/wave-v0.schema.json`. | |
| req-fedramp-20x-ksi-wave-schema-2 | Format Identifier | Deprecated | Wave batches use `format = "tap.fedramp_20x_ksi.wave-v0"`. | |
| req-fedramp-20x-ksi-wave-schema-3 | Queryable Provenance | Deprecated | Wave provenance is queryable via Django JSONField lookups against `description_json.data`. | |
| req-fedramp-20x-ksi-wave-schema-4 | Tool Self-Validates | Deprecated | `refresh.py` validates every emitted wave's description payload against `wave-v0.schema.json` before writing. | |

### Refresh Safety Model
----
RID: `req-fedramp-20x-ksi-safety`
Status: `Deprecated`

**Deprecated.** Safety flags are now implemented inside the runtime `KSICollector` — same flag codes, but the runtime treats every flag as block-class (`req-fedramp-20x-ksi-collector-block-flags`). The three-severity refresh-time model below is retained for context only.

The refresh tool classified anomalies into three severities: `block`, `warn`, `info`. Block aborted the run; warn generated a wave but marked the PR for required safety review; info was telemetry.

#### Flag catalog

**`block` — abort, no wave generated, CI fails:**

| Code | Condition |
| --- | --- |
| `INTEGRITY_REWIND` | Submodule HEAD is not a descendant of last-integrated SHA |
| `ORIGIN_MISMATCH` | Submodule URL differs from `pinned/source_origin.json` |
| `SOURCE_MISSING` | Source JSON or schema file missing from submodule |
| `SCHEMA_DRIFT` | Submodule schema differs from pinned schema |
| `SCHEMA_VALIDATION` | Source JSON fails pinned schema validation |
| `UNKNOWN_FIELD` | Source contains a field not declared in pinned schema |
| `SIZE_CAP` | Source exceeds byte/count caps |
| `CHARACTER_CLASS` | Any text field contains BiDi override or non-`\t\n` control chars |
| `MASS_DELETION` | Would deprecate > 10% of existing indicators in one wave |

**`warn` — wave emitted, PR requires `safety-review-ok` label before merge:**

| Code | Condition |
| --- | --- |
| `INDICATOR_DELETED` | Any indicator dropped from source (even one) |
| `THEME_DELETED` | Any theme dropped from source |
| `CODE_FORMAT` | Indicator code violates `^KSI-[A-Z]{3}-[A-Z0-9]{3}$` |
| `COMMITTER_DOMAIN` | Upstream commit author email outside `@fedramp.gov`/`@gsa.gov` |
| `COMMIT_MESSAGE_QUALITY` | Commit message shorter than 10 chars or matches low-quality regex |
| `CHURN_HIGH` | Net content churn (add+modify+deprecate) > 50% of catalog |
| `DENYLIST_PHRASE` | Prompt-injection phrase hit in any text field |
| `URL_SCHEME` | Non-`https://` URL scheme in any text field other than `reference_url` |

**`info` — recorded in wave PR body, no gating:**

| Code | Condition |
| --- | --- |
| `INITIAL_WAVE` | No prior baseline; full catalog emitted as new |
| `COMMIT_UNSIGNED` | Any upstream commit is unsigned |
| `OUTLIER_LENGTH` | String field > 10× median length for that field |
| `REFRESH_OK` | No anomalies detected |

#### Expected committer domain list

Sourced dynamically at CI time from `gh api /orgs/FedRAMP/members` plus a static fallback of `{"fedramp.gov", "gsa.gov"}`. Not pinned in YAML to avoid PR churn as FedRAMP staff changes.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-safety-1 | Three Severity Levels | Deprecated | The tool classifies anomalies as `block`, `warn`, or `info` per the flag catalog. | |
| req-fedramp-20x-ksi-safety-2 | Block Aborts Run | Deprecated | Any `block`-severity flag aborts the refresh with non-zero exit; no wave is emitted. | |
| req-fedramp-20x-ksi-safety-3 | Warn Requires Label | Deprecated | PRs carrying `warn`-level flags require a `safety-review-ok` label before merge. | CI enforces via branch protection / required status check |
| req-fedramp-20x-ksi-safety-4 | Deletion Threshold At 10% | Deprecated | Mass-deletion block threshold is 10% of existing indicators in a single wave. | `MASS_DELETION` code |
| req-fedramp-20x-ksi-safety-5 | Dynamic Committer Allowlist | Deprecated | Expected committer email domains are fetched at run time from GitHub org membership plus a static fallback. | |
| req-fedramp-20x-ksi-safety-6 | Prompt-Injection Denylist | Deprecated | Content is scanned for known prompt-injection phrase patterns configured in `safety/denylist.json`. | Tunable via PR |

### Plugin Validation
----
RID: `req-fedramp-20x-ksi-plugin-validation`
Status: `Implemented`

The plugin passes TAP's centralized plugin validation system at the structure level in v0 and is expected to pass `loads` and `runs` validation before broader publication.

#### Status Details

Structure-level validation passes in strict mode. Loads and runs validation require the plugin to be registered in TAP's `INSTALLED_APPS` with migrations applied, which is not part of v0 scaffold by design.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-plugin-validation-1 | Structure Validation Required | Implemented | The plugin passes `tap_plugins` structure validation in strict mode. | Verified via `python -m tap_plugins.validate_plugin plugins/fedramp_20x_ksi --strict` |
| req-fedramp-20x-ksi-plugin-validation-2 | Deeper Validation Recommended | Proposed | Authors should run `loads` and `runs` validation before publishing the plugin widely. | Pending `INSTALLED_APPS` integration |

### v0 Non-Goals
----
RID: `req-fedramp-20x-ksi-nongoals`
Status: `Proposed`

This specification does not define:

- a `framework` model representing FedRAMP 20x as a node
- a `ksi_evidence_requirement` model or `REQUIRES_EVIDENCE` edge
- crosswalk edges from KSI indicators to NIST control nodes (`MAPS_TO_CONTROL`) — tracked in `req-fedramp-20x-ksi-nist-crosswalk`
- crosswalks to other compliance frameworks (ISO 27001, SOC 2, etc.)
- assessment-organization data such as 3PAO findings, ATO packages, or POA&Ms
- per-CSP compliance state, posture, or scoring
- (deprecated) the refresh skill — superseded by the runtime `KSICollector`
- per-indicator iconography
- FedRAMP program phase as a modeled field
- `KSI-ABF` (Authorization by FedRAMP) — present in the docs site but not in the machine-readable consolidated rules
- FRD and FRR sections of the consolidated rules (definitions and requirements beyond KSIs)

These are intentionally outside the v0 catalog-representation pass.

## Future Work

- Deliver `req-fedramp-20x-ksi-nist-crosswalk` once a NIST 800-53 plugin provides control nodes.
- Introduce a `framework` model (likely in a future `compliance_core` plugin) and add a `CONTAINS_THEME` edge from framework to `ksi_theme`.
- Add crosswalk edges to other compliance frameworks (ISO 27001, SOC 2, etc.).
- Promote `terms` list entries to `REFERENCES_TERM` edges once a term-node model exists in TAP.
- Wire indicator change history through TAP's history system once it covers plugin models, allowing indicator drift between waves to be queried as graph data in addition to reading wave files directly.
- Rebind per-theme SVGs as canonical instance-level icons once `req-grid-icon-instance` is implemented in `tap_grid`.
- Investigate whether KSI-ABF and FRD/FRR material warrant parallel sibling plugins (`fedramp_20x_frd`, `fedramp_20x_frr`, `fedramp_20x_abf`) once the KSI plugin is stable.
