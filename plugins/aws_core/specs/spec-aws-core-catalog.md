# AWS Core Catalog Refresh Specification

## Philosophy

The AWS Core plugin's reference data must stay current as AWS launches new regions, availability zones, and services. Rather than maintaining a static dataset that drifts, the plugin includes a catalog refresh capability that uses AI to gather the latest information from AWS documentation and directly update the plugin's source files.

The refresh is not a traditional data pipeline with intermediate formats. It is a Claude Code skill that reads the current plugin state, searches for changes, and writes updates to models, GRIFT seed data, edge definitions, and icon assets. Git provides the audit trail, and the TAP plugin validation system confirms the result is structurally and functionally correct.

This approach was chosen over a deterministic scraper because AWS does not present its service surface area consistently in any machine-readable format. Regions and AZs are well-documented, but the full service catalog requires synthesizing information from multiple inconsistent sources — a task better suited to AI judgment than brittle parsers.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Current       | Reference data reflects the latest AWS global infrastructure |
| 2. | Safe          | Changes are incremental; removals require authoritative deprecation evidence |
| 3. | Validated     | Every refresh run is verified by the plugin validation system |
| 4. | Auditable     | Git tracks exactly what changed, when, and from what sources |
| 5. | Automated     | The skill can run in CI on a nightly schedule |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-aws-catalog-scope | [Catalog Scope](#catalog-scope) | Implemented | Defines what the catalog refresh covers |
| req-aws-catalog-skill | [Refresh Skill](#refresh-skill) | Implemented | Claude Code skill for catalog updates |
| req-aws-catalog-incremental | [Incremental Updates](#incremental-updates) | Implemented | Change detection and safe update strategy |
| req-aws-catalog-deprecation | [Deprecation Policy](#deprecation-policy) | Implemented | Rules governing removal of catalog entries |
| req-aws-catalog-validation | [Post-Refresh Validation](#post-refresh-validation) | Implemented | Validation pipeline after every refresh |
| req-aws-catalog-icons | [Icon Management](#icon-management) | Implemented | Icon creation and update as part of refresh |
| req-aws-catalog-future-services | [Service Catalog Expansion](#service-catalog-expansion) | Proposed | Future: resource type and model discovery |
| req-aws-catalog-future-live | [Live Account Discovery](#live-account-discovery) | Proposed | Future: populate from a running AWS account |
| req-aws-catalog-future-ci | [CI Integration](#ci-integration) | Proposed | Future: nightly automated refresh |

### Catalog Scope
----
RID: `req-aws-catalog-scope`
Status: `Implemented`

The catalog refresh currently covers AWS regions, availability zones, and entity type icons.

#### Implementation

**In scope:**

- AWS commercial regions (code, display name, geographic area)
- Availability zones per region (zone name, zone ID, parent region)
- COMPRISES_AZ edges from region to AZ
- SVG icon assets for all declared entity types

**Excluded:**

- GovCloud and China partition regions
- Local Zones and Wavelength Zones
- Service/resource type discovery and model generation
- Live AWS account queries

Data is written as GRIFT seed data to `grift/regions.grift.json` and icon SVGs to `static/aws_core/icons/`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-catalog-scope-1 | Regions Covered | Implemented | All standard commercial AWS regions are maintained. | |
| req-aws-catalog-scope-2 | AZs Covered | Implemented | All availability zones with zone IDs are maintained. | |
| req-aws-catalog-scope-3 | Icons Covered | Implemented | SVG icons for all entity types are maintained. | |

#### Future

Expand scope to include service/resource type discovery — detecting new AWS services and proposing new models, edge types, and GRIFT data.

### Refresh Skill
----
RID: `req-aws-catalog-skill`
Status: `Implemented`

The catalog refresh is a Claude Code skill that directly modifies plugin source files.

#### Implementation

The skill lives at `skills/refresh-aws-catalog/SKILL.md` (relative to the plugin root). It is invoked manually via `/refresh-aws-catalog` or can be triggered by a CI schedule.

The skill's workflow:

1. Read current plugin state (existing GRIFT, models, icons)
2. Search the web for current AWS infrastructure data
3. Update GRIFT seed data with new/changed regions and AZs
4. Create or update icon SVG files
5. Validate the result against the GRIFT JSON Schema and the TAP plugin validator at `--level runs`
6. Report a summary of changes

The skill is marked `disable-model-invocation: true` — it runs only when explicitly invoked, never auto-triggered.

The skill references TAP's GRIFT JSON Schema (`tap_grid/schemas/grift-document.schema.json`) and icon specification (`tap_grid/specs/spec-grid-icon.md`) by path rather than embedding format knowledge. This prevents drift between the skill and the authoritative format definitions.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-catalog-skill-1 | Skill Exists | Implemented | The refresh skill is defined in the plugin's `skills/` directory. | |
| req-aws-catalog-skill-2 | Manual Invocation Only | Implemented | The skill is `disable-model-invocation: true`. | |
| req-aws-catalog-skill-3 | Format By Reference | Implemented | The skill references GRIFT and icon specs by path, not embedded knowledge. | |
| req-aws-catalog-skill-4 | Dry Run Support | Implemented | The skill accepts `--dry-run` to report changes without writing files. | |

#### Future

The skill should grow to handle model file generation when the service catalog expansion is implemented. It should also be able to propose edge type changes when new relationship patterns are discovered.

### Incremental Updates
----
RID: `req-aws-catalog-incremental`
Status: `Implemented`

The refresh skill detects changes since the last run rather than regenerating everything.

#### Implementation

The incremental strategy:

1. Check file modification dates on existing GRIFT files to scope searches
2. Preserve existing entity IDs for known regions/AZs (enables GRIFT upsert)
3. Assign new deterministic entity IDs for newly discovered items by continuing the incrementing sequence from the highest existing ID in each range
4. Focus web searches on changes since the last update date
5. Sort regions by region code and AZs grouped under their parent region for stable diffs

Entity ID ranges are partitioned by type:

| Type | ID Prefix |
| --- | --- |
| Batch | `01965b00-0000-7000-8000-*` |
| Regions | `01965b00-1000-7000-8000-*` |
| AZs | `01965b00-2000-7000-8000-*` |
| Edges | `01965b00-3000-7000-8000-*` |

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-catalog-incremental-1 | Existing IDs Preserved | Implemented | Known regions and AZs retain their entity IDs across refreshes. | |
| req-aws-catalog-incremental-2 | New IDs Sequential | Implemented | New items get IDs that continue the existing sequence. | |
| req-aws-catalog-incremental-3 | Stable Ordering | Implemented | Output is sorted for minimal git diffs. | |

### Deprecation Policy
----
RID: `req-aws-catalog-deprecation`
Status: `Implemented`

The refresh skill never removes data without authoritative evidence.

#### Implementation

A region, AZ, service, or model must NOT be removed unless:

- An official AWS page or announcement explicitly declares it deprecated or removed
- The source URL can be cited in the change summary

Missing an item from a web search result is NOT sufficient evidence for removal. If a resource cannot be confirmed but has no deprecation notice, it is kept and flagged in the summary report.

This policy exists because false removals are far more damaging than stale entries. A region that still exists but gets removed from the catalog breaks every entity and edge that references it. A region that was deprecated but lingers in the catalog is harmless.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-catalog-deprecation-1 | No Silent Removals | Implemented | Items are never removed without an authoritative deprecation source. | |
| req-aws-catalog-deprecation-2 | Source Citation Required | Implemented | Every removal must cite the AWS source URL. | |
| req-aws-catalog-deprecation-3 | Unconfirmed Items Flagged | Implemented | Items that cannot be confirmed are kept and flagged, not removed. | |

### Post-Refresh Validation
----
RID: `req-aws-catalog-validation`
Status: `Implemented`

Every refresh run is validated before completion.

#### Implementation

After updating files, the skill runs two validation steps:

1. **GRIFT schema validation** — validates the GRIFT file against `tap_grid/schemas/grift-document.schema.json` using `jsonschema.validate()`
2. **Plugin validation** — runs `python manage.py validate_plugin <plugin_root> --level runs` which exercises manifest parsing, class imports, icon existence, service-layer smoke tests, and GRIFT import

Both must pass before the skill reports success. If either fails, the skill diagnoses and fixes the issue before completing.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-catalog-validation-1 | Schema Validation | Implemented | GRIFT output is validated against the published JSON Schema. | |
| req-aws-catalog-validation-2 | Plugin Validation | Implemented | Full plugin validation at `runs` level passes after every refresh. | |
| req-aws-catalog-validation-3 | Fail-Safe | Implemented | The skill does not report success if validation fails. | |

### Icon Management
----
RID: `req-aws-catalog-icons`
Status: `Implemented`

Icon creation and maintenance is part of the catalog refresh.

#### Implementation

The refresh skill:

1. Reads all `ENTITY_ICON` values from model files
2. Checks which SVGs exist in `static/aws_core/icons/`
3. Creates or updates missing icons

Icons must conform to the TAP grid icon specification:

- 24x24 viewBox, SVG format
- `currentColor` fill for CSS theming
- `aria-hidden="true"` for accessibility
- Kebab-case filename matching the model's `ENTITY_ICON` value

The skill references existing LOTR icons at `plugins/lotr/static/lotr/icons/` as a style reference. Multiple models may share an icon key (e.g. `aws-iam` for User, Role, and Policy).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-catalog-icons-1 | Missing Icons Created | Implemented | The skill creates SVGs for any declared icon key without a file. | |
| req-aws-catalog-icons-2 | TAP Icon Contract | Implemented | Generated icons conform to the grid icon specification. | |
| req-aws-catalog-icons-3 | Shared Keys Handled | Implemented | Multiple models sharing an icon key produce one SVG file. | |

#### Future

Source icons from the official AWS Architecture Icons asset pack, simplified to TAP's single-color convention, rather than generating from scratch.

### Service Catalog Expansion
----
RID: `req-aws-catalog-future-services`
Status: `Proposed`

Future capability: the refresh skill detects new AWS services and proposes new models, edge types, and GRIFT data.

#### Implementation

When implemented, the skill would:

- Search for newly launched AWS services since the last refresh
- Propose new model files with appropriate fields, schemas, and CREATE_REQUIRED
- Propose new edge types for relationships between new and existing resource types
- Generate initial GRIFT seed data for reference-type resources
- Create icon SVGs for new models
- Present changes for review before committing

This is a creative AI task — the skill must make judgment calls about field selection, naming conventions, and edge semantics. The plugin validation system and git review process provide the safety net.

#### Future

This capability depends on the skill being able to reliably gather AWS service metadata from documentation, blog posts, and API references. The inconsistency of AWS's documentation surface area is the primary challenge.

### Live Account Discovery
----
RID: `req-aws-catalog-future-live`
Status: `Proposed`

Future capability: populate the grid from a running AWS account.

#### Implementation

When implemented, the plugin would:

- Accept AWS credentials (assumed role or org-level access)
- Query each region for running resources across all modeled resource types
- Create entities, edges, and configuration metadata for discovered resources
- Use the service layer to write through the standard TAP pipeline
- Support incremental updates (discover changes since last scan)

This is distinct from the catalog refresh, which maintains the plugin's static reference data. Live discovery populates a TAP grid with the actual state of a customer's AWS environment.

#### Future

This capability will likely use tools like AWS Config, CloudTrail, or direct API calls. The plugin's 37 resource-type models and 15 edge types provide the schema foundation that live discovery will populate.

### CI Integration
----
RID: `req-aws-catalog-future-ci`
Status: `Proposed`

Future capability: automated nightly refresh via CI.

#### Implementation

When implemented, the CI pipeline would:

1. Run the refresh skill on a schedule (nightly)
2. If changes are detected, create a PR with the diff
3. Run the plugin validation suite in CI
4. Auto-merge if validation passes, or flag for human review if the changes are significant (new models, removals)

The refresh skill already supports the validation and reporting steps. CI integration requires:

- A CI environment with Claude Code access
- Git credentials for PR creation
- A policy for auto-merge vs. human review thresholds

#### Future

Define the threshold for auto-merge (e.g. new AZs in existing regions = auto-merge; new regions or model changes = human review).
