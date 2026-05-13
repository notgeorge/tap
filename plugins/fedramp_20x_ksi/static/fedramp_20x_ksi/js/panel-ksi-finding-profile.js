// FedRAMP 20x KSI Finding Profile — Tabulator initializers for the KSI and
// Evidence tables. Both tables read embedded JSON payloads emitted by the
// panel template; no client-side fetching.
(function () {
    "use strict";

    function readPayload(scriptId) {
        var el = document.getElementById(scriptId);
        if (!el) return [];
        try {
            return JSON.parse(el.textContent || "[]");
        } catch (e) {
            console.error("[finding-profile] Failed to parse " + scriptId, e);
            return [];
        }
    }

    function relPillFormatter(cell) {
        var v = (cell.getValue() || "").toString();
        if (!v) return "";
        var el = document.createElement("span");
        el.className = "finding-rel-pill finding-rel-pill--" + v;
        el.textContent = v;
        return el;
    }

    function verdictPillFormatter(cell) {
        var v = (cell.getValue() || "").toString();
        if (!v) return "";
        var el = document.createElement("span");
        el.className = "finding-verdict-pill finding-verdict-pill--" + v;
        el.textContent = v;
        return el;
    }

    function kindTagFormatter(cell) {
        var v = (cell.getValue() || "").toString();
        if (!v) return "";
        var el = document.createElement("span");
        el.className = "finding-kind-tag";
        el.textContent = v;
        return el;
    }

    function ksiCodeFormatter(cell) {
        var row = cell.getRow().getData();
        var code = row.code || "";
        var entityId = row.entity_id || "";
        if (!code) return "";
        if (!entityId) return code;
        var a = document.createElement("a");
        a.className = "finding-ksi-code-link";
        a.href = "/fedramp-ksi/indicator?entity_id=" + encodeURIComponent(entityId);
        a.textContent = code;
        return a;
    }

    function chevronFormatter() {
        var el = document.createElement("span");
        el.className = "finding-evidence-chevron";
        el.textContent = "›";
        return el;
    }

    function timestampFormatter(cell) {
        var row = cell.getRow().getData();
        var label = cell.getValue() || "";
        if (!label) return "";
        var el = document.createElement("span");
        el.className = "finding-evidence-timestamp";
        el.textContent = label;
        if (row.timestamp_tooltip) {
            el.title = row.timestamp_tooltip;
        }
        return el;
    }

    function initKsiTable(rows) {
        var mount = document.getElementById("finding-profile-ksi-table");
        if (!mount) return;
        new Tabulator(mount, {
            data: rows,
            layout: "fitColumns",
            placeholder: "No related indicators.",
            columns: [
                {
                    title: "Relationship",
                    field: "relationship_type",
                    width: 140,
                    headerSort: true,
                    formatter: relPillFormatter,
                    hozAlign: "center",
                    headerHozAlign: "center",
                },
                {
                    title: "Code",
                    field: "code",
                    width: 140,
                    headerSort: true,
                    formatter: ksiCodeFormatter,
                },
                {
                    title: "Name",
                    field: "name",
                    width: 240,
                    headerSort: true,
                },
                {
                    title: "Description",
                    field: "description",
                    widthGrow: 3,
                    headerSort: false,
                    formatter: "textarea",
                },
            ],
        });
    }

    function buildEvidenceDetail(row) {
        var data = row.getData();
        var wrap = document.createElement("div");
        wrap.className = "finding-evidence-detail";
        wrap.dataset.findingDetailFor = data.entity_id || "";

        var header = document.createElement("div");
        header.className = "finding-evidence-detail-header";
        header.textContent = data.name || "(unnamed evidence)";
        wrap.appendChild(header);

        var pre = document.createElement("pre");
        pre.textContent = data.description || "(no description)";
        wrap.appendChild(pre);
        return wrap;
    }

    function findExistingDetail(container, entityId) {
        if (!container) return null;
        return container.querySelector(
            '.finding-evidence-detail[data-finding-detail-for="' + entityId + '"]'
        );
    }

    function toggleEvidenceRow(row) {
        var rowEl = row.getElement();
        var data = row.getData();
        var entityId = data.entity_id || "";
        var container = document.getElementById("finding-profile-evidence-details");
        if (!container) return;
        var existing = findExistingDetail(container, entityId);
        if (existing) {
            existing.parentNode.removeChild(existing);
            rowEl.classList.remove("finding-evidence-row--expanded");
            return;
        }
        container.appendChild(buildEvidenceDetail(row));
        rowEl.classList.add("finding-evidence-row--expanded");
    }

    function initEvidenceTable(rows) {
        var mount = document.getElementById("finding-profile-evidence-table");
        if (!mount) return;

        var table = new Tabulator(mount, {
            data: rows,
            layout: "fitColumns",
            placeholder: "No evidence attached.",
            selectableRows: false,
            columns: [
                {
                    title: "Verdict",
                    field: "support_kind",
                    width: 140,
                    headerSort: true,
                    formatter: verdictPillFormatter,
                    hozAlign: "center",
                    headerHozAlign: "center",
                },
                {
                    title: "Name",
                    field: "name",
                    width: 240,
                    headerSort: true,
                },
                {
                    title: "Kind",
                    field: "kind",
                    width: 140,
                    headerSort: true,
                    formatter: kindTagFormatter,
                },
                {
                    title: "Updated",
                    field: "updated_relative",
                    width: 110,
                    headerSort: true,
                    formatter: timestampFormatter,
                    hozAlign: "right",
                    headerHozAlign: "right",
                },
                {
                    title: "Note",
                    field: "note",
                    widthGrow: 2,
                    headerSort: false,
                    formatter: "textarea",
                },
                {
                    title: "",
                    field: "_chevron",
                    width: 36,
                    headerSort: false,
                    hozAlign: "center",
                    formatter: chevronFormatter,
                },
            ],
            rowFormatter: function (row) {
                row.getElement().classList.add("finding-evidence-row");
            },
        });

        // Tabulator 6: subscribe via .on() rather than constructor callbacks for
        // reliable click delivery when rowFormatter is present.
        table.on("rowClick", function (e, row) {
            toggleEvidenceRow(row);
        });
    }

    function initAll() {
        if (typeof Tabulator === "undefined") {
            console.error("[finding-profile] Tabulator not loaded");
            return;
        }
        initKsiTable(readPayload("finding-profile-ksis"));
        initEvidenceTable(readPayload("finding-profile-evidence"));
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }

    // HTMX support — re-init on swapped panel content.
    document.body.addEventListener("htmx:afterSwap", function (evt) {
        if (!evt || !evt.target) return;
        if (evt.target.querySelector("#finding-profile-ksi-table")
            || evt.target.querySelector("#finding-profile-evidence-table")) {
            initAll();
        }
    });
})();
