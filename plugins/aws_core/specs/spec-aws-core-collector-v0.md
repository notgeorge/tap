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
| req-aws-collector-edges | [Declarative Edge Rules](#declarative-edge-rules) | Approved for Development | Recompute-uuid5 edge resolution; v0 make-it-work = mutually-available natural keys |
| req-aws-collector-edge-resolver | [Edge Identifier Resolution (Future Seam)](#edge-identifier-resolution-future-seam) | Backlog | The durable fix: pre-batch resolution pass; `key_kind`-driven; misses become observable warnings |
| req-aws-collector-reconcile | [Grid-State Reconciliation (Future Seam)](#v0-non-goals) | Backlog | Implied-absence/tombstone via the same grid-read primitive as the resolver; one generic reconcile vs Cartography per-type cleanup |
| req-aws-collector-hydrate | [Fan-Out Hydrate Seam](#fan-out-hydrate-seam) | Approved for Development | First named seam; per-op error-swallow; S3-style many-call |
| req-aws-collector-s3-bucket-size | [S3 Bucket Size Metrics](#s3-bucket-size-metrics) | Approved for Development | Aggregate size/count from CloudWatch storage metrics; `size_observed_at` data-currency disclosure |
| req-aws-collector-credentials | [Credential Resolution](#credential-resolution) | Approved for Development | `tap_cares` secret, `aws_static_access_key`, single account |
| req-aws-collector-runtime | [Collector Runtime Integration](#collector-runtime-integration) | Approved for Development | `CollectorBase` pipeline; mirrors the KSI reference collector |
| req-aws-collector-regions | [Region Iteration And Resilience](#region-iteration-and-resilience) | Approved for Development | Classify-and-skip; bounded throttle backoff |
| req-aws-collector-grift-batch | [GRIFT Batch Assembly](#grift-batch-assembly) | Approved for Development | One batch/run; provenance; no deletion semantics |
| req-aws-collector-audit-ledger | [Audit Verifiability](#audit-verifiability) | Approved for Development | Per-run AWS call ledger → `CollectionJob.results`; step one of the verifiability theme |
| req-aws-collector-tags | [Resource Tags](#resource-tags) | Approved for Development | Per-node `tags.source` (RGTA default / per-service side-quest); one canonical `{str:str}` field |
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
  (confirmed for S3, ACM full detail, Route 53 record sets, DynamoDB
  table-describe fan-out, IAM OIDC-provider detail fan-out). The callable
  signature is `fn(session, *, client_for) -> Iterator[dict]`: it receives
  the unbound boto3 session (for global resources or service-bound clients
  it constructs itself) AND a `client_for(service) -> Client` callable
  already bound to the current per-region iteration so regional custom_fns
  can build region-bound clients without inventing their own region
  resolution. Global custom_fns (Route 53, the S3 list-buckets head)
  accept-and-ignore the kwarg. The manifest names the callable; the engine
  looks it up in a plugin-local registry. Code is **never** loaded from
  manifest data (mirrors `req-tap-cares-collector-registry-6`).

`custom_fn` callables are expected to compose the [Fan-Out Hydrate
Seam](#fan-out-hydrate-seam) rather than hand-rolling pagination/error handling.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-source-1 | Uniform Item Contract | Approved for Development | `aws_op` and `custom_fn` both yield the same raw-item iterable; the engine does not branch on source kind downstream. | |
| req-aws-collector-source-2 | Generic Pagination | Approved for Development | `aws_op` uses the botocore paginator when the model defines one, else a single call; no per-resource pagination code. | |
| req-aws-collector-source-3 | Registered Callables Only | Approved for Development | `custom_fn` resolves through a plugin-local registry; manifest data never drives code import or path loading. | |
| req-aws-collector-source-4 | Quarantined Complexity | Approved for Development | Multi-call assembly exists only inside `custom_fn` callables, never in the engine. | |
| req-aws-collector-source-5 | Custom-Fn Signature | Approved for Development | `custom_fn` callables accept `(session, *, client_for)`. `client_for(service) → Client` is bound to the current per-region iteration so regional custom_fns can build region-bound clients without inventing their own region resolution; global custom_fns accept-and-ignore. | Discovered in autonomous pass 2026-05-20 when DynamoDB regional collection failed with "You must specify a region." |

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
  (the dominant case — Lambda, IAM role, ACM, EventBridge, CloudFront, S3);
  otherwise the stable AWS **resource id** (e.g. a hosted-zone id, a subnet id).
  **Documented v0 exception:** `aws_cloudwatch_log_group` is keyed by
  `logGroupName`, not its ARN — a deliberate make-it-work choice so the
  `WRITES_LOGS` edge resolves under the no-resolver v0 engine (see
  [v0 Make-It-Work: Mutually-Available Natural Keys](#v0-make-it-work-mutually-available-natural-keys)
  under `req-aws-collector-edges`). The name is unique per account+region,
  which holds under `req-aws-collector-scope`.
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
| req-aws-collector-identity-2 | ARN-Preferred Key | Approved for Development | Natural key is the ARN where available, else the stable resource id. **Documented exception:** `aws_cloudwatch_log_group` is keyed by `logGroupName` per `req-aws-collector-edges-7` (v0 make-it-work; unique per account+region under `req-aws-collector-scope`). | The lone deviation; recorded here so spec↔manifest cannot drift. |
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
| `key_kind` | `arn` \| `id` \| `name` — declares which identifier space the target's natural key lives in. **Inert in the v0 engine**: it neither transforms nor interprets the extracted value. It is declared intent, consumed only by the backlogged [Edge Identifier Resolution](#edge-identifier-resolution-future-seam) seam. In v0, correctness rests entirely on `value_path` (+ optional `transform`) emitting *exactly* the target's `natural_key` string. |
| `edge_type` | An edge type already declared by `aws_core` (`req-aws-core-edges`). |
| `direction` | `outbound` (this node → target) or `inbound` (target → this node). |

The engine forms the target `entity_id` by *recomputing* the same `uuid5`
scheme as [Deterministic Identity](#deterministic-identity) from the value the
source side extracted, and emits the edge. It does **not** verify the target
was collected, and it does **not** consult `key_kind`. The honest consequence:
an edge connects **iff both ends independently derive the byte-identical
`natural_key` string** — the source side's `value_path`(+`transform`) output
must equal the target entry's `natural_key`. When they match (ARN→ARN:
`ASSUMES_ROLE`, `RETRIEVES_CERT_FROM`; transform→ARN: `RETRIEVES_CONTENT_FROM`)
the edge resolves with no lookup or ordering dependency. When they *cannot*
match — the source carries only a name/domain and the target's ARN needs
account/region/suffix the source item lacks, or a cross-resource join — the
recompute silently produces a `uuid5` no node has: a dangling edge, not an
error. v0 closes this by the manifest discipline below; the durable fix is the
backlogged [Edge Identifier Resolution](#edge-identifier-resolution-future-seam)
seam.

#### v0 Make-It-Work: Mutually-Available Natural Keys

Because the engine is identity-coincidence (not identity-*resolution*) in v0,
every edge that must connect for the demo is made to satisfy the
"both-ends-derive-the-same-string" invariant **by manifest choice alone — no
engine change**: pick a `natural_key` for the target that the edge-emitting
source side already carries verbatim.

The one entry this forces off the ARN-preferred default
(`req-aws-collector-identity-2`): **`aws_cloudwatch_log_group` is keyed by
`logGroupName`, not its ARN.** Rationale — the Lambda's `WRITES_LOGS`
`value_path` (`LoggingConfig.LogGroup`) yields the log-group *name*, and a
CloudWatch Logs ARN (`arn:aws:logs:<region>:<acct>:log-group:<name>:*`) is not
derivable from the Lambda item (needs account/region/`:*`), so no pure
transform can bridge it. Keying the log group by `logGroupName` makes both ends
emit the identical string. The name is unique per account+region, which holds
under v0's single-account, region-scoped collection (`req-aws-collector-scope`);
it is **not** a general-purpose identity and does not generalize past v0 — that
is precisely what the resolver seam is for. Re-keying changes the
`aws_cloudwatch_log_group` `entity_id`; under v0's single-developer,
no-prod-data posture a re-collect simply lands the correctly-keyed nodes
(old ARN-keyed rows orphan harmlessly).

This is a deliberate, documented deviation, not drift: `key_kind` stays
truthful (it now reads `arn` on `RETRIEVES_CONTENT_FROM`, matching the
transform's `arn:aws:s3:::<bucket>` output), and `req-aws-collector-identity-2`
records the log-group exception inline so spec and manifest cannot diverge.

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
| req-aws-collector-edges-7 | Mutually-Available Natural Keys (v0 make-it-work) | Approved for Development | v0 has no edge resolver: an edge connects iff both ends derive the byte-identical `natural_key`. Every demo-required edge satisfies this by manifest choice alone. `aws_cloudwatch_log_group` is keyed by `logGroupName` (the documented deviation from `req-aws-collector-identity-2`), unique per account+region under `req-aws-collector-scope`, so `WRITES_LOGS` resolves with no engine change. `key_kind` stays truthful but inert. | Deliberate, documented; durable fix is the backlogged `req-aws-collector-edge-resolver` seam. |

### Edge Identifier Resolution (Future Seam)
----
RID: `req-aws-collector-edge-resolver`
Status: `Backlog`

The durable fix for the fragility `req-aws-collector-edges-7` papers over by
manifest discipline. v0 resolves edges by *coincidence* — recompute
`uuid5(target_type, value_from_source)` and hope the string equals what the
target derived. A source that can only name its target by name/domain while the
target is ARN-keyed produces a **silent dangling edge**, and `key_kind` — the
field that exists to express exactly this — is inert.

The future design is a pre-`assemble_batch` **resolution pass**, not a new
identity scheme. `uuid5` stays the *id allocator* (it is what makes re-runs
idempotent, and GRIFT edges are `entity_id`-keyed regardless — see
`req-aws-collector-grift-batch`); the resolver is the missing *lookup layer*
on top of it. Mechanically, with the run's nodes already in memory before batch
assembly:

1. Index the collected nodes by their standard identifiers (ARN, resource id,
   name) per `target_type`.
2. For each edge rule, resolve the target in that index using the identifier
   the source actually carries — **`key_kind` becomes the live input** that
   selects which identifier space to match in (`arn` \| `id` \| `name`).
3. Three outcomes:
   - **(a) resolved** — stamp the resolved node's `entity_id` (still its
     `uuid5` id; idempotency preserved). Verified-present, not assumed.
   - **(b) supported `target_type`, not found** — `warn` + drop. No fabricated
     dangling edge; the miss is observable (rate-limit / permission / scope
     gap is the operator's to read), replacing today's silent failure.
   - **(c) unsupported `target_type`** — already handled today (`warn` + drop,
     the v0 fence — `req-aws-collector-edges-6`); the resolver subsumes it.

Honest cost, and the reason `uuid5` stays *under* the resolver rather than
being replaced: an edge to a node collected in a *prior* run but not *this*
one would `warn`+drop instead of resolving. Acceptable under v0's
collect-everything-every-run scope; revisit if incremental/partial collection
ever lands. Converges conceptually with the grid **hotlink** identifier-
resolution model (a node findable by any of its identifiers); design that
alignment in-spec first if/when built. Demand-signal-gated, not built;
the loud-by-construction warnings are the payoff that justifies it over the
manifest workaround when the signal arrives.

**Grid as the resolution backstop (refinement).** The resolver's index need
not be limited to *this run's* in-memory node set. The grid is fully
functional and already holds every previously-collected node with its ARN and
associated identifiers as standard `BaseModel` fields; the collector is an
ordinary Python process that can read it. So the authoritative index is the
**grid itself**, consulted through a *service-layer read* (a gryphon query, or
a generated search/ORM-backed runner if gryphon lacks the shape — never ad hoc
per-model ORM iteration; that brute-force fallback is the thing the canonical
path exists to avoid, not the design). This is exactly the resolution one
would do anyway absent `uuid5`; `uuid5` is the optimistic accelerator (skip
the lookup when both ends provably coincide), the grid read is the
authoritative relief valve for every case where they might not. It
**dissolves the "honest cost" above**: an edge to a node collected in a prior
run but not this one now *resolves* against the grid instead of `warn`-
dropping. The conscious tradeoff to record (it ties to
[Audit Verifiability](#audit-verifiability)): a resolver that reads grid state
makes the batch no longer a pure function of the AWS responses + manifest
alone. Resolution stays a *lookup* (it does not alter what AWS reported, so
the batch remains a faithful projection); the grid-state dependence becomes
load-bearing only for **reconciliation/tombstone**, which is inherently a diff
and shares this same grid-read primitive — see
the grid-state reconciliation seam (`req-aws-collector-reconcile`) under
[v0 Non-Goals](#v0-non-goals).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-edge-resolver-1 | Seam Named, Not Built | Backlog | The pre-batch edge-resolution pass (collected-node index keyed by standard identifiers; `key_kind`-driven target lookup; resolve / warn-drop / unsupported-drop) is specified here as the durable replacement for `req-aws-collector-edges-7`'s manifest workaround. Not implemented in v0. | The three-case model. |
| req-aws-collector-edge-resolver-2 | uuid5 Retained As Allocator | Backlog | The resolver does not replace `uuid5` identity; it adds a lookup layer above it. `uuid5` stays the idempotent id allocator (`req-aws-collector-identity`); GRIFT edges remain `entity_id`-keyed. | Two jobs, decoupled. |
| req-aws-collector-edge-resolver-3 | Misses Are Observable | Backlog | A supported-type target not found in the run resolves to a recorded `warn` + dropped edge, never a silent dangling edge. | The correctness payoff. |
| req-aws-collector-edge-resolver-4 | Grid Is The Backstop | Backlog | The resolution index is the grid (via a service-layer read), not only this run's in-memory set; this dissolves the prior-run cost. Reads never use ad hoc per-model ORM iteration. Shares the grid-state-read primitive with `req-aws-collector-reconcile`. | uuid5 = accelerator; grid read = authoritative relief valve. |

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

### S3 Bucket Size Metrics
----
RID: `req-aws-collector-s3-bucket-size`
Status: `Approved for Development`

Every `aws_s3_bucket` node carries `size_bytes` and `object_count` so the
grid distinguishes a four-object bucket from a four-million-object one —
and, via `size_bytes / object_count`, a pile of tiny objects from a few
large ones. Both feed the viz: a bucket node can be weighted by its
actual footprint instead of rendering identically regardless of contents.

#### Source — CloudWatch daily storage metrics, not object listing

The values come from the `AWS/S3` CloudWatch namespace (`BucketSizeBytes`,
`NumberOfObjects`), which S3 publishes automatically and free once per day.
One `get_metric_data` call per bucket — batching `NumberOfObjects`
(`AllStorageTypes`) and `BucketSizeBytes` across every storage tier — gets
both. The rejected alternative is summing `list_objects_v2`: one call per
1000 objects, i.e. thousands of calls and (if objects were also nodes) a
grid-count explosion for a large bucket. CloudWatch is pre-aggregated; the
collector never enumerates objects.

`BucketSizeBytes` has no all-tiers rollup dimension — it is queried per
storage tier and the tiers that return data are summed, so a lifecycled
bucket (objects tiered to Glacier etc.) reports a complete total. The
CloudWatch call lives inside the `s3_buckets_hydrated` custom_fn, which
already resolves each bucket's region per-bucket; the CloudWatch client is
bound to that region.

#### Data currency — the shortcut is disclosed, machine-readably

CloudWatch storage metrics are daily, with up to ~24–48h publish lag, so
`size_bytes` / `object_count` are not real-time. Rather than estimate the
staleness, the collector surfaces the exact `Timestamp` of the CloudWatch
datapoint the values came from, as `size_observed_at` (ISO 8601). A
consumer computes `now − size_observed_at` and knows the currency
precisely. The **absolute timestamp is stored; the age is always derived
at read time, never stored** — a stored age is wrong one second later
(same discipline as the docs `last-edited` rule).

`size_observed_at` is **data currency** — what wall-clock moment the value
reflects — and is deliberately distinct from FLIP write provenance (which
collector / batch wrote the field). The collector ran today; the value
reflects yesterday's daily rollup. Conflating the two would be wrong.
This is the first instance of a currency-disclosure field. If a second
lagged-data consumer appears, generalizing the pattern — a standard
currency shape, or folding it into FLIP's adjacent axis — is the demand
signal; it is not pre-built here (future-seam discipline:
[[feedback-spec-before-mirroring-rules]]).

The per-field constants — "sourced from CloudWatch daily storage metrics,
granularity daily" — describe the *field*, not the *row*, and live in the
field schema (the registry-backed discovery surface), not duplicated on
every bucket row.

When CloudWatch has no datapoint for a bucket (new or just-emptied), all
three fields are empty/null and internally consistent: "unknown", never a
misleading "0 bytes".

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-s3-bucket-size-1 | Aggregate, Not Per-Object | Approved for Development | `size_bytes` + `object_count` come from CloudWatch `AWS/S3` storage metrics via one `get_metric_data` call per bucket; the collector never enumerates objects. | |
| req-aws-collector-s3-bucket-size-2 | All Storage Tiers Summed | Approved for Development | `BucketSizeBytes` is queried across every storage tier and the datapoints with data are summed; `NumberOfObjects` uses `AllStorageTypes`. | `BucketSizeBytes` has no all-tiers rollup dimension. |
| req-aws-collector-s3-bucket-size-3 | Currency Disclosed | Approved for Development | `size_observed_at` carries the CloudWatch datapoint's own timestamp; the consumer derives age, the collector never stores it. | Data currency — distinct from FLIP write provenance. |
| req-aws-collector-s3-bucket-size-4 | Unknown Is Not Zero | Approved for Development | A bucket with no CloudWatch datapoint reports empty/null fields, never a misleading 0. | |
| req-aws-collector-s3-bucket-size-5 | Non-Fatal | Approved for Development | A denied/failed CloudWatch call leaves the three fields empty/null; the bucket still collects. | Mirrors the hydrate-seam per-op resilience. |

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
  `session_token`, optional `region` (single), optional `regions_allowed`
  (list). The kind shape and its `aws_core`-owned schema are specified in
  `spec-aws-core-secrets.md` (`req-aws-core-secret-aws-static`).
- Region scope is operator-owned and carried on the secret: a non-empty
  `data.regions_allowed` scopes regional collection to exactly those regions; absent,
  the singular `data.region` is the sole swept region; with neither, the run
  fails visibly (one region is required to collect). Global-scope services are
  collected once regardless. A manifest/run-configuration region source is a
  deferred seam — not in the make-it-work path — and would override the secret
  default when introduced.
- A missing or malformed secret fails the run visibly with a structured,
  redacted error (`req-tap-cares-secrets-redaction-3`); it never logs secret
  material and never disables the collector capability.
- v0 is single-account static keys only. Assume-role and multi-account are
  deferred (`req-aws-core-secret-aws-static-3`, `req-aws-collector-nongoals`);
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

- The swept region set is resolved from the secret: `data.regions_allowed` if
  non-empty, else `[data.region]`, else the run fails visibly. Regional entries
  are collected once per resolved region; global entries once.
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
| req-aws-collector-regions-5 | Secret-Scoped Region Set | Approved for Development | The swept region set is `data.regions_allowed` if non-empty, else `[data.region]`, else the run fails visibly. | Operator-owned scope; `req-aws-core-secret-aws-static-4`. |
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

### Audit Verifiability
----
RID: `req-aws-collector-audit-ledger`
Status: `Approved for Development`

**Theme (future).** A later theme makes a collection run *verifiable* — able
to show evidence the grid reflects data actually gathered from AWS at a
knowable time, not merely asserted. The only non-deterministic datum AWS
returns that anchors this is the per-call **request id**
(`ResponseMetadata.RequestId`; S3 also `HostId` / `x-amz-id-2`) plus the
response `Date`. Correlating our recorded request ids and times to the
account's own CloudTrail (`requestID` ↔, `eventTime` ↔ response `Date`) is
contemporaneous proof a call occurred — *not* attestation of the response
body, but the evidentiary spine the verification theme will build on. The
verification machinery itself (matching, attestation, reporting) is out of
v0 scope and is named here only as the future seam this requirement feeds.

**Step one (this requirement).** The collector records a per-run AWS call
ledger as run provenance on the persisted, history-tracked `CollectionJob`
(its `results` log) — never on a resource node, never in the GRIFT batch.

#### Implementation

- Request ids are the canonical reason `ResponseMetadata` is stripped from
  every node / `configuration` / `_hydrate`
  (`req-aws-collector-field-projection-6`): per-call ids change every run
  and would poison node byte-identity. The ledger captures them on the run
  record instead, where per-run variance is expected and carries zero
  idempotent-upsert / History cost.
- Capture is at the boto3 boundary via botocore `after-call` /
  `after-call-error` session handlers (a run-scoped collaborator), so every
  enumerate call, paginator page, fan-out sub-call, and the STS identity
  probe is recorded with no per-resource code and no engine-signature
  change. The `after-call-error` path is the only place a `denied` /
  `throttled` call is observable.
- The ledger is drained once at end of `run()` as a single structured
  `record_info` entry (`message_code` `AWS_CALL_LEDGER`) whose
  `message_data` carries the call array: per call `{service, operation,
  request_id, host_id?, http_status, outcome, response_date}`. One run-log
  event, not one per call — the operator stream stays legible while the
  full machine ledger is captured.
- `outcome` ∈ `ok | absent | denied | throttled | error` — aligned with
  the hydrate classifier, **including `absent`**: AWS's expected "not
  configured" 404 (e.g. `NoSuchBucketPolicy`) is a first-class call
  outcome, never folded into `error`. (Live validation falsified the
  earlier "a call cannot be absent" framing — S3 fan-out is dominated by
  these expected 404s; conflating them into `error` is exactly the
  anti-pattern `req-aws-collector-hydrate-6` forbids.) The `absent`/
  `denied` code rule is shared with hydrate by convention (one dialect);
  factoring a single classifier is a named future cleanup, not v0.
- It lands in `CollectionJob.results` via the existing `record_*` →
  task-body persistence path; this needs **no** new schema — the
  `collection_job_results.schema.json` entry shape already defines
  `message_data` as free-form keyed by `message_code`.
- The ledger is the *complete* call record; `record_warn`
  (`ENTRY_SKIPPED` / `HYDRATE_GAP`) remains the operator-attention subset —
  complementary, never a second source of truth.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-audit-ledger-1 | Run-Record Placement | Approved for Development | The call ledger is on `CollectionJob.results`, never a resource node or the GRIFT batch. | Determinism — why `ResponseMetadata` is stripped elsewhere. |
| req-aws-collector-audit-ledger-2 | Boundary Capture | Approved for Development | Capture via botocore `after-call` / `after-call-error`; every call incl. paginator / fan-out / STS; no engine-signature change. | `after-call-error` is the only `denied` / `throttled` site. |
| req-aws-collector-audit-ledger-3 | Single Drained Entry | Approved for Development | Drained once per run as one `AWS_CALL_LEDGER` `record_info` entry; `message_data.calls` is the array. | Operator stream stays legible. |
| req-aws-collector-audit-ledger-4 | Outcome Vocabulary | Approved for Development | Per-call `outcome` ∈ `ok\|absent\|denied\|throttled\|error`, aligned with the hydrate classifier; AWS "not configured" 404s are `absent`, never `error`. | Live-validated; conflating absent into error is the `req-aws-collector-hydrate-6` anti-pattern. |
| req-aws-collector-audit-ledger-5 | No New Format | Approved for Development | Reuses `collection_job_results.schema.json` (`message_data` free-form by `message_code`); no new schema. | Verification machinery is a future theme, not v0. |

### Resource Tags
----
RID: `req-aws-collector-tags`
Status: `Approved for Development`

Every collected node carries a single canonical `tags` field — a flat
`{str: str}` map — regardless of the wildly varying ways AWS returns tags.
A broad botocore survey (42 services) found ~5 distinct wire shapes; AWS's
unified Resource Groups Tagging API (`resourcegroupstaggingapi:GetResources`,
"RGTA") returns one uniform shape for most resources in a single per-region
sweep.

The strategy is **RGTA-primary with per-service side-quests**, chosen
clean-room from prior-art analysis (Cartography/CloudQuery/Steampipe/Prowler/
ScoutSuite — patterns only, no code). Mature tools distrust RGTA *as a
discovery source* (it returns only ever-tagged resources). That failure mode
**does not bind this collector**: discovery is the per-service enumerate
path (`req-aws-collector-source`); RGTA only *decorates* already-discovered,
deterministically-identified nodes. An untagged resource simply gets
`tags: {}` — the correct answer, not a gap. And because nodes are keyed
`uuid5(type, natural_key)` where `natural_key` is the ARN for almost all
types, the RGTA `ResourceARN`→node join is identity-equal — it does *not*
reintroduce the `req-aws-collector-edges` ARN↔identity reconciliation
problem (the decisive reason mature ARN-short-id tools suffered it; we do
not).

#### Implementation

- A per-entry optional manifest `tags` block declares the source:
  - `{"source": "rgta"}` — the default. Tags come from the per-region RGTA
    sweep, joined by ARN.
  - `{"source": "service", "op": …, "params": {<param-name>: {…spec…}, …},
    "path": …, "shape": "list_kv"|"map"}` — a side-quest: a per-resource
    tag op resolved through the [Fan-Out Hydrate Seam](#fan-out-hydrate-seam)
    (no new mechanism). `params` is a dict mapping the boto3 keyword-arg
    name to a per-arg spec, where each spec is either `{"literal": "…"}`
    (a constant value) or `{"from": "<path>"}` (a path into the item).
    Most ops take a single identifier param (e.g. `ListRoleTags →
    {"RoleName": {"from": "RoleName"}}`); the multi-param form supports
    APIs that mix constants with per-item identifiers
    (e.g. `route53:ListTagsForResource → {"ResourceType": {"literal":
    "hostedzone"}, "ResourceId": {"from": "_zone_resource_id"}}`).
    Quarantined complexity, per `req-aws-collector-source-4`.
  - Absent `tags` block → the type carries no tags (declarative; never
    hidden code).
- **RGTA path.** One paginated `GetResources` per swept region, scoped by
  `ResourceTypeFilters`, building an `ResourceARN → [{Key,Value}]` map; each
  node's tags are `map.get(arn_for(node), {})` where `arn_for` is the node's
  `natural_key` directly, or a small declared ARN→key transform where they
  differ (CloudWatch log-group trailing `:*`; Route 53 hosted-zone
  `arn:aws:route53:::hostedzone/<id>` → bare id). Reuses the existing
  transform registry.
- **Side-quest path (v0).** `aws_iam_role` (RGTA *explicitly excludes* IAM
  roles) via `iam:ListRoleTags`; `aws_cloudfront_distribution` (CloudFront
  documents Tag Editor / Resource Groups as unsupported, contradicting the
  RGTA service list — do not trust RGTA) via
  `cloudfront:ListTagsForResource`; `aws_route53_zone` via
  `route53:ListTagsForResource` (RGTA excludes; multi-param call —
  `ResourceType="hostedzone"` literal + `ResourceId` from a bare-zone-id
  field the `custom_fn` adds to each item as `_zone_resource_id`);
  `aws_iam_oidc_provider` via `iam:ListOpenIDConnectProviderTags` (single
  ARN param). Other resource types follow the same shape as those need
  arises.
- **One canonical normalizer.** A single engine seam folds any declared
  shape (`list_kv` `[{Key,Value}]` → `{Key:Value}`; `map` → as-is) into the
  `{str: str}` field. Never a per-service loop — that is the drift-prone
  Steampipe-style boilerplate the prior-art analysis flagged; the
  CloudQuery single-helper pattern is the model. Raw-retention follows the
  `tags`/`tags_raw` discipline but is path-aware: the variable-shaped
  **side-quest** path retains the raw response losslessly via the
  `_hydrate` envelope (with the `ok|absent|denied|error` slot status);
  the **RGTA** path needs no separate raw store because RGTA's
  `list_kv`↔`map` is information-preserving (AWS tag keys are unique per
  resource, values are strings) — the canonical `{str:str}` map is itself
  the lossless form.
- **Per-model field, no spine.** `tags` is a `JSONField(default=dict)` on
  each `aws_core` model — same field name and canonical shape across the
  model family, so "everything `Owner=X` across `aws_*`" is a normal field
  query *by convention*. It is **not** an Entity-spine facet: `dimensions`
  is already the spine's key/value system, and AWS tags are mutable
  source-owned descriptive metadata that must never silently re-partition
  the grid (`req-grid-*` scoping is dimension-owned).
- **`us-east-1` invariant.** Global resources (IAM, CloudFront, Route 53)
  and CloudFront-bound ACM certificates appear in RGTA only in the
  `us-east-1` per-region results. The region scope **must** include
  `us-east-1` or those tags are silently missed; `self_test` warns when it
  is absent.
- **RGTA operational contract.** `PaginationToken` is valid ≤ 15 minutes
  (`PaginationTokenExpiredException` → restart the sweep, never resume
  mid-iteration); `ThrottledException` → bounded backoff; per-region,
  per-account; `ResourceTypeFilters` only (never `ResourceARNList`) for
  sweeps. RGTA is a tag-presence index, eventually consistent — the
  per-service enumerate remains authoritative for existence; RGTA only
  decorates.
- The v0 shape enum is fenced to `list_kv | map` (covers all of Sam's 8).
  The known outliers — ECS lowercase `key`/`value`, CloudTrail per-resource
  nesting, WAFv2 wrapped — are real but out of scope, named as a future
  enum extension, not built.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-collector-tags-1 | Declarative Source | Approved for Development | A manifest `tags.source` ∈ `rgta\|service` declares per-type tag retrieval; absent ⇒ no tags. No hidden per-service code. | |
| req-aws-collector-tags-2 | RGTA Default Path | Approved for Development | One paginated per-region `GetResources` sweep, `ResourceTypeFilters`-scoped, joined to nodes by ARN (`natural_key` or a declared transform). Untagged ⇒ `{}`, correct (discovery is independent). | RGTA never drives discovery. |
| req-aws-collector-tags-3 | Side-Quest Path | Approved for Development | `service` sources resolve via the hydrate seam with a `params` dict (each entry `{literal:…}` or `{from:<path>}`) so multi-param tag APIs are first-class; v0 = `aws_iam_role` (`ListRoleTags`), `aws_cloudfront_distribution` (`ListTagsForResource`), `aws_route53_zone` (`ListTagsForResource`, multi-param), `aws_iam_oidc_provider` (`ListOpenIDConnectProviderTags`). | RGTA excludes IAM roles, Route 53 zones, and IAM OIDC providers; CloudFront unsupported. |
| req-aws-collector-tags-4 | One Canonical Normalizer | Approved for Development | A single engine seam folds any declared shape → `{str:str}`; no per-service loops; raw retained losslessly. | CloudQuery pattern; not Steampipe boilerplate. |
| req-aws-collector-tags-5 | Per-Model Field, No Spine | Approved for Development | `tags` `JSONField` on each `aws_core` model, uniform name+shape; never an Entity-spine facet. | Cross-resource query by convention. |
| req-aws-collector-tags-6 | us-east-1 Invariant | Approved for Development | Region scope must include `us-east-1`; `self_test` warns if absent, or global / CloudFront-cert tags are silently missed. | |
| req-aws-collector-tags-7 | RGTA Op-Contract | Approved for Development | 15-min pagination-token TTL (restart, not resume), throttle backoff, `ResourceTypeFilters` only; RGTA decorates, never authoritative for existence. | Eventually consistent. |
| req-aws-collector-tags-8 | Shape Enum Fenced | Approved for Development | v0 `shape` ∈ `list_kv\|map` (all of Sam's 8); ECS / CloudTrail / WAFv2 outliers named as a future extension, not built. | |

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

- **Grid-state reconciliation — deletion / reaping / staleness sweep.**
  RID: `req-aws-collector-reconcile` (Backlog). No tombstones, no implied
  absence in v0. The named future seam: implied-absence is *the same
  primitive* as the edge resolver's grid-as-backstop
  (`req-aws-collector-edge-resolver-4`) — read the authoritative current grid
  shape through a service-layer read, diff this run's batch against the slice
  of the grid the run claims authority over, tombstone the difference. One
  capability serves both (resolve references; reap absences). The strategic
  bet (Cartography contrast): Cartography and peers carry per-node-type
  `lastupdated` timestamps + bespoke per-relationship cleanup jobs — fiddly,
  scattered, and the classic mass-false-delete footgun. TAP's uniform
  Entity/Edge spine + dimensions + per-run GRIFT batch provenance make a
  *single generic* reconcile (scope authority by source/dimensions, tombstone
  grid-minus-batch) plausibly far less code and more systematic — that is the
  reason to keep this seam, designed in-spec first when the signal arrives.
  Hard constraints, non-negotiable: it must route through GRIFT + the service
  layer (never a collector side channel); it must honor
  `req-aws-collector-regions-4` (an ambiguous/skipped read must never cause a
  false delete — the transient-vs-skippable hazard); and a **partial or
  failed run must never trigger a sweep** (authority is only as wide as what
  the run actually, completely covered — the single sharpest Cartography
  footgun). Demand-signal-gated; not built.
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
- **Per-object S3 introspection — its own targeted collector.** Listing a
  bucket's *contents* as individual `aws_s3_object` nodes (with a
  `STORES_OBJECT` edge from the bucket) is deferred to a dedicated
  collector — one pointed at a specific bucket deliberately, not part of the
  general manifest-driven account sweep. Object counts run to the millions
  (this account already has buckets at 1.7M and 2.1M objects); a blanket
  node-per-object pass over every bucket would explode the grid and the viz.
  The general sweep gets only the cheap CloudWatch *aggregate*
  (`req-aws-collector-s3-bucket-size` — `size_bytes` / `object_count`);
  deep per-object introspection is an opt-in "point it at one bucket and go
  to town" tool. The aggregate and the per-object collector compose — cheap
  universal stats now, targeted deep introspection when a specific bucket
  warrants it. Backlog.
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
- **Tag-derived dimensions** *(deferred, demand-driven)*. The collector
  already captures AWS resource tags into the per-model `tags` JSON column
  (via RGTA sweep + per-service side-quests). A natural extension is a
  configurable mapping from collected tags → entity `dimensions`
  (e.g. `tag.Project` → `dimension.tap.project`), stamped at collection
  time without a downstream hook. Held off in v0 because **dimensions are
  the security-boundary pillar** and arbitrary user-controlled tags must
  not silently become security boundaries. When the feature is built it
  needs: a per-collector or per-account allowlist of which tags may become
  dimensions; a denylist for reserved TAP dimension prefixes (`tap.*`,
  `aws.*`, etc.); collision/conflict handling when multiple sources map the
  same tag key; FLIP provenance recording which collector run wrote which
  dimension on which node; and an explicit policy for what happens when a
  previously-mapped tag value changes (re-stamp, history, or both). Demand
  signal that promotes this from Open to Proposed: >1 system collected
  into one account, or >1 customer collected at all. Until then samsite
  (the originating use case) uses tag-based ORM filters directly. Cross-ref:
  `plan/strat-sam-demo.md` "System-identification" decision (2026-05-20).
