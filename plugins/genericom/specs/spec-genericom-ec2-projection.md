# Genericom EC2 Instance Internal Projection Specification

## Philosophy

This specification defines the EC2 instance internal projection — a service-centered view that shows what is happening inside a single EC2 host. Where the AWS top-level projection (`spec-aws-projection-top-level-minimal`) shows the account/VPC/subnet containment hierarchy from above, this projection shows the computing-core internals from the host's own perspective: what programs run on it, what ports they listen on, what connections they make to upstream and downstream services, and what crypto libraries they depend on.

The motivating use case is the Anwar demo compliance narrative (`spec-rampart-demo-anwar`, `req-demo-anwar-instance-view`). The demo needs to show that the ALB-to-EC2 connection uses unencrypted HTTP on port 80, that the Django application on the host depends on OpenSSL, and that the host connects outbound to RDS and Redis. This projection makes those relationships visible and positions them as the natural surface for compliance findings.

The projection is built on the computing_core plugin's vendor-neutral primitives (`network_interface`, `ip_address`, `port`, `tcp_connection`, `program`, `file`) rather than AWS-specific constructs, so the same projection shape can eventually apply to any host-level view regardless of cloud provider.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Host-Centered | The projection is anchored on a single EC2 instance and shows its internal structure. |
| 2. | Connection-Aware | Inbound and outbound TCP connections are visible with their remote endpoints. |
| 3. | Compliance-Ready | The layout makes unencrypted connections, crypto library state, and port exposure visually obvious. |
| 4. | Dynamic | The page accepts an entity_id parameter so the same projection works for any EC2 instance. |
| 5. | Composable | The projection panel occupies the top of a page that will later include findings tables and scorecards below. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-genericom-ec2-page | [Instance Page Routing](#instance-page-routing) | Implemented | Dynamic URL at `/genericom/instance/<entity_id>` |
| req-genericom-ec2-search | [Instance Internal Search](#instance-internal-search) | Implemented | Multi-hop gryphon search scoped to the target EC2 |
| req-genericom-ec2-data | [Computing Core Seed Data](#computing-core-seed-data) | Implemented | Both Genericom EC2 instances seeded with computing-core internals |
| req-genericom-ec2-projection | [Instance Projection Definition](#instance-projection-definition) | In Development | Semantic zone layout with icon-badge exclude_types |
| req-genericom-ec2-layout | [Instance Layout Strategy](#instance-layout-strategy) | Proposed | Refined layout with semantic placement and nesting |
| req-genericom-ec2-findings | [Findings Panel](#findings-panel) | Proposed | Findings table below the projection showing alerts for this host |
| req-genericom-ec2-aws-toplevel-click | [AWS Top-Level Click Entry (One-Off)](#aws-top-level-click-entry-one-off) | Implemented | Hard-coded click-to-navigate from AWS top-level EC2 nodes; demo-grade hack pending a generic interaction system |

---

### Instance Page Routing
----
RID: `req-genericom-ec2-page`
Status: `Implemented`

The EC2 instance detail page is accessible at `/genericom/instance/<entity_id>` where the UUID identifies the target EC2 instance.

#### Implementation

- URL pattern in `tap_web/urls.py` captures the UUID and routes to `parameterized_page_view`.
- `parameterized_page_view` in `tap_web/views.py` injects the `entity_id` from the URL path into `request.GET` via `extra_query_params`, so it flows through to the panel's seed search as `$entity_id`.
- The page entity has slug `/genericom/instance` and is defined in `plugins/genericom/grift/ec2-instance-page.grift.json`.
- The same page works for any EC2 instance — `genericom-prod-web-a` and `genericom-prod-web-c` both render correctly.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-ec2-page-1 | URL Resolves | Implemented | `/genericom/instance/<uuid>` loads the EC2 instance page. | |
| req-genericom-ec2-page-2 | Entity ID Flows To Search | Implemented | The UUID from the URL is available as `$entity_id` in the panel's seed search. | |
| req-genericom-ec2-page-3 | Both Instances Work | Implemented | The page renders correctly for both `genericom-prod-web-a` and `genericom-prod-web-c`. | |

---

### AWS Top-Level Click Entry (One-Off)
----
RID: `req-genericom-ec2-aws-toplevel-click`
Status: `Implemented`

Clicking an EC2 instance node on the Genericom AWS top-level page (`/genericom`) navigates the user to that instance's dedicated page (`/genericom/instance/<entity_id>`). This is the demo entry point that connects the spatial overview to the per-instance drilldown.

#### Status Details

This is a deliberate **make-it-work** implementation. There is no general per-entity-type interaction system in TAP projections yet — no registry of click handlers keyed by entity_type, no declarative `on_click` slot on entity types, no shared "node tap → URL template" mechanism that other projections could reuse. Rather than block the demo on building that abstraction, the click handler is wired directly into the AWS top-level projection JS as a hard-coded EC2-specific case.

This shortcut means:

- Adding click navigation for another entity type (e.g. RDS, ALB) requires another hard-coded block in the same JS file.
- Adding click navigation on a different page that also renders EC2 nodes requires duplicating the handler in that projection's JS.
- The destination URL template is duplicated in JS rather than discovered from the entity-type definition.

A related side-refactor was needed in `tap_viz`: the previous `panel-graph.js` tap handler also opened the status-badge info-window when a *badged host body* was tapped. That conflicted with this projection's host-body navigation handler — both fired on the same gesture, and only the synchronous `window.location.href` won by virtue of beating the info-window's debounced timer. The fix was to make badge taps the only trigger for the info-window and free up host-body taps for plugins to claim. See `spec-viz-panel.md` `req-viz-panel-click-semantics-7` (the new "Host Body Tap Is Plugin-Owned" rule) and `req-viz-panel-click-semantics-2` (Deprecated, the old "Badged Host Click Opens Info Window" rule). This badge-info window behavior is also tracked in `spec-viz-status-badge-info.md` `req-viz-info-window-trigger`.

#### Implementation

In `plugins/genericom/static/genericom/js/projections/aws-top-level.js`, after the projection runs and shadow interactions are wired up:

```js
cy.on("tap", 'node[entity_type="aws_ec2_instance"]', (evt) => {
    const node = evt.target;
    if (node.data("_is_shadow")) return;          // skip shadow copies
    const entityId = node.id();
    if (entityId) {
        window.location.href = "/genericom/instance/" + entityId;
    }
});
```

Hover affordance: `mouseover` / `mouseout` listeners on the same selector swap `cy.container().style.cursor` to `"pointer"` so the node visually advertises itself as clickable. Shadow copies (`_is_shadow` data flag) are excluded so the affordance and the navigation only apply to the primary subnet-resident node, not the VPC-scope shadow placeholders.

The EC2 page itself (`req-genericom-ec2-page`) already accepts the entity_id via `parameterized_page_view`, so this requirement is purely about the source-side entry point.

#### Refactor Signal

Build a generic projection-interaction system when **any** of:

- A second entity type needs click navigation (RDS, ALB, Route 53 zone, etc.).
- A second projection needs the same EC2-click behavior.
- The destination URL needs to vary by deployment, environment, or user permissions.

Likely shape: a registry of `(entity_type, action) → handler` keyed declaratively per entity type (or per projection, scoped to a specific page), with the URL template discovered from the registered entity-type definition rather than hard-coded in JS. Once that exists, this block deletes itself.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-ec2-aws-toplevel-click-1 | EC2 Tap Navigates | Implemented | Tapping an EC2 instance node on `/genericom` navigates to `/genericom/instance/<entity_id>`. | |
| req-genericom-ec2-aws-toplevel-click-2 | Pointer Cursor On Hover | Implemented | Hovering an EC2 node shows a pointer cursor. | |
| req-genericom-ec2-aws-toplevel-click-3 | Shadows Excluded | Implemented | Shadow EC2 placeholders (none in current data, but defensively guarded) do not trigger navigation. | |
| req-genericom-ec2-aws-toplevel-click-4 | Marked One-Off In Code | Implemented | The handler is annotated in `aws-top-level.js` with a comment pointing back to this spec section as the refactor signal. | |

---

### Instance Internal Search
----
RID: `req-genericom-ec2-search`
Status: `Implemented`

A gryphon search gathers the computing-core internal graph for the target EC2 instance.

#### Implementation

- Search entity `EC2 Instance Internal Slice` defined in `plugins/genericom/grift/ec2-instance-page.grift.json`.
- Uses 8 MATCH clauses with UNION semantics across the advanced executor.
- First 5 clauses are multi-hop chains anchored on `ec2.entity_id = $entity_id`:
  - `ec2 -HOSTS-> interface -HAS_IP-> ip`
  - `ec2 -HOSTS-> interface <-ATTACHED_TO- port`
  - `ec2 -HOSTS-> program -LISTENS_ON-> port`
  - `ec2 -HOSTS-> program -DEPENDS_ON-> file`
  - `ec2 -HOSTS-> program -CONNECTS_TO-> tcp -CONNECTS_TO-> remote_port`
- Remaining 3 clauses are edge-type scans for remote-side entities (inbound connections, remote hosts, port-to-IP bindings).
- Returns a graph envelope (nodes + edges) in extended layer for visualization.

#### Development

The multi-hop chains required extending the gryphon advanced executor to support UNION across multiple multi-hop MATCH clauses and per-clause WHERE predicate filtering. The last 3 clauses remain unscoped edge-type scans — acceptable for the demo dataset but will need tighter scoping when other environments are added.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-ec2-search-1 | Scoped To Instance | Implemented | The search returns computing-core entities connected to the target EC2 instance. | |
| req-genericom-ec2-search-2 | Key Entities Present | Implemented | Results include the EC2, its network interface, IP, listening port, Django program, OpenSSL library, TCP connections, and remote endpoints (ALB, RDS, Redis). | |
| req-genericom-ec2-search-3 | Graph Envelope Format | Implemented | Results are a graph envelope (nodes + edges) suitable for Cytoscape rendering. | |

---

### Computing Core Seed Data
----
RID: `req-genericom-ec2-data`
Status: `Implemented`

Both Genericom EC2 instances are seeded with computing-core internals.

#### Implementation

- Seed data in `plugins/genericom/grift/ec2-internals.grift.json`.
- Per EC2 instance: `network_interface` (eth0), `ip_address`, `port` (:80/tcp listening), `program` (Django 5.1.3), `file` (libssl.so.3 / OpenSSL 3.0.12), and 3 `tcp_connection` nodes (ALB inbound, RDS outbound, Redis outbound).
- Shared nodes: RDS port :5432, Redis port :6379, and their IP addresses.
- Edge types: HOSTS, HAS_IP, ATTACHED_TO, LISTENS_ON, DEPENDS_ON, CONNECTS_TO, AVAILABLE_AT.
- OpenSSL library modeled as a `file` entity at `/usr/lib64/libssl.so.3` with `configuration.fips_mode` and `configuration.fips_provider_available` fields.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-ec2-data-1 | Both Instances Seeded | Implemented | web-a and web-c both have computing-core internal structure. | |
| req-genericom-ec2-data-2 | TCP Connections Modeled | Implemented | ALB inbound, RDS outbound, and Redis outbound connections exist as tcp_connection nodes with directional CONNECTS_TO edges. | |
| req-genericom-ec2-data-3 | Crypto Library Present | Implemented | OpenSSL 3.0.12 is modeled as a file entity with FIPS mode metadata. | |

---

### Instance Projection Definition
----
RID: `req-genericom-ec2-projection`
Status: `In Development`

The projection definition for the EC2 internal view.

#### Implementation

- Projection entity `EC2 Instance Internal Projection` defined in `plugins/genericom/grift/ec2-instance-page.grift.json`.
- Single elevation `ec2-internal` with a cose layout as the initial starting point.
- Layout JS at `plugins/genericom/static/genericom/js/projections/ec2-internal.js`.
- `node_style` uses object form `{mode: "icon-badge", exclude_types: [...]}` to disable icon badges on small entities (ports, TCP connections, IPs, keys) while keeping them on programs, files, and AWS resources.

#### Development

The layout uses hard-coded positional placement with semantic zones: interfaces on the left edge with ports stacked vertically inside, programs in the center-top, files at the bottom, external services outside the EC2 container (ALB left, RDS right, Redis above). TCP connections are positioned near their traffic flow. Edges are styled thick (3px) and dark for visibility.

A cascade-reveal bug was discovered during development: Cytoscape treats `opacity: 0` as `:hidden`, which prevented the edge fade-in timer from finding any edges. Fixed by using `opacity: 0.001` for the initial edge zero-out in `cascade-reveal.js`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-ec2-projection-1 | Projection Renders | Implemented | The projection renders all computing-core entities in the Cytoscape panel. | |
| req-genericom-ec2-projection-2 | Semantic Layout | Implemented | Entities are grouped by role: interfaces left, programs center, files bottom, services outside. | |
| req-genericom-ec2-projection-3 | Connection Direction Visible | Implemented | Edges show directional arrows; inbound ALB left, outbound RDS right, Redis above. | |
| req-genericom-ec2-projection-4 | Finding Surfaces Visible | In Development | Unencrypted HTTP connection visible but not yet highlighted; crypto library present. | |

---

### Instance Layout Strategy
----
RID: `req-genericom-ec2-layout`
Status: `Proposed`

The refined layout for the EC2 internal projection should group entities semantically and make the compliance narrative visually clear.

#### Implementation

The layout should organize the graph into visually distinct zones:

- **Inbound zone** (top or left): ALB and the inbound TCP connection arriving at the host's listening port.
- **Host zone** (center): the EC2 instance containing its network interface, IP address, listening port, program, and crypto library.
- **Outbound zone** (bottom or right): outbound TCP connections to RDS and Redis with their remote ports and IP addresses.

The unencrypted HTTP connection (ALB → EC2:80) should be visually prominent as the primary finding target. The OpenSSL library should be visible as a dependency of the Django program.

#### Development

The layout may use bounded-layer nesting (the EC2 as a viewport parent containing its hosted resources) or a simpler positional strategy. The choice depends on what reads best at the demo scale.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-ec2-layout-1 | Semantic Grouping | Proposed | Entities are visually grouped by role (inbound, host, outbound). | |
| req-genericom-ec2-layout-2 | Traffic Direction Clear | Proposed | The layout shows a clear left-to-right or top-to-bottom traffic flow. | |
| req-genericom-ec2-layout-3 | Finding Prominence | Proposed | The unencrypted HTTP connection is visually prominent. | |
| req-genericom-ec2-layout-4 | Host Containment | Proposed | The EC2 instance visually contains its internal resources. | |

---

### Findings Panel
----
RID: `req-genericom-ec2-findings`
Status: `Proposed`

A findings table below the projection panel shows compliance findings associated with this EC2 instance.

#### Implementation

The page layout should include a second row below the projection panel containing a findings table. The table should show findings linked to entities in the projection — primarily the unencrypted HTTP finding on the ALB-to-EC2 TCP connection.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-ec2-findings-1 | Findings Table Visible | Proposed | The instance page includes a visible findings table below the projection. | |
| req-genericom-ec2-findings-2 | Findings Scoped To Host | Proposed | The table shows findings associated with the target EC2 instance and its connected entities. | |
| req-genericom-ec2-findings-3 | Finding Detail Readable | Proposed | Each finding row shows enough detail to understand the compliance issue. | |

---

## Cross-References

- `spec-rampart-demo-anwar` — `req-demo-anwar-instance-view` defines the demo-level goal this projection serves.
- `spec-aws-projection-top-level-minimal` — the companion top-level AWS projection that this view drills down from.
- `spec-computing-core-v0` — defines the vendor-neutral models used by this projection.
- `spec-grid-gryphon-multihop-aggregation` — `req-grid-gryphon-multihop-envelope` enables the multi-hop graph envelope search.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed | Hey everyone, here's an idea. |
| Approved for Development | Requirement is accepted and ready to be implemented. |
| In Development | Actively being worked on. |
| Implemented | Has been written. |
| Verified | Has met the acceptance criteria. |
| Deprecated | No longer live. |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`
