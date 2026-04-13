/**
 * LOTR saga-stage tap layout.
 *
 * Initial-load layout for the LOTR saga projection. Works off the pre-baked
 * seed graph (realm/locations/characters/artifacts already loaded into cy)
 * and arranges it into nested compound-node scene:
 *
 *   realm
 *     ├── location
 *     │     └── character
 *     │           └── artifact
 *     └── ...
 *
 * Uses tap_viz runtime modules for nesting and per-parent dimensions.
 */

import {applyNesting} from "/static/tap_viz/js/runtime/nesting.js";
import "/static/tap_viz/js/runtime/cytoscape-tap-dimensions.js";

const NESTING_CONFIG = {
    clear_existing: false,
    relationships: [
        {
            name: "realm-contains-location",
            description: "Nest locations inside their realm.",
            gryphon: "(parent:realm)-[:CONTAINS]->(child:location)",
        },
        {
            name: "location-contains-character",
            description: "Nest characters inside their location.",
            gryphon: "(parent:location)<-[:LOCATED_IN]-(child:character)",
        },
        {
            name: "character-contains-artifact",
            description: "Nest artifacts inside their wielder.",
            gryphon: "(parent:character)-[:WIELDS]->(child:artifact)",
        },
    ],
};

const PARENT_DIMENSIONS = {
    realm: {width: 1800, height: 1200, padding: 60},
    location: {width: 520, height: 360, padding: 30},
    character: {width: 220, height: 160, padding: 18},
};

export async function execute(context) {
    const {cy, trigger_reason} = context;

    if (trigger_reason !== "initial_load" && trigger_reason !== "zoom_transition") {
        return;
    }

    // 1. Layout-owned nesting.
    const {warnings} = applyNesting(cy, NESTING_CONFIG);
    warnings.forEach((w) => console.warn("[saga-stage]", w.category, w.message));

    // 2. Declare per-parent dimensions on every compound node.
    const td = cy.tapDimensions();
    cy.nodes(":parent")
        .not(".tap-dim-anchor")
        .forEach((parent) => {
            const t = parent.data("entity_type");
            const dim = PARENT_DIMENSIONS[t];
            if (dim) td.set(parent.id(), dim);
        });

    // 3. Post-order recursive layout. Grid is dense and honors boundingBox.
    td.clearWarnings();
    td.layoutRecursive({
        defaultLayout: {name: "grid", spacingFactor: 1.2},
    });
    td.warnings().forEach((w) => console.warn("[saga-stage]", w.category, w));

    // 4. Fit the whole scene, excluding anchor nodes from the fit target.
    cy.fit(cy.nodes().not(".tap-dim-anchor"), 40);
}
