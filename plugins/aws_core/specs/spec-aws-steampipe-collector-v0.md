# AWS Steampipe Collector Specification

## Philosophy

The AWS Steampipe collector is the first live AWS inventory path for `aws_core`.
It uses Steampipe as an extraction engine and TAP as the semantic system of
record. Steampipe answers provider questions through SQL-shaped tables; TAP
normalizes selected rows into AWS Core models, relationships, dimensions,
provenance, and GRIFT batches.

The collector belongs in `aws_core` because AWS-specific collection needs to
know the plugin's model surface, edge vocabulary, field promotion choices, and
cloud-provider quirks. `tap_cares` remains the runtime plumbing: collector
registration, execution, secrets, run records, and GRIFT import boundaries.

This specification intentionally starts with a small, inspectable slice:
inventory VPCs and subnets from a demo AWS account through Steampipe and place
them on the grid. Broader AWS coverage should advance by updating the Steampipe
coverage inventory, adding model/edge specs where needed, and then extending
collection profiles.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Inventory Map | Maintain an explicit Steampipe-to-TAP table coverage inventory |
| 2. | Runtime Safe  | Resolve AWS credentials through `tap_cares` secrets without storing secret values on the grid |
| 3. | Configurable  | Define how a collector run knows account, region, secret ref, and collection profile |
| 4. | Semantic      | Normalize Steampipe rows into AWS Core models and edges rather than generic raw blobs |
| 5. | GRIFT Native  | Submit all grid mutations through inspectable GRIFT batches and the standard import path |
| 6. | Incremental   | Start with VPC and subnet collection and defer deletes/reaping |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-aws-steampipe-scope | [Collector Scope](#collector-scope) | In Development | AWS plugin owns Steampipe-backed inventory collection |
| req-aws-steampipe-inventory | [Steampipe Coverage Inventory](#steampipe-coverage-inventory) | Implemented | `docs/steampipe-aws-table-inventory.yaml` is the planning map |
| req-aws-steampipe-model-expansion | [Model Expansion Heuristic](#model-expansion-heuristic) | Proposed | ARN-bearing durable resources are model candidates, not automatic models |
| req-aws-steampipe-secrets | [AWS Credential Resolution](#aws-credential-resolution) | Implemented | v0 uses the `tap_cares.secrets` backend with AWS static credentials |
| req-aws-steampipe-config | [Collector Configuration](#collector-configuration) | Implemented | v0 defines a simple config shape for secret, account, regions, and profile |
| req-aws-steampipe-runner | [Steampipe Execution](#steampipe-execution) | In Development | Steampipe is invoked as the extraction backend |
| req-aws-steampipe-identity | [Provider Identity Resolution](#provider-identity-resolution) | Proposed | Stable AWS source identity resolves to existing TAP entity IDs before minting new UUIDv7s |
| req-aws-steampipe-vpc-subnet | [First Collector Slice: VPC And Subnet](#first-collector-slice-vpc-and-subnet) | In Development | Initial collector imports `aws_vpc` and `aws_vpc_subnet` |
| req-aws-steampipe-grift | [GRIFT Batch Contract](#grift-batch-contract) | Proposed | Collector output mutates grid only through GRIFT import |
| req-aws-steampipe-observability | [Run Observability](#run-observability) | In Development | CollectionJob receives redacted summaries, counts, warnings, and batch refs |
| req-aws-steampipe-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Deletes/reaping, assume-role, and broad AWS coverage are deferred |

## Collector Scope
----
RID: `req-aws-steampipe-scope`
Status: `In Development`

`aws_core` owns AWS-specific collector implementations that populate AWS Core
models from AWS account state. The first implementation uses Steampipe, but the
plugin's contract is not "dump Steampipe into TAP." The contract is: query a
known AWS source, normalize selected resources into TAP's AWS vocabulary, and
submit graph changes through GRIFT.

The collector must register through `tap_cares.registry.register_collector(...)`
from `plugins/aws_core/apps.py` or an equivalent plugin startup path. The
registered collector is a trusted Python class; the grid stores only the
collector registry key on the `Collector` capability node per the tap-cares
collector spec.

The collector must not introduce dynamic code loading, arbitrary SQL from grid
state, direct ORM writes for AWS resource nodes, or any TAP-managed mutation
outside the service-layer GRIFT import path.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-scope-1 | Plugin Ownership | Implemented | AWS-specific Steampipe collection code lives in `aws_core`, not in `tap_cares`. | `plugins/aws_core/collectors/`. |
| req-aws-steampipe-scope-2 | Registered Collector | Implemented | The collector is registered through `tap_cares.registry.register_collector(...)` with human-readable name and description. | `AwsCoreConfig.ready()`. |
| req-aws-steampipe-scope-3 | No Dynamic Code Loading | Proposed | Collector execution never imports code, reads executable paths, or evaluates behavior from grid data. | Mirrors tap-cares collector boundary. |
| req-aws-steampipe-scope-4 | No Generic Dump | Proposed | Steampipe table availability does not automatically create TAP models or raw resource nodes. | |

## Steampipe Coverage Inventory
----
RID: `req-aws-steampipe-inventory`
Status: `Implemented`

The AWS plugin maintains a machine-readable coverage inventory at:

```text
plugins/aws_core/docs/steampipe-aws-table-inventory.yaml
```

The inventory compares upstream Steampipe AWS tables to the current AWS Core
model surface. It is a planning artifact used to classify tables before they are
collected. The inventory should be updated when Steampipe adds tables, when
`aws_core` adds models or edges, or when collection decisions change.

Inventory classifications:

- `implemented_model`: a Steampipe table maps to an existing `aws_core` model.
- `model_gap_candidate`: likely durable AWS resource that may deserve a model.
- `edge_or_attribute_candidate`: relationship, attachment, association, rule, or
  detailed config table likely used for edges or node enrichment.
- `evidence_candidate`: finding, compliance result, health event, analyzer
  output, recommendation, or other observation.
- `metric_candidate`: metric/time-series table that needs a separate metrics
  design before grid modeling.
- `attribute_or_observation_candidate`: detail, history, version, snapshot,
  report, scan, or log-like table that needs more judgment.

The inventory may include source version metadata, status counts, collection
tiers, source documentation links, notes, and first-pass collector flags.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-inventory-1 | Inventory File | Implemented | `docs/steampipe-aws-table-inventory.yaml` exists and is parseable YAML. | |
| req-aws-steampipe-inventory-2 | Current Model Comparison | Implemented | The inventory records current `aws_core` model mappings for implemented Steampipe tables. | |
| req-aws-steampipe-inventory-3 | Decision Buckets | Implemented | Every table has a classification bucket rather than being silently ignored. | |
| req-aws-steampipe-inventory-4 | VPC Targets Flagged | Implemented | `aws_vpc` and `aws_vpc_subnet` are flagged as first-pass collector targets. | |
| req-aws-steampipe-inventory-5 | Update Trigger | Proposed | Model, edge, or Steampipe table changes update the inventory alongside implementation. | |

## Model Expansion Heuristic
----
RID: `req-aws-steampipe-model-expansion`
Status: `Proposed`

AWS Core model growth should be intentional and spec-backed. Steampipe exposes
many AWS tables; TAP should not mirror them mechanically.

The default model expansion heuristic is:

> Anything with a stable ARN is a candidate TAP node unless it is clearly only
> an embedded configuration detail, transient execution artifact, metric sample,
> or policy statement fragment.

This is a heuristic, not a law. A table with no ARN can still become a model
when it is structurally important, edge-worthy, or compliance-relevant. A table
with an ARN can still remain an attribute, observation, or deferred item when it
is too high-churn, too granular, or not useful as a graph object.

New model families should generally be added with corresponding edge semantics
and field-promotion rules. A new node without relationships or queryable fields
is a sign the table may belong in `configuration`, evidence, or a later phase.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-model-expansion-1 | ARN Heuristic | Proposed | Stable ARN-bearing resources are treated as model candidates. | |
| req-aws-steampipe-model-expansion-2 | No Automatic Promotion | Proposed | ARN-bearing tables are not automatically promoted to models without a spec/model update. | |
| req-aws-steampipe-model-expansion-3 | Non-ARN Exception | Proposed | Structurally important non-ARN resources may still be first-class models. | VPC, subnet, route table, and security group are examples. |
| req-aws-steampipe-model-expansion-4 | Edge-Aware Growth | Proposed | New resource model families define likely edge relationships alongside the model decision. | |

## AWS Credential Resolution
----
RID: `req-aws-steampipe-secrets`
Status: `Implemented`

The v0 AWS collector resolves credentials through the `tap_cares.secrets`
backend. Secret values are off-grid runtime material loaded from mounted
`*.secret.json` files into the tap-cares runtime registry. Collector nodes,
configuration records, GRIFT batches, and run records may reference a non-secret
`tap_cares.secrets.SecretRef`, but they must never store access keys, session
tokens, or other credential values.

The collector's runtime flow is:

1. Parse collector configuration into an `AwsSteampipeCollectorConfig`
   containing only a `SecretRef`.
2. Resolve the secret with `tap_cares.secrets.resolve_secret(...)`.
3. Validate `kind` and `data` with `tap_cares.secrets.require_secret_kind(...)`
   and an AWS-plugin-owned JSON Schema.
4. Build a transient Steampipe subprocess environment containing AWS credential
   variables.
5. Run trusted profile queries.
6. Drop credential material after the subprocess boundary. Only redacted
   diagnostics and non-secret `SecretRef` identity may reach run records or
   logs.

v0 supports the `tap_cares` AWS static credential shape:

- `kind`: `aws_static_access_key`
- `data.access_key_id`
- `data.secret_access_key`
- optional `data.session_token`
- optional `data.region`

The AWS collector validates this consumer-specific shape after resolving the
secret. Missing, malformed, or kind-mismatched secrets fail the run visibly with
redacted structured errors. `SecretRef` identity is safe to record; any
structured diagnostic context that may contain secret-shaped fields must be
redacted with `tap_cares.secrets.redact(...)` before it reaches run records or
logs. Secret material must not appear in subprocess arguments, logs,
`CollectionJob.results`, GRIFT payloads, or rendered UI.

Steampipe credential configuration should be created in a transient runtime
location for the duration of the run, using environment variables or temporary
configuration files as needed. Any temporary file containing secret material must
be scoped to the run, excluded from source control, and removed or isolated so it
cannot be mistaken for plugin state.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-secrets-1 | tap-cares Resolver | Implemented | The collector resolves AWS credentials through `tap_cares.secrets.resolve_secret(...)`. | `resolve_aws_static_credentials(...)`. |
| req-aws-steampipe-secrets-2 | Static Credentials v0 | Implemented | v0 supports `aws_static_access_key` with optional session token and region. | Schema and env mapping implemented in `credentials.py`. |
| req-aws-steampipe-secrets-3 | Consumer Validation | Implemented | The AWS collector validates kind and required data fields before invoking Steampipe. | Uses `require_secret_kind(...)` with AWS-owned schema. |
| req-aws-steampipe-secrets-4 | Redacted Failure | Implemented | Missing or invalid secrets fail the run with redacted structured diagnostics. | Missing secrets record `SECRET_INVALID`; Steampipe diagnostics scrub secret values. |
| req-aws-steampipe-secrets-5 | No Secret Persistence | Implemented | Secret values are not written to grid nodes, edges, GRIFT batches, run records, logs, or source-controlled files. | Tests cover env construction, secret repr, and diagnostic redaction. |

## Collector Configuration
----
RID: `req-aws-steampipe-config`
Status: `Implemented`

The AWS collector needs runtime configuration beyond the capability-level
`Collector` node: account target, secret reference, regions, and collection
profile. The tap-cares v0 `Collector` model does not yet support per-instance
configuration, so this spec defines a v0 plugin-owned configuration shape while
leaving the durable on-grid configuration model as future work.

The v0 configuration shape is JSON-safe:

```json
{
  "target_key": "demo",
  "account_id": "123456789012",
  "partition": "aws",
  "secret_ref": {"scope": "aws", "key": "demo-readonly"},
  "regions": ["us-east-1"],
  "profile": "vpc-subnet-v0"
}
```

Configuration values may come from plugin settings, a local non-secret config
file, or an explicit test fixture. The configuration source must not contain
secret values. The collector validates the shape before resolving secrets or
running Steampipe.

`profile` selects a trusted collection profile implemented by AWS plugin code.
It is not arbitrary SQL. The v0 profile is `vpc-subnet-v0`.

Future work should introduce on-grid collector instances or target nodes that
reference `SecretRef`s and collection profiles without storing secret values.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-config-1 | JSON-Safe Shape | Implemented | v0 collector configuration is a JSON-safe object containing target, account, partition, secret ref, regions, and profile. | `AwsSteampipeCollectorConfig`. |
| req-aws-steampipe-config-2 | Secret Reference Only | Implemented | Configuration stores only shared `tap_cares.secrets.SecretRef` identity, never secret material. | |
| req-aws-steampipe-config-3 | Explicit Regions | Implemented | v0 requires an explicit region list for collection. | |
| req-aws-steampipe-config-4 | Trusted Profile | Implemented | `profile` selects a plugin-authored collection profile and does not accept arbitrary SQL. | `vpc-subnet-v0`. |
| req-aws-steampipe-config-5 | Future On-Grid Config | Backlog | Durable on-grid collector target/instance configuration is deferred. | |

## Steampipe Execution
----
RID: `req-aws-steampipe-runner`
Status: `In Development`

The v0 collector invokes Steampipe as an extraction backend from trusted AWS
plugin code. The exact integration may use the Steampipe CLI, Export CLI, or a
small wrapper around either. The first implementation should prefer the simplest
subprocess boundary that returns structured JSON and does not require TAP's
Postgres database to host Steampipe foreign tables.

The runner must:

- verify the Steampipe executable or configured command is available
- use a controlled query set for the selected profile
- request JSON output
- apply explicit account and region scoping
- capture structured stdout/stderr, exit status, row counts, and warnings
- redact credentials and credential-shaped values from diagnostics
- fail visibly when Steampipe is unavailable, exits non-zero, or returns invalid
  JSON

The v0 profile query set is limited to:

```sql
select * from aws_vpc;
select * from aws_vpc_subnet;
```

Implementation may narrow selected columns once the normalizers are finalized.
The collector should keep the complete source row that it actually receives in
the target node's `configuration`.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-runner-1 | Structured JSON | Implemented | Steampipe execution returns parseable structured JSON rows to the collector. | Runner supports array and `{"rows": [...]}` output. |
| req-aws-steampipe-runner-2 | Trusted Queries | Implemented | Queries are owned by plugin code and selected by profile, not supplied by grid data. | |
| req-aws-steampipe-runner-3 | Availability Failure | Implemented | Missing Steampipe binary/configuration fails the run visibly. | |
| req-aws-steampipe-runner-4 | Scoped Regions | In Development | The runner applies the configured region list rather than silently scanning every region. | Current shell sets primary region env; Steampipe multi-region config still pending. |
| req-aws-steampipe-runner-5 | Redacted Diagnostics | Implemented | Command diagnostics are captured without leaking credential material. | Marker and secret-value redaction implemented. |

## Provider Identity Resolution
----
RID: `req-aws-steampipe-identity`
Status: `Proposed`

AWS source identity must be stable across collection runs, while TAP `Entity`
IDs remain UUIDv7. The collector must therefore resolve provider identity before
authoring GRIFT.

For each collected AWS resource, the collector derives a provider identity key:

```text
aws:<partition>:<account_id>:<region-or-global>:<entity_type>:<provider-id-or-arn>
```

Examples:

```text
aws:aws:123456789012:us-east-1:aws_vpc:vpc-0abc123
aws:aws:123456789012:us-east-1:aws_subnet:subnet-0def456
```

Before minting a new GRIFT entity ID, the collector checks whether an existing
TAP node already has the same provider identity. The exact lookup surface is a
first implementation detail because `aws_core` does not yet have a dedicated
external identity model. The collector may initially use current model fields
plus dimensions (`account_id`, region, resource ID) and should converge on a
shared provider-identity helper once that pattern appears in more collectors.

If an existing node is found, the GRIFT object reuses that `entity_id`. If no
node is found, the collector mints a fresh UUIDv7. The collector must not use
UUID5 or hand-shaped deterministic UUIDs for AWS resource entities unless the
grid identity rules are explicitly changed by spec.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-identity-1 | Provider Key | Proposed | The collector derives a stable AWS provider identity key for every collected resource. | |
| req-aws-steampipe-identity-2 | Existing Reuse | Proposed | Existing TAP entity IDs are reused when the provider identity already exists on-grid. | |
| req-aws-steampipe-identity-3 | UUIDv7 New IDs | Proposed | New AWS resource entities receive fresh UUIDv7 IDs. | |
| req-aws-steampipe-identity-4 | No UUID5 Resources | Proposed | The collector does not create deterministic UUID5 entity IDs for AWS resources. | Collector capability nodes remain governed by tap-cares registry identity. |
| req-aws-steampipe-identity-5 | Future Helper | Backlog | A shared provider identity model/helper should replace ad hoc lookup once the need is proven. | |

## First Collector Slice: VPC And Subnet
----
RID: `req-aws-steampipe-vpc-subnet`
Status: `In Development`

The first AWS Steampipe collector profile is `vpc-subnet-v0`. It collects VPCs
and subnets from one configured demo account and explicit region list.

### Steampipe Tables

| Table | TAP Model | Notes |
| --- | --- | --- |
| `aws_vpc` | `aws_vpc` | Existing `Vpc` model |
| `aws_vpc_subnet` | `aws_subnet` | Existing `Subnet` model |

### VPC Normalization

Each `aws_vpc` row becomes or updates one `Vpc` node:

| Vpc Field | Source |
| --- | --- |
| `name` | Name tag when present, otherwise VPC ID |
| `vpc_id` | Steampipe VPC ID |
| `cidr_block` | Primary CIDR block from the row |
| `state` | VPC state |
| `is_default` | Default VPC flag |
| `configuration` | Full received Steampipe row plus collector metadata needed for provenance and debugging |

### Subnet Normalization

Each `aws_vpc_subnet` row becomes or updates one `Subnet` node:

| Subnet Field | Source |
| --- | --- |
| `name` | Name tag when present, otherwise subnet ID |
| `subnet_id` | Steampipe subnet ID |
| `cidr_block` | Subnet CIDR block |
| `availability_zone` | Availability zone name |
| `public` | Derived from Steampipe subnet/public-route information when available, otherwise `false` with a warning or explicit uncertainty marker |
| `configuration` | Full received Steampipe row plus collector metadata needed for provenance and debugging |

### Dimensions

Collected VPC and subnet entities should include the model default
`{"tap.cloud": "aws"}` plus AWS collection dimensions where supported by the
service layer and GRIFT importer:

- `aws.account_id`
- `aws.partition`
- `aws.region`
- `aws.collection_target`

If dynamic dimensions expose importer or model limitations, the collector should
record the limitation in the run summary and continue with the static model
default rather than bypassing the service layer.

### Edges

The first profile should create these relationships when both endpoints are
known:

| Edge | From | To | Notes |
| --- | --- | --- | --- |
| `CONTAINS` | `aws_region` | `aws_vpc` | Region reference nodes already ship in AWS Core GRIFT seed data |
| `CONTAINS` | `aws_vpc` | `aws_subnet` | VPC contains subnet |
| `RESIDES_IN` | `aws_subnet` | `aws_region` | Subnet lives in region |
| `RESIDES_IN` | `aws_subnet` | `aws_vpc` | Subnet lives in VPC |
| `RESIDES_IN` | `aws_subnet` | `aws_az` | Created when the AZ reference node can be resolved |
| `BELONGS_TO_ACCOUNT` | `aws_vpc` | `aws_account` | Created when the account node exists or is collected in the same batch |
| `BELONGS_TO_ACCOUNT` | `aws_subnet` | `aws_account` | Created when the account node exists or is collected in the same batch |

The first implementation may create a minimal `AwsAccount` node for the
configured account if one does not already exist, but it should not collect broad
account metadata beyond what the v0 profile needs for relationship anchoring.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-vpc-subnet-1 | Profile Exists | Implemented | The trusted profile `vpc-subnet-v0` exists in AWS plugin code. | |
| req-aws-steampipe-vpc-subnet-2 | VPC Query | In Development | The profile collects rows from `aws_vpc`. | Query shell exists; live Steampipe execution not yet verified. |
| req-aws-steampipe-vpc-subnet-3 | Subnet Query | In Development | The profile collects rows from `aws_vpc_subnet`. | Query shell exists; live Steampipe execution not yet verified. |
| req-aws-steampipe-vpc-subnet-4 | Node Normalization | Proposed | VPC and subnet rows normalize into existing `Vpc` and `Subnet` models. | |
| req-aws-steampipe-vpc-subnet-5 | Raw Row Preserved | Proposed | The received Steampipe row is stored in each node's `configuration`. | |
| req-aws-steampipe-vpc-subnet-6 | Relationship Edges | Proposed | The collector creates supported account, region, VPC, subnet, and AZ edges when endpoints can be resolved. | |
| req-aws-steampipe-vpc-subnet-7 | Demo Account Scope | Proposed | v0 targets one configured demo account and explicit regions. | |

## GRIFT Batch Contract
----
RID: `req-aws-steampipe-grift`
Status: `Proposed`

The collector must produce an inspectable GRIFT document before mutating the
grid. GRIFT batches are the only mutation shape for collected AWS resource
nodes and edges.

The collector should create one logical GRIFT batch per collector run/profile
execution. The batch metadata should identify:

- collector registry key
- collection profile
- target key
- account ID
- partition
- region list
- Steampipe plugin/source version when available
- collection start and finish timestamps

Batch nodes and edges must use canonical AWS Core entity types and edge types.
The collector may use `CollectorBase.submit_grift(...)` or the current
tap-cares-approved helper so the task body can accumulate imported/skipped batch
IDs on `CollectionJob.grift_batches`.

No collector code may directly create, patch, replace, or delete AWS resource
nodes or graph edges through the ORM.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-grift-1 | Draft GRIFT | Proposed | The collector authors a GRIFT document before grid mutation. | |
| req-aws-steampipe-grift-2 | Service Import | Proposed | Grid mutation executes through the standard GRIFT import/service-layer path. | |
| req-aws-steampipe-grift-3 | Batch Metadata | Proposed | GRIFT batch metadata records collector, target, account, region, profile, and source context. | |
| req-aws-steampipe-grift-4 | Batch Tracking | Proposed | Imported and skipped GRIFT batch IDs are accumulated on the collector and persisted to `CollectionJob.grift_batches`. | |
| req-aws-steampipe-grift-5 | No ORM Writes | Proposed | Collector code does not directly write AWS resource nodes or edges through the ORM. | |

## Run Observability
----
RID: `req-aws-steampipe-observability`
Status: `In Development`

The run record should let an operator understand what was attempted, what
changed, and what failed without exposing secrets.

The collector should populate `CollectionJob.summary` with a concise result,
for example:

```text
Collected AWS demo vpc-subnet-v0: 3 VPCs, 12 subnets, 18 edges, 1 GRIFT batch.
```

`CollectionJob.results` should be JSON-safe and redacted. Suggested shape:

```json
{
  "target_key": "demo",
  "account_id": "123456789012",
  "partition": "aws",
  "regions": ["us-east-1"],
  "profile": "vpc-subnet-v0",
  "tables": {
    "aws_vpc": {"rows": 3},
    "aws_vpc_subnet": {"rows": 12}
  },
  "normalized": {
    "nodes": {"aws_vpc": 3, "aws_subnet": 12},
    "edges": {"CONTAINS": 13, "RESIDES_IN": 24, "BELONGS_TO_ACCOUNT": 15}
  },
  "warnings": []
}
```

Errors should include enough context to debug missing Steampipe, invalid config,
invalid credentials, denied AWS APIs, invalid JSON, and GRIFT import failures.
Credential values and credential-shaped diagnostics must be redacted.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-observability-1 | Summary | In Development | Successful runs produce a concise human-readable `CollectionJob.summary`. | Shell summary reports row counts; GRIFT counts pending. |
| req-aws-steampipe-observability-2 | Structured Results | In Development | Runs populate JSON-safe table, node, edge, region, and warning counts. | Table counts implemented; node/edge counts pending normalization. |
| req-aws-steampipe-observability-3 | Redacted Errors | Implemented | Failure diagnostics are structured and redacted. | Config, profile, secret, and Steampipe failures record safe context. |
| req-aws-steampipe-observability-4 | Source Context | Implemented | Results include target key, account ID, partition, regions, and profile. | |
| req-aws-steampipe-observability-5 | No Secret Values | Implemented | Results and summaries never include AWS access keys, secret keys, or session tokens. | Secret values are passed only through subprocess env. |

## v0 Non-Goals
----
RID: `req-aws-steampipe-nongoals`
Status: `Proposed`

The v0 AWS Steampipe collector explicitly does not define:

- deletes, reaping, tombstones, or absence semantics
- broad AWS account inventory beyond the `vpc-subnet-v0` profile
- dynamic model generation from Steampipe metadata
- arbitrary SQL execution supplied by users, grid state, or configuration
- assume-role, external ID, AWS SSO, AWS Organizations account fanout, or
  cross-account inventory
- Steampipe Postgres FDW integration inside TAP's database
- metric ingestion or time-series storage
- Security Hub, GuardDuty, Inspector, Access Analyzer, Config, or other finding
  model semantics
- autonomous remediation or side-effecting AWS actions

Deletes and reaping are expected to be difficult and important. When defined,
they must use GRIFT and the TAP service-layer import path rather than a
collector-specific side channel.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-nongoals-1 | No Deletes | Proposed | v0 creates/updates and reports coverage; it does not delete or reap absent resources. | |
| req-aws-steampipe-nongoals-2 | No Dynamic Schema | Proposed | v0 does not create TAP models from Steampipe metadata at runtime. | |
| req-aws-steampipe-nongoals-3 | No Arbitrary SQL | Proposed | v0 does not execute user-supplied or grid-supplied SQL. | |
| req-aws-steampipe-nongoals-4 | No Cross-Account Fanout | Proposed | v0 targets one configured account, not AWS Organizations inventory. | |
| req-aws-steampipe-nongoals-5 | No AWS Actions | Proposed | v0 is read-only against AWS and does not perform remediation or side-effecting cloud actions. | |
