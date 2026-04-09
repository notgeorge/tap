/**
 * panel-graph.js — TAP Graph Panel Cytoscape renderer.
 *
 * Reads nodes and edges from embedded JSON script blocks, initialises a
 * Cytoscape instance inside the panel container, and attaches toolbar
 * controls (zoom in, zoom out, fit, fullscreen).
 *
 * Called per-panel via the inline IIFE in graph_panel.html:
 *   initGraph(panelId)
 */

/* global cytoscape */

// ---------------------------------------------------------------------------
// TapVizNestingResolver — client-side compound-node resolution
// ---------------------------------------------------------------------------

// Matches: (parent:label)-[:TYPE]->(child:label) OR (parent:label)<-[:TYPE]-(child:label)
// Edge bracket supports [:TYPE], [var:TYPE], or [TYPE].
var NESTING_PATTERN_RE = /^\(parent(?::(\w+))?\)\s*(?:-\[(?:\w+)?:?(\w+)\]->\s*\(child(?::(\w+))?\)|<-\[(?:\w+)?:?(\w+)\]-\s*\(child(?::(\w+))?\))$/;

function TapVizNestingResolver(nodes, edges) {
    this.nodes = nodes;
    this.edges = edges;
}

TapVizNestingResolver.prototype._parsePattern = function (gryphon) {
    var m = NESTING_PATTERN_RE.exec(gryphon.trim());
    if (!m) return null;
    // Groups: 1=parentLabel, 2=outEdgeType, 3=outChildLabel, 4=inEdgeType, 5=inChildLabel
    if (m[2]) {
        return { parentLabel: m[1] || null, childLabel: m[3] || null, edgeType: m[2], direction: "out" };
    }
    return { parentLabel: m[1] || null, childLabel: m[5] || null, edgeType: m[4], direction: "in" };
};

TapVizNestingResolver.prototype.resolve = function () {
    var self = this;
    var warnings = [];

    // 1. Build type-by-entity-id map.
    var typeByEntityId = {};
    this.nodes.forEach(function (n) {
        var ent = n.entity || {};
        typeByEntityId[ent.entity_id] = ent.entity_type;
    });

    // 2. Collect all nesting rules from all node types' display.nesting metadata.
    var rules = [];
    var seenTypes = {};
    this.nodes.forEach(function (n) {
        var ent = n.entity || {};
        var entityType = ent.entity_type;
        if (seenTypes[entityType]) return;
        seenTypes[entityType] = true;

        var nesting = (n.display || {}).nesting;
        if (!nesting) return;

        // Parent-side rules: self-side is parent, so parentLabel must match entityType.
        (nesting.parent || []).forEach(function (rel) {
            var parsed = self._parsePattern(rel.gryphon || "");
            if (!parsed) {
                warnings.push({ category: "unsupported_matcher_syntax", message: "Cannot parse: " + rel.gryphon });
                return;
            }
            if (parsed.parentLabel && parsed.parentLabel !== entityType) {
                warnings.push({ category: "context_type_mismatch", message: "Parent rule on " + entityType + " declares parent:" + parsed.parentLabel });
                return;
            }
            parsed.parentLabel = entityType;
            rules.push(parsed);
        });

        // Child-side rules: self-side is child, so childLabel must match entityType.
        (nesting.child || []).forEach(function (rel) {
            var parsed = self._parsePattern(rel.gryphon || "");
            if (!parsed) {
                warnings.push({ category: "unsupported_matcher_syntax", message: "Cannot parse: " + rel.gryphon });
                return;
            }
            if (parsed.childLabel && parsed.childLabel !== entityType) {
                warnings.push({ category: "context_type_mismatch", message: "Child rule on " + entityType + " declares child:" + parsed.childLabel });
                return;
            }
            parsed.childLabel = entityType;
            rules.push(parsed);
        });
    });

    // 3. Deduplicate rules (same parentLabel + childLabel + edgeType + direction).
    var ruleKeys = {};
    var uniqueRules = [];
    rules.forEach(function (r) {
        var key = (r.parentLabel || "") + "|" + (r.childLabel || "") + "|" + r.edgeType + "|" + r.direction;
        if (!ruleKeys[key]) {
            ruleKeys[key] = true;
            uniqueRules.push(r);
        }
    });

    // 4. Match edges against rules, build candidate assignments.
    var candidates = {};  // childId -> Set of parentIds
    var consumedEdges = {};  // edgeId -> [parentId, childId]
    this.edges.forEach(function (e) {
        var ent = e.entity || {};
        var ed = e.edge || {};
        var edgeId = ent.entity_id;
        var fromType = typeByEntityId[ed.from_entity_id];
        var toType = typeByEntityId[ed.to_entity_id];

        uniqueRules.forEach(function (rule) {
            var parentId, childId;
            if (rule.direction === "out" && ed.edge_type === rule.edgeType) {
                if ((!rule.parentLabel || fromType === rule.parentLabel) &&
                    (!rule.childLabel || toType === rule.childLabel)) {
                    parentId = ed.from_entity_id;
                    childId = ed.to_entity_id;
                }
            } else if (rule.direction === "in" && ed.edge_type === rule.edgeType) {
                // Inbound: (parent)<-[:TYPE]-(child) means from=child, to=parent.
                if ((!rule.parentLabel || toType === rule.parentLabel) &&
                    (!rule.childLabel || fromType === rule.childLabel)) {
                    parentId = ed.to_entity_id;
                    childId = ed.from_entity_id;
                }
            }
            if (parentId && childId) {
                if (!candidates[childId]) candidates[childId] = {};
                candidates[childId][parentId] = true;
                consumedEdges[edgeId] = [parentId, childId];
            }
        });
    });

    // 5. Accept single-parent, reject multiple parents.
    var parentByChildId = {};
    var hiddenEdgeIds = new Set();
    Object.keys(candidates).forEach(function (childId) {
        var parents = Object.keys(candidates[childId]);
        if (parents.length === 1) {
            parentByChildId[childId] = parents[0];
        } else {
            warnings.push({
                category: "multiple_parents",
                message: "Child " + childId + " has " + parents.length + " candidate parents: " + parents.join(", "),
            });
        }
    });

    // 6. Detect cycles — walk parent chain, drop cyclic assignments.
    var inCycle = {};
    Object.keys(parentByChildId).forEach(function (startChild) {
        var visited = {};
        var current = startChild;
        while (parentByChildId[current]) {
            if (visited[current]) {
                // Mark all nodes in the cycle.
                var cycleNode = current;
                do {
                    inCycle[cycleNode] = true;
                    cycleNode = parentByChildId[cycleNode];
                } while (cycleNode !== current);
                break;
            }
            visited[current] = true;
            current = parentByChildId[current];
        }
    });
    if (Object.keys(inCycle).length > 0) {
        warnings.push({
            category: "cycle_detected",
            message: "Cycle involving: " + Object.keys(inCycle).join(", "),
        });
        Object.keys(inCycle).forEach(function (id) {
            delete parentByChildId[id];
        });
    }

    // 7. Mark consumed edges as hidden (only for accepted assignments).
    Object.keys(consumedEdges).forEach(function (edgeId) {
        var pair = consumedEdges[edgeId];
        var parentId = pair[0], childId = pair[1];
        if (parentByChildId[childId] === parentId) {
            hiddenEdgeIds.add(edgeId);
        }
    });

    return { parentByChildId: parentByChildId, hiddenEdgeIds: hiddenEdgeIds, warnings: warnings };
};


// ---------------------------------------------------------------------------
// TapParentLabelOverlay — lightweight HTML label positioner for parent nodes.
//
// The cytoscape-node-html-label plugin cannot reliably position compound node
// labels because its one("render") bootstrap fires before layout, when
// compound node dimensions are NaN.  This overlay creates and positions
// label divs directly, hooking into layoutstop, pan/zoom, and position/bounds
// events after layout completes and dimensions are stable.
// ---------------------------------------------------------------------------

function TapParentLabelOverlay(cy, parentLabelData) {
    this._cy = cy;
    this._data = parentLabelData;  // { entityId: { label, icon_url, config } }
    this._container = null;        // outer div (pan/zoom transformed)
    this._els = {};                // entityId -> wrapper div
}

TapParentLabelOverlay.prototype.init = function () {
    var self = this;
    var cyContainer = this._cy.container();

    // Create overlay container next to the canvas.
    var el = document.createElement("div");
    var canvas = cyContainer.querySelector("canvas");
    var s = el.style;
    s.position = "absolute";
    s.zIndex = "10";
    s.width = "500px";
    s.margin = s.padding = s.border = s.outline = "0px";
    s.pointerEvents = "none";
    s.transformOrigin = "top left";
    canvas.parentNode.appendChild(el);
    this._container = el;

    // Create a wrapper per parent node.
    this._cy.nodes(":parent").forEach(function (node) {
        var id = node.id();
        var pl = self._data[id];
        if (!pl) return;

        var wrapper = document.createElement("div");
        wrapper.style.position = "absolute";

        var escapedLabel = _escapeHtml(pl.label);
        var iconHtml = pl.icon_url
            ? '<img class="tap-parent-label__icon" src="' + _escapeHtml(pl.icon_url) + '" alt="" />'
            : "";
        wrapper.innerHTML = '<div class="tap-parent-label">' + iconHtml +
            '<span class="tap-parent-label__text">' + escapedLabel + "</span></div>";

        el.appendChild(wrapper);
        self._els[id] = wrapper;
    });

    // Initial sync.
    this._syncPanZoom();
    this._syncAllPositions();

    // Bind events.
    this._cy.on("pan zoom", function () { self._syncPanZoom(); });
    this._cy.on("layoutstop", function () { self._syncAllPositions(); });
    this._cy.on("position bounds", "node:parent", function (evt) {
        self._syncPosition(evt.target);
    });
};

TapParentLabelOverlay.prototype._syncPanZoom = function () {
    var pan = this._cy.pan();
    var zoom = this._cy.zoom();
    var t = "translate(" + pan.x + "px," + pan.y + "px) scale(" + zoom + ")";
    var s = this._container.style;
    s.webkitTransform = t;
    s.msTransform = t;
    s.transform = t;
};

TapParentLabelOverlay.prototype._syncAllPositions = function () {
    var self = this;
    this._cy.nodes(":parent").forEach(function (node) {
        self._syncPosition(node);
    });
};

TapParentLabelOverlay.prototype._syncPosition = function (node) {
    var wrapper = this._els[node.id()];
    if (!wrapper) return;

    var pos = node.position();
    var w = node.width();
    var h = node.height();

    // Guard against pre-layout NaN dimensions.
    if (isNaN(pos.x) || isNaN(pos.y) || isNaN(w) || isNaN(h)) return;

    // Position at horizontal center, vertical top of compound node.
    var x = pos.x;
    var y = pos.y - h / 2;

    var t = "translate(-50%, -100%) translate(" + x.toFixed(2) + "px," + y.toFixed(2) + "px)";
    var s = wrapper.style;
    s.webkitTransform = t;
    s.msTransform = t;
    s.transform = t;
};


// ---------------------------------------------------------------------------
// initGraph — main entry point per graph panel
// ---------------------------------------------------------------------------

function initGraph(panelId) {
    const nodesEl = document.getElementById("tap-graph-nodes-" + panelId);
    const edgesEl = document.getElementById("tap-graph-edges-" + panelId);
    const container = document.getElementById("tap-graph-container-" + panelId);
    const cyEl = document.getElementById("tap-graph-" + panelId);

    if (!nodesEl || !edgesEl || !container || !cyEl) return;

    const nodes = JSON.parse(nodesEl.textContent || "[]");
    const edges = JSON.parse(edgesEl.textContent || "[]");

    if (nodes.length === 0) {
        cyEl.innerHTML = '<p class="text-sm text-slate-400 p-4">No nodes to display.</p>';
        return;
    }

    // Nesting resolution — gated by layout flag.
    var nestingEnabled = container.dataset.nesting === "true";
    var nesting = { parentByChildId: {}, hiddenEdgeIds: new Set(), warnings: [] };

    if (nestingEnabled) {
        var resolver = new TapVizNestingResolver(nodes, edges);
        nesting = resolver.resolve();
        nesting.warnings.forEach(function (w) {
            console.warn("[TAP Nesting]", w.category, w.message);
        });
    }

    // Collect the set of entity IDs that are actual parents (have children).
    var parentIds = new Set();
    Object.keys(nesting.parentByChildId).forEach(function (childId) {
        parentIds.add(nesting.parentByChildId[childId]);
    });

    // Build per-parent metadata for HTML label rendering.
    // parentLabelData: { entityId: { label, icon_url, config } }
    var parentLabelData = {};
    if (parentIds.size > 0) {
        nodes.forEach(function (n) {
            var ent = n.entity || {};
            if (!parentIds.has(ent.entity_id)) return;
            var nestingMeta = ((n.display || {}).nesting) || {};
            var plConfig = nestingMeta.parent_label || {};
            parentLabelData[ent.entity_id] = {
                label: ent.name || ent.entity_type || ent.entity_id,
                icon_url: n.icon_url || "",
                config: {
                    horizontal_alignment: plConfig.horizontal_alignment || "center",
                    vertical_alignment: plConfig.vertical_alignment || "top",
                    inside_or_outside: plConfig.inside_or_outside || "outside",
                },
            };
        });
    }

    // Build Cytoscape elements from GRIFT extended node/edge envelopes.
    const cyNodes = nodes.map(function (n) {
        var ent = n.entity || {};
        var data = {
            id: ent.entity_id,
            label: ent.name || ent.entity_type || ent.entity_id,
            entity_type: ent.entity_type || "",
            icon_url: n.icon_url || "",
            shape: n.shape || "ellipse",
            url_id: n.url_id || "",
        };
        if (nesting.parentByChildId[ent.entity_id]) {
            data.parent = nesting.parentByChildId[ent.entity_id];
        }
        return { data: data };
    });

    const nodeIds = new Set(nodes.map(function (n) { return n.entity.entity_id; }));
    const cyEdges = edges
        .filter(function (e) {
            var ed = e.edge || {};
            return nodeIds.has(ed.from_entity_id) && nodeIds.has(ed.to_entity_id);
        })
        .map(function (e) {
            var ent = e.entity || {};
            var ed = e.edge || {};
            var edgeId = ent.entity_id || (ed.from_entity_id + "-" + ed.to_entity_id + "-" + ed.edge_type);
            var classes = nesting.hiddenEdgeIds.has(edgeId) ? "tap-nesting-hidden" : "";
            return {
                data: {
                    id: edgeId,
                    source: ed.from_entity_id,
                    target: ed.to_entity_id,
                    label: ed.edge_type || "",
                },
                classes: classes,
            };
        });

    const placement = container.dataset.placement || "cytoscape:cose";
    const cy = cytoscape({
        container: cyEl,
        elements: cyNodes.concat(cyEdges),
        style: [
            {
                // Base node style — solid colour, used when no icon resolves.
                selector: "node",
                style: {
                    "shape": "data(shape)",
                    "background-color": "#4f46e5",
                    "label": "data(label)",
                    "color": "#1e293b",
                    "font-size": "11px",
                    "text-valign": "bottom",
                    "text-margin-y": "4px",
                    "width": 40,
                    "height": 40,
                },
            },
            {
                // Nodes that have a resolved icon URL: show the icon over a
                // light background so the SVG is legible.
                selector: "node[icon_url != '']",
                style: {
                    "background-color": "#e0e7ff",
                    "background-image": "data(icon_url)",
                    "background-fit": "none",
                    "background-width": "65%",
                    "background-height": "65%",
                    "background-position-x": "50%",
                    "background-position-y": "50%",
                    "background-clip": "none",
                    "background-image-opacity": 1,
                },
            },
            {
                selector: "edge",
                style: {
                    "width": 2,
                    "line-color": "#94a3b8",
                    "target-arrow-color": "#94a3b8",
                    "target-arrow-shape": "triangle",
                    "curve-style": "bezier",
                    "label": "data(label)",
                    "font-size": "9px",
                    "color": "#64748b",
                },
            },
            {
                // Compound parent nodes (nesting containers).
                // Normal text label and background-image icon are suppressed;
                // parent-label HTML overlay handles icon + text rendering.
                selector: ":parent",
                style: {
                    "background-opacity": 0.08,
                    "background-image": "none",
                    "border-width": 2,
                    "border-color": "#94a3b8",
                    "padding": "30px",
                    "label": "",
                },
            },
            {
                // Hidden containment edges (consumed by nesting).
                selector: ".tap-nesting-hidden",
                style: { "display": "none" },
            },
            {
                selector: ":selected",
                style: {
                    "background-color": "#7c3aed",
                    "line-color": "#7c3aed",
                    "target-arrow-color": "#7c3aed",
                },
            },
        ],
        userZoomingEnabled: true,
        userPanningEnabled: true,
        boxSelectionEnabled: true,
    });

    // Light background grid via cytoscape-grid-guide extension.
    if (cy.gridGuide) {
        cy.gridGuide({
            drawGrid: true,
            gridSpacing: 40,
            gridColor: "#cbd5e1",
            lineWidth: 1.0,
            gridStackOrder: -1,
            snapToGridOnRelease: false,
            snapToGridDuringDrag: false,
            snapToAlignmentLocationOnRelease: false,
            snapToAlignmentLocationDuringDrag: false,
            distributionGuidelines: false,
            geometricGuideline: false,
            resize: false,
            parentPadding: false,
            zoomDash: true,
            panGrid: true,
        });
    }

    // Register before running layout so we catch layoutstop even for
    // synchronous layouts (cose with animate:false fires before the
    // constructor returns if layout is passed inline).
    cy.one("layoutstop", function () {
        cy.minZoom(cy.zoom());

        // Parent-label HTML overlay — initialized after layout so compound
        // node positions and dimensions are stable.
        if (parentIds.size > 0) {
            var overlay = new TapParentLabelOverlay(cy, parentLabelData);
            overlay.init();
        }
    });

    cy.layout(_buildLayout(placement)).run();

    _attachToolbar(container, cy);

    // Node tap → navigate to the object viewer (req-viz-panel-node-nav).
    cy.on("tap", "node", function (evt) {
        var node = evt.target;
        var entityType = node.data("entity_type");
        var urlId = node.data("url_id");
        if (entityType && urlId) {
            window.location.href = "/object/" + entityType + "/" + urlId + "/";
        }
    });
}

function _buildLayout(placement) {
    if (placement === "cytoscape:grid") {
        return { name: "grid", fit: true, padding: 30 };
    }
    if (placement === "cytoscape:preset") {
        return { name: "preset" };
    }
    // cytoscape:cose (default)
    return {
        name: "cose",
        idealEdgeLength: 100,
        nodeOverlap: 20,
        fit: true,
        padding: 30,
        randomize: false,
        componentSpacing: 80,
        nodeRepulsion: 400000,
        edgeElasticity: 100,
        gravity: 80,
        numIter: 1000,
        initialTemp: 200,
        coolingFactor: 0.95,
        minTemp: 1.0,
    };
}

function _attachToolbar(container, cy) {
    // Guarantee the container is the positioning context regardless of class resolution order.
    container.style.position = "relative";

    const toolbar = document.createElement("div");
    toolbar.className = "tap-cy-toolbar";
    toolbar.innerHTML = [
        '<button class="tap-cy-btn" data-action="zoom-in" title="Zoom in">',
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">',
        '<circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>',
        '<line x1="11" y1="8" x2="11" y2="14"></line><line x1="8" y1="11" x2="14" y2="11"></line>',
        "</svg></button>",
        '<button class="tap-cy-btn" data-action="zoom-out" title="Zoom out">',
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">',
        '<circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>',
        '<line x1="8" y1="11" x2="14" y2="11"></line>',
        "</svg></button>",
        '<button class="tap-cy-btn" data-action="fit" title="Fit to view">',
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">',
        '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>',
        "</svg></button>",
        '<div class="tap-cy-sep"></div>',
        '<button class="tap-cy-btn" data-action="fullscreen" title="Toggle fullscreen">',
        '<svg class="tap-cy-expand" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">',
        '<polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline>',
        '<line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line>',
        "</svg>",
        '<svg class="tap-cy-compress" style="display:none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">',
        '<polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline>',
        '<line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line>',
        "</svg>",
        "</button>",
    ].join("");

    container.appendChild(toolbar);

    toolbar.addEventListener("click", function (e) {
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const action = btn.dataset.action;
        if (action === "zoom-in") cy.zoom(cy.zoom() * 1.2);
        else if (action === "zoom-out") cy.zoom(cy.zoom() / 1.2);
        else if (action === "fit") cy.fit();
        else if (action === "fullscreen") _toggleFullscreen(container, cy, btn);
    });

    document.addEventListener("fullscreenchange", function () {
        if (!document.fullscreenElement) {
            const btn = toolbar.querySelector("[data-action='fullscreen']");
            if (btn) _syncFullscreenIcon(btn, false);
            setTimeout(function () { cy.resize(); cy.fit(); }, 100);
        }
    });
}

function _toggleFullscreen(container, cy, btn) {
    if (!document.fullscreenElement) {
        container.requestFullscreen().then(function () {
            _syncFullscreenIcon(btn, true);
            setTimeout(function () { cy.resize(); cy.fit(); }, 100);
        });
    } else {
        document.exitFullscreen();
    }
}

function _syncFullscreenIcon(btn, isFullscreen) {
    const expand = btn.querySelector(".tap-cy-expand");
    const compress = btn.querySelector(".tap-cy-compress");
    if (expand) expand.style.display = isFullscreen ? "none" : "";
    if (compress) compress.style.display = isFullscreen ? "" : "none";
}

function _escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
