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
        // After a commanded transition, anchorZoom pins the zoom watcher to
        // the current elevation so small user scroll movements don't
        // immediately override it. Cleared when the user zooms far enough
        // away from the anchor to warrant a real transition.
        anchorZoom: null,
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

        // Scroll-driven elevation transitions preserve the user's visual
        // frame of reference: record the node closest to the viewport center
        // before the layout runs, then re-pan after so that same node lands
        // at the same rendered position. Without this, layoutRecursive
        // shuffles compounds out from under the viewport and the user ends
        // up looking at some unrelated part of the scene.
        let hero = null;
        let heroBefore = null;
        if (triggerReason === "zoom_transition") {
            hero = findHeroNode();
            if (hero) heroBefore = {...hero.renderedPosition()};
        }

        await runLayoutsSerially(elevation, context);

        if (hero && heroBefore && !hero.removed()) {
            const zoom = cy.zoom();
            const modelNow = hero.position();
            cy.pan({
                x: heroBefore.x - modelNow.x * zoom,
                y: heroBefore.y - modelNow.y * zoom,
            });
        }
    }

    function findHeroNode() {
        const containerRect = cy.container().getBoundingClientRect();
        const cxR = containerRect.width / 2;
        const cyR = containerRect.height / 2;
        let best = null;
        let bestDist = Infinity;
        cy.nodes(":visible").not(".tap-dim-anchor").forEach((n) => {
            if (n.isParent()) return; // prefer leaf nodes — they move less on layout
            const rp = n.renderedPosition();
            const d = Math.hypot(rp.x - cxR, rp.y - cyR);
            if (d < bestDist) {
                bestDist = d;
                best = n;
            }
        });
        return best;
    }

    // ---- Zoom watcher ----
    // log-ratio distance from the anchor required to release the pin.
    // ln(1.6) ≈ 0.47 → need to zoom to less than ~62% or more than ~160%
    // of the anchor before the watcher resumes normal elevation activation.
    const ANCHOR_RELEASE_LOG_RATIO = 0.47;

    function onZoom() {
        if (state.destroyed || state.transitionLock) return;
        const zoom = cy.zoom();

        if (state.anchorZoom != null) {
            const drift = Math.abs(Math.log(zoom / state.anchorZoom));
            if (drift < ANCHOR_RELEASE_LOG_RATIO) {
                // Small movement inside the hysteresis window — stay put.
                return;
            }
            // User zoomed far enough to "leave" the commanded elevation.
            state.anchorZoom = null;
        }

        const target = elevationForZoom(zoom);
        if (target && target !== state.activeElevation) {
            activate(target, "zoom_transition").catch((e) => state.onError(e));
        }
    }
    cy.on("zoom", onZoom);
    state.listeners.push(["zoom", onZoom]);

    // ---- Double-tap watcher ----
    // panel-graph.js detects double-taps via a manual two-tap timer and fires
    // a `tap-double` custom cytoscape event on the target node. We subscribe
    // to that rather than cytoscape's built-in `dbltap`, which is not
    // reliably emitted across pointer configurations in 3.30.x.
    function onNodeDblTap(evt) {
        if (state.destroyed) return;
        const node = evt.target;
        if (!node || !node.isNode || !node.isNode()) return;
        handleDoubleTap(node).catch((e) => state.onError(e));
    }
    cy.on("tap-double", "node", onNodeDblTap);
    state.listeners.push(["tap-double node", onNodeDblTap]);

    /**
     * Look up the target elevation for a given entity type across *all*
     * elevations' double_tap_targets. Model: double-tap is a property of
     * the entity type, not the source elevation — double-tapping a character
     * always drills into character-view regardless of where you started.
     */
    function findDoubleTapTarget(entityType) {
        for (const elev of projection.elevations) {
            const rules = elev.double_tap_targets || [];
            const hit = rules.find((t) => t.entity_type === entityType);
            if (hit) return elevationByName(hit.target_elevation);
        }
        return null;
    }

    async function handleDoubleTap(node) {
        const entityType = node.data("entity_type") || "";
        const target = findDoubleTapTarget(entityType);
        if (!target) return;

        state.transitionLock = true;
        try {
            // Only assert the target elevation's scene state if we're not
            // already there. Re-running a layout we're already in would
            // reposition every node under the user and feel jarring — and
            // within the same elevation, the tapped node is already in its
            // expanded form.
            if (target !== state.activeElevation) {
                await activate(target, "double_tap");
            }
            // Smoothly fly the viewport to the (possibly repositioned) node.
            await animateViewportTo(target.zoom, node);
            // Pin the zoom watcher to the landing zoom so a small scroll
            // doesn't instantly revert the commanded elevation.
            state.anchorZoom = cy.zoom();
        } finally {
            state.transitionLock = false;
        }
    }

    const COMMANDED_FIT_PADDING = 60;

    function animateViewportTo(targetZoom, centerNode) {
        return new Promise((resolve) => {
            const opts = centerNode
                ? {fit: {eles: centerNode, padding: COMMANDED_FIT_PADDING}}
                : {zoom: targetZoom};
            cy.animate(opts, {duration: 350, easing: "ease-in-out", complete: resolve});
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
