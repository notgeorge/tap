/**
 * ec2-internal.js — EC2 instance internal view layout.
 *
 * Hard-coded positional layout for the Genericom EC2 internal projection.
 * The EC2 instance is rendered as a viewport parent (bordered container)
 * with hosted resources positioned inside it.
 *
 * Zones:
 *   LEFT of EC2: inbound services (ALB) and their TCP connections
 *   Inside EC2:
 *     - Left edge: network interfaces with ports
 *     - Center/top: programs (gunicorn, django)
 *     - Bottom: files, keys
 *   RIGHT of EC2: backend services (RDS)
 *   ABOVE EC2: supporting services (Redis)
 */

// Arrangements are owned by the Layout entity (definition.arrangements) and
// run by the projection runtime after this module returns. This module only
// does broad-strokes positioning + post-arrangement-friendly fix-up.

export async function execute(context) {
    const {cy, trigger_reason, inputs} = context;

    // --- Find anchor EC2 ---
    let anchorId = inputs?.entity_id;
    if (!anchorId) {
        const ec2s = cy.nodes().filter((n) => n.data("entity_type") === "aws_ec2_instance");
        if (ec2s.length > 0) anchorId = ec2s[0].id();
    }
    if (!anchorId) return;

    // --- Build hosted set ---
    const hosted = new Set();
    cy.edges(`[label = "HOSTS"]`).forEach((e) => {
        if (e.data("source") === anchorId) {
            hosted.add(e.data("target"));
        }
    });

    // --- Build relevance set ---
    const relevant = new Set([anchorId, ...hosted]);

    // Include ports attached to hosted interfaces and ports programs listen on.
    cy.edges(`[label = "ATTACHED_TO"]`).forEach((e) => {
        if (hosted.has(e.data("target"))) relevant.add(e.data("source"));
    });
    cy.edges(`[label = "LISTENS_ON"]`).forEach((e) => {
        if (hosted.has(e.data("source"))) relevant.add(e.data("target"));
    });

    for (let pass = 0; pass < 3; pass++) {
        cy.edges(`[label = "CONNECTS_TO"]`).forEach((e) => {
            const f = e.data("source"), t = e.data("target");
            if (relevant.has(f)) relevant.add(t);
            if (relevant.has(t)) relevant.add(f);
        });
    }
    cy.edges(`[label = "HOSTS"]`).forEach((e) => {
        if (relevant.has(e.data("target"))) relevant.add(e.data("source"));
    });
    cy.edges(`[label = "AVAILABLE_AT"]`).forEach((e) => {
        if (relevant.has(e.data("source"))) relevant.add(e.data("target"));
    });
    cy.edges(`[label = "PAIRED_WITH"]`).forEach((e) => {
        const f = e.data("source"), t = e.data("target");
        if (relevant.has(f)) relevant.add(t);
        if (relevant.has(t)) relevant.add(f);
    });
    cy.edges(`[label = "CONTAINS"]`).forEach((e) => {
        if (relevant.has(e.data("source"))) relevant.add(e.data("target"));
    });

    // Hide irrelevant.
    cy.elements().forEach((el) => {
        const eid = el.isNode() ? el.id() : null;
        const from = el.isEdge() ? el.data("source") : null;
        const to = el.isEdge() ? el.data("target") : null;
        if (el.isNode() && !relevant.has(eid)) el.addClass("tap-elevation-hidden");
        if (el.isEdge() && (!relevant.has(from) || !relevant.has(to))) el.addClass("tap-elevation-hidden");
    });

    // --- Strip label prefixes ---
    cy.nodes().forEach((n) => {
        let label = n.data("label") || "";
        if (label.startsWith("genericom-prod-")) label = label.slice("genericom-prod-".length);
        n.data("label", label);
    });

    // --- Layout constants ---
    const EC2_W = 660;
    const EC2_H = 440;
    const CX = 0;  // EC2 center
    const CY = 0;

    // --- Style and position EC2 as a visible container ---
    const ec2 = cy.getElementById(anchorId);
    if (!ec2 || ec2.length === 0) return;

    ec2.addClass("tap-viewport-parent");
    ec2.style({
        width: EC2_W,
        height: EC2_H,
        "border-color": "#2B5783",
        "border-width": 3,
        "background-color": "#5E89B2",
        "background-opacity": 0.08,
        "text-margin-y": -4,
        "font-size": 13,
        "z-index": 0,
        "z-index-compare": "manual",
    });
    ec2.position({x: CX, y: CY});

    // Force all other nodes and edges to render above the container.
    cy.nodes().not(ec2).style({"z-index-compare": "manual", "z-index": 10});
    cy.edges().style({"z-index-compare": "manual", "z-index": 20});

    // Set child z-index so cascade reveal processes them after the container
    // and they render above the EC2 background.
    cy.nodes().not(ec2).forEach((n) => {
        if (!n.hasClass("tap-elevation-hidden")) {
            n.style({"z-index": 10});
        }
    });


    const L = CX - EC2_W / 2;  // left edge
    const T = CY - EC2_H / 2;  // top edge

    // --- Categorize hosted nodes ---
    const byType = {};
    hosted.forEach((id) => {
        if (!relevant.has(id)) return;
        const n = cy.getElementById(id);
        if (n.length === 0) return;
        const t = n.data("entity_type");
        if (!byType[t]) byType[t] = [];
        byType[t].push(n);
    });

    const ifaces = byType["network_interface"] || [];
    const programs = byType["program"] || [];
    const files = byType["file"] || [];

    // Sort interfaces: eth0 before lo.
    ifaces.sort((a, b) => (a.data("label") || "").localeCompare(b.data("label") || ""));
    // Sort programs: gunicorn before django.
    programs.sort((a, b) => {
        const na = (a.data("label") || "").toLowerCase();
        return na.includes("gunicorn") ? -1 : 1;
    });

    // --- Position interfaces (left column inside EC2) ---
    // Interfaces are tall narrow containers with ports stacked vertically inside.
    // Listening ports (solid circles) first, then a gap, then client ports (dashed).
    ifaces.forEach((iface, idx) => {
        // Find attached ports first to size the interface.
        const ports = [];
        cy.edges(`[label = "ATTACHED_TO"]`).forEach((e) => {
            if (e.data("target") === iface.id() && relevant.has(e.data("source"))) {
                ports.push(cy.getElementById(e.data("source")));
            }
        });
        const listening = ports.filter((p) => p.data("port_number") != null)
            .sort((a, b) => (a.data("port_number") || 0) - (b.data("port_number") || 0));
        const client = ports.filter((p) => p.data("port_number") == null);
        const totalPorts = listening.length + client.length;
        const ifaceH = Math.max(80, totalPorts * 34 + (client.length > 0 ? 20 : 0) + 30);

        iface.style({width: 55, height: ifaceH, "background-opacity": 0.12, "border-width": 1, "font-size": 9});
        iface.position({x: L + 50, y: T + 80 + idx * (ifaceH + 30)});

        const px = iface.position().x;
        let py = iface.position().y - ifaceH / 2 + 24;

        // Listening ports: solid circles, stacked vertically.
        listening.forEach((p) => {
            p.style({width: 24, height: 24, shape: "ellipse", "font-size": 8});
            p.position({x: px, y: py});
            py += 32;
        });

        // Gap before client ports.
        if (client.length > 0) {
            py += 12;
            client.forEach((p) => {
                p.style({width: 20, height: 20, shape: "ellipse", "border-style": "dashed", "border-width": 2, "font-size": 7});
                p.position({x: px, y: py});
                py += 28;
            });
        }
    });

    // --- Position programs (center-top inside EC2) ---
    // gunicorn at left-center, django at right-center, staggered vertically.
    programs.forEach((prog, idx) => {
        prog.style({width: 130, height: 42, shape: "round-rectangle"});
        prog.position({x: L + 220 + idx * 180, y: T + 70 + idx * 70});
    });

    // --- Position files (bottom row inside EC2) ---
    // Files that contain keys become mini-containers with the key nested inside.
    const fileContains = {};
    cy.edges(`[label = "CONTAINS"]`).forEach((e) => {
        if (relevant.has(e.data("source")) && relevant.has(e.data("target"))) {
            fileContains[e.data("source")] = cy.getElementById(e.data("target"));
        }
    });

    files.sort((a, b) => (a.data("label") || "").localeCompare(b.data("label") || ""));
    const fileBaseX = L + 140;
    const fileBaseY = T + EC2_H - 55;
    files.forEach((f, idx) => {
        const hasChild = !!fileContains[f.id()];
        if (hasChild) {
            f.addClass("tap-viewport-parent");
            f.style({width: 100, height: 50, "background-color": "#f5f0e0", "border-color": "#a89060", "z-index": 5});
        } else {
            f.style({width: 95, height: 30});
        }
        f.position({x: fileBaseX + idx * 120, y: fileBaseY});
    });

    // --- Position keys inside their containing files ---
    cy.nodes().filter((n) => (n.data("entity_type") === "public_key" || n.data("entity_type") === "private_key") && relevant.has(n.id()))
        .forEach((key) => {
            let parentFile = null;
            cy.edges(`[label = "CONTAINS"]`).forEach((e) => {
                if (e.data("target") === key.id()) {
                    parentFile = cy.getElementById(e.data("source"));
                }
            });
            if (parentFile && parentFile.length > 0) {
                key.style({width: 20, height: 20, "z-index": 15});
                key.position({x: parentFile.position().x, y: parentFile.position().y + 8});
            }
        });

    // --- External: ALB (left of EC2) ---
    const EXT_L = L - 160;
    cy.nodes().filter((n) => n.data("entity_type") === "aws_alb" && relevant.has(n.id()))
        .forEach((n) => {
            n.style({width: 110, height: 40});
            n.position({x: EXT_L, y: CY - 30});
        });

    // --- External: RDS (right of EC2) ---
    const EXT_R = L + EC2_W + 160;
    cy.nodes().filter((n) => n.data("entity_type") === "aws_rds_instance" && relevant.has(n.id()))
        .forEach((n) => {
            n.style({width: 110, height: 40});
            n.position({x: EXT_R, y: CY});
        });

    // --- External: Redis (above EC2) ---
    const EXT_T = T - 80;
    cy.nodes().filter((n) => n.data("entity_type") === "aws_elasticache_cluster" && relevant.has(n.id()))
        .forEach((n) => {
            n.style({width: 110, height: 40});
            n.position({x: CX + 140, y: EXT_T});
        });

    // --- TCP connections ---
    cy.nodes().filter((n) => n.data("entity_type") === "tcp_connection" && relevant.has(n.id()))
        .forEach((tcp) => {
            tcp.style({width: 28, height: 28});
            const name = (tcp.data("label") || "").toLowerCase();
            if (name.includes("alb")) {
                tcp.position({x: EXT_L + 110, y: CY - 30});
            } else if (name.includes("gunicorn") && name.includes("django")) {
                tcp.position({x: L + 310, y: T + 120});
            } else if (name.includes("rds") || name.includes("5432")) {
                tcp.position({x: EXT_R - 100, y: CY});
            } else if (name.includes("redis") || name.includes("6379")) {
                tcp.position({x: CX + 140, y: EXT_T + 45});
            }
        });

    // --- Remote ports ---
    cy.nodes().filter((n) => n.data("entity_type") === "port" && !hosted.has(n.id()) && relevant.has(n.id()))
        .forEach((port) => {
            port.style({width: 24, height: 24, shape: "ellipse"});
            const num = port.data("port_number");
            if (num === 5432) port.position({x: EXT_R - 50, y: CY + 25});
            else if (num === 6379) port.position({x: CX + 180, y: EXT_T + 20});
        });

    // --- IP addresses ---
    cy.nodes().filter((n) => n.data("entity_type") === "ip_address" && relevant.has(n.id()))
        .forEach((ip) => {
            ip.style({width: 70, height: 20, "font-size": 9});
            const name = ip.data("label") || "";
            if (name.includes("127.0.0.1")) {
                ip.position({x: L + 65, y: T + 90 + 180 + 80});
            } else if (name.startsWith("10.0.10") || name.startsWith("10.0.11")) {
                ip.position({x: L + 65, y: T + 30});
            } else if (name.includes("10.0.20.44")) {
                ip.position({x: EXT_R, y: CY + 35});
            } else {
                ip.position({x: CX + 200, y: EXT_T});
            }
        });

    // --- Post-arrangement fix-up: visual polish for the demo ---
    // Even-distribution arrangements snap y but preserve x, so a single-member
    // arrangement (B3) leaves lo iface and lo port at the same x. Shrink the
    // lo iface and nudge it left of its port so they sit adjacent on the row.
    // Also re-shelve files below the program row.
    const loPort = cy.nodes().filter((n) =>
        n.data("entity_type") === "port" &&
        (n.data("label") || "") === ":8000/tcp" &&
        relevant.has(n.id())
    );
    const loIface = cy.nodes().filter((n) =>
        n.data("entity_type") === "network_interface" &&
        (n.data("label") || "") === "lo" &&
        relevant.has(n.id())
    );
    if (loPort.length > 0 && loIface.length > 0) {
        const lp = loPort[0];
        const li = loIface[0];
        li.style({width: 28, height: 24, "font-size": 8});
        li.position({x: lp.position().x - 36, y: lp.position().y});
    }

    // Re-anchor files below the program row, and pull contained keys with them.
    if (loPort.length > 0) {
        const shelfY = loPort[0].position().y + 110;
        const shelfBaseX = L + 140;
        files.forEach((f, idx) => {
            f.position({x: shelfBaseX + idx * 120, y: shelfY});
        });
        // Crypto keys: park them on the key file's tile (CONTAINS edges are pruned at this layer).
        const keyFile = files.find((f) => (f.data("label") || "").endsWith(".key"));
        if (keyFile) {
            cy.nodes()
                .filter((n) => (n.data("entity_type") === "public_key" || n.data("entity_type") === "private_key") && relevant.has(n.id()))
                .forEach((key, i) => {
                    key.style({width: 14, height: 14, "z-index": 15});
                    key.position({x: keyFile.position().x - 16 + i * 16, y: keyFile.position().y + 6});
                });
        }
    }

    // --- Edge styling: thick and dark for visibility ---
    cy.edges().not(".tap-elevation-hidden").forEach((e) => {
        e.data("label", "");  // Clear edge type label from data.
    });
    cy.edges().not(".tap-elevation-hidden").style({
        width: 3,
        "line-color": "#334155",
        "target-arrow-color": "#334155",
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
    });

    // --- Fit viewport ---
    if (trigger_reason === "initial_load") {
        cy.fit(cy.nodes(":visible").not(".tap-elevation-hidden"), 50);
    }
}
