/**
 * LOTR character-view tap layout.
 *
 * Asserts the character-view scene state: every character in cy is expanded
 * into a compound node containing the artifacts they wield.
 *
 * This is the "magnify and enhance" behavior — when the user crosses the
 * character-view zoom threshold (by scroll OR by double-tap commanded
 * animation), all applicable characters expand in lockstep, not just a
 * single tapped target.
 *
 * Re-entry reuses prior state: artifacts added on a previous visit are
 * hidden + un-nested by saga-stage when the user zooms back out; this
 * layout unhides and re-nests them instead of re-fetching.
 */

import {applyNesting} from "/static/tap_viz/js/runtime/nesting.js";
import {executeSearch} from "/static/tap_viz/js/runtime/search.js";
import "/static/tap_viz/js/runtime/cytoscape-tap-dimensions.js";

// "Characters and Their Artifacts" — one-hop ORM search that returns every
// character plus their wielded artifacts and the WIELDS edges. Referenced
// by entity_id from plugins/lotr/grift/searches.grift.json.
const WIELDS_SEARCH_ID = "019d657d-cc50-71e9-a77b-e7dcd0332e8f";

const NESTING_CONFIG = {
    clear_existing: false,
    relationships: [
        {
            name: "character-contains-artifact",
            description: "Nest artifacts inside their wielder.",
            gryphon: "(parent:character)-[:WIELDS]->(child:artifact)",
        },
    ],
};

const CHARACTER_DIMENSIONS = {width: 360, height: 240, padding: 24};

export async function execute(context) {
    const {cy} = context;

    // Step 1. Reuse hidden artifacts from a prior visit, else fetch.
    const hiddenArtifacts = cy.nodes('[entity_type="artifact"].tap-elevation-hidden');
    if (hiddenArtifacts.length > 0) {
        hiddenArtifacts.removeClass("tap-elevation-hidden");
        cy.edges('[edge_type="WIELDS"].tap-elevation-hidden').removeClass("tap-elevation-hidden");
    } else {
        await _fetchAndAddArtifacts(cy);
    }

    // Step 2. Apply character→artifact nesting. Idempotent.
    const {warnings} = applyNesting(cy, NESTING_CONFIG);
    warnings.forEach((w) => console.warn("[character-view]", w.category, w.message));

    // Step 3. Declare dimensions on every character that is now a parent.
    const td = cy.tapDimensions();
    cy.nodes('[entity_type="character"]')
        .not(".tap-dim-anchor")
        .forEach((c) => td.set(c.id(), CHARACTER_DIMENSIONS));

    // Step 4. Post-order recursive layout over the whole scene so the new
    //         character compounds find clean positions.
    td.clearWarnings();
    td.layoutRecursive({
        defaultLayout: {name: "grid", spacingFactor: 1.2},
    });
    td.warnings().forEach((w) => console.warn("[character-view]", w.category, w));
}

async function _fetchAndAddArtifacts(cy) {
    let result;
    try {
        result = await executeSearch({
            searchId: WIELDS_SEARCH_ID,
            inputs: {},
            layer: "extended",
        });
    } catch (err) {
        console.error("[character-view] fetch failed", err);
        return;
    }

    const existingNodeIds = new Set();
    cy.nodes().forEach((n) => existingNodeIds.add(n.id()));
    const existingEdgeIds = new Set();
    cy.edges().forEach((e) => existingEdgeIds.add(e.id()));

    const newElements = [];

    (result.nodes || []).forEach((n) => {
        const ent = n.entity || {};
        if (ent.entity_type !== "artifact") return;
        if (existingNodeIds.has(ent.entity_id)) return;
        newElements.push({
            group: "nodes",
            data: {
                id: ent.entity_id,
                label: ent.name || "",
                entity_type: "artifact",
                icon_url: n.icon_url || "",
                shape: n.shape || "ellipse",
                url_id: n.url_id || "",
            },
        });
    });

    (result.edges || []).forEach((e) => {
        const ed = e.edge || {};
        if (ed.edge_type !== "WIELDS") return;
        const edgeId = (e.entity && e.entity.entity_id) ||
            `${ed.from_entity_id}-${ed.to_entity_id}-${ed.edge_type}`;
        if (existingEdgeIds.has(edgeId)) return;
        newElements.push({
            group: "edges",
            data: {
                id: edgeId,
                source: ed.from_entity_id,
                target: ed.to_entity_id,
                label: ed.edge_type,
                edge_type: ed.edge_type,
            },
        });
    });

    if (newElements.length > 0) {
        cy.add(newElements);
    }
}
