# Samsite KSI Scoreboard Specification

## Philosophy

The Samsite KSI Scoreboard is a synthesized roll-up — a view that **doesn't exist in any single artifact on the wire**. Sam's `/.well-known/ksi-signal.json` carries inventory + granular OPA-rule validations. His OSCAL SSP carries Rev-5 control statuses. His OSCAL POA&M carries open and risk-accepted findings. None of them carries "KSI-IAM-MFA is passing" as a primitive fact. The scoreboard computes it.

The construct: the on-grid FedRAMP 20x KSI catalog (`ksi_indicator` + `ksi_theme` nodes, seeded by the `fedramp_20x_ksi` plugin's GRIFT) lists each indicator with its `controls` array — a string of Rev-5 control IDs the indicator claims to evaluate. The scoreboard joins that array against the latest OSCAL SSP's `implemented-requirements[]` and the latest OSCAL POA&M's `poam-items[]` `controls` prop. The result, per indicator, is one of four aggregated statuses: **passing**, **in-progress**, **accepted**, or **gap**.

This is samsite-specific in v0 because the catalog, the SSP, and the POA&M are all samsite's specific artifacts. The panel type can be lifted to the `fedramp_20x_ksi` plugin if a second consumer appears (see [Future Lift](#future-lift)) — but per [[future-seam-discipline]] / [[panel-latest-emission-fallback-pattern]], the rule is "third use is the lift trigger; don't pre-extract on one." Samsite is the first proving instance.

What this fixes: the original repo doesn't surface KSI-family status anywhere; the closest you get from Sam's published artifacts is the SSP (Rev-5, not 20x) and the raw signal validations (OPA-rule-level, not KSI-family-level). The scoreboard makes the 20x → Rev-5 mapping computationally explicit and renders it in one page.

## Goals

|   | Goal | Description |
| :---: | --- | --- |
| 1. | Synthesized Roll-up | Produce per-KSI pass/in-progress/accepted/gap status by joining the indicator catalog × SSP × POA&M; no upstream artifact change required. |
| 2. | Class-Aware | Read the system's FedRAMP class from SSP metadata and exclude indicators that don't apply, so the score reflects what the system is actually trying to claim. |
| 3. | Drill-Downable | Each indicator card expands to a per-control table that shows the SSP implementation status and any POA&M item ids — so users can verify the math row by row. |
| 4. | Bare-URL Renders | Visiting `/samsite/compliance/scoreboard` (no query string) shows the latest emission of each artifact via panel-level fallback; explicit deep links to specific emissions also work. |
| 5. | Pure-Function Scoring | The math lives in `plugins.samsite.scoring`, no Django or ORM imports — testable offline against fixture JSON. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-samsite-scoreboard-page | [Page and Panel Instance](#page-and-panel-instance) | Implemented | `/samsite/compliance/scoreboard` page + `samsite-ksi-scoreboard` panel + USES_PANEL edge (compliance-pages.grift.json batch v0.1.0) |
| req-samsite-scoreboard-panel | [Panel Type Contract](#panel-type-contract) | Implemented | Registered via `samsite.apps.SamsiteConfig.ready()` |
| req-samsite-scoreboard-resolution | [Dual-Artifact Resolution](#dual-artifact-resolution) | Implemented | Reuses ROSCALE's `_lookup_by_entity_id` + `_lookup_latest_by_kind`; SSP and POA&M each have their own fallback.kind |
| req-samsite-scoreboard-scoring | [Per-Control and Per-Indicator Scoring](#per-control-and-per-indicator-scoring) | Implemented | Pure functions in `plugins/samsite/scoring.py`; 11 unit tests against fixture SSP+POA&M |
| req-samsite-scoreboard-class-filter | [Class-Aware Filtering](#class-aware-filtering) | Implemented | Reads `fedramp-class` prop from SSP metadata; indicators whose `classes` array excludes the system class are skipped + counted |
| req-samsite-scoreboard-class-variants | [Class-Variant Control Overrides](#class-variant-control-overrides) | Implemented | Honors `ksi_indicator.class_variants[<class>].controls` when present; falls back to base `controls` otherwise |
| req-samsite-scoreboard-rendering | [Rendering Contract](#rendering-contract) | Implemented | Headline strip + themed grid + per-control drill-down + provenance footer |
| req-samsite-scoreboard-errors | [Error and Degraded Behavior](#error-and-degraded-behavior) | Implemented | SSP missing = hard fail with polished error; POA&M missing = warning banner, scoring proceeds (no POA&M coverage applied) |
| req-samsite-scoreboard-gap-explanation | [Gap Explanation](#gap-explanation) | Backlog | "Why is this control unmapped?" hint distinguishing catalog-references-nonexistent-Rev-5 from SSP-omitted-from-scope |
| req-samsite-scoreboard-history | [Emission History / Drift](#emission-history-drift) | Backlog | "This SSP from 2026-05-26; previous 2026-05-25" timeline with score-delta per indicator |
| req-samsite-scoreboard-lift | [Future Lift to fedramp_20x_ksi](#future-lift) | Backlog | Promote panel + scoring to the fedramp_20x_ksi plugin when a second consumer needs it |

### Page and Panel Instance
----
RID: `req-samsite-scoreboard-page`
Status: `Implemented`

Samsite contributes a GRIFT page at `/samsite/compliance/scoreboard` that hosts a single panel instance with `panel_type_slug = "samsite-ksi-scoreboard"`. The page is reachable from the existing `/samsite/compliance` landing via the third nav-link card (added to the `samsite-nav-links` panel in the `compliance-landing.grift.json` nav-additions batch).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-page-1 | Page Route | Implemented | A GRIFT page exists with route `/samsite/compliance/scoreboard`. | `grift/compliance-pages.grift.json` batch `019e65d6-8754-7b35-a46d-fc45757ef64a` |
| req-samsite-scoreboard-page-2 | Panel Instance | Implemented | The page contains a single Panel node referencing panel type `samsite-ksi-scoreboard`. | USES_PANEL edge hotlinked as `scoreboard` |
| req-samsite-scoreboard-page-3 | Nav Discoverability | Implemented | The page is one click from `/samsite/compliance` via the third samsite-nav-links card. | Updated in-place via `--force-batches=019e6531-ef00-75a7-ad57-e08e31d5e95d` |

### Panel Type Contract
----
RID: `req-samsite-scoreboard-panel`
Status: `Implemented`

ROSCALE registered slug: **`samsite-ksi-scoreboard`**. Lives at `plugins/samsite/panels/ksi_scoreboard/__init__.py`. Panel type ClassVars follow the duck-typed contract used elsewhere in TAP (slug, label, view, css, js, config_defaults, classmethod `get_view_context`).

Default config:

```json
{
  "ssp_artifact_entity_id_var": "oscal_ssp_artifact_entity_id",
  "poam_artifact_entity_id_var": "oscal_poam_artifact_entity_id",
  "fallback": {
    "ssp_kind": "oscal_ssp",
    "poam_kind": "oscal_poam"
  }
}
```

Consumers can override any of these. The two `*_var` keys name the URL-backed page variables to read; the `fallback` block names the `compliance_artifact.kind` value used when each URL var is empty.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-panel-1 | Registered | Implemented | `samsite-ksi-scoreboard` registered in `tap_web.registry.panel_type_registry` via `SamsiteConfig.ready()`. | |
| req-samsite-scoreboard-panel-2 | Config-Driven Resolution | Implemented | The panel reads URL var names and fallback kinds from `panel.config`; nothing hardcoded. | |
| req-samsite-scoreboard-panel-3 | No Consumer-Specific Logic | Implemented | The panel knows about `compliance_artifact`, `ksi_indicator`, and `ksi_theme` — all TAP-generic models. No samsite-specific branching. | The panel is samsite-side only because nobody else needs it yet; the code itself is consumer-neutral |

### Dual-Artifact Resolution
----
RID: `req-samsite-scoreboard-resolution`
Status: `Implemented`

The scoreboard needs **both** the latest OSCAL SSP and the latest OSCAL POA&M to render fully. Resolution is per-artifact and follows the [[panel-latest-emission-fallback-pattern]]:

1. Explicit URL deep link wins: if `request.GET[<var_name>]` has a value, look up that `entity_id` via Gryphon. If not found → polished "artifact not found" error.
2. Fallback: if the URL var is empty and `config.fallback.<kind>` is set, run `MATCH (a:compliance_artifact) WHERE a.data.kind = $kind` (Gryphon's `.data.` prefix is required for per-model fields), sort by `fetched_at` desc in Python, pick the first node. Surface a "Showing latest emission" banner.
3. No URL var and no fallback configured → polished "no artifact specified" error.

Helpers `_lookup_by_entity_id` and `_lookup_latest_by_kind` are imported from `plugins.roscale.panels._common` — ROSCALE is the OSCAL-panel center of gravity. Per [[panel-latest-emission-fallback-pattern]], the third use of this shape is the lift-to-shared trigger.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-resolution-1 | SSP via URL or Fallback | Implemented | The SSP resolves from `oscal_ssp_artifact_entity_id` URL var or, when empty, the latest emission with `kind = oscal_ssp`. | |
| req-samsite-scoreboard-resolution-2 | POA&M via URL or Fallback | Implemented | Same pattern, with `kind = oscal_poam`. | |
| req-samsite-scoreboard-resolution-3 | used_fallback Surfaced | Implemented | Per-artifact `used_fallback` flag flows to the template; "Showing latest emissions" note appears when either or both fell back. | |

### Per-Control and Per-Indicator Scoring
----
RID: `req-samsite-scoreboard-scoring`
Status: `Implemented`

The scoring math is in `plugins/samsite/scoring.py` and is pure: it takes a list of indicator dicts, the parsed SSP doc, and the parsed POA&M doc (any of which may be `None`), and returns a `ScoreboardResult` dataclass with per-indicator detail and aggregate totals.

#### Per-control taxonomy

Evaluates `(SSP × POA&M)` per control id (lowercased Rev-5 form):

| Condition | Per-control status |
| --- | --- |
| In POA&M with `status = open` | `open` |
| In POA&M with `status = risk-accepted` (and no open POA&M) | `accepted` |
| Control id NOT found in SSP `implemented-requirements[]` | `unmapped` |
| SSP `implementation-status = not-applicable` (and no POA&M coverage) | `n/a` |
| SSP `implementation-status = partial` (and no POA&M coverage) | `partial` |
| Otherwise (treat any other SSP value as implemented) | `pass` |

POA&M precedence is intentional: if a control has both an SSP `implemented` status and an open POA&M item against it, the POA&M signal wins — Sam's POA&M is telling you the implementation is in question regardless of what the SSP claims.

#### Per-indicator aggregation

Worst-case wins, with this priority:

| Per-control status | Contributes to per-indicator |
| --- | --- |
| `unmapped` | `gap` (priority 4 — worst) |
| `open` or `partial` | `in-progress` (priority 3) |
| `accepted` | `accepted` (priority 2) |
| `pass` or `n/a` | `passing` (priority 1) |

If an indicator has no `controls` array at all, it's treated as `gap` (the catalog itself is the bug, not the system).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-scoring-1 | Pure Functions | Implemented | The scoring module has no Django/ORM imports; it operates on plain dicts. | Testable offline |
| req-samsite-scoreboard-scoring-2 | Per-Control Taxonomy | Implemented | Six per-control statuses per the table above. | `test_control_evaluation` in `plugins/samsite/tests/test_ksi_scoreboard.py` |
| req-samsite-scoreboard-scoring-3 | Worst-Case Aggregation | Implemented | Indicator status takes the worst-case of its controls. | `test_mixed_indicator_takes_worst_case_status` |
| req-samsite-scoreboard-scoring-4 | POA&M Precedence | Implemented | A control with both SSP `implemented` and an open POA&M item scores as `open` (POA&M wins). | `test_ac_2_in_ssp_appears_in_poam_open` |
| req-samsite-scoreboard-scoring-5 | controls (plural) Prop | Implemented | POA&M control references read from the `controls` (plural) prop with `control` (singular) fallback for legacy docs. | Bug discovered + fixed in `plugins/roscale/panels/_common.py` same change |

### Class-Aware Filtering
----
RID: `req-samsite-scoreboard-class-filter`
Status: `Implemented`

The system's FedRAMP 20x class is read from the SSP's metadata as a prop named `fedramp-class` (samsite declares Class C). Indicators whose `classes` array excludes the system class are skipped from scoring entirely and counted under `excluded_class_mismatch` for transparency.

If the SSP doesn't carry the prop (and no override is supplied), all indicators are scored regardless of class — the score is still computable but doesn't reflect a tier claim.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-class-filter-1 | SSP Source | Implemented | The class is read from the SSP metadata `fedramp-class` prop. | |
| req-samsite-scoreboard-class-filter-2 | Mismatch Counted | Implemented | Indicators that don't apply to the system class are excluded and the count appears on the headline strip. | |
| req-samsite-scoreboard-class-filter-3 | No-Class Fallback | Implemented | When no class is declared, no filtering is applied (all indicators scored). | |

### Class-Variant Control Overrides
----
RID: `req-samsite-scoreboard-class-variants`
Status: `Implemented`

`ksi_indicator.class_variants` is an optional object keyed by class (e.g. `"c"`, `"d"`) whose value is an object with its own `controls` array. When the system's class has a matching variant, that variant's `controls` list replaces the base `controls`. Otherwise the base list applies.

In Samsite's current GRIFT seed, every indicator has `class_variants = null`, so this code path doesn't fire today. It's covered by `test_class_variants_override_base_controls` so future seed updates that introduce variants don't surprise the scoring.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-class-variants-1 | Variant Wins When Present | Implemented | When `class_variants[<system_class>]` exists, its `controls` list is used instead of the base `controls`. | |
| req-samsite-scoreboard-class-variants-2 | Base Fallback | Implemented | No variant for the system class → use base `controls`. | |

### Rendering Contract
----
RID: `req-samsite-scoreboard-rendering`
Status: `Implemented`

The scoreboard renders as a single panel with four layers:

1. **Headline strip** at the top: the system's FedRAMP class + total KSIs scored + excluded-class-mismatch count + status totals as pills (one pill per status: passing, in-progress, accepted, gap). If the SSP or POA&M was resolved via fallback, a "Showing latest emissions" note appears beneath the totals.
2. **Themed sections**, one per `ksi_theme` (e.g. "Identity and Access Management"). Theme name from the `ksi_theme` node when available, falling back to the theme code (e.g. `KSI-IAM`).
3. **Indicator cards** within each theme. Each card is a `<details>` element whose summary row reads left-to-right: **code → name → status badge → "N/M controls"**. Closed by default.
4. **Per-control table** inside each expanded card: control id, computed status, raw SSP implementation status, comma-separated POA&M item ids if any.

Plus a footer `<details>` block with source-artifact provenance (URLs, fetched-at, signature-verified) for both SSP and POA&M.

Status pill / badge colors:

- `passing` — green
- `in-progress` — amber
- `accepted` — blue
- `gap` — red
- Per-control `n/a` — gray
- Per-control `partial` — orange (rare; emitted by SSP `implementation-status = partial`)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-rendering-1 | Headline Strip | Implemented | Class, total, excluded count, and one status pill per status appear at the top. | |
| req-samsite-scoreboard-rendering-2 | Themed Grouping | Implemented | Indicators are grouped under their `ksi_theme.name`, sorted stably. | Theme code parsed from indicator code (`KSI-CMT-LMC` → `KSI-CMT`) |
| req-samsite-scoreboard-rendering-3 | Card Summary Order | Implemented | Each indicator's summary row reads code → name → status → progress. | Tweaked 2026-05-26 to put narrative first, state second |
| req-samsite-scoreboard-rendering-4 | Per-Control Drill-Down | Implemented | Each card expands to a table with control id, computed status, SSP raw status, and POA&M item ids. | |
| req-samsite-scoreboard-rendering-5 | Provenance Footer | Implemented | Source-artifact URLs, fetched-at, and signature-verified are visible in a collapsed `<details>` at the bottom. | |

### Error and Degraded Behavior
----
RID: `req-samsite-scoreboard-errors`
Status: `Implemented`

Failure modes and responses:

- **SSP not resolvable** (no URL var, no fallback, or fallback found no emission) → hard fail. Polished error block at the top of the panel; no scoring. Without an SSP there's nothing to score against.
- **POA&M not resolvable** → recoverable. Scoring proceeds with no POA&M coverage applied; an amber "POA&M not available" note appears above the headline strip. Every per-control status that would have been `open` or `accepted` instead reads `pass` or `n/a` — surfaced as the "no POA&M coverage" caveat so users don't take "passing" at face value.
- **No `ksi_indicator` nodes on the grid** → hard fail with explicit instruction to import the `fedramp_20x_ksi` plugin's GRIFT seed.
- **Gryphon lookup fails** (transient, network, etc.) → polished error with the exception message logged via the panel's `[scbN]` short-id logger.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-errors-1 | SSP Hard Fail | Implemented | Without an SSP, the panel renders an error and skips scoring. | |
| req-samsite-scoreboard-errors-2 | POA&M Soft Fail | Implemented | Without a POA&M, scoring still proceeds and the user is told. | |
| req-samsite-scoreboard-errors-3 | Empty Catalog Fail | Implemented | Zero `ksi_indicator` nodes on the grid surfaces a polished error pointing at the seed import. | |
| req-samsite-scoreboard-errors-4 | Polished Phase Tags | Implemented | Error messages include a phase tag (e.g. `[load]`) so users can locate the failure. | |

### Gap Explanation
----
RID: `req-samsite-scoreboard-gap-explanation`
Status: `Backlog`

A `gap` status today means "at least one control referenced by the indicator is not in the SSP." That's accurate but not enriching — users can't tell which of two distinct shapes the gap takes:

- **Catalog-references-nonexistent-Rev-5 control.** The KSI indicator names a control id that isn't in NIST 800-53 Rev 5 at all (or isn't in the FedRAMP Moderate/High baselines). This is a catalog seed bug.
- **SSP-omitted control.** The control exists in the relevant baseline and Sam *should* have it in his SSP, but doesn't. This is an SSP-coverage gap and a real action item.

Future work: vendor or fetch a Rev-5 catalog (or the FedRAMP-resolved profile chain) and check each unmapped control against it. Render the distinction in the per-control table.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-gap-explanation-1 | Distinguish gap shape | Backlog | The per-control table distinguishes catalog-bug gaps from SSP-coverage gaps. | Requires catalog lookup (out of v0 scope; aligns with `req-roscale-vendor` follow-up) |

### Emission History / Drift
----
RID: `req-samsite-scoreboard-history`
Status: `Backlog`

Each `compliance_artifact` is per-emission (the samsite collector lands a new node every run; see `req-samsite-collector-identity`). Multiple historical emissions accumulate on the grid. Future work: a timeline view on the scoreboard showing per-indicator score changes across the last N emissions, with click-through to a specific emission's snapshot.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-history-1 | Multi-Emission Timeline | Backlog | A timeline visualization renders score deltas across recent SSP+POA&M emissions. | |

### Future Lift
----
RID: `req-samsite-scoreboard-lift`
Status: `Backlog`

If a second consumer wants the same view (e.g. a fictional Class D system on the grid), the lift path is: promote the panel type to the `fedramp_20x_ksi` plugin as `fedramp-20x-ksi-scoreboard`, move the scoring module there too, and reduce the samsite side to a page-instance-only contribution (matching the ROSCALE/samsite split established by `spec-samsite-compliance-pages-v0.md`). The panel code already has no samsite-specific branching, so the lift is mechanical.

Per [[panel-latest-emission-fallback-pattern]] and [[future-seam-discipline]], **do not pre-lift on speculation** — wait for the demand signal. Samsite is the first proving instance; the second use is the trigger.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-lift-1 | Document the Lift | Backlog | When a second consumer appears, the lift is captured in a new `spec-fedramp-20x-ksi-scoreboard-v0.md` (in the fedramp_20x_ksi plugin) and the samsite spec marks its scoping section to point there. | |

### Future Migration: tap_web Entity Resolution
----
RID: `req-samsite-scoreboard-entity-resolution-migration`
Status: `Backlog`

The KSI scoreboard is a multi-entity panel (SSP + POA&M roles) that currently resolves its target `compliance_artifact` entities via the locally-defined helpers in `plugins/roscale/panels/_common.py`. When `tap_web/specs/spec-web-panel-entity-resolution-v0.md` lands and the canonical `tap_web/panels/entity_resolution.py` module exists, the scoreboard migrates to import from there.

#### Implementation

- Update `plugins/samsite/panels/ksi_scoreboard/__init__.py` to import `resolve_entity` and `EntityResolution` from `tap_web.panels.entity_resolution` instead of the roscale-local helpers.
- Rewrite the scoreboard panel config in grift from the legacy multi-role shape:

  ```json
  {
    "ssp_artifact_entity_id_var":  "oscal_ssp_artifact_entity_id",
    "poam_artifact_entity_id_var": "oscal_poam_artifact_entity_id",
    "fallback": {
      "ssp_kind":  "oscal_ssp",
      "poam_kind": "oscal_poam"
    }
  }
  ```

  to the canonical multi-role shape required by the platform spec:

  ```json
  {
    "ssp_entity_id_var":  "oscal_ssp_artifact_entity_id",
    "poam_entity_id_var": "oscal_poam_artifact_entity_id",
    "fallback": {
      "ssp":  {
        "entity_type": "compliance_artifact",
        "field":       "kind",
        "value":       "oscal_ssp",
        "sort_field":  "fetched_at"
      },
      "poam": {
        "entity_type": "compliance_artifact",
        "field":       "kind",
        "value":       "oscal_poam",
        "sort_field":  "fetched_at"
      }
    }
  }
  ```

- Update tests in `plugins/samsite/tests/test_ksi_scoreboard.py` to mock the helpers at the new module path under the new names.
- The required/degraded role behavior (SSP required, POA&M degraded) stays as-is — that's a scoreboard concern, not a platform concern.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-scoreboard-entity-resolution-migration-1 | Canonical Module Imported | Backlog | The scoreboard panel imports `resolve_entity` / `EntityResolution` from `tap_web.panels.entity_resolution`. | |
| req-samsite-scoreboard-entity-resolution-migration-2 | Multi-Role Config Rewritten | Backlog | The scoreboard panel config in grift uses the new per-role sub-block shape; the legacy `<role>_artifact_entity_id_var` and `fallback.<role>_kind` keys are removed. | |
