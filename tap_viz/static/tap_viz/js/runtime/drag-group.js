/**
 * drag-group.js — Parent-drags-children for TAP Viz bounded-layer nesting.
 *
 * When a viewport parent is dragged, all of its descendants (via the
 * _viewport_parent chain) move in lockstep. Dragging a child moves only
 * that child — group movement is parent-only.
 *
 * Badge nodes follow automatically because badge-nodes.js already listens
 * for position events on _badge_active hosts.
 *
 * Call enableDragGroup(cy) AFTER projectNested completes so _viewport_parent
 * data is stamped on all children.
 *
 * Spec: tap_viz/specs/spec-viz-nested-projection.md (req-viz-nested-projection-bounded-layer)
 */

/**
 * Enable drag-group behavior on all viewport parents in the current scene.
 *
 * @param {cytoscape.Core} cy
 * @returns {{ destroy: Function }} Cleanup handle.
 */
export function enableDragGroup(cy) {
    // Build the children-by-parent map from _viewport_parent stamps.
    const childrenByParent = {};
    cy.nodes().forEach((n) => {
        const vpParent = n.data("_viewport_parent");
        if (vpParent) {
            if (!childrenByParent[vpParent]) childrenByParent[vpParent] = [];
            childrenByParent[vpParent].push(n.id());
        }
    });

    const parentIds = new Set(Object.keys(childrenByParent));
    if (parentIds.size === 0) return {destroy() {}};

    // Snapshot current positions for delta computation.
    parentIds.forEach((id) => {
        const node = cy.getElementById(id);
        if (node.length > 0) {
            const pos = node.position();
            node.data("_prev_pos_x", pos.x);
            node.data("_prev_pos_y", pos.y);
        }
    });

    let propagating = false;

    function onParentPosition(evt) {
        if (propagating) return;
        const parent = evt.target;
        const parentId = parent.id();
        if (!parentIds.has(parentId)) return;

        const prevX = parent.data("_prev_pos_x");
        const prevY = parent.data("_prev_pos_y");
        if (prevX == null || prevY == null) return;

        const curr = parent.position();
        const dx = curr.x - prevX;
        const dy = curr.y - prevY;

        if (dx === 0 && dy === 0) return;

        // Update snapshot before propagating.
        parent.data("_prev_pos_x", curr.x);
        parent.data("_prev_pos_y", curr.y);

        // Collect all descendants recursively.
        const descendants = [];
        const stack = [parentId];
        while (stack.length > 0) {
            const id = stack.pop();
            const kids = childrenByParent[id];
            if (!kids) continue;
            for (const kidId of kids) {
                descendants.push(kidId);
                stack.push(kidId);
            }
        }

        if (descendants.length === 0) return;

        // Apply delta to all descendants in one batch.
        propagating = true;
        try {
            for (const descId of descendants) {
                const node = cy.getElementById(descId);
                if (node.length === 0) continue;
                const pos = node.position();
                node.position({x: pos.x + dx, y: pos.y + dy});
                // Update snapshot if this descendant is also a parent.
                if (parentIds.has(descId)) {
                    node.data("_prev_pos_x", pos.x + dx);
                    node.data("_prev_pos_y", pos.y + dy);
                }
            }
        } finally {
            propagating = false;
        }
    }

    cy.on("position", "node", onParentPosition);

    return {
        destroy() {
            cy.off("position", "node", onParentPosition);
            // Clean up snapshot data.
            parentIds.forEach((id) => {
                const node = cy.getElementById(id);
                if (node.length > 0) {
                    node.removeData("_prev_pos_x");
                    node.removeData("_prev_pos_y");
                }
            });
        },
    };
}
