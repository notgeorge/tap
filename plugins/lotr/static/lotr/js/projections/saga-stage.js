/**
 * LOTR saga-stage tap layout.
 *
 * Asserts the saga-level scene state using the bounded-layer nested
 * projection model:
 *
 *   realm (viewport parent)
 *     └── location (viewport parent)
 *           └── character (leaf at this elevation)
 *
 * Saga-stage is an elevation invariant: whenever it runs (initial load or
 * re-entry from character-view via zoom-out) it leaves cy in the shape above,
 * regardless of what the previous elevation left behind. Artifacts added by
 * character-view are hidden + un-nested on re-entry rather than removed, so
 * the next character-view re-entry can reuse them without re-fetching.
 *
 * Uses projectNested from the bounded-layer runtime — no Cytoscape compound
 * nodes, no anchor children, no tap-dimensions plugin.
 */

import {projectNested, ELEVATION_HIDDEN_CLASS} from "/static/tap_viz/js/runtime/nested-projection.js";

export async function execute(context) {
    const {cy, trigger_reason} = context;

    // 1. Teardown: artifacts from a prior character-view entry are hidden.
    //    They stay in cy so re-entry can unhide without another API round trip.
    cy.nodes('[entity_type="artifact"]').addClass(ELEVATION_HIDDEN_CLASS);
    cy.edges('[edge_type="WIELDS"]').addClass(ELEVATION_HIDDEN_CLASS);

    // 2. Declare nested projection: realm → location → character.
    //    Runtime handles viewport derivation, scale, and constrained layout.
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
        ],
        baseSizes: {
            realm: {width: 800, height: 800},
            location: {width: 160, height: 120},
            character: {width: 50, height: 50},
        },
        padding: 20,
        innerLayout: "grid",
    });

    warnings.forEach((w) => console.warn("[saga-stage]", w.category, w.message));

    // 3. Fit the whole scene only on initial load. Scroll-based re-entry
    //    leaves viewport control to the user / projection runtime.
    if (trigger_reason === "initial_load") {
        cy.fit(cy.nodes(":visible"), 40);
    }
}
