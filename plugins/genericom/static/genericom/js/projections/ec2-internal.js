/**
 * ec2-internal.js — EC2 instance internal view layout.
 *
 * Simple cose layout for the initial EC2 internal projection.
 * Shows the instance's computing-core internals: network interfaces,
 * IPs, ports, programs, libraries, TCP connections, and remote endpoints.
 */

export async function execute(context) {
    const {cy, elevation, trigger_reason} = context;

    // Run a standard cose layout on all visible nodes.
    const layout = cy.layout({
        name: "cose",
        animate: false,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 80,
        nodeRepulsion: 8000,
        gravity: 0.25,
        numIter: 500,
        padding: 40,
    });

    layout.run();

    // Fit viewport to all visible nodes after layout.
    if (trigger_reason === "initial_load") {
        cy.fit(cy.nodes(":visible"), 40);
    }
}
