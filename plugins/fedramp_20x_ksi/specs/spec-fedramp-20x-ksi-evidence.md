# KSI Evidence Specification

## Philosophy

Evidence is the artifact that justifies a finding's verdict. A finding asserts "something is in this state with respect to a compliance requirement"; the evidence is the screenshot, scanner output, policy document, attestation, or log excerpt that demonstrates *why* the finding holds.

The model is intentionally minimal in v1: a name, a description, and a kind. The verdict the evidence supports — passing, violation, or informational — does **not** live on the evidence record. It lives on the `HAS_EVIDENCE` edge between the finding and the evidence, as the `support_kind` property. That separation lets a single evidence artifact be reused across multiple findings with different relationships, and it keeps the verdict vocabulary on the relationship where it semantically belongs.

The vocabulary `passing | violation | informational` deliberately mirrors (and extends) the `relationship_type` enum on `RELATED_INDICATOR`, which currently uses `violation | informational | other`. A future iteration of `RELATED_INDICATOR` should add `passing` so the two enums align fully and downstream validation logic can read either edge with the same vocabulary. That alignment is called out in the Future section here rather than reshaped in v1.

This spec lives inside the FedRAMP 20x KSI plugin for the same reason Finding does: there is one compliance framework today, and when a second appears, Evidence and its edge will move to a dedicated compliance plugin alongside Finding and Exception. The type slug, edge name, and property vocabulary are deliberately generic (`evidence`, `HAS_EVIDENCE`, `support_kind`) to make that move a rename-free promotion.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Minimal            | v1 models only the three fields required to identify the artifact: name, description, kind |
| 2. | Verdict-On-Edge    | The `passing | violation | informational` verdict is carried by the edge, not the node — evidence is reusable across findings |
| 3. | Reusable           | A single evidence artifact may attach to many findings with different `support_kind` values |
| 4. | Generic-By-Design  | Type slug, edge name, and vocabulary carry no FedRAMP-specific terms; promotable to a general compliance plugin without rename |
| 5. | Evolvable          | Provenance fields (collected_at, source URL, hash, mime type), full-text search, and binary attachments are explicit Future work |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-evidence-model | [Evidence Model](#evidence-model) | Implemented | Minimal v1 `evidence` entity with name, description, kind |
| req-fedramp-20x-ksi-evidence-kind | [Evidence Kind Vocabulary](#evidence-kind-vocabulary) | Implemented | Enum: `screenshot`, `scanner_output`, `policy_doc`, `attestation`, `log_excerpt`, `other` |
| req-fedramp-20x-ksi-evidence-has-edge | [Finding Linkage — `HAS_EVIDENCE`](#finding-linkage--has_evidence) | Implemented | Edge from finding to evidence with `support_kind` property |
| req-fedramp-20x-ksi-evidence-support-kind | [Evidence Support-Kind Vocabulary](#evidence-support-kind-vocabulary) | Implemented | Enum: `passing`, `violation`, `informational` |
| req-fedramp-20x-ksi-evidence-dimension | [Dimension Membership](#dimension-membership) | Implemented | Evidence defaults to `compliance: fedramp-20x` while the model lives in this plugin |

---

### Evidence Model
----
RID: `req-fedramp-20x-ksi-evidence-model`
Status: `Implemented`

The `evidence` entity is a TAP-managed BaseModel with a minimal field set.

#### Implementation

`Evidence` is a `BaseModel` subclass at `plugins/fedramp_20x_ksi/models/evidence.py` with:

- `ENTITY_TYPE = "fedramp_20x_ksi__evidence"` (owner-namespaced per `req-plugin-type-node-prefix`, 2026-07-02 sweep)
- `ENTITY_NAME = "Evidence"`
- `ENTITY_ICON = "evidence"` (icon SVG deferred; sibling models like `finding` and `exception` follow the same pattern)
- `DEFAULT_DIMENSIONS = {"compliance": "fedramp-20x"}`
- Fields:
  - `name` — `CharField(max_length=255, blank=True, default="")`
  - `description` — `TextField(blank=True, default="")`
  - `kind` — `CharField(max_length=32, blank=True, default="other", db_index=True)` constrained to the kind vocabulary
- `CREATE_REQUIRED = ["name", "kind"]`

`get_name()` returns `self.name`; `Entity.name` is the spine projection per `req-grid-node-display`.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-evidence-model-1 | Model is registered | Implemented | `evidence` is registered in the plugin manifest under `[models]` and resolves to `tap_plugin.fedramp_20x_ksi.models.evidence.Evidence`. |
| req-fedramp-20x-ksi-evidence-model-2 | Schema accepts valid input | Implemented | `create_node(type_slug="evidence", payload={"name": ..., "kind": "scanner_output", ...})` succeeds and produces a corresponding `Entity` row. |
| req-fedramp-20x-ksi-evidence-model-3 | Required fields enforced | Implemented | Omitting `name` or `kind` produces a validation error from the service layer. |
| req-fedramp-20x-ksi-evidence-model-4 | Display projection synced | Implemented | After save, `entity.name` equals `Evidence.get_name()`. |

#### Future

- Provenance fields: `collected_at` (datetime), `source_url`, `content_hash`, `mime_type`.
- Full-text searchable body / excerpt field.
- Binary attachment integration (file storage backend not yet specified for this plugin).

---

### Evidence Kind Vocabulary
----
RID: `req-fedramp-20x-ksi-evidence-kind`
Status: `Implemented`

The `kind` field constrains evidence to a small categorical set covering the most common compliance artifact types.

#### Implementation

The v1 enum:

- `screenshot` — captured UI state demonstrating configuration or behavior.
- `scanner_output` — output from automated security or compliance scanners.
- `policy_doc` — text of a policy, standard, or procedure that governs the asset.
- `attestation` — a written statement signed or asserted by a responsible party.
- `log_excerpt` — relevant lines from system or application logs.
- `other` — fallback for artifacts that do not yet warrant their own enum value.

The default value is `"other"` so unspecified-kind evidence remains valid.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-evidence-kind-1 | Schema enforces enum | Implemented | `kind` outside the v1 set produces a validation error from `FIELD_VALIDATION_SCHEMA`. |
| req-fedramp-20x-ksi-evidence-kind-2 | Default applied | Implemented | When omitted, `kind` defaults to `"other"`. |

#### Future

- Subdivide `scanner_output` by tool (e.g. `nessus_scan`, `prowler_scan`) once specific scanner integrations exist.
- Add `image` / `pdf` / `text` content-type metadata as separate fields once binary attachments land.

---

### Finding Linkage — `HAS_EVIDENCE`
----
RID: `req-fedramp-20x-ksi-evidence-has-edge`
Status: `Implemented`

A finding may have one or more pieces of evidence connected via the `HAS_EVIDENCE` edge.

#### Implementation

Edge slug: `HAS_EVIDENCE`. Definition at `plugins/fedramp_20x_ksi/edges/HAS_EVIDENCE.edge.json`:

- `sources: ["finding"]`
- `targets: ["evidence"]`
- `property_schema`:
  - `support_kind` — required, enum (see [Evidence Support-Kind Vocabulary](#evidence-support-kind-vocabulary))
  - `note` — optional free-text annotation
  - `additionalProperties: false`
- `default_dimensions: {"compliance": "fedramp-20x"}`

Multiple `HAS_EVIDENCE` edges per finding are expected. The finding's effective verdict (passing, violation, informational) is **derived** from the aggregated `support_kind` values of its evidence; it is not stored on the finding itself.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-evidence-has-edge-1 | Edge type is registered | Implemented | `HAS_EVIDENCE` is registered in the plugin manifest under `[edges]`. |
| req-fedramp-20x-ksi-evidence-has-edge-2 | Source/target enforced | Implemented | Edges where source is not a `finding` or target is not an `evidence` are rejected by the service layer. |
| req-fedramp-20x-ksi-evidence-has-edge-3 | Property schema enforced | Implemented | Edges with `support_kind` outside the enum or with unknown property keys are rejected. |
| req-fedramp-20x-ksi-evidence-has-edge-4 | Default dimensions applied | Implemented | New edges inherit `compliance: fedramp-20x` when the caller does not override. |

#### Future

- Reverse edge `EVIDENCES` (evidence → finding) — currently HAS_EVIDENCE traverses both directions through gryphon; an explicit reverse edge would only land if directionality becomes load-bearing for a query.
- Aggregation projection: a derived field on Finding (or a runtime helper) that summarizes the dominant `support_kind` across attached evidence.

---

### Evidence Support-Kind Vocabulary
----
RID: `req-fedramp-20x-ksi-evidence-support-kind`
Status: `Implemented`

The `support_kind` enum on `HAS_EVIDENCE` classifies what verdict the evidence supports for the finding.

#### Implementation

The v1 enum:

- `passing` — evidence demonstrates the finding is in a passing / approved / acceptable state with respect to the related KSI indicator(s).
- `violation` — evidence demonstrates a violation of the related KSI indicator(s).
- `informational` — evidence is contextual; it neither passes nor violates the indicator but is relevant to understanding the finding.

The vocabulary is intentionally aligned with (and extends) the `relationship_type` enum on `RELATED_INDICATOR`, which currently carries `violation | informational | other`. A future iteration of `RELATED_INDICATOR` should add `passing` so both edges share a single vocabulary; that alignment is tracked under [Future](#future-2).

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-evidence-support-kind-1 | Enum enforced | Implemented | `support_kind` outside the enum produces an `EdgePropertyValidationError`. |
| req-fedramp-20x-ksi-evidence-support-kind-2 | Required on create | Implemented | Edges created without `support_kind` are rejected. |

#### Future <a name="future-2"></a>

- Align `RELATED_INDICATOR.relationship_type` to include `passing`, then route validation logic for both edges through a single shared enum constant.
- Add a fourth value (e.g. `mitigating`) when the demo workflow needs a finer-grained verdict for findings backed by partial evidence.

---

### Dimension Membership
----
RID: `req-fedramp-20x-ksi-evidence-dimension`
Status: `Implemented`

Evidence and `HAS_EVIDENCE` edges default to `compliance: fedramp-20x` while the model lives in this plugin.

#### Implementation

- `Evidence.DEFAULT_DIMENSIONS = {"compliance": "fedramp-20x"}`.
- `HAS_EVIDENCE.edge.json` declares `default_dimensions: {"compliance": "fedramp-20x"}`.

When the model is promoted to a general compliance plugin, both defaults will move with it, and downstream callers that import dimension defaults from the new plugin will pick up the new convention.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-evidence-dimension-1 | Node default applied | Implemented | New evidence created without explicit dimensions inherits `compliance: fedramp-20x`. |
| req-fedramp-20x-ksi-evidence-dimension-2 | Edge default applied | Implemented | New `HAS_EVIDENCE` edges created without explicit dimensions inherit `compliance: fedramp-20x`. |

---

## Out of Scope (v1)

- Binary attachments (images, PDFs, raw scanner output as files).
- Provenance fields (collected_at, source URL, hash, mime type).
- Full-text searchable body.
- Cross-framework crosswalks (evidence reused across compliance frameworks).
- An explicit reverse edge from evidence to finding.
- A dedicated UI surface for evidence; the Anwar/Ace of Clouds demo will reach evidence via drill-down from findings, not via an evidence-first index.
