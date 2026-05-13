# KSI Compliance View Specification

## Philosophy

The KSI Compliance View is a dedicated read-only reference surface for the FedRAMP 20x KSI catalog. Its audience is compliance teams, auditors, and engineering teams who need to quickly browse, search, and filter the full set of Key Security Indicators organized by theme.

The standard Table Panel exists for generic search-backed entity browsing with common metadata columns and server-side pagination. The compliance view needs fundamentally different behavior: theme-based row grouping, client-side keyword search across domain-specific fields, a class selector that both filters indicators and swaps displayed statement text, and columns tailored to the KSI data model. Forcing this into the standard table panel would override nearly every default and fight the spec on columns, grouping, and pagination model.

Instead, the compliance view registers as its own panel type within the KSI plugin. This follows the panel architecture's design intent — plugins provide specialized panel types for domain-specific views, while `tap_web` provides generic reusable standards. The panel type lives in the plugin alongside the models it renders, keeping domain knowledge co-located.

The first version is informational only: no editing, no scoring, no evidence linking. It should feel like a well-organized, searchable reference document — the kind of page you'd bookmark and come back to when answering "which KSIs apply at Class C?" or "what does KSI-MLA-LOG require?"

## Goals

|    |                    |                                                                                       |
| :---: | ---             | ---                                                                                   |
| 1. | Grouped            | Indicators are organized by theme with collapsible theme headers                      |
| 2. | Searchable         | Instant client-side keyword search across all indicator fields                        |
| 3. | Class-Aware        | A class selector filters indicators by applicability and swaps class-variant statements |
| 4. | Self-Contained     | All assets ship locally; no CDN or external dependencies                              |
| 5. | Informational      | Read-only reference surface; no editing, scoring, or evidence linking in v0            |
| 6. | Plugin-Owned       | Panel type lives in the KSI plugin, not in `tap_web` core                             |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-ksi-compview-panel | [Compliance View Panel Type](#compliance-view-panel-type) | Implemented | Plugin-registered panel type with dedicated template and JS |
| req-ksi-compview-data | [Data Loading](#data-loading) | Implemented | Gryphon query loads full subgraph; raw envelope passed to JS |
| req-ksi-compview-grouping | [Theme Grouping](#theme-grouping) | Implemented | Indicators grouped by theme with collapsible headers; order via `sort_order` field |
| req-ksi-compview-search | [Keyword Search](#keyword-search) | Implemented | Client-side keyword filtering across all indicator text fields |
| req-ksi-compview-class-select | [Class Selector](#class-selector) | Implemented | Dropdown filters by class and resolves class-variant statements; default class read from the FedRAMP 20x ComplianceContext via gryphon |
| req-ksi-compview-columns | [Indicator Columns](#indicator-columns) | Implemented | Domain-specific column set tailored to KSI indicator fields |
| req-ksi-compview-render | [Rendering Flow](#rendering-flow) | Implemented | Gryphon subgraph embedded via safe_json; JS builds grouped table |
| req-ksi-compview-url | [Page and URL](#page-and-url) | Implemented | Page seeded via GRIFT at `/fedramp-ksi` |

---

### Compliance View Panel Type
----
RID: `req-ksi-compview-panel`
Status: `Implemented`

The compliance view is a dedicated panel type registered by the KSI plugin, following the standard panel type contract from `spec-web-panel.md`.

#### Implementation
- The panel type lives in `plugins/fedramp_20x_ksi/panels/compliance_view/`.
- It is registered in `panel_type_registry` during the KSI plugin's `AppConfig.ready()`.
- It conforms to the standard panel type contract: `slug`, `label`, `view`, `css`, `js`.
- No editor view in v0 — the compliance view has no user-configurable options yet.
- The panel type slug is `fedramp-20x-ksi-compliance`.
- Required assets:
  - Tabulator CSS and JS from `tap_web/static/` (reuse the vendored copies already shipped for the standard table panel)
  - A dedicated `panel-ksi-compliance.js` for compliance-view-specific behavior (search, class selector, grouping)
  - A dedicated `panel-ksi-compliance.css` for compliance-view-specific styling (theme headers, class badges)
- The panel must not depend on CDN-hosted or internet-hosted assets.
- The panel must not embed inline JavaScript in rendered HTML.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-compview-panel-1 | Plugin-Owned Panel Type | Implemented | The panel type class lives in the KSI plugin package, not in `tap_web`. | |
| req-ksi-compview-panel-2 | Registered At Startup | Implemented | The panel type is registered in `panel_type_registry` during `AppConfig.ready()`. | |
| req-ksi-compview-panel-3 | Standard Contract | Implemented | The panel type conforms to the panel type contract defined in `spec-web-panel.md`. | |
| req-ksi-compview-panel-4 | No Inline JS | Implemented | All browser behavior is implemented through referenced static files. | |
| req-ksi-compview-panel-5 | Reuses Vendored Tabulator | Implemented | The panel reuses the Tabulator CSS/JS already vendored in `tap_web/static/`. | |

### Data Loading
----
RID: `req-ksi-compview-data`
Status: `Implemented`

The compliance view loads all KSI indicators and themes via a gryphon edge-type scan query and passes the raw subgraph envelope to the browser for client-side processing.

#### Implementation
- The panel is linked to a Search entity via `USES_SEARCH` edge. The Search uses `search_type: "gryphon"` with query `MATCH (t:ksi_theme)-[e:CONTAINS_INDICATOR]->(i:ksi_indicator)`.
- The panel type's `get_view_context()` executes the linked Search through `execute_search()` with `layer="extended"`, returning the standard subgraph envelope `{nodes, edges, info, warnings}`.
- The raw subgraph is serialized via `safe_json()` and embedded in the template — no Python-side post-processing. The JS builds the grouped table from the subgraph.
- No pagination is needed — the v0 catalog is ~46 indicators across 10 themes. The entire dataset fits in a single page load.
- Using gryphon ensures the query benefits from future service-layer features (dimension filtering, time-travel) transparently.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-compview-data-1 | Gryphon Query | Implemented | Data is loaded via a gryphon edge-type scan through the search service layer. | `MATCH (t:ksi_theme)-[e:CONTAINS_INDICATOR]->(i:ksi_indicator)` |
| req-ksi-compview-data-2 | Raw Subgraph To JS | Implemented | The raw subgraph envelope is passed to the browser; JS handles joining and grouping. | |
| req-ksi-compview-data-3 | safe_json Embedding | Implemented | The subgraph is serialized via `safe_json()` per `req-web-panel-json-embed.sec`. | |
| req-ksi-compview-data-4 | Extended Layer | Implemented | Search executes with `layer="extended"` providing `url_id` and `icon_url` per node. | |

### Theme Grouping
----
RID: `req-ksi-compview-grouping`
Status: `Implemented`

Indicators are visually organized by their parent KSI theme, with each theme section showing the theme name and icon as a group header.

#### Implementation
- Tabulator's `groupBy` feature groups rows by `theme_code`.
- Group order is controlled by the `sort_order` field on `KsiTheme` (PositiveIntegerField, 10-step increments). The JS builds a sorted theme code list from the pre-sorted row data and passes it via Tabulator's `groupValues` to enforce ordering.
- Group headers display the theme's per-theme SVG icon (resolved from `icon_url` in the extended subgraph layer, falling back to static assets by theme short_name) and the theme name with indicator count.
- Groups are collapsible — users can expand/collapse individual theme sections.
- Groups default to expanded on initial page load.
- Within each group, indicators are sorted by `code`.
- Theme ordering follows a security-lifecycle flow: Policy and Inventory (10) → Identity and Access Management (20) → Cloud Native Architecture (30) → Service Configuration (40) → Monitoring, Logging, and Auditing (50) → Change Management (60) → Supply Chain Risk (70) → Incident Response (80) → Recovery Planning (90) → Cybersecurity Education (100).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-compview-grouping-1 | Grouped By Theme | Implemented | Rows are grouped by parent theme using Tabulator's `groupBy`. | |
| req-ksi-compview-grouping-2 | Theme Icon In Header | Implemented | Group headers display the per-theme SVG icon. | Via `icon_url` from extended layer |
| req-ksi-compview-grouping-3 | Collapsible Groups | Implemented | Theme groups are collapsible and default to expanded. | |
| req-ksi-compview-grouping-4 | Sorted By Code | Implemented | Indicators within each group are sorted by `code`. | |
| req-ksi-compview-grouping-5 | Sort Order Field | Implemented | Theme ordering uses `KsiTheme.sort_order` (PositiveIntegerField) set via GRIFT wave. | |

### Keyword Search
----
RID: `req-ksi-compview-search`
Status: `Implemented`

A search bar above the table provides instant client-side keyword filtering across all indicator text fields. The search shrinks the table to only indicators containing the keyword(s).

#### Implementation
- A text input above the table acts as the search control.
- Typing triggers client-side filtering with a short debounce (e.g. 200-300ms).
- The filter matches against: `code`, `name`, `description`, `class_variants` statement text (all classes), `controls` entries, and `terms` entries.
- Search is case-insensitive.
- Multiple space-separated keywords are treated as AND — all keywords must match within the same indicator's searchable fields.
- When a filter is active, theme groups with no matching indicators are hidden.
- Clearing the search restores the full table.
- The search input should display a result count (e.g. "Showing 12 of 46 indicators").

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-compview-search-1 | Client-Side Filtering | Implemented | Search filtering happens entirely in the browser with no server round-trip. | |
| req-ksi-compview-search-2 | Multi-Field Match | Implemented | Search matches against code, name, description, class_variants text, controls, and terms. | |
| req-ksi-compview-search-3 | Case-Insensitive | Implemented | Search matching is case-insensitive. | |
| req-ksi-compview-search-4 | AND Semantics | Implemented | Multiple keywords are AND-joined: all must match within the same indicator. | |
| req-ksi-compview-search-5 | Empty Groups Hidden | Implemented | Theme groups with no matching indicators are hidden during filtered view. | |
| req-ksi-compview-search-6 | Result Count | Implemented | The UI displays how many indicators match the current filter. | |

### Class Selector
----
RID: `req-ksi-compview-class-select`
Status: `Implemented`

A dropdown selector allows choosing a FedRAMP Certification Class (a, b, c, d) or "All Classes". The selection filters the indicator list to those applicable at the chosen class and resolves the correct statement text for indicators with class-specific variants. The default selection is read from the Grid's FedRAMP 20x ComplianceContext via gryphon at panel render time; user changes during a session are not persisted client-side.

#### Implementation
- A select/dropdown control above the table (alongside the keyword search) offers: "All Classes", "Class A — Pilot", "Class B — Low", "Class C — Moderate", "Class D — High".
- The default selected class is read server-side from the Grid's FedRAMP 20x ComplianceContext (the entity with `regime = "fedramp_20x"`) via a small gryphon query at panel render. The query is scoped to the FedRAMP 20x ComplianceContext only — see `req-fedramp-20x-ksi-compliance-context-fedramp-class`.
- Default-resolution rules:
  - ComplianceContext exists with non-empty `fedramp_class` ∈ {a, b, c, d} → use that class as the default.
  - ComplianceContext exists with `fedramp_class = ""` (empty) → "FedRAMP 20x not in scope for this Grid" → default to `"all"`.
  - No ComplianceContext exists for `regime = "fedramp_20x"` → deployment misconfiguration; default to `"all"` (defensive — shows everything rather than silently filtering to an unjustified class) and log a warning.
- The resolved default is passed to the browser via the panel's existing JSON payload — no separate request, no client-side fallback chain, no localStorage. The JS reads the default once at startup and applies it to the dropdown.
- Per-session user changes to the dropdown are NOT persisted: refreshing the page returns to the ComplianceContext-derived default. This is intentional — link-sharing requires the dominant class to be a property of the Grid, not a property of the viewer's browser. If a user wants to permanently change the dominant class, they update the ComplianceContext via the standard editor flow (future work) or the service layer.
- When a specific class is selected:
  - Indicators whose `classes` list does not include the selected class are hidden.
  - For indicators with `class_variants`, the statement column displays the statement for the selected class (from `class_variants[<class>].statement`) instead of the generic description.
  - For indicators with a direct `description` (no class_variants), the statement column continues showing the description unchanged.
- When "All Classes" is selected:
  - All indicators are shown regardless of their `classes` list.
  - For indicators with `class_variants`, the statement column displays a combined or primary statement (e.g. the highest applicable class statement, or an indicator that variants exist).
- The class selector works in combination with keyword search — both filters apply simultaneously.
- Class labels in the dropdown should include the human-readable description: "Class A — Pilot", "Class B — Low", "Class C — Moderate", "Class D — High".

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-compview-class-select-1 | Class Dropdown Present | Implemented | A dropdown allows selecting a specific certification class or "All Classes". | |
| req-ksi-compview-class-select-2 | Filters By Applicability | Implemented | Selecting a class hides indicators whose `classes` list does not include the selected class. | |
| req-ksi-compview-class-select-3 | Resolves Class Variants | Implemented | When a class is selected, indicators with `class_variants` display the statement for that specific class. | |
| req-ksi-compview-class-select-4 | Combines With Search | Implemented | Class filter and keyword search apply simultaneously. | |
| req-ksi-compview-class-select-5 | Default From ComplianceContext | Implemented | The default class is read at render time from the FedRAMP 20x ComplianceContext's `fedramp_class` field. Empty / missing context falls back to "All Classes". | Replaces the prior localStorage stickiness; cross-ref `req-fedramp-20x-ksi-compliance-context-fedramp-class` |
| req-ksi-compview-class-select-6 | No Client-Side Persistence | Implemented | User changes to the dropdown are not persisted to localStorage or cookies; refreshing returns to the ComplianceContext-derived default. | Intentional — preserves link-sharing semantics |

### Indicator Columns
----
RID: `req-ksi-compview-columns`
Status: `Implemented`

The compliance view displays a domain-specific column set tailored to the KSI indicator model, not the generic common-metadata columns used by the standard table panel.

#### Implementation

| Column | Source | Notes |
| --- | --- | --- |
| Code | `indicator.code` | Short identifier like KSI-IAM-MFA. Links to the TAP object viewer for the indicator. |
| Name | `indicator.name` | Short title of the indicator |
| Statement | `indicator.description` or resolved `class_variants` | Class-aware: shows direct description or class-specific variant based on class selector. See `req-ksi-compview-class-select`. |
| Classes | `indicator.classes` | Rendered as badge-style labels (A, B, C, D). Active class highlighted when class selector is in use. |
| Controls | `indicator.controls` | Comma-separated NIST 800-53 control IDs |
| Status | `indicator.status` | Published / Draft / Deprecated with visual styling |

- The Code column links to the TAP object viewer at `/object/ksi_indicator/{url_id}/` on click, consistent with `req-web-stdpanel-table-row-nav`.
- The Statement column is the widest — it contains the requirement text and should wrap cleanly.
- The Classes column uses compact badge styling. When a class is selected via the class selector, the active class badge is visually emphasized.
- Column widths should be tuned for readability: Code and Status narrow, Statement wide.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-compview-columns-1 | Domain-Specific Columns | Implemented | The compliance view uses KSI-specific columns, not generic entity metadata. | |
| req-ksi-compview-columns-2 | Class-Aware Statement | Implemented | The Statement column resolves class-variant text when a class is selected. | Cross-ref `req-ksi-compview-class-select-3` |
| req-ksi-compview-columns-3 | Code Links To Viewer | Implemented | The Code column links to the TAP object viewer for the indicator entity. | |
| req-ksi-compview-columns-4 | Class Badges | Implemented | The Classes column renders as compact badges with active-class emphasis. | |

### Rendering Flow
----
RID: `req-ksi-compview-render`
Status: `Implemented`

The compliance view follows the same rendering pattern as the standard table panel: server-side data embedding with client-side Tabulator mount from shipped static JS.

#### Implementation
- The panel type's `get_view_context()` executes the data query and serializes the result.
- The template embeds the serialized JSON in a `<script type="application/json">` tag.
- A dedicated static JS file (`panel-ksi-compliance.js`) reads the payload, initializes Tabulator with grouping, and wires up the search input and class selector.
- Tabulator configuration includes: `groupBy`, custom `groupHeader` formatter (theme icon + name + indicator count), column definitions, and initial sort.
- The search input and class selector are standard HTML form controls rendered in the template, not generated by Tabulator.
- The JS file attaches event listeners to the search input (debounced `input` event) and class selector (`change` event), calling Tabulator's `setFilter` / `clearFilter` methods.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-compview-render-1 | Embedded JSON Payload | Implemented | Data is embedded as escaped JSON, not inline JS. | Same pattern as standard table panel |
| req-ksi-compview-render-2 | Static JS Mount | Implemented | Tabulator initialization and behavior are in a shipped static JS file. | |
| req-ksi-compview-render-3 | HTML Form Controls | Implemented | Search input and class selector are standard HTML elements, not Tabulator-generated. | |
| req-ksi-compview-render-4 | No Server Round-Trips For Filter | Implemented | Search and class filtering happen client-side with no AJAX calls. | |

### Page and URL
----
RID: `req-ksi-compview-url`
Status: `Implemented`

The compliance view is accessible at a stable, human-readable URL so users can bookmark and share it.

#### Implementation
- The KSI plugin seeds a Page entity containing the compliance view panel during GRIFT import or plugin setup.
- The page is accessible at `/fedramp-ksi` via TAP's catch-all page routing.
- The page slug is `/fedramp-ksi`.
- The page title is "FedRAMP 20x Key Security Indicators".
- The page contains a single panel slot occupied by the compliance view panel instance.

#### Development
The page, panel, search, and wiring edges are seeded via a GRIFT file at `grift/ksi-compliance-page.grift.json` in the batched format, following the same pattern as the plugin's dimension and catalog data seeds.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-compview-url-1 | Stable URL | Implemented | The compliance view page is accessible at a bookmarkable URL. | |
| req-ksi-compview-url-2 | Descriptive Slug | Implemented | The page slug is human-readable and descriptive. | |
| req-ksi-compview-url-3 | Seeded By Plugin | Implemented | The page and panel instances are seeded by the KSI plugin. | Mechanism TBD |

## Future Work

- **Inline evidence status**: Show per-indicator evidence coverage once an evidence model exists — green/yellow/red indicators for "has evidence", "partial", "missing".
- **Export**: CSV or PDF export of the filtered view for audit documentation.
- **NIST control crosswalk column**: Once `req-fedramp-20x-ksi-nist-crosswalk` is implemented, controls column could link to actual NIST control nodes.
- **Comparison mode**: Side-by-side class comparison showing how statements differ across classes for the same indicator.
- **Print-friendly layout**: Optimized print stylesheet for compliance documentation.
- **URL-backed filter state**: Encode search query and class selection in URL parameters so filtered views can be shared via link.
- **Editor support**: Allow configuring which columns are visible, default class selection, or default search terms via the panel editor.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Implemented |  |
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
