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
 *   defaults to the first member's current position.
 * @param {string} [opts.anchorMode="start"]  "start" — anchor is the leading
 *   (left/top) edge and the line grows from it; "center" — anchor is the midpoint.
 * @param {number} [opts.gap]  Edge-to-edge spacing between nodes (px). Alias:
 *   opts.spacing. Default 24.
 * @param {boolean} [opts.sort=true]  Sort members by label first (false keeps
 *   caller order).
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
    const anchor = opts.anchor || members[0].position();

    const ordered =
        opts.sort === false
            ? members
            : [...members].sort((a, b) => (a.data("label") || "").localeCompare(b.data("label") || ""));

    // Distribute along the main axis (edge-to-edge gap), aligned on the cross axis.
    const totalMain = ordered.reduce((s, n) => s + sizeMain(n), 0) + gap * (ordered.length - 1);
    let cursor = opts.anchorMode === "center" ? anchor[main] - totalMain / 2 : anchor[main];
    ordered.forEach((n) => {
        const half = sizeMain(n) / 2;
        const pos = {};
        pos[main] = cursor + half;
        pos[cross] = anchor[cross];
        n.position(pos);
        cursor += sizeMain(n) + gap;
    });

    // Optional titled box around the group (reuses the scope-box overlay, which
    // is additive — it never clobbers other scope boxes).
    let box = {destroy: () => {}};
    if (opts.label) {
        const ids = new Set(ordered.map((n) => n.id()));
        box = applyScopeBoxes(cy, [{label: opts.label, filter: (n) => ids.has(n.id()), style: opts.style}]);
    }

    return {destroy: () => box.destroy(), members: ordered};
}

export function alignDistributeHorizontal(cy, opts = {}) {
    return _alignDistribute(cy, opts, "x");
}

export function alignDistributeVertical(cy, opts = {}) {
    return _alignDistribute(cy, opts, "y");
}
