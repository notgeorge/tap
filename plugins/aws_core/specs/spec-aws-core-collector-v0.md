# AWS Core Collector Specification (v0)

## Philosophy

The AWS Core collector populates the TAP grid from a running AWS account. It is the
first concrete consumer of the `aws_core` resource-type models, the `tap_cares`
collector runtime, and the `tap_cares` secrets subsystem.

The collector is **manifest-driven**. Instead of one hand-written fetch/transform
module per AWS resource type, a single generic engine is driven by a JSON resource
manifest. Each manifest entry declares: which service it covers, how to enumerate
its instances, which fields to surface as indexed model columns, and which
relationships to materialize as edges. The full AWS payload is always retained
verbatim in the node's `configuration` blob, so nothing collected is ever lost to
a too-narrow projection.

The design bet, validated by an offline extensibility probe before any code was
written (S3 / EC2 / IAM hard set): roughly **80% of resources and edges across the
AWS surface are declarable** as manifest data, and the non-declarable residue is
**concentrated, not scattered** — it collapses into two write-once engine seams
(a fan-out hydrate template and a policy-document edge resolver) rather than
sprawling into per-service code. This is what makes the pattern extensible and
keeps the future build-collector skill a *config generator*, not a code generator.

v0 is fenced hard to the `step-rampart-sam-demo` roadmap step: a single account,
the finite set of resource types in the reproduced samaydlette.com stack, no
deletion/reaping, no multi-account. The engine is specified generally (the
architectural bet is deliberate and the user is choosing this over a
Steampipe/Cartography-style per-service route), but the manifest *contents* and the
seams *built* in v0 are scoped to what the demo needs.

There is deliberately **no per-service class**. Per-service subclasses are the
Steampipe/Cartography/Magpie pattern this design rejects: the moment per-resource
knowledge lives in a class hierarchy instead of manifest data, the manifest is
decorative and the future build-collector skill reverts to a code generator. The
only base class is the framework's `CollectorBase`, with exactly one subclass for
all of AWS. Beneath it the engine composes a small fixed set of shared
collaborators — a credential/client factory, the fan-out hydrate helper, a
`custom_fn` protocol, a parsed `ResourceSpec` value object — composition over
inheritance, per the TAP guide. Reuse lives in those composed helpers, never an
inheritance tree; "no per-service class" is a load-bearing invariant, not a
style choice.

## Prior Art

Cartography (Lyft), ScoutSuite, Prowler, and CloudQuery were studied early for
shape: the fetch → pure-transform → load → cleanup decomposition, declarative
node/relationship schemas, per-region/per-account iteration, classify-and-skip
error handling, and the `update_tag` staleness sweep. The manifest-driven
*inversion* (declarative-first with code as the bounded exception, rather than
code-first with schema declarations) is TAP's own design.

No open-source code is incorporated. Per `AGENTS.md`, this is a licensing boundary,
not a style preference: ideas and shapes were extracted; implementations are
clean-room in TAP's own vocabulary against `CollectorBase` and GRIFT. AWS API
facts (which operation, which response field) are factual properties of the AWS
SDK that TAP depends on, not borrowed source.

## Roadmap Alignment

Governing step: `step-rampart-sam-demo` (Active, Timeline Target 2026-06-01).
This collector is named in that step's `Depends-on` as "the from-scratch boto3
`aws_core` collector — clean slate, Steampipe excised". It supersedes the parked
Steampipe collector design (`git tag park/steampipe-tooling`); the durable
credential/config/target *patterns* from the parked spec informed this design and
were re-expressed clean-room here. The step's Non-Goals (no live pull from Sam's
real account, no VPC/subnet topology, no config-vs-ops dimensions, no multi-user,
no encrypted secrets) are inherited as v0 fences.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Declarative   | A JSON manifest drives collection; adding a resource is a manifest entry, not a module |
| 2. | Lossless      | The full AWS payload is retained in `configuration`; projection never discards data |
| 3. | Connected     | Relationships are materialized as edges via declarative rules resolved by deterministic identity |
| 4. | Bounded       | The non-declarative residue is two write-once seams, not per-service code |
| 5. | Conventional  | The collector is an ordinary `CollectorBase` implementation; it invents no parallel runtime |
| 6. | Fenced        | v0 collects Sam's finite resource set, one account, no deletion semantics |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-aws-collector-scope | [Collector Scope](#collector-scope) | Approved for Development | One account, Sam's resource set, no deletes |
| req-aws-collector-manifest | [Resource Manifest](#resource-manifest) | Approved for Development | The JSON descriptor format — the architectural heart |
| req-aws-collector-source | [Source Primitive](#source-primitive) | Approved for Development | `source` ∈ {aws_op, custom_fn}, uniform "yields items" contract |
| req-aws-collector-field-projection | [Field Projection](#field-projection) | Approved for Development | jsonpath → typed fields + full payload → `configuration` |
| req-aws-collector-identity | [Deterministic Identity](#deterministic-identity) | Approved for Development | `uuid5(ns, "<type>:<natural_key>")`; re-runs upsert |
| req-aws-collector-edges | [Declarative Edge Rules](#declarative-edge-rules) | Approved for Development | jsonpath → target by key_kind; scalar/list fan-out |
| req-aws-collector-hydrate | [Fan-Out Hydrate Seam](#fan-out-hydrate-seam) | Approved for Development | First named seam; per-op error-swallow; S3-style many-call |
| req-aws-collector-credentials | [Credential Resolution](#credential-resolution) | Approved for Development | `tap_cares` secret, `aws_static_access_key`, single account |
| req-aws-collector-runtime | [Collector Runtime Integration](#collector-runtime-integration) | Approved for Development | `CollectorBase` pipeline; mirrors the KSI reference collector |
| req-aws-collector-regions | [Region Iteration And Resilience](#region-iteration-and-resilience) | Approved for Development | Classify-and-skip; bounded throttle backoff |
| req-aws-collector-grift-batch | [GRIFT Batch Assembly](#grift-batch-assembly) | Approved for Development | One batch/run; provenance; no deletion semantics |
| req-aws-collector-model-deps | [Model Dependencies](#model-dependencies) | Proposed | CloudFront / CloudWatch log group / EventBridge rule models must exist |
| req-aws-collector-sam-example | [Sam Worked Example](#sam-worked-example) | Proposed | Concrete manifest + edge set for the demo target |
| req-aws-collector-build-skill | [Build-Collector Skill Direction](#build-collector-skill-direction) | Proposed | Skill is a manifest generator; trust-tier axis |
| req-aws-collector-drift | [Shape-Drift Detection](#shape-drift-detection) | Proposed | botocore-pinned `service-2.json` diff via the catalog skill |
| req-aws-collector-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Deletes, multi-account, uniform-enum, policy resolver, deep IAM graph |

### Collector Scope
----
RID: `req-aws-collector-scope`
Status: `Approved for Development`

v0 collects a single AWS account into the grid, scoped to the resource types
present in the reproduced samaydlette.com stack.

#### Implementation

In scope for v0:

- one AWS account, resolved from one `tap_cares` secret
- the resource types: S3 bucket, CloudFront distribution, ACM certificate,
  Route 53 hosted zone, Lambda function, IAM role, CloudWatch log group,
  EventBridge rule
- one or more commercial regions, plus global services (S3, CloudFront,
  Route 53, IAM) collected once
- create/upsert of nodes and edges through GRIFT only

Explicitly out of scope for v0 (see [v0 Non-Goals](#v0-non-goals)): deletion /
reaping / implied-absence semantics, multi-account, uniform-enumeration APIs,
the policy-document edge resolver, the deep IAM/Org/SCP permission graph,
GovCloud/China partitions.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-scope-1 | Single Account | Approved for Development | v0 targets exactly one AWS account per collection run. | |
| req-aws-collector-scope-2 | Sam Resource Set | Approved for Development | The v0 manifest covers exactly the eight named resource types. | Driven by the demo, not by completeness. |
| req-aws-collector-scope-3 | No Deletion Semantics | Approved for Development | v0 only creates/upserts; absence from a run never deletes a node. | Reaping deferred (`req-aws-collector-nongoals`). |
| req-aws-collector-scope-4 | Commercial Only | Approved for Development | Only commercial AWS partitions are collected. | Mirrors `req-aws-core-scope-2`. |

### Resource Manifest
----
RID: `req-aws-collector-manifest`
Status: `Approved for Development`

A single JSON manifest, versioned and shipped in the plugin, declares every
resource type the collector knows how to gather. The generic engine carries no
per-resource knowledge.

#### Implementation

The manifest is an ordered list of resource entries. Each entry declares:

| Key | Meaning |
| --- | --- |
| `entity_type` | The `aws_core` model entity type the entry populates (e.g. `aws_lambda`). |
| `service` | The boto3 service name (e.g. `lambda`, `s3`). |
| `scope` | `regional` or `global`. Global services are collected once, not per region. |
| `source` | The enumeration source (see [Source Primitive](#source-primitive)). |
| `why` | Human one-line reason this resource/enumerate call is collected; materialized into the node's `_source` (see [Field Projection](#field-projection)). |
| `items_path` | jsonpath to the list of resource items within the source result, supporting nested-array flatten (e.g. `Reservations[].Instances[]`). |
| `natural_key` | jsonpath to the value used for deterministic identity (see [Deterministic Identity](#deterministic-identity)). |
| `fields` | Map of model field name → jsonpath into the item (see [Field Projection](#field-projection)). |
| `hydrate` | Optional list of per-item hydrate ops, each `{key, op, why}` (see [Fan-Out Hydrate Seam](#fan-out-hydrate-seam)). |
| `edges` | List of declarative edge rules (see [Declarative Edge Rules](#declarative-edge-rules)). |

The manifest is pure data. The engine validates the manifest against a JSON
Schema shipped alongside it at load time; a malformed manifest fails the run
visibly (it is operator/author error, not a runtime condition).

Manifest entry order is advisory only — because edges resolve by deterministic
identity (not by matching an already-loaded node), the engine does not depend on
collection order. This is a deliberate divergence from the prior-art convention
where sync order encodes the dependency graph.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-manifest-1 | Data-Only Manifest | Approved for Development | The engine contains no per-resource-type branching; all per-type knowledge lives in the manifest. | The escape hatch is `custom_fn`, itself named in the manifest. |
| req-aws-collector-manifest-2 | Schema Validated | Approved for Development | The manifest validates against a shipped JSON Schema at load; invalid manifest fails the run visibly. | |
| req-aws-collector-manifest-3 | Order Independent | Approved for Development | Collection results are identical regardless of manifest entry order. | Enabled by deterministic identity. |
| req-aws-collector-manifest-4 | Versioned | Approved for Development | The manifest carries a version recorded in the GRIFT batch provenance. | Supports drift tracking. |
| req-aws-collector-manifest-5 | Self-Describing Entries | Approved for Development | Each entry carries a `why`, and each `hydrate` element a `{key, op, why}`; the schema requires `why` so every collected call's rationale is authorable and visible in the manifest. | Materialized per-node so a grid object is legible without the manifest. |

### Source Primitive
----
RID: `req-aws-collector-source`
Status: `Approved for Development`

A manifest entry's `source` is a single primitive with two implementations. Both
return the same thing — an iterable of raw resource items — so the engine never
branches on which was used.

#### Implementation

`source` is one of:

- **`aws_op`** — a declared boto3 operation. The entry names the operation (e.g.
  `ListFunctions`) and the engine drives it generically: it resolves the client
  for `service`, uses the operation's paginator when one exists in the botocore
  model, otherwise calls it once, and yields items via `items_path`. This is the
  common case ("one describe call per service" — confirmed single-call for
  Lambda, IAM roles, EventBridge rules, CloudWatch log groups, and CloudFront).
- **`custom_fn`** — a named, registered Python callable shipped in the plugin,
  used only where AWS requires multiple calls to assemble one logical resource
  (confirmed for S3, ACM full detail, Route 53 record sets). The callable
  receives a bound boto3 session/region context and yields items in the same
  shape an `aws_op` would. The manifest names the callable; the engine looks it
  up in a plugin-local registry. Code is **never** loaded from manifest data
  (mirrors `req-tap-cares-collector-registry-6`).

`custom_fn` callables are expected to compose the [Fan-Out Hydrate
Seam](#fan-out-hydrate-seam) rather than hand-rolling pagination/error handling.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-source-1 | Uniform Item Contract | Approved for Development | `aws_op` and `custom_fn` both yield the same raw-item iterable; the engine does not branch on source kind downstream. | |
| req-aws-collector-source-2 | Generic Pagination | Approved for Development | `aws_op` uses the botocore paginator when the model defines one, else a single call; no per-resource pagination code. | |
| req-aws-collector-source-3 | Registered Callables Only | Approved for Development | `custom_fn` resolves through a plugin-local registry; manifest data never drives code import or path loading. | |
| req-aws-collector-source-4 | Quarantined Complexity | Approved for Development | Multi-call assembly exists only inside `custom_fn` callables, never in the engine. | |

### Field Projection
----
RID: `req-aws-collector-field-projection`
Status: `Approved for Development`

Each raw item is projected into a typed `aws_core` node plus a full
`configuration` payload.

#### Implementation

For each item:

- the manifest `fields` map assigns each declared model field a jsonpath into
  the item; the engine extracts each, applying graceful-missing semantics — a
  path that does not resolve yields `null`, never an error. (AWS response shapes
  are stable across SDK versions; the real variability is conditional/optional
  fields absent on a given instance, which this handles by design — it mirrors
  the existing `aws_core` hybrid nullable-field pattern, `req-aws-core-fields-3`.)
- the **entire raw item** is stored verbatim in the node's `configuration`
  JSONField (`req-aws-core-fields-1`), so no AWS attribute is ever lost even if
  it is not surfaced as a typed field.
- the node's `name` is taken from the manifest-declared name field or the
  natural key.

Field projection performs no type coercion beyond what the model's
`FIELD_CRUD_SCHEMA` requires; values are passed as received and the existing
service-layer validation applies.

**Temporal fields.** Dates are the one normalization the collector performs, and
it is engine-level, not a manifest transform:

- boto3 already parses every AWS field the botocore model types as `timestamp`
  into a `datetime` (uniform regardless of wire format). The engine serializes
  every `datetime` to ISO 8601 UTC (`…Z`) when writing the `configuration` blob
  and GRIFT — a single mandatory rule (a `datetime` is not JSON-serializable),
  not a per-field transform.
- The raw `configuration` blob otherwise keeps AWS's value verbatim, including
  the two known non-`timestamp` date shapes (epoch-millis `long` — CloudWatch
  Logs `creationTime`; offset-string — Lambda `LastModified`). The blob is for
  inspection and is never canonicalized (consistent with No Silent Coercion).
- The manifest may map one source field to the entity envelope's `created_at`
  and one to `updated_at`. This is the **only** place a date is canonicalized
  for query. That mapping carries a 3-value format hint
  (`timestamp` | `epoch_ms` | `iso8601_offset`) covering exactly the two
  non-`timestamp` warts; the engine normalizes all three into one ISO 8601 UTC
  envelope field at collection time. The hint is an input-parsing enum on ~1
  field per resource, not a transform language, and it never leaks to the query
  side: "entities created/updated after X" is a single query against one
  canonical envelope field — never three queries or per-resource field
  spelunking.

Two temporal concepts are kept distinct and must not be conflated: the
**grid-native** first-seen/updated time (TAP-owned, always present, uniform —
the reliable spine for "what did this run collect/change" and the History/FLIP
audit-evidence surface) and the **AWS-source** creation/modification time
(mapped into the envelope where AWS exposes it). The probe showed several
enumerate calls — CloudFront `ListDistributions`, Route 53 `ListHostedZones`,
EventBridge `ListRules` — return *no* creation timestamp; for those the
AWS-source envelope `created_at` is legitimately null and the grid-native time
is the answer. Single-field / single-query holds for both; completeness of the
AWS-source field is bounded by what AWS returns, by design.

**Reserved envelope keys and stable serialization.** The node `configuration`
is the enumerate item at its root plus engine-reserved keys: `_source`
(`{op, why}` — the enumerate call and its manifest rationale, present on
**every** node, single-call and fan-out, so even a single-call object is
self-describing), and on fan-out resources `_hydrate` and `_hydrate_mapping`
(see [Fan-Out Hydrate Seam](#fan-out-hydrate-seam)). Reserved keys are
engine-managed and are **not** valid `fields`/`edges` jsonpath targets for
authored mappings — they are engine output, not AWS payload. Node identity
derives only from the root enumerate item, never a reserved key.

Two engine rules keep the blob stable across runs:

- `ResponseMetadata` is stripped from every boto3 response before it becomes the
  item, `_hydrate[*].data`, or `configuration`. It carries request ids, retry
  counts, and timestamped headers; retaining it would change `configuration`
  every run on an unchanged resource, churning idempotent upsert and polluting
  History/FLIP.
- The engine serializes deterministically (manifest/sorted key order plus the
  ISO 8601 datetime rule above). Combined with `ResponseMetadata` stripping, an
  unchanged resource yields byte-identical `configuration` — clean re-runs, no
  false History entries, protecting the "re-run live in the demo" and
  audit-evidence properties.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-field-projection-1 | Declared Field Mapping | Approved for Development | Typed fields are populated from manifest jsonpaths. | |
| req-aws-collector-field-projection-2 | Graceful Missing | Approved for Development | An unresolved jsonpath yields `null`, never a run failure. | |
| req-aws-collector-field-projection-3 | Lossless Payload | Approved for Development | The full raw item is stored in `configuration`. | |
| req-aws-collector-field-projection-4 | No Silent Coercion | Approved for Development | Values are passed through; model/service-layer validation is the sole gate. | |
| req-aws-collector-field-projection-5 | One Canonical Timestamp | Approved for Development | All date input shapes normalize at collection into one ISO 8601 UTC envelope field; "created/updated after X" is one query, never per-resource spelunking. | Grid-native time is the always-present spine; AWS-source time is null where AWS omits it. |
| req-aws-collector-field-projection-6 | Reserved Keys & Stable Blob | Approved for Development | `_source`/`_hydrate`/`_hydrate_mapping` are engine-reserved (not authored jsonpath targets); `ResponseMetadata` stripped; deterministic serialization ⇒ unchanged resource = byte-identical `configuration`. | Protects idempotent upsert + History/FLIP. |

### Deterministic Identity
----
RID: `req-aws-collector-identity`
Status: `Approved for Development`

Every collected node and edge has a deterministic `entity_id` so that repeated
collection runs upsert in place rather than duplicating — the property that makes
"re-run the collector live in the demo" safe.

#### Implementation

- Node identity is `uuid5(NAMESPACE_AWS_COLLECTOR, f"{entity_type}:{natural_key}")`.
- The natural key is the value at the manifest's `natural_key` jsonpath.
  Preference order, declared per entry: the resource **ARN** where one exists
  (the dominant case — Lambda, IAM role, ACM, EventBridge, CloudWatch log group,
  CloudFront, S3); otherwise the stable AWS **resource id** (e.g. a hosted-zone
  id, a subnet id).
- Edge identity is `uuid5(NAMESPACE_AWS_COLLECTOR, f"edge:{edge_type}:{from_key}->{to_key}")`.
- `NAMESPACE_AWS_COLLECTOR` is a frozen module-level UUID constant in the plugin;
  changing it would re-identify every collected node and is not permitted.

Because edge endpoints are computed from the same `uuid5` of the target's
natural key, an edge can be emitted before — or without ever — the target node
being collected in the same run; it resolves by identity, not by load order.
GRIFT's dangling-edge handling governs the not-yet-present case.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-identity-1 | Deterministic Nodes | Approved for Development | The same AWS resource always yields the same `entity_id` across runs and grids. | |
| req-aws-collector-identity-2 | ARN-Preferred Key | Approved for Development | Natural key is the ARN where available, else the stable resource id. | |
| req-aws-collector-identity-3 | Deterministic Edges | Approved for Development | Edge identity derives from edge type plus endpoint natural keys. | |
| req-aws-collector-identity-4 | Idempotent Re-Run | Approved for Development | Re-running collection upserts; it never duplicates nodes or edges. | |

### Declarative Edge Rules
----
RID: `req-aws-collector-edges`
Status: `Approved for Development`

Relationships are materialized from declarative edge rules in the manifest entry,
resolved by deterministic identity. The probe established ~80% of valuable edges
are expressible this way.

#### Implementation

An edge rule declares:

| Key | Meaning |
| --- | --- |
| `value_path` | jsonpath into the item yielding the target's natural key — a scalar **or** a list. A list produces fan-out (one edge per element); this covers the common many-target case (e.g. an instance's network interfaces). |
| `target_type` | The target `aws_core` entity type. |
| `key_kind` | `arn` \| `id` \| `name` — how to interpret the extracted value when forming the target's `uuid5`. |
| `edge_type` | An edge type already declared by `aws_core` (`req-aws-core-edges`). |
| `direction` | `outbound` (this node → target) or `inbound` (target → this node). |

The engine forms the target `entity_id` via the same `uuid5` scheme as
[Deterministic Identity](#deterministic-identity) and emits the edge. It does
**not** verify the target exists in this run (deterministic identity makes that
unnecessary; GRIFT governs dangling edges).

This spec defines the edge *mechanism* only. It introduces no new edge *types*;
edge-type and target-model selection for specific relationships is `aws_core`
model/edge work governed by `spec-aws-core-v0` (`req-aws-core-edges`). Edges
whose target key is not directly present in the item (derived keys — e.g.
matching a Route 53 alias to a CloudFront distribution by domain rather than
ARN) are supported via a small declared transform on `value_path`; edges that
require parsing an embedded IAM/resource policy document are **out of v0 scope**
and routed to the deferred policy-document resolver (`req-aws-collector-nongoals`).

**Two-phase application.** All nodes are emitted first, then edges in a separate
pass — nodes, then edges. Because endpoints resolve by deterministic identity,
the edge pass needs no per-target lookup. An edge whose `target_type` is not a
resource type this collector models/collects (an expected condition under the v0
fence — e.g. a reference to a not-yet-modeled service) is **dropped with a
recorded `warn`, never a run failure**; the edge pass is the single chokepoint
for that check rather than scattering it. An edge to a modeled type whose
specific instance was not collected this run is a dangling edge governed by
GRIFT's `dangling_edge_mode`; the AWS collector uses the mode that retains/skips
rather than fails, so a later run that collects the target resolves it by
identity.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-edges-1 | Declarative Rules | Approved for Development | Edges are emitted from manifest rules; the engine has no per-relationship code. | |
| req-aws-collector-edges-2 | Scalar And Fan-Out | Approved for Development | `value_path` supports scalar and list extraction; a list yields one edge per element. | |
| req-aws-collector-edges-3 | Identity-Resolved | Approved for Development | Edge endpoints resolve by deterministic `uuid5`, independent of collection order or target presence. | |
| req-aws-collector-edges-4 | Existing Edge Types Only | Approved for Development | Edge rules reference edge types already declared by `aws_core`; no new edge types are defined here. | |
| req-aws-collector-edges-5 | Policy Edges Excluded | Approved for Development | Edges requiring policy-document parsing are not emitted in v0. | Deferred resolver, named seam. |
| req-aws-collector-edges-6 | Two-Phase, Unmodeled-Safe | Approved for Development | Nodes are emitted before edges; an edge to an unmodeled `target_type` is dropped with a `warn`, never a failure; uncollected modeled targets follow GRIFT dangling-edge mode. | Single chokepoint for the v0-fence gap. |

### Fan-Out Hydrate Seam
----
RID: `req-aws-collector-hydrate`
Status: `Approved for Development`

The first of the two named seams. A reusable, manifest-parameterised template
for the AWS resources that have no single rich describe call and instead require
a per-item fan-out of secondary calls (confirmed worst case: S3, where
`ListBuckets` returns four fields and ~9 independent `GetBucket*` calls supply
everything else).

#### Implementation

The hydrate template is a single engine helper a `custom_fn` composes. Given an
enumerate operation and the manifest's declared `hydrate` list, for each
enumerated item it calls each hydrate op with the item's identifier and assembles
one **self-describing configuration envelope** on the node. The enumerate item is
the envelope root; hydrate output and its explanation are two reserved siblings:

- `_hydrate` — the **event record**. Per declared slot key:
  `{ "status": <ok|absent|denied|error>, "op": <aws op>, "data": <verbatim
  response> }` on success, or `{ "status": …, "op": …, "error_code": <aws code> }`
  when the call returned no data. `data` is the full response verbatim
  (losslessly, per slot) with `ResponseMetadata` stripped (see [Field
  Projection](#field-projection)).
- `_hydrate_mapping` — the **intent**. Per slot key:
  `{ "op": <aws op>, "why": <manifest rationale> }`, materialized from the
  manifest at collection time, embedded per-node (deterministic, tiny next to
  `data`) so a grid object is legible **without** the manifest. The batch
  independently records manifest version / account / regions; the per-node
  mapping is what makes a single object self-explanatory.

Slot `status` is the load-bearing distinction:

- `ok` — call succeeded; `data` present.
- `absent` — AWS's "not configured" signal (`NoSuchBucketPolicy`,
  `NoSuchWebsiteConfiguration`, `…NotFoundError`). A real, queryable fact: the
  resource genuinely has no such configuration.
- `denied` — `AccessDenied` / authorization failure. Value unknown — recorded as
  a structured `warn`. **Never conflated with `absent`**: "no policy" and "could
  not read the policy" are opposite compliance conclusions, and the KSI
  scoreboard depends on telling them apart.
- `error` — unexpected / throttle-exhausted. Swallowed → `warn`; the node is
  still collected, partially hydrated.

`absent`/`denied`/`error` are swallowed independently per op, so one missing
sub-config never fails the resource. Node identity is always taken from the root
enumerate item (`req-aws-collector-identity`), never a hydrate slot — a fully
denied hydration still yields a stable, correctly-identified node.

The template is written once. Adding an S3-like resource is a manifest `hydrate`
list, not new Python. This is the mechanism by which even the worst-case
collection class stays declarative.

v0 builds the template and exercises it for S3, with S3's hydrate list fenced to
the minimum the demo needs (existence + region + the small set of
compliance-relevant sub-configs the KSI scoreboard reads). Broad S3
sub-configuration is deferred.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-hydrate-1 | Single Template | Approved for Development | One reusable hydrate helper exists; per-item multi-call code is not duplicated per resource. | |
| req-aws-collector-hydrate-2 | Independent Sub-Call Resilience | Approved for Development | Each hydrate sub-call's `NoSuch*`/`AccessDenied`/absent result is swallowed independently and recorded as `warn`. | |
| req-aws-collector-hydrate-3 | Manifest-Driven Op List | Approved for Development | Adding a hydrated resource is a declared op-name list, not new engine code. | |
| req-aws-collector-hydrate-4 | S3 Fenced | Approved for Development | v0 exercises the template for S3 with a minimal hydrate op list. | Broad S3 sub-config deferred. |
| req-aws-collector-hydrate-5 | Hydrate Envelope | Approved for Development | Fan-out output is the `_hydrate` event-record map (per slot: `status`, `op`, verbatim `data` or `error_code`) on the enumerate-item root. | |
| req-aws-collector-hydrate-6 | Absent vs Denied Distinct | Approved for Development | `absent` (not configured) and `denied` (no permission) are distinct first-class statuses, never merged; the KSI reading depends on it. | |
| req-aws-collector-hydrate-7 | Self-Describing, No Manifest Needed | Approved for Development | `_hydrate_mapping` (slot → `{op, why}`, materialized from the manifest, embedded per-node, deterministic) makes a grid object legible without the manifest. | |

### Credential Resolution
----
RID: `req-aws-collector-credentials`
Status: `Approved for Development`

AWS credentials are resolved through the `tap_cares` secrets subsystem. The
collector never reads credential files directly.

#### Implementation

- The collector resolves a secret via `resolve_secret(SecretRef(scope="aws",
  key=<configured>))` and validates it is `kind: aws_static_access_key` with the
  required `data` fields, using `require_secret_kind(...)` with an `aws_core`-owned
  JSON Schema (consumer-side validation, `req-tap-cares-secrets-validation-2`).
- Accepted `data`: `access_key_id`, `secret_access_key`, optional
  `session_token`, optional `region` (`req-tap-cares-secrets-aws-static`).
- Regions to sweep come from the manifest/run configuration; the secret's
  `region` is the default/fallback. Global-scope services are collected once.
- A missing or malformed secret fails the run visibly with a structured,
  redacted error (`req-tap-cares-secrets-redaction-3`); it never logs secret
  material and never disables the collector capability.
- v0 is single-account static keys only. Assume-role and multi-account are
  deferred (`req-tap-cares-secrets-aws-static-3`, `req-aws-collector-nongoals`);
  the secret model already anticipates multi-account as "more secret files".

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-credentials-1 | Secrets Subsystem Only | Approved for Development | Credentials resolve via `resolve_secret`; no direct file reads. | |
| req-aws-collector-credentials-2 | Consumer-Side Validation | Approved for Development | The collector validates `kind` and required `data` against an `aws_core`-owned schema before use. | |
| req-aws-collector-credentials-3 | Visible Redacted Failure | Approved for Development | Missing/malformed secret fails the run with a structured redacted error; no secret material is logged. | |
| req-aws-collector-credentials-4 | Static Keys v0 | Approved for Development | v0 supports static access keys for one account only. | Assume-role/multi-account deferred. |

### Collector Runtime Integration
----
RID: `req-aws-collector-runtime`
Status: `Approved for Development`

The collector is an ordinary `CollectorBase` implementation registered with
`tap_cares`. It invents no parallel runtime; it mirrors the established
`fedramp_20x_ksi` KSI collector reference shape.

#### Implementation

- A `CollectorBase` subclass implementing `run()` and `self_test()`.
- `run()` pipeline: resolve credentials → load+validate manifest → for each
  manifest entry, drive `source` → project fields → emit nodes → emit edges →
  assemble one GRIFT batch → `self.submit_grift(document)` → set `self.summary`
  to a one-line human result.
- `self_test()`: validate the secret resolves and is the right kind, and probe
  read-only reachability via STS `GetCallerIdentity` (cheap, no resource
  permissions required), within the bounded self-test latency budget
  (`req-tap-cares-collector-self-test-12`).
- Structured events via `record_info` / `record_warn` / `record_error` with
  4-hex site tokens minted by `scripts/log-site-id` and held unique per the
  repo-wide site-uniqueness test.
- Failure protocol: an unrecoverable condition records a structured error and
  raises (an `_abort`-style helper), letting the `run_collector` task body write
  the FAILED terminal patch — exactly the framework convention
  (`req-tap-cares-collector-failure-mode`). The collector never writes
  `CollectionJob`.
- Registration in the plugin `apps.py` `ready()` via `register_collector(key=…,
  cls=…, name=…, description=…)` — the dual-existence call that both registers
  the runner and upserts the on-grid `Collector` node.
- The collector reads AWS (external) and the grid only through approved
  surfaces; its sole grid-mutation path is `self.submit_grift`
  (`req-tap-cares-collector-read-boundary`, `-grift-import`).

Trust posture: unlike the KSI collector (which ingests untrusted upstream JSON
and carries a paranoid denylist/structural-cap/mass-deletion layer), this
collector reads our own account with our own read-only credentials. That input
is **trusted**; the KSI-style paranoid safety layer is deliberately **not**
replicated. This trust-tier distinction is carried forward as a build-skill axis
(`req-aws-collector-build-skill`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-runtime-1 | CollectorBase Subclass | Approved for Development | The collector subclasses `CollectorBase`, implements `run()` and `self_test()`. | |
| req-aws-collector-runtime-2 | Sole Mutation Path | Approved for Development | The only grid write is `self.submit_grift`; the collector never writes `CollectionJob` or the ORM. | |
| req-aws-collector-runtime-3 | Framework Failure Protocol | Approved for Development | Unrecoverable conditions record a structured error and raise; the task body owns the terminal patch. | |
| req-aws-collector-runtime-4 | Dual-Existence Registration | Approved for Development | Registered in `apps.py` via `register_collector(...)`. | |
| req-aws-collector-runtime-5 | Self-Test Reachability | Approved for Development | `self_test()` validates the secret and probes STS `GetCallerIdentity` within budget. | |
| req-aws-collector-runtime-6 | No Paranoid Layer | Approved for Development | The trusted-input posture is documented; the KSI paranoid safety layer is intentionally not replicated. | |
| req-aws-collector-runtime-7 | No Per-Service Class | Approved for Development | Exactly one `CollectorBase` subclass for all of AWS; no per-service subclasses; reuse via composed collaborators. | The invariant that keeps the build-skill a config generator. |

### Region Iteration And Resilience
----
RID: `req-aws-collector-regions`
Status: `Approved for Development`

The engine iterates regions for regional services and degrades gracefully on the
expected partial-failure conditions, without ever corrupting collected data.

#### Implementation

- Regional entries are collected per configured region; global entries once.
- A permission/region condition — `AccessDenied`, `UnauthorizedOperation`,
  authorization failures, "not supported in this region" — is recorded as a
  structured `warn` and that (region, resource) is skipped; the run continues.
- Throttling is retried with bounded exponential backoff; an unbounded or
  unbroken throttle ultimately records an `error` and the run fails per the
  framework protocol.
- A skipped region/resource never removes or alters previously collected data.
  Because v0 has no deletion semantics, the Cartography-style
  transient-vs-skippable hazard (an ambiguous read causing a false delete) does
  not arise in v0; it is noted as a constraint to honor if/when reaping is
  introduced.

The classify-and-skip behavior is a clean-room re-expression of a widely-used
resilience shape, implemented as TAP code against `record_warn`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-regions-1 | Per-Region / Global Split | Approved for Development | Regional entries sweep configured regions; global entries collect once. | |
| req-aws-collector-regions-2 | Classify-And-Skip | Approved for Development | Expected permission/region errors record a `warn` and skip; the run continues. | |
| req-aws-collector-regions-3 | Bounded Throttle Backoff | Approved for Development | Throttling retries with bounded backoff; unbroken throttle fails per protocol. | |
| req-aws-collector-regions-4 | No Data Corruption On Skip | Approved for Development | A skipped region/resource never alters previously collected data. | v0 has no deletes; reaping must honor this. |

### GRIFT Batch Assembly
----
RID: `req-aws-collector-grift-batch`
Status: `Approved for Development`

One collection run assembles one GRIFT batch carrying all collected nodes and
edges, submitted through the approved import surface.

#### Implementation

- One batch per run. The `batch_node` records provenance: collector source
  identity, AWS account id, regions swept, manifest version, and per-type
  counts, in a structured `description_json` (mirroring the KSI collector's
  provenance shape, in `aws_core`'s own format).
- Nodes and edges use the deterministic identities from
  [Deterministic Identity](#deterministic-identity).
- The document is submitted via `self.submit_grift(...)`; the returned result's
  imported/skipped batch ids and counts inform `self.summary`.
- No deletion, tombstone, or implied-absence content appears in the batch
  (`req-aws-collector-scope-3`).
- Dangling-edge handling uses GRIFT's standard mode; the deterministic-identity
  design means most cross-resource edges resolve even when emitted before their
  target.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-grift-batch-1 | One Batch Per Run | Approved for Development | A run produces a single GRIFT batch. | |
| req-aws-collector-grift-batch-2 | Provenance Recorded | Approved for Development | The batch records account, regions, manifest version, and counts. | |
| req-aws-collector-grift-batch-3 | Approved Surface Only | Approved for Development | Submission is via `self.submit_grift`. | |
| req-aws-collector-grift-batch-4 | No Deletion Content | Approved for Development | The batch contains no deletion/tombstone semantics. | |

### Model Dependencies
----
RID: `req-aws-collector-model-deps`
Status: `Proposed`

The collector can only populate models that exist. Three of Sam's eight resource
types are not yet modeled in `aws_core`.

#### Implementation

Already modeled (usable now): S3 bucket, ACM certificate, Route 53 hosted zone,
Lambda function, IAM role.

Must be added via the `add-model` skill before their manifest entries can
collect, governed by `spec-aws-core-v0` (`req-aws-core-models`):

- CloudFront distribution
- CloudWatch log group
- EventBridge rule

Edge types required by the Sam worked example must already be declared by
`aws_core` (`req-aws-core-edges`); any not present are added through that spec's
edge process, not invented here.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-model-deps-1 | Missing Models Identified | Proposed | CloudFront, CloudWatch log group, and EventBridge rule are named as prerequisites. | |
| req-aws-collector-model-deps-2 | Added Via Skill | Proposed | The three models are added via `add-model` under `spec-aws-core-v0`, not ad hoc. | |
| req-aws-collector-model-deps-3 | Edge Types Pre-Declared | Proposed | Worked-example edges use `aws_core`-declared edge types; new types go through the edge process. | |

### Sam Worked Example
----
RID: `req-aws-collector-sam-example`
Status: `Proposed`

A concrete v0 manifest and edge set for the reproduced samaydlette.com stack, so
the demo target is explicit rather than implied.

#### Implementation

Resource entries (eight): S3 bucket, CloudFront distribution, ACM certificate,
Route 53 hosted zone, Lambda function, IAM role, CloudWatch log group,
EventBridge rule.

Collection class per entry (from the offline probe):

- single-call `aws_op`: Lambda, IAM role, EventBridge rule, CloudWatch log
  group, CloudFront
- `custom_fn` + hydrate: S3 (minimal hydrate list), ACM (summary list is
  sufficient for the demo; full-detail hydrate optional), Route 53 (zones via
  `aws_op`; record sets via `custom_fn` for the alias edge)

The demo-legible edges, all declarable (no policy resolver needed — none of
Sam's edges require policy-document parsing):

- CloudFront → S3 (origin domain → bucket; derived-key transform on the origin
  domain)
- CloudFront → ACM (viewer certificate ARN)
- Route 53 → CloudFront (alias target → distribution by domain; the matcher the
  prior art does not ship — TAP-authored)
- Lambda → IAM role (`Role` ARN)
- EventBridge rule → IAM role (`RoleArn`)
- Lambda → CloudWatch log group (logging configuration / convention)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-sam-example-1 | Eight Entries Named | Proposed | The manifest's v0 entries are exactly Sam's eight resource types. | |
| req-aws-collector-sam-example-2 | Collection Class Stated | Proposed | Each entry's source class (single-call vs custom_fn+hydrate) is explicit. | From the probe. |
| req-aws-collector-sam-example-3 | Demo Edges Declarable | Proposed | The six demo edges are expressible as declarative rules; no policy resolver is required for the demo. | |

### Build-Collector Skill Direction
----
RID: `req-aws-collector-build-skill`
Status: `Proposed`

The manifest-driven design is the foundation of a future build-collector skill.
This requirement records what the skill should be so the design stays aligned
with it (it is not built in v0).

#### Implementation

The skill should:

- generate manifest entries (entity_type, service, source, items_path,
  natural_key, field map, edge rules) by introspecting the botocore service
  model — the ~80% declarative majority
- compose, not generate, the fixed seam library — the [fan-out hydrate
  template](#fan-out-hydrate-seam) and the deferred policy-document resolver —
  for the bounded residue
- gate which guards apply on a **trust-tier axis**: a trusted own-account boto3
  source omits the KSI-style paranoid input layer; an untrusted source (a future
  external/customer feed) would re-enable it. Trust tier is an explicit skill
  input, not an implicit default
- stay a **config generator**, never a code generator, even at depth

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-build-skill-1 | Manifest Generator | Proposed | The skill generates manifest entries from botocore introspection. | |
| req-aws-collector-build-skill-2 | Seam Library Composed | Proposed | The skill composes the fixed seam library; it does not generate per-resource fetch/edge code. | |
| req-aws-collector-build-skill-3 | Trust-Tier Axis | Proposed | Which safety guards apply is an explicit trust-tier input. | |

#### Future

The skill graduates from Proposed once the v0 collector is proven against the
Sam target and the manifest format has stabilized through real use.

### Shape-Drift Detection
----
RID: `req-aws-collector-drift`
Status: `Proposed`

AWS API shape changes are detected deterministically by diffing the pinned
botocore service models, folded into the existing catalog-refresh skill rather
than as new infrastructure.

#### Implementation

- `botocore` is pinned in the lockfile; its bundled, versioned `service-2.json`
  models are the canonical machine-readable AWS API surface (offline, no
  external tracker).
- On a botocore bump, the relevant operation output shapes for manifested
  services are diffed; added/removed/changed members are surfaced as proposed
  manifest/field updates.
- This extends `spec-aws-core-catalog`'s refresh skill (already "detects changes
  and proposes additions") to cover collector manifest drift; it is not a
  separate pipeline.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-drift-1 | botocore Pinned | Proposed | botocore is version-pinned; its service models are the drift baseline. | |
| req-aws-collector-drift-2 | Model Diff | Proposed | Botocore bumps trigger an output-shape diff for manifested services. | |
| req-aws-collector-drift-3 | Folded Into Catalog Skill | Proposed | Drift detection extends the existing catalog-refresh skill, not new infra. | |

### v0 Non-Goals
----
RID: `req-aws-collector-nongoals`
Status: `Proposed`

Explicitly deferred. Each is a bounded future seam, not an abandoned idea — named
so later readers do not mistake the omission for an oversight (`feedback:
future-seam discipline`).

#### Implementation

Deferred from v0:

- **Deletion / reaping / staleness sweep.** No tombstones, no implied absence.
  When introduced it must route through GRIFT and the service layer (not a
  collector side channel) and must honor `req-aws-collector-regions-4` (an
  ambiguous read must never cause a false delete — the transient-vs-skippable
  hazard).
- **Multi-account.** v0 is one account. The secrets model already frames
  multi-account as "more secret files"; orchestration across accounts is later.
- **Uniform-enumeration APIs** (Resource Groups Tagging API, Cloud Control API,
  AWS Config). Evaluated and rejected for v0: Tagging API returns spine only,
  Cloud Control is CFN-shaped with uneven coverage and strips edge-bearing
  fields, Config requires an in-account recorder. Per-service declared ops are
  the v0 basis.
- **Policy-document edge resolver** — the second named seam. The ~20%
  non-declarable edges concentrate almost entirely into IAM/resource policy
  document parsing. None of Sam's demo edges need it, so it is specified as a
  seam (one write-once resolver, built — when built — as a post-ingestion pass
  over the already-collected graph, the shape every mature prior-art project
  converged on independently: Cartography analysis jobs, Fix `connect_in_graph`;
  not an ever-richer inline manifest DSL) but not built in v0. Its existence is
  what proves the pattern extensible without per-service sprawl.
- **Deep IAM / Organizations / SCP permission graph.** The known weak spot
  (~60% declarable); the same weak spot prior-art tools have and solve with a
  dedicated pass. Deferred with the policy resolver.
- **General jsonpath edge-DSL** beyond the declared rule shape (scalar/list +
  small derived-key transform). Richer expression waits for a demand signal.
- **GovCloud / China partitions.**

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-nongoals-1 | Deferrals Named | Proposed | Each deferral is explicitly named as a bounded future seam. | |
| req-aws-collector-nongoals-2 | Reaping Constraint Recorded | Proposed | Future reaping must route through GRIFT and never false-delete on an ambiguous read. | |
| req-aws-collector-nongoals-3 | Uniform-Enum Rejection Justified | Proposed | The rejection of Tagging/Cloud Control/Config for v0 is recorded with rationale. | |
| req-aws-collector-nongoals-4 | Policy Resolver Is A Seam | Proposed | The policy-document resolver is specified as a write-once seam, deferred, not abandoned. | |

## Open Questions

- **Derived-key edge transforms.** The Route 53-alias → CloudFront-by-domain
  edge needs a small transform on `value_path` (domain normalization), not a raw
  jsonpath. v0 supports a minimal declared transform; how expressive that
  becomes before it turns into a DSL is a demand-driven decision, not settled
  here.
- **S3 hydrate op list for the KSI scoreboard.** The exact minimal set of
  `GetBucket*` operations v0 hydrates depends on which compliance signals the
  KSI scoreboard reads from Sam's catalog; pinned when that surface is built.
- **Edge-type assignment.** Which already-declared `aws_core` edge type each
  demo relationship uses (and whether CloudFront/CloudWatch/EventBridge model
  additions require any new edge types) is resolved in the `add-model` work
  under `spec-aws-core-v0`, not here.
