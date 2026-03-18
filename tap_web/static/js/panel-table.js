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
  var COMMON_METADATA_COLUMNS = [
    {
      title: "ID",
      field: "entity_id",
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
      field: "name",
      widthGrow: 2,
    },
    {
      title: "Type",
      field: "entity_type",
      width: 120,
    },
    {
      title: "Last Edited",
      field: "updated_at",
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
      field: "dimensions",
      widthGrow: 1,
      formatter: function (cell) {
        var val = cell.getValue();
        if (!val || typeof val !== "object") return "";
        return JSON.stringify(val);
      },
    },
  ];

  // Columns for edge mode — shows enriched from/to display names.
  var EDGE_COLUMNS = [
    {
      title: "From",
      field: "from_name",
      widthGrow: 2,
    },
    {
      title: "Type",
      field: "edge_type",
      width: 160,
    },
    {
      title: "To",
      field: "to_name",
      widthGrow: 2,
    },
    {
      title: "Properties",
      field: "properties",
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

    /* global Tabulator */
    new Tabulator(mountEl, {
      data: rows,
      columns: columns,
      layout: "fitColumns",
      pagination: false, // Server handles pagination; disable Tabulator's own.
      placeholder: "No results.",
    });
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
  document.addEventListener("htmx:afterSwap", function (evt) {
    mountAll(evt.detail.target);
  });
})();
