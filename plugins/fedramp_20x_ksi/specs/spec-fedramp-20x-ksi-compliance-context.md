# FedRAMP 20x KSI Compliance Context Specification

## Philosophy

Every Grid that runs Rampart is operating *under* something — a FedRAMP 20x certification class, a CMMC level, a SOC2 type, an ISO 27001 scope, or some combination. Real Grids will commonly carry *more than one* posture at a time: a federal customer's environment might be FedRAMP 20x Class B and CMMC Level 2 simultaneously, with each compliance program tracked in parallel.

The **ComplianceContext** is the home for that posture data. It's a per-regime entity on the Grid that captures one compliance program's posture (regime slug, framework-specific class / level / type, freeform notes). A Grid that runs three regimes carries three ComplianceContext entities — one per regime — each scoped to its own framework via dimensions.

Panels (KSI compliance view, indicator profile, future system pages, future CMMC and SOC2 panels) read the regime-relevant ComplianceContext via gryphon — typically by filtering on `regime = "<this plugin's regime>"` — and use it to set defaults, filter content, and render the right per-class statements. There's no per-viewer preference, no localStorage fallback, no link-sharing de-sync: the dominant class for each framework is graph state.

This spec **supersedes** the link-sharing concern that put `spec-web-panel-client-state.md` and `spec-fedramp-20x-ksi-class-preference.md` into Backlog. The dominant-class problem is solved here, on the graph, not in browser cookies.

### Cardinality is convention, not schema

The graph layer does not yet have a uniqueness-constraint mechanism — there is no way to declare "exactly one ComplianceContext per regime per Grid" at the schema level. v0 enforces the invariant by **seeding**: a single ComplianceContext per intended regime is seeded into the demo Grid via dedicated GRIFT bundle(s), and queries that read the dominant class for a regime fetch the first (and only) ComplianceContext entity matching that regime. If real-world deployments produce multiple ComplianceContext rows for the same regime by accident, the panel-side query needs to disambiguate; until then, the convention holds. A general "singleton-on-Grid-per-regime" mechanism is Future Work for `tap_grid`.

### Regime as the discriminator

The `regime` field is the primary identifier of which compliance program a ComplianceContext represents. The slug aligns with the relevant compliance plugin's identity (e.g. `fedramp_20x` for the FedRAMP 20x KSI plugin). It is pattern-validated rather than hard-enumerated so additional compliance plugins can register their regime without a model migration in this plugin. Each instance also carries the framework's dimension (e.g. `{"compliance": "fedramp-20x"}` for a FedRAMP 20x context) so it sits in the same dimension namespace as the rest of that framework's entities (`KsiTheme`, `KsiIndicator`, `Finding`, `Evidence`, `ComplianceException`).

### Where the seed lives

The model lives in the FedRAMP 20x KSI plugin (since `fedramp_class` is currently the only framework-specific field), but **the seeded instance is a deployment artifact**, not a framework-catalog artifact. The Genericom demo's FedRAMP 20x ComplianceContext is therefore seeded from the Genericom plugin's grift directory rather than from the FedRAMP plugin. When future framework plugins (CMMC, SOC2) extend this model with additional fields, their per-deployment ComplianceContext seeds also live with the deployment plugin, not with the framework plugin.

### Cross-References

- Backlog (parked pending this spec): [`spec-web-panel-client-state.md`](../../../tap_web/specs/spec-web-panel-client-state.md), [`spec-fedramp-20x-ksi-class-preference.md`](spec-fedramp-20x-ksi-class-preference.md). The link-sharing critique that parked them is resolved by reading the dominant class from this graph object.
- Consumed by: [`spec-fedramp-20x-ksi-compliance-view.md`](spec-fedramp-20x-ksi-compliance-view.md) `req-ksi-compview-class-select` (will be amended in a follow-on commit to read the FedRAMP 20x ComplianceContext's `fedramp_class` as the default class on first load), [`spec-fedramp-20x-ksi-indicator-profile.md`](spec-fedramp-20x-ksi-indicator-profile.md) (future amendment for initial-class selection), and any future system pages.
- BaseModel contract: [`tap_grid/specs/spec-grid-entity.md`](../../../tap_grid/specs/spec-grid-entity.md).

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Single Source Of Truth Per Regime | One ComplianceContext per regime per Grid tells every panel "this Grid is operating under FedRAMP class X / SOC2 type Y / CMMC level Z" — no per-viewer preferences |
| 2. | Cross-Regime, Same Model        | The same model serves every compliance regime; each instance carries a regime slug and the framework-specific posture fields it cares about |
| 3. | Graph-Native                    | Read via gryphon; no separate in-memory cache; no settings table |
| 4. | Narrow v0                       | Only `regime` and `fedramp_class` ship today; placeholder fields for unscoped frameworks are not added preemptively |
| 5. | Per-Regime Dimensioning         | Each instance carries the framework's dimension (e.g. `{compliance: fedramp-20x}`), aligning the context with the rest of that framework's entities |
| 6. | Convention-Enforced Cardinality | "One per regime per Grid" is enforced by seeding, not schema — documented as such until a graph-level singleton mechanism exists |
| 7. | Seed With The Deployment        | Per-deployment ComplianceContext instances are seeded by the deployment plugin (e.g. Genericom), not by the framework plugin |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-compliance-context-model | [Compliance Context Model](#compliance-context-model) | Implemented | `ComplianceContext` BaseModel with `name`, `description`, `regime`, `fedramp_class` |
| req-fedramp-20x-ksi-compliance-context-regime | [Regime Field](#regime-field) | Implemented | `regime` slug, pattern-validated, required on create |
| req-fedramp-20x-ksi-compliance-context-fedramp-class | [FedRAMP Class Field](#fedramp-class-field) | Implemented | `fedramp_class` enum-validated to `a/b/c/d` (or empty for "FedRAMP not in scope for this context") |
| req-fedramp-20x-ksi-compliance-context-dimension | [Dimension Membership](#dimension-membership) | Implemented | Per-instance framework dimension (e.g. `compliance: fedramp-20x`); `compliance: context` is a fallback only |
| req-fedramp-20x-ksi-compliance-context-cardinality | [Convention-Enforced Cardinality](#convention-enforced-cardinality) | Implemented | "One ComplianceContext per regime per Grid" enforced by seed, not schema |
| req-fedramp-20x-ksi-compliance-context-seed | [Demo Seed Data](#demo-seed-data) | Implemented | Genericom seeds the FedRAMP 20x ComplianceContext via `compliance-context-fedramp.grift.json` |

---

### Compliance Context Model
----
RID: `req-fedramp-20x-ksi-compliance-context-model`
Status: `Implemented`

The `compliance_context` entity is a TAP-managed BaseModel that captures one Grid's posture under one compliance regime.

#### Implementation
- Python model lives at `plugins/fedramp_20x_ksi/models/compliance_context.py`, subclassing `BaseModel`.
- `ENTITY_TYPE = "compliance_context"`.
- `ENTITY_NAME = "Compliance Context"`.
- `ENTITY_DESCRIPTION` describes the per-regime, multi-instance shape — see model source for the exact wording.
- `ENTITY_ICON = "compliance-context"` — the icon SVG is not authored in v0; the platform's icon-fallback behavior covers it. A dedicated SVG lands in a follow-on alongside any other display polish.
- `DEFAULT_DIMENSIONS = {"compliance": "context"}` — generic fallback for instances created without explicit dimensions. Per-regime seed bundles override with the framework's dimension; see `req-fedramp-20x-ksi-compliance-context-dimension`.
- Fields:
  - `name`: `CharField(max_length=255)`, required. Short human-readable label (e.g. "Genericom FedRAMP 20x Context").
  - `description`: `TextField(blank=True, default="")`. Free-form context-of-the-context — audit cycle, deployment notes, who designated this posture.
  - `regime`: `CharField(max_length=64)`, required. See `req-fedramp-20x-ksi-compliance-context-regime`.
  - `fedramp_class`: `CharField(max_length=8)`, enum-validated. See `req-fedramp-20x-ksi-compliance-context-fedramp-class`.
- `FIELD_CRUD_SCHEMA` and `FIELD_VALIDATION_SCHEMA` follow the existing KSI-plugin pattern.
- `CREATE_REQUIRED = ["name", "regime"]`. `fedramp_class` has a safe default (`"b"`) and is not required.
- `get_name()` returns `self.name`.

#### Development
- Resist adding `cmmc_level`, `soc2_type`, etc. preemptively. Each gets its own field on the same model (with its own enum validation, default, and field schema entry) when the relevant framework's spec lands. Empty placeholders accumulate migration cost and obscure which fields are real.
- Framework-specific fields are present on every ComplianceContext instance regardless of regime, but only meaningful for the matching regime. A SOC2 instance leaves `fedramp_class=""`; a FedRAMP instance leaves `soc2_type=""` (when that field exists). This is the cost of additive-fields-on-one-model; the alternative (regime-scoped subtables) is rejected for v0 because it explodes the surface area.
- The model is intentionally not connected to any other entity by edge in v0. The "lives on the Grid" relationship is implicit — the demo Grid hosts one ComplianceContext per regime, and consumers query for them by regime + entity type. When per-system contexts become a real need, add an explicit `APPLIES_TO_SYSTEM` edge type at that point.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-context-model-1 | Standard BaseModel Integration | Implemented | Model subclasses `BaseModel` and participates in the standard entity spine, history, and service-layer write pipeline. | |
| req-fedramp-20x-ksi-compliance-context-model-2 | Four-Field v0 Shape | Implemented | The v0 model exposes exactly `name`, `description`, `regime`, `fedramp_class` as writable fields. | Future framework fields land additively |
| req-fedramp-20x-ksi-compliance-context-model-3 | Service-Layer Writes Only | Implemented | Application code and plugin code that creates or mutates `ComplianceContext` instances does so via the service layer. | Matches TAP core architectural rule |
| req-fedramp-20x-ksi-compliance-context-model-4 | Display Projection | Implemented | `Entity.name` is set from `get_name()` (which returns `self.name`) on every save, per the standard `BaseModel` display projection. | Cross-references `req-grid-node-display` |

#### Future

- `cmmc_level` field with enum `["", "1", "2", "3"]`. Lands when the CMMC plugin / spec is drafted.
- `soc2_type` field with enum `["", "type_i", "type_ii"]`. Same trigger.
- `iso_27001_scope` field. Same trigger.
- Cross-framework fields: `audit_cycle_start`, `audit_cycle_end`, `designated_approver_user_id`. Hold until a real audit-cycle workflow demands them.
- `APPLIES_TO_SYSTEM` edge type so a Grid can host multiple ComplianceContext entities of the same regime, each scoped to a subset of systems. Lands when per-system context becomes a real need.
- Move `ComplianceContext` out of the FedRAMP 20x KSI plugin into a regime-agnostic home (e.g. a `tap_compliance` app) once a second framework plugin lands and the cross-cutting nature is unambiguous.

---

### Regime Field
----
RID: `req-fedramp-20x-ksi-compliance-context-regime`
Status: `Implemented`

The `regime` field identifies which compliance program a ComplianceContext represents.

#### Implementation
- `CharField(max_length=64)`, required on create, indexed.
- Pattern-validated via `FIELD_VALIDATION_SCHEMA` against `^[a-z][a-z0-9_]+$` — lowercase, snake_case-friendly, starts with a letter. Catches typos and case mismatches without hard-enumerating valid values.
- Convention: the regime slug aligns with the registering compliance plugin's slug (e.g. `fedramp_20x`, future `soc2`, `cmmc_2_0`). This is policy, not schema.
- Indexed (`db_index=True`) because the dominant-pattern read is "give me the ComplianceContext for regime X" — a per-panel query that runs on every render.

#### Development
- Pattern validation is deliberately permissive. We don't want every new compliance plugin to require a model migration in `fedramp_20x_ksi`. If the surface of valid regimes ever needs central enforcement, the natural home is a registry-based check at write time — Future Work, not v0.
- Resist treating regime as a free-form label. Stick to plugin-aligned slugs; reviewers should push back on any usage that drifts into human-readable strings ("Federal Compliance Posture") or version-collapsed identifiers (`fedramp` instead of `fedramp_20x`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-context-regime-1 | Required On Create | Implemented | A `ComplianceContext` cannot be created without a `regime` value. | Enforced via `CREATE_REQUIRED` |
| req-fedramp-20x-ksi-compliance-context-regime-2 | Pattern Enforcement | Implemented | Values that don't match `^[a-z][a-z0-9_]+$` are rejected at the service-layer write path. | |
| req-fedramp-20x-ksi-compliance-context-regime-3 | Indexed | Implemented | The column is indexed for cheap per-regime lookup. | |

---

### FedRAMP Class Field
----
RID: `req-fedramp-20x-ksi-compliance-context-fedramp-class`
Status: `Implemented`

The `fedramp_class` field captures the dominant FedRAMP 20x certification class for a FedRAMP 20x ComplianceContext.

#### Implementation
- Allowed values: `""`, `"a"`, `"b"`, `"c"`, `"d"`.
- `""` (empty string) is explicitly allowed and is the natural value for ComplianceContexts whose regime is not `fedramp_20x` — they don't carry a FedRAMP class. It also covers the "FedRAMP 20x is in scope but not yet classed" intermediate state on a fedramp_20x context.
- Non-empty values map to FedRAMP 20x certification classes:
  - `"a"` — Class A — Pilot
  - `"b"` — Class B — Low (v0 demo default)
  - `"c"` — Class C — Moderate
  - `"d"` — Class D — High
- Validated via `FIELD_VALIDATION_SCHEMA` with an `enum` constraint.
- Default on creation is `"b"` — matches the demo deployment's working baseline. Non-FedRAMP regimes (SOC2, CMMC, ...) seed their ComplianceContext with `fedramp_class=""`.
- `db_index=True` so per-class queries (rare but plausible) stay cheap.

#### Development
- The empty-string-as-disabled idiom keeps the field schema simple (no `null=True`, no nullable handling in panel code). FedRAMP-aware panels read the field on the `regime="fedramp_20x"` ComplianceContext only; non-FedRAMP regimes' empty `fedramp_class` is invisible to FedRAMP panels.
- Resist adding "All Classes" as a value. The compliance-view's "All Classes" pseudo-value is a *transient view filter* on that panel, not a value the dominant class can take. A Grid is operating under exactly one class at a time, even if a panel is happy to show the catalog without filtering.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-context-fedramp-class-1 | Five-Value Enum | Implemented | `fedramp_class` accepts exactly `""`, `"a"`, `"b"`, `"c"`, `"d"`. | |
| req-fedramp-20x-ksi-compliance-context-fedramp-class-2 | Schema Enforcement | Implemented | Invalid values are rejected at the service-layer write path. | |
| req-fedramp-20x-ksi-compliance-context-fedramp-class-3 | Default Is `b` | Implemented | A `ComplianceContext` created without an explicit `fedramp_class` receives `"b"`. | Demo-deployment baseline; non-FedRAMP regimes override to `""` |
| req-fedramp-20x-ksi-compliance-context-fedramp-class-4 | Empty Means Out-Of-Scope | Implemented | `fedramp_class=""` means "FedRAMP 20x is not in scope for this context." | Natural value for SOC2 / CMMC contexts |

---

### Dimension Membership
----
RID: `req-fedramp-20x-ksi-compliance-context-dimension`
Status: `Implemented`

Each ComplianceContext instance carries the dimension of its regime so it sits in the same dimension namespace as the rest of that framework's entities.

#### Implementation
- `DEFAULT_DIMENSIONS = {"compliance": "context"}` is a generic fallback — it applies only to instances created without an explicit `dimensions` payload. It's the meta-marker for "this is a posture object and the caller didn't tell us which framework."
- Per-regime seed bundles set the framework dimension explicitly. The Genericom FedRAMP 20x seed sets `dimensions={"compliance": "fedramp-20x"}` so the FedRAMP ComplianceContext sits alongside `KsiTheme`, `KsiIndicator`, `Finding`, `Evidence`, and `ComplianceException` in the `fedramp-20x` dimension.
- Future framework seeds carry their own framework dimension (a SOC2 ComplianceContext seeded with `dimensions={"compliance": "soc2"}`, a CMMC ComplianceContext with `dimensions={"compliance": "cmmc-2.0"}`, etc.).
- The dimension-set rule lines up with the cardinality rule: "one ComplianceContext per `compliance` dimension on the Grid" is the same statement as "one ComplianceContext per regime."
- Reviewers may push back on letting the meta-marker `compliance: context` stay as the default — the alternative ("ComplianceContext carries no DEFAULT_DIMENSIONS") was considered and rejected because dimension-less BaseModels are a smell per the platform conventions, even if every real instance in v0 overrides the default.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-context-dimension-1 | Default Fallback | Implemented | `ComplianceContext` instances default to `{"compliance": "context"}` when no dimensions are supplied. | |
| req-fedramp-20x-ksi-compliance-context-dimension-2 | Per-Regime Override | Implemented | Seed bundles supply `dimensions` at create time to attach the instance to the framework's dimension. | The Genericom FedRAMP 20x seed uses `{"compliance": "fedramp-20x"}` |
| req-fedramp-20x-ksi-compliance-context-dimension-3 | No Hard-Coded Lookup | Implemented | Neither the model nor queries assume the dimension; callers may override. | |

---

### Convention-Enforced Cardinality
----
RID: `req-fedramp-20x-ksi-compliance-context-cardinality`
Status: `Implemented`

The "one ComplianceContext per regime per Grid" invariant is enforced by seeding convention, not by schema.

#### Status Details
The graph layer does not yet have a uniqueness-constraint mechanism. A future `tap_grid` requirement could add per-Grid singleton-per-regime enforcement; until then this requirement documents the convention and the consumer-side disambiguation behavior.

#### Implementation
- The demo Grid is seeded with **exactly one** `compliance_context` entity per intended regime via the relevant deployment-plugin grift bundle(s). For v0 the only regime in scope is `fedramp_20x`, seeded by Genericom.
- Consumers (panels, gryphon queries) that read "the dominant FedRAMP class for this Grid" issue a query like `MATCH (c:compliance_context {regime: "fedramp_20x"}) RETURN c LIMIT 1` and treat the first (and only) row as authoritative.
- If a deployment ever produces multiple ComplianceContext rows for the same regime by accident:
  - Panel-side queries should be deterministic across re-renders. Picking the row with the lowest `entity_id` (UUIDv7-sortable, oldest-first) is the v0 disambiguation rule.
  - This case is not expected and represents a deployment bug, not a supported state. The recovery path is to delete or merge the extras.
- v0 explicitly does NOT add an `is_active` boolean or a "selected context" pointer per regime. Adding those would invent multi-context-per-regime semantics before the use case forces it.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-context-cardinality-1 | Convention Documented | Implemented | This spec explicitly states the "one per regime per Grid" invariant is convention-enforced. | |
| req-fedramp-20x-ksi-compliance-context-cardinality-2 | Deterministic Disambiguation | Implemented | Multi-context-per-regime fallback rule: lowest `entity_id` wins. | Documented but not implemented; consumer-side decision when the case appears |
| req-fedramp-20x-ksi-compliance-context-cardinality-3 | Cross-Regime Coexistence | Implemented | Multiple ComplianceContext rows on a Grid are valid as long as they carry distinct `regime` values. | Tested via `test_multiple_contexts_coexist_per_regime` |

#### Future

- A general `tap_grid` singleton-per-regime-per-Grid mechanism (e.g. a unique constraint at the entity-spine level keyed by `entity_type` + a discriminator field) would replace the convention with schema enforcement. Out of scope here; tracked when it becomes worth the lift.

---

### Demo Seed Data
----
RID: `req-fedramp-20x-ksi-compliance-context-seed`
Status: `Implemented`

The Genericom deployment plugin seeds a single FedRAMP 20x ComplianceContext on the demo Grid.

#### Implementation
- Bundle: `plugins/genericom/grift/compliance-context-fedramp.grift.json`. Lives in the deployment plugin (Genericom) rather than the framework plugin (FedRAMP 20x KSI) — see Philosophy § "Where the seed lives."
- Standalone bundle — not folded into other Genericom bundles so re-imports of either do not churn the ComplianceContext (and vice versa).
- The bundle declares one `compliance_context` entity:
  - `name`: `"Genericom FedRAMP 20x Context"`
  - `description`: short note explaining this is the demo Grid's FedRAMP 20x posture record.
  - `regime`: `"fedramp_20x"`
  - `fedramp_class`: `"b"` — matches the demo's working baseline.
  - `dimensions`: `{"compliance": "fedramp-20x"}` — aligns with the rest of the FedRAMP 20x KSI plugin's entities.
- The bundle is registered in `plugins/genericom/tap-plugin.toml` under `[grift]` as `compliance-context-fedramp`.
- The bundle uses fresh UUIDv7s for the batch and node entities.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-context-seed-1 | Bundle Exists | Implemented | A `compliance-context-fedramp.grift.json` bundle is declared in the Genericom plugin manifest and imports cleanly. | |
| req-fedramp-20x-ksi-compliance-context-seed-2 | Single Context Per Regime | Implemented | The bundle creates exactly one `compliance_context` entity for the FedRAMP 20x regime. | |
| req-fedramp-20x-ksi-compliance-context-seed-3 | Demo Default Class | Implemented | The seeded entity's `fedramp_class` is `"b"`. | |
| req-fedramp-20x-ksi-compliance-context-seed-4 | Framework Dimension | Implemented | The seeded entity carries `{"compliance": "fedramp-20x"}` rather than the meta-fallback `{"compliance": "context"}`. | |
| req-fedramp-20x-ksi-compliance-context-seed-5 | Standalone Bundle | Implemented | The bundle is separate from other Genericom grift bundles so re-imports of either do not churn the other. | |
| req-fedramp-20x-ksi-compliance-context-seed-6 | Owned By Deployment Plugin | Implemented | The seed lives in the Genericom plugin, not the FedRAMP 20x KSI plugin, because it's a deployment artifact. | Future framework seeds follow the same rule |

---

## Future Work

- **CMMC posture fields.** `cmmc_level`, future related fields. Lands when the CMMC plugin / spec is drafted. Each demo deployment that runs CMMC will seed its own CMMC ComplianceContext.
- **SOC2 posture fields.** `soc2_type`, future related fields. Same trigger.
- **ISO 27001 posture fields.** Same trigger.
- **Per-system contexts.** When a Grid hosts both FedRAMP and SOC2 work in different parts of the estate at the same regime granularity, an `APPLIES_TO_SYSTEM` edge type lets multiple ComplianceContext entities of the same regime each scope to a subset of assets.
- **Audit-cycle metadata.** Cycle start / end, designated approver, review cadence.
- **Singleton-per-regime-per-Grid schema enforcement.** A general `tap_grid` mechanism replaces the convention with schema-level uniqueness.
- **History-aware "current" pointer.** When multi-context-per-regime becomes a real thing, a way to ask "which context is in effect right now" without ordering by entity_id.
- **Move ComplianceContext to a regime-agnostic app.** Once a second framework plugin lands, relocate the model out of `fedramp_20x_ksi` into something like `tap_compliance` so no framework plugin "owns" the cross-cutting model.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |
| Backlog | Held pending other work |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: `...``
`Status: `...``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
