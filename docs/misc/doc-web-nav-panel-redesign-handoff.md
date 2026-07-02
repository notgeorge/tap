---
title: Navigation-as-Panel redesign — superseded handoff
spec: tap_web/specs/spec-web-chrome.md
covers:
  - req-web-chrome-migration
  - req-web-nav-panel
  - req-web-nav-panel-1
  - req-web-nav-panel-2
  - req-web-nav-panel-3
  - req-web-nav-panel-4
---

# Navigation-as-Panel redesign — handoff

> **Superseded 2026-07-02.** This handoff captured the security/architecture
> thread that originally proposed navigation as a built-in Panel. The target
> architecture is now [`tap_web/specs/spec-web-chrome.md`](../../tap_web/specs/spec-web-chrome.md):
> navigation becomes built-in `ChromeEntry` objects on a persistent
> `ChromeSurface`, and graph-backed chrome activates only after Page/chrome read
> authorization. Keep this doc as historical context; do not implement from its
> Objective section.

A fresh, booted session picks up `req-web-nav-panel` to close out the tap_web
navigation security/architecture thread. This doc is a **pointer to canon + the
starting line + the open design questions** — it is not authoritative. Verify
everything against the specs; do not build from this doc alone
(`ground-in-canon-before-building`).

## Objective

Navigation (breadcrumb + Cmd-K command palette + popovers) becomes a **standard
built-in Panel type that runs a gated Search**, auto-mounted by the page builder
into a reserved chrome slot on page-builder Pages. Non-page-builder surfaces mount
nothing and do **no** graph reads. Reuse existing panel plumbing — do not invent a
parallel path.

The four sub-requirements (`spec-web-navigation.md`, all **Proposed**):

- **-1 Nav Is A Built-In Panel** — nav renders through a standard built-in Panel
  type running a gated Search, not a per-render context processor.
- **-2 Page Builder Mounts It** — the page builder auto-injects the nav panel into a
  reserved chrome slot on every page-builder Page; other surfaces mount nothing and
  do no graph reads.
- **-3 Context Processor Removed** — `tap_web.navigation.breadcrumb` is deleted;
  non-grid pages render product-mark-only chrome.
- **-4 Palette + Modal Under The Panel** — the Cmd-K command palette and modal
  pop-in are owned by the nav panel, reusing panel plumbing.

## Ground in canon first (read, then verify)

1. `tap_web/specs/spec-web-chrome.md` — target architecture for `ChromeSurface`,
   `ChromeEntry`, activation, shortcuts, signals, and migration.
2. `tap_web/specs/spec-web-navigation.md` — historical/current navigation behavior;
   `req-web-nav-panel` is now Deprecated and superseded.
3. `plan/road-rampart.md` active step — judge this work against its Objective /
   Done-Test / Non-Goals; apply the roadmap Doctrine + `specs/spec-security-posture.md`.
4. The oldest keystone on the grid — `MATCH (k:keystone) RETURN k ORDER BY k.created_at ASC`.
5. `spec-web-panel.md` and `spec-web-page.md` — the reusable Page/Panel patterns
   chrome intentionally adapts without becoming a Page or Panel.

## What's already done (the starting line)

- **The acute security hole is already closed and on main.**
  `tap_web/navigation.py` wraps the breadcrumb's Page read in
  `if caller_can_read():` (read-free chrome) — that fixed the login-500. This
  redesign **removes** that read path from chrome entirely (`-3`) rather than
  guarding it, so non-grid pages do zero graph reads *by construction*.
- **The service-layer gateway refactor is on main (2026-07-02, tip `95e147a3`).**
  `tap_grid.services` is now a package where every public grid read/write is
  capability-gated (`grid.read`, etc.), enforced by a location-scoped lint
  (`tap/tests/test_service_gateway_coverage.py`). The nav panel's Search **must**
  route through that gated service layer — do not reach past it. See
  `req-grid-service-gateway-gated` in `tap_grid/specs/spec-grid-service.md`.

## Open design questions — settle these WITH GEORGE before coding

These were flagged but never resolved; they change the shape of the build:

1. **Panel-instance-per-Page vs a chrome singleton** — does each page-builder Page
   own a nav Panel instance, or is there one shared chrome nav panel?
2. **Palette cross-Page reach** — how does the Cmd-K palette navigate/search across
   Pages it isn't mounted on?
3. **Migration order** — this is entangled with the page-builder / page redesign
   ("nav + page redesign together" was the intent); sequence the two.

## Discipline

- **Discuss the design with George before implementing.** Surface the three open
  questions above and get alignment first.
- Follow the sprint patterns: gate at entry, route every grid touch through the
  service layer, keep `spec-web-chrome.md` aligned as you build, and add/adjust
  any Validation Map row in `spec-dev-validation.md`.
- Fresh booted instance: containers up on latest `main`. `scripts/test --fast` for
  the inner loop; full `scripts/test` before promoting; `scripts/promote-to-main.sh`.

## Relevant memory

`service-layer-guards-sprint` (the breadcrumb thread origin),
`codex-security-gateway-refactor-merged` (the gated service layer you build on),
`ground-in-canon-before-building`, `subgrid-collapses-into-grid`.
