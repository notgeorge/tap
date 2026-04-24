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
        "background-color": "#e8eff6",
        "z-index": 0,
    });
    ec2.position({x: CX, y: CY});

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
    ifaces.forEach((iface, idx) => {
        iface.style({width: 80, height: 140, "background-opacity": 0.15, "border-width": 1});
        iface.position({x: L + 65, y: T + 90 + idx * 180});

        // Find attached ports.
        const ports = [];
        cy.edges(`[label = "ATTACHED_TO"]`).forEach((e) => {
            if (e.data("target") === iface.id() && relevant.has(e.data("source"))) {
                ports.push(cy.getElementById(e.data("source")));
            }
        });
        const listening = ports.filter((p) => p.data("port_number") != null)
            .sort((a, b) => (a.data("port_number") || 0) - (b.data("port_number") || 0));
        const client = ports.filter((p) => p.data("port_number") == null);

        const px = iface.position().x;
        let py = iface.position().y - 35;
        listening.forEach((p, pi) => {
            p.style({width: 26, height: 26, shape: "ellipse"});
            p.position({x: px - 12 + pi * 32, y: py});
        });
        if (client.length > 0) {
            py += 55;
            client.forEach((p, pi) => {
                p.style({width: 22, height: 22, shape: "ellipse", "border-style": "dashed", "border-width": 2});
                p.position({x: px - 12 + pi * 32, y: py});
            });
        }
    });

    // --- Position programs (center-top inside EC2) ---
    programs.forEach((prog, idx) => {
        prog.style({width: 120, height: 40, shape: "round-rectangle"});
        prog.position({x: L + 260 + idx * 170, y: T + 80 + idx * 55});
    });

    // --- Position files (bottom row inside EC2) ---
    files.sort((a, b) => (a.data("label") || "").localeCompare(b.data("label") || ""));
    files.forEach((f, idx) => {
        f.style({width: 95, height: 30});
        f.position({x: L + 140 + idx * 120, y: T + EC2_H - 55});
    });

    // --- Position keys (below their containing files) ---
    const allKeys = [...(byType["public_key"] || []), ...(byType["private_key"] || [])];
    // Keys are not hosted by EC2 directly but are connected via CONTAINS from files.
    cy.nodes().filter((n) => (n.data("entity_type") === "public_key" || n.data("entity_type") === "private_key") && relevant.has(n.id()))
        .forEach((key) => {
            let parentFile = null;
            cy.edges(`[label = "CONTAINS"]`).forEach((e) => {
                if (e.data("target") === key.id()) {
                    parentFile = cy.getElementById(e.data("source"));
                }
            });
            if (parentFile && parentFile.length > 0) {
                key.style({width: 22, height: 22});
                key.position({x: parentFile.position().x, y: parentFile.position().y + 30});
            } else {
                key.style({width: 22, height: 22});
                key.position({x: L + EC2_W - 60, y: T + EC2_H - 25});
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
            tcp.style({width: 30, height: 30});
            const name = (tcp.data("label") || "").toLowerCase();
            if (name.includes("alb")) {
                tcp.position({x: EXT_L + 100, y: CY - 30});
            } else if (name.includes("gunicorn") && name.includes("django")) {
                tcp.position({x: L + 340, y: T + 155});
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

    // --- Fit viewport ---
    if (trigger_reason === "initial_load") {
        cy.fit(cy.nodes(":visible").not(".tap-elevation-hidden"), 50);
    }
}
