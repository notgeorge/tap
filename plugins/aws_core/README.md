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

## Service icons

New AWS-service BaseModels must not get hand-drawn icons. The `get-aws-icons`
skill (`skills/get-aws-icons/`) sources the official AWS Architecture icon for a
model's `ENTITY_ICON` key: it downloads the pack on demand to a tmp dir (never
committed, never persisted — re-downloaded per run by design) and installs the
SVG normalized to the existing 80×80 AWS-branded convention. `add-model` Step 7
points here, so creating a service model picks this up automatically. The first
real run should also replace the hand-drawn placeholders `aws-cloudfront`,
`aws-cloudwatch`, `aws-eventbridge` (created during the boto3 collector
model-gap work).

## Collector status — boto3 pivot

The Steampipe-based collector (and the `session/codex-prime` tooling
layer built on it) was excised on 2026-05-17. The replacement is a
from-scratch **manifest-driven boto3 collector**, now **specified but
not yet built**:

> **Canonical spec:** [`specs/spec-aws-core-collector-v0.md`](specs/spec-aws-core-collector-v0.md)
> — a generic engine driven by a JSON resource manifest; per-resource
> code only as two bounded, write-once seams (fan-out hydrate; deferred
> policy-document resolver). That spec is authoritative for collector
> behavior; this file is orientation only.

No collector is registered yet: `plugins/aws_core/collectors/` is empty
and `apps.py` registers none. Build is fenced to the
`step-rampart-sam-demo` resource set (S3, CloudFront, ACM, Route 53,
Lambda, IAM role, CloudWatch log group, EventBridge rule), one account,
no deletes.

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
`docs/aar/2026-05-16-aws-collector-sprint-sprawl.md`.

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

Steps 1–3 are **done**: the collector, its credential/secret resolution,
and its run/config shape are specified in
[`specs/spec-aws-core-collector-v0.md`](specs/spec-aws-core-collector-v0.md)
(credentials reuse the existing `tap_cares` `aws_static_access_key`
secret path; there is no per-`Collector` config in v0). Remaining:

4. Add the three unmodeled demo resource types — CloudFront distribution,
   CloudWatch log group, EventBridge rule — via the `add-model` skill
   under `spec-aws-core-v0` (S3 / ACM / Route 53 / Lambda / IAM role
   already exist).
5. Build the manifest engine and a first vertical slice (a single-call
   resource — Lambda — end to end), then fan out across the demo set.
6. Expand by resource family by adding manifest entries, not modules.

Deletes and reaping remain explicitly deferred; when they arrive they
route through GRIFT and the service layer, never a collector side
channel (see the spec's v0 Non-Goals).

## First Collector Slice

The first slice is the manifest engine proven end to end on **one
single-call resource (Lambda)** before fanning out across the demo set:

- resolve AWS credentials through the `tap_cares` `aws_static_access_key`
  secret
- load + schema-validate the resource manifest
- drive one manifest entry's `aws_op`, project declared fields via
  jsonpath, retain the full payload in `configuration`
- emit nodes, then edges in a second pass (deterministic `uuid5`
  identity; an edge to an unmodeled target is dropped with a `warn`)
- submit one GRIFT batch via the `tap_cares` collector path; set a useful
  `CollectionJob.summary`

No deletion, reaping, or implied-absence semantics in the slice. The
authoritative contract is the spec; this is the orientation summary.

Implementation status: **not built** — `plugins/aws_core/collectors/` is
empty and `apps.py` registers no collector. The credential/config/target
*patterns* from the parked Steampipe spec (`park/steampipe-tooling`)
informed the design and were re-expressed clean-room; no code was copied
(`AGENTS.md` OSS rule).
