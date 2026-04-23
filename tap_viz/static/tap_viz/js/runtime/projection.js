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
 * Under the bounded-layer nested projection model, viewport-preservation
 * (hero-node anchoring, cursor tracking, ancestor fallback) is removed.
 * Stable outer geometry eliminates the geometry discontinuities those
 * mechanisms were compensating for.
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
        shadowInteractionHandle: null,
        statusBadgesHandle: null,
        typeBadgesHandle: null,
        // After a commanded transition, anchorZoom pins the zoom watcher to
        // the current elevation so small user scroll movements don't
        // immediately override it. Cleared when the user zooms far enough
        // away from the anchor to warrant a real transition.
        anchorZoom: null,
        destroyed: false,
        listeners: [],
        dragGroupHandle: null,
    };

    const elevations = [...projection.elevations].sort((a, b) => a.zoom - b.zoom);

    function elevationByName(name) {
        return projection.elevations.find((e) => e.name === name) || null;
    }

    function elevationForZoom(zoomLevel) {
        // Active elevation = one with largest zoom value <= current zoom.
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
        const nodeStyle = projection.node_style || "default";

        // Hide the canvas before layout to prevent flash of unpositioned
        // nodes. The cascade reveal will unhide and animate them in.
        if (triggerReason === "initial_load") {
            cy.container().style.visibility = "hidden";
        }

        const context = {
            cy,
            projection,
            elevation,
            trigger_reason: triggerReason,
            trigger_node: triggerNode,
            inputs: state.inputs,
            node_style: nodeStyle,
        };

        await runLayoutsSerially(elevation, context);

        // Apply type icon badges after layout settles positions.
        if (state.typeBadgesHandle) {
            state.typeBadgesHandle.destroy();
            state.typeBadgesHandle = null;
        }
        let sharedBadgeSize = 0;
        if (nodeStyle === "icon-badge") {
            const {applyBadgeNodes} = await import("./badge-nodes.js");
            state.typeBadgesHandle = applyBadgeNodes(cy);
            sharedBadgeSize = state.typeBadgesHandle.uniformBadgeSize || 0;
        }

        // Apply status badges (alert, warn, ...) if configured on the
        // projection. Independent of node_style; shares badge diameter with
        // the type icon pass when that pass is active.
        if (state.statusBadgesHandle) {
            state.statusBadgesHandle.destroy();
            state.statusBadgesHandle = null;
        }
        if (projection.status_badges) {
            const {applyStatusBadges} = await import("./status-badges.js");
            state.statusBadgesHandle = applyStatusBadges(cy, projection.status_badges, {
                uniformBadgeSize: sharedBadgeSize,
            });
        }

        // Re-init shadow interaction listeners after layout.
        if (state.shadowInteractionHandle) {
            state.shadowInteractionHandle.destroy();
            state.shadowInteractionHandle = null;
        }
        if (cy.nodes("[_is_shadow]").length > 0) {
            const {initShadowInteraction} = await import("./shadow-nodes.js");
            state.shadowInteractionHandle = initShadowInteraction(cy);
        }

        // Enable parent-drags-children after nesting is stamped
        // (skip if nodes are locked — no dragging allowed).
        if (state.dragGroupHandle) {
            state.dragGroupHandle.destroy();
            state.dragGroupHandle = null;
        }
        if (!projection.lock_nodes) {
            const {enableDragGroup} = await import("./drag-group.js");
            state.dragGroupHandle = enableDragGroup(cy);
        }

        // Lock all nodes in place if configured.
        if (projection.lock_nodes) {
            cy.nodes().lock();
        }

        // Cascade reveal on initial load — nodes pop in layer by layer.
        if (triggerReason === "initial_load") {
            const {cascadeReveal} = await import("./cascade-reveal.js");
            await cascadeReveal(cy);

            // Pin minimum zoom to the post-fit level if configured.
            if (projection.min_zoom === "fit") {
                cy.minZoom(cy.zoom());
            } else if (typeof projection.min_zoom === "number") {
                cy.minZoom(projection.min_zoom);
            }
        }
    }

    // ---- Zoom watcher ----
    // log-ratio distance from the anchor required to release the pin.
    // ln(1.6) ~ 0.47 -> need to zoom to less than ~62% or more than ~160%
    // of the anchor before the watcher resumes normal elevation activation.
    const ANCHOR_RELEASE_LOG_RATIO = 0.47;

    function onZoom() {
        if (state.destroyed || state.transitionLock) return;
        const zoom = cy.zoom();

        if (state.anchorZoom != null) {
            const drift = Math.abs(Math.log(zoom / state.anchorZoom));
            if (drift < ANCHOR_RELEASE_LOG_RATIO) {
                return;
            }
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
     * elevations' double_tap_targets.
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
            if (target !== state.activeElevation) {
                await activate(target, "double_tap");
            }
            await animateViewportTo(target.zoom, node);
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
            if (state.shadowInteractionHandle) {
                state.shadowInteractionHandle.destroy();
                state.shadowInteractionHandle = null;
            }
            if (state.dragGroupHandle) {
                state.dragGroupHandle.destroy();
                state.dragGroupHandle = null;
            }
            if (state.statusBadgesHandle) {
                state.statusBadgesHandle.destroy();
                state.statusBadgesHandle = null;
            }
            if (state.typeBadgesHandle) {
                state.typeBadgesHandle.destroy();
                state.typeBadgesHandle = null;
            }
        },
    };
}
