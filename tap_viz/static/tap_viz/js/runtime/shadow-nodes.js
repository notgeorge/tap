/**
 * shadow-nodes.js — Shadow node system for TAP Viz.
 *
 * Multi-homed entities (e.g. RDS instances spanning subnets) are represented
 * with a single primary node at their natural nesting level and lightweight
 * shadow copies inside each location where the entity has a presence.
 *
 * Call createShadows() BEFORE projectNested so shadow nodes participate in
 * nesting resolution and influence parent sizing. Call initShadowInteraction()
 * AFTER layout completes to wire up hover highlighting.
 *
 * Spec: tap_viz/specs/spec-viz-shadows.md
 */

const SHADOW_ID_PREFIX = "shadow:";
const SHADOW_LINK_PREFIX = "shadow-link:";
const SHADOW_EDGE_PREFIX = "shadow-edge:";

/**
 * Create shadow nodes, placement edges, and visual links for multi-homed
 * entities. Must be called BEFORE projectNested so shadows participate in
 * nesting resolution.
 *
 * @param {cytoscape.Core} cy
 * @param {Object} config
 * @param {string[]} config.entityTypes - Entity types that produce shadows.
 * @param {string} config.edgeType - Edge type that connects entities to
 *   their host containers (e.g. "RESIDES_IN").
 * @param {string} config.placementEdgeType - Synthetic edge type for nesting
 *   resolution (e.g. "_SHADOW_PLACEMENT").
 * @returns {{ shadowGroups: Object }} Map of primary ID -> [shadow IDs].
 */
export function createShadows(cy, config) {
    const {entityTypes, edgeType, placementEdgeType} = config;
    const shadowGroups = {};

    entityTypes.forEach((type) => {
        cy.nodes(`[entity_type="${type}"]`).forEach((primary) => {
            const primaryId = primary.id();

            // Find all outbound edges of the specified type.
            const locationEdges = primary
                .connectedEdges()
                .filter(
                    (e) =>
                        e.source().id() === primaryId &&
                        (e.data("label") === edgeType || e.data("edge_type") === edgeType)
                );

            if (locationEdges.length < 2) return; // Not multi-homed.

            // Mark primary as a shadow group member.
            primary.data("_shadow_group", primaryId);
            primary.data("_shadow_role", "primary");

            const shadowIds = [];

            locationEdges.forEach((edge) => {
                const container = edge.target();
                const containerId = container.id();
                const shadowId = SHADOW_ID_PREFIX + primaryId + ":" + containerId;

                // Create shadow node.
                cy.add({
                    group: "nodes",
                    data: {
                        id: shadowId,
                        label: primary.data("label") || "",
                        entity_type: primary.data("entity_type") || "",
                        icon_url: primary.data("icon_url") || "",
                        shape: primary.data("shape") || "ellipse",
                        _shadow_group: primaryId,
                        _shadow_role: "shadow",
                        _shadow_primary: primaryId,
                        _shadow_host: containerId,
                        _is_shadow: true,
                    },
                });

                // Create synthetic placement edge for nesting resolution.
                cy.add({
                    group: "edges",
                    data: {
                        id: SHADOW_EDGE_PREFIX + shadowId,
                        source: shadowId,
                        target: containerId,
                        label: "",
                        edge_type: placementEdgeType,
                    },
                    classes: "tap-nesting-hidden",
                });

                // Create visual shadow link from shadow to primary.
                cy.add({
                    group: "edges",
                    data: {
                        id: SHADOW_LINK_PREFIX + shadowId,
                        source: shadowId,
                        target: primaryId,
                        label: "",
                        _is_shadow_link: true,
                        _shadow_group: primaryId,
                    },
                });

                shadowIds.push(shadowId);
            });

            shadowGroups[primaryId] = shadowIds;
        });
    });

    return {shadowGroups};
}

/**
 * Wire up hover highlighting for shadow groups. Call AFTER layout completes
 * so nodes are positioned and visible.
 *
 * @param {cytoscape.Core} cy
 * @returns {{ destroy: Function }} Cleanup handle.
 */
export function initShadowInteraction(cy) {
    const HIGHLIGHT_CLASS = "tap-shadow-highlight";

    function getGroup(node) {
        const groupId = node.data("_shadow_group");
        if (!groupId) return null;
        return cy.elements(`[_shadow_group="${groupId}"]`);
    }

    function onMouseOver(evt) {
        const node = evt.target;
        const group = getGroup(node);
        if (group) group.addClass(HIGHLIGHT_CLASS);
    }

    function onMouseOut(evt) {
        const node = evt.target;
        const group = getGroup(node);
        if (group) group.removeClass(HIGHLIGHT_CLASS);
    }

    cy.on("mouseover", "node[_shadow_group]", onMouseOver);
    cy.on("mouseout", "node[_shadow_group]", onMouseOut);

    return {
        destroy() {
            cy.off("mouseover", "node[_shadow_group]", onMouseOver);
            cy.off("mouseout", "node[_shadow_group]", onMouseOut);
            cy.elements("." + HIGHLIGHT_CLASS).removeClass(HIGHLIGHT_CLASS);
        },
    };
}

/**
 * Remove all shadow nodes, links, and placement edges. Call during
 * elevation transitions or destroy.
 *
 * @param {cytoscape.Core} cy
 */
export function removeShadows(cy) {
    // Remove shadow links.
    cy.edges("[_is_shadow_link]").remove();
    // Remove shadow placement edges.
    cy.edges().filter((e) => e.id().startsWith(SHADOW_EDGE_PREFIX)).remove();
    // Clear primary shadow data.
    cy.nodes("[_shadow_role='primary']").forEach((n) => {
        n.removeData("_shadow_group");
        n.removeData("_shadow_role");
    });
    // Remove shadow nodes.
    cy.nodes("[_is_shadow]").remove();
}
