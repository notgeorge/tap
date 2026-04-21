/**
 * panel-table.js — TAP Table Panel browser glue.
 *
 * Initializes a Tabulator instance for each Table Panel fragment on the page.
 * Data is read from an embedded <script type="application/json"> container
 * placed by the server-side template (req-web-stdpanel-table-render-3).
 *
 * Pagination is server-backed: clicking Prev/Next triggers an HTMX request
 * that replaces the panel fragment with a new server-rendered page.
 * Tabulator's own pagination is disabled.
 *
 * Column mode is selected via data-tap-table-mode on the mount element:
 *   "node" (default) — common_metadata columns
 *   "edge"           — edge relationship columns (from / type / to)
 */

(function () {
  "use strict";

  // Columns for common_metadata mode (req-web-stdpanel-table-columns).
  // Node data uses GRIFT extended format: {entity: {...}, node: {...}, icon_url, shape, url_id}
  var COMMON_METADATA_COLUMNS = [
    {
      // Icon column — decorative, no header text, empty when no icon available.
      title: "",
      field: "icon_url",
      width: 36,
      hozAlign: "center",
      headerSort: false,
      formatter: function (cell) {
        var url = cell.getValue();
        if (!url) return "";
        var img = document.createElement("img");
        img.src = url;
        img.alt = "";
        img.setAttribute("aria-hidden", "true");
        img.style.width = "20px";
        img.style.height = "20px";
        img.style.display = "block";
        img.style.margin = "auto";
        return img;
      },
    },
    {
      title: "ID",
      field: "entity.entity_id",
      width: 120,
      formatter: function (cell) {
        // Show only the last 8 chars of the UUID for readability.
        var val = cell.getValue() || "";
        return val.length > 8 ? "\u2026" + val.slice(-8) : val;
      },
      tooltip: function (e, cell) {
        return cell.getValue();
      },
    },
    {
      title: "Name",
      field: "entity.name",
      widthGrow: 2,
    },
    {
      title: "Type",
      field: "entity.entity_type",
      width: 120,
    },
    {
      title: "Last Edited",
      field: "entity.updated_at",
      width: 160,
      formatter: function (cell) {
        var val = cell.getValue();
        if (!val) return "";
        try {
          return new Date(val).toLocaleString();
        } catch (e) {
          return val;
        }
      },
    },
    {
      title: "Dimensions",
      field: "entity.dimensions",
      widthGrow: 1,
      formatter: function (cell) {
        var val = cell.getValue();
        if (!val || typeof val !== "object") return "";
        return JSON.stringify(val);
      },
    },
  ];

  // Columns for edge mode — shows enriched from/to display names.
  // Edge data uses GRIFT extended format: {entity: {...}, edge: {...}, from_name, to_name}
  var EDGE_COLUMNS = [
    {
      title: "From",
      field: "from_name",
      widthGrow: 2,
    },
    {
      title: "Type",
      field: "edge.edge_type",
      width: 160,
    },
    {
      title: "To",
      field: "to_name",
      widthGrow: 2,
    },
    {
      title: "Properties",
      field: "edge.properties",
      widthGrow: 1,
      formatter: function (cell) {
        var val = cell.getValue();
        if (!val || typeof val !== "object" || Object.keys(val).length === 0) return "";
        return JSON.stringify(val);
      },
    },
  ];

  /**
   * Mount a single Table Panel.
   *
   * @param {HTMLElement} mountEl  - div[data-tap-table-mount]
   */
  function mountTablePanel(mountEl) {
    // Skip if already initialized (prevents double-init on full-document re-scan).
    if (mountEl.getAttribute("data-tap-table-mounted")) return;

    var panelId = mountEl.getAttribute("data-tap-table-panel-id");
    if (!panelId) return;

    var dataScriptEl = document.getElementById("tap-table-data-" + panelId);
    if (!dataScriptEl) {
      console.warn("TAP table panel: no data script found for panel", panelId);
      return;
    }

    var rows;
    try {
      rows = JSON.parse(dataScriptEl.textContent);
    } catch (e) {
      console.error("TAP table panel: failed to parse data for panel", panelId, e);
      return;
    }

    var mode = mountEl.getAttribute("data-tap-table-mode") || "node";
    var columns = mode === "edge" ? EDGE_COLUMNS : COMMON_METADATA_COLUMNS;

    var tableOptions = {
      data: rows,
      columns: columns,
      layout: "fitColumns",
      pagination: false, // Server handles pagination; disable Tabulator's own.
      placeholder: "No results.",
    };

    // Node-mode rows navigate to the object viewer on click (req-web-stdpanel-table-row-nav).
    // Use rowFormatter to attach the click handler directly on the DOM element — Tabulator v6
    // removed rowClick as a constructor option in favour of table.on().
    if (mode === "node") {
      tableOptions.rowFormatter = function (row) {
        var el = row.getElement();
        el.style.cursor = "pointer";
        el.addEventListener("click", function () {
          var data = row.getData();
          var entityType = data.entity ? data.entity.entity_type : "";
          var urlId = data.url_id || "";
          if (urlId && entityType) {
            window.location.href = "/object/" + entityType + "/" + urlId + "/";
          }
        });
      };
    }

    /* global Tabulator */
    new Tabulator(mountEl, tableOptions);
    mountEl.setAttribute("data-tap-table-mounted", "true");
  }

  /**
   * Find and mount all table panels within a root element.
   *
   * @param {Document|HTMLElement} root
   */
  function mountAll(root) {
    var mounts = (root || document).querySelectorAll("[data-tap-table-mount]");
    mounts.forEach(function (el) {
      mountTablePanel(el);
    });
  }

  // Initial mount on DOMContentLoaded.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      mountAll(document);
    });
  } else {
    mountAll(document);
  }

  // Re-mount after HTMX swaps (panel fragment reload, pagination).
  // Use htmx:afterSettle (fires after DOM is stable) and search from
  // document — outerHTML swaps remove the original target from the DOM,
  // so evt.detail.target may be stale.
  document.addEventListener("htmx:afterSettle", function () {
    mountAll(document);
    mountPageSizeSelectors(document);
  });

  // --- Page-size selector with localStorage persistence ---

  var STORAGE_KEY = "tap-table-page-size";

  function getStoredPageSize() {
    try {
      var val = localStorage.getItem(STORAGE_KEY);
      return val !== null ? val : null;
    } catch (e) {
      return null;
    }
  }

  function storePageSize(value) {
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch (e) {
      // Silently ignore storage failures.
    }
  }

  /**
   * Wire up page-size <select> elements within a root.
   * On change, persist to localStorage and reload the panel via HTMX.
   * The nav bar appears twice (above + below table); both selectors are
   * wired but only one triggers the localStorage-restore reload.
   */
  function mountPageSizeSelectors(root) {
    var selects = (root || document).querySelectorAll("[data-tap-page-size-select]");
    var reloadTriggered = false;

    selects.forEach(function (sel) {
      // Skip already-wired selectors.
      if (sel.getAttribute("data-tap-mounted")) return;
      sel.setAttribute("data-tap-mounted", "true");

      // On first load, if localStorage has a stored value and it differs from
      // the server-rendered selection, trigger a reload with the stored value.
      // Only one selector needs to trigger this (the reload replaces both).
      if (!reloadTriggered) {
        var stored = getStoredPageSize();
        if (stored !== null && sel.value !== stored) {
          var hasOption = Array.from(sel.options).some(function (o) {
            return o.value === stored;
          });
          if (hasOption) {
            sel.value = stored;
            reloadTriggered = true;
            reloadPanel(sel, stored);
            return;
          }
        }
      }

      sel.addEventListener("change", function () {
        var newSize = sel.value;
        storePageSize(newSize);
        reloadPanel(sel, newSize);
      });
    });
  }

  /**
   * Reload the panel fragment via HTMX with the given page_size.
   */
  function reloadPanel(selectEl, pageSize) {
    var footer = selectEl.closest("[data-tap-table-footer]");
    if (!footer) return;
    var slug = footer.getAttribute("data-tap-panel-slug");
    var panelId = footer.getAttribute("data-tap-panel-id");
    if (!slug || !panelId) return;

    var panelEl = footer.closest(".tap-panel--table");
    if (!panelEl) return;

    var url = "/panel/" + slug + "--" + panelId + "/?page_size=" + pageSize + "&offset=0";

    /* global htmx */
    if (typeof htmx !== "undefined") {
      htmx.ajax("GET", url, { target: panelEl, swap: "outerHTML" });
    }
  }

  // Initial mount for page-size selectors.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      mountPageSizeSelectors(document);
    });
  } else {
    mountPageSizeSelectors(document);
  }
})();
