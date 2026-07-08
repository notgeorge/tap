# AWS Top-Level Minimal Projection Specification

## Philosophy

This specification defines the smallest useful AWS top-level projection TAP should support.

The intent is not to compute a perfect or fully authoritative layout. The intent is to get a small, coherent slice of AWS infrastructure onto the board quickly so a human can see it, react to it, and adjust it. The first layout is therefore an approximate starting point rather than a finished diagram.

This minimal projection is intentionally narrow. It exists to prove a workable projection workflow against real data before the system grows into richer AWS topology, traffic semantics, perimeter zones, or lower-elevation runtime detail. Genericom is the first worked example, but the projection shape is meant to live in `aws_core` as a reusable AWS-oriented standard.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Minimal | Show the smallest AWS infrastructure slice that is still visually useful. |
| 2. | Fast | Favor rapid first-pass placement over exact final geometry. |
| 3. | Contained | Preserve visible `account -> VPC -> subnet -> resource` structure. |
| 4. | Editable | Produce an initial scene that a human can refine manually. |
| 5. | Reusable | Define a seed AWS projection contract that can later grow into richer views and skills. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-aws-projection-top-level-minimal-scope | [Projection Scope](#projection-scope) | Proposed | Defines the minimal AWS top-level projection boundary |
| req-aws-projection-top-level-minimal-input-slice | [Input Graph Slice](#input-graph-slice) | Proposed | Exact entity and edge types gathered for the minimal view |
| req-aws-projection-top-level-minimal-scene | [Minimal Scene Contract](#minimal-scene-contract) | Proposed | Defines what is visible in the scene and what is not |
| req-aws-projection-top-level-minimal-placement | [Approximate Placement Model](#approximate-placement-model) | Proposed | Fast initial packing and containment-first sizing flow |
| req-aws-projection-top-level-minimal-genericom | [Genericom Worked Example](#genericom-worked-example) | Proposed | Concrete first proving-ground example for the minimal view |
| req-aws-projection-top-level-minimal-skill | [Future Skill Direction](#future-skill-direction) | Proposed | Describes the future skill boundary for gathering and placing the slice |
| req-aws-projection-top-level-minimal-nongoals | [Minimal Non-Goals](#minimal-non-goals) | Proposed | Explicitly deferred concerns for later work |

### Projection Scope
----
RID: `req-aws-projection-top-level-minimal-scope`
Status: `Proposed`

The minimal AWS top-level projection shows a single AWS account containing VPCs, subnets, EC2 instances, and RDS instances.

#### Status Details

This is the narrowest useful starting point for AWS infrastructure visualization in TAP. It deliberately omits most AWS service types and all richer traffic or perimeter semantics so the first result can be produced quickly and judged visually.

#### Implementation

The minimal projection has these boundaries:

- one AWS account at a time
- one or more VPCs inside that account
- all subnets inside those VPCs
- EC2 instances and RDS instances placed inside chosen subnets

The projection is intentionally limited to visible containment and rough packing. It does not yet require:

- application-lane semantics
- ingress, security, SaaS, or ops perimeter zones
- multi-account arrangement
- protocol-aware traffic display
- precise deterministic subnet ordering

#### Development

This requirement exists to keep the first AWS projection small enough to succeed. A larger first specification would force too many arbitrary placement decisions before a real scene exists to react to.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-projection-top-level-minimal-scope-1 | Single Account Only | Proposed | The minimal projection targets exactly one AWS account at a time. | |
| req-aws-projection-top-level-minimal-scope-2 | Minimal Resource Set | Proposed | The visible scope is limited to account, VPC, subnet, EC2, and RDS resources. | |
| req-aws-projection-top-level-minimal-scope-3 | Smallest Useful View | Proposed | The written scope explicitly favors a usable starter scene over broader infrastructure completeness. | |

#### Future

Later AWS projections may add account-space resources, VPC-adjacent resources, perimeter zones, and multi-account scenes once this minimal slice proves workable.

### Input Graph Slice
----
RID: `req-aws-projection-top-level-minimal-input-slice`
Status: `Proposed`

The minimal projection gathers a fixed, explicit slice of the graph rather than trying to infer its working set from the whole AWS environment.

#### Status Details

This requirement exists to keep the first projection skill and layout simple. A bounded graph slice is easier to reason about, easier to validate, and faster to place.

#### Implementation

The input graph slice includes exactly these entity types:

- `aws_account`
- `aws_vpc`
- `aws_subnet`
- `aws_ec2_instance`
- `aws_rds_instance`

> **Edge-set pruned (pre-eviction, 2026-07-08).** This Proposed projection assumed a
> structural edge slice of `BELONGS_TO_ACCOUNT` + `DIVIDED_INTO_AZ` + `RESIDES_IN`. The
> pre-eviction edge prune found all three were defined-but-never-emitted except the
> region→AZ containment, which became the specific `DIVIDED_INTO_AZ`; `RESIDES_IN` and
> `BELONGS_TO_ACCOUNT` were deleted (no collector emits them). When this projection is
> actually built it must re-scope its edge slice to edges that exist / are emitted —
> today that is only `DIVIDED_INTO_AZ`. Account-ownership and resource-location containment
> return when a collector emits them (correctly named per the add-edge skill).

The input graph slice includes exactly these edge types:

- `DIVIDED_INTO_AZ` (region → az; formerly the region→AZ portion of the generic `CONTAINS`)
- ~~`BELONGS_TO_ACCOUNT`~~, ~~`RESIDES_IN`~~ — deleted in the prune; re-add when emitted

Other entity types and edge types are out of scope for this minimal projection even if they exist in the graph.

#### Development

This explicit slice boundary is important because it separates “what the graph may know” from “what this first projection is trying to show.” The minimal projection should not degrade simply because richer AWS or computing data exists nearby.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-projection-top-level-minimal-input-slice-1 | Fixed Entity Slice | Proposed | The minimal projection gathers only the five named AWS entity types. | |
| req-aws-projection-top-level-minimal-input-slice-2 | Fixed Edge Slice | Proposed | The minimal projection gathers only `BELONGS_TO_ACCOUNT`, `DIVIDED_INTO_AZ`, and `RESIDES_IN` edges. | |
| req-aws-projection-top-level-minimal-input-slice-3 | No Implicit Expansion | Proposed | The presence of additional AWS or computing data does not enlarge the minimal input slice automatically. | |

#### Future

Later projections may extend the slice to include ALBs, target groups, account-space resources, security components, or lower-elevation computing-core nodes.

### Minimal Scene Contract
----
RID: `req-aws-projection-top-level-minimal-scene`
Status: `Proposed`

The minimal scene renders containment and placement only.

#### Status Details

This requirement intentionally narrows the visible scene to the simplest visually meaningful contract. It removes traffic semantics and perimeter concerns so the first scene can be judged on basic legibility alone.

#### Implementation

The minimal visible scene includes:

- one AWS account container
- its VPC containers
- all subnets inside those VPCs
- EC2 and RDS nodes placed inside one chosen subnet each
- visible `BELONGS_TO_ACCOUNT`, `DIVIDED_INTO_AZ`, and `RESIDES_IN` edges

All subnets render, including empty subnets.

This minimal scene does not yet show:

- non-containment perimeter zones
- left-to-right traffic semantics
- port or TCP session nodes
- non-slice AWS services

#### Development

Rendering all subnets, even when empty, preserves important structural context and gives the human editor places to reason from. That matters more here than a densely packed “only what has content” picture.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-projection-top-level-minimal-scene-1 | Containment Visible | Proposed | Account, VPC, subnet, and in-scope resources are all visible in the initial scene. | |
| req-aws-projection-top-level-minimal-scene-2 | Empty Subnets Render | Proposed | A subnet with no visible EC2 or RDS nodes still appears in the scene. | |
| req-aws-projection-top-level-minimal-scene-3 | Structural Edges Only | Proposed | The minimal scene shows only `BELONGS_TO_ACCOUNT`, `DIVIDED_INTO_AZ`, and `RESIDES_IN` edges. | |

#### Future

Later top-level AWS views may add perimeter zones, adjacency bands, or selected non-structural edges once the containment view is proven.

### Approximate Placement Model
----
RID: `req-aws-projection-top-level-minimal-placement`
Status: `Proposed`

The minimal projection uses an approximate placement model whose purpose is to get the scene started, not finished.

#### Status Details

This requirement is proposed as the core tradeoff of the minimal projection: speed and legibility are prioritized over geometry exactness.

#### Implementation

The minimal placement flow runs in this order:

1. resource packing
2. subnet sizing and placement
3. VPC sizing and placement
4. account sizing and placement

Resource packing rules:

- EC2 and RDS nodes are packed into a chosen subnet first
- multiple EC2 instances in one subnet are arranged as a simple grid
- no intra-subnet semantic ordering is required

Subnet placement rules:

- subnets must appear inside their containing VPC
- subnet ordering is not normative in this minimal version
- initial placement may be rough and later adjusted by a human

Multi-subnet placement rules:

- if a resource has multiple `RESIDES_IN` subnet edges, one subnet is chosen as the primary visible placement subnet
- the resource is rendered inside that chosen subnet
- all `RESIDES_IN` edges remain visible, including edges to the non-primary subnets

The projection is explicitly approximate by design. Its job is to create a workable first board state for human refinement.

#### Development

This model keeps the first layout system from hard-coding too much interpretation too early. It gives the human editor room to correct and improve the scene after the first render rather than demanding perfect placement logic up front.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-projection-top-level-minimal-placement-1 | Packing Before Containers | Proposed | Resources are packed before subnet, VPC, and account sizing occurs. | |
| req-aws-projection-top-level-minimal-placement-2 | Human-Editable Approximation | Proposed | The written contract states that the initial geometry is approximate and intended for human refinement. | |
| req-aws-projection-top-level-minimal-placement-3 | Multi-Subnet Primary Placement | Proposed | A multi-subnet resource is placed in one chosen subnet while keeping all `RESIDES_IN` edges visible. | |
| req-aws-projection-top-level-minimal-placement-4 | Simple Grid Packing | Proposed | Multiple EC2 instances inside one subnet may be packed as a simple grid. | |

#### Future

Later projections may add stronger placement semantics, deterministic tiering, adjacency rules, or LLM-assisted semantic planning before rendering.

### Genericom Worked Example
----
RID: `req-aws-projection-top-level-minimal-genericom`
Status: `Proposed`

Genericom is the first concrete proving ground for the minimal AWS top-level projection.

#### Status Details

This requirement anchors the abstract minimal projection in a real TAP dataset without turning the Genericom arrangement into a universal AWS truth.

#### Implementation

For the Genericom minimal scene, the visible nodes are:

| Category | Visible Nodes |
| --- | --- |
| Account | `genericom-prod` |
| VPC | `genericom-prod-vpc` |
| Subnets | `genericom-prod-public-alb-a`, `genericom-prod-public-alb-c`, `genericom-prod-private-web-a`, `genericom-prod-private-web-c`, `genericom-prod-private-db-a`, `genericom-prod-private-db-c` |
| EC2 | `genericom-prod-web-a`, `genericom-prod-web-c` |
| RDS | `genericom-prod-postgres` |

For the Genericom minimal scene, the visible edge families are:

- `BELONGS_TO_ACCOUNT`
- `DIVIDED_INTO_AZ`
- `RESIDES_IN`

For the Genericom minimal scene, the initial primary placement choices are:

| Resource | Primary Visible Placement |
| --- | --- |
| `genericom-prod-web-a` | `genericom-prod-private-web-a` |
| `genericom-prod-web-c` | `genericom-prod-private-web-c` |
| `genericom-prod-postgres` | `genericom-prod-private-db-a` |

The `genericom-prod-postgres` node still keeps its visible `RESIDES_IN` edge to `genericom-prod-private-db-c`.

This worked example is an expected initial placement, not a canonical final arrangement. A human may rearrange the scene after initial render.

#### Development

Genericom is useful here because it already contains both straightforward single-subnet placement and a multi-subnet RDS case. That makes it a good test of the minimal projection without forcing broader AWS complexity.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-projection-top-level-minimal-genericom-1 | Genericom Node List Named | Proposed | The spec explicitly names the Genericom nodes visible in the minimal scene. | |
| req-aws-projection-top-level-minimal-genericom-2 | Genericom Placement Picks Named | Proposed | The spec explicitly names the initial primary placement choices for Genericom EC2 and RDS nodes. | |
| req-aws-projection-top-level-minimal-genericom-3 | Initial Not Final | Proposed | The Genericom example is described as an initial layout seed rather than a final authoritative arrangement. | |

#### Future

Later Genericom examples may exercise richer AWS top-level projections with ALBs, target groups, account-space resources, and lower-elevation runtime detail.

### Future Skill Direction
----
RID: `req-aws-projection-top-level-minimal-skill`
Status: `Proposed`

A future skill should gather the minimal AWS slice and produce an initial placement plan from it.

#### Status Details

This requirement defines the intended handoff point between the written specification and future automation. It does not require implementation yet.

#### Implementation

The future skill should:

1. select one AWS account
2. gather the minimal input graph slice defined by `req-aws-projection-top-level-minimal-input-slice`
3. choose primary placement subnets for multi-subnet resources
4. generate an initial approximate placement for resources, subnets, VPCs, and the account
5. produce a scene that is ready for human adjustment

The future skill is expected to generate a fast first-pass layout, not a finished topology diagram.

#### Development

Defining the skill boundary now helps keep the specification practical. The spec describes what the skill should gather and what kind of output it should aim for without overcommitting to a particular implementation strategy.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-projection-top-level-minimal-skill-1 | Slice Gathering Defined | Proposed | The spec states that the future skill gathers the minimal one-account graph slice. | |
| req-aws-projection-top-level-minimal-skill-2 | Placement Plan Defined | Proposed | The spec states that the future skill chooses primary placement subnets and produces an initial placement plan. | |
| req-aws-projection-top-level-minimal-skill-3 | Human Refinement Preserved | Proposed | The spec states that the future skill's output is meant to be adjusted by a human. | |

#### Future

Later skills may add semantic interpretation, richer AWS coverage, or LLM-assisted classification before deterministic rendering.

### Minimal Non-Goals
----
RID: `req-aws-projection-top-level-minimal-nongoals`
Status: `Proposed`

Several AWS visualization concerns are intentionally deferred from the minimal projection.

#### Status Details

This requirement exists to keep the first projection bounded and to prevent later readers from assuming the omissions were accidental.

#### Implementation

Out of scope for this minimal specification:

- multi-account formatting
- left-to-right application-lane semantics
- north, east, south, and west perimeter zones
- VPC-adjacent but non-subnet resource placement
- ALB, target group, Route 53, ACM, and other non-minimal AWS service types
- lower-elevation TCP or session visualization
- richer protocol modeling above TCP

These are backlog items, not abandoned ideas.

#### Development

Calling these out explicitly protects the minimal spec from accidental scope creep while keeping the larger AWS projection direction visible.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-projection-top-level-minimal-nongoals-1 | Major Deferrals Named | Proposed | The spec explicitly names the larger AWS projection concerns that are deferred. | |
| req-aws-projection-top-level-minimal-nongoals-2 | Not Treated As Failures | Proposed | Deferred concerns are framed as intentional backlog rather than missing implementation detail. | |

#### Future

As the minimal projection proves itself, individual deferred concerns can graduate into their own top-level AWS projection requirements or follow-on specifications.
