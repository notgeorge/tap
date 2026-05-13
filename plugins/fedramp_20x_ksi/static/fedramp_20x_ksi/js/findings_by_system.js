// Findings By System panel — Tabulator init grouped by system.
(function () {
    "use strict";

    function formatTimestamp(iso) {
        if (!iso) return "";
        try {
            const d = new Date(iso);
            return isNaN(d.getTime()) ? iso : d.toLocaleString();
        } catch (e) {
            return iso;
        }
    }

    function titleCellFormatter(cell) {
        const row = cell.getRow().getData();
        const title = cell.getValue() || "";
        const fid = row.finding_id || "";
        if (!fid) return title;
        const a = document.createElement("a");
        a.className = "findings-title-link";
        a.href = "/fedramp-ksi/finding?entity_id=" + encodeURIComponent(fid);
        a.textContent = title;
        return a;
    }

    function ksiCellFormatter(cell) {
        const row = cell.getRow().getData();
        const code = row.ksi_code || "";
        const name = row.ksi_name || "";
        if (!code) return "";
        const el = document.createElement("span");
        el.className = "findings-ksi-code";
        el.textContent = code;
        el.title = name ? code + " — " + name : code;
        return el;
    }

    function relationshipCellFormatter(cell) {
        const rel = cell.getValue() || "";
        if (!rel) return "";
        const el = document.createElement("span");
        el.className = "findings-rel findings-rel--" + rel;
        el.textContent = rel;
        return el;
    }

    function ageCellFormatter(cell) {
        const days = cell.getValue();
        const row = cell.getRow().getData();
        if (days === null || days === undefined) return "";
        let label;
        if (days <= 0) label = "today";
        else if (days === 1) label = "1 day";
        else label = days + " days";
        const el = document.createElement("span");
        el.textContent = label;
        if (row.created_at) el.title = "Opened " + formatTimestamp(row.created_at);
        return el;
    }

    function groupHeaderFormatter(value, count) {
        const wrap = document.createElement("span");
        wrap.className = "findings-group-header";
        const name = document.createElement("span");
        name.className = "findings-group-name";
        name.textContent = value || "(no system)";
        const tally = document.createElement("span");
        tally.className = "findings-group-count";
        tally.textContent = count + (count === 1 ? " finding" : " findings");
        wrap.appendChild(name);
        wrap.appendChild(tally);
        return wrap;
    }

    function initOne(mountEl) {
        const panelId = mountEl.dataset.findingsBySystemPanelId;
        if (!panelId) return;
        const dataEl = document.getElementById("findings-by-system-data-" + panelId);
        if (!dataEl) return;
        let rows;
        try {
            rows = JSON.parse(dataEl.textContent || "[]");
        } catch (e) {
            console.error("[findings-by-system] payload parse failed:", e);
            return;
        }
        new Tabulator(mountEl, {
            data: rows,
            layout: "fitColumns",
            placeholder: "No open findings.",
            initialSort: [{ column: "age_days", dir: "asc" }],
            groupBy: "system_name",
            groupHeader: groupHeaderFormatter,
            groupStartOpen: true,
            columns: [
                { title: "Title", field: "title", widthGrow: 1, headerSort: true, formatter: titleCellFormatter },
                { title: "Summary", field: "summary", widthGrow: 3, headerSort: false, formatter: "textarea" },
                { title: "KSI", field: "ksi_code", width: 130, headerSort: true, formatter: ksiCellFormatter, hozAlign: "center", headerHozAlign: "center" },
                { title: "Relationship", field: "ksi_relationship", width: 130, headerSort: true, formatter: relationshipCellFormatter, hozAlign: "center", headerHozAlign: "center" },
                { title: "Age", field: "age_days", width: 110, headerSort: true, sorter: "number", formatter: ageCellFormatter, hozAlign: "center", headerHozAlign: "center" },
            ],
        });
    }

    function initAll() {
        document.querySelectorAll('[id^="findings-by-system-table-"]').forEach(initOne);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }

    document.body.addEventListener("htmx:afterSwap", function (evt) {
        if (!evt || !evt.target) return;
        evt.target.querySelectorAll('[id^="findings-by-system-table-"]').forEach(initOne);
    });
})();
