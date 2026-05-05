// Genericom Open Alerts panel — initializes a Tabulator table from the
// embedded row payload. Hard-coded columns: Title, Associated System,
// Description, Created, Last Updated. One-off demo build; see
// spec-genericom-open-alerts-table.md for the refactor signals that should
// trigger folding this back into the standard tap_web Table Panel.
(function () {
    "use strict";

    function formatTimestamp(isoString) {
        if (!isoString) {
            return "";
        }
        try {
            const d = new Date(isoString);
            if (isNaN(d.getTime())) {
                return isoString;
            }
            return d.toLocaleString();
        } catch (e) {
            return isoString;
        }
    }

    function titleCellFormatter(cell) {
        var row = cell.getRow().getData();
        var title = cell.getValue() || "";
        var fid = row.finding_id || "";
        if (!fid) {
            return title;
        }
        var a = document.createElement("a");
        a.className = "genericom-finding-link";
        a.href = "/fedramp-ksi/finding?entity_id=" + encodeURIComponent(fid);
        a.textContent = title;
        return a;
    }

    function ksiCellFormatter(cell) {
        const row = cell.getRow().getData();
        const code = row.ksi_code || "";
        const name = row.ksi_name || "";
        if (!code) {
            return "";
        }
        const codeEl = document.createElement("span");
        codeEl.className = "genericom-ksi-code";
        codeEl.textContent = code;
        codeEl.title = name ? code + " — " + name : code;
        return codeEl;
    }

    function relationshipCellFormatter(cell) {
        const rel = cell.getValue() || "";
        if (!rel) {
            return "";
        }
        const el = document.createElement("span");
        el.className = "genericom-ksi-rel genericom-ksi-rel--" + rel;
        el.textContent = rel;
        return el;
    }

    function groupHeaderFormatter(value, count) {
        const wrap = document.createElement("span");
        wrap.className = "genericom-group-header";
        const name = document.createElement("span");
        name.className = "genericom-group-name";
        name.textContent = value || "(no system)";
        const tally = document.createElement("span");
        tally.className = "genericom-group-count";
        tally.textContent = count + (count === 1 ? " finding" : " findings");
        wrap.appendChild(name);
        wrap.appendChild(tally);
        return wrap;
    }

    function ageCellFormatter(cell) {
        const days = cell.getValue();
        const row = cell.getRow().getData();
        if (days === null || days === undefined) {
            return "";
        }
        let label;
        if (days <= 0) {
            label = "today";
        } else if (days === 1) {
            label = "1 day";
        } else {
            label = days + " days";
        }
        const el = document.createElement("span");
        el.textContent = label;
        if (row.created_at) {
            el.title = "Opened " + formatTimestamp(row.created_at);
        }
        return el;
    }

    function initOne(mountEl) {
        const panelId = mountEl.dataset.genericomOpenAlertsPanelId;
        if (!panelId) {
            return;
        }
        const dataEl = document.getElementById("genericom-open-alerts-data-" + panelId);
        if (!dataEl) {
            return;
        }
        let rows;
        try {
            rows = JSON.parse(dataEl.textContent || "[]");
        } catch (e) {
            console.error("[genericom-open-alerts] Failed to parse payload:", e);
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
                {
                    title: "Description",
                    field: "description",
                    widthGrow: 3,
                    headerSort: false,
                    formatter: "textarea",
                },
                {
                    title: "KSI",
                    field: "ksi_code",
                    width: 130,
                    headerSort: true,
                    formatter: ksiCellFormatter,
                    hozAlign: "center",
                    headerHozAlign: "center",
                },
                {
                    title: "Relationship",
                    field: "ksi_relationship",
                    width: 130,
                    headerSort: true,
                    formatter: relationshipCellFormatter,
                    hozAlign: "center",
                    headerHozAlign: "center",
                },
                {
                    title: "Age",
                    field: "age_days",
                    width: 110,
                    headerSort: true,
                    sorter: "number",
                    formatter: ageCellFormatter,
                    hozAlign: "center",
                    headerHozAlign: "center",
                },
            ],
        });
    }

    function initAll() {
        document
            .querySelectorAll('[id^="genericom-open-alerts-table-"]')
            .forEach(initOne);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }

    // HTMX support — re-init on swapped panel content.
    document.body.addEventListener("htmx:afterSwap", function (evt) {
        if (!evt || !evt.target) {
            return;
        }
        evt.target
            .querySelectorAll('[id^="genericom-open-alerts-table-"]')
            .forEach(initOne);
    });
})();
