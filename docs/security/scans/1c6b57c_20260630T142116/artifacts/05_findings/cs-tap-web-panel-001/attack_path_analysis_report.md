# Attack Path Analysis: Generic panel endpoint lets no-cap users read panel content and request-selected entity fields

Severity: high
Confidence: high

Attack path:

1. Attacker obtains any authenticated session without tap_viewer/tap_admin.
2. Attacker discovers or guesses a panel URL id from a page/nav leak, seed data, or URL history.
3. Attacker requests /panel/<slug>--<uuid>/ directly.
4. If the panel is a ViewerPanel, attacker supplies entity_id and entity_type query parameters to render another object.
5. Sensitive page/panel/object fields are returned without grid.read and without authz-denial logging.

Why the existing controls did not stop it:

Panel fragments were treated as UI implementation details instead of graph-read entrypoints, so the route relies on downstream helpers that are not guaranteed to enforce grid.read.

Recommended fix:

Call tap_auth.policy.authorize(get_caller_context(), "grid.read", operation="panel_view") before any Panel lookup or panel-type context building. Add defense-in-depth grid.read authorization before ViewerPanel request-selected object resolution, and add no-cap HTTP tests proving panel fragments return 403 and emit authz-denial logs.
