# Finding Discovery Report

Scope: repository-wide scan with parent-agent focus on TAP auth, web, API, page/panel rendering, capability enforcement, denial logging, CSRF, XSS, CORS and HTTP security posture.

Worker fan-out note: six intended independent discovery workers failed due the session usage limit. The parent pass therefore converted the broad worker worklist into explicit per-row closures in `work_ledger.jsonl`: high-impact auth/web/API/spec surfaces were reviewed by the parent; remaining rank-input rows were marked deferred rather than silently treated as reviewed.

Validated candidate families:

- `cs-tap-web-panel-001`: generic panel endpoint renders graph-backed panel content without a `grid.read` authorization decision.
- `cs-tap-web-page-002`: dynamic page and navigation routes enumerate page metadata, layout slots, and panel URL identifiers without `grid.read`.
- `cs-tap-api-typecat-003`: entity-type catalog API returns model/plugin metadata to authenticated no-cap users.

Suppressed or no-issue surfaces:

- `/object/...`, `/api/v1/entities/`, `/api/v1/edges/`, Search, and Gryphon read paths denied capless users and emitted authz logs.
- CSRF middleware blocked missing/bogus token POSTs and cross-origin POSTs.
- Text panel hostile content rendered escaped; explicit `|safe` uses were paired with `safe_json()` or locally escaped strings in the inspected templates.
- Current dev profile fails Django deploy checks, but `tap_auth.boot` contains a deploy posture gate that aborts deploy boot when dev settings are present.
