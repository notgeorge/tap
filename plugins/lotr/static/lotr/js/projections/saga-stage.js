/**
 * LOTR saga-stage tap layout.
 *
 * Asserts the saga-level scene state:
 *
 *   realm
 *     └── location
 *           └── character       (leaf; no artifact children at this elevation)
 *
 * Saga-stage is an elevation invariant: whenever it runs (initial load or
 * re-entry from character-view via zoom-out) it leaves cy in the shape above,
 * regardless of what the previous elevation left behind. Artifacts added by
 * character-view are hidden + un-nested on re-entry rather than removed, so
 * the next character-view re-entry can reuse them without re-fetching.
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
            name: "location-contains-location",
            description: "Nest sub-locations inside their parent location.",
            gryphon: "(parent:location)-[:CONTAINS]->(child:location)",
        },
        {
            name: "location-contains-character",
            description: "Nest characters inside their location.",
            gryphon: "(parent:location)<-[:LOCATED_IN]-(child:character)",
        },
    ],
};

// At saga-level characters are leaf nodes — only realms and locations are
// compound parents. Character dims are declared by character-view when it
// nests artifacts inside them, and stripped by the plugin on re-entry.
const PARENT_DIMENSIONS = {
    realm: {width: 1800, height: 1200, padding: 60},
    location: {width: 520, height: 360, padding: 30},
};

export async function execute(context) {
    const {cy, trigger_reason} = context;

    // 1. Teardown: artifacts from a prior character-view entry are un-nested
    //    and marked hidden. They stay in cy so re-entry can unhide without
    //    another API round trip.
    cy.nodes('[entity_type="artifact"]').forEach((a) => {
        if (a.parent().length > 0) a.move({parent: null});
        a.addClass("tap-elevation-hidden");
    });
    cy.edges('[edge_type="WIELDS"]').addClass("tap-elevation-hidden");

    // 2. Layout-owned nesting — only the saga-level rules.
    const {warnings} = applyNesting(cy, NESTING_CONFIG);
    warnings.forEach((w) => console.warn("[saga-stage]", w.category, w.message));

    // 3. Declare per-parent dimensions on every compound node.
    const td = cy.tapDimensions();
    cy.nodes(":parent")
        .not(".tap-dim-anchor")
        .forEach((parent) => {
            const t = parent.data("entity_type");
            const dim = PARENT_DIMENSIONS[t];
            if (dim) td.set(parent.id(), dim);
        });

    // 4. Post-order recursive layout. Grid is dense and honors boundingBox.
    td.clearWarnings();
    td.layoutRecursive({
        defaultLayout: {name: "grid", spacingFactor: 1.2},
    });
    td.warnings().forEach((w) => console.warn("[saga-stage]", w.category, w));

    // 5. Fit the whole scene only on initial load. Scroll-based re-entry
    //    leaves viewport control to the user / projection runtime.
    if (trigger_reason === "initial_load") {
        cy.fit(cy.nodes(":visible").not(".tap-dim-anchor"), 40);
    }
}
