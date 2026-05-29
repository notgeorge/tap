/**
 * tap_viz runtime: align-distribute helpers.
 *
 * Lay out a caller-supplied set of nodes in a clean, evenly-spaced line —
 * aligned on the cross axis, distributed along the main axis with a configurable
 * gap. A standalone companion to the `align-distribute-vertical` *natural layout*
 * in nested-projection.js (which arranges a compound's children); these operate
 * on any node set, no container required.
 *
 * Two modes, one helper:
 *   - "just make them pretty" — pass a node set; they're aligned + distributed.
 *   - "give it a label" — pass `label`; a titled box is drawn around the group
 *     (reusing the scope-box overlay), e.g. "Deploy & Bootstrap". Omit `label`
 *     when the group already sits in a titled container (e.g. a repo's workflows,
 *     which just want clean distribution inside the repo box).
 *
 * Spec: tap_viz/specs/spec-viz-align-distribute.md
 */

import {applyScopeBoxes} from "./layout-scope-boxes.js";

const DEFAULT_GAP = 24;

function _toNodeArray(members) {
    if (!members) return [];
    if (typeof members.toArray === "function") return members.toArray();
    return Array.from(members);
}

/**
 * @param {cytoscape.Core} cy
 * @param {Object} opts
 * @param {cytoscape.Collection|Array} opts.members  Nodes to lay out.
 * @param {{x:number,y:number}} [opts.anchor]  Reference point (see anchorMode);
 *   defaults to the first member's current position. When `anchorNode` is set this
 *   only supplies a cross-axis override (e.g. `{y: rowY}` for a horizontal row).
 * @param {cytoscape.Collection} [opts.anchorNode]  Anchor on a NODE's live bounding
 *   box instead of a static point: the row's main-axis center tracks the node's
 *   bbox center (cross-axis from `anchor` if given, else the node's bbox center),
 *   and — unless `reactive: false` — re-resolves on the node's "position"/"bounds"
 *   and the cy "layoutstop", so it stays put through post-layout reflows (badges,
 *   stack settle) and drags. The node must NOT be an ancestor of any member (that
 *   would feedback-loop). Implies anchorMode "center".
 * @param {{x:number,y:number}} [opts.offset]  Added to the resolved anchor point —
 *   e.g. `{x:0, y:80}` to drop the row below the anchor node.
 * @param {boolean} [opts.reactive=true]  When `anchorNode` is set, re-resolve on
 *   its events (set false for a one-shot snapshot).
 * @param {string} [opts.anchorMode="start"]  "start" — anchor is the leading
 *   (left/top) edge and the line grows from it; "center" — anchor is the midpoint.
 *   Defaults to "center" when `anchorNode` is set.
 * @param {number} [opts.gap]  Edge-to-edge spacing between nodes (px). Alias:
 *   opts.spacing. Default 24.
 * @param {boolean} [opts.sort=true]  Sort members by label first (false keeps
 *   caller order).
 * @param {number} [opts.step=0]  Cross-axis offset added per successive node — a
 *   staircase. For a horizontal row this is a downward drop per node (so labels
 *   below each node stagger and stop overlapping). 0 = a flat line (default).
 * @param {string} [opts.stepFrom]  Which end is the staircase baseline (the
 *   un-stepped end the cascade descends away from): "left"/"right" for horizontal
 *   (default "left"), "top"/"bottom" for vertical (default "top"). Only meaningful
 *   when step != 0.
 * @param {string} [opts.label]  Optional — draw a titled box around the group.
 * @param {Object} [opts.style]  Optional scope-box style override (when labeled).
 * @returns {{destroy: Function, members: Array}}
 */
function _alignDistribute(cy, opts, axis) {
    const members = _toNodeArray(opts.members).filter((n) => n && n.length > 0 && n.isNode());
    if (members.length === 0) return {destroy: () => {}, members: []};

    const gap = opts.gap != null ? opts.gap : opts.spacing != null ? opts.spacing : DEFAULT_GAP;
    const main = axis; // "x" for horizontal, "y" for vertical
    const cross = axis === "x" ? "y" : "x";
    const sizeMain = (n) => (axis === "x" ? n.width() : n.height());
    const offset = opts.offset || {};

    const anchorNode = opts.anchorNode && opts.anchorNode.nonempty && opts.anchorNode.nonempty() ? opts.anchorNode : null;
    const anchorMode = opts.anchorMode || (anchorNode ? "center" : "start");

    const step = opts.step != null ? opts.step : 0;
    // The baseline is the "start" end; nodes step away from it. ordered[] runs in
    // increasing main-axis position (left→right / top→bottom), so the far end is
    // "right"/"bottom".
    const stepFromFar =
        (axis === "x" && opts.stepFrom === "right") || (axis === "y" && opts.stepFrom === "bottom");

    const ordered =
        opts.sort === false
            ? members
            : [...members].sort((a, b) => (a.data("label") || "").localeCompare(b.data("label") || ""));

    // Resolve the anchor point. For a static anchor it's `opts.anchor` (or the first
    // member's position); for an anchorNode it's that node's live bbox center, with
    // an optional cross-axis override from `opts.anchor`. `offset` nudges either.
    function resolveAnchor() {
        let pt;
        if (anchorNode) {
            const bb = anchorNode.boundingBox();
            pt = {x: (bb.x1 + bb.x2) / 2, y: (bb.y1 + bb.y2) / 2};
            if (opts.anchor && opts.anchor[cross] != null) pt[cross] = opts.anchor[cross];
        } else {
            pt = {...(opts.anchor || ordered[0].position())};
        }
        if (offset.x != null) pt.x += offset.x;
        if (offset.y != null) pt.y += offset.y;
        return pt;
    }

    // Distribute along the main axis (edge-to-edge gap), aligned on the cross axis
    // (optionally stepped into a staircase via `step` + `stepFrom`).
    function place(anchor) {
        const totalMain = ordered.reduce((s, n) => s + sizeMain(n), 0) + gap * (ordered.length - 1);
        let cursor = anchorMode === "center" ? anchor[main] - totalMain / 2 : anchor[main];
        const last = ordered.length - 1;
        ordered.forEach((n, i) => {
            const half = sizeMain(n) / 2;
            const stepIndex = stepFromFar ? last - i : i;
            const pos = {};
            pos[main] = cursor + half;
            pos[cross] = anchor[cross] + step * stepIndex;
            n.position(pos);
            cursor += sizeMain(n) + gap;
        });
    }

    place(resolveAnchor());

    // Reactive anchor: re-resolve whenever the anchor node moves or its bbox changes
    // (post-layout badge/stack reflow, drags), mirroring how applyScopeBoxes tracks
    // its members. Loop-safe only when no member is a descendant of the anchor node;
    // skip + warn otherwise (moving such a member would re-fire the anchor's bounds).
    let unbind = () => {};
    if (anchorNode && opts.reactive !== false) {
        const descendantMember = ordered.some((n) => n.ancestors().anySame(anchorNode));
        if (descendantMember) {
            console.warn("[align-distribute] anchorNode is an ancestor of a member; skipping reactive bind (would loop).");
        } else {
            // Bind plain (un-namespaced) events and unbind by handler reference —
            // Cytoscape's node.on() does NOT honor event namespaces for
            // position/bounds, so a namespaced handler silently never fires.
            const reResolve = () => place(resolveAnchor());
            anchorNode.on("position bounds", reResolve);
            cy.on("layoutstop", reResolve);
            unbind = () => {
                anchorNode.off("position bounds", reResolve);
                cy.off("layoutstop", reResolve);
            };
        }
    }

    // Optional titled box around the group (reuses the scope-box overlay, which
    // is additive — it never clobbers other scope boxes). It carries its own
    // position/bounds listeners, so it follows the members on every re-resolve.
    let box = {destroy: () => {}};
    if (opts.label) {
        const ids = new Set(ordered.map((n) => n.id()));
        box = applyScopeBoxes(cy, [{label: opts.label, filter: (n) => ids.has(n.id()), style: opts.style}]);
    }

    return {
        destroy: () => {
            unbind();
            box.destroy();
        },
        members: ordered,
    };
}

export function alignDistributeHorizontal(cy, opts = {}) {
    return _alignDistribute(cy, opts, "x");
}

export function alignDistributeVertical(cy, opts = {}) {
    return _alignDistribute(cy, opts, "y");
}
