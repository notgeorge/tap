/**
 * badge-nodes.js — Type icon badge rendering for TAP Viz.
 *
 * Creates small satellite Cytoscape nodes that sit at the upper-left corner
 * of each host node, protruding from the body. The badge displays the node's
 * type icon while the host node body is freed for its text label.
 *
 * Badge nodes are real Cytoscape nodes (not HTML overlays) so they scale
 * with zoom naturally. They are non-interactive ("events": "no" in style)
 * and excluded from layout algorithms.
 *
 * Spec: tap_viz/specs/spec-viz-badges-BACKLOG.md
 */

const BADGE_ID_PREFIX = "badge:";

/**
 * Compute the uniform badge diameter for a collection of host nodes using
 * the "smallest host wins" rule. Exported so status badges can share the
 * same diameter as type icon badges at a given elevation.
 *
 * @param {cytoscape.Collection} hosts
 * @param {Object} [opts]
 * @param {number} [opts.badgeRatio=0.35]
 * @param {number} [opts.minBadgeSize=24]
 * @returns {number}
 */
export function computeUniformBadgeSize(hosts, opts = {}) {
    const badgeRatio = opts.badgeRatio || 0.35;
    const minBadgeSize = opts.minBadgeSize || 24;
    let smallestMin = Infinity;
    hosts.forEach((host) => {
        const w = host.width();
        const h = host.height();
        const hostMin = Math.min(w, h);
        if (hostMin > 0 && hostMin < smallestMin) smallestMin = hostMin;
    });
    return smallestMin === Infinity
        ? minBadgeSize
        : Math.max(minBadgeSize, smallestMin * badgeRatio);
}

/**
 * Apply type icon badges to all visible nodes that have an icon_url.
 *
 * Call this AFTER layout completes so host node positions and dimensions
 * are stable.
 *
 * @param {cytoscape.Core} cy
 * @param {Object} [opts]
 * @param {number} [opts.badgeRatio=0.35] Badge diameter as fraction of the smallest host's shorter dimension.
 * @param {number} [opts.minBadgeSize=24] Minimum uniform badge diameter in model units.
 * @param {string[]} [opts.excludeTypes=[]] Entity types to skip (no badge; icon stays on node body).
 * @returns {{ destroy: Function, uniformBadgeSize: number }} Cleanup handle + computed diameter.
 */
export function applyBadgeNodes(cy, opts = {}) {
    // Clean up any previous badge pass.
    _removeBadges(cy);

    const excludeSet = new Set(opts.excludeTypes || []);

    // Collect host nodes that qualify for a badge.
    const hosts = cy.nodes().filter((n) => {
        const url = n.data("icon_url");
        if (!url || url === "" || n.data("_is_badge")) return false;
        if (excludeSet.size > 0 && excludeSet.has(n.data("entity_type"))) return false;
        return true;
    });

    // Excluded types: clear icon so the node renders as a plain colored shape.
    if (excludeSet.size > 0) {
        cy.nodes().forEach((n) => {
            if (n.data("_is_badge") || !excludeSet.has(n.data("entity_type"))) return;
            const url = n.data("icon_url");
            if (url && url !== "") {
                n.data("_original_icon_url", url);
                n.data("icon_url", "");
                n.data("_badge_excluded", true);
            }
        });
    }

    if (hosts.length === 0) {
        return {destroy: () => _removeBadges(cy), uniformBadgeSize: 0};
    }

    const uniformBadgeSize = computeUniformBadgeSize(hosts, opts);

    const badgeElements = [];

    hosts.forEach((host) => {
        const hostId = host.id();
        const iconUrl = host.data("icon_url");

        // Stash original icon so it can be restored on cleanup.
        host.data("_original_icon_url", iconUrl);
        // Clear icon from host so the background-image style stops applying.
        host.data("icon_url", "");
        // Mark host so the _badge_active style selector applies.
        host.data("_badge_active", true);

        const pos = host.position();
        const w = host.width();
        const h = host.height();

        // Upper-left corner: badge center sits at the host's top-left corner
        // so it protrudes equally inside and outside.
        const bx = pos.x - w / 2;
        const by = pos.y - h / 2;

        badgeElements.push({
            group: "nodes",
            data: {
                id: BADGE_ID_PREFIX + hostId,
                icon_url: iconUrl,
                _is_badge: true,
                _badge_host: hostId,
            },
            position: {x: bx, y: by},
            locked: true,
        });
    });

    cy.add(badgeElements);

    // Apply the uniform size (width/height are style properties on the node).
    hosts.forEach((host) => {
        const badge = cy.getElementById(BADGE_ID_PREFIX + host.id());
        if (badge.length === 0) return;
        badge.style({width: uniformBadgeSize, height: uniformBadgeSize});
    });

    // Position listener: when a host node moves, reposition its badge.
    function onHostPosition(evt) {
        const host = evt.target;
        if (host.data("_is_badge")) return;
        const badge = cy.getElementById(BADGE_ID_PREFIX + host.id());
        if (badge.length === 0) return;
        const pos = host.position();
        const w = host.width();
        const h = host.height();
        badge.unlock();
        badge.position({x: pos.x - w / 2, y: pos.y - h / 2});
        badge.lock();
    }
    cy.on("position", "node[_badge_active]", onHostPosition);

    return {
        destroy: () => {
            cy.off("position", "node[_badge_active]", onHostPosition);
            _removeBadges(cy);
        },
        uniformBadgeSize,
    };
}

/**
 * Remove all badge nodes and restore host node icon data.
 */
function _removeBadges(cy) {
    // Restore stashed icons on hosts.
    cy.nodes("[_badge_active]").forEach((host) => {
        const original = host.data("_original_icon_url");
        if (original) {
            host.data("icon_url", original);
        }
        host.removeData("_original_icon_url");
        host.removeData("_badge_active");
    });

    // Restore stashed icons on excluded-type nodes.
    cy.nodes("[_badge_excluded]").forEach((n) => {
        const original = n.data("_original_icon_url");
        if (original) {
            n.data("icon_url", original);
        }
        n.removeData("_original_icon_url");
        n.removeData("_badge_excluded");
    });

    // Remove badge nodes.
    cy.nodes("[_is_badge]").remove();
}
