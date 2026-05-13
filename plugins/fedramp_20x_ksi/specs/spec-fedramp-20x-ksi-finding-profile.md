# KSI Finding Profile Specification

## Philosophy

The Finding Profile is a dedicated detail page for a single Finding — the full story of *why this finding exists*, presented in one place. It surfaces the finding's identity (name, status, description), the system(s) it applies to, the KSI indicator(s) it relates to, and the supporting evidence collected against it.

The page is the natural drill-down from the genericom open-alerts table: clicking a finding's title navigates here. It is also an entry point from any future surface that lists or counts findings (alert badges, search results, dashboards).

In v0 the page is read-only. Lifecycle controls (resolving, attaching evidence, editing classification) are out of scope; that workflow will land alongside the Resolution model and the broader compliance-workflow iteration. Exception coverage is also out of scope for v0 — the seeded `COVERS_FINDING` edge exists in the graph but is not yet rendered on this page; it will be added once exception display is standardized across the plugin.

The page mirrors the visual structure of the KSI Indicator Profile (`spec-fedramp-20x-ksi-indicator-profile.md`) intentionally: hero header, sectioned body, breadcrumb, the same typography, chip styles, and table conventions. The two profiles together establish the consistent look-and-feel that subsequent profile pages (Asset, Evidence, Exception, Resolution) will inherit.

The page receives the finding's `entity_id` as a URL query parameter and uses a single gryphon hub-and-spoke query to load the finding plus its full neighborhood — every node connected by a `HAS_FINDING`, `RELATED_INDICATOR`, or `HAS_EVIDENCE` edge — in one pass.

### Why A Plugin-Owned Panel (And Not The Standard Table Panel) For v0

The standard `tap_web` Table Panel (`spec-web-panels-standard-table.md`) is the long-term home for tabular data in TAP, and both tables on this profile *should* eventually fold into it. Three current limits prevent that today:

1. **`column_mode` is `common_metadata`-only.** The KSI table (Code · Name · Relationship · Description) and Evidence table (Verdict · Name · Kind · Note + expand) need plugin-defined column sets that the standard panel cannot yet express.
2. **No row-detail / click-to-expand.** The Evidence table's expand-on-click reveal of the full description / scanner output has no analog in the standard panel.
3. **No inline-payload mode.** The standard panel always re-executes a linked Search. Both finding-profile tables are filtered slices of the *same* subgraph the parent panel already loaded for its hero/identity rendering; routing them through `USES_SEARCH` would mean three searches per page render (one for the profile, one per table) parameterized on `entity_id`, and we'd still hit the column-customization wall.

**Decision.** v0 ships as a single plugin-owned panel that loads the neighborhood once and embeds two Tabulator instances driven by that in-page JSON payload. The genericom open-alerts panel (`spec-genericom-open-alerts-table.md`) sets the precedent: same shape, same justification, same Tabulator footprint.

**Refactor signal.** Fold both tables into the standard Table Panel when *all three* of the following land:

- `column_overrides` (or equivalent custom-column mechanism) on the standard panel.
- A row-detail / expand-on-click feature on the standard panel.
- An inline-payload binding mode that lets a panel render off pre-loaded data instead of always re-executing a Search.

Until then, "two Tabulator instances inside a plugin-owned panel" is the right level of investment.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Polished           | Visually refined profile layout consistent with the indicator profile |
| 2. | One-Page Story     | All directly-connected context for the finding — system(s), KSIs, evidence — visible without navigating |
| 3. | Multi-System Aware | The system field can render a comma-separated list when a finding spans multiple assets |
| 4. | KSI-In-Context     | Related KSIs displayed inline with their short descriptions, not just code references |
| 5. | Evidence Drill-In  | Evidence is row-per-evidence with click-to-expand for the full description / scanner output |
| 6. | Plugin-Owned       | Panel type and page live in the KSI plugin |
| 7. | Single-Query Load  | All neighborhood data loaded in one gryphon hub-and-spoke pass |
| 8. | Tabulator-Backed   | KSI and Evidence tables use Tabulator for consistency with other tap_web tables, with a clear refactor path back into the standard Table Panel |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-ksi-finding-profile-panel | [Finding Profile Panel Type](#finding-profile-panel-type) | Implemented | Plugin-registered panel type for single-finding display |
| req-ksi-finding-profile-data | [Data Loading](#data-loading) | Implemented | Gryphon hub-and-spoke query loads finding + system/KSI/evidence neighborhood |
| req-ksi-finding-profile-header | [Hero Header](#hero-header) | Implemented | Name + breadcrumb. Verdict pill removed pending verdict-rollup logic — see `spec-fedramp-20x-ksi-finding.md` `req-fedramp-20x-ksi-finding-verdict-rollup` (Backlog). |
| req-ksi-finding-profile-meta | [Identity Section](#identity-section) | Implemented | System(s), description, status |
| req-ksi-finding-profile-ksi-table | [Related KSIs Table](#related-ksis-table) | Implemented | Table of related indicators with short descriptions |
| req-ksi-finding-profile-evidence-table | [Evidence Table](#evidence-table) | Implemented | Row-per-evidence table with click-to-expand details |
| req-ksi-finding-profile-page | [Page and Navigation](#page-and-navigation) | Implemented | Page seeded via GRIFT; reachable from open-alerts table |
| req-ksi-finding-profile-open-alerts-link | [Open Alerts Title Linkage](#open-alerts-title-linkage) | Implemented | Genericom open-alerts table title cell links to the finding profile |

---

### Finding Profile Panel Type
----
RID: `req-ksi-finding-profile-panel`
Status: `Implemented`

The finding profile is a dedicated panel type registered by the KSI plugin.

#### Implementation
- Panel type lives in `plugins/fedramp_20x_ksi/panels/finding_profile/__init__.py`.
- Registered in `panel_type_registry` during `Fedramp20xKsiConfig.ready()`.
- Panel type slug: `fedramp-20x-ksi-finding-profile`.
- Panel reads `entity_id` from `request.GET` query parameters.
- Required assets:
  - `static/fedramp_20x_ksi/css/panel-ksi-finding-profile.css` — layout styling that re-uses the visual vocabulary of the indicator profile (hero gradient, section titles, chips, breadcrumb).
  - `static/fedramp_20x_ksi/js/panel-ksi-finding-profile.js` — initializes the KSI and Evidence Tabulator instances from embedded JSON payloads.
  - Tabulator CSS + JS are pulled from the existing `tap_web/css/lib/tabulator.min.css` and `tap_web/js/lib/tabulator.min.js` assets — no new vendor copy.
- No editor view in v0.
- See the Philosophy section "Why A Plugin-Owned Panel (And Not The Standard Table Panel) For v0" for the standard-table-panel tradeoff and refactor signals.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-finding-profile-panel-1 | Plugin-Owned Panel Type | Implemented | The panel type class lives in the KSI plugin package. | |
| req-ksi-finding-profile-panel-2 | Registered At Startup | Implemented | The panel type is registered in `panel_type_registry` during `AppConfig.ready()`. | |
| req-ksi-finding-profile-panel-3 | Reads Entity ID From Query Params | Implemented | The panel reads `entity_id` from `request.GET` to identify the finding. | |

---

### Data Loading
----
RID: `req-ksi-finding-profile-data`
Status: `Implemented`

The profile panel loads the finding and its full one-hop neighborhood via a single gryphon hub-and-spoke query.

#### Implementation
- `get_view_context()` reads `entity_id` from `request.GET`.
- Executes the standard hub-and-spoke gryphon: `MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id RETURN hub, e, neighbor`.
- The neighborhood will include:
  - **Inbound `HAS_FINDING`** edges from one or more system/asset nodes (any entity type).
  - **Outbound `RELATED_INDICATOR`** edges to KSI indicator nodes, with a `relationship_type` edge property.
  - **Outbound `HAS_EVIDENCE`** edges to evidence nodes, with `support_kind` and optional `note` edge properties.
- The panel walks the returned subgraph in Python and builds a structured view-model:
  - `finding` — flat dict of finding fields plus computed presentation fields: `created_full` / `updated_full` (full UTC timestamps for hover tooltips), and `created_relative` / `updated_relative` (short human-friendly labels for inline display).
  - `systems` — ordered list of `{entity_id, entity_type, name}` for every `HAS_FINDING` source. Multi-system findings render as a comma-separated list in the identity section.
  - `ksis` — ordered list of `{entity_id, code, name, description, relationship_type}` for every `RELATED_INDICATOR` target.
  - `evidence` — ordered list of `{entity_id, name, kind, description, support_kind, note, updated_relative, timestamp_tooltip}` for every `HAS_EVIDENCE` target. `timestamp_tooltip` is a pre-formatted two-line string (`Created: …` / `Updated: …`) bound to the row's Updated cell as a hover tooltip.
- **No aggregated verdict in v0.** The view-model does not emit a finding-level `verdict` field. The first iteration computed one from `HAS_EVIDENCE.support_kind` values, but the rule was unspec'd; both this requirement and the hero pill have been deferred until `spec-fedramp-20x-ksi-finding.md` `req-fedramp-20x-ksi-finding-verdict-rollup` (Backlog) lands. Per-edge verdict signal is still surfaced unmodified on `evidence[i].support_kind` and `ksis[i].relationship_type` for tables that render their own per-row pills.
- **Relative-time helper.** A small Python helper renders `datetime` deltas as `just now` / `Nm ago` / `Nh ago` / `yesterday` / `Nd ago` / `MMM D` (same year) / `MMM D, YYYY` (prior years). The helper output goes to `updated_relative` and `created_relative`; the full UTC timestamps go to the `*_full` fields used as hover tooltips.
- Default subgraph layer is `extended` so any `icon_url` or computed presentation fields surface naturally.
- If the finding is missing or the entity_id is invalid, the panel renders an error state rather than crashing.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-finding-profile-data-1 | Single Gryphon Query | Implemented | Finding, systems, KSIs, and evidence are loaded in one hub-and-spoke gryphon query. | |
| req-ksi-finding-profile-data-2 | Multi-System Support | Implemented | The view-model represents `HAS_FINDING` parents as a list, not a single value. | |
| req-ksi-finding-profile-data-3 | Edge Properties Captured | Implemented | `RELATED_INDICATOR.relationship_type`, `HAS_EVIDENCE.support_kind`, and `HAS_EVIDENCE.note` are surfaced into the view-model. | |
| req-ksi-finding-profile-data-4 | Graceful Missing Entity | Implemented | Missing or invalid `entity_id` renders an error state rather than crashing. | |
| req-ksi-finding-profile-data-5 | No Aggregated Verdict In v0 | Implemented | The view-model emits no finding-level `verdict` field. Per-edge verdict signal (`evidence[i].support_kind`, `ksis[i].relationship_type`) is surfaced unmodified for per-row consumers. | Pending `req-fedramp-20x-ksi-finding-verdict-rollup` |
| req-ksi-finding-profile-data-6 | Relative Timestamps | Implemented | The view-model emits both relative (`*_relative`) and full UTC (`*_full`) timestamp strings for the finding and evidence rows. | |

---

### Hero Header
----
RID: `req-ksi-finding-profile-header`
Status: `Implemented`

The top of the profile shows the finding's identity at a glance.

#### Status Details
The verdict pill that originally lived in the hero has been removed pending a documented verdict-rollup rule. See `spec-fedramp-20x-ksi-finding.md` `req-fedramp-20x-ksi-finding-verdict-rollup` (Backlog) for the open design question and the conditions for re-introducing the pill. The hero today carries the breadcrumb and the finding name only.

#### Implementation
- **Breadcrumb** — `FedRAMP 20x KSI / Findings / <finding name>` styled identically to the indicator profile's breadcrumb. The "Findings" segment links to the findings index page.
- **Hero block** with the same gradient background as the indicator profile.
- **Name** — primary `<h1>` (the finding's `name`).
- **No verdict pill in v0** — the hero's right side is empty until the verdict-rollup rule lands. The lifecycle `status` field is still authoritative on the model and queryable via the graph; it just does not surface in the hero, because surfacing it (alone) mixes lifecycle vocabulary (`open`/`resolved`) with verdict vocabulary (`passing`/`violation`/`informational`) in a single pill, which the first iteration of this panel got wrong.
- The hero contains no class badges (findings don't carry classes).

#### Development
- Resist re-adding a status-only or inferred-verdict pill before the rollup rule is spec'd. The first iteration shipped a "prefer aggregated verdict over lifecycle status" rule baked into render code; that rule answered a real question but invented the policy rather than citing one. The lesson: this is platform policy, not a panel-local choice — it gets spec'd in the finding spec, then re-implemented here, then the pill comes back.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-finding-profile-header-1 | Name Prominent | Implemented | The finding's name is the primary visual element of the hero. | |
| req-ksi-finding-profile-header-2 | No Verdict Pill | Implemented | The hero does not render a status or verdict pill in v0. | Pending `req-fedramp-20x-ksi-finding-verdict-rollup` |
| req-ksi-finding-profile-header-3 | Breadcrumb | Implemented | A breadcrumb leads back to `/fedramp-ksi`; "Findings" links to the findings index. | |

---

### Identity Section
----
RID: `req-ksi-finding-profile-meta`
Status: `Implemented`

A definition-list-style block of the finding's core facts (System / Systems and Description), with a subtle timestamp meta line below.

#### Implementation
- Rendered immediately below the hero, before the KSI table.
- Two stacked rows of label + value:
  - **System / Systems** — label switches between singular `System` (one parent) and plural `Systems` (multiple parents). Comma-separated list of system names; each name links to its entity (`/grid/<entity_id>`). Order: stable by `entity_id` so refreshes don't reshuffle.
  - **Description** — the finding's `description` rendered as plain text (no markdown). Long descriptions wrap; no truncation in this section.
- Empty descriptions render the section's row as `—` rather than collapsing — the slot is meaningful even when blank.
- **Timestamp meta line** — a small grey footer line below the dl, format `Opened <relative> · Updated <relative>`. Each span carries the full UTC timestamp in its `title` attribute (visible on hover); a dotted underline hints that a tooltip is available. This replaced an earlier draft that used two heavy dl rows for Created / Last Updated — the timestamps stay informative but visually subordinate.
- Status / verdict is intentionally absent from this section in v0 — the hero pill that previously carried it has been removed pending `req-fedramp-20x-ksi-finding-verdict-rollup`. Per-edge verdict signal still appears on the related-KSI and evidence tables below.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-finding-profile-meta-1 | Multi-System Comma List | Implemented | When a finding has multiple `HAS_FINDING` parents, the row shows a comma-separated list of names. | |
| req-ksi-finding-profile-meta-2 | System Name Links | Implemented | Each system name links to the system's entity view. | |
| req-ksi-finding-profile-meta-3 | Description Rendered | Implemented | The finding's `description` is rendered as plain text in the identity section. | |
| req-ksi-finding-profile-meta-4 | Singular/Plural System Label | Implemented | The label reads `System` when there is one parent and `Systems` when there are multiple. | |
| req-ksi-finding-profile-meta-5 | Timestamp Meta Line | Implemented | A subtle grey meta line below the dl displays `Opened <relative> · Updated <relative>` with full UTC timestamps in `title`-attribute tooltips. | |

---

### Related KSIs Table
----
RID: `req-ksi-finding-profile-ksi-table`
Status: `Implemented`

A compact table of every KSI indicator related to this finding, with their short descriptions inline so reviewers don't have to context-switch to look them up.

#### Implementation
- Section header: "Related Indicators".
- Rendered as a Tabulator table, initialized from a JSON payload embedded in the panel's HTML (no separate Search call). Same library and embedded-payload pattern as the genericom open-alerts panel.
- Layout: `fitColumns`. No pagination (KSI counts per finding are small — typical 1, structurally bounded by how many KSIs a finding can plausibly relate to).
- Columns (left-to-right):
  - **Relationship** — `relationship_type` from the `RELATED_INDICATOR` edge property, rendered via a Tabulator formatter as a colored pill (`violation`, `passing`, `informational`, `other`). **Placed first** so it visually aligns with the Verdict column at the top-left of the Evidence table, giving the page a single column of pills running down the left edge. Color vocabulary aligned with the genericom open-alerts table's relationship pills.
  - **Code** — KSI code in monospace, formatted as a link to the indicator profile (`/fedramp-ksi/indicator?entity_id=<uuid>`). Custom Tabulator formatter producing an `<a>` element.
  - **Name** — indicator name, plain text.
  - **Description** — the indicator's `description` field, full-text wrap (`formatter: "textarea"`), no truncation in v0.
- The table renders even when there is exactly one related indicator (do not collapse the table to a single card).
- If the finding has zero related indicators (data anomaly), Tabulator's `placeholder` shows: "No related indicators."

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-finding-profile-ksi-table-1 | Always A Table | Implemented | Related KSIs render as a Tabulator table even when there is only one row. | |
| req-ksi-finding-profile-ksi-table-2 | Code Links To Profile | Implemented | The KSI code cell is a link to that indicator's profile page. | |
| req-ksi-finding-profile-ksi-table-3 | Relationship Pill | Implemented | The relationship_type renders as a colored pill consistent with the genericom open-alerts vocabulary. | |
| req-ksi-finding-profile-ksi-table-4 | Description Inline | Implemented | The indicator's short description is shown inline in the same row. | |
| req-ksi-finding-profile-ksi-table-5 | Empty State | Implemented | If there are zero related indicators, the Tabulator `placeholder` displays an empty-state message. | Should not occur in seeded data |
| req-ksi-finding-profile-ksi-table-6 | Tabulator-Backed | Implemented | The table is initialized via Tabulator using the existing `tap_web/js/lib/tabulator.min.js` asset; no new vendor copy. | |
| req-ksi-finding-profile-ksi-table-7 | Relationship-First Column Order | Implemented | The Relationship pill is the leftmost column so it aligns with the Verdict column at the top-left of the Evidence table. | |

---

### Evidence Table
----
RID: `req-ksi-finding-profile-evidence-table`
Status: `Implemented`

A row-per-evidence table summarizing every `HAS_EVIDENCE` artifact attached to the finding, with a click-to-expand pattern that reveals the full evidence description/output.

#### Implementation
- Section header: "Evidence".
- Rendered as a Tabulator table, initialized from a JSON payload embedded in the panel's HTML (same library and embedded-payload pattern as the KSI table and the genericom open-alerts panel).
- Layout: `fitColumns`. No pagination; per-finding evidence counts are small.
- Columns (collapsed-row state, left-to-right):
  - **Verdict** — `support_kind` from the `HAS_EVIDENCE` edge (`passing` / `violation` / `informational`), rendered via a Tabulator formatter as a colored pill. **Placed first** so it visually aligns with the Relationship column at the top-left of the KSI table — both pill columns run down the same left edge of the page.
  - **Name** — evidence name, plain text.
  - **Kind** — evidence `kind` (`screenshot` / `scanner_output` / `policy_doc` / `attestation` / `log_excerpt` / `other`), rendered via a Tabulator formatter as a small monospace tag.
  - **Updated** — relative-time label (e.g. `1h ago` / `yesterday` / `Mar 12`) right-aligned in a narrow column, rendered by a Tabulator formatter that binds the row's `timestamp_tooltip` two-line string (Created / Updated full UTC timestamps) to the cell's `title` attribute. Replaces an earlier draft that used two full-ISO timestamp columns; this single relative column is narrower, more readable, and keeps the precise timestamps one hover away.
  - **Note** — the optional `note` from the `HAS_EVIDENCE` edge, single-line truncated by Tabulator with the full text in a `title` attribute for hover.
- Row expansion: click-to-expand is implemented via a Tabulator `rowClick` event handler subscribed via `table.on("rowClick", …)` and an **external detail container** (`#finding-profile-evidence-details`) rendered as a sibling of the Tabulator mount in the panel template. On row click the handler appends a `.finding-evidence-detail` `<div>` to the external container, keyed by `data-finding-detail-for` = evidence `entity_id`; clicking the same row again removes that block. *Why external?* Tabulator manages the DOM under its `tabulator-table` element and wipes injected siblings on its internal redraws (sort, scroll, layout recalc). An external container is safe from those redraws and the only DOM touch on the row itself is a `--expanded` class for chevron rotation. Each detail block carries its own header (the evidence name) so it remains identifiable when multiple are open at once.
- The detail `<div>` contains the evidence's full `description` inside a `<pre>` block with word-wrap so multi-line scanner output (e.g. raw `dig` output with leading whitespace) preserves its layout.
- A chevron control rendered in a synthetic last column rotates 90° on expand via the row's `--expanded` class. Clicking anywhere on the row — not just the chevron — toggles expansion.
- Expansion is per-row independent; multiple rows may be expanded simultaneously and stack vertically in the external container in click order.
- No client-side fetching — descriptions are rendered into the embedded JSON payload up front and toggled via DOM class. Sizes are bounded; the seeded DNSSEC `dig` output is the expected upper bound and is small enough.
- If the finding has zero evidence, Tabulator's `placeholder` shows: "No evidence attached."

#### Development
- `rowClick` is subscribed via `table.on("rowClick", …)` rather than the constructor `rowClick` option — the constructor-callback path fires inconsistently when a `rowFormatter` is also defined; the event-subscription path is reliable.
- Detail blocks live in an **external sibling container** (`#finding-profile-evidence-details`) rather than being inserted inside Tabulator's `tabulator-table` element. Tabulator wipes non-row siblings under its managed DOM on internal redraws (sort, layout recalc); an external container sidesteps that without giving up the click-to-expand UX.
- Click handler must distinguish row-clicks from cell-clicks that should fall through (e.g. clicking the Name link in the future) — for v0 there are no in-row interactive elements, so plain row-click is fine; revisit when columns gain links.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-finding-profile-evidence-table-1 | Row Per Evidence | Implemented | Each evidence artifact renders as one Tabulator row. | |
| req-ksi-finding-profile-evidence-table-2 | Verdict Pill | Implemented | The HAS_EVIDENCE.support_kind renders as a colored pill in its own column via a Tabulator formatter. | |
| req-ksi-finding-profile-evidence-table-3 | Click-To-Expand | Implemented | Clicking the row toggles a detail strip showing the evidence description. | Detail blocks live in an external sibling container below the table; row gains `--expanded` class for chevron rotation |
| req-ksi-finding-profile-evidence-table-4 | Independent Expand | Implemented | Multiple rows may be expanded at the same time; expanded blocks stack in the external container in click order. | |
| req-ksi-finding-profile-evidence-table-5 | Preformatted Description | Implemented | Evidence description renders inside a `<pre>` block with word-wrap so scanner output preserves layout. | |
| req-ksi-finding-profile-evidence-table-6 | Empty State | Implemented | If the finding has no evidence, the Tabulator `placeholder` displays an empty-state message. | |
| req-ksi-finding-profile-evidence-table-7 | Tabulator-Backed | Implemented | The table is initialized via Tabulator using the existing `tap_web/js/lib/tabulator.min.js` asset; no new vendor copy. | |
| req-ksi-finding-profile-evidence-table-8 | Verdict-First Column Order | Implemented | The Verdict pill is the leftmost column so it aligns with the Relationship column at the top-left of the Related Indicators table. | |
| req-ksi-finding-profile-evidence-table-9 | Relative Updated Column | Implemented | Evidence age is shown as a single right-aligned `Updated` column with a relative-time label and a `title`-attribute tooltip carrying the full Created and Updated UTC timestamps. | |

---

### Page and Navigation
----
RID: `req-ksi-finding-profile-page`
Status: `Implemented`

The profile page is seeded via GRIFT and reachable by URL.

#### Implementation
- Page seeded via a new GRIFT bundle: `grift/finding-profile-page.grift.json`.
- The bundle creates one `page` entity and one `panel` entity, connected by a `USES_PANEL` edge with a `hotlink` property pointing the page's `profile` slot at the finding-profile panel.
- Page slug: `/fedramp-ksi/finding`.
- Page is accessed at its slug URL with the finding's entity_id as a query parameter: `/fedramp-ksi/finding?entity_id=<uuid>`.
- Page layout: single column, single row containing the profile panel (mirrors the indicator profile page's layout).
- The bundle is registered in `tap-plugin.toml` under `[grift]` as `finding_profile_page`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-finding-profile-page-1 | GRIFT Seeded | Implemented | Page and panel are seeded via plugin GRIFT. | |
| req-ksi-finding-profile-page-2 | Query Param Navigation | Implemented | The page reads the finding identity from a URL query parameter. | |
| req-ksi-finding-profile-page-3 | Single-Column Layout | Implemented | The page has a single column with the profile panel as its sole occupant. | |

---

### Open Alerts Title Linkage
----
RID: `req-ksi-finding-profile-open-alerts-link`
Status: `Implemented`

The genericom open-alerts table — currently the only place findings are listed — is updated so the title cell links to this profile page.

#### Implementation
- Edit `plugins/genericom/static/genericom/js/panel-open-alerts.js`:
  - Add a `titleCellFormatter` that renders the title as an `<a>` with `href="/fedramp-ksi/finding?entity_id=" + row.finding_id`.
  - Wire it onto the Title column.
- Edit `plugins/genericom/panels/open_alerts/__init__.py`:
  - Add `finding_id` to each emitted row dict (already known internally as `finding_id`; just promote it to the row payload).
- The link uses `target="_self"` (default) — clicking navigates in-place. Findings detail is single-page, not a quick-view popover.
- No styling change beyond standard link affordance (blue text, hover underline) consistent with other in-table links in the build.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-finding-profile-open-alerts-link-1 | Title Is A Link | Implemented | The Title column in the genericom open-alerts table renders each title as a link. | |
| req-ksi-finding-profile-open-alerts-link-2 | Correct Target | Implemented | The link points at `/fedramp-ksi/finding?entity_id=<finding_id>`. | |
| req-ksi-finding-profile-open-alerts-link-3 | finding_id In Row Payload | Implemented | The open-alerts `_build_rows` output includes `finding_id` for every row. | |

---

## Future Work

- **Fold KSI + Evidence tables into the standard `tap_web` Table Panel.** Trigger: the standard panel gains *all three* of (a) custom-column / `column_overrides` support, (b) row-detail / click-to-expand, and (c) an inline-payload binding mode that lets the panel render off pre-loaded data instead of always re-executing a Search. At that point this profile's two Tabulator instances should be replaced by two standard Table Panel instances bound to subgraph-derived inline payloads, and the same refactor should sweep up the genericom open-alerts panel.
- **Exception coverage panel** — render an active-exception banner above the description when a `COVERS_FINDING` edge points at this finding from an `active` exception. Held for v1 alongside a standardized exception-display vocabulary.
- **Resolution panel** — once the Resolution model lands, surface the resolution metadata (who, when, how) on resolved findings.
- **Inline edit** — allow status changes, evidence attach/detach, and KSI re-classification directly from the profile.
- **Asset graph mini-viz** — a small Cytoscape sub-graph showing the finding's neighborhood (system → finding → KSI, plus evidence orbiters).
- **History timeline** — once history is wired through plugin models, render the finding's revision history as a timeline section.
- **External correlation IDs** — when the finding model gains a `source_identifier`, surface it with a copy-to-clipboard control.
- **Severity indicator** — once severity lands, render a severity badge in the hero alongside the status badge.
- **Findings index page** — a top-level `/fedramp-ksi/findings` listing; once it exists the breadcrumb's "Findings" segment becomes a navigational link.
- **Print layout** — optimized print stylesheet for audit documentation of individual findings.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Implemented |  |
| Implemented | Requirement is accepted and ready to be implemented |
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
