/**
 * cascade-reveal.js — Staged node reveal for TAP Viz.
 *
 * After layout completes, nodes are hidden and then revealed layer by layer
 * from lowest z-index (outermost containers) to highest (deepest leaves).
 * Within each layer, individual nodes fade in at slightly staggered times
 * to create a "bubbling up" effect. Edges fade in together after all nodes
 * are revealed.
 *
 * After the nodes, edges fade in one by one at staggered times (not all at
 * once) so the wiring "draws in" — the same bubbling feel as the nodes.
 *
 * Usage:
 *   await cascadeReveal(cy, { layerDelay: 200, staggerRange: 120, fadeDuration: 300 });
 *
 * Spec: tap_viz/specs/spec-viz-projection.md (presentation concern, no dedicated spec)
 */

/**
 * @param {cytoscape.Core} cy
 * @param {Object} [opts]
 * @param {number} [opts.layerDelay=100] - ms between each depth layer starting its reveal.
 * @param {number} [opts.staggerRange=60] - ms random spread for individual nodes within a layer.
 * @param {number} [opts.fadeDuration=150] - ms for each node's opacity transition.
 * @param {number} [opts.edgeStaggerRange=200] - ms random spread for individual edges (after the nodes).
 * @returns {Promise<void>} Resolves when the full cascade is complete.
 */
export function cascadeReveal(cy, opts = {}) {
    const layerDelay = opts.layerDelay ?? 100;
    const staggerRange = opts.staggerRange ?? 60;
    const fadeDuration = opts.fadeDuration ?? 150;
    const edgeStaggerRange = opts.edgeStaggerRange ?? 200;

    // Collect visible nodes grouped by z-index.
    // Badge nodes are excluded — they fade in with their host node.
    const layerMap = {};
    cy.nodes(":visible").forEach((n) => {
        if (n.data("_is_badge")) return;
        const z = parseInt(n.style("z-index"), 10) || 0;
        if (!layerMap[z]) layerMap[z] = [];
        layerMap[z].push(n);
    });

    const zLevels = Object.keys(layerMap).map(Number).sort((a, b) => a - b);
    if (zLevels.length === 0) {
        cy.container().style.visibility = "";
        return Promise.resolve();
    }

    // Set all elements to transparent, then unhide the canvas.
    // This avoids a flash: the canvas becomes visible but everything
    // on it is opacity 0, then the cascade animates them in.
    cy.nodes().style("opacity", 0);
    // Use a near-zero opacity instead of 0 so edges remain :visible
    // in Cytoscape's selector engine. Cytoscape treats opacity:0 elements
    // as :hidden, which prevents the edge fade-in from finding them.
    cy.edges().style("opacity", 0.001);
    cy.container().style.visibility = "";

    return new Promise((resolve) => {
        let totalTime = 0;

        zLevels.forEach((z, layerIdx) => {
            const nodes = layerMap[z];
            const layerStart = layerIdx * layerDelay;

            nodes.forEach((node) => {
                const stagger = Math.random() * staggerRange;
                const nodeStart = layerStart + stagger;
                const nodeEnd = nodeStart + fadeDuration;
                if (nodeEnd > totalTime) totalTime = nodeEnd;

                setTimeout(() => {
                    const targetOpacity = node.data("_is_shadow") ? 0.5 : 1;
                    node.animate(
                        {style: {opacity: targetOpacity}},
                        {duration: fadeDuration, easing: "ease-out"}
                    );
                    // Fade in the type icon badge alongside its host node.
                    const badge = cy.getElementById("badge:" + node.id());
                    if (badge.length > 0) {
                        badge.animate(
                            {style: {opacity: 1}},
                            {duration: fadeDuration, easing: "ease-out"}
                        );
                    }
                    // Fade in status badges alongside their host node.
                    const statusBadges = cy.nodes(`[_status_host = "${node.id()}"]`);
                    if (statusBadges.length > 0) {
                        statusBadges.animate(
                            {style: {opacity: 1}},
                            {duration: fadeDuration, easing: "ease-out"}
                        );
                    }
                }, nodeStart);
            });
        });

        // Edges fade in after all nodes, each at its own staggered time so the
        // wiring draws in one by one rather than snapping on all at once —
        // mirroring the per-node stagger above.
        const edgeBaseStart = totalTime + 50;
        let lastEdgeEnd = edgeBaseStart + fadeDuration;
        cy.edges(":visible").forEach((e) => {
            const edgeStart = edgeBaseStart + Math.random() * edgeStaggerRange;
            const edgeEnd = edgeStart + fadeDuration;
            if (edgeEnd > lastEdgeEnd) lastEdgeEnd = edgeEnd;
            setTimeout(() => {
                e.animate(
                    {style: {opacity: 1}},
                    {duration: fadeDuration, easing: "ease-out"}
                );
            }, edgeStart);
        });

        // Resolve after the last edge finishes.
        setTimeout(resolve, lastEdgeEnd + 50);
    });
}
