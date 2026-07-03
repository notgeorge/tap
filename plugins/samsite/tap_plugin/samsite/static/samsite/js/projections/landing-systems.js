/**
 * Samsite landing — seed the AWS cluster roots.
 *
 * Frame layout that runs FIRST in the elevation. It places the entry node of
 * the arrangement-driven AWS stories (website, compliance) at a provisional
 * position so their per-Component arrangements (run next by the runtime, per
 * cluster Layout) can build each cluster's internal 2D shape relative to its
 * root. The Deploy & Bootstrap cluster is NOT seeded here — it's a simple row
 * laid out + labeled wholesale by the adh helper in the finalize pass, so it
 * needs neither a root anchor nor arrangements.
 *
 * Everything global — treating each cluster as a group, left-aligning them,
 * distributing them vertically with even gaps, then deriving the GitHub /
 * Sigstore / OIDC-issuer positions off the settled groups, plus compound
 * nesting and scope boxes — happens in the finalize pass (landing-finalize.js),
 * which runs LAST, after the website/compliance arrangements have settled
 * member positions. The group bounding boxes don't exist until then, so the
 * composition can't live here.
 *
 * Provisional positions: only the build DIRECTION matters at this stage. finalize
 * re-aligns and re-distributes the whole groups afterward, so the exact
 * provisional x/y here are not load-bearing.
 *
 * Companion entities: the Layout entities samsite-landing-layout (this module)
 * and samsite-landing-finalize (landing-finalize.js) in
 * plugins/samsite/grift/landing.grift.json.
 */

// Only the arrangement-driven clusters need a seeded root. Deploy & Bootstrap is
// laid out wholesale by adh in finalize, so it has no entry here.
const CLUSTER_ROOTS = [
    {root_entity_type: "aws_core__aws_route53_zone",      x:  250, y:  200, cluster: "website"},
    {root_entity_type: "aws_core__aws_eventbridge_rule",  x:  250, y:  480, cluster: "compliance"},
];

export async function execute(context) {
    const {cy} = context;

    // Place the arrangement-driven AWS cluster roots — the entry node of each story.
    // Each root entity_type has exactly one samsite-tagged instance in the panel's
    // seed-search scope, so positioning by entity_type alone is sufficient. The
    // arrangements (run after this module returns) position the rest of each cluster
    // relative to its root; the finalize pass re-composes the groups globally (and
    // lays out Deploy & Bootstrap from scratch via adh).
    for (const r of CLUSTER_ROOTS) {
        cy.nodes(`[entity_type="${r.root_entity_type}"]`)
            .forEach((n) => n.position({x: r.x, y: r.y}));
    }
}
