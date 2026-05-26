/**
 * Samsite landing systems layout.
 *
 * Hybrid approach (path 3 from the design conversation): this module places
 * the three *cluster roots* — the entry node of each story — at fixed (x, y)
 * positions on the canvas. Everything else within each cluster is positioned
 * by stackable per-cluster arrangements (declared on the Layout entity) that
 * express the actual 2D flow between nodes, not just a vertical stack:
 *
 *   WEBSITE cluster                 COMPLIANCE cluster           BOOTSTRAP cluster
 *   Route53 ── ACM                  EventBridge                  OIDC
 *      │                                  │                        │
 *   CloudFront ── S3                   Lambda ── log-grp          deploy-IAM ── tfstate-S3
 *                                        │  └─ IAM-role above logs            │
 *                                                                          tfstate-DDB above
 *
 * Each arrangement is a single-rule positioning step (anchor + member +
 * axis + offset) — they stack to build up the 2D structure. The Layout
 * entity references all of them in execution order.
 *
 * Companion entity: the Layout entity `samsite-landing-layout` in
 * plugins/samsite/grift/landing.grift.json.
 */

const CLUSTER_ROOTS = [
    {root_entity_type: "aws_route53_zone",      x:  250, y: 220, cluster: "website"},
    {root_entity_type: "aws_eventbridge_rule",  x:  850, y: 220, cluster: "compliance"},
    {root_entity_type: "aws_iam_oidc_provider", x: 1400, y: 220, cluster: "bootstrap"},
];

// The aws_account container + boundary sit at top-left so the SCOPED_TO_BOUNDARY
// edge has a visible pair but doesn't crowd the four story columns.
const CONTAINER_NODES = [
    {entity_type: "aws_account",  x:  150, y:  60},
    {entity_type: "boundary",     x:  450, y:  60},
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

    // Container nodes (aws_account, boundary) — positioned but not tied to a
    // system; the SCOPED_TO_BOUNDARY edge between them is informational.
    for (const c of CONTAINER_NODES) {
        cy.nodes(`[entity_type="${c.entity_type}"]`)
            .forEach((n) => n.position({x: c.x, y: c.y}));
    }

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
