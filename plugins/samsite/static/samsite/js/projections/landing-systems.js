/**
 * Samsite landing systems layout.
 *
 * Places the four samsite system anchors at fixed X positions in a single
 * horizontal row. Each anchor pairs with a per-system arrangement (declared
 * on the Layout entity) that stacks the rest of that system's nodes
 * vertically below its anchor — giving four side-by-side story columns:
 *
 *   dns       site         compliance       bootstrap
 *   (Route53) (CloudFront) (EventBridge)    (OIDC)
 *       │         │             │              │
 *      ACM       S3          Lambda        deploy-IAM
 *                          IAM role        tfstate-S3
 *                          log group       tfstate-DDB
 *
 * The four `Component` tag values (`dns`, `site`, `compliance`, `bootstrap`)
 * are independently tweakable: edit the corresponding Arrangement entity to
 * adjust spacing without touching this module. To change which system goes
 * where, edit the SYSTEM_ANCHORS table below.
 *
 * Companion entity: the Layout entity `samsite-landing-layout` in
 * plugins/samsite/grift/landing.grift.json references this module via
 * `definition.js_file` and lists the four arrangements that execute after
 * this function returns.
 */

const SYSTEM_ANCHORS = [
    // dns + site visually pair (the public-facing website story); compliance and
    // bootstrap are clearly separated.
    {component: "dns",        anchor_type: "aws_route53_zone",         x:  300, y: 250},
    {component: "site",       anchor_type: "aws_cloudfront_distribution", x:  600, y: 250},
    {component: "compliance", anchor_type: "aws_eventbridge_rule",     x: 1050, y: 250},
    {component: "bootstrap",  anchor_type: "aws_iam_oidc_provider",    x: 1500, y: 250},
];

// The aws_account container + boundary sit at top-left so the SCOPED_TO_BOUNDARY
// edge has a visible pair but doesn't crowd the four story columns.
const CONTAINER_NODES = [
    {entity_type: "aws_account",  x:  150, y:  60},
    {entity_type: "boundary",     x:  450, y:  60},
];

export async function execute(context) {
    const {cy} = context;

    // Anchors — one per Component. The cy element only carries spine + display
    // fields in its data (not the typed model fields like `tags`), so we can't
    // filter by tags.Project at this layer. The graph this layout is rendered
    // against is already scoped to samsite-tagged nodes by the panel's seed
    // search, and each anchor type has exactly one instance on that scope, so
    // positioning by entity_type alone is sufficient. (If the seed search
    // later widens, the right place to add a discriminator is via a
    // display.tap_viz hint baked into the envelope server-side — not a tags
    // lookup here.)
    for (const a of SYSTEM_ANCHORS) {
        cy.nodes(`[entity_type="${a.anchor_type}"]`)
            .forEach((n) => n.position({x: a.x, y: a.y}));
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
