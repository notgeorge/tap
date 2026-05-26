# ROSCALE

**R**ead **OSCAL** **E**dit — a TAP helper/presentation plugin for OSCAL documents (System Security Plan and POA&M).

## What this plugin does

ROSCALE turns an existing on-grid OSCAL artifact into a readable compliance workbench. v0 ships two reusable TAP Web panel types:

- `roscale-oscal-workbench` — renders an OSCAL SSP (provenance, metadata, system overview, control implementation grouped by family, back matter, JSON fallback)
- `roscale-oscal-poam-workbench` — renders an OSCAL POA&M as an action/risk register

Both panels accept the artifact entity id through an explicit page variable rather than hard-coding their source, so any TAP page can host them. When the page variable is empty, each panel can optionally fall back to the most-recently-fetched `compliance_artifact` of a configured `kind` — so a bare URL like `/<consumer>/<page>` with no query string renders "current state" without the host needing a prefilled-link widget.

## What this plugin owns

- pure Python OSCAL parsing helpers
- pure Python OSCAL validation (against vendored official OSCAL `1.1.2` JSON Schemas + TAP-authored semantic checks)
- the two panel types listed above, their templates, and static assets
- vendored OSCAL `1.1.2` schemas + public examples under `vendor/nist/oscal/1.1.2/`
- tests for parser, validation, and panel-facing behavior

## What lives elsewhere

- **Consumers own the page instances.** Each consumer plugin contributes its own GRIFT pages that host ROSCALE's panels. The initial consumer is the `samsite` plugin (see `plugins/samsite/specs/spec-samsite-compliance-pages-v0.md`); ROSCALE owns the panel implementations those pages use.
- **OSCAL artifacts on the grid.** ROSCALE does not collect OSCAL. Collector plugins (e.g. the `samsite` compliance collector) fetch and verify them; they live as `fedramp_20x_ksi.compliance_artifact` nodes. ROSCALE reads from those nodes.

## Read first

- [`specs/spec-roscale-v0.md`](specs/spec-roscale-v0.md) — the canonical plugin spec (Plugin Identity, scope, requirements, ACs)
- [`tap_plugins/specs/spec-plugin-architecture.md`](../../tap_plugins/specs/spec-plugin-architecture.md) — plugin layout + package rules
- [`tap_plugins/specs/spec-plugin-manifest-v0.md`](../../tap_plugins/specs/spec-plugin-manifest-v0.md) — manifest format
- [`tap_web/specs/`](../../tap_web/specs/) — panel-type, page-variable, and GRIFT-page contracts

## v0 scope

- **Models:** none.
- **Edges:** none.
- **GRIFT seed data:** none — consumer plugins contribute the page/panel GRIFT separately.
- **Schedules:** none — ROSCALE is helper code, not a collector.
- **Default dimensions:** N/A — no TAP-managed entities in v0.
- **Icons:** none in v0; may add a panel/document-type icon later.

## Install

In-tree under `plugins/roscale/`. Once panel implementations land:

```python
INSTALLED_APPS = [
    # ...
    "plugins.roscale",
]
```

Then run `python manage.py migrate` (no-op for roscale — no models — but consistent with TAP install flow).

## Validate

```bash
python -m tap_plugins.validate_plugin plugins/roscale
```

Structure-level validation confirms manifest correctness, package layout, and `apps.py` shape. `loads` and `runs` levels work once the plugin is in `INSTALLED_APPS`.

## Status

v0 — scaffolded. Panel implementations, vendored schemas, parser, and validator are next.
