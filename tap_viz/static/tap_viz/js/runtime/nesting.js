/**
 * tap_viz runtime: nesting resolver and applyNesting helper.
 *
 * Implements the layout-owned nesting process from spec-viz-nesting.md:
 *   - Accepts layout-declared relationships as gryphon strings.
 *   - Resolves candidate parent-child assignments.
 *   - Accepts single-parent assignments, rejects multiple, detects cycles.
 *   - Hides consumed containment edges rather than removing them.
 *   - Returns {parentByChildId, hiddenEdgeIds, warnings}.
 *
 * The high-level `applyNesting(cy, config)` call mutates a live Cytoscape
 * graph in place, setting data.parent on nodes and a hidden class on the
 * consumed containment edges.
 */

// Matches: (parent:label)-[:TYPE]->(child:label) OR (parent:label)<-[:TYPE]-(child:label)
// Edge bracket supports [:TYPE], [var:TYPE], or [TYPE].
const NESTING_PATTERN_RE = /^\(parent(?::(\w+))?\)\s*(?:-\[(?:\w+)?:?(\w+)\]->\s*\(child(?::(\w+))?\)|<-\[(?:\w+)?:?(\w+)\]-\s*\(child(?::(\w+))?\))$/;

export const HIDDEN_CONTAINMENT_CLASS = "tap-hidden-containment";

function parsePattern(gryphon) {
    if (!gryphon) return null;
    const m = NESTING_PATTERN_RE.exec(gryphon.trim());
    if (!m) return null;
    // Groups: 1=parentLabel, 2=outEdgeType, 3=outChildLabel, 4=inEdgeType, 5=inChildLabel
    if (m[2]) {
        return {parentLabel: m[1] || null, childLabel: m[3] || null, edgeType: m[2], direction: "out"};
    }
    return {parentLabel: m[1] || null, childLabel: m[5] || null, edgeType: m[4], direction: "in"};
}

/**
 * Resolve parent-child assignments against a cytoscape graph.
 *
 * @param {cytoscape.Core} cy
 * @param {Array<{gryphon: string}>} relationships
 * @returns {{parentByChildId: Object<string,string>, hiddenEdgeIds: Set<string>, warnings: Array}}
 */
export function resolveNesting(cy, relationships) {
    const warnings = [];
    const rules = [];

    relationships.forEach((rel) => {
        const parsed = parsePattern(rel.gryphon || "");
        if (!parsed) {
            warnings.push({
                category: "unsupported_matcher_syntax",
                message: `Cannot parse gryphon: ${rel.gryphon}`,
            });
            return;
        }
        rules.push(parsed);
    });

    const candidates = {}; // childId -> {parentId: true}
    const consumedEdges = {}; // edgeId -> [parentId, childId]

    cy.edges().forEach((edge) => {
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

    // Cycle detection: walk parent chain, drop assignments that form a cycle.
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
        warnings.push({
            category: "cycle_detected",
            message: `Cycle involving: ${Object.keys(inCycle).join(", ")}`,
        });
        Object.keys(inCycle).forEach((id) => {
            delete parentByChildId[id];
        });
    }

    const hiddenEdgeIds = new Set();
    Object.keys(consumedEdges).forEach((edgeId) => {
        const [parentId, childId] = consumedEdges[edgeId];
        if (parentByChildId[childId] === parentId) {
            hiddenEdgeIds.add(edgeId);
        }
    });

    return {parentByChildId, hiddenEdgeIds, warnings};
}

/**
 * Apply layout-owned nesting to a live Cytoscape graph.
 *
 * @param {cytoscape.Core} cy
 * @param {{clear_existing?: boolean, relationships: Array<{gryphon: string}>}} config
 * @returns {{warnings: Array}}
 */
export function applyNesting(cy, config) {
    const warnings = [];
    if (!config || !Array.isArray(config.relationships)) {
        return {warnings};
    }

    if (config.clear_existing) {
        cy.nodes().forEach((n) => {
            if (n.parent().length > 0) {
                n.move({parent: null});
            }
        });
        cy.edges("." + HIDDEN_CONTAINMENT_CLASS).removeClass(HIDDEN_CONTAINMENT_CLASS);
    }

    const result = resolveNesting(cy, config.relationships);
    warnings.push(...result.warnings);

    // Track prior-parent overrides to emit `layout_nesting_override` warnings.
    Object.keys(result.parentByChildId).forEach((childId) => {
        const newParent = result.parentByChildId[childId];
        const node = cy.getElementById(childId);
        if (node.empty()) return;
        const priorParent = node.parent();
        if (priorParent.length > 0 && priorParent.id() !== newParent) {
            warnings.push({
                category: "layout_nesting_override",
                message: `Node ${childId} re-nested from ${priorParent.id()} to ${newParent}`,
            });
        }
        node.move({parent: newParent});
    });

    result.hiddenEdgeIds.forEach((edgeId) => {
        const edge = cy.getElementById(edgeId);
        if (!edge.empty()) edge.addClass(HIDDEN_CONTAINMENT_CLASS);
    });

    return {warnings};
}
