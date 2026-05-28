# Samsite VDR Ingestion Health Panel Specification

## Philosophy

The upstream `notgeorge/samsite` VDR aggregator emits two disclosure flags on `vdr-report.json` `summary` (added 2026-05-27 in commit `436ff9f`): `kev_catalog_loaded` and `dependabot_alerts_loaded`. These tell consumers whether the CISA KEV catalog and the GitHub Dependabot alerts API actually contributed to the build, or whether the corresponding evaluations silently no-op'd because the input was missing. The flags exist because absence of data is not the same as a clean signal.

This panel is the **consumer-side complement** to those producer-side flags. The TAP-managed `vdr_report` node's `summary` JSONField copies the flags verbatim, but a flag in JSON nobody reads is useless — the panel surfaces them as ✓/✗ pills on the compliance landing so a regression of either upstream ingestion is visible without anyone opening the published report.

This is consumer-side discipline, codified by the `consumer-side-disclosure-complement` memory: producer-side disclosure only works if the consumer completes the loop.

## Goals

|   | Goal | Description |
| :---: | --- | --- |
| 1. | One-glance Health | A user landing on `/samsite/compliance` sees the latest VDR's two disclosure flags as ✓/✗ pills without scrolling or clicking. |
| 2. | Unknown ≠ False | Reports that predate the disclosure flags (older `vdr_report` nodes) render as a third "unknown" state, not as "false." |
| 3. | Active Warning On Regression | When any flag is `false`, the panel turns red and emits an explicit warning that derived "no findings" interpretations are unreliable for the corresponding source. |
| 4. | No Producer-Side Coupling | The panel reads from `vdr_report.summary.<key>` — it doesn't know or care which upstream pipeline produced the report, only that the disclosure-flag contract is honored. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-samsite-vdr-health-panel | [Panel Type Contract](#panel-type-contract) | Implemented | `samsite-vdr-ingestion-health` registered in `SamsiteConfig.ready()` |
| req-samsite-vdr-health-resolution | [Latest Report Resolution](#latest-report-resolution) | Implemented | Gryphon `MATCH (r:vdr_report)` sorted by `data.emitted_at` desc; picks first |
| req-samsite-vdr-health-pills | [Pill Rendering](#pill-rendering) | Implemented | Three states: ok (green ✓), missing (red ✗), unknown (gray ?) |
| req-samsite-vdr-health-warning | [Degraded Warning](#degraded-warning) | Implemented | Panel container turns red + emits explicit caveat when any flag is `missing` |
| req-samsite-vdr-health-page-row | [Compliance Landing Placement](#compliance-landing-placement) | Implemented | Row-1 of `/samsite/compliance` (top of page), via compliance-landing.grift.json v0.3.0 |
| req-samsite-vdr-health-extensibility | [Flag List Extensibility](#flag-list-extensibility) | Backlog | New flags added upstream require a code update to the `DISCLOSURE_FLAGS` constant; could become config-driven if a second consumer needs it |

### Panel Type Contract
----
RID: `req-samsite-vdr-health-panel`
Status: `Implemented`

Slug **`samsite-vdr-ingestion-health`**, registered in `tap_web.registry.panel_type_registry` via `SamsiteConfig.ready()`. Panel module at `plugins/samsite/panels/vdr_ingestion_health/__init__.py`. ClassVars follow the standard duck-typed contract (slug, label, view, css, js, config_defaults). The `get_view_context` classmethod resolves the latest `vdr_report` and emits the flag list as template context.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-vdr-health-panel-1 | Registered | Implemented | Panel type registered in `panel_type_registry`. | |
| req-samsite-vdr-health-panel-2 | Empty Config | Implemented | `config_defaults = {}` — no config required from consumers. | |

### Latest Report Resolution
----
RID: `req-samsite-vdr-health-resolution`
Status: `Implemented`

`_load_latest_vdr_report()` runs `MATCH (r:vdr_report)` via Gryphon and sorts the result in Python by the per-model `emitted_at` field (ISO 8601 string, sorts lexically as chronological). Returns the first node, or `None` if no `vdr_report` is on the grid yet.

The shape mirrors `_lookup_latest_by_kind` from the ROSCALE panel-common module ([[panel-latest-emission-fallback-pattern]]). Same pattern of "Gryphon for the row set, Python for the sort" — works without depending on Gryphon's `ORDER BY` semantics. Per the memory, the third use of this shape is the lift trigger; this is the third (after ROSCALE single-artifact and the scoreboard's dual-artifact). The lift target is `tap_web.panels.artifact_resolution` or `fedramp_20x_ksi.panels.artifact_resolution` — out of scope for this v0 spec but tracked.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-vdr-health-resolution-1 | Latest Wins | Implemented | The most-recently-emitted `vdr_report` is the source; older reports are ignored. | |
| req-samsite-vdr-health-resolution-2 | Empty Catalog Polished Error | Implemented | When no `vdr_report` exists, the panel renders a polished "no report yet" message, not a crash. | |

### Pill Rendering
----
RID: `req-samsite-vdr-health-pills`
Status: `Implemented`

For each entry in the panel's `DISCLOSURE_FLAGS` list (currently `kev_catalog_loaded` and `dependabot_alerts_loaded`):

- If the key is present in `summary` AND its value is truthy → **ok** (green ✓ pill).
- If the key is present in `summary` AND its value is falsy → **missing** (red ✗ pill, bold).
- If the key is NOT in `summary` at all → **unknown** (gray ? pill).

Each pill carries the flag's help text as a `title=` tooltip so the user can hover for the full explanation.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-vdr-health-pills-1 | Three-state Rendering | Implemented | ok / missing / unknown render with distinct colors and glyphs. | |
| req-samsite-vdr-health-pills-2 | Unknown Distinct from Missing | Implemented | An older report that predates a flag renders the pill as `unknown`, not as `missing`. | The distinction matters: missing = explicit upstream "did not run"; unknown = absence of signal about absence of signal |
| req-samsite-vdr-health-pills-3 | Help Tooltip | Implemented | Hovering a pill reveals the flag's help text via `title=`. | |

### Degraded Warning
----
RID: `req-samsite-vdr-health-warning`
Status: `Implemented`

When the panel context's `any_false` is true (at least one flag is in the `missing` state), the panel container picks up a `samsite-vdr-health-degraded` class (red background) AND emits an explicit caveat paragraph: "One or more upstream ingestions did not run in the latest VDR build. Findings derived from the corresponding source are absent by omission, not by clean signal — interpret 'no findings' of that source with care."

`unknown` states do NOT trigger the degraded UI — they're a separate axis (we don't know whether evaluation ran, but we also have no positive disclosure of failure).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-vdr-health-warning-1 | Red on Any Missing | Implemented | The container background flips to red when any flag is in `missing` state. | |
| req-samsite-vdr-health-warning-2 | Explicit Caveat Text | Implemented | The warning paragraph names the consequence: "absent by omission, not by clean signal." | Aligns with consumer-side-disclosure-complement rule 2 |

### Compliance Landing Placement
----
RID: `req-samsite-vdr-health-page-row`
Status: `Implemented`

The panel is hosted on `/samsite/compliance` as **row 1** (top of page), above the nav-links cards and the existing 9 entity tables. Wired via `compliance-landing.grift.json` v0.3.0 page-layout batch + the sibling vdr-ingestion-health panel batch.

The placement reflects the panel's job: it's an orientation widget answering "is the underlying pipeline healthy enough that I should trust what's below?" That belongs above everything else.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-vdr-health-page-row-1 | Top of Page | Implemented | The panel is the first visual element on `/samsite/compliance` below the page chrome. | row-1-vdr-health in the layout |
| req-samsite-vdr-health-page-row-2 | Sibling Batch Pattern | Implemented | Panel + USES_PANEL edge land in an earlier batch than the page-layout-bump batch so hotlinks resolve. | Same panels-first / page-second pattern established by the nav-additions split |

### Flag List Extensibility
----
RID: `req-samsite-vdr-health-extensibility`
Status: `Backlog`

The `DISCLOSURE_FLAGS` list is currently hardcoded in the panel module. New flags added upstream require a code update. Future work: make it config-driven (so consumers can add flags via GRIFT) or auto-discover flags by introspecting `summary` keys with the `_loaded` suffix.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-vdr-health-extensibility-1 | Config-Driven Flags | Backlog | Panel config can supply a flag list (label, key, help text); hardcoded list becomes the default. | Trigger: a second consumer plugin wants this panel with different flag set |
