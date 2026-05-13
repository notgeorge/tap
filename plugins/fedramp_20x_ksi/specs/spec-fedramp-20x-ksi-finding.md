# KSI Finding Specification

## Philosophy

A Finding is the bridge between **what's in the graph** (assets — EC2 instances, databases, load balancers, services, users, and so on) and **what the compliance framework cares about** (KSI Indicators). It is the unit of "something here is not right, relative to a specific compliance requirement."

The model is intentionally minimal in v1. It declares a finding, marks the asset it applies to, and names the KSI indicator it relates to. That's it. The surrounding workflow — severity, source/provenance, resolution as its own entity-and-edge event, evidence attachments, assignment, external correlation identifiers — is all deferred and tracked in the Future section. Every one of those additions can land without reshaping the core model.

This spec lives inside the FedRAMP 20x KSI plugin for now because that's the only compliance framework modeled in TAP today. The model has no FedRAMP-specific semantics; when a second compliance framework appears, the Finding entity and its edges will be promoted to a dedicated general-purpose compliance plugin and the KSI plugin will import from there. The type slugs and edge names chosen here are deliberately generic (`finding`, `exception`, `HAS_FINDING`, `RELATED_INDICATOR`, `COVERS_FINDING`) to make that promotion a rename-free move.

Lifecycle events that a finding can undergo — being granted an exception, being resolved — are modeled as their own sibling entities connected by edges, not as fields on the finding itself. Exception is specified here in v1 alongside the finding. Resolution is tracked as Future work. This separation keeps the finding a clean assertion of "something is not right" while delegating the workflow details (who granted what, when, why, and does it still apply) to dedicated entities that can grow their own fields and lifecycle without bloating the finding model.

The finding's own `status` field intentionally *does not* project exception coverage. A finding with an active `COVERS_FINDING` edge from an `active` exception still reads `status: open` — its "intrinsically open" nature has not changed, only its disposition has. Queries that want to know "which findings are currently in effect" do the two-hop graph traversal and filter out covered ones. That traversal is expressible in gryphon via the multi-hop + `NOT EXISTS` extension specified in [spec-grid-gryphon-multihop-aggregation.md](../../../tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md). This design trade — a slightly heavier query instead of a denormalized status cache — keeps `Finding.status` semantically single-sourced and removes a whole class of sync bugs between two entity types.

The immediate downstream consumer of Finding is the status-badge alert count on graph panels — "for each entity in the scene, count outbound `HAS_FINDING` edges where the finding status is `open`." That binding is specified separately as a new `population.type: "search"` variant in `spec-viz-badges.md`; it is *not* in scope for this spec. This spec ends at "the finding model exists, findings can be attached to assets and indicators, and a handful of demo findings can be seeded for downstream specs to consume."

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Minimal            | v1 models only the four fields required to represent a finding: name, summary, description, status |
| 2. | Graph-Native       | Asset linkage and indicator linkage are first-class edges, not embedded IDs |
| 3. | Generic-By-Design  | Type slug and edge names carry no FedRAMP-specific vocabulary; promotable to a general compliance plugin without rename |
| 4. | Lifecycle-Aware    | Findings carry an explicit status so graph queries can filter open vs. resolved |
| 5. | Evolvable          | Severity, source, resolution-as-entity, and evidence linkage are explicit Future work, not forgotten gaps |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-finding-model | [Finding Model](#finding-model) | Implemented | Minimal v1 `finding` entity with name, summary, description, status |
| req-fedramp-20x-ksi-finding-status | [Finding Status Lifecycle](#finding-status-lifecycle) | Implemented | `open`, `resolved` |
| req-fedramp-20x-ksi-finding-has-edge | [Asset Linkage — `HAS_FINDING`](#asset-linkage--has_finding) | Implemented | Edge from any entity to a finding it applies to |
| req-fedramp-20x-ksi-finding-related-edge | [Indicator Linkage — `RELATED_INDICATOR`](#indicator-linkage--related_indicator) | Implemented | Edge from a finding to a KSI indicator, with a `relationship_type` property |
| req-fedramp-20x-ksi-exception-model | [Exception Model](#exception-model) | Implemented | Minimal `exception` entity with name, description, status |
| req-fedramp-20x-ksi-exception-status | [Exception Status Lifecycle](#exception-status-lifecycle) | Implemented | `active`, `expired`, `revoked` |
| req-fedramp-20x-ksi-exception-edge | [Exception Linkage — `COVERS_FINDING`](#exception-linkage--covers_finding) | Implemented | Edge from an exception to the finding(s) it covers |
| req-fedramp-20x-ksi-finding-dimension | [Dimension Membership](#dimension-membership) | Implemented | Findings and exceptions default to `compliance: fedramp-20x` while the models live in this plugin |
| req-fedramp-20x-ksi-finding-seed | [Demo Seed Data](#demo-seed-data) | Implemented | A small set of seeded findings (including at least one with a covering exception) so downstream alert-badge work has something to count |
| req-fedramp-20x-ksi-finding-verdict-rollup | [Verdict Rollup From Edges](#verdict-rollup-from-edges) | Backlog | A documented rule that aggregates per-edge verdict signal into a single finding-level verdict for display |

---

### Finding Model
----
RID: `req-fedramp-20x-ksi-finding-model`
Status: `Implemented`

The `finding` entity is a TAP-managed model with a minimal field set.

#### Implementation

- Python model lives at `plugins/fedramp_20x_ksi/models/finding.py`, subclassing `BaseModel`.
- `ENTITY_TYPE = "finding"`. Intentionally generic — no `ksi_` or `fedramp_` prefix — because the model is slated for promotion to a general compliance plugin.
- `ENTITY_NAME = "Finding"`.
- `ENTITY_DESCRIPTION = "A single instance of non-compliance or risk observed against an asset, related to one or more compliance requirements."`
- `ENTITY_ICON`: a new `finding` icon registered via the plugin's static assets. If a new SVG is not ready for v1 landing, fall back to a suitable existing glyph and open a follow-on for the dedicated icon.
- `DEFAULT_DIMENSIONS = {"compliance": "fedramp-20x"}` — see `req-fedramp-20x-ksi-finding-dimension`.
- Fields:
  - `name`: `CharField(max_length=255)`, required. Short human-readable label for the finding (e.g. "EC2 instance missing MFA on SSH access").
  - `summary`: `CharField(max_length=500, blank=True, default="")`. Pithy one-sentence description of the issue suitable for table rows and quick-glance UI surfaces. Optional; falls back to empty when not authored.
  - `description`: `TextField(blank=True, default="")`. Longer free-form detail (full context, remediation guidance, references).
  - `status`: `CharField(max_length=32)`, required, enum-validated. See `req-fedramp-20x-ksi-finding-status`.
- `FIELD_CRUD_SCHEMA` and `FIELD_VALIDATION_SCHEMA` follow the existing KSI-plugin pattern (jsonschema-backed).
- `CREATE_REQUIRED = ["name"]`. `status` is not in the required list because the model provides a safe default (`"open"`) and forgetful callers get a sensible value rather than a validation error.
- `get_name()` returns `self.name`.

#### Development

Keep the field list honestly minimal. Any field added here will need a migration and plugin-test coverage. The Future section enumerates the fields we know we'll want later; resist adding them preemptively. A future `detected_at` datetime is a leading candidate for the first additive iteration but is not part of v1 — if we need to know "when was this observed?" before the next iteration, the GRIFT `source_created_at` on the batch envelope already captures that for seeded data.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-finding-model-1 | Generic Slug | Implemented | `ENTITY_TYPE` is `"finding"`, not `"ksi_finding"`. | Preserves promotion-without-rename intent |
| req-fedramp-20x-ksi-finding-model-2 | Four-Field Shape | Implemented | Model exposes exactly `name`, `summary`, `description`, `status` as writable fields in v1. | |
| req-fedramp-20x-ksi-finding-model-3 | Standard BaseModel Integration | Implemented | Model subclasses `BaseModel` and participates in the standard entity spine, history, and service-layer write pipeline. | |
| req-fedramp-20x-ksi-finding-model-4 | Service-Layer Writes Only | Implemented | Application code and plugin code that creates or mutates findings does so via the service layer. | Matches TAP core architectural rule |

#### Future

- `detected_at` datetime — when the finding was first observed.
- `severity` enum — critical/high/medium/low/informational. Tracked as a separate downstream iteration because severity design is meaty enough to be its own sub-spec (and, per user direction, is adjacent to an anticipated standalone severity-model plugin).
- `source` — free-form provenance string: scanner name, `"manual"`, plugin slug, etc.
- External identifier / correlation ID for matching against third-party scanner output.
- Assignee, tags, due date, priority — workflow fields that belong to a later compliance-workflow iteration.

---

### Finding Status Lifecycle
----
RID: `req-fedramp-20x-ksi-finding-status`
Status: `Implemented`

Findings carry an explicit status that reflects the *intrinsic* state of the finding — whether the underlying issue has been fixed — independent of whether any disposition (exception, risk acceptance, etc.) has been applied.

#### Implementation

- Allowed values: `"open"`, `"resolved"`.
- Validated via `FIELD_VALIDATION_SCHEMA` with an `enum` constraint.
- Semantics:
  - `open` — the finding represents an unfixed issue. The underlying condition still exists in the asset.
  - `resolved` — the finding has been remediated; the underlying condition no longer exists. Resolution is anticipated to become its own entity plus a `RESOLVES` edge in a future iteration; the `resolved` status flag is a convenient summary that does not preclude that future work.
- **`exception_granted` is intentionally *not* a status value.** A finding with an active `COVERS_FINDING` edge from an `active` exception is still "open" in the intrinsic sense — the underlying condition hasn't been fixed, only formally accepted. Queries that want to filter for "currently-in-effect findings" do the two-hop graph traversal and exclude covered findings, rather than reading a cached projection off this field. This avoids a sync rule between Finding and Exception state and keeps `Finding.status` semantically single-sourced.
- No `resolved_at` timestamp in v1. When Resolution becomes its own entity it will carry the timestamp.
- Status defaults to `open` on creation if a caller omits the field — though `CREATE_REQUIRED` marks it required, the default is the safe fallback for downstream tools that forget.

#### Development

Keep the enum small. The temptation to add status values that project graph-relational state onto this field should be resisted; graph state belongs in the graph. Adding a new intrinsic state (e.g. `in_progress`, `false_positive`) is a schema change with migration cost; do it only when a concrete workflow demands it, not speculatively.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-finding-status-1 | Two-Value Enum | Implemented | `status` accepts exactly `open` and `resolved`. | |
| req-fedramp-20x-ksi-finding-status-2 | Schema Enforcement | Implemented | Invalid status values are rejected at the service-layer write path. | |
| req-fedramp-20x-ksi-finding-status-3 | Default Is `open` | Implemented | A finding created without an explicit status value receives `open`. | |
| req-fedramp-20x-ksi-finding-status-4 | No Exception Projection | Implemented | `Finding.status` does not change when exceptions are granted or revoked; exception coverage is a graph-relational fact, queried via traversal, not cached on the finding. | |

---

### Asset Linkage — `HAS_FINDING`
----
RID: `req-fedramp-20x-ksi-finding-has-edge`
Status: `Implemented`

The `HAS_FINDING` edge connects any asset to the findings that have been observed against it.

#### Implementation

- New edge definition at `plugins/fedramp_20x_ksi/edges/HAS_FINDING.edge.json`.
- `slug: "HAS_FINDING"`, `name: "Has Finding"`, `description: "An asset has a finding observed against it."`.
- `sources`: omitted — wildcard. Any TAP-managed node type may be the source.
- `targets`: `["finding"]`.
- `default_dimensions: {"compliance": "fedramp-20x"}` while the model lives in this plugin; the dimension block will change when Finding is promoted.
- Edge registered via the plugin's `tap-plugin.toml` `[edges]` section.
- In v1, a finding is connected to a single asset via exactly one `HAS_FINDING` edge. The graph model itself does not impose cardinality limits (multiple incoming edges from different assets are allowed at the storage layer), but v1 seed data and downstream consumers assume one-asset-per-finding. Multi-asset findings are Future work.

#### Development

The wildcard `sources` is deliberate: a finding can apply to an EC2 instance, an S3 bucket, a Kubernetes deployment, a user account, or anything else in the graph. Constraining sources by type would force the plugin to re-publish every time a new asset type lands, which defeats the purpose.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-finding-has-edge-1 | Wildcard Source | Implemented | `HAS_FINDING` accepts any entity type as source. | |
| req-fedramp-20x-ksi-finding-has-edge-2 | Finding-Only Target | Implemented | `HAS_FINDING` only accepts `finding` as target. | |
| req-fedramp-20x-ksi-finding-has-edge-3 | Service-Layer Edge Writes | Implemented | Edge creation and deletion go through the service layer. | |

---

### Indicator Linkage — `RELATED_INDICATOR`
----
RID: `req-fedramp-20x-ksi-finding-related-edge`
Status: `Implemented`

The `RELATED_INDICATOR` edge connects a finding to the compliance indicator(s) it concerns.

#### Implementation

- New edge definition at `plugins/fedramp_20x_ksi/edges/RELATED_INDICATOR.edge.json`.
- `slug: "RELATED_INDICATOR"`, `name: "Related Indicator"`, `description: "A finding relates to a compliance indicator it concerns."`.
- `sources: ["finding"]`.
- `targets: ["ksi_indicator"]` in v1. When additional compliance frameworks land and the Finding model is promoted, this target list will expand (or become wildcard across framework indicator types).
- `default_dimensions: {"compliance": "fedramp-20x"}` consistent with the linked indicators.
- `property_schema` enforces a structured edge-property object that classifies the nature of the relationship:

  ```json
  {
    "type": "object",
    "required": ["relationship_type"],
    "additionalProperties": false,
    "properties": {
      "relationship_type": {
        "type": "string",
        "enum": ["violation", "informational", "other"]
      },
      "name": {"type": "string"},
      "description": {"type": "string"}
    }
  }
  ```

  - `relationship_type` (required) — the load-bearing semantic classification. v1 enum is `violation` (the finding represents a gap or failure against this indicator), `informational` (observational context, not a failure), and `other` (escape hatch). The enum is expected to grow over time; additions like `partial_coverage`, `derived`, and `compensating` are natural candidates.
  - `name` (optional) — short human-readable label for this specific relationship instance.
  - `description` (optional) — longer free-form context.
- The edge itself remains deliberately named `RELATED_INDICATOR` rather than `VIOLATES` or `FAILS_INDICATOR`. The generic edge name plus a `relationship_type` property is stronger than a semantically loaded edge name: it lets the same edge type carry different relationship kinds without renaming, and it keeps the edge viable for non-failure relationships that don't fit a "violates" frame.
- In v1, each finding has exactly one `RELATED_INDICATOR` edge. The graph model does not impose cardinality; multi-indicator findings are Future work.

#### Development

The naming choice is load-bearing for the promotion path. `VIOLATES` bakes in a failure-mode assumption; `RELATED_INDICATOR` stays neutral and lets the `relationship_type` property classify each specific relationship. Resist collapsing the property back onto the edge name even as common patterns emerge — the point of the property is that one edge type can represent multiple relationship kinds without a type explosion.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-finding-related-edge-1 | Finding-Only Source | Implemented | `RELATED_INDICATOR` only accepts `finding` as source. | |
| req-fedramp-20x-ksi-finding-related-edge-2 | Indicator Target | Implemented | `RELATED_INDICATOR` accepts `ksi_indicator` as target in v1. | Target list expands when other framework indicators are added |
| req-fedramp-20x-ksi-finding-related-edge-3 | Generic Naming | Implemented | The edge is named `RELATED_INDICATOR` — not `VIOLATES` or `FAILS_INDICATOR` — so nuanced relationship types are carried as edge properties. | |
| req-fedramp-20x-ksi-finding-related-edge-4 | Property Schema | Implemented | Edge properties are validated against a JSON Schema requiring `relationship_type` and permitting optional `name` and `description`. | `relationship_type` enum is `violation` / `informational` / `other` in v1 |
| req-fedramp-20x-ksi-finding-related-edge-5 | `relationship_type` Required | Implemented | An edge cannot be created without a valid `relationship_type`; a missing or unknown value is rejected at the service-layer write path. | |

---

### Exception Model
----
RID: `req-fedramp-20x-ksi-exception-model`
Status: `Implemented`

The `exception` entity represents a formal acceptance of one or more findings — a risk acknowledgment rather than a remediation. An exception captures that someone has reviewed a finding, decided not to fix it (at least for now), and documented the rationale.

#### Implementation

- Python model lives at `plugins/fedramp_20x_ksi/models/exception.py`, class name `ComplianceException`, subclassing `BaseModel`. The class is named `ComplianceException` rather than `Exception` to avoid shadowing the Python built-in; the entity-type slug remains `"exception"` so GRIFT and service-layer strings are unaffected.
- `ENTITY_TYPE = "exception"`. Intentionally generic — parallel to the choice not to prefix `finding` — because the model is slated for promotion to a general compliance plugin alongside Finding.
- `ENTITY_NAME = "Exception"`.
- `ENTITY_DESCRIPTION = "A formal acceptance of one or more findings, typically recording the rationale for not remediating."`
- `ENTITY_ICON`: a new `exception` icon (or an interim fallback glyph) registered via the plugin's static assets.
- `DEFAULT_DIMENSIONS = {"compliance": "fedramp-20x"}`.
- Fields:
  - `name`: `CharField(max_length=255)`, required. Short human-readable label.
  - `description`: `TextField(blank=True, default="")`. Free-form body. **By convention in v1, the description carries the business justification for the exception.** The model does not enforce that the description is non-empty, because external workflows (e.g. an imported scanner's programmatic exception) may carry the justification in a linked record later. Human-authored exceptions should fill this field.
  - `status`: `CharField(max_length=32)`, required, enum-validated. See `req-fedramp-20x-ksi-exception-status`.
- `FIELD_CRUD_SCHEMA` and `FIELD_VALIDATION_SCHEMA` follow the existing plugin pattern.
- `CREATE_REQUIRED = ["name"]`. As with Finding, `status` relies on its DB default (`"active"`) rather than being required by the service-layer schema.
- `get_name()` returns `self.name`.

The field list deliberately mirrors Finding. Anything that would grow the exception record — approver, expiration date, review cadence, linked change ticket, attached evidence — is Future work and will be layered on as separate entities and edges or as additive fields with clear triggers.

#### Development

The temptation to put `expiration_date`, `approver`, and `business_justification` fields on the entity in v1 should be resisted for the same reason we kept Finding minimal: each field accrues migration cost and workflow expectations. Let real ingestion flows drive the additions.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-exception-model-1 | Generic Slug | Implemented | `ENTITY_TYPE` is `"exception"`, not `"ksi_exception"` or `"compliance_exception"`. | Preserves promotion-without-rename intent |
| req-fedramp-20x-ksi-exception-model-2 | Three-Field Shape | Implemented | Model exposes exactly `name`, `description`, `status` as writable fields in v1. | |
| req-fedramp-20x-ksi-exception-model-3 | Standard BaseModel Integration | Implemented | Model subclasses `BaseModel` and participates in the standard entity spine, history, and service-layer write pipeline. | |
| req-fedramp-20x-ksi-exception-model-4 | Service-Layer Writes Only | Implemented | Application code and plugin code that creates or mutates exceptions does so via the service layer. | |

#### Future

- `expiration_date` — when the exception needs to be re-reviewed. Pairs with automated `status` transition to `expired`.
- Approver as a linked user entity (`GRANTED_BY` edge) — audit trail of who accepted the risk.
- Review cadence and next-review date.
- Linkage to a change management record or ticket identifier.
- Attached evidence (e.g. the email or policy document that grants the exception).

---

### Exception Status Lifecycle
----
RID: `req-fedramp-20x-ksi-exception-status`
Status: `Implemented`

Exceptions carry an explicit status. The status values align with how exceptions are typically managed in real compliance workflows: active acceptance, expired acceptance requiring re-review, and explicitly revoked acceptance.

#### Implementation

- Allowed values: `"active"`, `"expired"`, `"revoked"`.
- Validated via `FIELD_VALIDATION_SCHEMA` with an `enum` constraint.
- Semantics:
  - `active` — the exception is currently in effect. Any finding covered by this exception is treated as formally accepted.
  - `expired` — the exception's validity window has elapsed (typically because a review date passed) and a reassessment is required. The exception no longer covers its findings until renewed.
  - `revoked` — the exception has been explicitly withdrawn. The underlying findings revert to whatever their non-excepted status would be.
- Default status on creation is `"active"`.
- No `expired_at` / `revoked_at` timestamp fields in v1 — the Entity spine's `updated_at` captures when state changed. Fine-grained transition timestamps belong to a future audit-trail iteration.
- Status transitions in v1 are explicit writes by callers; there is no automated expiration enforcement. A scheduled task that flips `active` to `expired` based on a future `expiration_date` field is Future work.

Exception state does **not** project onto `Finding.status`. An exception covering a finding is represented entirely by the graph: an `active` exception with a `COVERS_FINDING` edge to the finding. Queries that need "currently-in-effect findings" (the alert-count being the motivating example) express that via a multi-hop anti-join in gryphon — see [spec-grid-gryphon-multihop-aggregation.md](../../../tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md). This deliberately avoids the sync-rule coupling that would be required if exception coverage were cached on the finding.

#### Development

The choice to leave `Finding.status` unmodified by exception state is deliberate. An earlier draft of this spec carried a service-layer sync rule that kept `Finding.status` in lockstep with exception coverage; it was removed once the gryphon extension made the graph-traversal expressible as a declarative query. If a read-heavy use case ever demands a cached projection, it should live in a dedicated read-side cache (materialized view, query-cached aggregate) rather than re-introducing write-time coupling between two entity types.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-exception-status-1 | Three-Value Enum | Implemented | `status` accepts exactly `active`, `expired`, `revoked`. | |
| req-fedramp-20x-ksi-exception-status-2 | Schema Enforcement | Implemented | Invalid status values are rejected at the service-layer write path. | |
| req-fedramp-20x-ksi-exception-status-3 | Default Is `active` | Implemented | An exception created without an explicit status value receives `active`. | |
| req-fedramp-20x-ksi-exception-status-4 | No Finding-Side Coupling | Implemented | Exception status changes do not trigger writes to `Finding.status`. Exception coverage is a graph fact, queried via traversal. | Cross-reference `req-fedramp-20x-ksi-finding-status-4` |

#### Future

- Per-transition timestamps (`expired_at`, `revoked_at`) once a formal audit trail is needed beyond entity `updated_at`.
- Scheduled task that automatically transitions `active` → `expired` based on a future `expiration_date` field.
- Read-side cache of effective finding state if query-time traversal ever becomes a bottleneck (materialized view, denormalized aggregate, or similar read-side construct — never re-introduced as write-time coupling).

---

### Exception Linkage — `COVERS_FINDING`
----
RID: `req-fedramp-20x-ksi-exception-edge`
Status: `Implemented`

The `COVERS_FINDING` edge connects an exception to the finding(s) it covers.

#### Implementation

- New edge definition at `plugins/fedramp_20x_ksi/edges/COVERS_FINDING.edge.json`.
- `slug: "COVERS_FINDING"`, `name: "Covers Finding"`, `description: "An exception covers a finding — formally accepting the risk the finding represents."`.
- `sources: ["exception"]`.
- `targets: ["finding"]`.
- `default_dimensions: {"compliance": "fedramp-20x"}`.
- No `property_schema` in v1. Edge properties like `note` (reason for adding this specific finding to the exception), `added_at`, or `added_by` are Future work.
- Direction — Exception → Finding — is deliberate. A single exception can legitimately cover multiple findings (one risk acceptance blanketing a family of similar gaps), so modeling the exception as the subject with outbound edges reads more naturally than fanning per-finding `HAS_EXCEPTION` edges. This also keeps symmetry with how Resolution will be modeled when it lands (Resolution → Finding via `RESOLVES`).

#### Development

Edge writes have no side effects on `Finding.status`. The alert-count query expresses coverage via graph traversal (multi-hop + `NOT EXISTS`); there is no denormalized cache to keep in sync.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-exception-edge-1 | Exception Source | Implemented | `COVERS_FINDING` only accepts `exception` as source. | |
| req-fedramp-20x-ksi-exception-edge-2 | Finding Target | Implemented | `COVERS_FINDING` only accepts `finding` as target. | |
| req-fedramp-20x-ksi-exception-edge-3 | Multi-Finding Permitted | Implemented | A single exception may have multiple outbound `COVERS_FINDING` edges covering distinct findings. | No cardinality constraint imposed by the graph model |
| req-fedramp-20x-ksi-exception-edge-4 | No Finding-Side Side Effects | Implemented | Creating, updating, or deleting a `COVERS_FINDING` edge does not write to `Finding.status` or any other finding field. | Cross-reference `req-fedramp-20x-ksi-finding-status-4` |

---

### Dimension Membership
----
RID: `req-fedramp-20x-ksi-finding-dimension`
Status: `Implemented`

Findings and exceptions carry the `compliance: fedramp-20x` dimension by default, matching the other KSI-plugin models.

#### Implementation

- `DEFAULT_DIMENSIONS = {"compliance": "fedramp-20x"}` on both the `Finding` and `Exception` models.
- All three new edge types (`HAS_FINDING`, `RELATED_INDICATOR`, `COVERS_FINDING`) carry the same default via `default_dimensions` in their `.edge.json` files.
- This is a stance for the current plugin-owned iteration. Once the Finding and Exception models promote to a general compliance plugin, the default dimension will change — the dimension is an indicator of framework membership, not a permanent identity.
- Nothing in the models, edges, or search plumbing hard-codes the framework dimension beyond these defaults. Callers are free to override on create.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-finding-dimension-1 | Default Dimension | Implemented | `Finding` and `Exception` entities and all three new edge types default to `compliance: fedramp-20x`. | |
| req-fedramp-20x-ksi-finding-dimension-2 | No Hard-Coded Framework Lookup | Implemented | Neither the models nor queries assume the framework dimension; callers may override. | |

---

### Demo Seed Data
----
RID: `req-fedramp-20x-ksi-finding-seed`
Status: `Implemented`

A small seed of findings ships with the plugin so downstream work — specifically the search-backed status-badge population in `spec-viz-badges.md` — has something to count.

#### Implementation

- A new GRIFT bundle `plugins/fedramp_20x_ksi/grift/findings.grift.json` declares a handful of findings.
- Seed targets the Genericom demo assets (EC2 instances, RDS instances, ALBs, ElastiCache clusters) so the landing projection visibly responds when the search-backed population mechanism is wired up in the next iteration. This creates a cross-plugin seed dependency: the findings bundle references Genericom entity IDs. That cross-plugin reference is acceptable for a demo bundle; the same findings-authoring pattern generalizes in production environments by importing against live asset inventories.
- Seed volume is deliberately small — a dozen or so findings across a few distinct KSI indicators. Enough to exercise the alert counts, not so much that the demo becomes noisy.
- Each seeded finding has:
  - a descriptive `name` that reads naturally (e.g. "prod-web-a: SSH access permitted from public internet")
  - a short `description`
  - `status: "open"` on most; at least one `"resolved"` so the status filter can be demonstrated in screenshots
  - one outgoing `RELATED_INDICATOR` edge to a specific KSI indicator, with a `relationship_type` property chosen per finding (`violation` for most, `informational` on at least one)
  - one incoming `HAS_FINDING` edge from the targeted Genericom asset
- At least one seeded `exception` entity with `status: "active"`, covering at least one seeded finding via a `COVERS_FINDING` edge. The covered finding's `status` remains `"open"` (its intrinsic state is unchanged); the alert-count query filters it out via the multi-hop traversal. This exercises both the exception model and the downstream traversal-based filtering end-to-end in the demo.

#### Development

Seed bundles for cross-plugin entity references need to be authored carefully: the referenced asset IDs must exist in the installed grid, which for this demo is guaranteed because Genericom seeds first. Real-world finding ingestion will come from scanners, not authored GRIFT — the seed is purely for demonstrating the alert-count UI.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-finding-seed-1 | Bundle Exists | Implemented | A `findings.grift.json` bundle is declared in the plugin manifest and imports cleanly. | |
| req-fedramp-20x-ksi-finding-seed-2 | Targets Genericom Assets | Implemented | Seeded findings reference real Genericom asset entity IDs via `HAS_FINDING` edges. | Cross-plugin reference acceptable for demo seed |
| req-fedramp-20x-ksi-finding-seed-3 | Status Variety | Implemented | Seed includes at least one finding in each of the three status values so downstream filters can be exercised. | |
| req-fedramp-20x-ksi-finding-seed-4 | Indicator Linkage | Implemented | Every seeded finding carries exactly one `RELATED_INDICATOR` edge to a specific KSI indicator, with a valid `relationship_type` property. | |
| req-fedramp-20x-ksi-finding-seed-5 | Exception Coverage | Implemented | At least one seeded exception with `status: active` covers at least one seeded finding via a `COVERS_FINDING` edge; the covered finding's status is `exception_granted`. | Exercises the full exception lifecycle in the demo |

---

### Verdict Rollup From Edges
----
RID: `req-fedramp-20x-ksi-finding-verdict-rollup`
Status: `Backlog`

A finding does not carry a verdict field on the model itself. Verdict signal lives on the finding's edges, in two places that share the same vocabulary (`violation`, `passing`, `informational`):

- `HAS_EVIDENCE.support_kind` — verdict carried per evidence row.
- `RELATED_INDICATOR.relationship_type` — verdict carried per linked KSI indicator.

This is the deliberate "verdict-on-edge" design recorded in the seed bundles' prose: `Finding.status` stays as a pure lifecycle field (`open` / `resolved`); per-edge verdict signal is the source of truth for "passing vs violation vs informational." This requirement is the place where the *rollup rule* — how a panel collapses one or more per-edge verdict signals into a single finding-level verdict — gets specified.

#### Status Details
Backlog. The first attempt to render a hero verdict pill on the finding profile page baked an inferred rollup rule into the panel template ("`violation` > `passing` > `informational`, aggregated across both edge types, fall back to lifecycle status when neither edge carries signal"). That logic shipped briefly, then got reverted because it wasn't spec'd: it answered a real question (which pill to show on the hero) but invented the rule rather than citing one. The hero verdict pill was removed from the finding profile pending this requirement landing. See `spec-fedramp-20x-ksi-finding-profile.md` `req-fedramp-20x-ksi-finding-profile-hero` for the corresponding panel-side note.

The shape of the rollup rule is the open design question. Five cases need explicit answers before this requirement can move to `Approved for Development`:

1. **Both edges carry verdict signal, agreeing.** Trivially returns the agreed value.
2. **Both edges carry verdict signal, disagreeing.** E.g. an evidence row says `passing` but the related-indicator linkage says `violation`. Which wins, and why? (Plausible rules: most-severe wins; evidence-edges win because they're the more recent observation; related-indicator wins because it's the framework-level claim.)
3. **Only `HAS_EVIDENCE` carries verdict** (no `RELATED_INDICATOR`, or no `relationship_type` on it). Aggregate across evidence rows by precedence.
4. **Only `RELATED_INDICATOR` carries verdict** (no `HAS_EVIDENCE` rows yet, or none with a `support_kind`). Use the indicator linkage's verdict directly.
5. **Neither edge carries verdict signal.** What does the panel show? Falling back to lifecycle `status` mixes two different vocabularies into one pill (`open` is not a verdict); rendering nothing is honest but loses information. Either is defensible — pick one.

#### Implementation
Deferred. When this requirement is picked up:
- Pick the rollup rule for each of the five cases above and write it down here with rationale.
- Decide where the rule lives. Three plausible homes:
  - **Panel-level** — each panel that needs a verdict computes it locally. Cheapest; risks drift between panels.
  - **Service-layer helper** — a `derived_verdict(finding)` function in the plugin so every consumer gets the same answer.
  - **Materialized field on Finding** — denormalized, kept in sync via signal/refresh. Heaviest; revisits the verdict-on-edge stance and probably wrong given the design intent.
- Re-introduce the hero verdict pill on the finding profile (and the matching cell formatter on the findings tables) once the rule is documented.
- Add ACIDs covering each of the five cases above.

#### Development
- Resist re-introducing the inferred rollup logic in render code without spec backing. The lesson from the first attempt: the question "which pill?" sounds local to the panel, but the *answer* is platform policy — different panels giving different answers for the same finding would erode trust faster than missing pills.
- The five cases above are the *minimum* coverage. Additional cases (e.g. one edge type carries a verdict that isn't in the shared vocabulary, edges carrying `null`, edges with `relationship_type` outside the verdict vocabulary) need to be enumerated before code lands.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-finding-verdict-rollup-1 | Rule Documented | Backlog | The rollup rule for each of the five spec'd cases is written into this requirement before code lands. | Drafted in Implementation when picked up |
| req-fedramp-20x-ksi-finding-verdict-rollup-2 | Single Source Of Logic | Backlog | The rollup rule has exactly one home in code; multiple panels computing the same verdict differently is a regression. | Home choice is a sub-decision |
| req-fedramp-20x-ksi-finding-verdict-rollup-3 | Hero Pill Re-Introduced | Backlog | The finding profile hero re-renders a verdict pill once the rule lands. | See `spec-fedramp-20x-ksi-finding-profile.md` `req-fedramp-20x-ksi-finding-profile-hero` |

#### Future
- Per-class verdict rollup. Today's rollup is regime-agnostic; once `ComplianceContext.fedramp_class` selection is wired into the finding profile, "violation at Class B" vs "violation at Class C" may resolve differently.
- Explanation surface. When a panel renders a rolled-up verdict, expose *why* on hover (which edges, which precedence step won) so reviewers can audit the rollup without leaving the page.

---

## Future Work

The v1 model is deliberately narrow so growth directions stay enumerable. The following are known-known extensions, roughly ordered by expected arrival:

- **`detected_at` timestamp** — the first additive field, natural to add when any real ingestion path lands.
- **Severity** — a whole sub-spec. Anticipated as a pluggable severity model (its own plugin, ideas in flight). The alert-badge population mechanism will filter by severity once this lands.
- **Resolution as its own entity** — a `Resolution` entity connected to a finding via a `RESOLVES` edge, carrying who resolved it, when, how, and evidence. The `status: resolved` field is a summary projection of "there exists a valid Resolution connected to this finding." Symmetric with the Exception pattern already specified in v1.
- **Exception expiration & approver** — `expiration_date` field on Exception plus a scheduled task that flips `active` → `expired`, and a `GRANTED_BY` edge linking to the approver user.
- **Source/provenance** — scanner name, plugin slug, manual, etc. Likely grows into a `Source` entity when it gets interesting (registry of scanners, credential state, last-run timestamps).
- **Multi-asset findings** — a finding that legitimately applies to a group of assets (e.g. "all EC2 instances in this subnet are missing logging"). Either multiple `HAS_FINDING` edges from one finding, or a new `APPLIES_TO_GROUP` relationship to a cluster/tag entity.
- **Multi-indicator findings** — a finding that addresses several indicators at once. Multiple `RELATED_INDICATOR` edges are already structurally supported; v1 just constrains seeded data to one.
- **Evidence linkage** — `HAS_EVIDENCE` edge from a finding to evidence entities (screenshots, log excerpts, scanner output, policy attestations).
- **Relationship nuance on `RELATED_INDICATOR`** — edge properties like `relationship_kind` that distinguish "direct violation" from "derived," "informational," "partial-coverage," etc.
- **External correlation** — a `source_identifier` or `external_id` field for deduplication against third-party scanner output.
- **Promotion** — move Finding, `HAS_FINDING`, and `RELATED_INDICATOR` to a general compliance plugin once a second compliance framework lands. The generic naming in v1 makes this a rename-free move; the dimension default shifts to something framework-neutral.
- **Downstream: search-backed alert population** — a new `population.type: "search"` variant in `spec-viz-badges.md` that binds status-badge counts to a Gryphon search over `HAS_FINDING` with a `status` filter. This is the immediate next piece of work once this spec lands.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Implemented |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

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
