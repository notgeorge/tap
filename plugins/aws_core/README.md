# AWS Core Developer Notes

This file holds developer and AI-agent notes for the AWS Core plugin.
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

## Collector status — boto3 pivot (2026-05-17)

There is currently **no AWS collector**. The earlier Steampipe-based
collector (and the `session/codex-prime` tooling layer built on it) was
excised on 2026-05-17 ahead of a from-scratch `boto3` collector that
begins 2026-05-18.

The **complete** Steampipe effort is recoverable in one place:

```
git tag park/steampipe-tooling
```

That tag holds the deleted code, the design spec
(`spec-aws-steampipe-collector-v0.md`), the table inventory
(`docs/steampipe-aws-table-inventory.yaml`), the setup guide, and the
plugin tooling layer. It is the durable record of what was learned —
mine it to guide the boto3 build, do not resurrect it wholesale. The
decision rationale lives in the AAR at
`aar/2026-05-16-aws-collector-sprint-sprawl.md`.

What is **preserved and collector-agnostic** (the durable WHAT that
guides the boto3 build): the 37 resource-type models, 15 edge types,
reference GRIFT, and the specs `spec-aws-core-v0.md`,
`spec-aws-core-catalog.md`, `spec-aws-projection-top-level-minimal.md`.

The table-inventory decision buckets below remain a useful planning
lens (they classify AWS resources, not Steampipe specifics) — the
boto3 collector should reach the same per-resource classifications:

- `implemented_model`: an AWS resource maps to an existing `aws_core` model.
- `model_gap_candidate`: a likely durable AWS resource that may deserve a model.
- `edge_or_attribute_candidate`: a relationship, attachment, association, rule,
  or detailed configuration that likely enriches existing nodes or creates
  edges.
- `evidence_candidate`: a finding, evaluation, compliance result, health event,
  recommendation, or similar observation.
- `metric_candidate`: a metric/time-series source that should not become a normal
  resource node.
- `attribute_or_observation_candidate`: a backup, snapshot, report, version,
  scan, log, or other detail that needs more judgment.

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

1. Spec the boto3 collector from scratch (mine the parked Steampipe spec at
   `park/steampipe-tooling` for durable design knowledge; do not copy it).
2. Specify AWS credential and secret resolution through `tap_cares`.
3. Specify collector configuration for account, region, and collection scope.
4. Build the first boto3-backed collector for VPCs and subnets in a demo
   account.
5. Expand by resource family, adding models and edges intentionally.

Deletes and reaping are explicitly deferred. When they arrive, they should be
expressed through GRIFT and the TAP service-layer import path rather than a
collector-specific side channel.

## First Collector Slice

The first boto3 collector slice should be deliberately small (this shape
is collector-agnostic and survived the pivot — it is the durable target):

- resolve AWS credentials through `tap_cares` secrets
- call the boto3 EC2 APIs for VPCs and subnets
- normalize responses into existing `Vpc` and `Subnet` models
- store the full normalized resource payload in each node's `configuration`
- create account/region/VPC/subnet relationship edges where the current edge
  vocabulary supports them
- submit a GRIFT batch through the existing `tap_cares` collector path
- produce a useful `CollectionJob.summary`

No deletion, reaping, or implied absence semantics belong in the first slice.

Current implementation status (2026-05-17): **nothing** — the collector
package (`plugins/aws_core/collectors/`) is intentionally empty and no
collector is registered in `apps.py`. The boto3 collector is built from
scratch starting 2026-05-18. The credential/config/target *patterns* from
the prior collector are documented in the parked spec at
`park/steampipe-tooling` and should inform (not be copied into) the boto3
design.
