# Repository Coverage Ledger

Scan id: `1c6b57c_20260630T142116`
Revision: `1c6b57c3132a5340df4510340c8be6831c379cec`
Completeness: partial, because worker variance-reduction fan-out failed and broad non-auth/plugin-domain file review is explicitly deferred.

Reviewed with runtime proof:

- Authenticated no-cap, viewer, and admin capability permutations for page, panel, panel edit, object view, and core entity APIs over `http://host.docker.internal:8030` with `Host: localhost:8030`.
- Access-control denial logging for guarded routes: `tap_auth.policy` `[e5d9]` and `tap_auth.middleware` `[a6b7]` emitted for capless object/API denials.
- CSRF enforcement for panel edit POST and cross-origin POST.
- XSS escaping for hostile TextPanel content and source review of first-party `safe_json` embeds.
- HTTP header/CORS sanity on live responses.

Deferred:

- Complete multi-worker repository sweep across all plugins and collector internals.
- Full line-by-line audit of vendored/minified JavaScript.
- Full route/capability permutation matrix for future plugin API routers; current search found no plugin API routers mounted.
