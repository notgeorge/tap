# Finding Strip Panel Specification

## Philosophy

The Finding Strip is a horizontal row of compact tiles, each displaying a single headline metric for a compliance landing page — *"open violations,"* *"passing checks,"* *"informational findings,"* and similar one-glance numbers. It is the panel that answers *"what's the temperature of this environment right now?"* before the user drills into the graph or the alerts table.

The panel is intentionally generic in shape: each tile is configured by a label, a color accent, and a gryphon query whose result is rendered as a single integer. The tile's contract is *"give me one number with a label."* That keeps the panel reusable across landing pages — the FedRAMP 20x KSI demo on the Genericom landing is one specific configuration; a different compliance frame would configure different tiles against the same panel type.

The panel runs each tile's gryphon query at request time. There is no caching layer in v0; refresh cadence is "page load." The numbers reflect graph state at the moment the page renders.

The name *Finding Strip* is deliberate. Earlier iterations of this panel were called the *KPI Strip*, but in practice every tile shipped to date counts compliance findings — open violations, passing checks, informational items. The rename clarifies the intended use, distinguishes the panel from a hypothetical pure-metrics dashboard widget, and aligns with the verdict vocabulary (`passing` / `violation` / `informational`) the rest of the FedRAMP 20x KSI plugin uses.

## Goals

|    |                    |                                                                                       |
| :---: | ---             | ---                                                                                   |
| 1. | Single-Number Per Tile | Each tile shows exactly one integer; no chart, no sparkline, no list                   |
| 2. | Gryphon-Driven        | Each tile's value comes from a gryphon query, not a hand-coded panel callback         |
| 3. | Configurable Per Page | Tile content is per-instance config (panel.config["tiles"]), not panel-type code      |
| 4. | Resilient             | A failed tile renders an error indicator without crashing the panel                   |
| 5. | Plugin-Owned          | Panel type lives in the FedRAMP 20x KSI plugin in v0; future relocation is explicit Future work   |
| 6. | Horizontal Strip      | Tiles flex evenly across the panel width; no row wrapping configured                  |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-finding-strip-panel-type | [Panel Type Contract](#panel-type-contract) | Implemented | Class shape, registration, slug, label, view, css, config_defaults |
| req-finding-strip-tile-schema | [Tile Schema](#tile-schema) | Implemented | Per-tile keys: label, color, query, value_field, mode, hint |
| req-finding-strip-resolution | [Tile Resolution](#tile-resolution) | Implemented | Gryphon execution at request time; mode=first vs mode=sum; default 0 |
| req-finding-strip-error-handling | [Tile Error Handling](#tile-error-handling) | Implemented | Per-tile try/except; error string surfaced in tile; panel does not crash |
| req-finding-strip-rendering | [Rendering And Styling](#rendering-and-styling) | Implemented | Template structure, CSS conventions, dot accent, tabular-nums value, empty state |
| req-finding-strip-instance-config | [Instance Configuration](#instance-configuration) | Implemented | Panel instance configured via GRIFT at the consuming plugin; type-side stays generic |

---

### Panel Type Contract
----
RID: `req-finding-strip-panel-type`
Status: `Implemented`

The panel is a TAP plugin panel type registered with `tap_web.registry.panel_type_registry`. It exposes a fixed surface that the page rendering pipeline consumes.

#### Implementation

The panel type class lives at `plugins/fedramp_20x_ksi/panels/finding_strip/__init__.py` and exposes:

- `slug = "finding_strip"` — the type slug used in `panel_type_registry.register(slug, cls)` and matched by the panel instance's `view` template path.
- `label = "Finding Strip"` — human-readable type label.
- `view = "fedramp_20x_ksi/panels/finding_strip.html"` — the template the panel renders into.
- `css = ["fedramp_20x_ksi/css/finding_strip.css"]` — list of static asset paths the page injects.
- `config_defaults = {"tiles": []}` — default config; an instance with no `tiles` key renders the empty state.
- `get_view_context(panel, request) -> dict` — resolves each tile via gryphon and returns a render-ready context dict.

Registration happens in `Fedramp20xKsiConfig.ready()` via `panel_type_registry.register("finding_strip", FindingStripPanelType)`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-finding-strip-panel-type-1 | Slug Registered | Implemented | `panel_type_registry` has an entry for `finding_strip` after plugin startup. | |
| req-finding-strip-panel-type-2 | View Template Path | Implemented | `view` resolves to a real template under `fedramp_20x_ksi/templates/`. | |
| req-finding-strip-panel-type-3 | CSS Asset Listed | Implemented | The panel type declares `finding_strip.css` so the page pipeline injects it. | |
| req-finding-strip-panel-type-4 | Empty Default Config | Implemented | `config_defaults["tiles"] = []` so a freshly created instance renders the empty state rather than erroring. | |
| req-finding-strip-panel-type-5 | Plugin-Owned | Implemented | The panel type class lives in the FedRAMP 20x KSI plugin package. | Will be revisited in [Future](#future). |

#### Future

- Relocating the panel type to `tap_web` so any plugin can declare a Finding Strip instance without depending on the FedRAMP plugin. See [Future](#future).
- Adding an editor view (`editor_view` is `""` in v0).

---

### Tile Schema
----
RID: `req-finding-strip-tile-schema`
Status: `Implemented`

Each entry in `panel.config["tiles"]` is an object with a fixed set of keys controlling label, color, query, value extraction, and aggregation.

#### Implementation

Tile shape (per-tile, all fields except `query` and `label` optional):

| Key | Type | Default | Purpose |
| --- | --- | --- | --- |
| `label` | string | `""` | Tile heading text. Rendered in uppercase small caps via CSS. |
| `color` | CSS color string | `"#64748b"` (slate-500) | Accent dot color. Rendered as a small circular swatch left of the label. |
| `query` | string \| list[string] | `""` | gryphon query. List form is joined with `\n` for readability in GRIFT. |
| `value_field` | string | `"value"` | The row-alias key whose value becomes the tile's number. |
| `mode` | `"first"` \| `"sum"` | `"first"` | `"first"` reads `value_field` from `rows[0]`; `"sum"` adds `value_field` across all rows (treating missing values as 0). |
| `hint` | string | `""` | Optional secondary line under the label. Suppressed if empty. |

The `query` is executed against the `search_readonly` database alias via `tap_grid.gryphon.executor.execute_gryphon_raw`. The query is expected to return a `rows` envelope (the tabular shape produced by gryphon's `RETURN ... AS <alias>` projection).

There is no per-tile `inputs` map in v0; tile queries are parameter-less from the panel's perspective.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-finding-strip-tile-schema-1 | Required Fields | Implemented | A tile renders even if all keys except `query` are omitted; defaults apply. | |
| req-finding-strip-tile-schema-2 | List-Form Query | Implemented | `query` accepts a list[str] and joins with newline before execution. | Convenience for multi-line gryphon authoring in GRIFT JSON. |
| req-finding-strip-tile-schema-3 | String-Form Query | Implemented | `query` accepts a single string verbatim. | |
| req-finding-strip-tile-schema-4 | Default value_field | Implemented | When `value_field` is omitted, the panel reads the row key `"value"`. | |
| req-finding-strip-tile-schema-5 | Default mode | Implemented | When `mode` is omitted, behavior is `"first"`. | |

---

### Tile Resolution
----
RID: `req-finding-strip-resolution`
Status: `Implemented`

For each tile in `panel.config["tiles"]`, the panel runs the configured gryphon query at request time and reduces the result envelope to a single integer per the tile's `mode`.

#### Implementation

The resolution loop in `get_view_context` does, per tile:

1. Build the query string (joining if list-form).
2. Execute via `execute_gryphon_raw(query, {}, db_alias="search_readonly")`.
3. Read `envelope["rows"]` (defaulting to `[]`).
4. Reduce:
   - `mode == "sum"`: `value = sum(row.get(value_field) or 0 for row in rows)`.
   - `mode == "first"` (default): `value = rows[0].get(value_field) if rows else None`.
5. If `value is None`, render as `0` in the tile context.

The loop is deliberately sequential — one query per tile, executed in declared order — for v0 simplicity. Concurrent tile resolution is Future work.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-finding-strip-resolution-1 | Read-Only Alias | Implemented | Tile queries execute against `search_readonly` (per spec-grid-search read-only enforcement). | |
| req-finding-strip-resolution-2 | Sum Mode Across Rows | Implemented | `mode == "sum"` aggregates `value_field` across all rows; missing values count as 0. | |
| req-finding-strip-resolution-3 | First Mode From Rows[0] | Implemented | `mode == "first"` returns the first row's `value_field` value. | |
| req-finding-strip-resolution-4 | Empty Rows Renders Zero | Implemented | A tile whose query returns no rows renders `0`, not blank. | |
| req-finding-strip-resolution-5 | Per-Tile Sequential | Implemented | Tiles resolve in declared order, one query at a time. | Concurrency is Future work. |

#### Future

- Concurrent tile resolution (asyncio.gather or thread pool) for landing pages with many tiles.
- Optional per-page or per-tile cache (e.g. 30s TTL) to amortize identical queries across panels.
- Per-tile `inputs` map so tile queries can take request-time parameters (e.g. dimension filters from URL).

---

### Tile Error Handling
----
RID: `req-finding-strip-error-handling`
Status: `Implemented`

A failed tile produces an error indicator in its slot but does not interfere with sibling tiles or the rest of the page.

#### Implementation

The resolution loop wraps the per-tile gryphon execution in a `try/except` (broad). On exception:

- The exception is logged via `logger.exception()` so the failure shows up in server logs with traceback.
- The tile context carries `error: str(exc)` instead of a value.
- The template renders an inline `error` indicator (italic red text "error", with the full message in the `title` attribute for hover) in place of the value.

The panel does not retry, surface the error to other tiles, or block page rendering.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-finding-strip-error-handling-1 | Per-Tile Try/Except | Implemented | An exception in tile N's query does not affect tile N±1 or the rest of the page. | |
| req-finding-strip-error-handling-2 | Logged Exception | Implemented | `logger.exception` captures the full traceback to server logs. | |
| req-finding-strip-error-handling-3 | Error Surfaced In Tile | Implemented | The tile slot renders an "error" indicator with the message in the hover title. | |
| req-finding-strip-error-handling-4 | No Page Crash | Implemented | The panel returns a valid context dict even if every tile fails. | |

---

### Rendering And Styling
----
RID: `req-finding-strip-rendering`
Status: `Implemented`

The panel renders into a single template that lays the tiles out as a flex row.

#### Implementation

Template at `plugins/fedramp_20x_ksi/templates/fedramp_20x_ksi/panels/finding_strip.html`:

- Outer `<div class="tap-panel tap-panel--finding-strip">` with optional `panel_header` include (suppressed by `panel.config.hide_header = true`).
- If `finding_strip_tiles` is non-empty, render `<div class="tap-finding-strip">` containing one `<div class="tap-finding-strip-tile">` per tile.
- Each tile contains: a colored dot (`tap-finding-strip-tile__dot` with `background-color` from the tile's `color`), a body block (label + optional hint), and either a value (`tap-finding-strip-tile__value`) or an error indicator (`tap-finding-strip-tile__error`).
- If `finding_strip_tiles` is empty, render `<div class="tap-finding-strip--empty">` with text "No finding-strip tiles configured."

CSS at `plugins/fedramp_20x_ksi/static/fedramp_20x_ksi/css/finding_strip.css`:

- `.tap-finding-strip` — flex row, gap `0.75rem`.
- `.tap-finding-strip-tile` — `flex: 1 1 0` (each tile claims an equal share of the strip), white background, slate-200 border, subtle shadow, min-height `64px`.
- `.tap-finding-strip-tile__dot` — `0.625rem` circle.
- `.tap-finding-strip-tile__label` — uppercase small caps, slate-500.
- `.tap-finding-strip-tile__value` — `1.875rem` semibold, tabular-nums (so digits don't shift width across refresh).
- `.tap-finding-strip-tile__error` — italic red.
- `.tap-finding-strip--empty` — italic slate-400, no border, indicating empty state without taking up tile space.

Color and typography conventions are TAP-default (slate scale), not framework-specific — the panel does not declare KSI brand colors, so it remains visually neutral when reused outside the FedRAMP context.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-finding-strip-rendering-1 | Flex Row Layout | Implemented | Tiles render side-by-side via `display: flex`; each tile claims an equal share via `flex: 1 1 0`. | |
| req-finding-strip-rendering-2 | Color Dot Accent | Implemented | The tile's `color` is applied to the small circular accent dot, not to text or background. | |
| req-finding-strip-rendering-3 | Tabular Nums | Implemented | Value text uses `font-variant-numeric: tabular-nums` so digit width is stable. | |
| req-finding-strip-rendering-4 | Hint Optional | Implemented | The hint line renders only when `hint` is truthy. | |
| req-finding-strip-rendering-5 | Empty State | Implemented | When `panel.config["tiles"]` is empty or unset, the panel renders the empty-state element instead of an empty strip. | |
| req-finding-strip-rendering-6 | Hide Header Honored | Implemented | `panel.config.hide_header = true` suppresses the standard panel header include. | |

---

### Instance Configuration
----
RID: `req-finding-strip-instance-config`
Status: `Implemented`

Panel instances are seeded via GRIFT at the consuming plugin (not the panel-type-owning plugin). Tile content is per-page, per-deployment configuration; the panel type itself stays generic.

#### Implementation

A panel instance is a `panel`-typed entity whose `view` field equals the panel type's `view` template path. The instance's `config` field carries the `tiles` list and any flags like `hide_header`.

For Genericom, the instance is seeded in [plugins/genericom/grift/pages-finding-strip.grift.json](../../genericom/grift/pages-finding-strip.grift.json) as a single batch:

- A `panel` entity (slug `genericom-finding-strip`, view `fedramp_20x_ksi/panels/finding_strip.html`) with one tile in `config.tiles` running the canonical "open findings per entity" gryphon query in `mode: "sum"` to produce the headline alert count.
- A `USES_PANEL` edge from the Genericom landing page to the panel instance, slot `kpi`, satisfying the page's `panels.<slot>` hotlink.

The panel-type plugin (`fedramp_20x_ksi`) does NOT seed a default Genericom instance — that would couple the type to one consumer. The Genericom plugin is responsible for its own instance.

The current Genericom Finding Strip configuration ships exactly one tile ("Open Alerts") because that was the v0 demo target. Adding more tiles — for example a green "Passing" tile and a blue "Informational" tile — is a per-instance configuration change, not a panel-type change.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-finding-strip-instance-config-1 | Instance In Consumer Plugin | Implemented | The Genericom landing's Finding Strip panel instance is seeded by `plugins/genericom/grift/pages-finding-strip.grift.json`, not by the FedRAMP plugin. | |
| req-finding-strip-instance-config-2 | Tile Config Lives In panel.config | Implemented | All tile content (label, color, query, mode, value_field, hint) lives in `panel.config["tiles"]`. | |
| req-finding-strip-instance-config-3 | Page Hotlink Wires Instance | Implemented | A `USES_PANEL` edge from page to panel, with `hotlink.value` matching the page-layout slot, mounts the instance into the page. | |

---

## Out Of Scope (v0)

- **Click-through behavior.** Tiles are display-only. Linking a tile to a filtered alerts table or a detail page is Future work.
- **Sparklines or trend indicators.** Each tile is a single integer; no over-time visualization in v0.
- **Editor view.** The panel type declares `editor_view = ""`; in-page editing of tile content is not supported.
- **Per-tile inputs / parameters.** Tile queries are parameter-less. Adding `inputs` per tile (with values from page state, URL query params, or session context) is Future work.
- **Caching.** Each page load re-runs every tile's query.
- **Verdict-aware tile presets at the panel-type level.** The panel does not treat "violation" / "passing" / "informational" as built-in concepts — those vocabularies live in the tile's gryphon query and the per-tile `color`. Built-in presets are Future work.

## Future

- **Promote the panel type to `tap_web`.** The panel type carries no FedRAMP-specific logic. Moving the type into `tap_web` would let non-FedRAMP plugins declare Finding Strip instances without depending on this plugin. The FedRAMP plugin would still seed FedRAMP-specific *instances* via GRIFT, but the type would be a TAP primitive.
- **Verdict-built-in tile presets.** Convenience presets for "violations open," "passing checks," and "informational" so consumers don't have to repeat the gryphon query plumbing for the canonical compliance tiles.
- **Click-through to filtered views.** Tile-level click handler that opens a filtered alerts table or navigates to a detail page.
- **Per-tile cache TTL** with a server-side invalidator hook.
- **Concurrent tile resolution** for pages with many tiles.
