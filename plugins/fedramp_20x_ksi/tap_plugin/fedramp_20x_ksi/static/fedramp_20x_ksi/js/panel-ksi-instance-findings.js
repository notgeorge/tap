// FedRAMP 20x KSI Instance Findings — asset-scoped findings table with
// inline-expandable rows. Each row's chevron toggles a detail block containing
// the finding's description, related-indicator mini-table, and evidence
// mini-table. Evidence rows preserve their own per-row chevron-to-detail
// behavior, mirroring panel-ksi-finding-profile.js.
(function () {
    "use strict";

    function readPayload(scriptId) {
        var el = document.getElementById(scriptId);
        if (!el) return [];
        try {
            return JSON.parse(el.textContent || "[]");
        } catch (e) {
            console.error("[instance-findings] Failed to parse " + scriptId, e);
            return [];
        }
    }

    function chevronCell() {
        var el = document.createElement("span");
        el.className = "instance-findings-chevron";
        el.textContent = "›";
        return el;
    }

    function verdictPillFormatter(cell) {
        var v = (cell.getValue() || "").toString();
        if (!v) return "";
        var el = document.createElement("span");
        el.className = "instance-findings-verdict instance-findings-verdict--" + v;
        el.textContent = v;
        return el;
    }

    function titleFormatter(cell) {
        var row = cell.getRow().getData();
        var name = cell.getValue() || "";
        var fid = row.finding_id || "";
        if (!fid) return name;
        var a = document.createElement("a");
        a.className = "instance-findings-title-link";
        a.href = "/fedramp-ksi/finding?entity_id=" + encodeURIComponent(fid);
        a.textContent = name;
        a.addEventListener("click", function (evt) { evt.stopPropagation(); });
        return a;
    }

    function ksiChipFormatter(cell) {
        var code = cell.getValue() || "";
        var row = cell.getRow().getData();
        if (!code) return "";
        var el = document.createElement("span");
        el.className = "instance-findings-ksi-chip";
        el.textContent = code;
        if (row.ksi_name) el.title = code + " — " + row.ksi_name;
        return el;
    }

    function buildIndicatorTable(parent, ksis) {
        if (!ksis || !ksis.length) {
            var note = document.createElement("div");
            note.className = "instance-findings-detail-empty";
            note.textContent = "No related indicators.";
            parent.appendChild(note);
            return;
        }
        var mount = document.createElement("div");
        mount.className = "instance-findings-detail-mini";
        parent.appendChild(mount);
        new Tabulator(mount, {
            data: ksis,
            layout: "fitColumns",
            columns: [
                { title: "Relationship", field: "relationship_type", width: 130, formatter: function (c) {
                    var v = c.getValue() || "";
                    if (!v) return "";
                    var s = document.createElement("span");
                    s.className = "instance-findings-rel instance-findings-rel--" + v;
                    s.textContent = v;
                    return s;
                }},
                { title: "Code", field: "code", width: 130 },
                { title: "Name", field: "name", width: 220 },
                { title: "Description", field: "description", widthGrow: 3, formatter: "textarea", headerSort: false },
            ],
        });
    }

    function buildEvidenceDetailEl(data) {
        var wrap = document.createElement("div");
        wrap.className = "instance-findings-evidence-detail";
        wrap.dataset.evidenceFor = data.entity_id || "";
        var header = document.createElement("div");
        header.className = "instance-findings-evidence-detail-header";
        header.textContent = data.name || "(unnamed evidence)";
        wrap.appendChild(header);
        var pre = document.createElement("pre");
        pre.textContent = data.description || "(no description)";
        wrap.appendChild(pre);
        return wrap;
    }

    function buildEvidenceTable(parent, evidence) {
        if (!evidence || !evidence.length) {
            var note = document.createElement("div");
            note.className = "instance-findings-detail-empty";
            note.textContent = "No evidence attached.";
            parent.appendChild(note);
            return;
        }
        var mount = document.createElement("div");
        mount.className = "instance-findings-detail-mini";
        parent.appendChild(mount);
        var detailContainer = document.createElement("div");
        detailContainer.className = "instance-findings-evidence-details";
        parent.appendChild(detailContainer);

        var table = new Tabulator(mount, {
            data: evidence,
            layout: "fitColumns",
            columns: [
                { title: "Verdict", field: "support_kind", width: 130, formatter: function (c) {
                    var v = c.getValue() || "";
                    if (!v) return "";
                    var el = document.createElement("span");
                    el.className = "instance-findings-verdict instance-findings-verdict--" + v;
                    el.textContent = v;
                    return el;
                }},
                { title: "Name", field: "name", width: 220 },
                { title: "Kind", field: "kind", width: 130, formatter: function (c) {
                    var v = c.getValue() || "";
                    if (!v) return "";
                    var el = document.createElement("span");
                    el.className = "instance-findings-kind-tag";
                    el.textContent = v;
                    return el;
                }},
                { title: "Updated", field: "updated_relative", width: 110, formatter: function (c) {
                    var label = c.getValue() || "";
                    if (!label) return "";
                    var el = document.createElement("span");
                    el.className = "instance-findings-evidence-timestamp";
                    el.textContent = label;
                    var row = c.getRow().getData();
                    if (row.timestamp_tooltip) el.title = row.timestamp_tooltip;
                    return el;
                }},
                { title: "Note", field: "note", widthGrow: 2, formatter: "textarea", headerSort: false },
                { title: "", field: "_chevron", width: 36, headerSort: false, hozAlign: "center", formatter: chevronCell },
            ],
            rowFormatter: function (row) {
                row.getElement().classList.add("instance-findings-evidence-row");
            },
        });
        table.on("rowClick", function (e, row) {
            var data = row.getData();
            var rowEl = row.getElement();
            var existing = detailContainer.querySelector(
                '.instance-findings-evidence-detail[data-evidence-for="' + (data.entity_id || "") + '"]'
            );
            if (existing) {
                existing.parentNode.removeChild(existing);
                rowEl.classList.remove("instance-findings-evidence-row--expanded");
                return;
            }
            detailContainer.appendChild(buildEvidenceDetailEl(data));
            rowEl.classList.add("instance-findings-evidence-row--expanded");
        });
    }

    function buildDetailBlock(row) {
        var data = row.getData();
        var wrap = document.createElement("div");
        wrap.className = "instance-findings-detail";

        if (data.description) {
            var section = document.createElement("section");
            section.className = "instance-findings-detail-section";
            var h = document.createElement("h3");
            h.className = "instance-findings-detail-section-title";
            h.textContent = "Description";
            section.appendChild(h);
            var body = document.createElement("div");
            body.className = "instance-findings-detail-description";
            body.textContent = data.description;
            section.appendChild(body);
            wrap.appendChild(section);
        }

        var ksiSection = document.createElement("section");
        ksiSection.className = "instance-findings-detail-section";
        var ksiH = document.createElement("h3");
        ksiH.className = "instance-findings-detail-section-title";
        ksiH.textContent = "Related Indicators";
        ksiSection.appendChild(ksiH);
        buildIndicatorTable(ksiSection, data.ksis || []);
        wrap.appendChild(ksiSection);

        var evSection = document.createElement("section");
        evSection.className = "instance-findings-detail-section";
        var evH = document.createElement("h3");
        evH.className = "instance-findings-detail-section-title";
        evH.textContent = "Evidence";
        evSection.appendChild(evH);
        buildEvidenceTable(evSection, data.evidence || []);
        wrap.appendChild(evSection);

        return wrap;
    }

    function toggleRow(row, panelId) {
        var rowEl = row.getElement();
        var fid = row.getData().finding_id || "";
        var detailContainer = document.getElementById(
            "instance-findings-details-" + panelId
        );
        if (!detailContainer) return;
        var existing = detailContainer.querySelector(
            '.instance-findings-detail-wrap[data-finding-detail="' + fid + '"]'
        );
        if (existing) {
            existing.parentNode.removeChild(existing);
            rowEl.classList.remove("instance-findings-row--expanded");
            return;
        }
        var wrap = document.createElement("div");
        wrap.className = "instance-findings-detail-wrap";
        wrap.dataset.findingDetail = fid;
        var heading = document.createElement("div");
        heading.className = "instance-findings-detail-finding-name";
        heading.textContent = row.getData().name || "";
        wrap.appendChild(heading);
        wrap.appendChild(buildDetailBlock(row));
        detailContainer.appendChild(wrap);
        rowEl.classList.add("instance-findings-row--expanded");
    }

    function initOne(mountEl) {
        var panelId = mountEl.dataset.instanceFindingsPanelId;
        if (!panelId) return;
        var dataEl = document.getElementById("instance-findings-data-" + panelId);
        if (!dataEl) return;
        var rows;
        try {
            rows = JSON.parse(dataEl.textContent || "[]");
        } catch (e) {
            console.error("[instance-findings] Failed to parse payload", e);
            return;
        }

        var table = new Tabulator(mountEl, {
            data: rows,
            layout: "fitColumns",
            placeholder: "No findings.",
            columns: [
                { title: "", field: "_chevron", width: 36, headerSort: false, hozAlign: "center", formatter: chevronCell },
                { title: "Verdict", field: "verdict", width: 130, formatter: verdictPillFormatter, hozAlign: "center", headerHozAlign: "center" },
                { title: "Title", field: "name", widthGrow: 1, formatter: titleFormatter },
                { title: "Summary", field: "summary", widthGrow: 3, headerSort: false, formatter: "textarea" },
                { title: "KSI", field: "ksi_code", width: 140, formatter: ksiChipFormatter, hozAlign: "center", headerHozAlign: "center" },
                { title: "Age", field: "age_relative", width: 100, hozAlign: "center", headerHozAlign: "center" },
            ],
            rowFormatter: function (row) {
                row.getElement().classList.add("instance-findings-row");
            },
        });
        table.on("rowClick", function (e, row) {
            toggleRow(row, panelId);
        });
    }

    function initAll() {
        if (typeof Tabulator === "undefined") {
            console.error("[instance-findings] Tabulator not loaded");
            return;
        }
        document
            .querySelectorAll('[data-instance-findings-panel-id]')
            .forEach(initOne);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }

    document.body.addEventListener("htmx:afterSwap", function (evt) {
        if (!evt || !evt.target) return;
        if (evt.target.querySelector("[data-instance-findings-panel-id]")) {
            initAll();
        }
    });
})();
