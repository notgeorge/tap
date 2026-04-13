/**
 * cytoscape-tap-dimensions — independently-sized compound parents.
 *
 * Cytoscape's native compound nodes auto-size to their children's union bbox.
 * This plugin lets layout code declare a fixed `{width, height, padding}` per
 * parent and enforces it via two invisible "anchor" child nodes locked at the
 * parent's intended top-left and bottom-right corners. Parents bbox then
 * equals the union of real children and the anchor points.
 *
 * API (v0):
 *   var td = cy.tapDimensions();
 *   td.set(parentId, {width, height, padding});
 *   td.layoutRecursive({defaultLayout: {name: "grid"}, layoutForParent: fn});
 *   td.warnings();                    // collected warnings this run
 *   td.isAnchor(nodeOrId);            // true if synthetic anchor
 *
 * Recursion is post-order: deepest parents first, so each parent's layout
 * sees its children already at their settled bbox. If declared dimensions
 * are too small, they auto-expand to the children's actual bbox and a
 * `tap_dimensions_auto_expanded` warning is emitted.
 */

(function (global, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory;
    } else if (global && global.cytoscape) {
        factory(global.cytoscape);
    }
})(typeof window !== "undefined" ? window : this, function (cytoscape) {
    if (!cytoscape) return;

    var ANCHOR_CLASS = "tap-dim-anchor";
    var ANCHOR_PREFIX_TL = "__tap_dim_tl__";
    var ANCHOR_PREFIX_BR = "__tap_dim_br__";
    var DEFAULT_PADDING = 20;

    function TapDimensions(cy) {
        this._cy = cy;
        this._declared = {}; // parentId -> {width, height, padding}
        this._warnings = [];
        this._installAnchorStyle();
    }

    TapDimensions.prototype._installAnchorStyle = function () {
        var style = this._cy.style();
        if (!style) return;
        style
            .selector("." + ANCHOR_CLASS)
            .style({
                width: 1,
                height: 1,
                "background-opacity": 0,
                "border-width": 0,
                opacity: 0,
                events: "no",
                label: "",
            })
            .update();
    };

    TapDimensions.prototype.set = function (parentId, dim) {
        if (!parentId) throw new Error("tapDimensions.set: parentId required");
        this._declared[parentId] = {
            width: dim && dim.width > 0 ? dim.width : 0,
            height: dim && dim.height > 0 ? dim.height : 0,
            padding: dim && dim.padding != null ? dim.padding : DEFAULT_PADDING,
        };
    };

    TapDimensions.prototype.get = function (parentId) {
        var d = this._declared[parentId];
        return d ? {width: d.width, height: d.height, padding: d.padding} : null;
    };

    TapDimensions.prototype.warnings = function () {
        return this._warnings.slice();
    };

    TapDimensions.prototype.clearWarnings = function () {
        this._warnings = [];
    };

    TapDimensions.prototype.isAnchor = function (nodeOrId) {
        var id = typeof nodeOrId === "string" ? nodeOrId : nodeOrId && nodeOrId.id && nodeOrId.id();
        if (!id) return false;
        return id.indexOf(ANCHOR_PREFIX_TL) === 0 || id.indexOf(ANCHOR_PREFIX_BR) === 0;
    };

    TapDimensions.prototype.anchorSelector = function () {
        return "." + ANCHOR_CLASS;
    };

    TapDimensions.prototype.realNodes = function (collection) {
        var sel = "." + ANCHOR_CLASS;
        return collection ? collection.not(sel) : this._cy.nodes().not(sel);
    };

    TapDimensions.prototype.layoutRecursive = function (opts) {
        opts = opts || {};
        var defaultLayout = opts.defaultLayout || {name: "grid"};
        var layoutForParent = opts.layoutForParent || null;
        var cy = this._cy;
        var self = this;

        // 1. Collect all parents and compute depths.
        var parents = cy.nodes(":parent").not("." + ANCHOR_CLASS);
        if (parents.length === 0) return;

        var parentDepth = {};
        parents.forEach(function (p) {
            var d = 0;
            var cur = p.parent();
            while (cur && cur.length) {
                d++;
                cur = cur.parent();
            }
            parentDepth[p.id()] = d;
        });

        // 2. Sort deepest-first (post-order).
        var ordered = parents.toArray().slice().sort(function (a, b) {
            return parentDepth[b.id()] - parentDepth[a.id()];
        });

        // 3. For each parent, sub-layout its real children inside declared rect.
        ordered.forEach(function (parent) {
            self._layoutOneParent(parent, defaultLayout, layoutForParent);
        });
    };

    TapDimensions.prototype._layoutOneParent = function (parent, defaultLayout, layoutForParent) {
        var cy = this._cy;
        var parentId = parent.id();
        var declared = this._declared[parentId] || {};
        var padding = declared.padding != null ? declared.padding : DEFAULT_PADDING;

        // Real children = direct children minus any anchors we may have added.
        var realChildren = parent.children().not("." + ANCHOR_CLASS);
        if (realChildren.length === 0) return;

        var declaredW = declared.width || 0;
        var declaredH = declared.height || 0;

        // If any child is itself a compound parent, cytoscape's built-in grid
        // places them by center-point without honoring their real widths. For
        // those cases we use a size-aware manual grid instead.
        var anyCompoundChild = false;
        realChildren.forEach(function (c) {
            if (c.isParent()) anyCompoundChild = true;
        });

        if (anyCompoundChild) {
            this._manualGrid(realChildren, padding);
        } else {
            var bboxW = declaredW > 0 ? declaredW - 2 * padding : 400;
            var bboxH = declaredH > 0 ? declaredH - 2 * padding : 400;
            var layoutOpts = layoutForParent ? layoutForParent(parent) : null;
            layoutOpts = Object.assign({}, defaultLayout, layoutOpts || {}, {
                boundingBox: {x1: 0, y1: 0, x2: Math.max(bboxW, 1), y2: Math.max(bboxH, 1)},
                fit: false,
                animate: false,
                avoidOverlap: true,
                avoidOverlapPadding: 10,
            });
            var layout = realChildren.layout(layoutOpts);
            layout.run();
        }

        // Measure actual children bbox post-layout.
        var bb = realChildren.boundingBox();
        var actualW = bb.w;
        var actualH = bb.h;

        // Auto-expand: declared is a floor. Pick final rect, warn if grown.
        var finalInnerW = Math.max(declaredW > 0 ? declaredW - 2 * padding : 0, actualW);
        var finalInnerH = Math.max(declaredH > 0 ? declaredH - 2 * padding : 0, actualH);
        var finalW = finalInnerW + 2 * padding;
        var finalH = finalInnerH + 2 * padding;

        if ((declaredW > 0 && finalW > declaredW) || (declaredH > 0 && finalH > declaredH)) {
            this._warnings.push({
                category: "tap_dimensions_auto_expanded",
                parent_id: parentId,
                declared: {width: declaredW, height: declaredH},
                actual: {width: finalW, height: finalH},
            });
        }

        // Place anchors at final rect corners, sized relative to current children origin.
        var cornerX1 = bb.x1 - padding;
        var cornerY1 = bb.y1 - padding;
        var cornerX2 = cornerX1 + finalW;
        var cornerY2 = cornerY1 + finalH;

        this._ensureAnchors(parentId, cornerX1, cornerY1, cornerX2, cornerY2);
    };

    TapDimensions.prototype._manualGrid = function (children, padding) {
        var maxW = 0;
        var maxH = 0;
        children.forEach(function (c) {
            var w = c.width() || 40;
            var h = c.height() || 40;
            if (w > maxW) maxW = w;
            if (h > maxH) maxH = h;
        });
        var spacing = padding;
        var cellW = maxW + spacing;
        var cellH = maxH + spacing;
        var n = children.length;
        var cols = Math.max(1, Math.ceil(Math.sqrt(n)));
        children.forEach(function (c, i) {
            var col = i % cols;
            var row = Math.floor(i / cols);
            c.position({
                x: col * cellW + cellW / 2,
                y: row * cellH + cellH / 2,
            });
        });
    };

    TapDimensions.prototype._ensureAnchors = function (parentId, x1, y1, x2, y2) {
        var cy = this._cy;
        var tlId = ANCHOR_PREFIX_TL + parentId;
        var brId = ANCHOR_PREFIX_BR + parentId;

        var tl = cy.getElementById(tlId);
        if (tl.empty()) {
            tl = cy.add({
                group: "nodes",
                data: {id: tlId, parent: parentId},
                classes: ANCHOR_CLASS,
                selectable: false,
                grabbable: false,
            });
        }
        tl.position({x: x1, y: y1});

        var br = cy.getElementById(brId);
        if (br.empty()) {
            br = cy.add({
                group: "nodes",
                data: {id: brId, parent: parentId},
                classes: ANCHOR_CLASS,
                selectable: false,
                grabbable: false,
            });
        }
        br.position({x: x2, y: y2});
    };

    // Register as a core cytoscape extension: `cy.tapDimensions()`.
    cytoscape("core", "tapDimensions", function () {
        if (!this.scratch("_tapDimensions")) {
            this.scratch("_tapDimensions", new TapDimensions(this));
        }
        return this.scratch("_tapDimensions");
    });
});
