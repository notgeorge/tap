/**
 * panel-ksi-compliance.js — FedRAMP 20x KSI Compliance View browser glue.
 *
 * Reads a raw gryphon subgraph envelope ({nodes, edges}) from an embedded
 * JSON payload, joins indicators to themes via CONTAINS_INDICATOR edges,
 * and renders a grouped Tabulator table with client-side keyword search
 * and certification class filtering.
 */

(function () {
  "use strict";

  // Hard fallback used only if the server-rendered default JSON is missing or
  // unparseable. The server resolves the real default from the FedRAMP 20x
  // ComplianceContext (regime="fedramp_20x") and renders it into the
  // ksi-default-class-<panelId> script tag — see compliance_view.html and
  // spec-fedramp-20x-ksi-compliance-view.md req-ksi-compview-class-select.
  var FALLBACK_CLASS = "all";

  var CLASS_LABELS = {
    a: "A",
    b: "B",
    c: "C",
    d: "D",
  };

  // -------------------------------------------------------------------------
  // Subgraph processing
  // -------------------------------------------------------------------------

  /**
   * Transform a raw subgraph envelope into a flat array of indicator row objects,
   * each enriched with parent theme metadata.
   */
  // Three-lane envelope adapter (spec-grift-envelope). Gryphon's "extended"
  // layer puts spine fields (entity_id, entity_type, name) at the top level
  // of each node, per-model fields under `data`, and display hints under
  // `display`. Earlier callers wrapped these in nested `entity` / `node`
  // sub-objects. We accept either shape so the JS keeps working if the
  // serializer reverts or a different layer is ever served.
  function spine(n) {
    return {
      entity_id: n.entity_id || (n.entity && n.entity.entity_id) || "",
      entity_type: n.entity_type || (n.entity && n.entity.entity_type) || "",
      name: n.name || (n.entity && n.entity.name) || "",
      data: n.data || n.node || {},
      url_id:
        (n.display && n.display.tap_viz && n.display.tap_viz.url_id) ||
        n.url_id ||
        "",
      icon_url:
        (n.display && n.display.tap_viz && n.display.tap_viz.icon_url) ||
        n.icon_url ||
        "",
    };
  }

  function buildRows(subgraph) {
    var nodes = subgraph.nodes || [];
    var edges = subgraph.edges || [];

    // Separate themes and indicators by entity_type.
    var themes = {};
    var indicators = [];
    for (var i = 0; i < nodes.length; i++) {
      var s = spine(nodes[i]);
      if (s.entity_type === "ksi_theme") {
        themes[s.entity_id] = nodes[i];
      } else if (s.entity_type === "ksi_indicator") {
        indicators.push(nodes[i]);
      }
    }

    // Build indicator-to-theme mapping from CONTAINS_INDICATOR edges.
    var indicatorToTheme = {};
    for (var j = 0; j < edges.length; j++) {
      var e = edges[j];
      var edgeData = e.edge || e;
      if (edgeData.edge_type === "CONTAINS_INDICATOR") {
        indicatorToTheme[edgeData.to_entity_id] = edgeData.from_entity_id;
      }
    }

    // Build flat row array.
    var rows = [];
    for (var k = 0; k < indicators.length; k++) {
      var ind = spine(indicators[k]);
      var themeId = indicatorToTheme[ind.entity_id] || "";
      var theme = themes[themeId] ? spine(themes[themeId]) : null;

      rows.push({
        // Indicator fields
        entity_id: ind.entity_id,
        code: ind.data.code || "",
        name: ind.data.name || ind.name || "",
        description: ind.data.description || "",
        classes: ind.data.classes || [],
        class_variants: ind.data.class_variants || null,
        controls: ind.data.controls || [],
        status: ind.data.status || "",
        terms: ind.data.terms || [],
        url_id: ind.url_id,
        // Theme fields
        theme_code: theme ? (theme.data.code || "") : "",
        theme_name: theme ? (theme.name || theme.data.name || "") : "",
        theme_short_name: theme ? (theme.data.short_name || "") : "",
        theme_sort_order: theme ? (theme.data.sort_order || 0) : 0,
        theme_icon_url: theme ? theme.icon_url : "",
      });
    }

    // Sort by theme order, then indicator code.
    rows.sort(function (a, b) {
      if (a.theme_sort_order !== b.theme_sort_order) {
        return a.theme_sort_order - b.theme_sort_order;
      }
      return a.code < b.code ? -1 : a.code > b.code ? 1 : 0;
    });

    return rows;
  }

  // -------------------------------------------------------------------------
  // Statement resolution
  // -------------------------------------------------------------------------

  /**
   * Render statement text into a container element, replacing **Optional:**
   * with a styled tag.
   */
  function renderStatementInto(container, text) {
    container.textContent = "";
    if (text.indexOf("**Optional:**") === 0) {
      var tag = document.createElement("span");
      tag.className = "ksi-optional-tag";
      tag.textContent = "Optional";
      container.appendChild(tag);
      container.appendChild(
        document.createTextNode(" " + text.replace("**Optional:** ", ""))
      );
    } else {
      container.textContent = text;
    }
  }

  /**
   * Check whether a row has class-specific statement variants.
   */
  function hasVariants(row) {
    return row.class_variants && Object.keys(row.class_variants).length > 0;
  }

  /**
   * Resolve the display statement for an indicator given a class.
   * If the class is "all" or the indicator has no class_variants, return
   * the direct description. Otherwise return the class-specific statement.
   */
  function resolveStatement(row, cls) {
    if (cls !== "all" && row.class_variants && row.class_variants[cls]) {
      return row.class_variants[cls].statement || "";
    }
    return row.description || "";
  }

  /**
   * Build a searchable text blob from all indicator text fields.
   */
  function buildSearchBlob(row) {
    var parts = [
      row.code,
      row.name,
      row.description,
      (row.controls || []).join(" "),
      (row.terms || []).join(" "),
    ];
    // Include all class_variant statements.
    if (row.class_variants) {
      var keys = Object.keys(row.class_variants);
      for (var i = 0; i < keys.length; i++) {
        var v = row.class_variants[keys[i]];
        if (v && v.statement) {
          parts.push(v.statement);
        }
      }
    }
    return parts.join(" ").toLowerCase();
  }

  // -------------------------------------------------------------------------
  // Panel initialization
  // -------------------------------------------------------------------------

  function initPanel(mount) {
    var panelId = mount.getAttribute("data-ksi-panel-id");
    var iconsBase = mount.getAttribute("data-static-icons") || "";

    // Read embedded JSON payload.
    var dataEl = document.getElementById("ksi-data-" + panelId);
    if (!dataEl) return;
    var subgraph;
    try {
      subgraph = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }

    var rows = buildRows(subgraph);
    var totalCount = rows.length;

    // Pre-compute search blobs.
    for (var i = 0; i < rows.length; i++) {
      rows[i]._searchBlob = buildSearchBlob(rows[i]);
    }

    // Controls.
    var searchInput = document.getElementById("ksi-search-" + panelId);
    var classSelect = document.getElementById("ksi-class-select-" + panelId);
    var countSpan = document.getElementById("ksi-count-" + panelId);

    // Server-rendered default class from the FedRAMP 20x ComplianceContext.
    var serverDefault = FALLBACK_CLASS;
    var defaultEl = document.getElementById("ksi-default-class-" + panelId);
    if (defaultEl) {
      try {
        var parsed = JSON.parse(defaultEl.textContent || "");
        if (parsed === "all" || CLASS_LABELS[parsed]) {
          serverDefault = parsed;
        }
      } catch (e) {
        // Malformed payload — keep fallback.
      }
    }
    if (classSelect) {
      classSelect.value = serverDefault;
    }

    var selectedClass = serverDefault;

    // Per-row class overrides: entity_id -> class letter.
    // When a user clicks a badge on a row with class_variants, the override
    // is set for that row, changing its Statement text independently of the
    // global class selector.
    var rowClassOverrides = {};

    /**
     * Get the effective class for a row: per-row override if set, else global.
     */
    function effectiveClass(row) {
      return rowClassOverrides[row.entity_id] || selectedClass;
    }

    /**
     * Fade-swap the statement text in a cell's span element.
     */
    function fadeSwapStatement(cell, newText) {
      var el = cell.getElement();
      var span = el.querySelector(".ksi-statement-text");
      if (!span) return;
      span.classList.add("ksi-statement-fade-out");
      setTimeout(function () {
        renderStatementInto(span, newText);
        span.classList.remove("ksi-statement-fade-out");
        span.classList.add("ksi-statement-fade-in");
        setTimeout(function () {
          span.classList.remove("ksi-statement-fade-in");
        }, 200);
      }, 150);
    }

    // Tabulator column definitions.
    var columns = [
      {
        title: "Code",
        field: "code",
        width: 140,
        formatter: function (cell) {
          var row = cell.getRow().getData();
          var a = document.createElement("a");
          a.href = "/fedramp-ksi/indicator?entity_id=" + row.entity_id;
          a.textContent = row.code;
          a.className = "ksi-code-link";
          return a;
        },
      },
      {
        title: "Name",
        field: "name",
        widthGrow: 1,
      },
      {
        title: "Statement",
        field: "description",
        widthGrow: 3,
        formatter: function (cell) {
          var row = cell.getRow().getData();
          var ec = effectiveClass(row);
          var text = resolveStatement(row, ec);
          var span = document.createElement("span");
          span.className = "ksi-statement-text";
          renderStatementInto(span, text);
          return span;
        },
      },
      {
        title: "Classes",
        field: "classes",
        width: 120,
        hozAlign: "center",
        headerSort: false,
        formatter: function (cell) {
          var cls = cell.getValue() || [];
          var row = cell.getRow().getData();
          var rowHasVariants = hasVariants(row);
          var ec = effectiveClass(row);
          var container = document.createElement("span");
          container.className = "ksi-class-badges";

          for (var i = 0; i < cls.length; i++) {
            var badge = document.createElement("span");
            badge.className = "ksi-class-badge";

            if (!rowHasVariants) {
              // No variants: all badges are active (universal statement).
              badge.className += " ksi-class-badge--active";
            } else {
              // Has variants: highlight the effective class, make clickable.
              if (ec !== "all" && cls[i] === ec) {
                badge.className += " ksi-class-badge--active";
              }
              badge.className += " ksi-class-badge--clickable";
              badge.setAttribute("data-class", cls[i]);
              badge.setAttribute("data-entity-id", row.entity_id);
            }

            badge.textContent = CLASS_LABELS[cls[i]] || cls[i];
            container.appendChild(badge);
          }
          return container;
        },
      },
      {
        title: "Controls",
        field: "controls",
        widthGrow: 1,
        formatter: function (cell) {
          var ctrls = cell.getValue() || [];
          return ctrls.join(", ");
        },
      },
      {
        title: "Status",
        field: "status",
        width: 100,
        hozAlign: "center",
        formatter: function (cell) {
          var val = cell.getValue() || "";
          var span = document.createElement("span");
          span.className = "ksi-status ksi-status--" + val;
          span.textContent = val;
          return span;
        },
      },
      {
        // Hidden sort column for theme ordering.
        title: "",
        field: "theme_sort_order",
        visible: false,
      },
    ];

    // Build ordered theme code list from pre-sorted rows.
    var orderedThemeCodes = [];
    var seenThemes = {};
    for (var t = 0; t < rows.length; t++) {
      if (!seenThemes[rows[t].theme_code]) {
        seenThemes[rows[t].theme_code] = true;
        orderedThemeCodes.push(rows[t].theme_code);
      }
    }

    // Initialize Tabulator.
    var table = new Tabulator(mount, {
      data: rows,
      layout: "fitColumns",
      groupBy: "theme_code",
      groupValues: [orderedThemeCodes],
      groupStartOpen: true,
      groupToggleElement: "header",
      groupHeader: function (value, count) {
        var themeRow = null;
        for (var i = 0; i < rows.length; i++) {
          if (rows[i].theme_code === value) {
            themeRow = rows[i];
            break;
          }
        }

        var container = document.createElement("span");
        container.className = "ksi-group-header";

        // Theme icon.
        if (themeRow && themeRow.theme_icon_url) {
          var img = document.createElement("img");
          img.src = themeRow.theme_icon_url;
          img.alt = "";
          img.className = "ksi-group-icon";
          container.appendChild(img);
        } else if (themeRow && themeRow.theme_short_name && iconsBase) {
          var img2 = document.createElement("img");
          img2.src =
            iconsBase + "ksi-" + themeRow.theme_short_name.toLowerCase() + ".svg";
          img2.alt = "";
          img2.className = "ksi-group-icon";
          container.appendChild(img2);
        }

        // Theme name + count.
        var nameSpan = document.createElement("span");
        nameSpan.className = "ksi-group-name";
        nameSpan.textContent =
          (themeRow ? themeRow.theme_name : value) +
          " (" + count + ")";
        container.appendChild(nameSpan);

        return container;
      },
      initialSort: [
        { column: "theme_sort_order", dir: "asc" },
        { column: "code", dir: "asc" },
      ],
      columns: columns,
    });

    // -------------------------------------------------------------------
    // Row click → navigate to indicator profile
    // -------------------------------------------------------------------

    table.on("rowClick", function (e, row) {
      // Don't navigate if clicking a class badge or a link.
      if (e.target.closest(".ksi-class-badge") || e.target.closest("a")) return;
      var data = row.getData();
      if (data.entity_id) {
        window.location.href =
          "/fedramp-ksi/indicator?entity_id=" + data.entity_id;
      }
    });

    // -------------------------------------------------------------------
    // Per-row class badge click handler
    // -------------------------------------------------------------------

    mount.addEventListener("click", function (evt) {
      var badge = evt.target.closest(".ksi-class-badge--clickable");
      if (!badge) return;

      var clickedClass = badge.getAttribute("data-class");
      var entityId = badge.getAttribute("data-entity-id");
      if (!clickedClass || !entityId) return;

      // Set the per-row override.
      rowClassOverrides[entityId] = clickedClass;

      // Find the Tabulator row and update the Statement + Classes cells.
      var tabulatorRows = table.getRows("active");
      for (var i = 0; i < tabulatorRows.length; i++) {
        var rd = tabulatorRows[i].getData();
        if (rd.entity_id === entityId) {
          // Re-render the Classes cell to update badge highlighting.
          tabulatorRows[i].reformat();

          // Fade-swap the statement text.
          var cells = tabulatorRows[i].getCells();
          for (var j = 0; j < cells.length; j++) {
            if (cells[j].getField() === "description") {
              var newText = resolveStatement(rd, clickedClass);
              fadeSwapStatement(cells[j], newText);
              break;
            }
          }
          break;
        }
      }
    });

    // -------------------------------------------------------------------
    // Filtering
    // -------------------------------------------------------------------

    var searchTerm = "";

    function hideEmptyGroups() {
      var groupEls = mount.querySelectorAll(".tabulator-group");
      groupEls.forEach(function (groupEl) {
        // Walk forward from the group header and count visible data rows
        // until the next group header or end of table.
        var visibleCount = 0;
        var sibling = groupEl.nextElementSibling;
        while (sibling && !sibling.classList.contains("tabulator-group")) {
          if (
            sibling.classList.contains("tabulator-row") &&
            sibling.style.display !== "none"
          ) {
            visibleCount++;
          }
          sibling = sibling.nextElementSibling;
        }
        groupEl.style.display = visibleCount === 0 ? "none" : "";
      });
    }

    function applyFilters() {
      table.clearFilter();

      var filters = [];

      // Class filter.
      if (selectedClass !== "all") {
        filters.push(function (data) {
          return data.classes && data.classes.indexOf(selectedClass) !== -1;
        });
      }

      // Keyword search filter.
      if (searchTerm) {
        var keywords = searchTerm.toLowerCase().split(/\s+/).filter(Boolean);
        filters.push(function (data) {
          var blob = data._searchBlob || "";
          for (var i = 0; i < keywords.length; i++) {
            if (blob.indexOf(keywords[i]) === -1) return false;
          }
          return true;
        });
      }

      if (filters.length > 0) {
        table.setFilter(function (data) {
          for (var i = 0; i < filters.length; i++) {
            if (!filters[i](data)) return false;
          }
          return true;
        });
      }

      // Redraw so column formatters pick up the new selectedClass
      // (Statement resolves class-variant text, Classes highlights active badge).
      table.redraw(true);

      // Hide group headers whose child rows are all filtered out.
      hideEmptyGroups();

      // Update result count.
      updateCount();
    }

    function updateCount() {
      if (!countSpan) return;
      var showing = table.getDataCount("active");
      if (showing === totalCount) {
        countSpan.textContent = totalCount + " indicators";
      } else {
        countSpan.textContent =
          "Showing " + showing + " of " + totalCount + " indicators";
      }
    }

    // Apply initial class filter after Tabulator has fully built.
    table.on("tableBuilt", function () {
      applyFilters();
    });

    // Search input — debounced.
    var debounceTimer = null;
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () {
          searchTerm = searchInput.value.trim();
          applyFilters();
        }, 250);
      });
    }

    // Class selector. User changes are NOT persisted — refresh restores the
    // server-resolved default. See req-ksi-compview-class-select-6.
    if (classSelect) {
      classSelect.addEventListener("change", function () {
        selectedClass = classSelect.value;
        rowClassOverrides = {};
        applyFilters();
      });
    }
  }

  // -------------------------------------------------------------------------
  // Bootstrap
  // -------------------------------------------------------------------------

  var INIT_ATTR = "data-ksi-initialized";

  function mountAll() {
    var mounts = document.querySelectorAll("[data-ksi-panel-id]");
    for (var i = 0; i < mounts.length; i++) {
      if (!mounts[i].hasAttribute(INIT_ATTR)) {
        mounts[i].setAttribute(INIT_ATTR, "1");
        initPanel(mounts[i]);
      }
    }
  }

  // Initial mount.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }

  // Re-mount after HTMX swaps (panel fragments loaded asynchronously).
  document.addEventListener("htmx:afterSettle", mountAll);
})();
