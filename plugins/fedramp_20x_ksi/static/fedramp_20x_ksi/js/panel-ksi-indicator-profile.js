/**
 * panel-ksi-indicator-profile.js — class badge toggle for the KSI profile page.
 *
 * When an indicator has class_variants, clicking a class badge in the hero
 * swaps the statement text with a fade transition.
 */

(function () {
  "use strict";

  /**
   * Render statement text, replacing **Optional:** with a styled tag.
   */
  function renderStatementInto(el, text) {
    if (text.startsWith("**Optional:**")) {
      var tag = document.createElement("span");
      tag.className = "ksi-optional-tag";
      tag.textContent = "Optional";
      el.textContent = "";
      el.appendChild(tag);
      el.appendChild(
        document.createTextNode(" " + text.replace("**Optional:** ", ""))
      );
    } else {
      el.textContent = text;
    }
  }

  function relationshipPillFormatter(cell) {
    var v = (cell.getValue() || "").toString();
    if (!v) return "";
    var el = document.createElement("span");
    el.className =
      "ksi-finding-status-pill ksi-finding-status-pill--" + v;
    el.textContent = v;
    return el;
  }

  function systemLinkFormatter(cell) {
    var row = cell.getRow().getData();
    var name = row.system_name || "";
    var sid = row.system_id || "";
    if (!name && !sid) {
      var dash = document.createElement("span");
      dash.className = "ksi-finding-empty";
      dash.textContent = "—";
      return dash;
    }
    if (!sid) return name;
    var a = document.createElement("a");
    a.className = "ksi-finding-row-link";
    a.href = "/grid/" + encodeURIComponent(sid);
    a.textContent = name || sid;
    return a;
  }

  function findingLinkFormatter(cell) {
    var row = cell.getRow().getData();
    var name = row.finding_name || "";
    var fid = row.finding_id || "";
    if (!fid) return name;
    var a = document.createElement("a");
    a.className = "ksi-finding-row-link";
    a.href = "/fedramp-ksi/finding?entity_id=" + encodeURIComponent(fid);
    a.textContent = name;
    return a;
  }

  function openedFormatter(cell) {
    var row = cell.getRow().getData();
    var label = cell.getValue() || "";
    if (!label) return "";
    var el = document.createElement("span");
    el.className = "ksi-finding-opened";
    el.textContent = label;
    if (row.opened_full) el.title = row.opened_full;
    return el;
  }

  function initFindingsTable() {
    var mount = document.getElementById("ksi-profile-findings-table");
    var dataEl = document.getElementById("ksi-profile-findings");
    if (!mount || !dataEl) return;
    if (mount.dataset.tabulatorInit === "1") return;
    if (typeof Tabulator === "undefined") return;
    var rows;
    try {
      rows = JSON.parse(dataEl.textContent || "[]");
    } catch (e) {
      console.error("[ksi-profile-findings] payload parse failed", e);
      return;
    }
    new Tabulator(mount, {
      data: rows,
      layout: "fitColumns",
      placeholder: "No findings linked to this indicator.",
      columns: [
        {
          title: "Relationship",
          field: "finding_relationship",
          width: 130,
          headerSort: true,
          formatter: relationshipPillFormatter,
          hozAlign: "center",
          headerHozAlign: "center",
        },
        {
          title: "System",
          field: "system_name",
          width: 200,
          headerSort: true,
          formatter: systemLinkFormatter,
        },
        {
          title: "Finding",
          field: "finding_name",
          width: 240,
          headerSort: true,
          formatter: findingLinkFormatter,
        },
        {
          title: "Description",
          field: "finding_description",
          widthGrow: 2,
          headerSort: false,
          formatter: "textarea",
        },
        {
          title: "Opened",
          field: "opened_relative",
          width: 110,
          headerSort: true,
          formatter: openedFormatter,
          hozAlign: "right",
          headerHozAlign: "right",
        },
      ],
    });
    mount.dataset.tabulatorInit = "1";
  }

  function initProfile() {
    initFindingsTable();

    // Render **Optional:** tag on the statement text regardless of class variants.
    var statementEl = document.querySelector(".ksi-profile-statement-text");
    if (statementEl) {
      renderStatementInto(statementEl, statementEl.textContent);
    }

    var variantsEl = document.getElementById("ksi-profile-variants");
    if (!variantsEl) return;

    var variants;
    try {
      variants = JSON.parse(variantsEl.textContent);
    } catch (e) {
      return;
    }
    if (!variants) return;

    var badges = document.querySelectorAll(
      ".ksi-profile-classes .ksi-class-badge--clickable"
    );
    if (!badges.length || !statementEl) return;

    badges.forEach(function (badge) {
      badge.addEventListener("click", function () {
        var cls = badge.getAttribute("data-class");
        if (!cls || !variants[cls]) return;

        var newText = variants[cls].statement || "";

        // Update active badge styling.
        badges.forEach(function (b) {
          b.classList.remove("ksi-class-badge--active");
        });
        badge.classList.add("ksi-class-badge--active");

        // Fade transition.
        statementEl.classList.add("ksi-fade-out");
        setTimeout(function () {
          renderStatementInto(statementEl, newText);
          statementEl.classList.remove("ksi-fade-out");
          statementEl.classList.add("ksi-fade-in");
          setTimeout(function () {
            statementEl.classList.remove("ksi-fade-in");
          }, 200);
        }, 150);
      });
    });
  }

  // Bootstrap.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initProfile);
  } else {
    initProfile();
  }
  document.addEventListener("htmx:afterSettle", initProfile);
})();
