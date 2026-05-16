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
coverage inventory, adding model/edge specs where needed, and then widening
the collector's hardcoded collection scope.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Inventory Map | Maintain an explicit Steampipe-to-TAP table coverage inventory |
| 2. | Runtime Safe  | Resolve AWS credentials through `tap_cares` secrets without storing secret values on the grid |
| 3. | Zero-Config   | Discover the collection target from a single well-known on-disk AWS secret — no config object, Django setting, or UI |
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
| req-aws-steampipe-config | [ENV-Based Collector Config](#env-based-collector-config) | Deprecated | The removed env/Django-setting config object; superseded by secret-discovery |
| req-aws-steampipe-config-object | [Collector Configuration](#collector-configuration) | Backlog | Future durable config object (once its shape is defined); where `target_regions`/collection-scoping migrates |
| req-aws-steampipe-secret-discovery | [Secret-Discovered Target](#secret-discovered-target) | Proposed | Zero-config: one well-known `aws/steampipe-collector` secret carries creds + region + account; no config object |
| req-aws-steampipe-self-test | [Collector Self-Test](#collector-self-test) | Proposed | Four accumulated readiness checks: secret present, secret valid, Steampipe available, AWS identity |
| req-aws-steampipe-runner | [Steampipe Execution](#steampipe-execution) | In Development | Steampipe is invoked as the extraction backend |
| req-aws-steampipe-identity | [Provider Identity Resolution](#provider-identity-resolution) | Proposed | Stable AWS source identity resolves to existing TAP entity IDs before minting new UUIDv7s |
| req-aws-steampipe-vpc-subnet | [First Collector Slice: VPC And Subnet](#first-collector-slice-vpc-and-subnet) | In Development | Initial collector imports `aws_vpc` and `aws_vpc_subnet` |
| req-aws-steampipe-grift | [GRIFT Batch Contract](#grift-batch-contract) | Proposed | Collector output mutates grid only through GRIFT import |
| req-aws-steampipe-edge-verbose-sweep | [Verbose Edge Slug Sweep](#verbose-edge-slug-sweep) | Backlog | Retire legacy generic `CONTAINS` / `RESIDES_IN` (and siblings) across aws_core in favour of the verbose sentence-forming convention |
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

1. Resolve the well-known secret `SecretRef(scope="aws", key="steampipe-collector")`
   with `tap_cares.secrets.resolve_secret(...)` — no config object (see
   [Secret-Discovered Target](#secret-discovered-target)).
2. Validate `kind` and `data` with `tap_cares.secrets.require_secret_kind(...)`
   and an AWS-plugin-owned JSON Schema requiring `data.region` and
   `metadata.account_id`.
3. Build a transient Steampipe subprocess environment containing AWS credential
   variables, scoped to `data.region` (and `metadata.target_regions` when set).
4. Run the hardcoded v0 query set (VPC + subnet).
5. Drop credential material after the subprocess boundary. Only redacted
   diagnostics and non-secret identity may reach run records or logs.

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
| req-aws-steampipe-secrets-4 | Redacted Failure | Implemented | Missing or invalid secrets fail the run with redacted structured diagnostics. | An unloaded well-known secret records `SECRET_MISSING_FILE` (run path) / `AWS_SECRET_PRESENT` fail (self-test); loaded-but-invalid records `SECRET_INVALID` / `SECRET_VALID` fail; Steampipe diagnostics scrub secret values. |
| req-aws-steampipe-secrets-5 | No Secret Persistence | Implemented | Secret values are not written to grid nodes, edges, GRIFT batches, run records, logs, or source-controlled files. | Tests cover env construction, secret repr, and diagnostic redaction. |

## ENV-Based Collector Config
----
RID: `req-aws-steampipe-config`
Status: `Deprecated`

**Deprecated.** v0 originally defined a plugin-owned JSON config object
(`AwsSteampipeCollectorConfig`: `target_key`, `account_id`, `partition`,
`secret_ref`, `regions`, `profile`) sourced from a Django setting or an
`AWS_CORE_STEAMPIPE_COLLECTOR` environment JSON. That approach is removed:

- Plugin-specific configuration in `docker-compose.yml` / core settings is an
  anti-pattern — it couples the plugin to host infrastructure and implies a
  config surface that was never designed (see the project anti-pattern note in
  AGENTS.md / the plugin spec).
- Every value the config carried already lives in, or is derivable from, the
  AWS secret itself: credentials + `data.region`, `metadata.account_id`, and an
  optional `metadata.target_regions`. The config object was redundant.

It is replaced by [Secret-Discovered Target](#secret-discovered-target)
(`req-aws-steampipe-secret-discovery`): the collector resolves a single
well-known `SecretRef` and reads everything it needs from that secret. There is
no config object, Django setting, environment variable, or UI in v0. The
`profile` knob is gone — the v0 collection scope (VPC + subnet) is a hardcoded
collector capability, not operator-selectable.

A future durable configuration object is tracked separately as
[Collector Configuration](#collector-configuration)
(`req-aws-steampipe-config-object`, Backlog) — this requirement is not revived.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-config-1 | JSON-Safe Shape | Deprecated | Superseded by secret-discovery; no config object exists. | |
| req-aws-steampipe-config-2 | Secret Reference Only | Deprecated | The secret is resolved directly by a well-known ref; nothing stores a separate `SecretRef`. | |
| req-aws-steampipe-config-3 | Explicit Regions | Deprecated | Region comes from the secret's `data.region`; optional `metadata.target_regions` downscopes. See `req-aws-steampipe-secret-discovery`. | |
| req-aws-steampipe-config-4 | Trusted Profile | Deprecated | The profile knob is removed; VPC/subnet is a hardcoded capability. | |
| req-aws-steampipe-config-5 | Superseded By Config Object | Deprecated | Future durable configuration is tracked as its own backlog requirement; `metadata.target_regions` is the interim stopgap that migrates there. | Cross-ref `req-aws-steampipe-config-object`. |

## Secret-Discovered Target
----
RID: `req-aws-steampipe-secret-discovery`
Status: `Proposed`

The AWS collector is **zero-config**: it resolves a single well-known secret
and reads everything it needs from that secret. No config object, Django
setting, environment variable, or UI.

### Well-known secret

The collector resolves exactly one `SecretRef`: **`scope="aws",
key="steampipe-collector"`** — operator file `aws/steampipe-collector.secret.json`
under `TAP_SECRETS_ROOT` (per `tap_cares/specs/spec-tap-cares-secrets.md`).
Resolved by point lookup (`resolve_secret`), not enumeration. Other
`aws_static_access_key` secrets under different keys are ignored — v0 collects
exactly the one account named by this ref.

### Secret shape

```json
{
  "scope": "aws",
  "key": "steampipe-collector",
  "kind": "aws_static_access_key",
  "description": "Read-only AWS credentials for the TAP AWS Steampipe collector.",
  "data": {
    "access_key_id": "AKIA...",
    "secret_access_key": "...",
    "region": "us-east-1"
  },
  "metadata": {
    "account_id": "123456789012",
    "target_regions": ["us-east-1", "us-west-2"]
  }
}
```

- `data.access_key_id` / `data.secret_access_key` (+ optional
  `data.session_token`): the credentials, resolved via
  `resolve_aws_static_credentials(...)` (existing `aws_static_access_key` shape).
- `data.region`: **required**. The primary region; the default collection
  region and the region for the identity check.
- `metadata.account_id`: **required**. The account the operator intends to
  collect. The identity check verifies the live credentials resolve to this
  account; a mismatch is `misconfigured`, not `error`.
- `metadata.target_regions` (optional list): downscopes collection to those
  regions. Absent ⇒ collect only `data.region`. This is **a stopgap** — see
  Future.

### Collection scope

v0 collects **VPC and subnet only**, a hardcoded collector capability (see
[First Collector Slice](#first-collector-slice-vpc-and-subnet)), not
operator-selectable. "Hoover everything in the account" is the *direction*, not
v0 scope; broader families advance through the coverage inventory and
model/edge specs.

### Future

`metadata.target_regions` is collection configuration riding in a credential
file only because no durable collector-configuration object exists yet. When
the configuration object lands ([Collector Configuration](#collector-configuration),
`req-aws-steampipe-config-object`, Backlog), `target_regions` and any future
collection-scoping move there and the secret carries only credential + identity
material again. Recorded so the stopgap does not silently calcify.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-secret-discovery-1 | Single Well-Known Ref | Proposed | The collector resolves exactly `SecretRef(scope="aws", key="steampipe-collector")` by point lookup; no config object, setting, env var, or UI. | |
| req-aws-steampipe-secret-discovery-2 | Secret Is The Target | Proposed | Credentials, `data.region`, and `metadata.account_id` come from the resolved secret; `data.region` and `metadata.account_id` are required. | |
| req-aws-steampipe-secret-discovery-3 | Optional Region Downscope | Proposed | `metadata.target_regions`, when present, scopes collection; absent ⇒ only `data.region`. | Interim; see Future. |
| req-aws-steampipe-secret-discovery-4 | Others Ignored | Proposed | Additional `aws_static_access_key` secrets under other keys are not discovered or collected in v0. | |
| req-aws-steampipe-secret-discovery-5 | No Plugin Config In Core Infra | Proposed | No plugin config in `docker-compose.yml`, core settings, or env. Supersedes `AWS_CORE_STEAMPIPE_COLLECTOR`. | Anti-pattern; cross-ref project memory / AGENTS.md. |
| req-aws-steampipe-secret-discovery-6 | target_regions Is A Stopgap | Proposed | `metadata.target_regions` is interim until the config object exists; flagged for migration, not permanent. | Cross-ref `req-aws-steampipe-config-object`. |

## Collector Configuration
----
RID: `req-aws-steampipe-config-object`
Status: `Backlog`

A durable collector configuration object — once its shape is defined — is the
proper home for collection scoping and per-target settings that today have no
home (and so ride in the secret as a stopgap; see
[Secret-Discovered Target](#secret-discovered-target) Future).

When defined it should cover at least:

- collection scoping currently stopgapped in the secret's
  `metadata.target_regions`
- future per-target / multi-account configuration (the unit of work becomes
  `(collector, configuration)`, mirroring the tiered/per-config self-test
  direction in `tap_cares/specs/spec-tap-cares-collector.md`)
- whether configuration is an on-grid object, a typed record, or another shape
  — open, decided when this requirement is promoted

This is intentionally a placeholder ticket. It is **not** the removed ENV-based
config (`req-aws-steampipe-config`, Deprecated) and must not reintroduce plugin
configuration into `docker-compose.yml` or core settings (anti-pattern).
Promote from Backlog when a second configured collector or a multi-account need
makes the shape concrete.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-config-object-1 | Shape Defined Before Build | Backlog | The configuration object's shape is specified before implementation; no implicit revival of the ENV-based approach. | |
| req-aws-steampipe-config-object-2 | Absorbs target_regions | Backlog | `metadata.target_regions` (and any other secret-borne collection scoping) migrates here; the secret returns to credential + identity material only. | Cross-ref `req-aws-steampipe-secret-discovery-6`. |
| req-aws-steampipe-config-object-3 | Not In Core Infra | Backlog | The config object does not live in `docker-compose.yml`, core settings, or env. | Anti-pattern guard. |

## Collector Self-Test
----
RID: `req-aws-steampipe-self-test`
Status: `Proposed`

The AWS Steampipe collector implements the tap-cares self-test contract
(`tap_cares/specs/spec-tap-cares-collector.md` `req-tap-cares-collector-self-test`).
It runs as **phase 1 of a collection run** (`full` or `self_test_only`):
synchronous, timeout-bounded, accumulated, read-only. It does not collect
inventory, author or import GRIFT, or mutate the grid. A non-runnable result
fails the `CollectionJob` via the standard collector failure mode — there is no
separate readiness entity and no `blocked` status (per the tap-cares contract).

### v0 Checks

Four checks, accumulated in one pass (skips do not escalate; skip-only ⇒
`ready`):

| Code | Healthy | Failure readiness | Purpose |
| --- | --- | --- | --- |
| `AWS_SECRET_PRESENT` | `pass` | `unconfigured` | The well-known `aws/steampipe-collector` secret is loaded by tap-cares. |
| `SECRET_VALID` | `pass` | `misconfigured` | Kind is `aws_static_access_key`; required credential fields + `data.region` + `metadata.account_id` satisfy the AWS schema. |
| `STEAMPIPE_AVAILABLE` | `pass` | `error` | The Steampipe executable + AWS plugin are available to the container. |
| `AWS_IDENTITY` | `pass` | `misconfigured` / `error` | A read-only Steampipe `aws_caller_identity` query succeeds and the returned account equals `metadata.account_id`. |

First-run (no secret) accumulates: `AWS_SECRET_PRESENT` `fail`, `SECRET_VALID`
`skip`, `STEAMPIPE_AVAILABLE` `pass`/`fail` (independent), `AWS_IDENTITY`
`skip`. The operator sees the missing secret *and* any local Steampipe problem
in one report, not one error at a time.

### AWS Identity Check

The identity check uses a **Steampipe** `aws_caller_identity` query (e.g.
`select account_id, arn from aws_caller_identity`) through the resolved
credentials — deliberately **not** an AWS SDK: TAP avoids new dependencies and
Steampipe is already the collection backend. It is read-only, single-row,
bounded by the self-test latency budget, and is not inventory collection.

Outcomes:

- Query succeeds, returned account == `metadata.account_id` → `pass`.
- Query succeeds, account != `metadata.account_id` → `misconfigured` (reachable,
  but the credentials are not the account the operator described).
- Query fails (bad/expired keys, no permission, unreachable) → `error`.

The result is redaction-safe: it may carry account ID, ARN/principal shape,
partition, region — never access keys, secret keys, or session tokens.

### Docs References

Non-ready checks carry `CollectorDocRef`s to the AWS setup doc (this plugin is
an *emitter* only, `req-tap-cares-collector-self-test-5`). Resolution is
`specs/spec-docs.md` `req-docs-ref-resolution`; rendering is `tap_web`
`req-web-rendering-docref`; both Backlog. Anchors target the (rewritten)
`plugins/aws_core/docs/setup-steampipe-collector.md`:

- missing secret → `#secret-file`
- missing Steampipe binary/plugin → `#host-prerequisites`
- failed identity/permissions → `#aws-permissions`

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-self-test-1 | Implements tap-cares Contract | Proposed | Implements `req-tap-cares-collector-self-test` as run phase 1; the result lands in `CollectionJob.self_test`. | |
| req-aws-steampipe-self-test-2 | Four Accumulated Checks | Proposed | `AWS_SECRET_PRESENT`, `SECRET_VALID`, `STEAMPIPE_AVAILABLE`, `AWS_IDENTITY`, accumulated; dependent checks `skip` when inputs are absent. | |
| req-aws-steampipe-self-test-3 | Missing Secret Unconfigured | Proposed | If the well-known secret is not loaded, `AWS_SECRET_PRESENT` fails and readiness is `unconfigured`. | Replaces the old config-presence checks. |
| req-aws-steampipe-self-test-4 | Invalid Secret Misconfigured | Proposed | Wrong kind, missing credential fields, missing `data.region`, or missing `metadata.account_id` ⇒ `SECRET_VALID` fail, `misconfigured`. | |
| req-aws-steampipe-self-test-5 | Steampipe Dependency Error | Proposed | Steampipe binary/plugin unavailable ⇒ `error`. | |
| req-aws-steampipe-self-test-6 | Steampipe Identity Mechanism | Proposed | The identity check is a read-only Steampipe `aws_caller_identity` query — no AWS SDK dependency. | D1 decision. |
| req-aws-steampipe-self-test-7 | Account Match | Proposed | Live account != `metadata.account_id` ⇒ `misconfigured`; query failure ⇒ `error`. | |
| req-aws-steampipe-self-test-8 | No Inventory Or Mutation | Proposed | Self-test runs no VPC/subnet inventory, writes/imports no GRIFT, mutates no grid state. | |
| req-aws-steampipe-self-test-9 | Redacted Context | Proposed | Context may carry non-secret account/region/identity metadata, never credential material. | |

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
- use the hardcoded v0 query set (not operator-selectable)
- request JSON output
- apply explicit account and region scoping
- capture structured stdout/stderr, exit status, row counts, and warnings
- redact credentials and credential-shaped values from diagnostics
- emit a `DEBUG` log of the steampipe invocation, exit status, per-table row
  counts, and **redacted** stderr/warnings, so opaque subprocess failures are
  debuggable from logs without exposing secrets
- fail visibly when Steampipe is unavailable, exits non-zero, or returns invalid
  JSON

The v0 query set (hardcoded, internally labelled `vpc-subnet-v0`) is limited to:

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
| req-aws-steampipe-runner-2 | Trusted Queries | Implemented | Queries are a hardcoded set owned by plugin code — not operator-selected and not supplied by grid data. | Profile-selection concept removed. |
| req-aws-steampipe-runner-3 | Availability Failure | Implemented | Missing Steampipe binary/configuration fails the run visibly. | |
| req-aws-steampipe-runner-4 | Scoped Regions | In Development | The runner scopes to the secret's `data.region`, widened to `metadata.target_regions` when set, rather than silently scanning every region. | Shell sets primary region env; multi-region scoping pending. |
| req-aws-steampipe-runner-5 | Redacted Diagnostics | Implemented | Command diagnostics are captured without leaking credential material. | Marker and secret-value redaction implemented. |
| req-aws-steampipe-runner-6 | Debug Logging | Proposed | The steampipe invocation, exit status, per-table row counts, and redacted stderr/warnings are emitted at `DEBUG`. The structured redacted run record remains the primary carrier. | `DEBUG` is site-ID-exempt per CLAUDE.md logging conventions. |

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

The v0 collector scope, internally labelled `vpc-subnet-v0`, is **hardcoded**
(not operator-selectable). It collects VPCs and subnets from the one
secret-named account, scoped to `data.region` (widened to
`metadata.target_regions` when set).

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

The v0 scope should create these relationships when both endpoints are
known. Edge slugs follow the verbose, sentence-forming aws_core convention
(slug + Title-case name + a semantic `description` sentence), not generic
single words:

| Edge | From | To | Reads as / Notes |
| --- | --- | --- | --- |
| `HOSTS_VPC` | `aws_region` | `aws_vpc` | "An AWS region hosts a VPC." Region reference nodes already ship in AWS Core GRIFT seed data |
| `PARTITIONED_INTO_SUBNET` | `aws_vpc` | `aws_subnet` | "A VPC is partitioned into subnets." |
| `BELONGS_TO_VPC` | `aws_subnet` | `aws_vpc` | "A subnet belongs to a VPC." |
| `BOUND_TO_AZ` | `aws_subnet` | `aws_az` | "A subnet is bound to one availability zone." Created when the AZ reference node can be resolved |
| `BELONGS_TO_ACCOUNT` | `aws_vpc` | `aws_account` | Created when the account node exists or is collected in the same batch |
| `BELONGS_TO_ACCOUNT` | `aws_subnet` | `aws_account` | Created when the account node exists or is collected in the same batch |

`subnet → region` is intentionally not a direct edge — it is reachable by
traversing `aws_subnet --BELONGS_TO_VPC--> aws_vpc --HOSTS_VPC(inv)--> aws_region`,
so a redundant edge is omitted.

`HOSTS_VPC`, `PARTITIONED_INTO_SUBNET`, `BELONGS_TO_VPC`, and `BOUND_TO_AZ` are
**new** verbose edge types this collector introduces; their `.edge.json`
definitions + registration landed with the #6 code rework. The separate
retirement of the legacy generic `CONTAINS` / `RESIDES_IN` slugs (and their
siblings) across the rest of aws_core is deferred and tracked here as
[`req-aws-steampipe-edge-verbose-sweep`](#verbose-edge-slug-sweep) (Backlog) —
the collector itself does not use those slugs, so it is not blocked.

The first implementation may create a minimal `AwsAccount` node for the
secret-named account if one does not already exist, but it should not collect
broad account metadata beyond what the v0 scope needs for relationship
anchoring.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-vpc-subnet-1 | v0 Query Set Exists | Implemented | The hardcoded `vpc-subnet-v0` query set exists in AWS plugin code; it is not operator-selectable. | Profile-selection concept removed. |
| req-aws-steampipe-vpc-subnet-2 | VPC Query | In Development | The v0 query set collects rows from `aws_vpc`. | Query shell exists; live Steampipe execution not yet verified. |
| req-aws-steampipe-vpc-subnet-3 | Subnet Query | In Development | The v0 query set collects rows from `aws_vpc_subnet`. | Query shell exists; live Steampipe execution not yet verified. |
| req-aws-steampipe-vpc-subnet-4 | Node Normalization | Proposed | VPC and subnet rows normalize into existing `Vpc` and `Subnet` models. | |
| req-aws-steampipe-vpc-subnet-5 | Raw Row Preserved | Proposed | The received Steampipe row is stored in each node's `configuration`. | |
| req-aws-steampipe-vpc-subnet-6 | Relationship Edges | Proposed | The collector creates supported account, region, VPC, subnet, and AZ edges when endpoints can be resolved. | |
| req-aws-steampipe-vpc-subnet-7 | Single-Account Scope | Proposed | v0 targets the one secret-named account, scoped to `data.region` (widened by optional `metadata.target_regions`). | |

## Verbose Edge Slug Sweep
----
RID: `req-aws-steampipe-edge-verbose-sweep`
Status: `Backlog`

The VPC/subnet collector introduced the verbose, sentence-forming edge
convention (slug + Title-case name + a semantic `description` sentence:
`HOSTS_VPC`, `PARTITIONED_INTO_SUBNET`, `BELONGS_TO_VPC`, `BOUND_TO_AZ`). The
rest of aws_core still carries the older generic single-word slugs —
`CONTAINS` ("Parent resource contains child resources…"), `RESIDES_IN`
("Resource lives in a region, AZ, VPC, or subnet…"), and siblings — which are
multi-purpose and read poorly in traversals. This requirement is the deferred
sweep that retires those generic slugs across aws_core in favour of the
verbose convention.

#### Status Details

Backlog. Deliberately deferred ("agreed to wait"): the collector does not use
the generic slugs, so it is not blocked, and a single-developer system can
make this dramatic edge-vocabulary change in one pass when it is scheduled
rather than dribbling it out. Tracked here so the deferral is a named seam,
not tribal memory. Promote when a consumer (projection, a second collector, a
query surface) actually needs the generic edges to read verbosely, or when the
edge vocabulary is next revised wholesale.

#### Scope (when promoted)

- Replace generic slugs (`CONTAINS`, `RESIDES_IN`, and any other generic
  single-word aws_core edges) with verbose, sentence-forming equivalents,
  one verbose slug per real relationship rather than one overloaded slug.
- Update every touchpoint together (single-dev, one dramatic pass): `.edge.json`
  definitions, `tap-plugin.toml` registration, GRIFT seed data, and any
  projection/spec references.
- No backward-compatibility shim or alias layer — the old slugs are removed,
  not deprecated-in-place.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-edge-verbose-sweep-1 | Generic Slugs Retired | Backlog | No generic single-word multi-purpose edge slugs remain in aws_core; each real relationship has its own verbose slug. | `CONTAINS`/`RESIDES_IN` are the headline cases. |
| req-aws-steampipe-edge-verbose-sweep-2 | All Touchpoints Updated Together | Backlog | Edge JSON, `tap-plugin.toml`, GRIFT seed data, and projection/spec references are updated in one pass. | Single-dev: no incremental-compat phase. |
| req-aws-steampipe-edge-verbose-sweep-3 | No Compatibility Layer | Backlog | Old slugs are removed outright; no alias/shim is introduced for them. | Cross-ref single-developer-system rule in `AGENTS.md`. |

## GRIFT Batch Contract
----
RID: `req-aws-steampipe-grift`
Status: `Proposed`

The collector must produce an inspectable GRIFT document before mutating the
grid. GRIFT batches are the only mutation shape for collected AWS resource
nodes and edges.

The collector creates one logical GRIFT batch per collector run. Per
`req-tap-cares-collector-grift-import-8` the collector sets a meaningful
collector-authored `name` and `description` on the batch envelope. The batch
metadata should identify:

- collector registry key
- account ID (from the secret's `metadata.account_id`)
- region(s) collected
- Steampipe plugin/source version when available
- collection start and finish timestamps

Batch nodes and edges must use canonical AWS Core entity types and edge types.
The collector uses `CollectorBase.submit_grift(...)`; the task body links each
produced `Batch` to the `CollectionJob` via a `PRODUCED_BATCH` edge at terminal
state (`tap_grid/specs/spec-grid-edge.md` `req-grid-edge-produced-batch`). There
is no `CollectionJob.grift_batches`.

No collector code may directly create, patch, replace, or delete AWS resource
nodes or graph edges through the ORM.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-grift-1 | Draft GRIFT | Proposed | The collector authors a GRIFT document before grid mutation. | |
| req-aws-steampipe-grift-2 | Service Import | Proposed | Grid mutation executes through the standard GRIFT import/service-layer path. | |
| req-aws-steampipe-grift-3 | Batch Metadata | Proposed | The collector sets a meaningful `name`/`description` on the batch; metadata records collector key, account, region(s), and source context (no target/profile — those concepts are removed). | Cross-ref `req-tap-cares-collector-grift-import-8`. |
| req-aws-steampipe-grift-4 | Batch Tracking | Proposed | Produced batches are linked to the `CollectionJob` via `PRODUCED_BATCH` edges (disposition `imported`/`skipped`); there is no `CollectionJob.grift_batches`. | Cross-ref `req-tap-cares-collector-grift-import-6`, `req-grid-edge-produced-batch`. |
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
Collected AWS vpc-subnet-v0 (acct 123456789012): 3 VPCs, 12 subnets, 18 edges, 1 GRIFT batch.
```

`CollectionJob.results` should be JSON-safe and redacted. Suggested shape:

```json
{
  "account_id": "123456789012",
  "regions": ["us-east-1"],
  "scope": "vpc-subnet-v0",
  "tables": {
    "aws_vpc": {"rows": 3},
    "aws_vpc_subnet": {"rows": 12}
  },
  "normalized": {
    "nodes": {"aws_vpc": 3, "aws_subnet": 12},
    "edges": {"HOSTS_VPC": 3, "PARTITIONED_INTO_SUBNET": 12, "BELONGS_TO_VPC": 12, "BOUND_TO_AZ": 12, "BELONGS_TO_ACCOUNT": 15}
  },
  "warnings": []
}
```

Errors should include enough context to debug missing Steampipe, a missing or
invalid well-known secret, invalid credentials, denied AWS APIs, invalid JSON,
and GRIFT import failures. Credential values and credential-shaped diagnostics
must be redacted.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-observability-1 | Summary | In Development | Successful runs produce a concise human-readable `CollectionJob.summary`. | Shell summary reports row counts; GRIFT counts pending. |
| req-aws-steampipe-observability-2 | Structured Results | In Development | Runs populate JSON-safe table, node, edge, region, and warning counts. | Table counts implemented; node/edge counts pending normalization. |
| req-aws-steampipe-observability-3 | Redacted Errors | Implemented | Failure diagnostics are structured and redacted. | Secret, identity, and Steampipe failures record safe context. |
| req-aws-steampipe-observability-4 | Source Context | In Development | Results include account ID, region(s), and the v0 scope label. | Pivot drops `target_key`/`partition`/`profile`; field-set change lands with the code rework. |
| req-aws-steampipe-observability-5 | No Secret Values | Implemented | Results and summaries never include AWS access keys, secret keys, or session tokens. | Secret values are passed only through subprocess env. |

## v0 Non-Goals
----
RID: `req-aws-steampipe-nongoals`
Status: `Proposed`

The v0 AWS Steampipe collector explicitly does not define:

- deletes, reaping, tombstones, or absence semantics
- broad AWS account inventory beyond the hardcoded v0 VPC/subnet scope
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
| req-aws-steampipe-nongoals-4 | No Cross-Account Fanout | Proposed | v0 targets the one secret-named account, not AWS Organizations inventory. | |
| req-aws-steampipe-nongoals-5 | No AWS Actions | Proposed | v0 is read-only against AWS and does not perform remediation or side-effecting cloud actions. | |
