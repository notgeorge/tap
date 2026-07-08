# KSI Instance Findings Panel Specification

## Philosophy

The Instance Findings panel renders every Finding attached to a single asset (typically an EC2 instance, but the panel is asset-agnostic) in one place, with each row inline-expandable to reveal the finding's description, related KSI indicators, and supporting evidence. It is the per-asset analog of the dedicated Finding Profile page: where Finding Profile shows one finding's full story on its own page, Instance Findings shows every finding for one asset in a single panel — drill-down without leaving the asset page.

The panel is keyed on the asset's `entity_id` (read from the URL query string the same way the existing finding/indicator profile panels do) and runs a single gryphon search returning the asset's findings plus their evidence and related-indicator neighborhoods in one pass. The render path mirrors `finding_profile`'s aggregation + verdict precedence so verdict pills read identically across surfaces.

The visual contract reuses the chevron + inline-detail pattern from the dedicated Finding Profile evidence table. Each row's chevron toggles an inline detail block (Tabulator's native `rowFormatter` row-detail) containing the finding's description, a Related Indicators mini-table, and an Evidence mini-table. The Evidence mini-table preserves its own per-row chevron-to-evidence-detail behavior — the same nested expand the dedicated finding profile uses today.

This is a v1, plugin-owned panel — same justification as `finding_profile`: column-customization and row-detail are not yet supported by the standard `tap_web` Table Panel. The refactor signal is identical: when `column_overrides`, row-detail, and inline-payload binding all land on the standard panel, fold this panel into it.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Asset-Scoped       | The panel is keyed on a single asset entity_id and shows only that asset's findings |
| 2. | Multi-Finding      | Renders zero, one, or many findings — no upper limit beyond the search's default_limit |
| 3. | Inline Drill-Down  | Each row expands inline to reveal the same data the dedicated finding profile shows |
| 4. | Evidence Drill-In  | Within the expanded row, the evidence table preserves the chevron-to-detail pattern from finding_profile |
| 5. | Verdict-Consistent | Verdict pills derive from the same `_aggregate_verdict` precedence used by finding_profile |
| 6. | Empty-State Aware  | An asset with zero findings renders a "No findings" empty state, not a hidden panel |
| 7. | Single-Query Load  | All neighborhood data (findings + their evidence + their related indicators) loads in one gryphon pass |
| 8. | Plugin-Owned       | Panel type and search live in the KSI plugin in v0; refactor path back to the standard Table Panel is documented |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-ksi-instance-findings-panel | [Panel Type Contract](#panel-type-contract) | In Development | Plugin-registered panel type; reads `entity_id` from query params |
| req-ksi-instance-findings-data | [Data Loading](#data-loading) | In Development | Single gryphon search returning findings + evidence + related indicators |
| req-ksi-instance-findings-rows | [Row Shape](#row-shape) | In Development | Per-row columns: Chevron · Verdict · Title · Summary · KSI · Age |
| req-ksi-instance-findings-detail | [Inline Detail Block](#inline-detail-block) | In Development | Description, Related Indicators table, Evidence table — all inline |
| req-ksi-instance-findings-evidence-expand | [Evidence Expand](#evidence-expand) | In Development | Evidence rows in the inline detail keep the chevron-to-detail behavior from finding_profile |
| req-ksi-instance-findings-empty | [Empty State](#empty-state) | In Development | Zero-finding case shows "No findings" |
| req-ksi-instance-findings-title-link | [Title Linkage](#title-linkage) | In Development | Title cell links to the dedicated finding profile page |

---

### Panel Type Contract
----
RID: `req-ksi-instance-findings-panel`
Status: `In Development`

#### Implementation
- Panel type class at `plugins/fedramp_20x_ksi/panels/instance_findings/__init__.py`.
- Slug: `fedramp-20x-ksi-instance-findings`.
- Registered in `panel_type_registry` during `Fedramp20xKsiConfig.ready()`.
- Reads `entity_id` from `request.GET`.
- Static assets:
  - `static/fedramp_20x_ksi/css/panel-ksi-instance-findings.css`
  - `static/fedramp_20x_ksi/js/panel-ksi-instance-findings.js`
  - Tabulator CSS + JS pulled from existing `tap_web/css/lib/tabulator.min.css` + `tap_web/js/lib/tabulator.min.js`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-instance-findings-panel-1 | Plugin-Owned | In Development | Panel class lives in the KSI plugin package. | |
| req-ksi-instance-findings-panel-2 | Registered At Startup | In Development | Type registered in `panel_type_registry` from `AppConfig.ready()`. | |
| req-ksi-instance-findings-panel-3 | Entity ID From Query Params | In Development | Panel reads `entity_id` from `request.GET`. | |

---

### Data Loading
----
RID: `req-ksi-instance-findings-data`
Status: `In Development`

#### Implementation
- New gryphon Search seeded in the EC2 instance page GRIFT, parameterized on `$entity_id`:
  ```
  MATCH (asset)-[hf:HAS_COMPLIANCE_FINDING]->(f:finding) WHERE asset.entity_id = $entity_id
  OPTIONAL MATCH (f)-[he:HAS_COMPLIANCE_EVIDENCE]->(ev:evidence)
  OPTIONAL MATCH (f)-[ri:RELATED_INDICATOR]->(ksi:ksi_indicator)
  RETURN asset, hf, f, he, ev, ri, ksi
  ```
- The panel walks the returned envelope, pivots edges by finding entity_id, builds a per-finding payload (`{name, summary, description, status, verdict, ksis, evidence, age_days}`), and emits a flat list as JSON consumed by Tabulator.
- Verdict aggregation reuses `_aggregate_verdict` from `finding_profile` (importing rather than duplicating).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-instance-findings-data-1 | Single Search | In Development | Findings + evidence + related indicators load in one gryphon pass. | |
| req-ksi-instance-findings-data-2 | Verdict Reuse | In Development | Verdict precedence matches `finding_profile._aggregate_verdict`. | Imported, not duplicated |
| req-ksi-instance-findings-data-3 | Open-Status Filter | In Development | Only `status="open"` findings render in v0. | Resolved findings deferred — see Future |

---

### Row Shape
----
RID: `req-ksi-instance-findings-rows`
Status: `In Development`

Each row represents one finding. Columns, left to right:

1. **Chevron** — collapsed/expanded toggle. Click anywhere on the chevron cell or the row toggles expansion.
2. **Verdict** — pill (`Passing` / `Violation` / `Informational`). Falls back to lifecycle status (`Open`) when no evidence has been aggregated yet.
3. **Title** — the finding's name. Link → `/fedramp-ksi/finding?entity_id=<finding_id>`.
4. **Summary** — the finding's `summary` field, wrapping if needed.
5. **KSI** — the related indicator's code as a chip (e.g. `KSI-SVC-SNT`). Multi-indicator findings show the first; v0 seed data is single-indicator.
6. **Age** — relative-time label of `created_at` ("today", "3d ago", "Mar 2", etc.).

The grouping/sort default is by age ascending (newest first), matching the open-alerts table.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-instance-findings-rows-1 | Chevron Column | In Development | First column is a chevron that toggles inline detail expansion. | |
| req-ksi-instance-findings-rows-2 | Verdict Pill | In Development | Verdict pill uses the same vocabulary and CSS classes as `findings-rel--*` from the shared findings_table.css. | |
| req-ksi-instance-findings-rows-3 | Title Link | In Development | Title cell renders an `<a>` to `/fedramp-ksi/finding?entity_id=<finding_id>`. | |

---

### Inline Detail Block
----
RID: `req-ksi-instance-findings-detail`
Status: `In Development`

When a row's chevron is toggled open, Tabulator renders an inline detail block beneath the row. The detail block contains:

- **Description** — the finding's full `description` field, multi-line, monospaced where the upstream content uses code fences.
- **Related Indicators** — a mini Tabulator (or simple table) with columns: Code · Name · Description · Relationship.
- **Evidence** — a mini Tabulator with one row per evidence entity, columns: Verdict · Name · Kind · Updated · Note · (chevron). The chevron behavior matches the dedicated finding profile evidence table — see [Evidence Expand](#evidence-expand).

If a finding has zero related indicators or zero evidence, the corresponding mini-table renders an inline "—" rather than a sub-empty-state, to keep the detail block compact.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-instance-findings-detail-1 | Description Rendered | In Development | Detail block contains the full description text, line breaks preserved. | |
| req-ksi-instance-findings-detail-2 | Indicators Mini-Table | In Development | Detail block contains a Related Indicators mini-table when ≥1 indicator linked. | |
| req-ksi-instance-findings-detail-3 | Evidence Mini-Table | In Development | Detail block contains an Evidence mini-table when ≥1 evidence linked. | |

---

### Evidence Expand
----
RID: `req-ksi-instance-findings-evidence-expand`
Status: `In Development`

The Evidence mini-table inside each finding's inline detail block reuses the chevron-to-detail behavior from `panel-ksi-finding-profile.js`: clicking an evidence row's chevron expands a sub-detail panel beneath the evidence row containing the evidence body (description / scanner output).

This nested expansion is the load-bearing UX requirement for the panel — the user explicitly called out preserving the dig-output drill-in. The chevron icon, expand animation, and rendered detail layout match the dedicated finding profile by design.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-instance-findings-evidence-expand-1 | Evidence Chevron | In Development | Evidence rows render a chevron that toggles a per-evidence detail panel. | |
| req-ksi-instance-findings-evidence-expand-2 | Same Visual As Finding Profile | In Development | Chevron icon, animation, and detail block styling match the finding profile evidence table. | |

---

### Empty State
----
RID: `req-ksi-instance-findings-empty`
Status: `In Development`

An asset with no `HAS_COMPLIANCE_FINDING` edges renders a single-line "No findings" panel state — the panel is **not** hidden. Hiding the panel would mask the difference between "no findings" and "panel failed to load." The empty state is rendered by the template when the row payload is empty.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-instance-findings-empty-1 | Empty Renders | In Development | Zero-finding case renders "No findings" rather than an empty panel. | |

---

### Title Linkage
----
RID: `req-ksi-instance-findings-title-link`
Status: `In Development`

The Title cell links to the dedicated finding profile at `/fedramp-ksi/finding?entity_id=<finding_id>`. This is the same drill-in path the open-alerts table uses; consistency keeps the navigation model coherent.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-ksi-instance-findings-title-link-1 | Title Anchor | In Development | Title cell renders a single anchor with `href="/fedramp-ksi/finding?entity_id=<finding_id>"`. | |

---

## Out Of Scope (v0)

- Resolved findings — only `status="open"` renders.
- Exception coverage — covered findings are not visually distinguished in v0; the `COVERS_COMPLIANCE_FINDING` edge is read by the open-findings counter elsewhere but not by this panel.
- Findings on assets nested under this asset (programs, ports, network interfaces hosted by an EC2). v0 only walks `HAS_COMPLIANCE_FINDING` directly from the asset; deeper rollup is Future.
- Multi-indicator findings render only the first KSI in the row chip; full list still appears in the inline detail mini-table.
- Lifecycle controls (resolve, attach evidence, edit relationship) — read-only panel.

## Future

- Roll up findings from nested assets (e.g. show the prod-web-a EC2's findings *and* findings on its programs/ports). Likely as a panel `config["include_descendants"]` toggle.
- Severity column once severity lands on the Finding model.
- Filter chips in the panel header (verdict, KSI theme, age window).
- Refactor into the standard Table Panel once it supports column overrides + row-detail + inline-payload binding.
- Cross-asset variant (`/fedramp-ksi/findings-by-asset` page) for use cases where the asset is selected from a list rather than implied by the page.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development |  |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated |  |
