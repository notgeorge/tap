# Samsite Compliance Collector Specification

## Philosophy

The samsite demo's compliance machinery publishes a family of Sigstore-signed
artifacts to `/.well-known/` on the public website — `ksi-signal.json`,
`oscal-ssp.json`, `oscal-poam.json`, `vdr-report.json`, `iiw.csv`, each paired
with a `.bundle` (Fulcio cert + signature + Rekor inclusion proof). This spec
defines the **collector** that ingests them: a daily run that fetches the set
over HTTPS, verifies every signature, and lands the result on the grid.

This spec owns only the collector. **What the artifacts become on the grid —
the model catalog — is `spec-fedramp-20x-ksi-compliance-artifacts-v0.md`**, in
the `fedramp_20x_ksi` plugin. The split is deliberate: the KSI signal and the
VDR report are framework-domain formats (Sam's KSI signal is a proposed
cross-CSP standard), so their models belong with the FedRAMP-20x-KSI
vocabulary. The collector is deployment-specific — it fetches *samsite's*
particular URLs — so it belongs in the `samsite` plugin. Framework owns the
vocabulary; deployment owns the wiring; this mirrors `aws_core` owning the AWS
model vocabulary that the boto3 collector populates.

The collector is concrete and samsite-specific in v0. A **generic web
collector** — fetch-and-verify against any declarative URL set, reusable beyond
samsite — is the future archetype, named here as a seam, not built. The samsite
collector is its first proving instance.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | One Run, Whole Set | A single scheduled run fetches every `.well-known/` artifact, verifies each, and submits one GRIFT batch. |
| 2. | Verify Every Signature | Each artifact is checked against its Sigstore `.bundle`; the verification result lands on the node. |
| 3. | Decompose Via The Framework Spec | The collector decomposes the KSI signal and VDR into the `fedramp_20x_ksi` models; it does not define its own model shapes. |
| 4. | Declarative Manifest | The URL set and per-artifact handling are data, not code. |
| 5. | Daily, Reusing Existing Infrastructure | Runs daily on the `tap_cares` scheduler; adds no collector or scheduler framework. |
| 6. | Concrete Now, Generic Later | v0 is the samsite collector; the reusable generic web collector is a named future seam. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-samsite-collector | [The Collector](#the-collector) | Proposed | `CollectorBase` subclass; no cloud creds; one run grabs the whole `.well-known/` set |
| req-samsite-collector-manifest | [Artifact Manifest](#artifact-manifest) | Proposed | Declarative `{url, kind, handling}` manifest, JSON-Schema-validated |
| req-samsite-collector-verify | [Signature Verification](#signature-verification) | Proposed | `sigstore` library; verification result recorded; failure visible, not fatal |
| req-samsite-collector-decompose | [Decomposition](#decomposition) | Proposed | KSI signal + VDR decomposed into the fedramp models; OSCAL/IIW blobbed |
| req-samsite-collector-schedule | [Daily Schedule](#daily-schedule) | Proposed | Registered to run daily through the `tap_cares` scheduler |
| req-samsite-collector-identity | [Identity And Emission History](#identity-and-emission-history) | Proposed | Components dedup across emissions; signals/reports/findings per-emission |
| req-samsite-collector-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Generic web collector archetype, deferred |

---

### The Collector
----
RID: `req-samsite-collector`
Status: `Proposed`

A `CollectorBase` subclass in the `samsite` plugin. Unlike the boto3 collector
it needs no cloud credentials — it fetches public artifacts over HTTPS. One run
grabs the entire `.well-known/` set, verifies each, decomposes per
`req-samsite-collector-decompose`, and submits one GRIFT batch.

It reuses the `tap_cares` collector runtime end to end: registration, run
records, the GRIFT submission boundary, and the abort-on-rejection default. It
is a second `CollectorBase` implementation alongside the boto3 one, not a new
framework. A per-artifact fetch or verification failure is recorded as a
structured `warn`/`error`, never silently dropped; the run still collects the
artifacts that succeeded.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-collector-1 | CollectorBase Subclass | Proposed | The collector subclasses `CollectorBase` and uses the standard `tap_cares` runtime. | |
| req-samsite-collector-2 | One Run, Whole Set | Proposed | A single run fetches every artifact in the manifest. | |
| req-samsite-collector-3 | No Cloud Credentials | Proposed | The collector fetches public HTTPS URLs; it requires no AWS or other cloud credentials. | |
| req-samsite-collector-4 | GRIFT Submission | Proposed | The run produces one GRIFT batch via `CollectorBase.submit_grift`; partial failures are recorded, not dropped. | |

### Artifact Manifest
----
RID: `req-samsite-collector-manifest`
Status: `Proposed`

The set of URLs to fetch and how to handle each is **declarative data, not
code** — a JSON manifest of `{url, kind, handling}` entries, validated by a
JSON Schema authored in the same change. `handling` selects the decomposition
path: `ksi_signal`, `vdr_report`, or `compliance_artifact` (blob). This is the
same declarative-shapes discipline as the boto3 collector's resource manifest —
an agent reads the manifest and knows what the collector fetches without
reading collector code.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-collector-manifest-1 | Declarative URL Set | Proposed | The fetch targets live in a JSON manifest, not hardcoded in the collector. | |
| req-samsite-collector-manifest-2 | Schema-Validated | Proposed | The manifest ships a JSON Schema and is validated at load — fail loud on invalid. | |

### Signature Verification
----
RID: `req-samsite-collector-verify`
Status: `Proposed`

Every artifact ships a paired `.bundle` (Sigstore keyless: Fulcio cert +
signature + Rekor inclusion proof). The collector verifies each artifact
against its bundle using the **`sigstore`** Python library — added to the root
`pyproject.toml` 2026-05-22; the dependency-approval gate is cleared. The
verification result is recorded on the node (`signature_verified`, `signed_by`,
`rekor_log_index`, `verified_at`).

A failed or unverifiable signature is recorded as `signature_verified =
false`/`null` — never silently dropped — and does not abort the run; an
unverified artifact is still collected, flagged.

**Scope line.** v0 verification is *bounded evaluation* — signature checking,
Rekor inclusion-proof checking, JSON-Schema validation, parsing. It does not
run fetched content as code. Arbitrary code-against-fetched-content is the
sandbox/satellite concern and is out of scope.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-collector-verify-1 | Bundles Verified | Proposed | Each artifact is verified against its `.bundle` via `sigstore`; the result is recorded on the node. | |
| req-samsite-collector-verify-2 | Failure Is Visible, Not Fatal | Proposed | A failed/unverifiable signature is recorded as such; the artifact still collects; the run does not abort. | |
| req-samsite-collector-verify-3 | Bounded Evaluation Only | Proposed | v0 verification is signature/proof/schema checking and parsing — never executing fetched content as code. | |

### Decomposition
----
RID: `req-samsite-collector-decompose`
Status: `Proposed`

The collector does not define model shapes — it produces nodes and edges per
`spec-fedramp-20x-ksi-compliance-artifacts-v0.md`:

- `ksi-signal.json` → a `ksi_signal` node, one `ksi_component` per
  `components[]`, one `ksi_validation` per `validations[]`, one `ksi_violation`
  per `violations[]`, and the `DECLARES_COMPONENT` / `DECLARES_VALIDATION` /
  `EVALUATES_COMPONENT` / `REPORTS_VIOLATION` edges.
- `vdr-report.json` → a `vdr_report` node, one `vdr_finding` per `findings[]`
  and `risk_accepted[]`, and the `REPORTS_FINDING` / `AFFECTS_RESOURCE` /
  `REFERENCES_SIGNAL` edges.
- `oscal-ssp.json`, `oscal-poam.json`, `iiw.csv` → one `compliance_artifact`
  blob node each.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-collector-decompose-1 | Framework Spec Owns Shapes | Proposed | The collector emits the `fedramp_20x_ksi` models; it defines no model shapes of its own. | |
| req-samsite-collector-decompose-2 | Signal And VDR Decomposed | Proposed | The KSI signal and VDR report are decomposed into their respective node/edge sets. | |
| req-samsite-collector-decompose-3 | Renderings Blobbed | Proposed | OSCAL SSP/POA&M and IIW each become one `compliance_artifact` node. | |

### Daily Schedule
----
RID: `req-samsite-collector-schedule`
Status: `Proposed`

The collector is registered to run on a daily schedule through the existing
`tap_cares` scheduler. Each run is one emission observation. The schedule is
collector configuration, not new scheduling infrastructure.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-collector-schedule-1 | Daily Cadence | Proposed | The collector is registered with a daily schedule via the `tap_cares` scheduler. | |
| req-samsite-collector-schedule-2 | No New Scheduler | Proposed | Scheduling reuses the existing scheduler; the collector adds no scheduling machinery. | |

### Identity And Emission History
----
RID: `req-samsite-collector-identity`
Status: `Proposed`

Deterministic identity, so re-runs upsert:

- `ksi_signal` — keyed by `signal_id`. Per-emission.
- `ksi_validation` — keyed by `signal_id` + `validation_id`. Per-emission.
- `ksi_violation` — keyed by `signal_id` + `validation_id` + a per-violation
  discriminator. Per-emission.
- `ksi_component` — keyed by `component_id`. The KSI schema states
  `component_id` is "stable across emissions where possible," so component
  nodes **deduplicate across emissions** — upserted, not re-created.
- `vdr_report` — keyed by `report_id`. Per-emission.
- `vdr_finding` — keyed by `report_id` + `tracking_id`. Per-emission. (A
  finding's `tracking_id` is stable across reports; the per-report key keeps
  each emission's evaluation distinct, which is the point — SLA clocks move.)
- `compliance_artifact` — keyed by `kind` + a per-emission discriminator.

Consequence, intentional: `ksi_component` nodes form a stable spine the daily
signal/validation/report emissions hang off, building an emission history.
Retention/pruning of old emissions is not a v0 concern — flagged for the
history system when emission volume warrants it.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-collector-identity-1 | Deterministic Identity | Proposed | Every node has a deterministic id so re-runs upsert rather than duplicate. | |
| req-samsite-collector-identity-2 | Components Dedup | Proposed | `ksi_component` nodes dedup across emissions by `component_id`. | |
| req-samsite-collector-identity-3 | Emissions Are Per-Run | Proposed | Signal, validation, violation, report, and finding nodes are per-emission; daily runs accumulate history. | |

### v0 Non-Goals
----
RID: `req-samsite-collector-nongoals`
Status: `Proposed`

- **Generic web collector.** v0 is the concrete samsite collector. A reusable
  fetch-and-verify web-collector engine — declarative URL set, generic
  verification, beyond samsite — is the future archetype. The samsite collector
  is its first proving instance; generalizing it waits for a second consumer.
- **Model shapes.** Owned entirely by `spec-fedramp-20x-ksi-compliance-artifacts-v0.md`;
  this spec never defines a node or edge shape.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-collector-nongoals-1 | Generic Collector Deferred | Proposed | The reusable generic web collector is named as a future seam, not built in v0. | |

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`,
`Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`,
`Backlog`.
