/**
 * Samsite landing systems layout.
 *
 * Hybrid approach (path 3 from the design conversation): this module places
 * the three *cluster roots* — the entry node of each story — at fixed (x, y)
 * positions on the canvas. Everything else within each cluster is positioned
 * by stackable per-cluster arrangements (declared on the Layout entity) that
 * express the actual 2D flow between nodes, not just a vertical stack.
 *
 * Vertical stacking (3 rows, ~600 px wide canvas):
 *
 *   ┌──────────────────────────────────────┐
 *   │ COMPLIANCE                           │   ← top
 *   │   EventBridge                        │
 *   │     │                                │
 *   │   Lambda ── log-grp                  │
 *   │     │  └─ IAM-role above logs        │
 *   ├──────────────────────────────────────┤
 *   │ WEBSITE                              │   ← middle
 *   │   Route53 ── ACM                     │
 *   │     │                                │
 *   │   CloudFront ── S3                   │
 *   ├──────────────────────────────────────┤
 *   │ DEPLOY / BOOTSTRAP                   │   ← bottom
 *   │   OIDC                               │
 *   │     │                                │
 *   │   deploy-IAM ── tfstate-S3           │
 *   │                  └─ tfstate-DDB      │
 *   └──────────────────────────────────────┘
 *
 * Each arrangement is a single-rule positioning step (anchor + member +
 * axis + offset) — they stack to build up the 2D structure. The Layout
 * entity references all of them in execution order. Arrangements are
 * root-anchor relative, so moving a root translates its whole cluster.
 *
 * Companion entity: the Layout entity `samsite-landing-layout` in
 * plugins/samsite/grift/landing.grift.json.
 */

import {resolveNesting, HIDDEN_CONTAINMENT_CLASS} from "/static/tap_viz/js/runtime/nested-projection.js";

const CLUSTER_ROOTS = [
    {root_entity_type: "aws_eventbridge_rule",  x:  250, y:  200, cluster: "compliance"},
    {root_entity_type: "aws_route53_zone",      x:  250, y:  450, cluster: "website"},
    {root_entity_type: "aws_iam_oidc_provider", x:  250, y:  700, cluster: "bootstrap"},
];

// aws_account and boundary become compound parents around the three cluster
// roots (see the nesting pass below). They don't need explicit positions —
// Cytoscape sizes a compound parent around its children automatically.

// Nesting relationships, applied after the arrangements settle. Two rules:
//
//   1. boundary contains aws_account     — edge: SCOPED_TO_BOUNDARY
//      (aws_account ─SCOPED_TO_BOUNDARY→ boundary, so the edge direction
//      reads child→parent in graph terms; the matcher walks it in reverse).
//   2. aws_account contains every aws_*  — dimension equality on `aws_account`.
//      Every collected aws_* node carries `dimensions.aws_account = "<id>"`
//      and the aws_account singleton itself carries the same value. The
//      shared dimension *is* the containment relationship; we don't
//      materialize edges for it.
const NESTING_RELATIONSHIPS = [
    {name: "boundary-contains-account", gryphon: "(parent:boundary)<-[:SCOPED_TO_BOUNDARY]-(child:aws_account)"},
    {name: "account-owns-resource",     dimension_match: {parent_type: "aws_account", dimension: "aws_account"}},
];

export async function execute(context) {
    const {cy} = context;

    // Place the three cluster roots — entry node of each story. Each root
    // entity_type has exactly one samsite-tagged instance on the panel's
    // seed-search scope, so positioning by entity_type alone is sufficient.
    // Arrangements (run after this module returns) position the rest of
    // each cluster relative to its root and to each other.
    for (const r of CLUSTER_ROOTS) {
        cy.nodes(`[entity_type="${r.root_entity_type}"]`)
            .forEach((n) => n.position({x: r.x, y: r.y}));
    }

    // Apply compound-parent nesting: every aws_* under aws_account, aws_account
    // under boundary. resolveNesting reads the SCOPED_TO_BOUNDARY edge and the
    // shared `aws_account` dimension value; cy.move stamps the parent
    // relationship on each cy node and Cytoscape draws the compound bbox
    // around children automatically. Done in this module rather than via
    // projectNested because samsite owns precise child positioning via the
    // arrangements — projectNested's natural-layout positioning would
    // override them. The aws_account / boundary bboxes auto-fit around
    // whatever positions the arrangements settle the children into.
    const {parentByChildId, hiddenEdgeIds, warnings} = resolveNesting(cy, NESTING_RELATIONSHIPS);
    warnings.forEach((w) => console.warn("[landing-systems nesting]", w.category, w.message));
    Object.entries(parentByChildId).forEach(([childId, parentId]) => {
        const child = cy.getElementById(childId);
        if (child && child.length > 0) child.move({parent: parentId});
    });
    // Hide edges that drove a containment assignment — once a node is nested
    // inside its parent compound, the edge that established that containment
    // (e.g. SCOPED_TO_BOUNDARY) is visual noise: the spatial nesting already
    // says it. The class is honored by the global tap_viz hidden-edge style.
    hiddenEdgeIds.forEach((edgeId) => {
        const edge = cy.getElementById(edgeId);
        if (edge && edge.length > 0) edge.addClass(HIDDEN_CONTAINMENT_CLASS);
    });
    // Boundary visual: transparent body, red border only. Override the
    // per-model `:parent[fill_color]` rule (which sets background-opacity 1)
    // at the element level so the boundary reads as an outline-only frame
    // around the aws_account compound rather than a tinted card.
    cy.nodes('[entity_type="boundary"]').style({"background-opacity": 0});

    // Members of each system are positioned by the per-Component arrangements
    // wired on the Layout entity — they run automatically after this module
    // returns. We don't touch member positions here; that's the arrangement
    // system's job, and keeping it there means each system stays
    // independently tweakable via its arrangement.

    // Fit only on the initial load so re-runs (e.g., HTMX refresh of the
    // panel) don't yank the viewport away from the user.
    if (context.trigger_reason === "initial_load") {
        cy.fit(cy.nodes(":visible"), 60);
    }
}
