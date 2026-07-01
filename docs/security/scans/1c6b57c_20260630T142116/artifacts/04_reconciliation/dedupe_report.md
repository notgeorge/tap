# Candidate Reconciliation

The panel, page/nav, and entity-type catalog issues share the same strategic root cause: graph reads reachable from web/API routes must call `tap_auth.policy.authorize(..., "grid.read", ...)` before graph state is resolved. They remain separate findings because they have different route families, data exposure, and remediation anchors.

- Panel fragment endpoint: direct content/object read sink, including request-selected ViewerPanel object lookup.
- Page/nav routes: page metadata/layout/panel URL enumeration, also chains into the panel endpoint.
- Entity-type catalog: model/plugin metadata exposure through a core API endpoint.

No duplicate was filed for `/object/...`, Search, Gryphon, entities, edges, or panel-edit mutation because runtime tests showed they deny no-cap users and log the denial.
