/**
 * Samsite landing — finalize / scene-composition pass.
 *
 * Runs LAST in the elevation (after landing-systems.js seeds the AWS cluster
 * roots and the website/compliance per-Component arrangements build their
 * internal 2D shapes; the Deploy & Bootstrap row is laid out + labeled by THIS
 * pass via the adh helper — step 0b). This pass treats each AWS cluster as a GROUP:
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
import {applyStack} from "/static/tap_viz/js/runtime/stack.js";
import {alignDistributeHorizontal} from "/static/tap_viz/js/runtime/align-distribute.js";

// Top→bottom group order. Selectors mirror the arrangement member queries and the
// scope-box filters: AWS resources carry a Component tag; the website group is the
// union of the dns + site components (one story on the landing).
const GROUPS = [
    {key: "website",    label: "Website Serving",    sel: (n) => { const c = (n.data("tags") || {}).Component; return c === "dns" || c === "site"; }},
    {key: "compliance", label: "Compliance Flow",     sel: (n) => (n.data("tags") || {}).Component === "compliance"},
    {key: "bootstrap",  label: "Deploy & Bootstrap",  sel: (n) => (n.data("tags") || {}).Component === "bootstrap"},
];

// Website + compliance keep their post-distribute scope boxes here. Bootstrap's
// titled box is drawn by its adh call (step 0b) — adh both lays out the row AND
// labels it — so it's excluded from this set to avoid a double box.
const SCOPE_BOXES = GROUPS.filter((g) => g.key !== "bootstrap").map((g) => ({label: g.label, filter: g.sel}));

// Same nesting rules as before — parent assignment is position-independent, so it
// runs here once the leaf positions (incl. github + sigstore) are settled.
const NESTING_RELATIONSHIPS = [
    {name: "boundary-contains-account", gryphon: "(parent:boundary)<-[:SCOPED_TO_BOUNDARY]-(child:aws_account)"},
    {name: "account-owns-resource",     dimension_match: {parent_type: "aws_account", dimension: "aws_account"}},
    {name: "platform-hosts-account",    gryphon: "(parent:github_platform)-[:HOSTS_ACCOUNT]->(child:github_account)"},
    {name: "account-owns-repo",         gryphon: "(parent:github_account)-[:OWNS_REPO]->(child:github_repository)"},
    {name: "repo-defines-workflow",     gryphon: "(parent:github_repository)-[:DEFINES_WORKFLOW]->(child:github_workflow)"},
    {name: "ca-contains-entries",       gryphon: "(parent:sigstore_ca)<-[:CERT_ISSUED_BY]-(child:rekor_log_entry)"},
    {name: "host-hosts-document",       gryphon: "(parent:web_host)<-[:HOSTED_BY]-(child:web_document)"},
    // github_app (Dependabot) is enabled on the repo (ENABLED_ON) but belongs at
    // the github.com PLATFORM level, not inside the repo box. The nesting resolver
    // is single-hop and there's no app→platform edge, so it's parented to the
    // platform compound directly in execute() (step 9) rather than via a rule.
];

// Layout constants (canvas units). Tuned for the samsite node-set; iterate visually.
const LEFT_X = 250;       // common left edge for the three AWS groups
const TOP_Y = 160;        // top of the first (website) group
const V_GAP = 48;         // vertical gap between AWS group icon-boxes (leaves room for the bottom-row labels)
const H_GAP = 380;        // gap from the bootstrap group's right edge to the GitHub cluster
const WF_GAP = 140;       // edge-to-edge gap between GitHub workflow-row nodes (adh)
const BOOT_GAP = 160;     // edge-to-edge gap for the Deploy & Bootstrap row (adh)
// Deploy & Bootstrap reads left→right by role: state-lock → tfstate bucket →
// deploy role → OIDC provider (the root, rightmost, nearest GitHub). adh needs
// this explicit order since it's semantic, not alphabetical (sort:false).
const BOOT_TYPE_ORDER = ["aws_dynamodb_table", "aws_s3_bucket", "aws_iam_role", "aws_iam_oidc_provider"];
const REKOR_GAP = 175;    // spacing between Rekor entries
const REKOR_ABOVE = 120;  // how far above TOP_Y the Rekor row sits

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
        "shape": "rectangle",
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

    // 0b. Deploy & Bootstrap row — laid out AND labeled by adh (this replaced the
    //     old per-Component arrangements). Runs BEFORE the group measure (step 1) so
    //     the bootstrap bbox exists for distribution; the titled box is reactive and
    //     follows the group when step 2 shifts it. landing-systems seeds only the
    //     root, so adh is what positions the rest. Ordered by role, not label (so
    //     sort:false) — see BOOT_TYPE_ORDER.
    const bootSel = GROUPS.find((g) => g.key === "bootstrap").sel;
    const bootMembers = cy.nodes().filter(bootSel).toArray().sort((a, b) => {
        const oi = (t) => { const i = BOOT_TYPE_ORDER.indexOf(t); return i < 0 ? 99 : i; };
        return oi(a.data("entity_type")) - oi(b.data("entity_type"));
    });
    if (bootMembers.length) {
        alignDistributeHorizontal(cy, {
            members: bootMembers,
            anchor: {x: LEFT_X, y: 760},
            gap: BOOT_GAP,
            sort: false,
            label: "Deploy & Bootstrap",
        });
    }

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
    // workflows: a clean horizontal row via adh — no label, the github_repository
    // compound box already frames them. Sorted by label (adh default) for a stable
    // left→right order; the row's y is the bootstrap row so FEDERATES_VIA reads flat.
    const workflows = cy.nodes('[entity_type="github_workflow"]');
    alignDistributeHorizontal(cy, {members: workflows, anchor: {x: ghLeftX, y: bootCenterY}, gap: WF_GAP});

    // 4. OIDC issuer (token.actions.githubusercontent.com) — it's a github.com
    //    service, so it's nested INSIDE the github.com platform box alongside the
    //    github_app(s). Positioned + parented in step 9 (after the platform compound
    //    is resolved). Its TRUSTS_ISSUER edge to the AWS provider then crosses the
    //    gap, showing the AWS→GitHub federation trust.

    // 5. Sigstore Rekor entries — collected here; collapsed into a single stack
    //    at the end (step 8), after nesting, so the representative already sits
    //    inside the sigstore_ca compound.
    const rekor = cy.nodes('[entity_type="rekor_log_entry"]')
        .sort((a, b) => (a.data("label") || "").localeCompare(b.data("label") || ""));

    // 5b. Signed files — styled as file cards, then laid out with the adh helper
    //     as a titled row in the blank space to the RIGHT of the Website Serving
    //     cluster, inside the boundary (they're eventually written there, so it's
    //     philosophically in-scope). Style first so the box wraps the final sizes.
    if (files.nonempty()) {
        files.forEach(styleFileNode);
        const websiteBB = (groups.find((g) => g.key === "website") || {}).bb;
        if (websiteBB) {
            const ARTIFACT_STEP = 16;  // staircase down-right so the filename labels stop overlapping
            // Center the staircase's vertical span on the website block's center
            // (lift the start by half the total drop) so the set reads as aligned
            // with Website Serving rather than drooping below it.
            const websiteCenterY = (websiteBB.y1 + websiteBB.y2) / 2;
            const startY = websiteCenterY - (ARTIFACT_STEP * (files.length - 1)) / 2;
            // Sit the same distance to the RIGHT of the website box as the website
            // box sits ABOVE the compliance box. The inter-group vertical gap is
            // V_GAP (icon-bbox to icon-bbox), and every scope box shares the same
            // padding, so an equal icon-bbox gap on x yields an equal visual box gap.
            alignDistributeHorizontal(cy, {
                members: files,
                anchor: {x: websiteBB.x2 + V_GAP, y: startY},
                gap: 26,
                step: ARTIFACT_STEP,
                stepFrom: "left",  // left card is highest; each one to the right drops a step
                label: "Signed Artifacts",
            });
        }
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

    const wfBB = workflows.boundingBox();
    const ghCenterX = (wfBB.x1 + wfBB.x2) / 2;

    // 8. Collapse the Rekor transparency-log entries into a single stack (the
    //    tap_viz stack primitive). Run LAST — after nesting + scope boxes — so the
    //    representative is already a child of the sigstore_ca compound; the depth
    //    cards join the same box and it auto-sizes around the compact pile instead
    //    of a wide row. The count chip carries the true count; members'
    //    SIGNED_BY_IDENTITY / IDENTITY_VOUCHED_BY edges dedup onto the
    //    representative and the files' ATTESTED_BY edges re-point onto it.
    //    Positioned at the Sigstore slot (top-right, centered above the GitHub set).
    if (rekor.nonempty()) {
        // direction defaults to "auto" — the projection runtime resolves it in
        // settleStacks() after every layout has run, so it correctly reads this
        // stack as upper-right and fans up-right (no longer skewed by step 9's
        // not-yet-placed actors / github_app / CISA at applyStack time).
        applyStack(cy, {
            members: rekor,
            representative: rekor.first(),
            position: {x: ghCenterX, y: TOP_Y - REKOR_ABOVE},
            label: "Rekor Entries",
        });
    }

    // 9. Threaded-in node types from the merge — anchored to the parts of the
    //    system they relate to.

    // github_app (Dependabot) + the oidc_issuer (token.actions.githubusercontent.com)
    // → github.com BACK-END SERVICES: nested inside the platform box in a row BELOW
    // the notgeorge account + its repo (the user-facing front; these two sit beneath
    // it). No service→account edge exists for a nesting rule and the resolver is
    // single-hop, so parent them to the platform compound directly — the box grows
    // down to wrap them under the account. The issuer is on the LEFT, closest to the
    // box edge, so its TRUSTS_ISSUER hop across to the AWS account and the up-hop to
    // Sigstore stay short.
    const platform = cy.nodes('[entity_type="github_platform"]').first();
    const account = cy.nodes('[entity_type="github_account"]').first();
    if (platform.nonempty() && account.nonempty()) {
        // Anchor below the notgeorge account compound (which wraps repo + workflows).
        const frontBB = account.boundingBox();
        const appRowY = frontBB.y2 + 80;
        const leftX = frontBB.x1 + 30;
        // Issuer pinned far-left (static) — closest to the box edge for its hops out
        // to AWS / up to Sigstore.
        cy.nodes('[entity_type="oidc_issuer"]').forEach((n) => {
            n.position({x: leftX, y: appRowY});
            n.move({parent: platform.id()});
        });
        // Dependabot centered on the account — but the account's box settles a few px
        // after this pass (post-layout reflow), so a center computed here lands off.
        // adh's anchorNode re-resolves on the account's "bounds"/"position" events
        // (like applyScopeBoxes tracks its members), keeping it dead-centered through
        // the settle. Cross-axis pinned to the shared row y via `anchor.y`.
        const apps = cy.nodes('[entity_type="github_app"]');
        apps.forEach((a) => a.move({parent: platform.id()}));
        alignDistributeHorizontal(cy, {
            members: apps,
            anchorNode: account,
            anchorMode: "center",
            anchor: {y: appRowY},
        });
    }

    // Both github.com services carry their title bottom-center (the issuer's model
    // default is top/center; github_app inherits a baked default). Drive it through
    // the standard label-position data fields so the node[label_valign][label_halign]
    // rule applies it.
    cy.nodes('[entity_type="oidc_issuer"], [entity_type="github_app"]').forEach((n) => {
        n.data("label_valign", "bottom");
        n.data("label_halign", "center");
        n.data("label_margin_y", 4);
    });

    // Human actors — anchored OUTSIDE the boundary they work on, at a consistent
    // gap (the "outside but still working on it" distance). Sam sits OUTSIDE_GAP
    // right of the github.com box; Readers / george sit the same gap outside the
    // FedRAMP boundary, aligned with the system part they touch.
    const OUTSIDE_GAP = 130;
    const userByName = (re) => cy.nodes('[entity_type="user"]').filter((n) => re.test(n.data("label") || ""));
    const boundary = cy.nodes('[entity_type="boundary"]').first();
    const bndBB = boundary.nonempty() ? boundary.boundingBox() : null;
    // Readers → left of the boundary, level with the CloudFront CDN they read from.
    const cf = cy.nodes('[entity_type="aws_cloudfront_distribution"]').first();
    if (cf.nonempty() && bndBB) userByName(/reader/i).forEach((n) => n.position({x: bndBB.x1 - OUTSIDE_GAP, y: cf.position("y")}));
    // george → below the boundary, under the bootstrap tfstate S3 bucket he manages.
    const tfstate = cy.nodes('[entity_type="aws_s3_bucket"]')
        .filter((n) => (n.data("tags") || {}).Component === "bootstrap").first();
    if (tfstate.nonempty() && bndBB) userByName(/george/i).forEach((n) => n.position({x: tfstate.position("x"), y: bndBB.y2 + OUTSIDE_GAP}));
    // Sam → right of the github.com box (recompute its bbox now the app is inside).
    if (platform.nonempty()) {
        const ghBB = platform.boundingBox();
        userByName(/sam/i).forEach((n) => n.position({x: ghBB.x2 + OUTSIDE_GAP, y: (ghBB.y1 + ghBB.y2) / 2}));
    }

    // CISA (web_host) contains the KEV catalog (web_document, nested via the
    // host-hosts-document rule). Position the catalog to the right of the Sigstore
    // box — CISA, the compound that auto-wraps it, then sits right of Sigstore.
    const sigCa = cy.nodes('[entity_type="sigstore_ca"]').first();
    const kevDoc = cy.nodes('[entity_type="web_document"]').first();
    if (sigCa.nonempty() && kevDoc.nonempty()) {
        const sb = sigCa.boundingBox();
        kevDoc.position({x: sb.x2 + 180, y: (sb.y1 + sb.y2) / 2});
    }

    // 10. Z-order: the IDENTITY_VOUCHED_BY edges run from the Rekor entries down to
    //     the OIDC issuer, crossing the notgeorge account + repo boxes on the way.
    //     Sink them beneath everything (z-compound-depth "bottom") so they tuck
    //     BEHIND the opaque account/repo boxes instead of drawing across their faces.
    //     That also drops them below the github.com platform box, so render that box
    //     outline-only (transparent body, the same treatment as the FedRAMP boundary
    //     — and its near-bg fill was barely visible anyway). The sunk edge then shows
    //     THROUGH github.com, keeping its connection to the issuer visible, while the
    //     filled account/repo boxes still occlude it. (The edge label is the edge type.)
    cy.edges('[label="IDENTITY_VOUCHED_BY"]').style({"z-compound-depth": "bottom"});
    cy.nodes('[entity_type="github_platform"]').style({"background-opacity": 0});
}
