# Samsite Compliance Artifact Viewer Pages — v0

## Philosophy

Samsite collects five published compliance artifacts off the live site and decomposes or stores them on the grid: the **KSI signal**, the **VDR report**, the **OSCAL SSP**, the **OSCAL POA&M**, and the **IIW inventory**. Today they are reachable only as rows in tables on `/samsite/compliance`. This spec gives each artifact type a **viewer page** — click a report's representation, land on a page that renders that artifact in a classy, human-legible format — plus a single **artifact inventory page** that indexes everything collected and links into the viewers.

The default load of a viewer shows the **latest** emission of that artifact type, resolved through the existing `tap_web.panels.entity_resolution` fallback (`ORDER BY <ts> DESC LIMIT 1`). A specific emission is deep-linkable by `entity_id` so a view is bookmarkable and stable across time.

**Two artifact families, two rendering strategies.** This split is the spine of the design:

- **Decomposed artifacts** (KSI signal, VDR report) were shredded into typed nodes + edges at collection time. Their viewers **recompose** the artifact from its graph nodes and *link out* to related entities — a KSI component whose `native_id` is an ARN links to the actual collected AWS resource; a VDR finding links to the existing `/samsite/finding/<id>` viewer. This is where TAP earns its keep over a raw JSON dump: the artifact becomes navigable in ways the publisher's static file is not.
- **Whole-blob artifacts** (OSCAL SSP, OSCAL POA&M, IIW) were kept whole in `compliance_artifact.content`. Their viewers render the blob faithfully. OSCAL SSP/POA&M reuse `roscale`'s existing `oscal_workbench` / `oscal_poam_workbench` renderers (a *deliberate* cross-plugin dependency — see Plugin Dependency); IIW renders its CSV as a table.

**Roadmap alignment.** This work supports `step-rampart-sam-demo` (`plan/road-rampart.md`, target 2026-06-01): it makes the collected compliance artifacts legible to a knowledgeable human, surfaces findings, and explains compliance status — Green-Flag work. **Version navigation across emissions (prev/next, history timeline, the `compliance_artifact` content-hash re-key) is explicitly out of v0 scope** (see Non-Goals); at demo time there is one emission per artifact and nothing to navigate, and that layer is already parked as a `tap_web` future seam.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Per-Type Viewers | Each of the five artifact types has a routable viewer page rendering that artifact in a human-legible format. |
| 2. | Latest By Default | A bare viewer URL renders the latest emission of that type via the entity-resolution fallback; no parameter required. |
| 3. | Deep-Linkable | `/samsite/<type>/<entity_id>` renders that specific emission, bookmarkable and stable. |
| 4. | Recompose + Link Out | Decomposed-artifact viewers (KSI, VDR) rebuild from graph nodes and link to related entities (AWS resource, per-finding viewer). |
| 5. | Faithful Blobs | Whole-blob viewers (OSCAL, IIW) render `compliance_artifact.content` faithfully; OSCAL reuses roscale's renderer. |
| 6. | Provenance + Disclosure Band | Every viewer shows a shared band: signature verification, signer identity, and the artifact's machine-readable disclosure flags — honoring `unknown ≠ false`. |
| 7. | Inventory Index | One page lists every collected artifact, grouped by type, each row linking to its viewer. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-samsite-viewer-routes | [Viewer Page Routes](#viewer-page-routes) | Proposed | Five parameterized pages; `discoverable:false`; latest-via-fallback config |
| req-samsite-viewer-ksi-signal | [KSI Signal Viewer](#ksi-signal-viewer) | Proposed | Recompose header + components + validations from nodes; ARN components link to AWS resource |
| req-samsite-viewer-vdr-report | [VDR Report Viewer](#vdr-report-viewer) | Proposed | Recompose summary + findings; findings link to existing finding viewer |
| req-samsite-viewer-oscal | [OSCAL SSP / POA&M Viewer](#oscal-ssp--poam-viewer) | Proposed | Reuse roscale's workbench renderers — declared cross-plugin dependency |
| req-samsite-viewer-iiw | [IIW Viewer](#iiw-viewer) | Proposed | Render CSV `content` as a table |
| req-samsite-viewer-provenance-band | [Provenance + Disclosure Band](#provenance--disclosure-band) | Proposed | Shared band across all five; disclosure pills; `unknown ≠ false` |
| req-samsite-artifact-inventory | [Artifact Inventory Page](#artifact-inventory-page) | Proposed | One table per type; rows link to viewers |
| req-samsite-viewer-plugin-dependency | [Plugin Dependency on roscale](#plugin-dependency-on-roscale) | Proposed | Narrowly-declared deliberate dependency on roscale's OSCAL renderers |

### Viewer Page Routes
----
RID: `req-samsite-viewer-routes`
Status: `Proposed`

Five parameterized pages, one per artifact type, following the existing `/samsite/finding/<uuid:entity_id>` precedent (Django URL pattern pins the entity context; the captured id is merged into query params; the page mounts a viewer panel). Each page is `discoverable: false` (nav surfaces don't link to a bare detail route; the inventory page and in-graph links are the entry points).

| Type | Page slug | Resolves entity | Renderer |
| --- | --- | --- | --- |
| KSI signal | `/samsite/ksi-signal` | `ksi_signal` | custom panel (recompose) |
| VDR report | `/samsite/vdr-report` | `vdr_report` | custom panel (recompose) |
| OSCAL SSP | `/samsite/oscal-ssp` | `compliance_artifact` (kind `oscal_ssp`) | roscale `oscal_workbench` |
| OSCAL POA&M | `/samsite/oscal-poam` | `compliance_artifact` (kind `oscal_poam`) | roscale `oscal_poam_workbench` |
| IIW | `/samsite/iiw` | `compliance_artifact` (kind `iiw`) | custom table panel |

Each viewer panel configures the entity-resolution helper: `entity_id_var` for the deep-link parameter, and a `fallback.query` selecting the latest emission. The blob types select by `kind` + latest `fetched_at`; the decomposed types select by latest `emitted_at`.

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
| req-samsite-viewer-routes-1 | Five Routes | Proposed | Five parameterized page routes exist, each pinning its entity context and merging the captured `entity_id` into query params. | Mirrors `parameterized_page_view` for `/samsite/finding`. |
| req-samsite-viewer-routes-2 | Latest Default | Proposed | A bare viewer URL renders the latest emission via the configured fallback; `used_fallback` is surfaced per the entity-resolution template contract. | |
| req-samsite-viewer-routes-3 | Deep Link Wins | Proposed | `/samsite/<type>/<entity_id>` renders that specific emission and never runs the fallback. | Per `req-web-panel-entity-resolution-order`. |
| req-samsite-viewer-routes-4 | Not Discoverable | Proposed | Each viewer page is `discoverable: false`; entry is via the inventory page or in-graph links, not nav. | |

### KSI Signal Viewer
----
RID: `req-samsite-viewer-ksi-signal`
Status: `Proposed`

A custom panel that recomposes the signal from its decomposed nodes:

- **Header** — `signal_id`, `emitted_at`, `emitter` (deploy vs runtime), `system_id`, `csp`, plus the provenance/disclosure band (`req-samsite-viewer-provenance-band`).
- **Components** — table of the signal's `ksi_component` nodes, grouped or filterable by `component_type`. Components carrying a `native_id` (ARN) link to the collected AWS resource node when one is on the grid; rows without a resolvable target render the identifier as plain text (no dead link).
- **Validations** — the signal's `ksi_validation` nodes with pass/fail styling and `component_refs` linked back to the components table. A violations sub-section renders `ksi_violation` nodes when present (empty is the expected current state and renders as an informational "no violations" note, not a blank).

The component → AWS-resource link is the headline graph payoff and SHOULD be present in v0; it is the single clearest "legible in ways the publisher's static file is not" affordance for the demo.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-ksi-signal-1 | Header Recomposed | Proposed | The panel renders the signal header fields from the resolved `ksi_signal` node. | |
| req-samsite-viewer-ksi-signal-2 | Components Listed | Proposed | The signal's components render as a grouped/filterable table sourced from `ksi_component` nodes via the signal's edges. | |
| req-samsite-viewer-ksi-signal-3 | ARN Links Out | Proposed | A component with a `native_id` ARN links to the collected AWS resource node when present; absent target → plain text, never a dead link. | |
| req-samsite-viewer-ksi-signal-4 | Validations + Violations | Proposed | Validations render with pass/fail styling; violations render when present and as an informational empty note when absent. | |

### VDR Report Viewer
----
RID: `req-samsite-viewer-vdr-report`
Status: `Proposed`

A custom panel that recomposes the report:

- **Header + summary** — `report_id`, `emitted_at`, and the `summary` rollup (counts, `kev_catalog_loaded`, `dependabot_alerts_loaded`) with the latter two surfaced as disclosure pills per the band.
- **Findings** — table of the report's `vdr_finding` nodes. KEV / blocking / overdue findings are visually emphasized. Each finding row links to the existing `/samsite/finding/<entity_id>` viewer (reuse — do not rebuild per-finding rendering).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-vdr-report-1 | Summary Rendered | Proposed | The panel renders the report header and `summary` rollup; coverage flags render as pills. | |
| req-samsite-viewer-vdr-report-2 | Findings Listed | Proposed | The report's findings render as a table sourced from `vdr_finding` nodes; KEV/blocking/overdue are emphasized. | |
| req-samsite-viewer-vdr-report-3 | Findings Link Out | Proposed | Each finding row links to the existing per-finding viewer page. | |

### OSCAL SSP / POA&M Viewer
----
RID: `req-samsite-viewer-oscal`
Status: `Proposed`

The SSP and POA&M viewers render the whole `compliance_artifact.content` blob by **reusing roscale's existing `oscal_workbench` and `oscal_poam_workbench` panels** rather than authoring a second OSCAL renderer. The samsite pages mount the roscale panel and configure its entity-resolution fallback to select the latest samsite-collected artifact of the matching `kind`. This reuse is a declared cross-plugin dependency (`req-samsite-viewer-plugin-dependency`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-oscal-1 | Reuse Not Reauthor | Proposed | The OSCAL SSP and POA&M viewers render via roscale's renderers; samsite does not implement its own OSCAL rendering. | |
| req-samsite-viewer-oscal-2 | Samsite Artifact Selected | Proposed | The fallback query selects samsite-collected `compliance_artifact` nodes of the matching `kind`, latest by `fetched_at`. | |

### IIW Viewer
----
RID: `req-samsite-viewer-iiw`
Status: `Proposed`

A custom panel rendering the IIW CSV held in `compliance_artifact.content` as a table, with the provenance/disclosure band above it.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-iiw-1 | CSV As Table | Proposed | The panel renders the IIW CSV content as a tabular view. | |

### Provenance + Disclosure Band
----
RID: `req-samsite-viewer-provenance-band`
Status: `Proposed`

A shared band rendered at the top of every viewer, sourced from the resolved node's stored fields:

- **Provenance** — `signature_verified` (a clear ✓/✗), `signed_by` (the signer identity), and the source URL the artifact was fetched from. Where the node carries Sigstore/Rekor attestation, surface the link.
- **Disclosure** — the artifact's machine-readable disclosure flags rendered as pills (for KSI: `fedramp_certified`, `authorization_status`). A `false` flag renders as an explicit ✗ pill; a flag that is **absent** (predates the field) renders as an `unknown` pill, never as ✗ or as a silent omission. This completes the producer→consumer disclosure loop: the panel refuses to let "absence" read as "compliant."

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-provenance-band-1 | Verification Shown | Proposed | Every viewer shows `signature_verified` and `signed_by` for the resolved artifact. | |
| req-samsite-viewer-provenance-band-2 | Disclosure Pills | Proposed | Disclosure flags render as pills; `false` is an explicit ✗. | |
| req-samsite-viewer-provenance-band-3 | Unknown Is Not False | Proposed | An absent disclosure flag renders as `unknown`, distinct from an explicit `false`, and never as a silent omission. | |

### Artifact Inventory Page
----
RID: `req-samsite-artifact-inventory`
Status: `Proposed`

A single discoverable page, `/samsite/artifacts`, that indexes everything collected. One table panel per artifact type (KSI signals, VDR reports, OSCAL SSPs, OSCAL POA&Ms, IIWs); each row shows the emission/fetch timestamp, the artifact's natural id, and `signature_verified`, and links to that artifact's viewer page (the existing finding-table → finding-viewer row-link mechanism is the precedent). This is the quick-and-dirty inventory and doubles as the primary launch surface into the viewers.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-artifact-inventory-1 | One Table Per Type | Proposed | The page renders one table per artifact type listing all collected emissions of that type, newest first. | |
| req-samsite-artifact-inventory-2 | Rows Link To Viewers | Proposed | Each row links to its artifact's viewer page via the parameterized deep-link route. | |
| req-samsite-artifact-inventory-3 | Discoverable | Proposed | The inventory page is discoverable in nav; the viewer pages it links to remain non-discoverable. | |

### Plugin Dependency on roscale
----
RID: `req-samsite-viewer-plugin-dependency`
Status: `Proposed`

The OSCAL viewers depend on roscale's `oscal_workbench` and `oscal_poam_workbench` panels. This is a **deliberate, intended cross-plugin dependency** — the legitimate kind under the hermetic rule's coincidental-vs-deliberate axis (`req-tap-test-hermetic-plugins`, "Future" section; mirrored in `AGENTS.md` and agent memory): the page/panel architecture exists precisely so one plugin can publish a reusable panel and another can mount it.

Until the backlogged plugin-dependency model exists, this dependency is declared narrowly **here**, naming exactly what is relied upon: the two roscale panel slugs and their entity-resolution config contract (a panel that resolves one `compliance_artifact` and renders its OSCAL `content`). The dependency must NOT reach into roscale's templates, fixtures, or internals beyond mounting the registered panel and configuring its public config.

**Open decision (resolve during implementation):** either (a) **lift** the OSCAL renderer to a shared home (`tap_web` or a shared compliance app) so both roscale and samsite consume it as a peer — preferred, since OSCAL rendering is not roscale-specific — or (b) keep it in roscale and have samsite mount it as a declared dependency. Pick (a) if the lift is cheap; otherwise (b) with this declaration. Either way, no reach-in.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-viewer-plugin-dependency-1 | Dependency Declared | Proposed | Samsite's spec names the roscale panels relied upon and the config contract; the dependency is not implicit. | |
| req-samsite-viewer-plugin-dependency-2 | No Reach-In | Proposed | Samsite mounts the registered roscale panel and configures its public config only; it does not reference roscale templates/fixtures/internals. | |

## Non-Goals (v0)

Explicitly deferred — named so the deferral is a decision, not an omission:

- **Version navigation (prev/next across emissions).** Deferred to a `tap_web` sequence-navigator primitive, which graduates the already-named "History timeline panel" future seam in `spec-web-panel-entity-resolution-v0.md`. At demo time there is one emission per artifact; the feature has no data to act on yet.
- **`compliance_artifact` content-hash re-key.** Re-keying identity from `kind/fetched_at` to `kind/<content-sha256>` (so genuine versions accumulate and pure re-fetches upsert) is the precondition for meaningful blob-type history. It is an identity change to every artifact node and is deferred until the history layer is built.
- **Wayback-style history/timeline visualization.** The motivating long-term vision for the above; not v0.
- **In-graph clickable artifact nodes on the `/samsite` landing graph** as a second entry point. The inventory page is the v0 launch surface.

## Rollout Priority

If demo time is tight, build in this order — each step is independently shippable and demo-legible:

1. **Inventory page** (`/samsite/artifacts`) — cheapest; reuses existing table panels, adds row-links.
2. **KSI signal viewer** — headline FedRAMP artifact; the ARN→AWS link-out is the strongest demo moment.
3. **VDR report viewer** — findings legibility; reuses the existing per-finding viewer.
4. **OSCAL SSP + POA&M viewers** — cheap via roscale reuse once the dependency decision is made.
5. **IIW viewer** — lowest narrative weight.
