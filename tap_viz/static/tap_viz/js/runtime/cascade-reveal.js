/**
 * cascade-reveal.js — Staged node reveal for TAP Viz.
 *
 * After layout completes, nodes are hidden and then revealed layer by layer
 * from lowest z-index (outermost containers) to highest (deepest leaves).
 * Within each layer, individual nodes fade in at slightly staggered times
 * to create a "bubbling up" effect. Edges fade in together after all nodes
 * are revealed.
 *
 * Usage:
 *   await cascadeReveal(cy, { layerDelay: 200, staggerRange: 120, fadeDuration: 300 });
 *
 * Spec: tap_viz/specs/spec-viz-projection.md (presentation concern, no dedicated spec)
 */

/**
 * @param {cytoscape.Core} cy
 * @param {Object} [opts]
 * @param {number} [opts.layerDelay=200] - ms between each depth layer starting its reveal.
 * @param {number} [opts.staggerRange=120] - ms random spread for individual nodes within a layer.
 * @param {number} [opts.fadeDuration=300] - ms for each node's opacity transition.
 * @returns {Promise<void>} Resolves when the full cascade is complete.
 */
export function cascadeReveal(cy, opts = {}) {
    const layerDelay = opts.layerDelay ?? 200;
    const staggerRange = opts.staggerRange ?? 120;
    const fadeDuration = opts.fadeDuration ?? 300;

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
    cy.edges().style("opacity", 0);
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
                    // Fade in the badge alongside its host node.
                    const badge = cy.getElementById("badge:" + node.id());
                    if (badge.length > 0) {
                        badge.animate(
                            {style: {opacity: 1}},
                            {duration: fadeDuration, easing: "ease-out"}
                        );
                    }
                }, nodeStart);
            });
        });

        // Edges fade in after all nodes.
        const edgeStart = totalTime + 50;
        setTimeout(() => {
            cy.edges(":visible").forEach((e) => {
                // Shadow links have their own reduced opacity from styles.
                const targetOpacity = e.data("_is_shadow_link") ? 1 : 1;
                e.animate(
                    {style: {opacity: targetOpacity}},
                    {duration: fadeDuration, easing: "ease-out"}
                );
            });
        }, edgeStart);

        // Resolve after everything is done.
        setTimeout(resolve, edgeStart + fadeDuration + 50);
    });
}
