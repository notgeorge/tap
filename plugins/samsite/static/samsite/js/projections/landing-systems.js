/**
 * Samsite landing — seed the AWS cluster roots.
 *
 * Frame layout that runs FIRST in the elevation. It places the entry node of
 * each AWS story at a provisional position so the per-Component arrangements
 * (run next by the runtime, per cluster Layout) can build each cluster's
 * internal 2D shape relative to its root.
 *
 * Everything global — treating each cluster as a group, left-aligning them,
 * distributing them vertically with even gaps, then deriving the GitHub /
 * Sigstore / OIDC-issuer positions off the settled groups, plus compound
 * nesting and scope boxes — happens in the finalize pass (landing-finalize.js),
 * which runs LAST, after the arrangements have settled member positions. The
 * group bounding boxes don't exist until then, so the composition can't live
 * here.
 *
 * Provisional positions: only the build DIRECTION matters at this stage — the
 * bootstrap cluster is a single horizontal row that builds LEFTWARD from its
 * OIDC-provider root (negative-offset arrangements), so that root starts to the
 * right. finalize re-aligns and re-distributes the whole groups afterward, so
 * the exact provisional x/y here are not load-bearing.
 *
 * Companion entities: the Layout entities samsite-landing-layout (this module)
 * and samsite-landing-finalize (landing-finalize.js) in
 * plugins/samsite/grift/landing.grift.json.
 */

const CLUSTER_ROOTS = [
    {root_entity_type: "aws_route53_zone",      x:  250, y:  200, cluster: "website"},
    {root_entity_type: "aws_eventbridge_rule",  x:  250, y:  480, cluster: "compliance"},
    // Bootstrap root sits to the right so its arrangements can build the row
    // leftward (lock ← tfstate-S3 ← deploy-role ← OIDC-provider).
    {root_entity_type: "aws_iam_oidc_provider", x:  970, y:  760, cluster: "bootstrap"},
];

export async function execute(context) {
    const {cy} = context;

    // Place the three AWS cluster roots — the entry node of each story. Each root
    // entity_type has exactly one samsite-tagged instance in the panel's seed-search
    // scope, so positioning by entity_type alone is sufficient. The arrangements
    // (run after this module returns) position the rest of each cluster relative to
    // its root; the finalize pass re-composes the groups globally.
    for (const r of CLUSTER_ROOTS) {
        cy.nodes(`[entity_type="${r.root_entity_type}"]`)
            .forEach((n) => n.position({x: r.x, y: r.y}));
    }
}
