/**
 * Genericom AWS top-level tap layout.
 *
 * Bounded-layer nested projection for the minimal AWS slice:
 *
 *   aws_account (viewport parent)
 *     ├── aws_route53_zone (leaf — account-scoped service)
 *     └── aws_vpc (viewport parent)
 *           ├── aws_alb (leaf — VPC-scoped service, ENIs span subnets)
 *           ├── aws_rds_instance (leaf — VPC-scoped service, multi-AZ placement)
 *           └── aws_subnet (viewport parent)
 *                 └── aws_ec2_instance (leaf — actually lives in one subnet)
 *
 * VPC-scoped services (ALB, RDS) don't live in any single subnet in AWS:
 * they have ENIs in two or more subnets across AZs, and the load balancer /
 * database itself is a VPC-scoped abstraction. We model this visually by
 * synthesizing a hidden containment edge from each such resource to its VPC
 * so the nesting resolver places them as siblings of subnets. Their original
 * RESIDES_IN edges to individual subnets stay visible on screen, so viewers
 * can still see which subnets the resource is wired to.
 */

import {projectNested} from "/static/tap_viz/js/runtime/nested-projection.js";

// Resources whose canonical AWS placement is the VPC, not a single subnet.
const VPC_SCOPED_TYPES = ["aws_alb", "aws_rds_instance"];

// Custom edge_type for the synthetic VPC-containment edges. The nesting rule
// below matches on this so these resources nest inside the VPC rather than
// any single subnet. The edges themselves are hidden.
const VPC_SCOPED_EDGE_TYPE = "_VPC_SCOPED";
const SYNTH_EDGE_ID_PREFIX = "__logical_vpc_edge:";

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

    addVpcScopedContainmentEdges(cy);

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
        ],
        baseSizes: {
            aws_account: {width: 1000, height: 700},
            aws_vpc: {width: 760, height: 520},
            aws_subnet: {width: 220, height: 160},
            aws_ec2_instance: {width: 50, height: 50},
            aws_rds_instance: {width: 50, height: 50},
            aws_alb: {width: 50, height: 50},
            aws_route53_zone: {width: 50, height: 50},
        },
        padding: 16,
        innerLayout: "grid",
    });

    warnings.forEach((w) => console.warn("[aws-top-level]", w.category, w.message));

    if (trigger_reason === "initial_load") {
        cy.fit(cy.nodes(":visible").filter((n) => !n.data("_is_badge")), 40);
    }
}
