# Web Navigation Specification

## Philosophy

TAP is a graph platform with multiple windows onto a single graph. Every entity has a position in the graph; every page has a URL path. The hierarchy a user navigates — *"TAP > samsite > compliance > OSCAL SSP"* — isn't an arbitrary tree the designer invented; it's the graph projected as a path. The navigation system should expose that path as the chrome, instead of inventing a separate "menu structure" alongside it.

The chrome is therefore a **breadcrumb header**, always. The header bar is not "where the menu lives." It *is* the menu, in the form of a path-with-options at each segment. Where you are AND what's adjacent to you are the same surface.

Anything not reachable by walking the breadcrumb is reachable through the **command palette** (Cmd-K). A single keyboard surface that fuzzy-searches every Page, every entity, every recent visit, and every account/session control. The palette absorbs everything that doesn't earn permanent chrome — there are no menu drawers, no hamburger icons, no overflow menus. If something doesn't fit on the breadcrumb path, it's one keystroke away.

A small persistent **mini-graph** in the header's upper-right shows the local neighborhood of the current entity: a tiny live Cytoscape rendering of the current node and its 3–5 closest neighbors, clickable to navigate. This is the platform's *signature* nav affordance — TAP can do this because the graph is the substrate, not a metaphor. Most apps can't.

**AI is a first-class consumer.** The breadcrumb is text; the URL is text; the command palette accepts text; the platform exposes a machine-readable nav index. Every navigation move a human can make, an agent can make through the same surfaces. This is not a separate "AI API" — it's the natural consequence of designing the human nav as text-first.

The chrome budget is fixed: product mark, breadcrumb, session tag, command-palette affordance, mini-graph. Nothing else is permanent. Features that grow into the chrome belong in the palette, not in new menu items.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Extensible | Plugins and pages slot into the breadcrumb hierarchy through data — no per-plugin nav code. |
| 2. | Expressive | Where the user is, what's at the same level, and what's one graph-step away are all visible simultaneously. |
| 3. | Affordant | Humans use breadcrumb popovers and Cmd-K; AI uses URLs and a machine-readable nav index. Both are text-first by design. |
| 4. | Classy | No hamburger, no overflow menu, no left-rail drawer. The chrome shrinks instead of growing with features. |
| 5. | Singular | One header bar, one palette, one mini-graph. New features earn placement; they don't accumulate as chrome. |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-nav-breadcrumb-header | [Breadcrumb Header](#breadcrumb-header) | Implemented | Header bar IS the breadcrumb of the current page's URL path |
| req-web-nav-segment-interactions | [Segment Interactions](#segment-interactions) | Implemented | Single-click navigates; chevron-click shows immediate sibling popover; alt-click opens expanded column-view |
| req-web-nav-auto-parent | [Auto-Derived Parent From URL](#auto-derived-parent-from-url) | Implemented | Each URL segment is a breadcrumb level; v0 has no explicit override |
| req-web-nav-command-palette | [Command Palette Affordance](#command-palette-affordance) | In Development | Cmd-K + chrome affordance + Pages index landed; entity / recent-visits / migrated-chrome indexing still Proposed (ACIDs -3 + -4) |
| req-web-nav-mini-graph | [Mini-Graph Affordance](#mini-graph-affordance) | Backlog | Reserved chrome slot held; mini-graph itself is backlog pending sibling `spec-viz-mini-map.md` |
| req-web-nav-no-hamburger | [No Hamburger Menu](#no-hamburger-menu) | Implemented | Hard prohibition; defends the design against drift |
| req-web-nav-chrome-budget | [Chrome Budget](#chrome-budget) | Implemented | Header contents enumerated and capped at five elements |
| req-web-nav-index-endpoint | [Machine-Readable Nav Index](#machine-readable-nav-index) | Implemented | `/__nav-index.json` enumerates reachable pages + canonical breadcrumb paths |
| req-web-nav-page-discoverable | [Page Discoverability Gate](#page-discoverability-gate) | Implemented | Pages requiring URL parameters opt out of all browse-discovery surfaces via a `discoverable=False` flag |

## Requirements

### Breadcrumb Header
----
RID: `req-web-nav-breadcrumb-header`
Status: `Implemented`

The header bar on every TAP page renders the current page's URL path as a clickable breadcrumb, with each path segment as a separate clickable level. The header bar *is* the breadcrumb — there is no separate breadcrumb line below or above the chrome.

#### Status Details

Supersedes the prior revision of this spec, which proposed a classic web-based hamburger menu with a `Navigation` node + `NAV_PAGE` edge model. That revision was Proposed but never implemented; this revision drops the hamburger model entirely and replaces it with the breadcrumb-header system described here. The `Navigation` node concept is dropped. The `NAV_PAGE` edge type is dropped from this spec; whether to keep it in `tap_grid` registries for future per-page link rendering is a separate decision (recommend: drop until a real consumer needs it).

#### Implementation

- The header bar contains, in left-to-right order: the product mark (e.g., `TAP`), the breadcrumb segments, the session tag, the command-palette affordance, and the mini-graph slot.
- The breadcrumb begins with the root segment (the home page, `/`) and extends through each URL path slice.
  - Example: URL `/samsite/compliance/oscal` produces breadcrumb `[home] › samsite › compliance › OSCAL SSP`.
- Each segment renders as a clickable link to its corresponding URL prefix.
- The last segment (the current page) is rendered with active styling to communicate position.
- The breadcrumb truncates from the middle when the path is too long for the header width (collapse to `[home] › … › grandparent › parent › current`); the collapsed segments remain accessible through the chevron popover on the ellipsis.

#### Development

The breadcrumb-as-chrome approach collapses two surfaces (where-am-I + how-do-I-navigate) into one. It also makes navigation state shareable: any URL communicates the full breadcrumb to the next viewer or agent, without requiring server state.

The user's mental model is reinforced: each segment is a place, the path is a story of how we got here, and going back is a click on any ancestor rather than a guess at which menu item leads to "home."

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-breadcrumb-header-1 | Header Is Breadcrumb | Implemented | The header bar on every page renders the page's URL path as a breadcrumb; no separate breadcrumb line exists elsewhere. | `tap_web/templates/tap_web/base.html` chrome rewritten in Phase 2. |
| req-web-nav-breadcrumb-header-2 | Each Segment Clickable | Implemented | Every breadcrumb segment links to its URL-prefix slice. | Parent segments render as `<a>`; current renders as a non-link `<span>` (per ACID-3). |
| req-web-nav-breadcrumb-header-3 | Current Segment Active | Implemented | The last (current) segment uses an active visual style to communicate position. | `text-white font-medium aria-current="page"`. |
| req-web-nav-breadcrumb-header-4 | Middle-Collapse On Overflow | Implemented | When the breadcrumb exceeds the header width, the middle of the path collapses to an ellipsis that remains interactively reachable. | `tap_web/static/tap_web/js/breadcrumb.js` `applyOverflowTruncation()` uses ResizeObserver to keep first 1 + last 2 segments; clicking the `…` reveals the hidden segments via the chevron-popover infrastructure. |

#### Future

Multi-perspective breadcrumbs: a future revision may allow the breadcrumb path to reflect a *dimension* or *perspective* rather than only the URL, so two users on different perspectives see different breadcrumbs for the same URL. Out of scope for v0.


### Segment Interactions
----
RID: `req-web-nav-segment-interactions`
Status: `Implemented`

Each breadcrumb segment supports three distinct interactions, optimized for the three different navigation intents users have at any level: go there, see what else is at this level, see the whole tree.

#### Implementation

- **Single-click on the segment text** — navigates to that segment's URL.
- **Single-click on a small chevron immediately after the segment text** — opens a low-chrome *sibling popover* anchored to that segment. The popover lists the sibling pages at the same hierarchy level, ordered consistently (alphabetical for v0; ordering hint is a future seam). Clicking a sibling navigates there. Clicking outside dismisses.
- **Alt/option-click on either the segment or the chevron** — opens an *expanded column-view explorer*: a wider panel that simultaneously shows siblings at every breadcrumb level from root to current. Looks like a Finder column view collapsed into the header; gives the user a one-shot map of the entire vicinity, not just one level.

The two popover modes (immediate vs. expanded) compose: the immediate popover is the daily lightweight tool, the column-view is the "show me everything near me" deep dive. Same data source; different visual density.

#### Development

Two interactions, two different scales of "what's nearby." The immediate popover is for the daily case ("what are my siblings here"). The column-view is for the deeper "I want to remap" case. Forcing users to pick one mode would push them toward menus elsewhere; offering both, gated by the alt key, keeps the breadcrumb the answer for both use cases.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-segment-interactions-1 | Click Navigates | Implemented | Single-click on a segment's text navigates to that segment's URL. | Default browser anchor behavior. |
| req-web-nav-segment-interactions-2 | Chevron Opens Popover | Implemented | Single-click on the chevron next to a segment opens a sibling popover anchored under that segment. | `tap_web/static/tap_web/js/breadcrumb.js` `showSiblingPopover` — chevron is a `<button>` with `data-tap-chevron` + `data-tap-sibling-url`. |
| req-web-nav-segment-interactions-3 | Alt-Click Opens Column View | Implemented | Alt/option-click on the segment or chevron opens an expanded column-view showing siblings at every breadcrumb level. | `showColumnView` — one column per breadcrumb depth, on-path entries highlighted. |
| req-web-nav-segment-interactions-4 | Popover Click-Outside Dismisses | Implemented | Both the immediate popover and the column-view dismiss on click-outside. | Esc also dismisses. |

#### Future

Right-click context menu (e.g., "open in new tab", "copy URL", "pin to favorites") is deferred; the same data source can drive it when needed.


### Auto-Derived Parent From URL
----
RID: `req-web-nav-auto-parent`
Status: `Implemented`

A page's breadcrumb parent is derived from its URL by removing the trailing path slice. No explicit page-to-parent edge is required in v0. The URL hierarchy is the canonical hierarchy.

#### Implementation

- For URL `/<seg-1>/<seg-2>/…/<seg-N>`, the breadcrumb is `[home] › <seg-1> › <seg-2> › … › <seg-N>`.
- For each segment, the renderer attempts to resolve a registered Page entity at the URL prefix `/<seg-1>/…/<seg-k>`. If a Page is registered, its `name` becomes the segment's display label and its URL becomes the segment's link target. If no Page is registered at that prefix, the segment is rendered as plain text (the raw slug, title-cased), unclickable.
- The home segment `/` is special: it always displays the product mark (`TAP`), always links to `/`, and never collapses.

Parameterized URL paths (e.g., `/object/<entity_type>/<url_id>/`) are out of scope for the auto-derive rule in v0 — those routes generate breadcrumbs through a different code path that knows the entity's display name and entity_type. Captured in the Future section.

#### Development

Auto-derive is dead simple to implement, matches what users already expect from URLs, and doesn't require plugin authors to declare anything. The cost: pages can't override their breadcrumb parent. The benefit in v0: zero plugin friction, zero data model surface area.

If a real need for breadcrumb-different-than-URL emerges, the seam is `Page.parent_url` (a property that overrides the auto-derive). Not built; not used by anything in v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-auto-parent-1 | URL Drives Hierarchy | Implemented | A page's breadcrumb path is the slash-separated decomposition of its URL. | `tap_web/navigation.py` `build_breadcrumb()`. |
| req-web-nav-auto-parent-2 | Registered Pages Are Clickable | Implemented | Breadcrumb segments whose URL prefix matches a registered Page link to that Page and use its name. | One batched Page query resolves all prefixes. |
| req-web-nav-auto-parent-3 | Unregistered Segments Render As Text | Implemented | Segments whose URL prefix has no registered Page render as unclickable plain text (raw slug, title-cased). | Also applies to `discoverable=False` Pages — see `req-web-nav-page-discoverable-3`. |
| req-web-nav-auto-parent-4 | Home Is Stable | Implemented | The home segment `/` always renders as the product mark, always links to `/`, and never collapses under overflow truncation. | Template short-circuits on `is_home` before checking registration; overflow truncation preserves the first segment unconditionally. |

#### Future

`Page.parent_url` override field for the case where a page wants a non-URL-derived breadcrumb parent. Parameterized entity routes (`/object/<type>/<id>/`) get their breadcrumb from the entity itself rather than the URL pattern; either keep that as a separate renderer path or fold it into a generalized "page reports its own breadcrumb" extension.


### Command Palette Affordance
----
RID: `req-web-nav-command-palette`
Status: `In Development`

#### Status Details

MVP scope landed (Phase 4 + palette tree mode in Phase 6): Cmd-K binding, header affordance button, fuzzy-search input, tree-mode rendering of every registered Page on empty query, flat ranked list on typed query, click-or-Enter to navigate, click-outside/Esc to dismiss. Implementation in `tap_web/static/tap_web/js/palette.js` + `tap_web/static/tap_web/css/palette.css`.

ACIDs -1 (Keyboard Summonable) and -2 (Header Affordance) are `Implemented`. ACIDs -3 (Indexes Pages And Entities) and -4 (Subsumes Migrated Chrome) stay `Proposed`: the palette currently indexes Pages only, not entities / recent visits / platform commands, and the three placeholder chrome icons (admin / history / layers) were removed in Phase 2 but not yet re-added as palette commands. Promoting -3 and -4 is the next palette work block.

A keyboard-summonable command palette (Cmd-K on macOS, Ctrl-K elsewhere) is the platform-level reach-anywhere surface. Everything not reachable through the breadcrumb path is reachable through the palette. Detailed behavior of the palette itself lives in a sibling spec (`tap_web/specs/spec-web-command-palette.md`); this requirement enumerates only the palette's *contract with the navigation system*.

#### Implementation

- The palette is summonable from any TAP page via the Cmd-K / Ctrl-K shortcut.
- A visual affordance for the palette lives in the header bar (a search-icon button labeled with the keyboard shortcut on hover); clicking it opens the palette identically to the shortcut.
- The palette indexes, at minimum: every registered Page, every TAP-managed entity (by `name` + `entity_type`), the user's recent visits (last 10), and the platform-level commands (account / session / dimension controls).
- Commands that today sit in the header bar (clock/history affordance, layers/dimension badge, user/account icon) migrate **into the palette** rather than living as permanent header chrome.
- The palette's UI specification — fuzzy matching algorithm, result ordering, scope filtering, keyboard navigation — is owned by the sibling palette spec.

#### Development

The palette absorbs everything that doesn't earn permanent chrome. The discipline this enforces is the protection against menu drift: when someone wants to add a new feature, the first answer is "it goes in the palette," and only if it's used constantly enough to be a permanent fixture does it earn a header slot.

For AI consumers, the palette is the primary cross-context action surface: a text input that maps to any action. Agents don't need to model "where is the foo menu" — they synthesize a palette query.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-command-palette-1 | Keyboard Summonable | Implemented | The palette opens via Cmd-K (macOS) or Ctrl-K (other platforms) from any TAP page. | Vanilla keydown listener in `palette.js`. |
| req-web-nav-command-palette-2 | Header Affordance | Implemented | A visible header affordance opens the palette and communicates the keyboard shortcut. | 🔍 + `⌘K` chip in the chrome (`tap-palette-affordance` class), `title="Search pages (⌘K)"`. |
| req-web-nav-command-palette-3 | Indexes Pages And Entities | Proposed | The palette searches across registered Pages, TAP entities, recent visits, and platform commands. | Pages indexing landed; entities + recent + commands are next-iteration work. |
| req-web-nav-command-palette-4 | Subsumes Migrated Chrome | Proposed | The clock/history, layers/dimension, and user/account controls that today live in the header bar move into the palette. | Migration paused: the three placeholder icons were deleted in Phase 2 without being re-added as palette commands. Requires the platform-commands surface that ACID-3's "commands" portion would bring. |

#### Future

Plugin-contributed commands (each plugin can register palette commands that operate in its domain) — sibling-spec concern. Per-context palette filtering ("only search within the current breadcrumb subtree") — sibling-spec concern.


### Mini-Graph Affordance
----
RID: `req-web-nav-mini-graph`
Status: `Backlog`

#### Status Details

Backlog — great idea, not v0 critical path. The chrome budget keeps the upper-right slot **reserved** (see `req-web-nav-chrome-budget` element 5) so the affordance can drop in when the sibling spec lands; the slot is empty in v0. This keeps the chrome from accumulating ad-hoc additions in what would otherwise be unused space, and makes it visible to reviewers that the slot is intentionally held.

The sibling spec (`tap_viz/specs/spec-viz-mini-map.md`) and the tap_viz Cytoscape primitives it relies on are the unlocking work; this requirement returns to `Proposed` and then moves through implementation when the substrate is in place.

The upper-right of the header bar contains a small live Cytoscape rendering of the current entity's local neighborhood: the entity + 3–5 nearest neighbors, clickable to navigate. Detailed sizing/rendering behavior lives in a sibling spec (`tap_viz/specs/spec-viz-mini-map.md`); this requirement enumerates only the mini-graph's *contract with the navigation system*.

#### Implementation

- The mini-graph occupies a fixed slot in the upper-right of the header bar, sized to be visible-but-not-dominant (rough target: 120–160 px wide, 32 px tall — exact bounds owned by the sibling spec).
- When the current page is an entity drill-down (e.g., `/object/<type>/<id>/`), the mini-graph renders that entity at center with its closest graph neighbors around it; clicking a neighbor node navigates to that entity's page.
- When the current page is not an entity drill-down, the mini-graph slot is empty or renders a small "go to landing graph" affordance — to be detailed in the sibling spec.
- Rendering uses the existing `tap_viz` Cytoscape primitives (re-using the same icons, colors, and node-style conventions that the main graph panels use) so the mini-graph reads as a true projection of TAP's data, not a separate widget.

#### Development

This is TAP's signature nav move and the *"huh, that's clever"* element of the chrome design. The graph isn't a metaphor in TAP — it's the substrate — and the mini-graph makes that visible at all times. Other apps can't do this credibly; TAP can.

It's also the answer to *"what's one step away from where I am"* — which is fundamentally the navigation question, expressed in graph terms instead of menu terms. The breadcrumb tells you the path you walked; the mini-graph tells you the doors you haven't opened.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-mini-graph-1 | Fixed Slot Upper-Right | Proposed | The mini-graph occupies a fixed slot in the upper-right of the header bar. | |
| req-web-nav-mini-graph-2 | Renders Current Entity + Neighbors | Proposed | On entity drill-down pages, the mini-graph shows the current entity at center with its closest graph neighbors. | |
| req-web-nav-mini-graph-3 | Neighbor Click Navigates | Proposed | Clicking a neighbor node in the mini-graph navigates to that entity's page. | |
| req-web-nav-mini-graph-4 | Re-Uses tap_viz Primitives | Proposed | The mini-graph uses the same node styling and icon resolution as the main graph panels. | |

#### Future

Mini-graph on non-entity pages (Pages, dashboards) — sibling-spec decides what the "neighborhood" of a Page is. Mini-graph as a zoom-out gesture — clicking the center entity expands to a larger graph view, possibly inline.


### No Hamburger Menu
----
RID: `req-web-nav-no-hamburger`
Status: `Implemented`

The TAP web platform has no hamburger menu, no overflow menu, no left-rail navigation drawer, and no equivalent collapse-everything-here surface. This is a hard prohibition; it exists to defend the design against the gravitational pull of "just add one more menu item somewhere."

#### Implementation

- No three-line hamburger icon anywhere in the chrome.
- No "More" or "..." overflow control in the header.
- No collapsible left rail (or right rail) that aggregates menu items.
- Features that would otherwise want a menu entry go into the command palette.

The reason this is a *requirement*, not a *guideline*: hamburger menus are the path of least resistance for any feature owner who wants their thing reachable. Without an explicit "no" in the spec, the chrome accumulates one item at a time until it becomes the same SaaS dashboard everyone else builds. The prohibition is the design.

#### Development

Reviewers can cite `req-web-nav-no-hamburger` when rejecting PRs that try to add menu-like surfaces. The presence of this requirement in the spec is itself the affordance.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-no-hamburger-1 | No Hamburger Icon | Implemented | No three-line / hamburger / overflow icon exists in any TAP chrome. | Verified by `tap_web/tests/test_navigation.py` chrome-affordance tests. |
| req-web-nav-no-hamburger-2 | No Menu Drawer | Implemented | No collapsible side-drawer that aggregates navigation items exists in any TAP chrome. | The samsite-nav-links hero-card panel was dropped in Phase 2 as a concrete enactment of this rule. |
| req-web-nav-no-hamburger-3 | Features Route To Palette | Implemented | New features that need broad reach are implemented as palette entries, not as new chrome elements. | Standing rule — enforced at review time, defended by this requirement. |

#### Future

If a real, repeated case for menu-like chrome surfaces emerges, the response is to revisit this requirement in spec — not to bypass it in code.


### Chrome Budget
----
RID: `req-web-nav-chrome-budget`
Status: `Implemented`

The header bar is the platform's only permanent chrome surface. Its contents are enumerated and capped. New permanent elements require a spec revision; ad-hoc additions are rejected.

#### Implementation

The header bar contains exactly the following, in this left-to-right order:

1. **Product mark** — the `TAP` wordmark, linked to `/`.
2. **Breadcrumb** — the active page's URL path, rendered per `req-web-nav-breadcrumb-header` and `req-web-nav-segment-interactions`.
3. **Session tag** — when a multi-session dev label is active, the `[<label>]` chip in the session tag style (see `spec-dev-multisession.md`).
4. **Command palette affordance** — the search-icon button (see `req-web-nav-command-palette`).
5. **Mini-graph slot** — the local-neighborhood graph (see `req-web-nav-mini-graph`). In v0 this slot is *reserved but empty* — the mini-graph requirement is `Backlog`; the slot exists in the chrome layout so nothing else accumulates into the space, and the mini-graph drops in when the sibling spec lands.

No sixth element. Features that earn permanent chrome require a new requirement in this spec.

#### Development

The cap is the discipline. The spec is the rejection mechanism for chrome bloat. Without an enumerated list, every team that needs visibility for its feature will add an icon to the header until the chrome becomes a tool palette.

The five elements were chosen because each answers a different always-present question:

- **Product mark** — "what am I in?" (TAP)
- **Breadcrumb** — "where am I?" (path) + "what's adjacent?" (popovers)
- **Session tag** — "is this a dev session?" (operational signal)
- **Palette affordance** — "how do I reach the rest of TAP?"
- **Mini-graph** — "what's one graph-step from here?" (the platform's signature view)

Removing any of these removes a category of question that has no other answer. Adding a sixth would compete with one of these for the user's eye.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-chrome-budget-1 | Enumerated List | Implemented | The header contains exactly the five enumerated elements; no others. | Product mark + breadcrumb + session tag + palette affordance + reserved mini-graph slot. |
| req-web-nav-chrome-budget-2 | Order Stable | Implemented | The five elements appear in the documented left-to-right order. | `tap_web/templates/tap_web/base.html`. |
| req-web-nav-chrome-budget-3 | Additions Require Spec Revision | Implemented | New permanent header elements require a new requirement in this spec; they cannot be added ad hoc. | Standing rule. |

#### Future

If a sixth element is genuinely necessary, the spec revision that adds it must explicitly explain which of the five current categories the new element fits into, or what new category it answers — to force the conversation rather than allow accumulation.


### Machine-Readable Nav Index
----
RID: `req-web-nav-index-endpoint`
Status: `Implemented`

TAP exposes a machine-readable index of every reachable Page, with each page's canonical breadcrumb path. The index is a first-class affordance for AI agents, automation scripts, and any consumer that needs to reason about the platform's navigation surface without scraping HTML.

#### Implementation

- An endpoint, tentatively `/__nav-index.json`, returns a JSON document enumerating registered Pages.
- Each entry contains: the page's URL, name, description (if any), and the ordered list of breadcrumb segments from root to that page (each segment as `{label, url}`).
- The index updates whenever Pages are added/removed from the grid; it is computed on request rather than cached for v0.
- The endpoint is unauthenticated for v0 (the index reveals only what's already discoverable by walking links); auth gating may be added in a future revision once user/permission model lands.
- The endpoint's exact schema is documented in this spec (below) — it is part of the platform contract, not a derivative.

v0 schema (illustrative):

```json
{
  "version": "0",
  "generated_at": "2026-05-27T00:00:00Z",
  "pages": [
    {
      "url": "/samsite/compliance/oscal",
      "name": "Samsite — OSCAL SSP Workbench",
      "description": "...",
      "breadcrumb": [
        {"label": "TAP",        "url": "/"},
        {"label": "samsite",    "url": "/samsite"},
        {"label": "compliance", "url": "/samsite/compliance"},
        {"label": "OSCAL SSP",  "url": "/samsite/compliance/oscal"}
      ]
    }
  ]
}
```

#### Development

The nav index is what makes "AI as first-class consumer" a measurable contract, not an aspiration. An agent fetches the index, picks a destination, navigates by URL. No HTML parsing, no UI scraping, no guessing where the menu lives.

It's also useful for tooling: a documentation generator can index the platform; a sitemap generator becomes trivial; a "what pages exist" inspection becomes one curl call.

The endpoint name uses the `__` prefix (e.g., `/__nav-index.json`) to follow the convention used by other platform-internal routes (e.g., synthetic pages at `/__entity-viewer`) — it's discoverable but namespaced away from user-facing slugs.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-index-endpoint-1 | Endpoint Exists | Implemented | An endpoint (e.g., `/__nav-index.json`) returns the nav index as JSON. | `tap_web/views.py` `nav_index_view`. |
| req-web-nav-index-endpoint-2 | Enumerates All Pages | Implemented | The index contains an entry for every registered Page. | Subject to the discoverability gate — see `req-web-nav-page-discoverable`. |
| req-web-nav-index-endpoint-3 | Each Entry Carries Breadcrumb | Implemented | Each page entry includes its full breadcrumb path as an ordered list of `{label, url}` segments. | Shares `build_breadcrumb()` with the chrome renderer so the chain is identical. |
| req-web-nav-index-endpoint-4 | Schema Documented In Spec | Implemented | The endpoint's response schema is documented in this spec, not in code-only contracts. | See the v0 schema block above. |

#### Future

Per-entity nav-index entries (a deeper index that includes drillable entities, not just registered Pages). Authentication / authorization filtering once a permission model exists. WebSocket / SSE push of index updates for long-lived agent sessions.


### Page Discoverability Gate
----
RID: `req-web-nav-page-discoverable`
Status: `Implemented`

A `discoverable` BooleanField on the `Page` model (default `True`) gates whether a Page appears in **any** of the browse-discovery surfaces — the palette, chevron popovers, column-view explorer, and the `/__nav-index.json` index. Non-discoverable Pages still resolve on direct visit and remain valid breadcrumb destinations *when the user is actually on a URL that nests under them*; only browse-style discovery is gated.

#### Status Details

The complaint that produced this requirement: pages registered at slugs like `/samsite/finding` (whose actual route is `/samsite/finding/<uuid:entity_id>`) appeared in the palette but rendered broken when clicked — they need a URL parameter the palette can't supply. Heuristic detection (introspecting panel configs for an `entity_id_var`-style declaration) was considered and rejected as brittle: pages can have arbitrary parameter mechanisms, and the discoverability metadata belongs on the Page entity, not cross-referenced from URL config.

#### Implementation

- The `Page.discoverable` field defaults to `True`. Most Pages are loadable as-is; the common case is automatic discoverability.
- Pages whose URL requires a parameter (typically `<entity_id>`) set `discoverable=False` in their GRIFT bundle.
- The nav-index endpoint filters `Page.objects.filter(discoverable=True)`.
- The breadcrumb helper (`build_breadcrumb`) also filters `discoverable=True` when resolving registered Pages, so an ancestor Page whose URL requires a parameter renders as plain text in the breadcrumb of a deeper-URL page rather than as a clickable link to a broken-render URL. Direct visit to the parameterized URL with a valid parameter still renders normally.
- The chevron popover, column-view, and palette tree all read from `/__nav-index.json`, so the single filter at the endpoint cascades to all four surfaces.

#### Development

This is the cheapest sustainable answer to "what pages are *actually* navigable from a discovery surface without me typing a UUID into the URL bar." The explicit flag costs one line per parameterized GRIFT batch; the gain is that every discovery surface auto-respects the same rule.

A future iteration may add **partial discoverability** — surfacing parameterized pages in the palette with a sub-picker for the entity (e.g., "Samsite Finding" → list of recent findings). That's the eventual UX once the palette indexes entities per `req-web-nav-command-palette-3`; until then, the all-or-nothing flag is the simplest contract that matches v0 reality.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-nav-page-discoverable-1 | Default Discoverable | Implemented | `Page.discoverable` defaults to `True`; new Pages are surfaced unless they explicitly opt out. | Migration `0010_historicalpage_discoverable_page_discoverable`. |
| req-web-nav-page-discoverable-2 | Nav-Index Filters | Implemented | `/__nav-index.json` returns only Pages with `discoverable=True`. | `nav_index_view` queryset filter. |
| req-web-nav-page-discoverable-3 | Breadcrumb Treats Non-Discoverable As Unregistered | Implemented | When `build_breadcrumb` resolves an ancestor URL prefix to a Page with `discoverable=False`, the segment renders as plain text (the unregistered-prefix branch), not as a clickable link. | The Page still loads on direct visit; only the breadcrumb link is suppressed. |
| req-web-nav-page-discoverable-4 | All Discovery Surfaces Honor The Gate | Implemented | Palette, chevron popovers, column view, and nav-index all respect `discoverable=False` because they share the nav-index data plane. | A future palette upgrade for partial discoverability (per `req-web-nav-command-palette-3`) may relax this for entities specifically. |

#### Future

Partial discoverability: surface parameterized Pages in the palette as `<Page Name> → pick entity` flows once the palette indexes entities (req-web-nav-command-palette-3). At that point the flag's semantic shifts from "this Page is not discoverable" to "this Page is only discoverable through an entity-picker affordance" — same default, expanded behavior on the opt-out side.


## Future Seams

A few directions intentionally deferred from v0, kept here as breadcrumbs for the next spec revision:

- **Explicit parent override** — `Page.parent_url` field for pages whose breadcrumb position differs from their URL.
- **Saved pins** — user-pinned Pages or entities that appear in a dedicated section of the command palette.
- **Perspective filtering** — breadcrumb path may vary by the user's active perspective / dimension; same URL, different chrome.
- **Right-click context menus** on breadcrumb segments — open-in-new-tab, copy-URL, pin-here.
- **Plugin-contributed palette commands** — each plugin registers palette commands that operate in its domain (covered by the palette sibling spec).
- **Parameterized-route breadcrumbs** — entity drill-down pages (`/object/<type>/<id>/`) report their own breadcrumb instead of relying on URL prefix derivation.
- **Authenticated nav-index** — index respects user permissions once a permission model lands.


## Status Vocabulary

| Status States | |
| --- | --- |
| Proposed | |
| Backlog | Wanted, intentionally deferred from this revision; distinct from `Proposed` (actively under consideration) and from Future Seams (not committed). |
| Approved for Development | |
| In Development | |
| Implemented | |
| Verified | |
| Refactoring | |
| Deprecating | |
| Deprecated | |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: \`...\``
`Status: \`...\``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details | |
| Implementation | |
| Development | |
| Acceptance Criteria | |
| Future | |
