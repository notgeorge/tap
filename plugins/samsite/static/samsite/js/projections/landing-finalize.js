/**
 * Samsite landing — finalize / scene-composition pass.
 *
 * Runs LAST in the elevation (after landing-systems.js seeds the three AWS
 * cluster roots and the per-Component arrangements build each cluster's internal
 * 2D shape). This pass treats each AWS cluster as a GROUP:
 *
 *   1. measure each group's post-arrangement bounding box,
 *   2. left-align all three to a common x, and
 *   3. distribute them vertically with even gaps (top→bottom:
 *      website → compliance → deploy/bootstrap),
 *
 * then derives the dependent positions off the settled groups:
 *
 *   4. the GitHub cluster sits directly to the RIGHT of where the (bottom)
 *      bootstrap group landed, workflows in a horizontal row on the bootstrap
 *      row's y so FEDERATES_VIA reads flat,
 *   5. the OIDC issuer hub goes in the gap between bootstrap and GitHub,
 *   6. the Sigstore Rekor row is centered above the GitHub set,
 *
 * and finally applies compound nesting + scope boxes against the settled layout.
 *
 * Why a SECOND module rather than doing this in landing-systems.js: the per-cluster
 * arrangements run AFTER the frame layout's execute() returns (projection.js
 * runLayoutsSerially runs `js_file` then `arrangements` per layout, and the
 * cluster layouts come after the frame). Member positions — and therefore the
 * group bounding boxes — don't exist until a pass that runs after every cluster
 * layout. This is that pass.
 *
 * Companion: landing-systems.js (seeds roots), and the Layout entities
 * samsite-landing-layout / -finalize in plugins/samsite/grift/landing.grift.json.
 */

import {resolveNesting, HIDDEN_CONTAINMENT_CLASS} from "/static/tap_viz/js/runtime/nested-projection.js";
import {applyScopeBoxes} from "/static/tap_viz/js/runtime/layout-scope-boxes.js";

// Top→bottom group order. Selectors mirror the arrangement member queries and the
// scope-box filters: AWS resources carry a Component tag; the website group is the
// union of the dns + site components (one story on the landing).
const GROUPS = [
    {key: "website",    label: "Website Serving",    sel: (n) => { const c = (n.data("tags") || {}).Component; return c === "dns" || c === "site"; }},
    {key: "compliance", label: "Compliance Flow",     sel: (n) => (n.data("tags") || {}).Component === "compliance"},
    {key: "bootstrap",  label: "Deploy & Bootstrap",  sel: (n) => (n.data("tags") || {}).Component === "bootstrap"},
];

const SCOPE_BOXES = GROUPS.map((g) => ({label: g.label, filter: g.sel}));

// Same nesting rules as before — parent assignment is position-independent, so it
// runs here once the leaf positions (incl. github + sigstore) are settled.
const NESTING_RELATIONSHIPS = [
    {name: "boundary-contains-account", gryphon: "(parent:boundary)<-[:SCOPED_TO_BOUNDARY]-(child:aws_account)"},
    {name: "account-owns-resource",     dimension_match: {parent_type: "aws_account", dimension: "aws_account"}},
    {name: "platform-hosts-account",    gryphon: "(parent:github_platform)-[:HOSTS_ACCOUNT]->(child:github_account)"},
    {name: "account-owns-repo",         gryphon: "(parent:github_account)-[:OWNS_REPO]->(child:github_repository)"},
    {name: "repo-defines-workflow",     gryphon: "(parent:github_repository)-[:DEFINES_WORKFLOW]->(child:github_workflow)"},
    {name: "ca-contains-entries",       gryphon: "(parent:sigstore_ca)<-[:CERT_ISSUED_BY]-(child:rekor_log_entry)"},
];

// Layout constants (canvas units). Tuned for the samsite node-set; iterate visually.
const LEFT_X = 250;       // common left edge for the three AWS groups
const TOP_Y = 160;        // top of the first (website) group
const V_GAP = 48;         // vertical gap between AWS group icon-boxes (leaves room for the bottom-row labels)
const H_GAP = 380;        // gap from the bootstrap group's right edge to the GitHub cluster
const WF_GAP = 185;       // spacing between GitHub workflow-row nodes
const REKOR_GAP = 175;    // spacing between Rekor entries
const REKOR_ABOVE = 120;  // how far above TOP_Y the Rekor row sits

export async function execute(context) {
    const {cy} = context;

    // 1. Measure each AWS cluster's post-arrangement bounding box. includeLabels:
    //    false measures the ICONS only — node labels are wider than the icons and
    //    overhang by different amounts per group, so a label-inclusive box would
    //    left-align the labels (leaving the icons ragged) and inflate the vertical
    //    gaps. Measuring icons gives a true icon left-justify + tight distribution.
    const groups = GROUPS
        .map((g) => ({...g, nodes: cy.nodes().filter(g.sel)}))
        .filter((g) => g.nodes.nonempty())
        .map((g) => ({...g, bb: g.nodes.boundingBox({includeLabels: false})}));

    // 2. Left-align (x1 → LEFT_X) and distribute vertically with even gaps. Shifting
    //    by a delta preserves each cluster's internal arrangement shape.
    let cursorY = TOP_Y;
    for (const g of groups) {
        const dx = LEFT_X - g.bb.x1;
        const dy = cursorY - g.bb.y1;
        g.nodes.positions((n) => ({x: n.position("x") + dx, y: n.position("y") + dy}));
        g.bb = {x1: g.bb.x1 + dx, y1: g.bb.y1 + dy, x2: g.bb.x2 + dx, y2: g.bb.y2 + dy, w: g.bb.w, h: g.bb.h};
        cursorY = g.bb.y2 + V_GAP;
    }

    const bootstrap = groups.find((g) => g.key === "bootstrap");
    const bootRight = bootstrap ? bootstrap.bb.x2 : LEFT_X + 720;
    const bootCenterY = bootstrap ? (bootstrap.bb.y1 + bootstrap.bb.y2) / 2 : cursorY;

    // 3. GitHub cluster — directly to the RIGHT of the (bottom) bootstrap group,
    //    workflows laid out as a horizontal row centered on the bootstrap row's y,
    //    so the repo box is a short bar and FEDERATES_VIA (repo → AWS OIDC provider)
    //    reads as a horizontal line.
    const ghLeftX = bootRight + H_GAP;
    const workflows = cy.nodes('[entity_type="github_workflow"]')
        .sort((a, b) => (a.data("label") || "").localeCompare(b.data("label") || ""));
    workflows.forEach((n, i) => n.position({x: ghLeftX + i * WF_GAP, y: bootCenterY}));

    // 4. OIDC issuer hub — midway in the gap, on the bootstrap row's y so
    //    TRUSTS_ISSUER (AWS provider → issuer) reads horizontal.
    cy.nodes('[entity_type="oidc_issuer"]').forEach((n) => n.position({x: (bootRight + ghLeftX) / 2, y: bootCenterY}));

    // 5. Sigstore Rekor row — centered above the GitHub set; the sigstore_ca
    //    compound (nesting rule below) auto-sizes around it.
    const rekor = cy.nodes('[entity_type="rekor_log_entry"]')
        .sort((a, b) => (a.data("label") || "").localeCompare(b.data("label") || ""));
    if (rekor.nonempty()) {
        const wfBB = workflows.boundingBox();
        const ghCenterX = (wfBB.x1 + wfBB.x2) / 2;
        const rLeft = ghCenterX - ((rekor.length - 1) * REKOR_GAP) / 2;
        rekor.forEach((n, i) => n.position({x: rLeft + i * REKOR_GAP, y: TOP_Y - REKOR_ABOVE}));
    }

    // 6. Compound nesting — boundary > aws_account > aws_*, github.com > account >
    //    repo > workflow, sigstore_ca > rekor entries. Applied after positions
    //    settle so each compound bbox auto-fits its children.
    const {parentByChildId, hiddenEdgeIds, warnings} = resolveNesting(cy, NESTING_RELATIONSHIPS);
    warnings.forEach((w) => console.warn("[landing-finalize nesting]", w.category, w.message));
    Object.entries(parentByChildId).forEach(([childId, parentId]) => {
        const child = cy.getElementById(childId);
        if (child && child.length > 0) child.move({parent: parentId});
    });
    hiddenEdgeIds.forEach((edgeId) => {
        const edge = cy.getElementById(edgeId);
        if (edge && edge.length > 0) edge.addClass(HIDDEN_CONTAINMENT_CLASS);
    });
    // Boundary: outline-only frame (transparent body) around the aws_account compound.
    cy.nodes('[entity_type="boundary"]').style({"background-opacity": 0});

    // 7. Scope boxes — labeled overlays per AWS cluster, drawn from the settled
    //    member positions.
    applyScopeBoxes(cy, SCOPE_BOXES);
}
