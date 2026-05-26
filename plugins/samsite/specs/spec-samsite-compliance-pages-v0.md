# Samsite Compliance Pages Specification

## Philosophy

Samsite is the first consumer of the [`roscale`](../../roscale/specs/spec-roscale-v0.md) plugin's OSCAL workbench panels. This spec defines the **page-and-panel wiring** the samsite plugin contributes so the OSCAL SSP and POA&M documents collected by [`spec-samsite-compliance-collector-v0.md`](spec-samsite-compliance-collector-v0.md) become readable inside TAP Web.

The split is the same ingest-vs-consume decomposition the collector spec already establishes:

- **Collector spec** — how Samsite's OSCAL artifacts get *onto* the grid (daily fetch, signature verify, GRIFT submit). Owns the artifact nodes.
- **Pages spec (this one)** — how those artifact nodes get *rendered* into a Samsite-branded compliance area of TAP Web. Owns the page routes, the panel instances, and the page-variable bindings.
- **ROSCALE plugin** — owns the panel implementations, templates, parser, and validator that the pages here use. Knows nothing about Samsite specifically.

Samsite chose two sibling pages rather than a single combined page because the SSP and POA&M tell different stories (system security plan vs. action/risk register), and the corresponding ROSCALE panel types are distinct. Cramming both into one page would compromise both readings.

## Goals

|   | Goal | Description |
| :---: | --- | --- |
| 1. | SSP Readable | An authenticated user navigating to `/samsite/compliance/oscal` sees Samsite's current OSCAL SSP rendered via the `roscale-oscal-workbench` panel. |
| 2. | POA&M Readable | An authenticated user navigating to `/samsite/compliance/poam` sees Samsite's current OSCAL POA&M rendered via the `roscale-oscal-poam-workbench` panel. |
| 3. | URL-Backed Selection | Both pages take the artifact entity id through a URL-backed page variable so a deep link reproduces exactly what the user saw. |
| 4. | Discoverable From Samsite | The pages are reachable from Samsite's existing navigation, not orphan URLs only known by spec. |
| 5. | No Implementation Code | Samsite contributes GRIFT page/panel instances only; all rendering code lives in ROSCALE. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-samsite-pages-ssp | [SSP Page](#ssp-page) | Implemented | `/samsite/compliance/oscal` hosting `roscale-oscal-workbench`. Declared in `grift/compliance-pages.grift.json` batch v0.1.0; end-to-end verification pending |
| req-samsite-pages-poam | [POA&M Page](#poam-page) | Implemented | `/samsite/compliance/poam` hosting `roscale-oscal-poam-workbench`. Same batch as above; end-to-end verification pending |
| req-samsite-pages-vars | [URL-Backed Page Variables](#url-backed-page-variables) | Implemented | Both panels' configs name the respective `*_artifact_entity_id` page variable. Formal `tap_page_vars` / `variable_map` declaration is future work tracked by the in-progress `req-web-page-params` in `tap_web/specs/spec-web-page.md` |
| req-samsite-pages-discovery | [Navigation Discoverability](#navigation-discoverability) | Implemented | Nav-link cards added to the top of `/samsite/compliance` in `grift/compliance-landing.grift.json` batch v0.2.0; ROSCALE's `req-roscale-input-5` fallback satisfies the prefilled-link concern automatically (bare URLs resolve to latest). |
| req-samsite-pages-no-code | [No Rendering Code In Samsite](#no-rendering-code-in-samsite) | Implemented | Verified by inspection: samsite plugin contributes GRIFT only; no OSCAL-aware Python or templates |
| req-samsite-pages-grift | [GRIFT Layout](#grift-layout) | Implemented | `grift/compliance-pages.grift.json`; declared in `tap-plugin.toml` `[grift]`; passes `grift-document.schema.json` validation |

### SSP Page
----
RID: `req-samsite-pages-ssp`
Status: `Implemented`

Samsite contributes a GRIFT page at the route `/samsite/compliance/oscal`. The page hosts a single panel instance with `panel_type_slug = "roscale-oscal-workbench"` (provided by the ROSCALE plugin). The panel's config names the SSP page variable; defaults from ROSCALE apply when the config doesn't override.

Source artifact: the OSCAL SSP fetched by the [samsite compliance collector](spec-samsite-compliance-collector-v0.md) from `/.well-known/oscal-ssp.json` on the public site and stored as a `fedramp_20x_ksi.compliance_artifact` node with `kind = "oscal_ssp"`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-pages-ssp-1 | Page Route | Implemented | A GRIFT page exists with route `/samsite/compliance/oscal`. | `grift/compliance-pages.grift.json` → page `019e6505-7081-7358-a3bc-4ac58251ba53` |
| req-samsite-pages-ssp-2 | Panel Instance | Implemented | The page contains a single Panel node referencing panel type `roscale-oscal-workbench`. | Panel `019e6505-7081-7358-a3bc-4ac656f47390` with `slug = "roscale-oscal-workbench"`; USES_PANEL edge `019e6505-7081-7358-a3bc-4ac774e2d488` |
| req-samsite-pages-ssp-3 | Source Compatibility | Proposed | The panel renders the on-grid `compliance_artifact` node where `kind = "oscal_ssp"` when its entity id is bound to the page variable. | Wiring in place; end-to-end verification pending a real Samsite collector run + browser-load |

### POA&M Page
----
RID: `req-samsite-pages-poam`
Status: `Implemented`

Samsite contributes a GRIFT page at the route `/samsite/compliance/poam`. The page hosts a single panel instance with `panel_type_slug = "roscale-oscal-poam-workbench"`. The panel's config names the POA&M page variable; defaults from ROSCALE apply when the config doesn't override.

Source artifact: the OSCAL POA&M fetched by the samsite compliance collector from `/.well-known/oscal-poam.json` and stored as a `fedramp_20x_ksi.compliance_artifact` node with `kind = "oscal_poam"`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-pages-poam-1 | Page Route | Implemented | A GRIFT page exists with route `/samsite/compliance/poam`. | `grift/compliance-pages.grift.json` → page `019e6505-7081-7358-a3bc-4ac800a2e1cc` |
| req-samsite-pages-poam-2 | Panel Instance | Implemented | The page contains a single Panel node referencing panel type `roscale-oscal-poam-workbench`. | Panel `019e6505-7081-7358-a3bc-4ac9b955c104` with `slug = "roscale-oscal-poam-workbench"`; USES_PANEL edge `019e6505-7081-7358-a3bc-4aca70d3c3f7` |
| req-samsite-pages-poam-3 | Source Compatibility | Proposed | The panel renders the on-grid `compliance_artifact` node where `kind = "oscal_poam"` when its entity id is bound to the page variable. | Wiring in place; end-to-end verification pending |

### URL-Backed Page Variables
----
RID: `req-samsite-pages-vars`
Status: `Implemented`

Both pages expose a single URL-backed page variable per the TAP Web page-variable spec:

- SSP page: `oscal_ssp_artifact_entity_id`
- POA&M page: `oscal_poam_artifact_entity_id`

The variable values are the `entity_id` of the corresponding `compliance_artifact` node. A deep link of the form `/samsite/compliance/oscal?oscal_ssp_artifact_entity_id=<entity_id>` is the canonical bookmark for the SSP workbench; same shape for POA&M.

These names match ROSCALE's defaults (the panel resolves them with no extra config) but they are *Samsite's* page-variable names — ROSCALE accepts any name a consumer configures via `artifact_entity_id_var`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-pages-vars-1 | SSP Variable Wired | Implemented | The `/samsite/compliance/oscal` page declares URL-backed page variable `oscal_ssp_artifact_entity_id`. | Panel config `{"artifact_entity_id_var": "oscal_ssp_artifact_entity_id"}` in the SSP workbench panel node. ROSCALE reads it via `request.GET[var_name]`; the formal `tap_page_vars` / `USES_PANEL.variable_map` declaration is future work pending `req-web-page-params` |
| req-samsite-pages-vars-2 | POA&M Variable Wired | Implemented | The `/samsite/compliance/poam` page declares URL-backed page variable `oscal_poam_artifact_entity_id`. | Same pattern as SSP; panel config in the POA&M workbench panel node |
| req-samsite-pages-vars-3 | Deep Link Reproducible | Proposed | Reloading the URL with the same `entity_id` reproduces the same workbench view. | End-to-end verification pending |

### Navigation Discoverability
----
RID: `req-samsite-pages-discovery`
Status: `Implemented`

The two compliance pages must be reachable from Samsite's existing navigation surface (e.g. the Samsite landing page or a compliance-area link), not URL-only routes. v0 minimum: a link or card from a Samsite page already in the navigation graph that points at each compliance page.

**Prefilled-link mechanism note.** Originally this requirement called for the discovery link to *prefill* the latest artifact entity id. That work is now handled at the panel level: ROSCALE's `req-roscale-input-5` (latest-emission fallback) lets the bare URL `/samsite/compliance/oscal` resolve to the latest emission automatically when no query string is present. So the discovery link is just the bare URL — no GRIFT-level lookup or query widget required. The remaining work for this requirement is the navigation-link contribution itself (ACID-1).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-pages-discovery-1 | Reachable From Samsite | Implemented | A user starting on a Samsite page in the existing navigation can reach the SSP and POA&M workbench pages in one click each. | Nav-link cards on `/samsite/compliance` (an existing navigable page) point at both workbench pages. Cards rendered by the new `samsite-nav-links` panel type (single static-link-card renderer in `plugins/samsite/panels/nav_links/`); panel instance + page layout update shipped in `grift/compliance-landing.grift.json` batch v0.2.0 |
| req-samsite-pages-discovery-2 | Prefilled Link | Implemented | The discovery link points at a URL that resolves the most-recently-collected document of that kind. | Satisfied by ROSCALE's panel-level `req-roscale-input-5` fallback: the bare URL `/samsite/compliance/oscal` (no query string) resolves to the latest emission. No prefilling logic needed in Samsite |

### No Rendering Code In Samsite
----
RID: `req-samsite-pages-no-code`
Status: `Implemented`

Samsite must not ship any OSCAL parser, validator, panel type, template, or static asset for these pages. All rendering code lives in the ROSCALE plugin. If Samsite ever needs to deviate (e.g. a Samsite-flavored OSCAL section the workbench doesn't render), the right move is to extend ROSCALE rather than fork rendering into Samsite — file a ROSCALE change request.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-pages-no-code-1 | GRIFT-Only Contribution | Implemented | Samsite's contribution to these pages is GRIFT files; no Python code or templates in `plugins/samsite/` is OSCAL-aware. | Verified by inspection: only `grift/compliance-pages.grift.json` references these routes |
| req-samsite-pages-no-code-2 | No Sibling Panel Types | Implemented | Samsite does not register an OSCAL-workbench-like panel type of its own. | Samsite's `apps.py` registers no OSCAL-related panel types; the GRIFT panels point at ROSCALE's registered slugs |

### GRIFT Layout
----
RID: `req-samsite-pages-grift`
Status: `Implemented`

The GRIFT files for these pages live under `plugins/samsite/grift/` per the existing convention. File naming should clearly indicate scope (e.g. `compliance-pages-ssp.grift.json`, `compliance-pages-poam.grift.json`, or a combined `compliance-pages.grift.json` — pick one convention and apply consistently).

Each GRIFT batch is declared in the samsite plugin manifest (`tap-plugin.toml` `[grift]` table) so it's auto-imported on plugin load per the existing TAP convention.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-pages-grift-1 | Under grift/ | Implemented | GRIFT files live under `plugins/samsite/grift/`. | `grift/compliance-pages.grift.json` |
| req-samsite-pages-grift-2 | Declared In Manifest | Implemented | GRIFT batches are listed in `plugins/samsite/tap-plugin.toml` `[grift]`. | Entry `compliance-pages = "grift/compliance-pages.grift.json"` |
| req-samsite-pages-grift-3 | Schema-Valid | Implemented | GRIFT batches validate against `tap_grid/schemas/grift-document.schema.json`. | Verified: `jsonschema.validate(doc, schema)` passes |
