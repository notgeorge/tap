# KSI Findings Page Specification

## Philosophy

The Findings page is the central index for "what compliance findings exist in this TAP installation, right now?" It pairs two views of the same dataset:

- **By system** — group every open finding by the asset it applies to. Same shape as the alerts table on the Genericom landing page; a compliance professional reading top-down asks "which system has the most issues?" and this answers it.
- **By KSI indicator** — group the same findings by the KSI indicator they relate to. A compliance professional reading bottom-up asks "which indicator is most often violated?" and this answers it.

Each grouping reveals a different shape of the same compliance posture. Surfacing both side-by-side is the page's whole job.

The page is intentionally a *list view*, not a *workflow*. Drill-down to a finding's detail page (already exists at `/fedramp-ksi/finding?entity_id=…`) and the indicator's detail page (`/fedramp-ksi/indicator?entity_id=…`) is via row click-through; in-page editing, batch operations, and cross-finding actions are out of scope. The page is read-only in v0.

The two panels live in this plugin (`fedramp_20x_ksi`) rather than in `genericom`. The Genericom landing's open-alerts panel was authored as a one-off demo build (per [`spec-genericom-open-alerts-table.md`](../../genericom/specs/spec-genericom-open-alerts-table.md)) and is plugin-owned by Genericom. The Findings page reuses the *shape* of that panel — sortable Tabulator table, group-by header, KSI/Relationship/Age columns — but as a fresh, fedramp_20x_ksi-owned panel type. Both will eventually fold into the tap_web standard table panel; see Future.

## Goals

|    |                  |                                                                                       |
| :---: | ---           | ---                                                                                   |
| 1. | Two Groupings        | Same dataset rendered as group-by-system and group-by-KSI                              |
| 2. | List-View Only       | Read-only; drill-down via row click-through, no in-page workflow                       |
| 3. | Plugin-Owned         | Page entity and both panel types live in fedramp_20x_ksi                               |
| 4. | Reuses Existing Drill-Downs | Row click navigates to the existing finding-profile and indicator-profile pages |
| 5. | Verdict-Aware        | Both panels surface relationship_type (passing / violation / informational) consistently with the rest of the plugin |
| 6. | Generic Across Frameworks | Page and panels carry no Genericom-specific or environment-specific terms; reusable across TAP installations |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-ksi-findings-page-entity | [Page Entity](#page-entity) | Implemented | Page slug `/fedramp-ksi/findings`, name "Findings", two-row layout |
| req-ksi-findings-page-panels | [Panel Slots](#panel-slots) | Implemented | findings-by-system and findings-by-ksi panel instances |
| req-ksi-findings-by-system-panel | [Findings By System Panel Type](#findings-by-system-panel-type) | Implemented | Plugin-owned panel type, Tabulator table grouped by system |
| req-ksi-findings-by-ksi-panel | [Findings By KSI Panel Type](#findings-by-ksi-panel-type) | Implemented | Plugin-owned panel type, Tabulator table grouped by KSI indicator |
| req-ksi-findings-page-navigation | [Navigation](#navigation) | Implemented | Reachable from the FedRAMP 20x KSI plugin landing breadcrumb; Findings breadcrumb in finding-profile already wired |
| req-ksi-findings-page-row-actions | [Row Click-Through](#row-click-through) | Implemented | Row click navigates to `/fedramp-ksi/finding?entity_id=…`; KSI cell links to `/fedramp-ksi/indicator?entity_id=…` |

---

### Page Entity
----
RID: `req-ksi-findings-page-entity`
Status: `Implemented`

The Findings page is a TAP-managed `Page` entity owned by the fedramp_20x_ksi plugin.

#### Implementation

- Slug: `/fedramp-ksi/findings`.
- Name: `"Findings"`.
- `DEFAULT_DIMENSIONS` from the Page model (`tap.graph: web`).
- Layout: single column, two rows, both rows `height: "auto"`. Page scrolls vertically when content exceeds viewport.

```json
{
  "columns": {
    "col-1": {
      "width": "1fr",
      "rows": {
        "row-1": {"panel-id": "findings-by-system", "height": "auto"},
        "row-2": {"panel-id": "findings-by-ksi", "height": "auto"}
      }
    }
  }
}
```

`auto/auto` was chosen over `1fr/1fr` because both tables are intrinsically tall (one row per finding) and "fight for fixed space" reads worse than "stack and scroll." The user reads top-to-bottom and uses the browser scroll bar.

The page is seeded by a new GRIFT bundle at `plugins/fedramp_20x_ksi/grift/findings-page.grift.json`.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-ksi-findings-page-entity-1 | Slug Routes | Implemented | `/fedramp-ksi/findings` returns the page (HTTP 200) and renders the two panels. |
| req-ksi-findings-page-entity-2 | Layout Validates | Implemented | The page's layout JSON passes `validate_page_layout` and the page-panels exact-match hotlink. |
| req-ksi-findings-page-entity-3 | Page-Owning Plugin | Implemented | The page entity and its USES_PANEL edges are seeded by `plugins/fedramp_20x_ksi/grift/findings-page.grift.json`. |

---

### Panel Slots
----
RID: `req-ksi-findings-page-panels`
Status: `Implemented`

Two panel slots, two panel instances, both seeded in the same GRIFT batch as the page.

#### Implementation

- **Slot `findings-by-system`** mounts an instance of the [Findings By System panel type](#findings-by-system-panel-type) (fedramp_20x_ksi-owned).
- **Slot `findings-by-ksi`** mounts an instance of the [Findings By KSI panel type](#findings-by-ksi-panel-type) (fedramp_20x_ksi-owned).

Both panel instances live in the same GRIFT bundle as the page entity (per the add-page skill: "Both panel instances live in the same GRIFT batch as the page" applies because both panels are first-run for this page; consuming-plugin ownership is satisfied since the page lives in fedramp_20x_ksi and both panel instances do too).

Each instance carries `hide_header: true` — the panel's intrinsic table header (column titles) provides the visual structure; a separate panel header would be redundant.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-ksi-findings-page-panels-1 | Two Slots Wired | Implemented | The page's `USES_PANEL` outbound edges include exactly two: one to each panel instance, with `hotlink.value` mirroring the slot name. |
| req-ksi-findings-page-panels-2 | Slot Names Match Layout | Implemented | The `findings-by-system` and `findings-by-ksi` slot names appear in `layout.columns.col-1.rows.<row>.panel-id` and as `hotlink.value` on the corresponding edges. |

---

### Findings By System Panel Type
----
RID: `req-ksi-findings-by-system-panel`
Status: `Implemented`

A plugin-owned panel type that renders all open findings as a Tabulator table grouped by the system the finding applies to.

#### Implementation

- Class: `FindingsBySystemPanelType` in `plugins/fedramp_20x_ksi/panels/findings_by_system/__init__.py`.
- Slug: `findings_by_system`.
- View template: `fedramp_20x_ksi/panels/findings_by_system.html`.
- CSS: `fedramp_20x_ksi/css/findings_by_system.css`.
- Registered in `Fedramp20xKsiConfig.ready()`.

Data shape: server-side `get_view_context` runs a gryphon query (matching findings + their system + RELATED_INDICATOR + KSI), flattens to one row per finding with columns `title`, `system_name`, `system_id`, `description`, `ksi_code`, `ksi_name`, `ksi_relationship`, `created_at`, `age_days`, `finding_id`. Sorted by `age_days` ascending, ties broken by `created_at` descending.

Tabulator config:

- `groupBy: "system_name"` (system as the group header).
- Group header styled to match the system-node fill color used in the AWS top-level projection (`#5e89b2` background, `#2b5783` border, white text), so the visual treatment echoes the graph elsewhere in TAP.
- Columns: Title (linkable), Description, KSI (code chip), Relationship (passing/violation/informational pill), Age.
- Initial sort: age ascending.

The panel is conceptually similar to the existing Genericom open-alerts panel ([`spec-genericom-open-alerts-table.md`](../../genericom/specs/spec-genericom-open-alerts-table.md)) but is a fresh build owned by this plugin. The two panel types should converge on the tap_web standard table panel once that panel supports plugin-defined columns, click-to-expand row detail, and group headers (refactor signals captured in the Genericom open-alerts spec). Until then, both panels exist; this one is the canonical fedramp_20x_ksi version.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-ksi-findings-by-system-panel-1 | Panel Type Registered | Implemented | `findings_by_system` is registered in `panel_type_registry` after plugin startup. |
| req-ksi-findings-by-system-panel-2 | Gryphon-Driven Rows | Implemented | Rows come from a gryphon query (no ORM, no module-runner workaround) — see feedback_prefer_gryphon and feedback_gryphon_in_development. |
| req-ksi-findings-by-system-panel-3 | Group By System | Implemented | Tabulator groups rows by `system_name`; group header shows system name and finding count. |
| req-ksi-findings-by-system-panel-4 | Verdict Pill | Implemented | Relationship column renders a colored pill matching the verdict vocabulary: red for violation, green for passing, blue for informational. |
| req-ksi-findings-by-system-panel-5 | Click-Through Title | Implemented | Title cell is an anchor to `/fedramp-ksi/finding?entity_id=…`. |

---

### Findings By KSI Panel Type
----
RID: `req-ksi-findings-by-ksi-panel`
Status: `Implemented`

A plugin-owned panel type that renders the same finding dataset as a Tabulator table grouped by the KSI indicator each finding relates to.

#### Implementation

- Class: `FindingsByKsiPanelType` in `plugins/fedramp_20x_ksi/panels/findings_by_ksi/__init__.py`.
- Slug: `findings_by_ksi`.
- View template: `fedramp_20x_ksi/panels/findings_by_ksi.html`.
- CSS: `fedramp_20x_ksi/css/findings_by_ksi.css`.
- Registered in `Fedramp20xKsiConfig.ready()`.

Data shape: same gryphon query and row shape as findings_by_system, sorted differently (KSI code ascending, then age ascending). Re-projecting the same dataset under a different group_by is the entire reason the two panels are separate — same query, same columns, different lens.

Tabulator config:

- `groupBy: "ksi_code"` (KSI code as the group header).
- Group header styled with the KSI theme color band (the theme-derived color of each indicator) so visually the user sees themes cluster naturally. Theme color mapping is read from the indicator's parent KSI theme via the existing theme→color convention.
- Columns: Title (linkable), Description, System (linkable to the system page once that exists; plain text for v0), Relationship (verdict pill), Age.
- Initial sort: KSI code ascending, age within KSI ascending.

Note: findings without a RELATED_INDICATOR edge are excluded from this panel (no group to put them under). They would still appear in the findings_by_system panel if any survived; the seed data does not currently produce orphans.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-ksi-findings-by-ksi-panel-1 | Panel Type Registered | Implemented | `findings_by_ksi` is registered in `panel_type_registry` after plugin startup. |
| req-ksi-findings-by-ksi-panel-2 | Gryphon-Driven Rows | Implemented | Rows come from a gryphon query. |
| req-ksi-findings-by-ksi-panel-3 | Group By KSI Code | Implemented | Tabulator groups rows by `ksi_code`; group header shows code, name, and finding count. |
| req-ksi-findings-by-ksi-panel-4 | Verdict Pill | Implemented | Relationship column renders the same verdict-pill treatment as findings_by_system. |
| req-ksi-findings-by-ksi-panel-5 | Click-Through Title | Implemented | Title cell is an anchor to `/fedramp-ksi/finding?entity_id=…`. |
| req-ksi-findings-by-ksi-panel-6 | Click-Through KSI Code | Implemented | Group header KSI code is an anchor to `/fedramp-ksi/indicator?entity_id=…`. |

---

### Navigation
----
RID: `req-ksi-findings-page-navigation`
Status: `Implemented`

The Findings page is reachable from:

- The **FedRAMP 20x KSI plugin landing breadcrumb** — every fedramp_20x_ksi profile page has a breadcrumb with a "Findings" segment that already navigates to this URL (the breadcrumb existed before the page; this requirement closes that loop).
- A **direct URL** for bookmarking and external links.

The page is *not* added to a top-level navigation menu in v0. Top-level navigation patterns are still being established across TAP and adding entries piecemeal would create churn.

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-ksi-findings-page-navigation-1 | Direct URL Resolves | Implemented | `GET /fedramp-ksi/findings` returns 200 and renders the page. |
| req-ksi-findings-page-navigation-2 | Breadcrumb Lands | Implemented | The "Findings" breadcrumb segment in finding-profile and indicator-profile pages navigates here. |

---

### Row Click-Through
----
RID: `req-ksi-findings-page-row-actions`
Status: `Implemented`

Both panels expose row-level navigation links. No bulk actions, no row selection, no edit-in-place.

#### Implementation

- **Title cell** in each panel is wrapped in `<a href="/fedramp-ksi/finding?entity_id={finding_id}">` (matches the existing Genericom open-alerts pattern).
- **KSI code** in the findings_by_ksi panel's group header is wrapped in `<a href="/fedramp-ksi/indicator?entity_id={ksi_id}">`.
- **System name** in the findings_by_ksi panel is plain text in v0 — no system page exists yet. (Mirrors the recent unwired-href removal on the finding-profile page.)

#### Acceptance Criteria

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-ksi-findings-page-row-actions-1 | Title Links To Finding Profile | Implemented | Clicking the title cell navigates to `/fedramp-ksi/finding?entity_id=…` for that row. |
| req-ksi-findings-page-row-actions-2 | KSI Code Links To Indicator Profile | Implemented | Clicking the KSI code in the findings_by_ksi group header navigates to `/fedramp-ksi/indicator?entity_id=…`. |
| req-ksi-findings-page-row-actions-3 | No System Link Yet | Implemented | System cells render as plain text; no anchor to a system page until that page exists. |

---

## Out Of Scope (v0)

- **In-page editing.** No status changes, no exception management, no evidence attachment.
- **Bulk operations.** No row selection, no multi-finding actions.
- **Sparklines / trend.** No "findings opened this week" indicator.
- **Filtering.** Both panels show *all* open findings; no UI affordance for filter-by-status, filter-by-verdict, filter-by-class, etc.
- **Pagination.** Tabulator handles arbitrary row counts client-side; we do not server-side paginate in v0.
- **Top-level navigation entry.** Reachable via direct URL and breadcrumb only.
- **System page.** System names render as plain text; the system-detail page is a separate, not-yet-spec'd surface.
- **Caching.** Each page load re-runs the gryphon query.

## Future

- **Fold both panels into the tap_web standard table panel.** The standard panel currently lacks plugin-defined columns, group headers, and click-to-expand row detail (per `req-genericom-open-alerts-panel-type`). Once those land, findings_by_system and findings_by_ksi become two configurations of the standard table rather than two custom panel types — much less code.
- **Filter affordances.** Status (open / resolved), verdict (passing / violation / informational), class (B / C / D), system, KSI theme — pick the filter shape once we see how users actually navigate.
- **A third grouping: findings-by-theme.** KSI themes are the parent of indicators; an "open findings rolled up to theme" view would be a natural addition once 30+ findings exist.
- **Cross-link from system-detail page.** Once the system-detail page exists, cross-link the system cell in findings_by_ksi to it; replace the v0 "plain text" treatment.
- **Export.** CSV / JSON download of the current dataset.
- **Live refresh.** SSE or WebSocket update so the table reflects new findings without a page reload.
