/**
 * Genericom AWS top-level tap layout.
 *
 * Bounded-layer nested projection for the minimal AWS slice:
 *
 *   aws_account (viewport parent)
 *     ├── aws_route53_zone (leaf at this elevation)
 *     └── aws_vpc (viewport parent)
 *           └── aws_subnet (viewport parent)
 *                 └── aws_ec2_instance | aws_rds_instance | aws_alb (leaf)
 *
 * Punt rule for multi-home resources (RDS with RESIDES_IN to two subnets):
 * keep the first RESIDES_IN out-edge active for the resolver; shadow the
 * rest with a non-matching edge_type so the resolver ignores them. The
 * visible edge label stays "RESIDES_IN" so the non-primary subnet remains
 * wired on screen.
 */

import {projectNested} from "/static/tap_viz/js/runtime/nested-projection.js";

const MULTIHOME_TYPES = ["aws_rds_instance", "aws_alb"];

function applyPrimaryPlacementPuntRule(cy) {
    MULTIHOME_TYPES.forEach((type) => {
        cy.nodes(`[entity_type="${type}"]`).forEach((node) => {
            const residesOut = node.connectedEdges().filter((e) =>
                e.source().id() === node.id() && e.data("label") === "RESIDES_IN"
            );
            residesOut.toArray().slice(1).forEach((e) => {
                e.data("edge_type", "RESIDES_IN_SECONDARY");
            });
        });
    });
}

export async function execute(context) {
    const {cy, trigger_reason} = context;

    applyPrimaryPlacementPuntRule(cy);

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
                name: "subnet-contains-ec2",
                gryphon: "(parent:aws_subnet)<-[:RESIDES_IN]-(child:aws_ec2_instance)",
            },
            {
                name: "subnet-contains-rds",
                gryphon: "(parent:aws_subnet)<-[:RESIDES_IN]-(child:aws_rds_instance)",
            },
            {
                name: "subnet-contains-alb",
                gryphon: "(parent:aws_subnet)<-[:RESIDES_IN]-(child:aws_alb)",
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
        cy.fit(cy.nodes(":visible"), 40);
    }
}
