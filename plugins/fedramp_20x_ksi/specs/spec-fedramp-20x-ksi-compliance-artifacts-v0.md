# FedRAMP 20x KSI Compliance Artifacts Specification

## Philosophy

A modern compliance program emits machine-readable artifacts: a KSI validation
signal, OSCAL documents, a vulnerability-detection report, an inventory
workbook. Samuel Aydlette's samaydlette.com publishes exactly this family to a
public `/.well-known/` surface, each artifact Sigstore-signed, as a worked
proposal for portfolio-scale compliance reasoning (the KSI signal schema is
`samaydlette.com/.well-known/ksi-signal.schema.json`, published MIT-licensed).
TAP ingests these artifacts. This spec defines what they *become on the grid*.

The artifacts are framework-domain, not deployment-specific. The KSI signal is
a *proposed cross-CSP standard* — any system can emit one; samsite merely
happens to. So the model catalog lives in `fedramp_20x_ksi`, the plugin that
owns FedRAMP-20x-KSI vocabulary (themes, indicators, findings, evidence,
boundaries). The `samsite` plugin owns only the *collector* — the
deployment-specific machinery that fetches samsite's particular URLs. Framework
owns the vocabulary; deployment owns the wiring. This mirrors `aws_core` owning
the AWS model vocabulary that any AWS deployment uses.

The central modeling decision: **the KSI signal is a graph Sam serialized to
JSON because JSON was his transport.** Its schema describes a graph in prose —
`components[]` are things with identity; `validations[].component_refs` is, in
the schema's own words, "the field that makes the signal compose — a portfolio
consumer joins on these refs." TAP restores the graph. Sam's marquee query —
"which validations covered component X" — becomes a one-hop Gryphon traversal,
not a nested-array scan.

The VDR report is decomposed the same way, and faithfully to Sam's framework.
His Vulnerability Detection and Response model — **PAIN** (N1–N5 severity),
**IRV** (internet-reachable), **LEV** (likely-exploitable), **KEV** (CISA
Known-Exploited), Class-C remediation SLAs — is the evaluation schema of a
finding. So a `vdr_finding` carries PAIN/IRV/LEV/KEV/SLA as *typed fields*:
"every N4+ internet-reachable finding past SLA" is a Gryphon `WHERE`. Modeling
his framework as queryable fields *is* the faithful adoption.

Two artifacts are deliberately **not** decomposed. The OSCAL SSP, OSCAL POA&M,
and IIW are downstream *renderings* of the same canonical inventory the KSI
signal already carries (`build-iiw.py` and `build-oscal-ssp.py` read
`ksi-signal.json` as their source). Decomposing them would model that inventory
three more times. They become `compliance_artifact` blob nodes — fetched,
verified, stored whole. Decompose the source of truth; blob the renderings.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Restore The Graph | The KSI signal and the VDR report decompose into grid nodes and edges, not JSON arrays in a blob. |
| 2. | Faithful To Sam's Framework | PAIN / IRV / LEV / KEV and the Class-C SLA are typed, queryable fields on `vdr_finding`. |
| 3. | Honest Fields, Principled Blobs | Scalars and fixed objects become typed columns; a JSON blob is used only where the source schema itself declares a field free-form. |
| 4. | Lossless | The strict closed source schemas make "decompose to grid, recompose to JSON" a checkable round-trip. |
| 5. | Framework-Domain Placement | The catalog lives in `fedramp_20x_ksi`; the `samsite` plugin owns only the collector. |
| 6. | Decompose The Source, Blob The Renderings | KSI signal + VDR decomposed; OSCAL SSP/POA&M and IIW kept whole — they are renderings of the signal's inventory. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-compliance-catalog | [Model Catalog](#model-catalog) | Proposed | Seven models — KSI-signal decomposition, VDR decomposition, rendering-artifact node |
| req-fedramp-20x-ksi-signal | [KSI Signal Model](#ksi-signal-model) | Proposed | The emission node — typed top-level fields, flattened provenance/ownership, verification result |
| req-fedramp-20x-ksi-component | [KSI Component Model](#ksi-component-model) | Proposed | One model, `type` discriminator; `attributes`/`information_flow` schema-authorized structured fields |
| req-fedramp-20x-ksi-validation | [KSI Validation Model](#ksi-validation-model) | Proposed | Validation results; `component_refs` and `violations` materialized as edges |
| req-fedramp-20x-ksi-violation | [KSI Violation Model](#ksi-violation-model) | Proposed | A policy violation split out as a node; cousin of `finding` — unification deferred |
| req-fedramp-20x-ksi-vdr-report | [VDR Report Model](#vdr-report-model) | Proposed | The VDR emission node |
| req-fedramp-20x-ksi-vdr-finding | [VDR Finding Model](#vdr-finding-model) | Proposed | A vulnerability finding — PAIN/IRV/LEV/KEV/SLA as typed fields |
| req-fedramp-20x-ksi-compliance-artifact | [Compliance Artifact Model](#compliance-artifact-model) | Proposed | OSCAL SSP / POA&M / IIW kept whole — `kind` discriminator |
| req-fedramp-20x-ksi-compliance-edges | [Edge Catalog](#edge-catalog) | Proposed | Seven edges joining the decomposed subgraphs |
| req-fedramp-20x-ksi-compliance-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Global vulnerability registry, information-flow edges, aws_core cross-edge, violation/finding unification |

---

### Model Catalog
----
RID: `req-fedramp-20x-ksi-compliance-catalog`
Status: `Proposed`

Seven `fedramp_20x_ksi` models. The KSI signal decomposes into four; the VDR
report into two; rendering artifacts share one.

| Model | Role |
| --- | --- |
| `ksi_signal` | One emission of the KSI signal — top-level identity, provenance, verification result. |
| `ksi_component` | One component the signal names. `components[]`, decomposed one node per entry. |
| `ksi_validation` | One validation result the signal carries. `validations[]`, one node per entry. |
| `ksi_violation` | One policy violation a failed validation reports. |
| `vdr_report` | One emission of the VDR report. |
| `vdr_finding` | One vulnerability finding the VDR report carries. |
| `compliance_artifact` | A rendering artifact kept whole — OSCAL SSP, OSCAL POA&M, IIW. `kind` discriminator. |

Discipline: `ksi_component` is **one** model with a `type` discriminator across
the schema's component-type enum, and `compliance_artifact` is **one** model
with a `kind` discriminator — polymorphism rides a field, never a model
explosion. The catalog grew from a 4-model first draft to 7 because the
violations split and the VDR decomposition were explicitly chosen; each of the
7 is a genuinely distinct entity.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-catalog-1 | Seven Models | Proposed | The plugin registers exactly the seven models above. | |
| req-fedramp-20x-ksi-compliance-catalog-2 | Discriminator Not Explosion | Proposed | Component and artifact polymorphism is a `type`/`kind` field, not one model per variant. | |
| req-fedramp-20x-ksi-compliance-catalog-3 | Framework-Plugin-Local | Proposed | All seven models live in `fedramp_20x_ksi`; the `samsite` plugin contributes none of them. | |

### KSI Signal Model
----
RID: `req-fedramp-20x-ksi-signal`
Status: `Proposed`

`ksi_signal` is one emission of the KSI signal document. Two emissions with the
same `signal_id` are the same observation; different `signal_id`s are different
observations over time.

**Typed top-level fields:** `signal_version`, `signal_id`, `emitted_at`,
`emitter` (enum `deploy`/`runtime`), `csp`, `system_id`.

**Flattened fixed objects.** `provenance` (`builder.id`, `builder.run_id`,
`builder.version`, `source.repository`, `source.commit`, `source.ref`),
`ownership` (`system_owner`, `application_owner`, `operator_contact`), and
`disclosure` (`authorization_status`, `fedramp_certified`, `remarks`) are small
fixed-shape objects — flattened to typed columns.

**Principled blob.** `provenance.attestation` is declared
`additionalProperties: true` by the source schema — genuinely free-form (the
Sigstore bundle). It is a JSON field.

**Verification fields**, populated by the collector, not the document:
`signature_verified`, `signed_by`, `rekor_log_index`, `verified_at`.

`ENTITY_ICON`: `ksi-signal`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-signal-1 | Top-Level Scalars Typed | Proposed | `signal_id`, `emitted_at`, `emitter`, `csp`, `system_id`, `signal_version` are typed columns. | |
| req-fedramp-20x-ksi-signal-2 | Fixed Objects Flattened | Proposed | `provenance`, `ownership`, `disclosure` flatten to typed columns, not blobs. | |
| req-fedramp-20x-ksi-signal-3 | Attestation Is A Blob | Proposed | `provenance.attestation` is a JSON field — the source schema declares it free-form. | |
| req-fedramp-20x-ksi-signal-4 | Verification Result Recorded | Proposed | `signature_verified`, `signed_by`, `rekor_log_index`, `verified_at` are typed fields the collector populates. | |

### KSI Component Model
----
RID: `req-fedramp-20x-ksi-component`
Status: `Proposed`

`ksi_component` is one entry of `components[]`. One model; `type` discriminates
across the schema's normalized component-type enum (`object_store`, `function`,
`cdn_distribution`, `npm_package`, `html_artifact`, `iam_role`, …).

**Typed fields:** `component_id` (the join key), `type`, `native_id`.
`global_id`'s sub-keys flatten to `global_purl`, `global_sha256`,
`global_image_digest` so a prefix query (`global_purl STARTS_WITH "pkg:npm/"`)
is reachable. `security_category` flattens to three enum columns
(`confidentiality`, `integrity`, `availability`).

**Principled blob:** `attributes` — the source schema declares it
`additionalProperties: true` and tells consumers to "treat unknown keys as
opaque." It is genuinely free-form and varies by component type; a JSON field.

**`information_flow` in v0:** retained as structured data on the component, not
yet decomposed into a flow-edge graph. It is conceptually edges, but
counterparties mix component-ids with free-form external strings, and the v0
marquee query does not need it. Flow-edge decomposition is a named non-goal.

`ENTITY_ICON`: `ksi-component`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-component-1 | One Model, Type Discriminator | Proposed | All component types are one `ksi_component` model discriminated by `type`. | |
| req-fedramp-20x-ksi-component-2 | Identifiers Typed | Proposed | `component_id`, `type`, `native_id`, flattened `global_id` and `security_category` are typed columns. | |
| req-fedramp-20x-ksi-component-3 | Attributes Is A Blob | Proposed | `attributes` is a JSON field — schema-authorized free-form. | |
| req-fedramp-20x-ksi-component-4 | Information Flow Retained | Proposed | `information_flow` is retained as structured data; flow-edge decomposition is deferred. | |

### KSI Validation Model
----
RID: `req-fedramp-20x-ksi-validation`
Status: `Proposed`

`ksi_validation` is one entry of `validations[]` — a policy result against a
set of components.

**Typed fields:** `validation_id`, `policy_id`, `policy_version` (the `policy`
object flattened), `result` (enum `pass`/`fail`).

**`component_refs`** is materialized as `EVALUATES_COMPONENT` edges — the join
the KSI schema is built around. **`violations`** is materialized as
`REPORTS_VIOLATION` edges to `ksi_violation` nodes. Neither is a stored array;
both are the graph.

`ENTITY_ICON`: `ksi-validation`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-validation-1 | Result Typed | Proposed | `validation_id`, `policy_id`, `policy_version`, `result` are typed columns. | |
| req-fedramp-20x-ksi-validation-2 | Component Refs Are Edges | Proposed | Each `component_refs` entry becomes one `EVALUATES_COMPONENT` edge. | |
| req-fedramp-20x-ksi-validation-3 | Violations Are Edges | Proposed | Each `violations[]` entry becomes a `ksi_violation` node linked by `REPORTS_VIOLATION`. | |

### KSI Violation Model
----
RID: `req-fedramp-20x-ksi-violation`
Status: `Proposed`

`ksi_violation` is one specific finding from a failed validation. The source
schema notes violations are "the same shape as the OPA `compliance_report`
violations the existing pipeline produces."

**Typed fields:** `violation_type` (the schema's `type`), `message`, `severity`
(enum `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`), `resource`.

**Open question — recorded, deliberately not resolved in v0.** `ksi_violation`
is a cousin of the existing `finding` model: both represent "something wrong
with the system," and the VDR collector even ingests OPA output, so a
`ksi_violation` and a `vdr_finding`-from-OPA can be the same underlying issue
surfaced in two artifacts. v0 keeps `ksi_violation` distinct (a raw policy
violation is not catalog-tied the way `finding` is — `finding` carries regime
and KSI-indicator linkage). Whether `finding`'s shape, a shared base, or a
merge is the right long-term answer is revisited once a second consumer of
violation data appears. `ksi_violation` lives alongside `finding` in this
plugin precisely so that future decision has both models in one place.

`ENTITY_ICON`: `ksi-violation`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-violation-1 | Violation Fields Typed | Proposed | `violation_type`, `message`, `severity`, `resource` are typed columns. | |
| req-fedramp-20x-ksi-violation-2 | Finding-Shape Question Recorded | Proposed | The spec records that `ksi_violation` vs `finding` unification is an open question, deferred to a second consumer. | |

### VDR Report Model
----
RID: `req-fedramp-20x-ksi-vdr-report`
Status: `Proposed`

`vdr_report` is one emission of the Vulnerability Detection and Response report.

**Typed fields:** `report_version`, `report_id`, `emitted_at`, `system_id`,
`vdr_class` (the report's `class` — `C` for the demo system), `ksi_signal_ref`
(URL string), `poam_ref`.

**Blob:** `summary` — the report's derived rollup counts (`by_pain`, `blocking`,
`kev`, `risk_accepted`, totals). It is a derived denormalization; the queryable
truth is the `vdr_finding` nodes, so the rollup is retained as a JSON field
rather than flattened into a dozen count columns.

The report's `ksi_signal_ref` is materialized as a `REFERENCES_SIGNAL` edge to
the `ksi_signal` it cites.

`ENTITY_ICON`: `vdr-report`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-vdr-report-1 | Report Fields Typed | Proposed | `report_id`, `report_version`, `emitted_at`, `system_id`, `vdr_class` are typed columns. | |
| req-fedramp-20x-ksi-vdr-report-2 | Summary Is A Blob | Proposed | `summary` is a JSON field — a derived rollup, not the queryable substance. | |
| req-fedramp-20x-ksi-vdr-report-3 | Signal Reference Is An Edge | Proposed | `ksi_signal_ref` is materialized as a `REFERENCES_SIGNAL` edge when the cited signal is on the grid. | |

### VDR Finding Model
----
RID: `req-fedramp-20x-ksi-vdr-finding`
Status: `Proposed`

`vdr_finding` is one vulnerability finding — and the model where Sam's VDR
evaluation framework lives, as typed fields. The report's `findings[]`
(disposition `open`) and `risk_accepted[]` (disposition `risk-accepted`) are
both `vdr_finding` nodes, discriminated by `current_disposition`.

**Provenance / identity:** `tracking_id`, `source` (enum `opa`/`checkov`/
`tfsec`/`dependabot`), `tool_id`, `title`, `description`, `resource`, `cve`,
`first_detected`, `days_since_first_detected`.

**Sam's framework, as typed fields:** `pain` (enum `N1`–`N5`),
`internet_reachable` (bool — IRV), `likely_exploitable` (bool — LEV), `is_kev`
(bool — CISA Known-Exploited), `remediation_sla_days`, `remediation_due_at`,
`is_blocking`, `block_reason`.

**Disposition:** `current_disposition` (enum `open`/`risk-accepted`);
risk-accepted findings additionally carry `explanation` and `poam_ref`.

Modeling the framework as typed columns is the faithful adoption: "every
`pain` ≥ N4 finding that is `internet_reachable` and past
`remediation_due_at`" is a Gryphon `WHERE`, not a blob scan.

The finding's `resource` is materialized, best-effort, as an `AFFECTS_RESOURCE`
edge (see the edge catalog); the `resource` string itself is retained as a
typed field regardless.

`ENTITY_ICON`: `vdr-finding`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-vdr-finding-1 | Framework Fields Typed | Proposed | `pain`, `internet_reachable`, `likely_exploitable`, `is_kev`, SLA fields, `is_blocking` are typed columns. | |
| req-fedramp-20x-ksi-vdr-finding-2 | One Model, Disposition Discriminator | Proposed | `open` findings and `risk-accepted` suppressions are one model discriminated by `current_disposition`. | |
| req-fedramp-20x-ksi-vdr-finding-3 | Resource Retained And Edged | Proposed | `resource` is a typed field; the `AFFECTS_RESOURCE` edge resolves it best-effort. | |
| req-fedramp-20x-ksi-vdr-finding-4 | CVE Is A Field In v0 | Proposed | `cve` is a typed field; a global vulnerability/CVE node is a v0 non-goal. | |

### Compliance Artifact Model
----
RID: `req-fedramp-20x-ksi-compliance-artifact`
Status: `Proposed`

`compliance_artifact` is a rendering artifact kept whole. One model, `kind`
discriminator: `oscal_ssp`, `oscal_poam`, `iiw`.

OSCAL SSP, OSCAL POA&M, and IIW are downstream renderings of the same canonical
inventory the KSI signal carries — decomposing them would re-model that
inventory. All three are therefore the same shape: typed metadata + the
document as a blob.

**Typed fields:** `kind`, `source_url`, `content_type`, `fetched_at`,
`size_bytes`, and the verification fields (`signature_verified`, `signed_by`,
`rekor_log_index`, `verified_at`).

**Blob:** `content` — the fetched document, parsed to JSON where it is JSON
(OSCAL), retained as text where it is not (IIW is CSV).

`ENTITY_ICON`: `compliance-artifact`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-artifact-1 | One Model, Kind Discriminator | Proposed | OSCAL SSP/POA&M and IIW are one `compliance_artifact` model discriminated by `kind`. | |
| req-fedramp-20x-ksi-compliance-artifact-2 | Metadata Typed, Document Blobbed | Proposed | Source/fetch/verification metadata are typed columns; the document body is the `content` blob. | |
| req-fedramp-20x-ksi-compliance-artifact-3 | Renderings Not Decomposed | Proposed | OSCAL/IIW are not decomposed — they are renderings of the KSI inventory. | |

### Edge Catalog
----
RID: `req-fedramp-20x-ksi-compliance-edges`
Status: `Proposed`

Seven edges, all `fedramp_20x_ksi`-owned, slugs per the `<ACTION>_<OBJECT>`
convention.

| Edge | Direction | Meaning |
| --- | --- | --- |
| `DECLARES_COMPONENT` | `ksi_signal → ksi_component` | The signal names this component. |
| `DECLARES_VALIDATION` | `ksi_signal → ksi_validation` | The signal carries this validation result. |
| `EVALUATES_COMPONENT` | `ksi_validation → ksi_component` | The validation evaluated this component — the `component_refs` join. |
| `REPORTS_VIOLATION` | `ksi_validation → ksi_violation` | A failed validation reports this violation. |
| `REPORTS_FINDING` | `vdr_report → vdr_finding` | The VDR report carries this finding. |
| `AFFECTS_RESOURCE` | `vdr_finding → <affected node>` | The vulnerability is in this resource. Polymorphic target; resolved best-effort. |
| `REFERENCES_SIGNAL` | `vdr_report → ksi_signal` | The report's `ksi_signal_ref` cross-link. |

`EVALUATES_COMPONENT` is the load-bearing one — the materialization of
`component_refs`, the edge that makes "which validations covered component X" a
one-hop traversal.

`AFFECTS_RESOURCE` has a polymorphic target (a `ksi_component`, a future
`software_package`, an `aws_core` node) and a fuzzy join — `vdr_finding.resource`
is heterogeneous (`ecosystem:package`, Terraform addresses, ARNs). v0 resolves
it **best-effort**: an edge is emitted where `resource` cleanly maps to a node
already on the grid; where it does not, the `resource` field stands alone and
no dangling edge is emitted. Full resolution is a future resolver, the same
shape as the `aws_core` edge-resolver seam. `sources` is `vdr_finding`;
`targets` is an intentional wildcard.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-edges-1 | Seven Edges | Proposed | The seven edge types above are registered `fedramp_20x_ksi` edges. | |
| req-fedramp-20x-ksi-compliance-edges-2 | Component Refs Materialized | Proposed | Each `validations[].component_refs` entry becomes one `EVALUATES_COMPONENT` edge. | |
| req-fedramp-20x-ksi-compliance-edges-3 | Affects-Resource Best-Effort | Proposed | `AFFECTS_RESOURCE` is emitted only where `resource` resolves to an on-grid node; unresolved findings keep the `resource` field with no dangling edge. | |

### v0 Non-Goals
----
RID: `req-fedramp-20x-ksi-compliance-nongoals`
Status: `Proposed`

Named, deferred — not abandoned (future-seam discipline).

- **Global vulnerability / CVE registry.** v0 keeps `cve` and `is_kev` as
  fields on `vdr_finding`. A global `vulnerability` node (CVE identity, KEV
  catalog ingestion, one node many findings reference) is the marquee
  vulnerability-management theme proper — a layer above this collector. v0
  models Sam's per-finding *evaluation* framework; the global *vulnerability
  universe* is its own theme.
- **Information-flow edges.** `ksi_component.information_flow` is retained as
  structured data. Decomposing it into a component-to-component flow graph
  waits on resolving how external (non-component) counterparties are modeled.
- **`ksi_violation` / `finding` unification.** Recorded as an open question on
  `req-fedramp-20x-ksi-violation`; deferred to a second consumer.
- **OSCAL / IIW decomposition.** Permanently not planned — they are renderings
  of the KSI inventory; decomposing them re-models the signal.
- **The aws_core cross-edge.** A `ksi_component` whose `type` maps to a
  collected AWS resource (`object_store` ↔ `aws_s3_bucket`, `function` ↔
  `aws_lambda`) could edge to the real collected node — the system as attested
  versus the system as observed. High-value; out of v0 scope.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-compliance-nongoals-1 | Deferrals Named | Proposed | Each deferral is named as a bounded future seam, not an oversight. | |
| req-fedramp-20x-ksi-compliance-nongoals-2 | Renderings Stay Renderings | Proposed | OSCAL/IIW decomposition is recorded as permanently not planned, with rationale. | |

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`,
`Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`,
`Backlog`.
