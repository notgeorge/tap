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
const FILE_GAP = 180;     // spacing between the signed-file nodes

// The signed /.well-known/ artifacts ("files"). The collector mints a new
// timestamped node per run, so the grid accumulates snapshots; the landing shows
// only the latest of each. Dedicated computing_core.file nodes + history are a
// deferred "storage" question — for now these existing domain nodes are the files.
const FILE_TYPES = ["ksi_signal", "vdr_report", "compliance_artifact"];

// Parse a file node's display name, shaped "<head> @ <iso-timestamp>". The graph
// only carries name + entity_type + tags + dimensions onto cy node data (per
// panel-graph.js) — per-model fields like kind / source_url / fetched_at are NOT
// lifted — so the name is the one place the kind + snapshot time are available
// client-side. head examples: "oscal_ssp", "KSI signal <uuid>", "VDR report <id>".
function _parseName(n) {
    const raw = n.data("label") || "";
    const at = raw.lastIndexOf(" @ ");
    if (at === -1) return {head: raw.trim(), ts: 0};
    const ts = Date.parse(raw.slice(at + 3).trim());
    return {head: raw.slice(0, at).trim(), ts: isNaN(ts) ? 0 : ts};
}
function _artifactTs(n) { return _parseName(n).ts; }

// Remove all but the latest snapshot of each signed file. Group key is the type,
// plus data.kind for compliance_artifact (oscal_ssp / oscal_poam / iiw). Returns
// the surviving (latest) file nodes.
function pruneToLatestFiles(cy) {
    const groups = {};
    cy.nodes().filter((n) => FILE_TYPES.includes(n.data("entity_type"))).forEach((n) => {
        const t = n.data("entity_type");
        const key = t === "compliance_artifact" ? `${t}:${_parseName(n).head}` : t;
        (groups[key] = groups[key] || []).push(n);
    });
    const stale = [];
    Object.values(groups).forEach((arr) => {
        arr.sort((a, b) => _artifactTs(b) - _artifactTs(a));
        stale.push(...arr.slice(1));
    });
    if (stale.length) cy.remove(cy.collection(stale));
    return cy.nodes().filter((n) => FILE_TYPES.includes(n.data("entity_type")));
}

// Generic file icon — the signed artifacts are different domain types
// (ksi_signal / vdr_report / compliance_artifact) but all play the "file" role
// on this board, so we standardize them onto one icon + rounded-rectangle.
const FILE_ICON_URL = "/static/computing_core/icons/file.svg";

// Short, readable label: the artifact's filename. Prefer the real source_url
// basename; fall back to a type/kind → filename map so the board shows
// "oscal-ssp.json" rather than "oscal_ssp @ 2026-05-29T01:15:21.525309Z".
const _FILE_NAME_BY_KIND = {oscal_ssp: "oscal-ssp.json", oscal_poam: "oscal-poam.json", iiw: "iiw.csv"};
function shortFileLabel(n) {
    const t = n.data("entity_type");
    const head = _parseName(n).head;
    if (t === "compliance_artifact") return _FILE_NAME_BY_KIND[head] || head || "artifact";
    if (t === "ksi_signal") return "ksi-signal.json";
    if (t === "vdr_report") return "vdr-report.json";
    return head || t;
}

// Standardize a signed-file node: rounded-rectangle, generic file icon, short label.
function styleFileNode(n) {
    n.data("label", shortFileLabel(n));
    n.style({
        "shape": "round-rectangle",
        "width": 46,
        "height": 38,
        "background-color": "#F1ECDD",
        "border-color": "#A99A63",
        "border-width": 1.5,
        "background-image": FILE_ICON_URL,
        "background-fit": "contain",
        "background-width": "62%",
        "background-height": "62%",
        "background-position-x": "50%",
        "background-position-y": "50%",
    });
}

export async function execute(context) {
    const {cy} = context;

    // 0. Prune signed-file snapshots down to the latest of each (kept for
    //    positioning in step 5b). Done first so the stale dupes never reach layout.
    const files = pruneToLatestFiles(cy);

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

    // 5b. Signed files — the latest snapshot of each, in a row in the right-middle
    //     between the Rekor row (above) and the GitHub deploy cluster (below), so
    //     the workflow ─GENERATES_FILE▶ file ◀─ATTESTED_BY─ rekor story reads
    //     vertically on the right. (Positions iterate; eyes-on placement.)
    if (files.nonempty()) {
        const wfBB = workflows.boundingBox();
        const ghCenterX = (wfBB.x1 + wfBB.x2) / 2;
        const fileY = (TOP_Y - REKOR_ABOVE + bootCenterY) / 2;
        const arr = files.sort((a, b) => (a.data("name") || "").localeCompare(b.data("name") || ""));
        const fLeft = ghCenterX - ((arr.length - 1) * FILE_GAP) / 2;
        arr.forEach((n, i) => {
            n.position({x: fLeft + i * FILE_GAP, y: fileY});
            styleFileNode(n);
        });
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
