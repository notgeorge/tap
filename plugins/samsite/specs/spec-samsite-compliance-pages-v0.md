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

## Known Issues

### KI-1: `compliance-landing.grift.json` fails on fresh-DB spawn (batch-ordering bug)

Status: **Open** — flagged 2026-05-27. Fix deferred pending the in-progress panel/page latest-entity-by-path resolution spec; revisit once that spec lands.

#### Symptom

On a freshly-spawned session (empty DB), `import_plugin_grift` reports:

```
[samsite/compliance-landing] FAILED:
  [execution] execution_failed at $.batches[0].edges[7]: not_found: Entity 019e5502-cee6-744a-93b2-9599032cb55d not found.
  [execution] execution_failed at $.batches[1].edges[0]: not_found: Entity 019e5502-cee6-744a-93b2-9599032cb55d not found.
  [execution] execution_failed at $.batches[2].nodes[0]: hotlink_validation_failed: Hotlink 'page-panels' (exact): missing edges for: ['artifacts', 'components', 'findings', 'indicators', 'ksi-signal', 'nav', 'themes', 'validations', 'vdr-report', 'violations'].
```

The rest of the spawn import succeeds (22 of 23 bundles green); only `/samsite/compliance` renders broken (missing panel rows).

#### Root cause

`plugins/samsite/grift/compliance-landing.grift.json` has a 3-batch design that creates the page entity (`019e5502-cee6-744a-93b2-9599032cb55d`) in batch 2, but batch 0 and batch 1 contain USES_PANEL edges that reference it as `from_entity_id`. The edge insertion path requires both endpoints to exist at insert time, so batch 0's edges fail immediately on a fresh DB; batch 2's hotlink validation then fails because none of the expected USES_PANEL edges exist.

The bundle's own marker-node description (`_compliance_landing_batch1_marker` in batch 0) self-documents the author's flawed mental model:

> *"The page node moved to batch 2 to defer its hotlink validation until after batch 1's USES_PANEL edges land."*

That sequencing isn't supported — edges can't land before their endpoints exist, regardless of which batch they're in.

#### History

| Commit | Date | Change | Bundle shape |
| --- | --- | --- | --- |
| `78de9c6` | 2026-05-23 | Original landing page | 1 batch: page + panels + edges (works on any DB) |
| `37aab54` | 2026-05-23 | Path B per-type viewer + KSI Framework rows | 2 batches: page moved into batch 1 ("add themes/indicators rows"); marker placeholder added to batch 0 to satisfy `nodes[]` requirement (broken on fresh DB) |
| `08881c4` | 2026-05-26 | OSCAL pages + nav-links | 3 batches: page now in batch 2; nav panel + nav edge in batch 1 (still broken on fresh DB; broken in same way) |

The bug has been latent on `origin/main` since `37aab54`. It only surfaces on fresh spawns because long-lived DBs retain the page entity from the original `78de9c6` single-batch import. Every spawn since `37aab54` has hit this, but the noise was attributed to other causes until the 2026-05-27 spawn investigation.

#### Dependency

This bug is structurally tied to the bundle's reliance on hardcoded USES_PANEL edges with explicit `from_entity_id`/`to_entity_id` UUIDs. The user is drafting a panel/page latest-entity-by-path resolution spec that would let page layouts reference panels by slug at render time (similar to ROSCALE's `req-roscale-input-5` latest-emission fallback pattern, generalized). If that spec eliminates the need for USES_PANEL edges entirely — or relaxes them to permissive runtime resolution — the bundle's batch structure can be simplified or collapsed back to the working single-batch shape, and this bug goes away by elimination rather than by patch.

#### Fix paths

**Preferred (post-spec):** Rework `compliance-landing.grift.json` to match whatever shape the new panel/page resolution spec dictates. If that means single-batch with slug-resolved panels, collapse accordingly.

**Interim (if pressure mounts before the spec lands):** Move the page entity from batch 2 into batch 0, with a 9-row layout (no nav). Drop the `_compliance_landing_batch1_marker` placeholder (no longer needed). Keep batch 1 (nav-panel addition) and batch 2 (re-upsert page with 10-row layout including nav) as they are. The deferred-hotlink-and-drain mechanism (req-grid-hotlink-deferred, landed 2026-05-26) makes this safe — hotlink validation runs at end-of-batch after all USES_PANEL edges have landed.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| KI-1-1 | Spec Resolution | Open | The new panel/page latest-entity-by-path resolution spec is finalized. | Tracked outside this spec; this issue is gated on its landing |
| KI-1-2 | Fresh-Spawn Green | Open | `import_plugin_grift --all` on a fresh DB completes with `samsite/compliance-landing` reporting OK. | Verifiable via `scripts/spawn-session.sh` against a new worktree |
| KI-1-3 | Live-DB Idempotent | Open | Re-importing the bundle against an already-seeded DB does not re-trigger the failure or produce drift. | Important because most existing sessions already have the page entity from the `78de9c6` original import |
