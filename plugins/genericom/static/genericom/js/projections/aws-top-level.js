/**
 * Genericom AWS top-level tap layout.
 *
 * Bounded-layer nested projection for the minimal AWS slice:
 *
 *   aws_account (viewport parent)
 *     ├── aws_route53_zone (leaf — account-scoped service)
 *     └── aws_vpc (viewport parent)
 *           ├── aws_alb (primary — VPC-scoped, shadows in subnets)
 *           ├── aws_rds_instance (primary — VPC-scoped, shadows in subnets)
 *           └── aws_subnet (viewport parent)
 *                 ├── aws_ec2_instance (leaf — actually lives in one subnet)
 *                 └── shadow nodes for ALB/RDS presence
 *
 * VPC-scoped services (ALB, RDS) have ENIs in multiple subnets across AZs.
 * Rather than placing them in any single subnet, the primary node stays at
 * VPC-level and lightweight shadow copies appear inside each subnet where
 * the entity has a presence. Shadow links (dashed visual-only edges) connect
 * each shadow back to its primary.
 */

import {projectNested} from "/static/tap_viz/js/runtime/nested-projection.js";
import {createShadows, initShadowInteraction} from "/static/tap_viz/js/runtime/shadow-nodes.js";

// Resources whose canonical AWS placement is the VPC, not a single subnet.
const VPC_SCOPED_TYPES = ["aws_alb", "aws_rds_instance"];

// One-off label cleanup for the Genericom demo: every resource name in the
// seed data starts with "genericom-" which is visual noise. Strip the prefix
// in-place on node labels. Not generalized — demo-specific kludge.
const GENERICOM_PREFIX = "genericom-";

function stripGenericomPrefix(cy) {
    cy.nodes().forEach((n) => {
        const label = n.data("label") || "";
        if (label.startsWith(GENERICOM_PREFIX)) {
            n.data("label", label.slice(GENERICOM_PREFIX.length));
        }
    });
}

// Custom edge_type for the synthetic VPC-containment edges. The nesting rule
// below matches on this so these resources nest inside the VPC rather than
// any single subnet. The edges themselves are hidden.
const VPC_SCOPED_EDGE_TYPE = "_VPC_SCOPED";
const SYNTH_EDGE_ID_PREFIX = "__logical_vpc_edge:";

// Synthetic edge type for shadow node nesting placement.
const SHADOW_PLACEMENT_EDGE_TYPE = "_SHADOW_PLACEMENT";

function addVpcScopedContainmentEdges(cy) {
    VPC_SCOPED_TYPES.forEach((type) => {
        cy.nodes(`[entity_type="${type}"]`).forEach((resource) => {
            // Find any RESIDES_IN edge out of this resource to locate a subnet
            // (resource is the source; subnet is the target).
            const residesEdge = resource
                .connectedEdges()
                .filter((e) => e.source().id() === resource.id() && e.data("label") === "RESIDES_IN")
                .first();
            if (residesEdge.length === 0) return;

            const subnet = residesEdge.target();

            // Subnet's inbound CONTAINS edge comes from its VPC.
            const vpcEdge = subnet
                .connectedEdges()
                .filter((e) => e.target().id() === subnet.id() && e.data("label") === "CONTAINS")
                .first();
            if (vpcEdge.length === 0) return;

            const vpc = vpcEdge.source();
            const synthId = SYNTH_EDGE_ID_PREFIX + resource.id();
            if (cy.getElementById(synthId).length > 0) return;

            cy.add({
                group: "edges",
                data: {
                    id: synthId,
                    source: resource.id(),
                    target: vpc.id(),
                    label: "",
                    edge_type: VPC_SCOPED_EDGE_TYPE,
                },
                classes: "tap-nesting-hidden",
            });
        });
    });
}

export async function execute(context) {
    const {cy, trigger_reason} = context;

    stripGenericomPrefix(cy);

    // Step 1: Promote VPC-scoped resources to VPC level (primary nodes).
    addVpcScopedContainmentEdges(cy);

    // Step 2: Create shadow nodes inside each subnet where VPC-scoped
    // resources have a presence. Must run BEFORE projectNested so shadows
    // participate in nesting resolution and influence subnet sizing.
    createShadows(cy, {
        entityTypes: VPC_SCOPED_TYPES,
        edgeType: "RESIDES_IN",
        placementEdgeType: SHADOW_PLACEMENT_EDGE_TYPE,
    });

    // Step 3: Run nesting resolution with shadow placement rule.
    const {warnings} = await projectNested(cy, {
        relationships: [
            {
                name: "account-contains-vpc",
                gryphon: "(parent:aws_account)<-[:BELONGS_TO]-(child:aws_vpc)",
            },
            {
                name: "account-contains-zone",
                gryphon: "(parent:aws_account)<-[:BELONGS_TO]-(child:aws_route53_zone)",
            },
            {
                name: "vpc-contains-subnet",
                gryphon: "(parent:aws_vpc)-[:CONTAINS]->(child:aws_subnet)",
            },
            {
                name: "vpc-contains-alb",
                gryphon: `(parent:aws_vpc)<-[:${VPC_SCOPED_EDGE_TYPE}]-(child:aws_alb)`,
            },
            {
                name: "vpc-contains-rds",
                gryphon: `(parent:aws_vpc)<-[:${VPC_SCOPED_EDGE_TYPE}]-(child:aws_rds_instance)`,
            },
            {
                name: "subnet-contains-ec2",
                gryphon: "(parent:aws_subnet)<-[:RESIDES_IN]-(child:aws_ec2_instance)",
            },
            {
                name: "subnet-contains-shadow",
                gryphon: `(parent:aws_subnet)<-[:${SHADOW_PLACEMENT_EDGE_TYPE}]-(child)`,
            },
        ],
        baseSizes: {
            aws_account: {width: 850, height: 340},
            aws_vpc: {width: 760, height: 520},
            aws_subnet: {width: 220, height: 160},
            aws_ec2_instance: {width: 188, height: 87},
            aws_rds_instance: {width: 188, height: 87},
            aws_alb: {width: 188, height: 87},
            aws_route53_zone: {width: 188, height: 87},
        },
        shadowBaseSizes: {width: 113, height: 53},
        padding: 16,
        innerLayout: "grid",
        innerLayouts: {
            aws_account: {name: "stack-vertical"},
        },
    });

    // Step 4: Wire up hover highlighting for shadow groups.
    initShadowInteraction(cy);

    warnings.forEach((w) => console.warn("[aws-top-level]", w.category, w.message));

    if (trigger_reason === "initial_load") {
        cy.fit(cy.nodes(":visible").filter((n) => !n.data("_is_badge") && !n.data("_is_shadow")), 40);
    }
}
