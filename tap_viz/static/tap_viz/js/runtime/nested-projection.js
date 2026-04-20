/**
 * tap_viz runtime: nested-projection.
 *
 * Implements the bounded-layer nested projection model from
 * spec-viz-nested-projection.md. Layout authors call projectNested(cy, config)
 * to declare nesting relationships, base sizes, and layout preferences.
 * The runtime handles:
 *   - nesting resolution (Gryphon subset edge matching)
 *   - containment edge hiding
 *   - viewport derivation from parent bbox
 *   - scale-to-fit computation
 *   - constrained inner layout execution
 *   - recursive descent for multi-level nesting
 *   - z-index layering
 *   - .tap-viewport-parent container visual switch
 *
 * No Cytoscape compound nodes are used. All nodes remain flat peers.
 * Containment is purely positional.
 */

// ---- Gryphon subset pattern parser ----
// Matches: (parent:label)-[:TYPE]->(child:label) OR (parent:label)<-[:TYPE]-(child:label)
const NESTING_PATTERN_RE = /^\(parent(?::(\w+))?\)\s*(?:-\[(?:\w+)?:?(\w+)\]->\s*\(child(?::(\w+))?\)|<-\[(?:\w+)?:?(\w+)\]-\s*\(child(?::(\w+))?\))$/;

export const HIDDEN_CONTAINMENT_CLASS = "tap-hidden-containment";
export const VIEWPORT_PARENT_CLASS = "tap-viewport-parent";
export const ELEVATION_HIDDEN_CLASS = "tap-elevation-hidden";

function parsePattern(gryphon) {
    if (!gryphon) return null;
    const m = NESTING_PATTERN_RE.exec(gryphon.trim());
    if (!m) return null;
    if (m[2]) {
        return {parentLabel: m[1] || null, childLabel: m[3] || null, edgeType: m[2], direction: "out"};
    }
    return {parentLabel: m[1] || null, childLabel: m[5] || null, edgeType: m[4], direction: "in"};
}

// ---- Nesting resolver (stamps data, no compounds) ----

/**
 * Resolve parent-child assignments from edges and relationship declarations.
 * Does NOT mutate cy. Returns assignment maps.
 */
export function resolveNesting(cy, relationships) {
    const warnings = [];
    const rules = [];

    relationships.forEach((rel) => {
        const parsed = parsePattern(rel.gryphon || "");
        if (!parsed) {
            warnings.push({category: "unsupported_matcher_syntax", message: `Cannot parse gryphon: ${rel.gryphon}`});
            return;
        }
        rules.push(parsed);
    });

    const candidates = {}; // childId -> {parentId: true}
    const consumedEdges = {}; // edgeId -> [parentId, childId]

    cy.edges().forEach((edge) => {
        if (edge.hasClass(ELEVATION_HIDDEN_CLASS)) return;
        const edgeType = edge.data("edge_type") || edge.data("label") || "";
        const sourceId = edge.source().id();
        const targetId = edge.target().id();
        const sourceType = edge.source().data("entity_type") || "";
        const targetType = edge.target().data("entity_type") || "";

        rules.forEach((rule) => {
            if (edgeType !== rule.edgeType) return;
            let parentId = null;
            let childId = null;
            if (rule.direction === "out") {
                if ((!rule.parentLabel || sourceType === rule.parentLabel) &&
                    (!rule.childLabel || targetType === rule.childLabel)) {
                    parentId = sourceId;
                    childId = targetId;
                }
            } else {
                if ((!rule.parentLabel || targetType === rule.parentLabel) &&
                    (!rule.childLabel || sourceType === rule.childLabel)) {
                    parentId = targetId;
                    childId = sourceId;
                }
            }
            if (parentId && childId) {
                if (!candidates[childId]) candidates[childId] = {};
                candidates[childId][parentId] = true;
                consumedEdges[edge.id()] = [parentId, childId];
            }
        });
    });

    // Accept single-parent, reject multiple.
    const parentByChildId = {};
    Object.keys(candidates).forEach((childId) => {
        const parents = Object.keys(candidates[childId]);
        if (parents.length === 1) {
            parentByChildId[childId] = parents[0];
        } else {
            warnings.push({
                category: "multiple_parents",
                message: `Child ${childId} has ${parents.length} candidate parents: ${parents.join(", ")}`,
            });
        }
    });

    // Cycle detection.
    const inCycle = {};
    Object.keys(parentByChildId).forEach((startChild) => {
        const visited = {};
        let current = startChild;
        while (parentByChildId[current]) {
            if (visited[current]) {
                let cycleNode = current;
                do {
                    inCycle[cycleNode] = true;
                    cycleNode = parentByChildId[cycleNode];
                } while (cycleNode && cycleNode !== current);
                break;
            }
            visited[current] = true;
            current = parentByChildId[current];
        }
    });
    if (Object.keys(inCycle).length > 0) {
        warnings.push({category: "cycle_detected", message: `Cycle involving: ${Object.keys(inCycle).join(", ")}`});
        Object.keys(inCycle).forEach((id) => delete parentByChildId[id]);
    }

    // Hidden edge ids (only for accepted assignments).
    const hiddenEdgeIds = new Set();
    Object.keys(consumedEdges).forEach((edgeId) => {
        const [parentId, childId] = consumedEdges[edgeId];
        if (parentByChildId[childId] === parentId) {
            hiddenEdgeIds.add(edgeId);
        }
    });

    return {parentByChildId, hiddenEdgeIds, warnings};
}

// ---- Main API ----

/**
 * Project nested scenes into parent viewports.
 *
 * @param {cytoscape.Core} cy
 * @param {Object} config
 * @param {Array<{name: string, gryphon: string}>} config.relationships
 * @param {Object<string, {width: number, height: number}>} config.baseSizes
 * @param {number} config.padding
 * @param {string|Object} config.innerLayout - Cytoscape layout name or options
 * @param {Object<string, string|Object>} [config.innerLayouts] - Per-parent-type overrides
 * @param {boolean} [config.fit] - Fit viewport after projection
 * @returns {Promise<{warnings: Array}>}
 */
export async function projectNested(cy, config) {
    const {relationships, baseSizes, padding, innerLayout} = config;
    const innerLayouts = config.innerLayouts || {};
    const warnings = [];

    if (!relationships || !baseSizes || padding == null || !innerLayout) {
        throw new Error("projectNested: relationships, baseSizes, padding, and innerLayout are required");
    }

    // Step 1: Clear prior nesting state.
    _clearNestingState(cy);

    // Step 2: Resolve nesting relationships.
    const resolved = resolveNesting(cy, relationships);
    warnings.push(...resolved.warnings);

    // Step 3: Stamp _viewport_parent on children and hide containment edges.
    Object.keys(resolved.parentByChildId).forEach((childId) => {
        const node = cy.getElementById(childId);
        if (!node.empty()) {
            node.data("_viewport_parent", resolved.parentByChildId[childId]);
        }
    });
    resolved.hiddenEdgeIds.forEach((edgeId) => {
        const edge = cy.getElementById(edgeId);
        if (!edge.empty()) edge.addClass(HIDDEN_CONTAINMENT_CLASS);
    });

    // Step 4: Apply base sizes to all nodes.
    cy.nodes().forEach((node) => {
        if (node.hasClass(ELEVATION_HIDDEN_CLASS)) return;
        const entityType = node.data("entity_type") || "";
        const size = baseSizes[entityType];
        if (size) {
            node.style({"width": size.width, "height": size.height});
        }
    });

    // Step 5: Build the nesting tree structure.
    const childrenByParent = {}; // parentId -> [childId, ...]
    Object.keys(resolved.parentByChildId).forEach((childId) => {
        const parentId = resolved.parentByChildId[childId];
        if (!childrenByParent[parentId]) childrenByParent[parentId] = [];
        childrenByParent[parentId].push(childId);
    });

    // Find root parents (have children but no _viewport_parent themselves).
    const rootParentIds = Object.keys(childrenByParent).filter(
        (id) => !resolved.parentByChildId[id]
    );

    // Step 6: Recursive descent projection.
    // Process depth layers from outermost in. Each parent positions its
    // children within its viewport, then we recurse into children that
    // are themselves parents.
    const depthByNode = {}; // nodeId -> nesting depth (0 = root)

    function processParent(parentId, depth) {
        const parentNode = cy.getElementById(parentId);
        if (parentNode.empty()) return;
        depthByNode[parentId] = Math.max(depthByNode[parentId] || 0, depth);

        const childIds = childrenByParent[parentId];
        if (!childIds || childIds.length === 0) return;

        // Mark as viewport parent.
        parentNode.addClass(VIEWPORT_PARENT_CLASS);

        // Derive inner viewport from parent's bbox.
        const parentPos = parentNode.position();
        const pw = parseFloat(parentNode.style("width"));
        const ph = parseFloat(parentNode.style("height"));

        const vpW = pw - padding * 2;
        const vpH = ph - padding * 2;

        if (vpW <= 0 || vpH <= 0) {
            warnings.push({
                category: "overfill",
                message: `Parent ${parentId} inner viewport is zero or negative after padding`,
            });
            return;
        }

        // Compute the natural extent of children at their base sizes.
        // Use a simple grid arrangement to estimate extent.
        const childNodes = childIds
            .map((id) => cy.getElementById(id))
            .filter((n) => !n.empty() && !n.hasClass(ELEVATION_HIDDEN_CLASS));

        if (childNodes.length === 0) {
            parentNode.removeClass(VIEWPORT_PARENT_CLASS);
            return;
        }

        // Determine child base sizes (largest width/height among children).
        let maxChildW = 0;
        let maxChildH = 0;
        childNodes.forEach((n) => {
            const et = n.data("entity_type") || "";
            const sz = baseSizes[et] || {width: 40, height: 40};
            maxChildW = Math.max(maxChildW, sz.width);
            maxChildH = Math.max(maxChildH, sz.height);
        });

        // Estimate natural grid extent for scale computation.
        const cols = Math.max(1, Math.ceil(Math.sqrt(childNodes.length)));
        const rows = Math.max(1, Math.ceil(childNodes.length / cols));
        const spacing = 1.2; // grid spacing factor
        const naturalW = cols * maxChildW * spacing;
        const naturalH = rows * maxChildH * spacing;

        // Compute uniform scale to fit.
        const scale = Math.min(vpW / naturalW, vpH / naturalH, 1.0);

        if (scale <= 0) {
            warnings.push({
                category: "overfill",
                message: `Parent ${parentId}: children cannot fit (scale=${scale.toFixed(3)})`,
            });
            return;
        }

        // Apply scaled sizes to children.
        childNodes.forEach((n) => {
            const et = n.data("entity_type") || "";
            const sz = baseSizes[et] || {width: 40, height: 40};
            const scaledW = sz.width * scale;
            const scaledH = sz.height * scale;
            n.style({"width": scaledW, "height": scaledH});
            depthByNode[n.id()] = depth + 1;
        });

        // Compute the bounding box for the inner viewport in model coords.
        // The viewport is centered on the parent position.
        const vpBBox = {
            x1: parentPos.x - vpW / 2,
            y1: parentPos.y - vpH / 2,
            x2: parentPos.x + vpW / 2,
            y2: parentPos.y + vpH / 2,
            w: vpW,
            h: vpH,
        };

        // Run the constrained inner layout.
        const layoutOpts = _resolveLayoutOpts(parentNode, innerLayout, innerLayouts);
        _runConstrainedLayout(cy, childNodes, vpBBox, layoutOpts);

        // Recurse into children that are themselves parents.
        childNodes.forEach((n) => {
            if (childrenByParent[n.id()]) {
                processParent(n.id(), depth + 1);
            }
        });
    }

    // Position root parents first (they use their base sizes, already applied).
    // Run a top-level layout on root parents + any orphan nodes.
    const allNodeIds = new Set();
    cy.nodes().forEach((n) => {
        if (!n.hasClass(ELEVATION_HIDDEN_CLASS)) allNodeIds.add(n.id());
    });
    const nestedChildIds = new Set(Object.keys(resolved.parentByChildId));

    // Top-level nodes: not a nested child of anyone.
    const topLevelNodes = cy.nodes().filter((n) => {
        return !nestedChildIds.has(n.id()) && !n.hasClass(ELEVATION_HIDDEN_CLASS);
    });

    if (topLevelNodes.length > 0) {
        const topLayoutOpts = _resolveLayoutOpts(null, innerLayout, innerLayouts);
        const topLayout = topLevelNodes.layout({
            ...topLayoutOpts,
            fit: false,
        });
        topLayout.run();
        // Cytoscape sync layouts (grid) complete immediately.
        // Async layouts need a promise. Grid is sync, so this is safe.
        await _waitForLayout(topLayout);
    }

    // Now recursively project children into parents.
    rootParentIds.forEach((id) => processParent(id, 0));

    // Step 7: Z-index assignment by depth.
    cy.nodes().forEach((n) => {
        if (n.hasClass(ELEVATION_HIDDEN_CLASS)) return;
        const d = depthByNode[n.id()] || 0;
        n.style({"z-index": d * 10});
    });

    // Fit if requested.
    if (config.fit) {
        cy.fit(cy.nodes().not("." + ELEVATION_HIDDEN_CLASS), 40);
    }

    return {warnings};
}

// ---- Internal helpers ----

function _clearNestingState(cy) {
    // Remove prior _viewport_parent stamps.
    cy.nodes().forEach((n) => {
        n.removeData("_viewport_parent");
    });
    // Remove containment hidden class from edges.
    cy.edges("." + HIDDEN_CONTAINMENT_CLASS).removeClass(HIDDEN_CONTAINMENT_CLASS);
    // Remove viewport-parent class from nodes.
    cy.nodes("." + VIEWPORT_PARENT_CLASS).removeClass(VIEWPORT_PARENT_CLASS);
}

function _resolveLayoutOpts(parentNode, defaultLayout, perTypeLayouts) {
    if (parentNode) {
        const parentType = parentNode.data("entity_type") || "";
        if (perTypeLayouts[parentType]) {
            const override = perTypeLayouts[parentType];
            return typeof override === "string" ? {name: override} : {...override};
        }
    }
    return typeof defaultLayout === "string" ? {name: defaultLayout} : {...defaultLayout};
}

function _runConstrainedLayout(cy, childNodes, vpBBox, layoutOpts) {
    // Build a collection from childNodes for layout.
    const collection = cy.collection().merge(childNodes);

    const opts = {
        ...layoutOpts,
        fit: false,
        boundingBox: vpBBox,
    };

    const layout = collection.layout(opts);
    layout.run();
    // Grid layout is synchronous — positions are set immediately after run().
}

function _waitForLayout(layout) {
    // For sync layouts (grid, preset, etc.) this resolves immediately.
    // For async layouts (cose, etc.) we'd need layoutstop — but v1 uses grid.
    return new Promise((resolve) => {
        if (layout.one) {
            layout.one("layoutstop", resolve);
            // Fallback: if already stopped (sync layout), resolve next tick.
            setTimeout(resolve, 0);
        } else {
            resolve();
        }
    });
}
