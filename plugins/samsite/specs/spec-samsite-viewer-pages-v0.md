# Samsite Compliance Artifact Viewer Pages — v0

## Philosophy

Samsite collects compliance artifacts off the live site and decomposes or stores them on the grid: the **KSI signal** (decomposed into signal + components + validations + violations), the **VDR report** (decomposed into report + findings), and three **whole-blob `compliance_artifact`s** — OSCAL SSP, OSCAL POA&M, and the IIW inventory. This spec gives each top-level artifact type a **classy viewer page** — click a report's representation, land on a page that renders it in a human-legible format — plus a single **artifact inventory page** that indexes everything collected and clicks through to the viewers.

**This work replaces the universal-viewer placeholder.** `per-type-viewers.grift.json` already routes `/samsite/{signal,artifact,finding,indicator,component}` through the generic `viewer_panel` (a field-dump), explicitly staged as "v0 uses the universal viewer_panel… per-type custom panels follow." This spec *is* that follow: it upgrades the artifact routes to custom panels and adds the one missing top-level viewer (VDR report). The existing slugs and the `PER_TYPE_DETAIL_URL` row-navigation map are kept; only the panel mounted in each page changes.

**Two artifact families, two rendering strategies** — the spine of the design:

- **Decomposed artifacts** (KSI signal, VDR report) were shredded into typed nodes + edges at collection time. Their viewers **recompose** the artifact from its graph nodes and *link out* to related entities — a KSI component whose `native_id` is an ARN links to the actual collected AWS resource node; a VDR finding links to the existing `/samsite/finding/<id>` viewer. This is where TAP earns its keep over a raw JSON dump: the artifact becomes navigable in ways the publisher's static file is not.
- **Whole-blob artifacts** live in `compliance_artifact.content`. A single `/samsite/artifact` viewer **branches by `kind`**: OSCAL SSP/POA&M render via `roscale`'s existing workbench renderers (a deliberate cross-plugin dependency — see Plugin Dependency); IIW renders its CSV as a table.

**Roadmap alignment.** Supports `step-rampart-sam-demo` (`plan/road-rampart.md`, target 2026-06-01): makes the collected compliance artifacts legible, surfaces findings, explains compliance status — Green-Flag work. **Version navigation across emissions (prev/next, history timeline, the `compliance_artifact` content-hash re-key) is explicitly out of v0 scope** (see Non-Goals); at demo time there is one emission per artifact, and that layer is already parked as a `tap_web` future seam.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Classy Per-Type Viewers | The KSI signal, VDR report, and compliance-artifact viewers render in a human-legible format, replacing the universal field-dump. |
| 2. | Latest By Default | A bare viewer URL renders the latest emission via the entity-resolution fallback; no parameter required. |
| 3. | Deep-Linkable | `/samsite/<type>/<entity_id>` renders that specific emission, bookmarkable and stable. |
| 4. | Recompose + Link Out | Decomposed-artifact viewers (KSI, VDR) rebuild from graph nodes and link to related entities (AWS resource, per-finding viewer). |
| 5. | Faithful Blobs, One Route | A single `/samsite/artifact` viewer branches by `kind`: OSCAL via roscale's renderer, IIW as a table. |
| 6. | Provenance + Disclosure Band | Every viewer shows a shared band: signature verification, signer identity, and the artifact's machine-readable disclosure flags — honoring `unknown ≠ false`. |
| 7. | Inventory Index | One page lists every collected artifact, grouped by type, each row clicking through to its viewer via the existing per-type row-nav map. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-samsite-viewer-routes | [Viewer Page Routes](#viewer-page-routes) | Proposed | Reuse `/samsite/signal` + `/samsite/artifact`; add `/samsite/vdr-report`; replace universal viewer_panel with custom panels; latest-via-fallback |
| req-samsite-viewer-ksi-signal | [KSI Signal Viewer](#ksi-signal-viewer) | Proposed | `/samsite/signal` — recompose header + components + validations; ARN components link to AWS resource |
| req-samsite-viewer-vdr-report | [VDR Report Viewer](#vdr-report-viewer) | Proposed | `/samsite/vdr-report` (new) — recompose summary + findings; findings link to finding viewer; add `vdr_report` to the row-nav map |
| req-samsite-viewer-artifact | [Compliance Artifact Viewer](#compliance-artifact-viewer) | Proposed | `/samsite/artifact` — branch by `kind`: OSCAL via roscale reuse, IIW as table |
| req-samsite-viewer-provenance-band | [Provenance + Disclosure Band](#provenance--disclosure-band) | Proposed | Shared band across all viewers; disclosure pills; `unknown ≠ false` |
| req-samsite-artifact-inventory | [Artifact Inventory Page](#artifact-inventory-page) | Implemented | `/samsite/artifacts` — reuse existing compliance table panels; row-nav via `PER_TYPE_DETAIL_URL` |
| req-samsite-viewer-plugin-dependency | [Plugin Dependency on roscale](#plugin-dependency-on-roscale) | Proposed | Narrowly-declared deliberate dependency on roscale's OSCAL renderers |
| req-samsite-viewer-row-nav-coupling | [Row-Nav Map Coupling](#row-nav-map-coupling) | Proposed | The `tap_web` `PER_TYPE_DETAIL_URL` map hardcodes samsite routes — acknowledged debt |

### Viewer Page Routes
----
RID: `req-samsite-viewer-routes`
Status: `Proposed`

Three top-level artifact viewers, built on the existing parameterized-page machinery (`parameterized_page_view` pins `entity_type`; the captured id is merged into query params; the page mounts a viewer panel). Two reuse existing routes; one is new.

| Type | Page slug | Pinned entity_type | Status of route | Renderer (this spec) |
| --- | --- | --- | --- | --- |
| KSI signal | `/samsite/signal` | `ksi_signal` | exists (universal) | custom recompose panel |
| VDR report | `/samsite/vdr-report` | `vdr_report` | **new** | custom recompose panel |
| Compliance artifact | `/samsite/artifact` | `compliance_artifact` | exists (universal) | custom panel, branches by `kind` |

The existing `/samsite/{finding,indicator,component}` routes (sub-entity viewers) are adjacent and out of this spec's scope; the VDR report viewer links to `/samsite/finding`. The new `/samsite/vdr-report` route needs a URL pattern in `tap_web/urls.py` pinning `vdr_report`, mirroring the existing four.

Each viewer panel configures the `tap_web.panels.entity_resolution` helper: `entity_id_var` for the deep-link parameter, and a `fallback.query` selecting the latest emission (decomposed types by `emitted_at`, the artifact viewer by `kind` + latest `fetched_at`).

Example fallback config (KSI signal viewer):

```json
{
  "entity_id_var": "ksi_signal_entity_id",
  "fallback": {
    "query": "MATCH (s:ksi_signal) WHERE s.data.emitted_at IS NOT NULL ORDER BY s.data.emitted_at DESC LIMIT 1",
    "description": "Latest ksi_signal emission by emitted_at."
  }
}
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-routes-1 | Routes Resolve | Proposed | `/samsite/signal`, `/samsite/vdr-report`, `/samsite/artifact` each resolve, pinning their entity_type and merging the captured `entity_id` into query params. | `/samsite/vdr-report` is a new `urls.py` pattern. |
| req-samsite-viewer-routes-2 | Custom Not Universal | Proposed | Each route mounts its custom panel, not the generic `viewer_panel`. | Replaces the placeholder per-type-viewer pages for these three types. |
| req-samsite-viewer-routes-3 | Latest Default | Proposed | A bare viewer URL renders the latest emission via the configured fallback; `used_fallback` is surfaced per the entity-resolution template contract. | |
| req-samsite-viewer-routes-4 | Deep Link Wins | Proposed | `/samsite/<type>/<entity_id>` renders that specific emission and never runs the fallback. | Per `req-web-panel-entity-resolution-order`. |

### KSI Signal Viewer
----
RID: `req-samsite-viewer-ksi-signal`
Status: `Proposed`

A custom panel at `/samsite/signal` that recomposes the signal from its decomposed nodes:

- **Header** — `signal_id`, `emitted_at`, `emitter` (deploy vs runtime), `system_id`, `csp`, plus the provenance/disclosure band.
- **Components** — table of the signal's `ksi_component` nodes, grouped or filterable by `component_type`. Components carrying a `native_id` (ARN) link to the collected AWS resource node when one is on the grid; rows without a resolvable target render the identifier as plain text (no dead link).
- **Validations** — the signal's `ksi_validation` nodes with pass/fail styling and `component_refs` linked back to the components table. A violations sub-section renders `ksi_violation` nodes when present (empty renders as an informational "no violations" note, not a blank).

The component → AWS-resource link is the headline graph payoff and SHOULD be present in v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-ksi-signal-1 | Header Recomposed | Proposed | The panel renders the signal header from the resolved `ksi_signal` node. | |
| req-samsite-viewer-ksi-signal-2 | Components Listed | Proposed | The signal's components render as a grouped/filterable table sourced from `ksi_component` nodes via the signal's edges. | |
| req-samsite-viewer-ksi-signal-3 | ARN Links Out | Proposed | A component with a `native_id` ARN links to the collected AWS resource node when present; absent target → plain text, never a dead link. | |
| req-samsite-viewer-ksi-signal-4 | Validations + Violations | Proposed | Validations render with pass/fail styling; violations render when present and as an informational empty note when absent. | |

### VDR Report Viewer
----
RID: `req-samsite-viewer-vdr-report`
Status: `Proposed`

A new route `/samsite/vdr-report` with a custom panel that recomposes the report:

- **Header + summary** — `report_id`, `emitted_at`, and the `summary` rollup (counts, `kev_catalog_loaded`, `dependabot_alerts_loaded`) with the latter two surfaced as disclosure pills.
- **Findings** — table of the report's `vdr_finding` nodes. KEV / blocking / overdue findings are visually emphasized. Each finding row links to the existing `/samsite/finding/<entity_id>` viewer (reuse — do not rebuild per-finding rendering).

The `vdr_report` entity type MUST be added to the `PER_TYPE_DETAIL_URL` map in `panel-table.js` (`vdr_report → /samsite/vdr-report/<id>`) so inventory and compliance-landing table rows click through here.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-vdr-report-1 | Route + Panel | Proposed | A new `/samsite/vdr-report` route mounts the custom VDR report panel. | |
| req-samsite-viewer-vdr-report-2 | Summary Rendered | Proposed | The panel renders the report header and `summary` rollup; coverage flags render as pills. | |
| req-samsite-viewer-vdr-report-3 | Findings Link Out | Proposed | The report's findings render as a table; each row links to the existing per-finding viewer. | |
| req-samsite-viewer-vdr-report-4 | Row-Nav Entry Added | Proposed | `vdr_report` is added to `PER_TYPE_DETAIL_URL`; table rows of `vdr_report` navigate to `/samsite/vdr-report/<id>`. | |

### Compliance Artifact Viewer
----
RID: `req-samsite-viewer-artifact`
Status: `Proposed`

A single custom panel at `/samsite/artifact` that resolves one `compliance_artifact` and **branches on `kind`**:

- `oscal_ssp` → render via roscale's `oscal_workbench` renderer.
- `oscal_poam` → render via roscale's `oscal_poam_workbench` renderer.
- `iiw` → render the CSV `content` as a table.

All three sit above the shared provenance/disclosure band. OSCAL rendering reuses roscale rather than reauthoring (`req-samsite-viewer-plugin-dependency`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-artifact-1 | Branch By Kind | Proposed | The panel selects its renderer from the resolved artifact's `kind`. | |
| req-samsite-viewer-artifact-2 | OSCAL Reuse | Proposed | `oscal_ssp` / `oscal_poam` render via roscale's renderers; samsite does not reauthor OSCAL rendering. | |
| req-samsite-viewer-artifact-3 | IIW As Table | Proposed | `iiw` renders its CSV `content` as a tabular view. | |

### Provenance + Disclosure Band
----
RID: `req-samsite-viewer-provenance-band`
Status: `Proposed`

A shared band at the top of every viewer, sourced from the resolved node's stored fields:

- **Provenance** — `signature_verified` (a clear ✓/✗), `signed_by` (signer identity), the source URL fetched from, and the Sigstore/Rekor attestation link where present.
- **Disclosure** — machine-readable disclosure flags as pills (for KSI: `fedramp_certified`, `authorization_status`). A `false` flag renders as an explicit ✗ pill; an **absent** flag (predates the field) renders as an `unknown` pill, never as ✗ or as a silent omission. This completes the producer→consumer disclosure loop: the panel refuses to let "absence" read as "compliant."

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-provenance-band-1 | Verification Shown | Proposed | Every viewer shows `signature_verified` and `signed_by` for the resolved artifact. | |
| req-samsite-viewer-provenance-band-2 | Disclosure Pills | Proposed | Disclosure flags render as pills; `false` is an explicit ✗. | |
| req-samsite-viewer-provenance-band-3 | Unknown Is Not False | Proposed | An absent disclosure flag renders as `unknown`, distinct from explicit `false`, never as a silent omission. | |

### Artifact Inventory Page
----
RID: `req-samsite-artifact-inventory`
Status: `Implemented`

A single discoverable page, `/samsite/artifacts`, that indexes everything collected. It **reuses the existing compliance table panel instances** (no new panels): `samsite-compliance-ksi-signals`, `samsite-compliance-vdr-reports`, and `samsite-compliance-artifacts`, mounted in narrative order. Panels are movable subjects — the same instances render on `/samsite/compliance` and here.

Row click-through is free: node-mode table rows navigate via the `PER_TYPE_DETAIL_URL` map. `ksi_signal → /samsite/signal/<id>` and `compliance_artifact → /samsite/artifact/<id>` are already mapped; `vdr_report` is added by `req-samsite-viewer-vdr-report`. Until that entry lands, `vdr_report` rows fall through to the generic `/object/` viewer (degrades, does not break).

This is the quick-and-dirty inventory and the primary launch surface into the viewers.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-artifact-inventory-1 | Reuses Existing Panels | Implemented | The page mounts the three existing compliance table panel instances via `USES_PANEL`; it does not author new panels. | `artifacts-inventory-page.grift.json` — 3 `USES_PANEL` edges to the existing `samsite-compliance-{ksi-signals,vdr-reports,artifacts}` instances. |
| req-samsite-artifact-inventory-2 | Rows Click Through | Implemented | Node-mode rows navigate to the per-type viewer via `PER_TYPE_DETAIL_URL` (or the generic `/object/` route for unmapped types). | Verified: KSI-signal row → `/samsite/signal/<id>`. `vdr_report` still falls through to `/object/` until `req-samsite-viewer-vdr-report` lands. |
| req-samsite-artifact-inventory-3 | Discoverable | Implemented | The inventory page is discoverable in nav; the viewer pages it links to remain non-discoverable. | |

### Plugin Dependency on roscale
----
RID: `req-samsite-viewer-plugin-dependency`
Status: `Proposed`

The artifact viewer's OSCAL branch depends on roscale's `oscal_workbench` and `oscal_poam_workbench` renderers. This is a **deliberate, intended cross-plugin dependency** — the legitimate kind under the hermetic rule's coincidental-vs-deliberate axis (`req-tap-test-hermetic-plugins`, "Future" section; mirrored in `AGENTS.md` and agent memory): the page/panel architecture exists precisely so one plugin can publish a reusable renderer and another can consume it.

Until the backlogged plugin-dependency model exists, this dependency is declared narrowly **here**, naming what is relied upon: the two roscale renderers and their entity-resolution config contract (resolve one `compliance_artifact`, render its OSCAL `content`). No reach-in to roscale templates/fixtures/internals beyond the public renderer.

**Open decision (resolve during implementation):** either (a) **lift** the OSCAL renderer to a shared home (`tap_web` or a shared compliance app) so roscale and samsite consume it as peers — preferred, since OSCAL rendering is not roscale-specific — or (b) keep it in roscale and consume it as a declared dependency.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-plugin-dependency-1 | Dependency Declared | Proposed | Samsite's spec names the roscale renderers relied upon and the config contract; the dependency is not implicit. | |
| req-samsite-viewer-plugin-dependency-2 | No Reach-In | Proposed | Samsite consumes the public renderer only; it does not reference roscale templates/fixtures/internals. | |

### Row-Nav Map Coupling
----
RID: `req-samsite-viewer-row-nav-coupling`
Status: `Proposed`

The per-type row-navigation override lives in a hardcoded `PER_TYPE_DETAIL_URL` map in `tap_web/static/tap_web/js/panel-table.js`, which already names samsite routes (`vdr_finding`, `ksi_indicator`, `ksi_component`, `ksi_signal`, `compliance_artifact`). This is core `tap_web` JS coupled to a specific plugin's URLs — its own in-code comment flags it: *"Coupling lives in the URL map for now; a per-plugin registration mechanism would lift this."*

This spec adds one entry (`vdr_report`) and records the coupling as **acknowledged debt on the same backlog as the plugin-dependency model** (`req-tap-test-hermetic-plugins` Future): a plugin should register its per-type detail routes rather than core JS hardcoding them. Not fixed in v0; named so the debt is visible and lifted with the dependency model, not piecemeal.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-row-nav-coupling-1 | Debt Recorded | Proposed | The hardcoded map's plugin coupling is documented here and linked to the plugin-dependency backlog. | |

## Non-Goals (v0)

Explicitly deferred — named so the deferral is a decision, not an omission:

- ~~**Version navigation (prev/next across emissions).**~~ **Built** — the `tap_web` sequence-navigator panel (`spec-web-panel-sequence-navigation-v0.md`) is mounted above the OSCAL SSP (`/samsite/compliance/ssp`) and POA&M (`/samsite/compliance/poam`) workbenches, walking their `compliance_artifact` emissions newest-first. The KSI signal and VDR report viewers get the same panel when those custom viewers are built. (Caveat: `ksi_signal`/`vdr_report` accumulate only on genuine new emissions; rich history for them awaits runtime-signal collection — below.)
- **`compliance_artifact` content-hash re-key.** Re-keying identity from `kind/fetched_at` to `kind/<content-sha256>` (so genuine versions accumulate and pure re-fetches upsert) is the precondition for meaningful blob-type history. An identity change to every artifact node; deferred until the history layer is built.
- **Wayback-style history/timeline visualization.** The motivating long-term vision for the above; not v0.
- **Lifting the `PER_TYPE_DETAIL_URL` map to a plugin-registration mechanism.** Recorded as debt (`req-samsite-viewer-row-nav-coupling`); lifted with the plugin-dependency model.
- **Upgrading the `/samsite/{finding,indicator,component}` sub-entity viewers** from the universal viewer_panel. Out of this spec's scope.
- **In-graph clickable artifact nodes on the `/samsite` landing graph** as a second entry point. The inventory page is the v0 launch surface.

## Rollout Priority

If demo time is tight, build in this order — each step is independently shippable and demo-legible:

1. **Inventory page** (`/samsite/artifacts`) — cheapest; reuses the three existing table panels, rows already click through.
2. **KSI signal viewer** — headline FedRAMP artifact; the ARN→AWS link-out is the strongest demo moment.
3. **VDR report viewer** — findings legibility; reuses the per-finding viewer; adds the `vdr_report` row-nav entry.
4. **Compliance artifact viewer** — OSCAL via roscale reuse (after the lift-vs-declare call) + IIW table.
