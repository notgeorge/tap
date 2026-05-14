# AWS Core Developer Notes

This directory holds developer and AI-agent notes for the AWS Core plugin.
It is intentionally plugin-local so the material can travel with `aws_core`
when the plugin later moves back into its own repository or submodule.

## Purpose

`aws_core` owns the TAP vocabulary for AWS resources and relationships:

- TAP-managed AWS resource models
- AWS graph edge types
- AWS reference GRIFT data
- AWS-native collectors that populate those models
- documentation that explains model coverage and collection design

`tap_cares` owns the collector runtime, run records, secret resolution,
and GRIFT import boundary. AWS-specific collection behavior belongs here.

## Steampipe Inventory

The first inventory artifact is:

- `steampipe-aws-table-inventory.yaml`

The collector design spec is:

- `../specs/spec-aws-steampipe-collector-v0.md`

The inventory compares the upstream Steampipe AWS table catalog to the
current `aws_core` model surface. It is a planning artifact for phased
collector work, not a promise that every Steampipe table should become a
TAP model.

The inventory uses these decision buckets:

- `implemented_model`: a Steampipe table maps to an existing `aws_core` model.
- `model_gap_candidate`: a likely durable AWS resource that may deserve a model.
- `edge_or_attribute_candidate`: a relationship, attachment, association, rule,
  or detailed configuration table that likely enriches existing nodes or creates
  edges.
- `evidence_candidate`: a finding, evaluation, compliance result, health event,
  recommendation, or similar observation.
- `metric_candidate`: a metric/time-series table that should not become a normal
  resource node.
- `attribute_or_observation_candidate`: a backup, snapshot, report, version,
  scan, log, or other detail table that needs more judgment.

## Model Expansion Heuristic

For AWS inventory, the default heuristic is:

> Anything with a stable ARN is a candidate TAP node unless it is clearly only
> an embedded configuration detail, transient execution artifact, metric sample,
> or policy statement fragment.

This is a heuristic, not a law. A non-ARN resource can still be a first-class
node when it is structurally important, edge-worthy, or compliance-relevant.
VPCs, subnets, route tables, security groups, and internet gateways are all
first-class graph objects even when AWS APIs foreground provider IDs over ARNs.

## Collector Roadmap

The planned AWS collector build-out is phased:

1. Keep the Steampipe table inventory current and classify model gaps.
2. Specify AWS credential and secret resolution through `tap_cares`.
3. Specify collector configuration for account, region, and collection profile.
4. Build the first Steampipe-backed collector for VPCs and subnets in a demo
   account.
5. Expand by resource family, adding models and edges intentionally.

Deletes and reaping are explicitly deferred. When they arrive, they should be
expressed through GRIFT and the TAP service-layer import path rather than a
collector-specific side channel.

## First Collector Slice

The first collector should be deliberately small:

- resolve AWS credentials through `tap_cares` secrets
- execute Steampipe queries for `aws_vpc` and `aws_vpc_subnet`
- normalize rows into existing `Vpc` and `Subnet` models
- store full Steampipe rows in each node's `configuration`
- create account/region/VPC/subnet relationship edges where the current edge
  vocabulary supports them
- submit a GRIFT batch through the existing `tap_cares` collector path
- produce a useful `CollectionJob.summary`

No deletion, reaping, or implied absence semantics belong in the first slice.

Current implementation status: the collector shell, config validator, trusted
`vpc-subnet-v0` profile, Steampipe subprocess wrapper, and collector
registration exist under `plugins/aws_core/collectors/`. The next implementation
step is to connect the incoming `tap_cares` secrets implementation and then add
VPC/subnet normalization into GRIFT.
