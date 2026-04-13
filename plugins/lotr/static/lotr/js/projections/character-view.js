/**
 * LOTR character-view tap layout.
 *
 * Activated on double-tap of a character node at saga-level. Fetches the
 * artifacts wielded by that character (if not already loaded), nests them
 * inside the character compound, and grids them in place.
 *
 * Demonstrates the runtime sub-search path: pre-baked saga data does not
 * always include every artifact's extended metadata, so the layout fetches
 * additional graph material through the tap_api search endpoint.
 */

import {applyNesting} from "/static/tap_viz/js/runtime/nesting.js";
import "/static/tap_viz/js/runtime/cytoscape-tap-dimensions.js";

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

export async function execute(context) {
    const {cy, trigger_node} = context;
    if (!trigger_node) return;

    // Re-apply character→artifact nesting; idempotent if already nested.
    applyNesting(cy, NESTING_CONFIG);

    const td = cy.tapDimensions();
    const parent = trigger_node;
    td.set(parent.id(), {width: 360, height: 240, padding: 20});

    // Grid just this character's artifact children.
    const children = parent.children().not(".tap-dim-anchor");
    if (children.length > 0) {
        td.clearWarnings();
        td.layoutRecursive({
            defaultLayout: {name: "grid", condense: true},
        });
    }

    // Center the character view in the viewport.
    cy.animate({center: {eles: parent}, zoom: 1.4}, {duration: 300});
}
