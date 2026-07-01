# Attack Path Analysis: Dynamic page and nav-index routes enumerate page metadata and panel URLs without grid.read

Severity: medium
Confidence: high

Attack path:

1. Attacker logs in as a capless user.
2. Attacker requests /__nav-index.json or a known page slug.
3. Response reveals page URLs, names, descriptions, layout slots, and panel URL ids.
4. Attacker uses disclosed panel URL ids to call /panel/... and read panel content via the companion finding.

Why the existing controls did not stop it:

Page/navigation rendering predates the authz backstop and uses graph ORM reads as a presentation convenience without treating the routes as graph-read entrypoints.

Recommended fix:

Require grid.read at the start of landing_view, page_view, parameterized_page_view, _render_grid_placeholder fallback, and nav_index_view before Page/Edge/Panel rows are loaded. Preserve anonymous login redirects, but authenticated no-cap users should receive 403 and log an authz denial.
