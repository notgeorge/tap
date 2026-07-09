# FedRAMP 20x KSI Authorization Boundary Specification

> **SUPERSEDED (Phase B, 2026-07-08).** The `boundary` model moved out of `fedramp_20x_ksi`
> into the regime-agnostic **compliance_core** substrate as
> `compliance_core__compliance_boundary`, with its `SCOPED_TO_COMPLIANCE_BOUNDARY` edge —
> generalized from a FedRAMP ATO boundary to a regime-agnostic authorization boundary. Its
> contract now lives in
> [`spec-compliance-core-v0.md`](../../compliance_core/specs/spec-compliance-core-v0.md).
> Retained for the boundary-as-fan-in-scope rationale.

## Philosophy

A FedRAMP authorization (ATO) is granted to a **system**, and a system is
defined by its **authorization boundary** — the perimeter that says
"these components are in scope for this authorization, and these are
not." The boundary is the single most load-bearing concept in a FedRAMP
package: every control, every piece of evidence, every finding is
*about* something inside a boundary.

TAP today has the components (AWS resources, collected by `aws_core`)
and the compliance catalog (`KsiTheme`, `KsiIndicator`, `Finding`,
`Evidence`). What it lacks is the perimeter. The **Boundary** model adds
it: a node that names an authorization boundary, with system components
linked to it by the `SCOPED_TO_BOUNDARY` edge.

This is deliberately an *initial pass*. The boundary node + the
membership edge are the minimum that makes "what is in scope for this
ATO?" a real graph query. Structured FedRAMP metadata (impact level, ATO
dates, authorizing official) and richer membership semantics are Future
Work, scoped when a consumer needs them.

### Why a dedicated node type, not a dimension or a tag

A boundary deserves identity, edges, history, and graph-visible
lifecycle — it is exactly the case the "create the dedicated node type,
don't jam" rule is about. A boundary is not a scoping dimension (it is
queryable subject matter, not a partition key) and not a tag (it has its
own description, its own membership set, and will grow its own fields).
It is a node.

### Edge direction — `SCOPED_TO_BOUNDARY`, component → boundary

The membership edge is `SCOPED_TO_BOUNDARY`, pointing **from the
contained component to the boundary**. Rationale:

- The edge naming convention (`tap_grid/skills/add-edge`) is
  `<ACTION>_<OBJECT>`, with a locative carve-out for predicates like
  `BELONGS_TO_ACCOUNT`, `RESIDES_IN`, `BOUND_TO_AZ`. Every locative edge
  in the codebase points contained → container (the small thing names
  its relationship to the big thing). `SCOPED_TO_BOUNDARY` follows that:
  verb `SCOPED`, locative `TO`, object `BOUNDARY`.
- `SCOPED TO` is the accurate FedRAMP predicate — components are "in
  scope of" an authorization boundary. `RESIDES_IN` was considered and
  rejected: it implies physical location, and an authorization boundary
  is a *scope*, not a place.
- "Identify everything inside boundary X" is a fan-in query: all
  `SCOPED_TO_BOUNDARY` edges whose target is X — structurally identical
  to "everything in account X" via `BELONGS_TO_ACCOUNT`.

The originating request named the edge `INSIDE_BOUNDARY` and described
"pointing the boundary at the account." `INSIDE_BOUNDARY` carries no
verb and does not match the convention; the direction phrasing was
loose. This spec resolves both to `SCOPED_TO_BOUNDARY`,
component → boundary. **Open for the author to flip** if a
boundary-as-source (`CONTAINS_*`) form is preferred — flagged here
rather than silently chosen.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Name The Perimeter | A `Boundary` node names a FedRAMP authorization boundary |
| 2. | Membership Is An Edge | `SCOPED_TO_BOUNDARY` links a component to its boundary; membership is graph-queryable, not implicit |
| 3. | Narrow Initial Pass | Only `name` + `description` ship today; structured FedRAMP metadata is added as typed fields when a consumer needs them |
| 4. | Cross-Plugin Membership | A boundary scopes components of any entity type (AWS resources, accounts, future external entities); the edge's `sources` is an intentional wildcard |
| 5. | Demo-Seeded | The samsite landing GRIFT seeds one boundary, pinned to the AWS account |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-fedramp-20x-ksi-boundary-model | [Boundary Model](#boundary-model) | Implemented | `Boundary` BaseModel with `name`, `description` |
| req-fedramp-20x-ksi-boundary-edge | [Scoped-To-Boundary Edge](#scoped-to-boundary-edge) | Implemented | `SCOPED_TO_BOUNDARY`, component → boundary, wildcard sources |
| req-fedramp-20x-ksi-boundary-seed | [Demo Seed Data](#demo-seed-data) | Implemented | samsite landing GRIFT seeds one boundary pinned to the `aws_account` |
| req-fedramp-20x-ksi-boundary-rendering | [Boundary Rendering](#boundary-rendering) | Proposed | "Bright red perimeter incorporating all contained systems" — display/projection work, deferred |
| req-fedramp-20x-ksi-boundary-path-membership | [Path-Embedded Membership](#path-embedded-membership) | Proposed | Directed-relationship traversal ("everything inside the boundary") via embedded path information in edges — shape TBD |

---

### Boundary Model
----
RID: `req-fedramp-20x-ksi-boundary-model`
Status: `Implemented`

`Boundary` is a `BaseModel` in `fedramp_20x_ksi` (`plugins/fedramp_20x_ksi/models/boundary.py`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-boundary-model-1 | Entity Type | Implemented | `ENTITY_TYPE = "fedramp_20x_ksi__boundary"`; registered in `tap-plugin.toml` `[models]`. | Owner-namespaced per `req-plugin-type-node-prefix` (2026-07-02 sweep), like the plugin's other compliance-domain models (`fedramp_20x_ksi__finding` / `__evidence` / `__exception`). The `compliance` dimension value stays the bare `"boundary"` — a dimension namespace, not a type. |
| req-fedramp-20x-ksi-boundary-model-2 | Fields | Implemented | `name` (required on create) and `description`. Both in `FIELD_CRUD_SCHEMA` and `FIELD_VALIDATION_SCHEMA`. | Initial pass — structured FedRAMP metadata added later as typed fields. |
| req-fedramp-20x-ksi-boundary-model-3 | Dimensions | Implemented | `DEFAULT_DIMENSIONS = {"compliance": "boundary"}`. | Sits in the plugin's `compliance` dimension namespace. |
| req-fedramp-20x-ksi-boundary-model-4 | Display + Icon | Implemented | No type icon (`ENTITY_ICON = ""`): `DEFAULT_DISPLAY` renders a red-themed round-rectangle, which is sufficient to read the boundary on the graph and is on-theme with the eventual bright-red perimeter. The corner-bracket glyph was dropped — it added visual noise without aiding recognition. | The `boundary.svg` asset remains in `static/` (orphaned) for easy revival. |

### Scoped-To-Boundary Edge
----
RID: `req-fedramp-20x-ksi-boundary-edge`
Status: `Implemented`

`SCOPED_TO_BOUNDARY` (`plugins/fedramp_20x_ksi/edges/SCOPED_TO_BOUNDARY.edge.json`)
links a system component to the authorization boundary it is in scope for.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-boundary-edge-1 | Direction | Implemented | Component (source) → boundary (target). | See Philosophy § edge direction. |
| req-fedramp-20x-ksi-boundary-edge-2 | Targets | Implemented | `targets = ["boundary"]`. | The constraint system uses Permission Union (`tap_grid/constraints.py::validate_edge`) — an edge is allowed if the node *or* the edge type permits it. The edge-side `targets` declaration therefore *permits* `boundary` targets; hard rejection of a non-boundary target additionally requires the receiving node to declare inbound constraints. Not a gap — the documented constraint model. |
| req-fedramp-20x-ksi-boundary-edge-3 | Wildcard Sources | Implemented | `sources` is omitted (wildcard). A boundary scopes components of any entity type, across plugins. | Intentional cross-plugin wildcard, per the add-edge skill's wildcard-justification guidance. |
| req-fedramp-20x-ksi-boundary-edge-4 | Default Dimensions | Implemented | `{"compliance": "boundary"}`, matching the boundary node. | |

### Demo Seed Data
----
RID: `req-fedramp-20x-ksi-boundary-seed`
Status: `Implemented`

The samsite landing GRIFT (`plugins/samsite/grift/landing.grift.json`)
seeds one `Boundary` — "Samsite Authorization Boundary" — and a
`SCOPED_TO_BOUNDARY` edge from the collected `aws_account` node to it.
The landing-page Gryphon search adds `MATCH (b:boundary)` so the
boundary renders in the graph.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-fedramp-20x-ksi-boundary-seed-1 | One Boundary Node | Implemented | The samsite landing batch seeds a single `boundary` node. | The seed is a deployment artifact in the samsite plugin, not the framework plugin — same pattern as the ComplianceContext seed. |
| req-fedramp-20x-ksi-boundary-seed-2 | Pinned To The Account | Implemented | A `SCOPED_TO_BOUNDARY` edge links the `aws_account` node to the boundary. | Initial pass: the account stands in for "the whole deployment". Per-resource membership edges follow. |
| req-fedramp-20x-ksi-boundary-seed-3 | Rendered In The Landing Graph | Implemented | The landing search's multi-MATCH includes `MATCH (b:boundary)`, binding a variable other than `n` so the tag-filter WHERE does not apply to it. | |

### Boundary Rendering
----
RID: `req-fedramp-20x-ksi-boundary-rendering`
Status: `Proposed`

The intended visualization is a **bright red perimeter that visually
incorporates every system inside the boundary** — a hull / compound-node
rendering, not just a node with edges. That is `tap_viz` display and
projection work and is deferred. The initial pass renders the boundary
as a red-themed node connected by `SCOPED_TO_BOUNDARY` edges; the
perimeter-hull rendering is the follow-up.

### Path-Embedded Membership
----
RID: `req-fedramp-20x-ksi-boundary-path-membership`
Status: `Proposed`

The boundary is intended to be the first case of **directed-relationship
traversal** — answering "identify all the things inside the boundary"
efficiently via some form of embedded path information inside edges.
The exact shape is TBD and explicitly out of scope for the initial
pass. Today the answer is a plain fan-in query over `SCOPED_TO_BOUNDARY`
edges; that is sufficient until membership sets grow large enough to
need the path-embedding optimization.
