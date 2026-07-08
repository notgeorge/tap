# KSI Indicator Profile Specification

## Philosophy

The KSI Indicator Profile is a dedicated detail page for viewing a single FedRAMP 20x Key Security Indicator. It provides a polished, information-rich view of everything TAP knows about an indicator — its requirement statement, applicable certification classes, referenced NIST controls, source metadata, and parent theme — in a layout designed for compliance professionals who need to understand an indicator thoroughly.

The page is the natural drill-down from the compliance view table: clicking an indicator code navigates here. In v0 it is read-only and informational. Future iterations will add live evidence status, findings, and assessment data as those systems are built.

The page receives the indicator's entity_id as a URL query parameter and uses a gryphon hub-and-spoke query to load the indicator and its graph neighborhood (parent theme via `CONTAINS_INDICATOR` edge) in a single pass.

## Goals

|    |                    |                                                                                       |
| :---: | ---             | ---                                                                                   |
| 1. | Polished           | Visually refined profile layout — not a raw field dump                                |
| 2. | Complete           | All indicator fields displayed in logically grouped sections                           |
| 3. | Contextual         | Parent theme shown with icon, providing navigational context                          |
| 4. | Class-Aware        | Statement section shows class-variant text with per-class toggle                      |
| 5. | Extensible         | Layout accommodates future sections (evidence, findings) without redesign             |
| 6. | Plugin-Owned       | Panel type and page live in the KSI plugin                                            |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-ksi-profile-panel | [Indicator Profile Panel Type](#indicator-profile-panel-type) | Proposed | Plugin-registered panel type for single-indicator display |
| req-ksi-profile-data | [Data Loading](#data-loading) | Proposed | Gryphon hub-and-spoke query loads indicator + theme neighborhood |
| req-ksi-profile-header | [Hero Header](#hero-header) | Proposed | Code, name, status badge, theme badge with icon, class badges |
| req-ksi-profile-statement | [Statement Section](#statement-section) | Proposed | Requirement text with per-class toggle for class_variants |
| req-ksi-profile-metadata | [Metadata Section](#metadata-section) | Proposed | Controls, terms, references in a structured grid |
| req-ksi-profile-changelog | [Change Log Section](#change-log-section) | Proposed | Timeline display of updated_log entries |
| req-ksi-profile-findings-table | [Findings Table](#findings-table) | Implemented | Per-system table of findings related to this indicator |
| req-ksi-profile-page | [Page and Navigation](#page-and-navigation) | Proposed | Page seeded via GRIFT, navigable from compliance view |

---

### Indicator Profile Panel Type
----
RID: `req-ksi-profile-panel`
Status: `Proposed`

The indicator profile is a dedicated panel type registered by the KSI plugin.

#### Implementation
- The panel type lives in `plugins/fedramp_20x_ksi/panels/indicator_profile/`.
- It is registered in `panel_type_registry` during the KSI plugin's `AppConfig.ready()`.
- The panel type slug is `fedramp-20x-ksi-indicator-profile`.
- The panel reads `entity_id` from `request.GET` query parameters (same pattern as the existing viewer and editor panels).
- Required assets:
  - A dedicated `panel-ksi-indicator-profile.css` for profile layout styling
  - No Tabulator or heavy JS libraries needed — the profile is primarily server-rendered HTML
  - Minimal JS for class-variant toggle (can be inline-safe or a small static file)
- No editor view in v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-profile-panel-1 | Plugin-Owned Panel Type | Proposed | The panel type class lives in the KSI plugin package. | |
| req-ksi-profile-panel-2 | Registered At Startup | Proposed | The panel type is registered in `panel_type_registry` during `AppConfig.ready()`. | |
| req-ksi-profile-panel-3 | Reads Entity ID From Query Params | Proposed | The panel reads `entity_id` from `request.GET` to identify the indicator. | |

### Data Loading
----
RID: `req-ksi-profile-data`
Status: `Proposed`

The profile panel loads the indicator and its graph neighborhood via a gryphon hub-and-spoke query.

#### Implementation
- The panel's `get_view_context()` reads `entity_id` from `request.GET`.
- It executes a gryphon hub-and-spoke query: `MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id RETURN hub, e, neighbor`.
- The query returns the indicator node, the parent theme node (via `CONTAINS_INDICATOR` edge), and any other future edges.
- The raw subgraph is passed to the template context — the template renders server-side from the structured data (unlike the compliance view which passes JSON to JS).
- The `extended` subgraph layer provides `icon_url` for the parent theme.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-profile-data-1 | Gryphon Hub-and-Spoke | Proposed | Data loaded via gryphon query through the search service layer. | |
| req-ksi-profile-data-2 | Theme Resolved | Proposed | Parent theme is resolved from the `CONTAINS_INDICATOR` edge in the neighborhood. | |
| req-ksi-profile-data-3 | Graceful Missing Entity | Proposed | If `entity_id` is missing or invalid, the panel renders an error state rather than crashing. | |

### Hero Header
----
RID: `req-ksi-profile-header`
Status: `Proposed`

The top of the profile displays the indicator's identity at a glance.

#### Implementation
- **Code** displayed prominently in a monospace font (e.g., `KSI-IAM-MFA`).
- **Name** as the primary heading (e.g., "Adopting Passwordless Methods").
- **Status badge** — styled pill showing Published / Draft / Deprecated (same styling as compliance view).
- **Theme badge** — parent theme name with per-theme icon, linking back to the compliance view (or scrolling to the theme group). Displayed as a navigational breadcrumb element.
- **Class badges** — applicable certification classes displayed as badge row. All purple if no class_variants; clickable with active highlight if class_variants exist (same behavior as compliance view).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-profile-header-1 | Code And Name Prominent | Proposed | Code and name are the primary visual elements at the top of the profile. | |
| req-ksi-profile-header-2 | Status Badge | Proposed | Status is displayed as a styled badge consistent with the compliance view. | |
| req-ksi-profile-header-3 | Theme Context | Proposed | Parent theme is shown with icon as a navigational breadcrumb. | |
| req-ksi-profile-header-4 | Class Badges | Proposed | Applicable classes shown as badges; clickable for class_variant indicators. | |

### Statement Section
----
RID: `req-ksi-profile-statement`
Status: `Proposed`

The requirement statement is the core content of the profile.

#### Implementation
- For indicators with a direct `description`: display the statement text in a readable block.
- For indicators with `class_variants`: display the statement for the currently active class. Class badges in the header toggle which variant is shown (same per-row toggle pattern as the compliance view, with fade transition).
- The statement section should have comfortable typography: larger font size than table cells, good line-height, adequate padding.
- If the statement contains markdown-style formatting (e.g., `**Optional:**`), render it as styled text rather than raw markdown syntax.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-profile-statement-1 | Statement Displayed | Proposed | The indicator's requirement statement is prominently displayed. | |
| req-ksi-profile-statement-2 | Class-Variant Toggle | Proposed | For class_variant indicators, clicking class badges swaps the statement with a fade. | |
| req-ksi-profile-statement-3 | Readable Typography | Proposed | Statement text uses comfortable reading typography. | |

### Metadata Section
----
RID: `req-ksi-profile-metadata`
Status: `Proposed`

Structured display of the indicator's reference data: NIST controls, terms, and external references.

#### Implementation
- **NIST Controls** — displayed as a list or grid of control IDs (e.g., `ac-2.2`, `ia-12`). Each control rendered as a compact chip/tag. Future: these will link to NIST control nodes once `req-fedramp-20x-ksi-nist-crosswalk` is implemented.
- **Terms** — list of referenced terms from the `terms` field (e.g., "Information Resource", "Machine-Based (Information Resources)"). Displayed as a simple list or tag set.
- **Reference** — if `reference` and/or `reference_url` are populated, display as a labeled link or citation block.
- Empty fields are omitted rather than showing blank sections.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-profile-metadata-1 | Controls Displayed | Proposed | NIST control IDs shown as chips/tags. | |
| req-ksi-profile-metadata-2 | Terms Displayed | Proposed | Referenced terms shown when present. | |
| req-ksi-profile-metadata-3 | Reference Link | Proposed | External reference displayed as a link when present. | |
| req-ksi-profile-metadata-4 | Empty Fields Omitted | Proposed | Sections with no data are hidden, not shown as empty. | |

### Change Log Section
----
RID: `req-ksi-profile-changelog`
Status: `Proposed`

The indicator's `updated_log` displayed as a timeline of changes.

#### Implementation
- Each `updated_log` entry contains `{date, comment}`.
- Displayed as a vertical timeline or simple date-labeled list, most recent first.
- If `updated_log` is empty, the section is omitted.
- The section is visually distinct (e.g., a muted background or bordered card) to separate it from the active requirement data.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-profile-changelog-1 | Timeline Display | Proposed | Change log entries rendered as a date-labeled list or timeline. | |
| req-ksi-profile-changelog-2 | Reverse Chronological | Proposed | Most recent entries appear first. | |
| req-ksi-profile-changelog-3 | Omitted When Empty | Proposed | Section is hidden if `updated_log` is empty. | |

### Findings Table
----
RID: `req-ksi-profile-findings-table`
Status: `Implemented`

A per-system table of findings related to this indicator — one row per (system, finding) pair. Reviewers reading the indicator profile see immediately *which assets currently have outstanding work against this indicator* without navigating away.

#### Implementation
- Section header: "Findings Affecting This Indicator". Placed after the Reference section and before the Change Log.
- Rendered as a Tabulator table initialized from a JSON payload embedded in the panel template (same pattern as the finding profile's KSI / Evidence tables and the genericom open-alerts panel). Layout: `fitColumns`, no pagination — counts are bounded by how many findings any one indicator picks up.
- Data is loaded by an additional gryphon query the panel runs alongside the existing hub-and-spoke. The new query is two-hop with both `MATCH` clauses inner-joined:
  - `MATCH (i)<-[r1:RELATED_INDICATOR]-(f:finding)` (findings linked to this indicator)
  - `MATCH (s)-[r2:HAS_COMPLIANCE_FINDING]->(f)` (each finding's system parents)
  - `WHERE i.entity_id = $entity_id`
  - Return `f, r1, r2, s` so the panel can build flat (system, finding) row pairs.
- The two `MATCH` clauses inner-join. Gryphon's parser does not yet support `OPTIONAL MATCH`, so a finding with no `HAS_COMPLIANCE_FINDING` parent does not appear in the table. v0 seed data always carries a parent system, so this is acceptable; orphan-finding handling is Future work and will land either with `OPTIONAL MATCH` support in gryphon or with a small fallback module pass that surfaces unmatched findings.
- One row per (system, finding) pair: a finding with multiple `HAS_COMPLIANCE_FINDING` parents emits multiple rows.
- Columns (left-to-right):
  - **Status** — finding `status` field (`open` / `resolved`) rendered as a colored pill via a Tabulator formatter. Color vocabulary: open → amber, resolved → green. Placed first to align with the Verdict / Relationship pill columns established by the finding profile pattern.
  - **System** — the parent asset's name. Rendered as a link to the standard system page (`/grid/<entity_id>`) via a Tabulator formatter. Cell shows `—` when the finding has no `HAS_COMPLIANCE_FINDING` parent.
  - **Finding** — the finding's `name`. Rendered as a link to the finding profile (`/fedramp-ksi/finding?entity_id=<entity_id>`) via a Tabulator formatter.
  - **Description** — finding `description`, full-text wrap (`formatter: "textarea"`).
  - **Opened** — finding `created_at` rendered with the same relative-time helper used in the finding profile; full UTC timestamp surfaces as a `title`-attribute hover tooltip. Right-aligned, narrow column.
- Empty state: if the indicator has zero linked findings, Tabulator's `placeholder` shows: "No findings linked to this indicator."
- Sort: default ascending by Status (open first), tie-break by Opened (descending — newest first within a status group).

#### Development
- The two-hop gryphon (sequential `MATCH` clauses) is the same chained-MATCH pattern the genericom open-alerts panel uses, just applied to the inverse direction. Inner-join semantics are acceptable while the seed guarantees every finding carries a parent system; revisit if gryphon ships `OPTIONAL MATCH` or if real-world data introduces parent-less findings.
- Rows are emitted as flat `(system, finding)` pairs server-side rather than as nested structures the JS would have to flatten. Mirrors the genericom open-alerts panel's flat-row contract.
- The table reuses the same Tabulator skin and pill vocabulary as the finding profile's tables — the two profiles already share their visual vocabulary, so this section reads as a natural extension rather than a new component.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-profile-findings-table-1 | Two-Hop Gryphon | Implemented | The findings table is loaded by a two-hop gryphon query (`RELATED_INDICATOR` ← finding ← `HAS_COMPLIANCE_FINDING`) returning flat (system, finding) row pairs. | |
| req-ksi-profile-findings-table-2 | Per-System Rows | Implemented | A finding with multiple `HAS_COMPLIANCE_FINDING` parents emits one row per parent. Findings without any parent are not surfaced in v0 (gryphon parser limitation; tracked in Future Work). | |
| req-ksi-profile-findings-table-3 | System Link | Implemented | The System cell links to `/grid/<entity_id>` for the parent asset when present. | |
| req-ksi-profile-findings-table-4 | Finding Link | Implemented | The Finding cell links to `/fedramp-ksi/finding?entity_id=<entity_id>`. | |
| req-ksi-profile-findings-table-5 | Status Pill First | Implemented | Status renders as a colored pill in the leftmost column, aligned with the verdict/relationship pill convention from the finding profile. | |
| req-ksi-profile-findings-table-6 | Opened Relative | Implemented | The Opened column shows a relative-time label with full UTC in a hover tooltip. | |
| req-ksi-profile-findings-table-7 | Empty State | Implemented | If the indicator has zero linked findings, the table's placeholder renders an empty-state message. | |
| req-ksi-profile-findings-table-8 | Tabulator-Backed | Implemented | The table is initialized via Tabulator using the existing `tap_web/js/lib/tabulator.min.js` asset. | |

---

### Page and Navigation
----
RID: `req-ksi-profile-page`
Status: `Proposed`

The profile page is seeded via GRIFT and navigable from the compliance view.

#### Implementation
- The page is seeded via a GRIFT file in the KSI plugin (`grift/ksi-indicator-profile-page.grift.json`).
- The page slug is `/fedramp-ksi/indicator`.
- The page is accessed at its slug URL with the indicator's entity_id as a query parameter: `/fedramp-ksi/indicator?entity_id=<uuid>`.
- The compliance view's Code column links are updated to navigate to this page instead of the generic entity viewer.
- The profile page's hero header includes a breadcrumb link back to the compliance view (`/fedramp-ksi`).
- The page contains a single panel slot occupied by the indicator profile panel instance.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-profile-page-1 | GRIFT Seeded | Proposed | Page and panel seeded via plugin GRIFT. | |
| req-ksi-profile-page-2 | Query Param Navigation | Proposed | The page reads the indicator identity from a URL query parameter. | |
| req-ksi-profile-page-3 | Compliance View Links | Proposed | Code links in the compliance view table navigate to this profile page. | |
| req-ksi-profile-page-4 | Breadcrumb Back | Proposed | The profile includes a link back to the compliance view. | |

## Future Work

- **Orphan findings in the findings table**: Once gryphon supports `OPTIONAL MATCH` (or once a small fallback module pass is added), surface findings that lack any `HAS_COMPLIANCE_FINDING` parent. Until then, the inner-joined two-hop in `req-ksi-profile-findings-table` only shows findings with at least one system parent.
- **Evidence section**: Show per-indicator evidence coverage — linked evidence artifacts, collection status, gaps.
- **Findings section enrichments**: Add severity, remediation status (once Resolution lands), and assessment history columns to the findings table built in `req-ksi-profile-findings-table`.
- **NIST control links**: Once `req-fedramp-20x-ksi-nist-crosswalk` is implemented, controls become clickable links to NIST control profile pages.
- **Term links**: Link terms to a future glossary or term-node viewer.
- **Edit mode**: Allow authorized users to annotate indicators with organization-specific notes or evidence mappings.
- **Print layout**: Optimized print stylesheet for audit documentation of individual indicators.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
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
