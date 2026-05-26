/**
 * tap_viz runtime: layout scope boxes.
 *
 * Draws a labeled background rectangle around a set of Cytoscape nodes —
 * the visual companion to the Layout entity, which (per spec-viz-layouts
 * § Philosophy) owns the scene-construction work for one node group
 * within an elevation.
 *
 * Each scope box is an HTML <div> overlay positioned over the bounding
 * box of its resolved members. Pan/zoom sync mirrors TapParentLabelOverlay:
 * a transformed container holds wrappers whose positions are computed in
 * canvas coordinates. Non-interactive (pointer-events: none) so the box
 * never intercepts clicks on the nodes inside.
 *
 * Compound parents (Cytoscape native :parent nesting) are strictly
 * hierarchical — a node may have only one compound parent. Scope boxes
 * are the *cross-cutting* container layer: a node already nested inside
 * aws_account compound can also belong to a "Compliance Flow" scope,
 * because scope boxes are purely visual overlays unrelated to the
 * compound-parent graph.
 *
 * API:
 *
 *   const handle = applyScopeBoxes(cy, [
 *     {label: "Compliance", selector: '[entity_type^="aws_"]', style: {...}},
 *     ...
 *   ]);
 *
 * Each box config takes:
 *   - label:    display string shown at the top of the box
 *   - selector: cytoscape selector resolving the box's members. The box
 *               bbox is computed from the union of matched node bboxes.
 *   - filter:   alternative to selector — a (node) => boolean predicate.
 *               Either selector OR filter; selector wins if both present.
 *   - style:    optional per-box style override merged into the default
 *               style (borderColor, backgroundColor, labelColor, padding).
 *
 * Returns a handle with a destroy() method that removes the overlay
 * container and detaches event listeners.
 */

const CONTAINER_CLASS = "tap-scope-box-container";
const BOX_CLASS = "tap-scope-box";
const LABEL_CLASS = "tap-scope-box__label";

const DEFAULT_STYLE = {
    borderColor: "#94a3b8",       // slate-400
    borderWidth: 1,
    borderStyle: "dashed",
    backgroundColor: "rgba(148, 163, 184, 0.06)",  // very faint slate
    labelColor: "#64748b",         // slate-500
    labelBackground: "#ffffff",
    padding: 12,                   // canvas-space px around the member bbox
};

/**
 * Draw labeled overlay rectangles around resolved node groups.
 *
 * @param {cytoscape.Core} cy
 * @param {Array<{label: string, selector?: string, filter?: Function, style?: Object}>} boxes
 * @returns {{destroy: Function}}
 */
export function applyScopeBoxes(cy, boxes) {
    if (!cy || !Array.isArray(boxes) || boxes.length === 0) {
        return {destroy: () => {}};
    }

    const cyContainer = cy.container();
    const canvas = cyContainer.querySelector("canvas");

    // One outer container; pan/zoom sync transforms it once for every box.
    const container = document.createElement("div");
    container.className = CONTAINER_CLASS;
    Object.assign(container.style, {
        position: "absolute",
        top: "0",
        left: "0",
        width: "0",
        height: "0",
        pointerEvents: "none",
        transformOrigin: "top left",
        zIndex: "1",                // behind node interaction layer, above grid
    });
    canvas.parentNode.appendChild(container);

    // One wrapper <div> per box config.
    const wrappers = boxes.map((box) => {
        const wrapper = document.createElement("div");
        wrapper.className = BOX_CLASS;
        const style = {...DEFAULT_STYLE, ...(box.style || {})};
        Object.assign(wrapper.style, {
            position: "absolute",
            boxSizing: "border-box",
            borderStyle: style.borderStyle,
            borderWidth: `${style.borderWidth}px`,
            borderColor: style.borderColor,
            backgroundColor: style.backgroundColor,
            borderRadius: "4px",
            pointerEvents: "none",
        });

        const labelEl = document.createElement("span");
        labelEl.className = LABEL_CLASS;
        labelEl.textContent = box.label || "";
        Object.assign(labelEl.style, {
            position: "absolute",
            top: "-8px",
            left: "12px",
            transform: "translateY(-50%)",
            padding: "0 6px",
            fontSize: "11px",
            fontWeight: "500",
            color: style.labelColor,
            background: style.labelBackground,
            whiteSpace: "nowrap",
            pointerEvents: "none",
        });
        wrapper.appendChild(labelEl);
        container.appendChild(wrapper);
        return {config: box, style, wrapper, labelEl};
    });

    function resolveMembers(box) {
        if (typeof box.filter === "function") {
            return cy.nodes().filter(box.filter);
        }
        if (box.selector) {
            return cy.nodes(box.selector);
        }
        return cy.collection();
    }

    function syncPanZoom() {
        const pan = cy.pan();
        const zoom = cy.zoom();
        const t = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
        const s = container.style;
        s.webkitTransform = t;
        s.msTransform = t;
        s.transform = t;
    }

    function syncBoxes() {
        wrappers.forEach(({config, style, wrapper}) => {
            const members = resolveMembers(config);
            if (members.length === 0) {
                wrapper.style.display = "none";
                return;
            }
            const bb = members.boundingBox({includeLabels: false});
            if (isNaN(bb.x1) || isNaN(bb.y1)) {
                wrapper.style.display = "none";
                return;
            }
            const pad = style.padding;
            const left = bb.x1 - pad;
            const top = bb.y1 - pad;
            const width = (bb.x2 - bb.x1) + 2 * pad;
            const height = (bb.y2 - bb.y1) + 2 * pad;
            wrapper.style.display = "";
            wrapper.style.left = `${left}px`;
            wrapper.style.top = `${top}px`;
            wrapper.style.width = `${width}px`;
            wrapper.style.height = `${height}px`;
        });
    }

    syncPanZoom();
    syncBoxes();

    cy.on("pan zoom", syncPanZoom);
    // bounds catches compound-parent bbox changes; position catches simple moves.
    cy.on("position bounds", "node", syncBoxes);
    cy.on("layoutstop", syncBoxes);

    return {
        destroy: () => {
            cy.off("pan zoom", syncPanZoom);
            cy.off("position bounds", "node", syncBoxes);
            cy.off("layoutstop", syncBoxes);
            if (container.parentNode) container.parentNode.removeChild(container);
        },
    };
}
