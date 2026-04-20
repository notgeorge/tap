/**
 * LOTR character-view tap layout.
 *
 * Asserts the character-view scene state using the bounded-layer nested
 * projection model. This is additive over saga-stage — all higher-level
 * nesting (realm → location → character) remains visible, and the
 * character → artifact layer is added on top.
 *
 * Full nesting chain at this elevation:
 *   realm (viewport parent)
 *     └── location (viewport parent)
 *           └── character (viewport parent at this elevation)
 *                 └── artifact (leaf)
 *
 * This is the "magnify and enhance" behavior — when the user crosses the
 * character-view zoom threshold (by scroll OR by double-tap commanded
 * animation), all applicable characters expand in lockstep.
 *
 * Re-entry reuses prior state: artifacts hidden by saga-stage are unhidden
 * here instead of re-fetching from the API.
 */

import {projectNested, ELEVATION_HIDDEN_CLASS} from "/static/tap_viz/js/runtime/nested-projection.js";
import {executeSearch} from "/static/tap_viz/js/runtime/search.js";

// "Characters and Their Artifacts" — one-hop ORM search that returns every
// character plus their wielded artifacts and the WIELDS edges. Referenced
// by entity_id from plugins/lotr/grift/searches.grift.json.
const WIELDS_SEARCH_ID = "019d657d-cc50-71e9-a77b-e7dcd0332e8f";

export async function execute(context) {
    const {cy} = context;

    // Step 1. Reuse hidden artifacts from a prior visit, else fetch.
    const hiddenArtifacts = cy.nodes('[entity_type="artifact"].' + ELEVATION_HIDDEN_CLASS);
    if (hiddenArtifacts.length > 0) {
        hiddenArtifacts.removeClass(ELEVATION_HIDDEN_CLASS);
        cy.edges('[edge_type="WIELDS"].' + ELEVATION_HIDDEN_CLASS).removeClass(ELEVATION_HIDDEN_CLASS);
    } else {
        await _fetchAndAddArtifacts(cy);
    }

    // Step 2. Declare the full 4-level nesting chain.
    //         This is additive over saga-stage — realm/location structure
    //         remains visible, character now becomes a viewport parent with
    //         artifacts inside.
    const {warnings} = await projectNested(cy, {
        relationships: [
            {
                name: "realm-contains-location",
                gryphon: "(parent:realm)-[:CONTAINS]->(child:location)",
            },
            {
                name: "location-contains-location",
                gryphon: "(parent:location)-[:CONTAINS]->(child:location)",
            },
            {
                name: "location-contains-character",
                gryphon: "(parent:location)<-[:LOCATED_IN]-(child:character)",
            },
            {
                name: "character-contains-artifact",
                gryphon: "(parent:character)-[:WIELDS]->(child:artifact)",
            },
        ],
        baseSizes: {
            realm: {width: 600, height: 400},
            location: {width: 160, height: 120},
            character: {width: 50, height: 50},
            artifact: {width: 30, height: 30},
        },
        padding: 6,
        innerLayout: "grid",
    });

    warnings.forEach((w) => console.warn("[character-view]", w.category, w.message));
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
