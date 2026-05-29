# Samsite Compliance Artifact Viewer Pages — v0

## Philosophy

Samsite collects compliance artifacts off the live site and decomposes or stores them on the grid: the **KSI signal** (decomposed into signal + components + validations + violations), the **VDR report** (decomposed into report + findings), and three **whole-blob `compliance_artifact`s** — OSCAL SSP, OSCAL POA&M, and the IIW inventory. This spec gives each top-level artifact a **classy workbench viewer**, plus an **artifact inventory** page that indexes everything collected and clicks through to the viewers, all under one `/samsite/artifacts` section.

**Decomposed vs. blob** is the spine:

- **Decomposed artifacts** (KSI signal, VDR report) are recomposed from their graph nodes by walking edges (`DECLARES_COMPONENT` / `DECLARES_VALIDATION` / `REPORTS_VIOLATION` / `REPORTS_FINDING`) with Gryphon — TAP makes them navigable in ways the publisher's static JSON is not.
- **Whole-blob artifacts** render their `compliance_artifact.content`: OSCAL SSP/POA&M via `roscale`'s existing workbench renderers (a deliberate cross-plugin dependency); IIW parses its CSV into a table.

Every viewer shares a workbench shape: a trust/coverage band, headline stats, the artifact's content (a minimalist-themed Tabulator where tabular), and provenance footers — with a **sequence-nav selector** above it (latest by default, back/forward across emissions) and **latest-by-default resolution** via `tap_web.panels.entity_resolution`.

**Roadmap alignment.** Supports `step-rampart-sam-demo` (`plan/road-rampart.md`): makes the collected compliance artifacts legible, surfaces findings, explains status.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Classy Per-Artifact Viewers | KSI signal, VDR report, and IIW each render in a human-legible workbench; OSCAL SSP/POA&M reuse roscale's. |
| 2. | One Artifacts Section | All viewers + the inventory live under `/samsite/artifacts/*`; the KSI Scoreboard sits directly under `/samsite`. |
| 3. | Latest By Default + History | Bare viewer URL renders the latest emission (entity-resolution fallback); a sequence-nav selector walks older/newer emissions. |
| 4. | Recompose + Link Out | Decomposed viewers rebuild from graph nodes; KSI components link to the AWS resource; VDR findings link to the per-finding viewer. |
| 5. | Interactive Tables | Component/finding/inventory tables are Tabulator-driven (sortable, quick-filter), minimalist-themed; VDR headline stats are faceted toggle filters. |
| 6. | Provenance + Disclosure | Every viewer surfaces signature/disclosure with `unknown ≠ false`. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-samsite-artifact-inventory | [Artifact Inventory Page](#artifact-inventory-page) | Implemented | `/samsite/artifacts` — reuses the compliance table panels (KSI signals, VDR reports, compliance artifacts grouped by kind); rows click through via `PER_TYPE_DETAIL_URL` |
| req-samsite-viewer-routes | [Viewer Routes & IA](#viewer-routes--ia) | Implemented | Viewers at `/samsite/artifacts/{ksi-signal,vdr-report,iiw,ssp,poam}`; KSI Scoreboard at `/samsite/scoreboard`; GitHub repo nestled at `/samsite/repo`; FedRAMP-KSI + `/samsite/compliance` hidden |
| req-samsite-viewer-ksi-signal | [KSI Signal Viewer](#ksi-signal-viewer) | Implemented | `samsite-ksi-signal-workbench` — trust band, headline stats, violations-high, components Tabulator (grouped under AWS, C/I/A badges), validations |
| req-samsite-viewer-vdr-report | [VDR Report Viewer](#vdr-report-viewer) | Implemented | `samsite-vdr-report-workbench` — coverage band, findings Tabulator (PAIN/KEV/blocking), headline stats as faceted toggle filters |
| req-samsite-viewer-iiw | [IIW Viewer](#iiw-viewer) | Implemented | `samsite-iiw-workbench` — CSV → Tabulator with dynamic columns, full-bleed page + angled headers |
| req-samsite-viewer-oscal | [OSCAL SSP / POA&M Viewers](#oscal-ssp--poam-viewers) | Implemented | roscale `oscal_workbench` / `oscal_poam_workbench` reused, relocated under `/samsite/artifacts` |
| req-samsite-viewer-provenance-band | [Provenance + Disclosure Band](#provenance--disclosure-band) | Implemented | Shared band; `unknown ≠ false` pills |
| req-samsite-viewer-sequence-nav | [Sequence Navigator](#sequence-navigator) | Implemented | A `tap_web` sequence-nav panel above each viewer — see `spec-web-panel-sequence-navigation-v0.md` |
| req-samsite-viewer-toggle-filters | [Faceted Toggle Filters](#faceted-toggle-filters) | Implemented | VDR headline stats down-select the findings table (AND-combined + text); zero-count facets inert |
| req-samsite-viewer-plugin-dependency | [Plugin Dependency on roscale](#plugin-dependency-on-roscale) | Implemented | Deliberate cross-plugin reuse of roscale's OSCAL renderers |
| req-samsite-viewer-row-nav-coupling | [Row-Nav Map Coupling](#row-nav-map-coupling) | Implemented (debt) | `PER_TYPE_DETAIL_URL` in `panel-table.js` hardcodes the routes — backlog: a plugin-registered mechanism |

### Artifact Inventory Page
----
RID: `req-samsite-artifact-inventory`
Status: `Implemented`

`/samsite/artifacts` mounts the three existing compliance table panel instances (`samsite-compliance-ksi-signals`, `-vdr-reports`, `-artifacts`) as movable subjects — KSI Signal Emissions, VDR Reports, and a Compliance Artifacts table grouped by `kind` (IIW / POA&M / SSP). Node-mode rows click through to the matching viewer via `PER_TYPE_DETAIL_URL`. It is the discoverable launch surface for the Artifacts section.

### Viewer Routes & IA
----
RID: `req-samsite-viewer-routes`
Status: `Implemented`

| Type | Route | Renderer |
| --- | --- | --- |
| Artifact inventory | `/samsite/artifacts` | reused compliance table panels |
| KSI signal | `/samsite/artifacts/ksi-signal` | `samsite-ksi-signal-workbench` |
| VDR report | `/samsite/artifacts/vdr-report` | `samsite-vdr-report-workbench` |
| IIW | `/samsite/artifacts/iiw` | `samsite-iiw-workbench` (full-bleed) |
| OSCAL SSP | `/samsite/artifacts/ssp` | roscale `oscal_workbench` |
| OSCAL POA&M | `/samsite/artifacts/poam` | roscale `oscal_poam_workbench` |
| KSI Scoreboard | `/samsite/scoreboard` | `samsite-ksi-scoreboard` (promoted, directly under Samsite) |
| Repository | `/samsite/repo` | github_core repo page (relocated; loads `notgeorge/samsite` by default) |

All are bare-slug, discoverable pages (no `urls.py` parameterized routes); they resolve latest-by-default via entity-resolution and accept a deep-link entity-id query var. The **command-modal tree**: Samsite → KSI Scoreboard, Artifacts (→ KSI Signal, VDR Report, IIW, POA&M, SSP), Repository; Administrivia kept. `nav_weight` orders them. The **FedRAMP 20x KSI plugin pages** (`/fedramp-ksi`, `/fedramp-ksi/findings`) and the superseded **`/samsite/compliance`** dashboard are `discoverable: false`. The relocation also yields the `Samsite › Artifacts › <type>` breadcrumb nesting.

### KSI Signal Viewer
----
RID: `req-samsite-viewer-ksi-signal`
Status: `Implemented`

`samsite-ksi-signal-workbench` resolves a `ksi_signal` and recomposes it: a trust band (signature + disclosure pills, `unknown ≠ false`); Headline Stats (components, types, checks passed/failed, violations); the **Violations** panel directly below the headline (load-bearing — "no violations" leads); a **components Tabulator** (grouped by `component_id` prefix so all AWS resources fall under one "AWS" heading with the specific type in the Type column, C/I/A as L/M/H badges, sortable + quick-filter); a validations table; and signal-metadata + provenance footers. Components/validations/violations are walked from the signal over their edges (envelope filtered to the child type).

### VDR Report Viewer
----
RID: `req-samsite-viewer-vdr-report`
Status: `Implemented`

`samsite-vdr-report-workbench` resolves a `vdr_report`: a coverage band (`kev_catalog_loaded` / `dependabot_alerts_loaded`, `unknown ≠ false`); Headline Stats counted from the rendered findings (total, KEV, blocking, internet-reachable, risk-accepted); a **findings Tabulator** (PAIN badge, KEV/net/blocking tick columns, sortable + quick-filter); report-metadata footer. Findings walk `REPORTS_FINDING`.

### IIW Viewer
----
RID: `req-samsite-viewer-iiw`
Status: `Implemented`

`samsite-iiw-workbench` resolves an `iiw` `compliance_artifact`, parses its CSV `content` into a Tabulator with **dynamic columns from the header** (positional keys so arbitrary header text is safe), sortable + quick-filter. The page is **full-bleed** (drops the max-width cap) and the headers render at **-45°** so the wide workbook's columns fit; a provenance band + footer bracket it.

### OSCAL SSP / POA&M Viewers
----
RID: `req-samsite-viewer-oscal`
Status: `Implemented`

`/samsite/artifacts/ssp` and `/poam` mount roscale's `oscal_workbench` / `oscal_poam_workbench` (relocated from `/samsite/compliance/*`), resolving the latest samsite-collected artifact of the matching `kind`. The POA&M workbench leads with Headline Stats, defaults the Open + Risk-Accepted register groups expanded, and footers the provenance/metadata.

### Provenance + Disclosure Band
----
RID: `req-samsite-viewer-provenance-band`
Status: `Implemented`

Each viewer surfaces `signature_verified` (✓/✗/unknown) + signer identity, and machine-readable disclosure/coverage flags as pills — an absent flag renders `unknown`, distinct from explicit `false`, never a silent omission.

### Sequence Navigator
----
RID: `req-samsite-viewer-sequence-nav`
Status: `Implemented`

A `tap_web` `sequence-nav` panel is mounted above each viewer, sharing the viewer's `entity_id_var`; it resolves the full newest-first emission sequence and renders Older/Newer + "N of M · ‹when› · latest". Canonical contract: `tap_web/specs/spec-web-panel-sequence-navigation-v0.md`. (Graduated the entity-resolution "History timeline panel" seam.)

### Faceted Toggle Filters
----
RID: `req-samsite-viewer-toggle-filters`
Status: `Implemented`

The VDR Headline Stats (KEV, blocking, internet-reachable, risk-accepted) are toggle cards that down-select the findings Tabulator — AND-combined with each other and with the text quick-filter; the Findings total is clear-all. A hollow corner dot marks the togglable boxes (fills + tints when active). A **zero-count** toggle filters to nothing, so it renders inert (no dot, no hover, no click). The cards drive one combined `setFilter` via `Tabulator.findTable` (the filter input bypasses panel-table.js's wiring so text + facets compose).

### Plugin Dependency on roscale
----
RID: `req-samsite-viewer-plugin-dependency`
Status: `Implemented`

The OSCAL viewers reuse roscale's `oscal_workbench` / `oscal_poam_workbench` — a **deliberate, intended** cross-plugin dependency (the legitimate kind under the hermetic coincidental-vs-deliberate axis; `req-tap-test-hermetic-plugins` Future). Samsite mounts the registered panels and configures their public entity-resolution config only; no reach-in. (Lifting the renderer to a shared home remains an option if a third consumer appears.)

### Row-Nav Map Coupling
----
RID: `req-samsite-viewer-row-nav-coupling`
Status: `Implemented` (acknowledged debt)

Per-type row navigation lives in a hardcoded `PER_TYPE_DETAIL_URL` map in `tap_web/static/tap_web/js/panel-table.js` naming samsite routes (`ksi_signal`, `vdr_report`, `compliance_artifact` fanned by kind, plus the sub-entity routes). Core `tap_web` JS coupled to plugin URLs — recorded as debt on the plugin-dependency backlog; a plugin should register its detail routes rather than core hardcoding them.

## Non-Goals (v0)

- **Runtime-signal collection + `compliance_artifact` content-hash re-key.** The continuously-changing `ksi-signal-runtime.json` isn't collected, and `compliance_artifact` still keys on `kind/fetched_at` (re-fetches over-accumulate). Both are the precondition for rich deploy-vs-runtime drift history; deferred to the customer-hosted inflection.
- **Raw FedRAMP KSI catalog browser.** The `ksi_theme` / `ksi_indicator` reference catalog is consumed (with status) by the KSI Scoreboard; its raw-listing home is the `/fedramp-ksi` page (intentionally hidden). Not reproduced under samsite.
- **Wayback-style emission timeline.** The sequence-nav is point-to-point; a calendar/timeline scrubber is future.
