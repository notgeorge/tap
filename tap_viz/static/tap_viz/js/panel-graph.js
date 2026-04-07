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

    // Build Cytoscape elements from GRIFT extended node/edge envelopes.
    const cyNodes = nodes.map(function (n) {
        var ent = n.entity || {};
        return {
            data: {
                id: ent.entity_id,
                label: ent.name || ent.entity_type || ent.entity_id,
                entity_type: ent.entity_type || "",
                icon_url: n.icon_url || "",
                shape: n.shape || "ellipse",
                url_id: n.url_id || "",
            },
        };
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
            return {
                data: {
                    id: ent.entity_id || (ed.from_entity_id + "-" + ed.to_entity_id + "-" + ed.edge_type),
                    source: ed.from_entity_id,
                    target: ed.to_entity_id,
                    label: ed.edge_type || "",
                },
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

    // Register before running layout so we catch layoutstop even for
    // synchronous layouts (cose with animate:false fires before the
    // constructor returns if layout is passed inline).
    cy.one("layoutstop", function () {
        cy.minZoom(cy.zoom());
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
