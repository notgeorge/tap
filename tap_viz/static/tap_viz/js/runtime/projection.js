/**
 * tap_viz runtime: projection orchestrator.
 *
 * Owns the multi-elevation visual journey for a graph panel:
 *   - initial load runs the default elevation's tap layouts
 *   - zoom threshold crossings swap the active elevation
 *   - double-tap on eligible nodes jumps to a target elevation with a
 *     commanded zoom animation and a transition lock that suppresses
 *     ambient zoom-threshold activation while the commanded transition
 *     runs
 *   - layout execution is serial, failures are isolated per layout
 *
 * Spec: tap_viz/specs/spec-viz-projection.md
 */

import {loadLayoutModule} from "./layout-loader.js";

/**
 * @param {cytoscape.Core} cy
 * @param {Object} projection Serialized Projection.definition (monolithic shape)
 * @param {{inputs?: Object, onWarning?: Function, onError?: Function}} [opts]
 * @returns {Promise<{destroy: Function, activate: Function}>}
 */
export async function initProjection(cy, projection, opts = {}) {
    if (!cy) throw new Error("initProjection: cy required");
    if (!projection || !Array.isArray(projection.elevations)) {
        throw new Error("initProjection: projection must have elevations[]");
    }

    const state = {
        cy,
        projection,
        inputs: opts.inputs || {},
        onWarning: opts.onWarning || ((w) => console.warn("[projection]", w)),
        onError: opts.onError || ((e) => console.error("[projection]", e)),
        activeElevation: null,
        transitionLock: false,
        destroyed: false,
        listeners: [],
    };

    const elevations = [...projection.elevations].sort((a, b) => a.zoom - b.zoom);

    function elevationByName(name) {
        return projection.elevations.find((e) => e.name === name) || null;
    }

    function elevationForZoom(zoomLevel) {
        // Active elevation = one with largest zoom value ≤ current zoom.
        let chosen = elevations[0];
        for (const e of elevations) {
            if (e.zoom <= zoomLevel) chosen = e;
        }
        return chosen;
    }

    async function runLayoutsSerially(elevation, context) {
        const layouts = elevation.tap_layouts || [];
        for (const layoutDef of layouts) {
            try {
                const mod = await loadLayoutModule(layoutDef.js_file);
                await mod.execute({...context, layout: layoutDef});
            } catch (err) {
                state.onError({
                    category: "layout_execution_failed",
                    elevation: elevation.name,
                    layout: layoutDef.name,
                    error: err,
                });
                // Continue: later layouts still run per req-viz-layout-execution.
            }
        }
    }

    async function activate(elevation, triggerReason, triggerNode = null) {
        if (!elevation) return;
        state.activeElevation = elevation;
        const context = {
            cy,
            projection,
            elevation,
            trigger_reason: triggerReason,
            trigger_node: triggerNode,
            inputs: state.inputs,
        };
        await runLayoutsSerially(elevation, context);
    }

    // ---- Zoom watcher ----
    function onZoom() {
        if (state.destroyed || state.transitionLock) return;
        const zoom = cy.zoom();
        const target = elevationForZoom(zoom);
        if (target && target !== state.activeElevation) {
            activate(target, "zoom_transition").catch((e) => state.onError(e));
        }
    }
    cy.on("zoom", onZoom);
    state.listeners.push(["zoom", onZoom]);

    // ---- Double-tap watcher ----
    let lastTapTime = 0;
    let lastTapNodeId = null;
    const DOUBLE_TAP_MS = 400;

    function onNodeTap(evt) {
        if (state.destroyed) return;
        const node = evt.target;
        if (!node || !node.isNode || !node.isNode()) return;

        const now = Date.now();
        const nodeId = node.id();
        if (nodeId === lastTapNodeId && now - lastTapTime < DOUBLE_TAP_MS) {
            lastTapTime = 0;
            lastTapNodeId = null;
            handleDoubleTap(node).catch((e) => state.onError(e));
            return;
        }
        lastTapTime = now;
        lastTapNodeId = nodeId;
    }
    cy.on("tap", "node", onNodeTap);
    state.listeners.push(["tap node", onNodeTap]);

    async function handleDoubleTap(node) {
        const entityType = node.data("entity_type") || "";
        const current = state.activeElevation;
        if (!current || !Array.isArray(current.double_tap_targets)) return;
        const hit = current.double_tap_targets.find((t) => t.entity_type === entityType);
        if (!hit) return;
        const target = elevationByName(hit.target_elevation);
        if (!target) {
            state.onWarning({category: "double_tap_target_missing", detail: hit});
            return;
        }

        state.transitionLock = true;
        try {
            await animateZoomTo(target.zoom);
            await activate(target, "double_tap", node);
        } finally {
            state.transitionLock = false;
        }
    }

    function animateZoomTo(targetZoom) {
        return new Promise((resolve) => {
            cy.animate(
                {zoom: targetZoom},
                {duration: 350, easing: "ease-in-out", complete: resolve}
            );
        });
    }

    // ---- Initial load ----
    const defaultName = projection.default_elevation;
    const initial = elevationByName(defaultName);
    if (!initial) {
        throw new Error(`initProjection: default_elevation "${defaultName}" not found`);
    }
    await activate(initial, "initial_load");

    return {
        activate: (name, reason = "commanded") => activate(elevationByName(name), reason),
        destroy() {
            if (state.destroyed) return;
            state.destroyed = true;
            state.listeners.forEach(([ev, fn]) => cy.off(ev, fn));
            state.listeners.length = 0;
        },
    };
}
