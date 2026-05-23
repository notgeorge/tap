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
  // Node data uses the GRIFT envelope shape (spec-grift-envelope):
  // spine fields flat at top; per-model fields in `data`; render hints in `display.tap_viz`.
  var COMMON_METADATA_COLUMNS = [
    {
      // Icon column — decorative, no header text, empty when no icon available.
      title: "",
      field: "display.tap_viz.icon_url",
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

  // ---------------------------------------------------------------------
  // Preset formatters — referenced by name from a panel's `columns` config
  // (config.columns[].formatter). String names keep the panel config
  // declarative (no inline JS in grift); the JS owns the rendering.
  // ---------------------------------------------------------------------
  function _safeStr(v) { return v == null ? "" : String(v); }

  var FORMATTERS = {
    plaintext: function (cell) { return _safeStr(cell.getValue()); },
    datetime: function (cell) {
      var v = cell.getValue();
      if (!v) return "";
      try {
        var d = new Date(v);
        if (isNaN(d)) return _safeStr(v);
        // Compact local rendering: yyyy-mm-dd hh:mm.
        var pad = function (n) { return String(n).padStart(2, "0"); };
        return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
          " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
      } catch (e) { return _safeStr(v); }
    },
    tickCross: function (cell) {
      var v = cell.getValue();
      if (v === true || v === "true") return '<span style="color:#16a34a;font-weight:600">✓</span>';
      if (v === false || v === "false") return '<span style="color:#dc2626;font-weight:600">✕</span>';
      return '<span style="color:#9ca3af">–</span>';
    },
    ellipsisSuffix: function (cell) {
      var v = _safeStr(cell.getValue());
      return v.length > 8 ? "…" + v.slice(-8) : v;
    },
    json: function (cell) {
      var v = cell.getValue();
      if (v == null) return "";
      if (typeof v === "object") {
        var s = JSON.stringify(v);
        return s.length > 60 ? s.slice(0, 60) + "…" : s;
      }
      return _safeStr(v);
    },
    passFailBadge: function (cell) {
      var v = _safeStr(cell.getValue()).toLowerCase();
      if (v === "pass") return '<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:4px;font-weight:600;font-size:11px">PASS</span>';
      if (v === "fail") return '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:4px;font-weight:600;font-size:11px">FAIL</span>';
      return _safeStr(cell.getValue());
    },
    painBadge: function (cell) {
      var v = _safeStr(cell.getValue());
      var colors = {
        N1: ["#dbeafe", "#1e40af"], N2: ["#dcfce7", "#166534"],
        N3: ["#fef3c7", "#92400e"], N4: ["#fed7aa", "#9a3412"],
        N5: ["#fecaca", "#991b1b"],
      };
      var pair = colors[v];
      if (!pair) return v;
      return '<span style="background:' + pair[0] + ';color:' + pair[1] +
        ';padding:2px 8px;border-radius:4px;font-weight:600;font-size:11px">' + v + '</span>';
    },
    arrayCount: function (cell) {
      var v = cell.getValue();
      if (!Array.isArray(v) || v.length === 0) return '<span style="color:#9ca3af">—</span>';
      return String(v.length);
    },
  };

  function buildCustomColumns(specs) {
    return specs.map(function (spec) {
      var col = {
        field: spec.field,
        title: spec.title,
        headerSort: spec.headerSort !== false,
      };
      if (spec.width != null) col.width = spec.width;
      if (spec.widthGrow != null) col.widthGrow = spec.widthGrow;
      var fmt = FORMATTERS[spec.formatter || "plaintext"];
      if (fmt) {
        col.formatter = fmt;
      }
      if (spec.tooltip === "full_value") {
        col.tooltip = function (e, cell) { return _safeStr(cell.getValue()); };
      }
      return col;
    });
  }

  // Columns for edge mode — endpoint labels resolved into display.tap_viz.
  // Edge envelopes follow the same shape as node envelopes; edge_type and
  // properties live in `data`, from/to labels in `display.tap_viz.{from,to}_label`.
  var EDGE_COLUMNS = [
    {
      title: "From",
      field: "display.tap_viz.from_label",
      widthGrow: 2,
    },
    {
      title: "Type",
      field: "data.edge_type",
      width: 160,
    },
    {
      title: "To",
      field: "display.tap_viz.to_label",
      widthGrow: 2,
    },
    {
      title: "Properties",
      field: "data.properties",
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

    // Per-panel custom column spec (from panel.config.columns); when present,
    // overrides the default common_metadata / edge column sets.
    var customColumns = null;
    var customColumnsScript = document.getElementById("tap-table-columns-" + panelId);
    if (customColumnsScript) {
      try {
        customColumns = JSON.parse(customColumnsScript.textContent);
      } catch (e) {
        console.warn("TAP table panel: failed to parse columns spec for panel", panelId, e);
      }
    }

    var mode = mountEl.getAttribute("data-tap-table-mode") || "node";
    var columns;
    if (customColumns && customColumns.length > 0) {
      columns = buildCustomColumns(customColumns);
    } else {
      columns = mode === "edge" ? EDGE_COLUMNS : COMMON_METADATA_COLUMNS;
    }

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
          var entityType = data.entity_type || "";
          var urlId = ((data.display || {}).tap_viz || {}).url_id || "";
          if (urlId && entityType) {
            // Save scroll position so the back-button restoration can return
            // the user to where they were on this page.
            saveScrollForReturn();
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

  // ---------------------------------------------------------------------
  // Scroll restoration.
  //
  // Pages with table panels lazy-load their content via HTMX after initial
  // page render. Browsers' default scroll restoration fires BEFORE the
  // panels expand the document height, so back-navigation lands at the top
  // even though the browser "tried" to restore. Workaround: take over the
  // restoration ourselves — save scrollY when navigating away via a row
  // click, restore once the document is tall enough to accommodate it
  // (after htmx:afterSettle fires for the lazy panels).
  // ---------------------------------------------------------------------
  var SCROLL_KEY_PREFIX = "tap-return-scroll:";

  function saveScrollForReturn() {
    try {
      sessionStorage.setItem(SCROLL_KEY_PREFIX + window.location.pathname, String(window.scrollY));
    } catch (e) {
      // sessionStorage can fail in private mode; silently ignore.
    }
  }

  function _scrollKey() { return SCROLL_KEY_PREFIX + window.location.pathname; }

  var _scrollRestoreDone = false;
  function tryRestoreScroll() {
    if (_scrollRestoreDone) return;
    var savedY;
    try { savedY = sessionStorage.getItem(_scrollKey()); } catch (e) { return; }
    if (!savedY) return;
    var targetY = parseInt(savedY, 10);
    if (isNaN(targetY) || targetY <= 0) {
      try { sessionStorage.removeItem(_scrollKey()); } catch (e) { /* ignore */ }
      _scrollRestoreDone = true;
      return;
    }
    // Only scroll once the document is tall enough for the saved Y to be valid.
    if (document.documentElement.scrollHeight >= targetY + window.innerHeight - 50) {
      window.scrollTo(0, targetY);
      try { sessionStorage.removeItem(_scrollKey()); } catch (e) { /* ignore */ }
      _scrollRestoreDone = true;
    }
  }

  // Take manual control so the browser doesn't auto-restore to the wrong
  // (pre-lazy-load) position.
  if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", tryRestoreScroll);
  } else {
    tryRestoreScroll();
  }
  // Each HTMX settle expands the page; retry restoration in case the
  // document just grew tall enough.
  document.addEventListener("htmx:afterSettle", tryRestoreScroll);
})();
