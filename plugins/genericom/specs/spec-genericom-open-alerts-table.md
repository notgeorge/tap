# Genericom Open Alerts Table Specification

> **⚠️ One-off demo construction.** This spec describes a deliberately rigid, plugin-owned panel built for the Anwar / Ace of Clouds demo. It cuts corners against the long-term standard-table-panel direction in the name of getting data on the board. See the [One-Off Choices](#one-off-choices) section under Philosophy for the full list of compromises and the reasoning behind each — those notes are the input for a later refactor pass that folds this back into the reusable system.

## Philosophy

The Genericom AWS top-level page today shows a single Cytoscape graph panel — a spatial view of the demo cloud estate. The graph is excellent at "where does this thing live in the architecture?" but poor at "what is broken right now?". A flat, sortable list of currently open findings answers the second question directly and lets a viewer triage by recency without panning the graph.

This spec adds a second panel beneath the graph on the Genericom page: a **plugin-owned** table panel that renders open findings using Tabulator. It does not extend the standard `tap_web` Table Panel; it is its own panel type, registered by the Genericom plugin, with its own template and column set hard-coded for the Finding model. The reusable abstraction (column overrides, finding-aware column modes, schema-driven cell renderers) is explicitly deferred — see One-Off Choices below.

The page lays out as a vertical scroll: the graph renders first at a fixed height (its existing presentation), and the alerts table flows beneath it, growing in height with the row count. The viewport scrolls when the table outgrows what fits below the graph. This is a deliberate departure from the page system's typical fixed-fraction (`Nfr`) row sizing.

The panel is intentionally minimal in v0: open findings only, no exception-awareness, no remediation workflow, no row click-through, no orphan handling — the dataset is curated upstream to guarantee every open finding has a `HAS_FINDING` parent. It is a top-of-page situational summary, not a worklist tool.

### One-Off Choices

This spec accepts the following compromises so the panel can ship before the demo. Each item is a known shortcut, not a long-term position. After the demo, fold these back into the standard table panel and / or proper service-layer abstractions.

1. **Plugin-owned panel type instead of extending the standard Table Panel.** The standard `tap_web` Table Panel only supports `column_mode: "common_metadata"` today, and `Associated System` plus `description` are not in that set. Rather than land `column_overrides` or a new `column_mode` (the right long-term move), the Genericom plugin registers its own panel type with a hard-coded column list. *Why:* unblocks the demo without modifying a shared standard under time pressure; the rigid column set is acceptable because no other view ever needs to reuse it. *Refactor signal:* if a second plugin needs a similar finding table, that's the trigger to merge this back into the standard panel.

2. **Hard-coded column definitions in JS.** Columns (Title, Associated System, Description, Created, Last Updated) are baked directly into the panel's static JS file rather than driven by a Panel `config` schema. *Why:* avoids designing and validating a config contract for a single instance. *Refactor signal:* the moment a second instance wants a different column set or order, drive columns from `Panel.config`.

3. **No `Panel.config` JSON Schema.** The panel's `config` field is unused / minimal. The reusable Table Panel spec requires a validated config schema; this one ignores it. *Why:* nothing on the panel is configurable, so a schema would be ceremony. *Refactor signal:* same as above — first parameterization need triggers the schema work.

4. **No pagination.** The full result set is loaded into the page at render time and Tabulator handles client-side virtualization only. *Why:* the demo dataset is bounded (a handful of findings against the seeded Genericom estate) and round-tripping pagination through gryphon adds complexity. *Refactor signal:* any production-scale dataset.

5. **Drops the Genericom-scoped predicate from the gryphon query.** Per the user, the demo dataset will only contain findings against Genericom assets, so the search collects *all* open findings grid-wide. *Why:* avoids designing a "is this entity in the Genericom subgraph?" predicate before dimension-based search lands. *Refactor signal:* the moment a non-Genericom plugin seeds findings, this predicate becomes mandatory; replace with dimension-based search per the eventual standard.

6. **No exception-awareness.** Findings covered by an active `Exception` via `COVERS_FINDING` are shown identically to uncovered findings. *Why:* exception filtering is a real UX question that should be answered properly, not hacked into a one-off. *Refactor signal:* product decision on how exception-covered findings should appear in alert lists.

7. **No row click-through, no severity, no grouping.** Per the user, deferred to Future Work. *Why:* scope discipline for the demo. *Refactor signal:* product priorities.

8. **Reuses the Tabulator assets shipped by `tap_web`'s standard Table Panel** (CSS + JS library files), with a Genericom-specific glue JS file. No new third-party JS library is added. *Why:* keeps the asset surface flat and avoids a second copy of Tabulator. *Refactor signal:* none — this is the right call regardless and should be preserved through any later refactor.

9. **Column data is shaped server-side into a flat row payload, not the standard subgraph envelope.** The panel's `get_view_context()` joins each finding to its parent system in Python and emits a flat `[{title, system, description, created, updated}, ...]` array. *Why:* drops the client-side join logic and edge-walking the standard table panel and KSI compliance view do, simplifying the JS to "render this list". *Refactor signal:* once column rendering is driven by a schema, switch to the standard envelope so row shape isn't bespoke per panel.

10. **Assumes zero orphan findings; does not handle the "no parent system" case.** A pre-implementation audit confirmed 0 orphans across 7 open findings (2026-05-04). The implementation does not check for, render, or warn about findings missing a `HAS_FINDING` parent — those are pruned upstream as a dataset invariant. *Why:* removes a whole branch of UI logic, server-side warning plumbing, and column formatter complexity for a case that should never exist in practice. *Refactor signal:* if any view of findings ever needs to surface integrity issues, build that as a generic data-quality dashboard rather than baking it into a one-off alerts table.

11. **Page mixes `1fr` graph with `auto` alerts row; graph compresses when the table is short.** The page-layout schema supports `"auto"` row heights, and the alerts row uses it. But because the graph row is `1fr`, when the table content is shorter than `viewport - kpi`, the graph row claims the leftover space and visually compresses. With a long table the page scrolls correctly. *Why:* avoiding this requires either pinning the graph to a viewport-minimum (CSS-only) or extending the page-layout schema to express "graph fills viewport, table flows below". The visual artifact is acceptable for the demo — the data is what matters. *Refactor signal:* if the demo presentation needs to "feel" graph-first, add a viewport-anchored min-height pattern to the page-layout schema (e.g. `min-vh` per row) or scope a CSS rule to the Genericom page.

## Goals

|     |                  |                                                                                          |
| :-: | ---              | ---                                                                                      |
| 1.  | Co-located       | The alerts table sits on the existing Genericom AWS top-level page beneath the graph     |
| 2.  | Plugin-Owned     | A self-contained panel type registered by the Genericom plugin                           |
| 3.  | Open-Only        | Shows only findings with `status = "open"`                                               |
| 4.  | All-Findings     | Demo-scoped: collects every open finding in the grid (Genericom is the only seeder)      |
| 5.  | System-Linked    | Every row identifies the system the finding is attached to via `HAS_FINDING`             |
| 6.  | Recency-First    | Default sort is most recently updated first                                              |
| 7.  | Asset-Frugal     | Reuses Tabulator from `tap_web`; no new third-party JS                                   |
| 8.  | Flow Layout      | Graph at fixed height; alerts table flows beneath at content height; page scrolls        |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-genericom-alerts-page | [Page Layout Update](#page-layout-update) | Implemented | Adds a second row to the Genericom page; alerts row flows at content height |
| req-genericom-alerts-panel-type | [Plugin-Owned Panel Type](#plugin-owned-panel-type) | Implemented | Genericom registers `genericom-open-alerts` as its own panel type |
| req-genericom-alerts-search | [Open Alerts Search](#open-alerts-search) | Implemented | Gryphon Search returning all open findings (demo-scoped) joined to their parent system |
| req-genericom-alerts-columns | [Alert Table Columns](#alert-table-columns) | Implemented | Title, Associated System, Description, Created, Last Updated |
| req-genericom-alerts-sort | [Default Sort](#default-sort) | Implemented | Most recent `updated_at` first |
| req-genericom-alerts-no-orphans | [No-Orphan Dataset Invariant](#no-orphan-dataset-invariant) | Implemented | The seeded dataset must contain zero open findings without a `HAS_FINDING` parent |
| req-genericom-alerts-assets | [Asset Reuse](#asset-reuse) | Implemented | Reuses Tabulator CSS/JS shipped by `tap_web`'s standard table panel |

---

### Page Layout Update
----
RID: `req-genericom-alerts-page`
Status: `Implemented`

The Genericom page (`/genericom`, slug `/genericom`) layout is extended from a single full-height graph row to two stacked rows: the existing graph on top at a fixed height matching its current presentation, the new alerts table flowing beneath at content-driven height. The page itself scrolls vertically when the table grows beyond the remaining viewport.

#### Implementation

- The Genericom Page entity's `layout` JSON is updated to:

  ```json
  {
    "columns": {
      "col-1": {
        "width": "1fr",
        "rows": {
          "row-1": {"panel-id": "main", "height": "<graph-fixed-height>"},
          "row-2": {"panel-id": "alerts", "height": "auto"}
        }
      }
    }
  }
  ```

- The exact `<graph-fixed-height>` value (e.g. `"600px"`, `"75vh"`, or whatever matches the graph's current rendered size) is finalized at implementation time after visual inspection.
- The page-layout schema already accepts `"auto"` row heights (per `spec-web-page.md`); no schema change required. The alerts row uses `height: "auto"`.
- A new `USES_PANEL` edge from the Page to the alerts Panel is seeded with `properties.hotlink.value = "alerts"` so it occupies the `row-2` slot.
- The existing graph panel and its `USES_PANEL` edge are unchanged; only the layout JSON and the new `USES_PANEL` edge are added.
- All page, panel, search, and edge changes are seeded via GRIFT — page-layout patch in [plugins/genericom/grift/pages.grift.json](plugins/genericom/grift/pages.grift.json), new entities in a sibling bundle [plugins/genericom/grift/open-alerts.grift.json](plugins/genericom/grift/open-alerts.grift.json).

#### Status Details

The page-layout JSON schema accepts `"auto"` row heights as a first-class option (per `spec-web-page.md` `req-web-page-layout`); the renderer translates `"auto"` rows to `flex: 0 0 auto`. No schema change was required.

The Genericom landing layout was already established by `pages-finding-strip.grift.json` as a 2-row stack (finding strip auto, graph 1fr). The Open Alerts implementation adds a third batch — in `open-alerts.grift.json` — that re-publishes the layout as a 3-row stack: finding strip (auto) → graph (1fr) → alerts (auto). Bundle order in the manifest places `open-alerts` after `pages-finding-strip` so the alerts patch wins. The top slot is named `finding-strip`; the panel was previously called the *KPI Strip* and the slot `kpi`, both renamed in lockstep when the verdict vocabulary landed.

A known visual artifact: when the table is short (e.g. 8 rows on a 900px viewport), the `1fr` graph row competes with the `auto` alerts row for vertical space and the graph compresses. The page does not yet pin the graph to a viewport-anchored minimum height. For long tables the page scrolls correctly; for the Anwar demo the compressed-graph behavior is acceptable. A graph viewport-min-height fix is deferred to Future Work.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-alerts-page-1 | Graph Above Table | Implemented | The Genericom page renders the graph in row-1 and the alerts table in row-2 in a single column. | |
| req-genericom-alerts-page-2 | Graph Fixed Height | Implemented | The graph row uses a fixed, presentation-matching height. | Tunable; value not load-bearing. |
| req-genericom-alerts-page-3 | Table Flows | Implemented | The alerts row uses content-driven height; the page scrolls when the table grows beyond the viewport. | Per One-Off Choice #11. |
| req-genericom-alerts-page-4 | Seeded Via GRIFT | Implemented | The layout change, panel, search, and edges are all seeded by the Genericom plugin's GRIFT files. | No code-side seeding. |

### Plugin-Owned Panel Type
----
RID: `req-genericom-alerts-panel-type`
Status: `Implemented`

The alerts table is a self-contained panel type registered by the Genericom plugin, with its own template, server-side context builder, and glue JS. It does **not** extend the standard `tap_web` Table Panel — see One-Off Choice #1.

#### Implementation

- The panel type lives in `plugins/genericom/panels/open_alerts/`:
  - `__init__.py` — panel type class
  - rendered template at `plugins/genericom/templates/genericom/panels/open_alerts.html`
  - `plugins/genericom/static/genericom/js/panel-open-alerts.js` — Tabulator init and column definitions
  - `plugins/genericom/static/genericom/css/panel-open-alerts.css` — minimal panel-specific styling; no full restyle of Tabulator
- The panel type is registered in `panel_type_registry` during the Genericom plugin's `AppConfig.ready()`.
- It conforms to the standard panel type contract from `spec-web-panel.md`: `slug`, `label`, `view`, `css`, `js`. No `editor_view` in v0 — the panel has no user-configurable options.
- Panel type slug: `genericom-open-alerts`.
- A single `Panel` instance is seeded with:
  - `slug`: `genericom-open-alerts`
  - `name`: `Genericom Open Alerts`
  - `view`: `panel_type_registry`-resolved (set by the panel type, not stored on the Panel)
  - `dimensions`: `{"tap.graph": "web"}` (consistent with the Genericom Page and Landing Graph)
  - `config`: `{}` — empty per One-Off Choice #3
- A `USES_SEARCH` edge from this Panel to the Open Alerts Search (`req-genericom-alerts-search`) provides the data binding.
- The panel header should display the title "Open Alerts".
- The panel must not depend on CDN-hosted assets.
- The panel must not embed inline JavaScript in rendered HTML.

#### Server-side rendering flow

The panel type's `get_view_context()`:

1. Resolves the linked Search via the `USES_SEARCH` edge.
2. Executes the search through `execute_search()` with `layer="extended"`.
3. For each finding node in the result, walks the `HAS_FINDING` edges in the envelope to find the parent system node. The panel relies on `req-genericom-alerts-no-orphans` to guarantee a parent always exists; if a finding is encountered with no `HAS_FINDING` parent, the panel logs a warning and skips the row (defensive only — should never fire).
4. Emits a flat row payload (One-Off Choice #9) of the form:

   ```json
   [
     {
       "title": "...",
       "system_name": "...",
       "system_id": "...",
       "description": "...",
       "created_at": "ISO-8601",
       "updated_at": "ISO-8601"
     }
   ]
   ```

5. Embeds the payload via `safe_json()` in the template under `<script id="genericom-open-alerts-data-{panel_id}">`.
6. The shipped JS reads the payload and initializes Tabulator.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-alerts-panel-type-1 | Plugin-Registered | Implemented | The panel type is registered in `panel_type_registry` during Genericom's `AppConfig.ready()`. | |
| req-genericom-alerts-panel-type-2 | Self-Contained | Implemented | All template, CSS, and JS for the panel live under `plugins/genericom/panels/open_alerts/`. | |
| req-genericom-alerts-panel-type-3 | Standard Contract | Implemented | The panel type conforms to the panel-type contract in `spec-web-panel.md`. | |
| req-genericom-alerts-panel-type-4 | Flat Row Payload | Implemented | `get_view_context()` emits a flat row array, not the standard subgraph envelope. | One-Off Choice #9 |
| req-genericom-alerts-panel-type-5 | safe_json Embedding | Implemented | The row payload is serialized via `safe_json()` per `req-web-panel-json-embed.sec`. | |
| req-genericom-alerts-panel-type-6 | No Inline JS | Implemented | All browser behavior is implemented in shipped static files. | |

### Open Alerts Search
----
RID: `req-genericom-alerts-search`
Status: `Implemented`

A new `Search` entity returns every open finding in the grid, including each finding's parent system entity in the same envelope. Per One-Off Choice #5, the search is **not** scoped to the Genericom subgraph — the demo dataset is the only finding-seeder, so a grid-wide query is equivalent in practice and avoids designing a scoping predicate before dimension-based search exists.

#### Implementation

- Search type: `gryphon`.
- Slug: `genericom-open-alerts`.
- Query (illustrative — final form to match gryphon syntax):

  ```
  MATCH (s)-[h:HAS_FINDING]->(f:finding)
  WHERE f.status = "open"
  ORDER BY f.updated_at DESC
  ```

- Inner JOIN only — orphan findings are excluded by construction. The dataset invariant in `req-genericom-alerts-no-orphans` guarantees this is equivalent to "all open findings".
- The search returns the standard subgraph envelope `{nodes, edges, info, warnings}`.
- `layer = "extended"` so the panel can resolve display names and entity-type metadata for the parent system without additional lookups.
- No pagination (One-Off Choice #4) — the demo dataset is bounded.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-alerts-search-1 | Gryphon-Backed | Implemented | The search uses `search_type: "gryphon"`. | |
| req-genericom-alerts-search-2 | Open Only | Implemented | The result set excludes findings with `status != "open"`. | |
| req-genericom-alerts-search-3 | Grid-Wide | Implemented | The search returns all open findings grid-wide; no Genericom-subgraph predicate in v0. | One-Off Choice #5 |
| req-genericom-alerts-search-4 | Includes Parent System | Implemented | When a `HAS_FINDING` parent exists, the parent node and edge are included in the envelope. | |
| req-genericom-alerts-search-5 | Extended Layer | Implemented | Search executes with `layer="extended"`. | |

### Alert Table Columns
----
RID: `req-genericom-alerts-columns`
Status: `Implemented`

The table renders five columns. Column definitions are hard-coded in `panel-open-alerts.js` per One-Off Choice #2.

#### Implementation

| Column            | Source                                           | Notes                                                                       |
| ---               | ---                                              | ---                                                                         |
| Title             | `finding.name`                                   | The finding's title text.                                                   |
| Associated System | Parent system from the `HAS_FINDING` edge        | Display the parent entity's `name`. Always present per `req-genericom-alerts-no-orphans`. |
| Description       | `finding.description`                            | Wraps cleanly; absorbs extra horizontal space (`widthGrow: 3`).             |
| Created           | `finding.entity.created_at`                      | When the finding entity was first persisted.                                |
| Last Updated      | `finding.entity.updated_at`                      | When the finding entity was last mutated.                                   |

- "Associated System" resolves to the parent entity's display name (`entity.name`). Whether to also show the parent's `entity_type` is deferred to Future Work.
- Date columns render in a human-readable format with full ISO timestamp on hover.
- Tabulator config: `layout: "fitColumns"` so columns absorb available horizontal space; `Description` uses `widthGrow: 3` to absorb the bulk; date columns are narrow with fixed width.
- No row click-through behavior in v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-alerts-columns-1 | Five Columns | Implemented | The table renders Title, Associated System, Description, Created, Last Updated. | |
| req-genericom-alerts-columns-2 | System From HAS_FINDING | Implemented | The Associated System column resolves to the parent entity of the finding's `HAS_FINDING` edge. | |
| req-genericom-alerts-columns-3 | Both Timestamps | Implemented | Both `created_at` and `updated_at` from the finding's Entity are surfaced as separate columns. | Inherited from `BaseModel` / `Entity`. |
| req-genericom-alerts-columns-4 | No Row Nav In V0 | Implemented | Rows are not click-through links in v0. | |
| req-genericom-alerts-columns-5 | Hard-Coded In JS | Implemented | Column definitions live in `panel-open-alerts.js`, not in `Panel.config`. | One-Off Choice #2 |

### Default Sort
----
RID: `req-genericom-alerts-sort`
Status: `Implemented`

The table's default sort order is most-recently-updated first so newly changed findings rise to the top of the view without user interaction.

#### Implementation

- The default ORDER BY in the gryphon query is `finding.updated_at DESC`. The pre-sorted order is preserved into the row payload so Tabulator's initial render matches.
- Tabulator is configured with an initial sort on the `Last Updated` column descending; user header-clicks may re-sort.
- Tie-breaking on equal `updated_at` falls back to `created_at DESC`, then `entity.id` for determinism.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-alerts-sort-1 | Updated Desc Default | Implemented | The table loads sorted by `updated_at` descending. | |
| req-genericom-alerts-sort-2 | User Resortable | Implemented | Users can re-sort by any sortable column via header click. | |
| req-genericom-alerts-sort-3 | Stable Ties | Implemented | Equal `updated_at` values are tie-broken by `created_at DESC` then `entity.id`. | |

### No-Orphan Dataset Invariant
----
RID: `req-genericom-alerts-no-orphans`
Status: `Implemented`

Every open finding in the seeded dataset must have at least one `HAS_FINDING` parent edge. The alerts table relies on this as a precondition rather than handling the missing-parent case in code.

#### Implementation

- The pre-implementation orphan audit (run 2026-05-04 against the current Genericom dataset) confirmed: 7 open findings, 0 orphans. The invariant holds today.
- A check is added to the Genericom plugin's test suite asserting that for every `Finding` with `status="open"` in the seeded data, at least one `HAS_FINDING` edge with `to_entity_id = finding.entity_id` exists. The test fails the build if a future GRIFT change introduces an orphan.
- The runtime `get_view_context()` adds a defensive guard: any finding encountered without a parent is logged at `WARNING` level and skipped. This is belt-and-suspenders — the test should catch it first.
- No UI affordance for orphans. No warning strip, no marker, no special row styling.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-alerts-no-orphans-1 | Audit Recorded | Implemented | The pre-implementation audit result is recorded in the spec or commit message. | |
| req-genericom-alerts-no-orphans-2 | Test Enforces Invariant | Implemented | A plugin test asserts zero orphan open findings in seeded data. | |
| req-genericom-alerts-no-orphans-3 | Runtime Defensive Guard | Implemented | `get_view_context()` skips and logs any finding it encounters without a `HAS_FINDING` parent. | Defensive only; should never fire. |

### Asset Reuse
----
RID: `req-genericom-alerts-assets`
Status: `Implemented`

The panel reuses the Tabulator CSS and JS already vendored under `tap_web/static/` for the standard Table Panel. No new copy of Tabulator is shipped with the Genericom plugin.

#### Implementation

- The panel type's static-asset declarations reference the existing Tabulator paths under `tap_web/static/` — same paths used by `tap_web/panels/table_panel/` and the KSI compliance view.
- Genericom-specific assets are limited to `panel-open-alerts.js` (Tabulator initialization, column definitions, payload reader) and `panel-open-alerts.css` (orphan-row highlighting and any minor layout tweaks).
- No CDN dependencies. No additional third-party JS libraries.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-alerts-assets-1 | Reuses Vendored Tabulator | Implemented | The panel reuses the Tabulator CSS/JS already shipped by `tap_web`. | |
| req-genericom-alerts-assets-2 | No CDN | Implemented | The panel ships no CDN-hosted asset references. | |
| req-genericom-alerts-assets-3 | No New Library | Implemented | No third-party JS library is added beyond what `tap_web` already ships. | |

## Future Work

These items are explicit in the One-Off Choices section above as refactor signals; collected here for the doc-traversal view.

- **Fold back into the standard Table Panel.** Land `column_overrides` (or a finding-aware `column_mode`) on `spec-web-panels-standard-table.md`, then replace this plugin-owned panel type with a standard Table Panel instance bound to a finding-aware column config.
- **Drive columns from `Panel.config`.** Move column definitions out of JS and into a validated config schema once a second column shape is required.
- **Dimension-based scoping for the search.** Replace the grid-wide query with a dimension-scoped predicate once dimension-based search lands and a non-Genericom plugin starts seeding findings.
- **Pagination.** Switch from full-payload load to gryphon-backed pagination once the dataset can grow beyond a demo handful.
- **Row click-through**: Navigate to the finding's object viewer or the parent system's page on row click.
- **Exception-aware status**: Visually distinguish open findings that are covered by an active `Exception` via `COVERS_FINDING`.
- **KSI linkage column**: Surface `RELATED_INDICATOR` edges to KSI indicators as a column or hover tooltip.
- **Severity / class column**: Once findings carry severity or class metadata, add a column and allow sort/filter by it.
- **System-type sub-label**: Show the parent system's `entity_type` next to its name (e.g. `i-prod-web-01 (aws_ec2_instance)`).
- **Detected-at column**: When `detected_at` lands on the Finding model (deferred per `spec-fedramp-20x-ksi-finding.md`), prefer it over `created_at`.
- **Group by system**: Tabulator-grouped view collapsing findings under their parent system.
- **Generic data-quality view**: If finding-integrity issues ever need to be visible to operators, build a dedicated data-quality dashboard rather than reintroducing orphan handling here.
- **Graph viewport-minimum**: Pin the Genericom page graph row to a viewport-anchored minimum height (or extend `spec-web-page.md` to support a per-row `min-vh` token) so the graph doesn't compress when the alerts table is short.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Implemented | Requirement is drafted and pending acceptance |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: `...``
`Status: `...``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
