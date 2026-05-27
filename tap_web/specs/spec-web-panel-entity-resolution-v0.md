# Panel Entity Resolution Specification

## Philosophy

Several TAP panels render content derived from a single on-grid entity. The entity is picked one of two ways: either the caller deep-links by passing the entity's `entity_id` as a URL query parameter (bookmarkable, stable across time), or the panel falls back to *the latest entity of a configured shape* when the URL is bare (always-render-something default). Either way, the rendered page should make it clear which path was taken so the user knows whether they're looking at a specific historical view or the current latest.

The originating use case is `compliance_artifact` nodes produced by the samsite compliance collector — each nightly fetch produces a new node per artifact kind, so the grid accumulates a history of emissions and the panel needs to either render *this specific one* (deep link) or *the most recent one* (fallback). The pattern generalizes cleanly: any entity type whose collector produces a new node per run (KSI signals, VDR reports, future per-emission types) has the same resolution problem.

The pattern was first sketched ad-hoc in `plugins/roscale/panels/_common.py` and copy-pasted into two later panels. This spec lifts the pattern into a TAP-wide convention and identifies `tap_web` as the canonical home for the helper. Future panels SHOULD use the helpers named here rather than re-implementing the resolution dance, and the rendering conventions (the "showing latest" banner, the polished error states) are common contracts rather than per-panel choices.

This spec governs **panel-side resolution**. Per-emission identity semantics for the *entities themselves* (why nodes accumulate per emission rather than upserting in place) live with the relevant collector spec (e.g. `req-samsite-collector-identity`). This spec does not govern that decision; it governs what panels do once those nodes exist.

Vocabulary note: this spec uses TAP-wide terms — `entity`, `entity_type`, `node`. The word "artifact" appears only when discussing the originating `compliance_artifact` example, never as a generic synonym for "entity."

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Bookmarkable | A bare URL like `/<consumer>/<page>` (no query string) renders the latest entity matching the panel's fallback config. |
| 2. | Deep-linkable | A URL with the canonical entity_id query parameter renders that specific entity, even if it's not the latest. |
| 3. | Honest About Source | When the panel resolved the entity via fallback rather than explicit URL, the template context exposes a `used_fallback` flag so the rendered page can surface a "showing latest" banner. Users never see "the entity" without knowing which one. |
| 4. | One Helper, N Callers | The resolution code is one named module under `tap_web`, not duplicated per consumer panel. Consumer panels import the helpers and call them; they do not re-implement the Gryphon query or the sort. |
| 5. | Polished Failures | Missing URL var with no fallback configured, fallback configured with no matching entities, transient Gryphon errors, and "entity_id doesn't exist on the grid" all render distinct, user-readable error states — not stack traces. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-panel-entity-resolution-config | [Panel Config Contract](#panel-config-contract) | Proposed | `entity_id_var` + optional `fallback` block |
| req-web-panel-entity-resolution-order | [Resolution Order](#resolution-order) | Proposed | URL deep link wins; fallback runs only when URL var is empty |
| req-web-panel-entity-resolution-helper | [Shared Helper Module](#shared-helper-module) | Proposed | `tap_web.panels.entity_resolution` — `_lookup_by_entity_id`, `_lookup_latest_by_field`, `EntityResolution`, `resolve_entity` |
| req-web-panel-entity-resolution-latest-sort | [Latest Sort Semantics](#latest-sort-semantics) | Proposed | Gryphon for the row set; Python sort by a configurable timestamp field (default `data.fetched_at`), empties last |
| req-web-panel-entity-resolution-result-shape | [EntityResolution Dataclass](#entityresolution-dataclass) | Proposed | Fields: `entity_id`, `var_name`, `node`, `error`, `used_fallback`, `fallback_value`, `ok` (derived) |
| req-web-panel-entity-resolution-template | [Template Surface Conventions](#template-surface-conventions) | Proposed | `used_fallback` propagates to context; "Showing latest" banner when true |
| req-web-panel-entity-resolution-errors | [Polished Error States](#polished-error-states) | Proposed | Distinct messages per failure phase; entity_id and var_name echoed in the error so the user can fix the URL |
| req-web-panel-entity-resolution-multi | [Multi-Entity Panels](#multi-entity-panels) | Proposed | Per-entity resolution + per-entity fallback config when a panel needs more than one (samsite-ksi-scoreboard is the first instance) |
| req-web-panel-entity-resolution-tests | [Test Coverage Requirements](#test-coverage-requirements) | Proposed | Each consumer mocks the helpers and exercises explicit-URL / fallback / no-fallback / no-matches paths |

### Panel Config Contract
----
RID: `req-web-panel-entity-resolution-config`
Status: `Proposed`

A panel using this resolution pattern declares two config fields:

- `<role>_entity_id_var` — the **name** of the URL query parameter the panel reads. The panel does not hardcode the URL parameter name; consumers pick whatever fits the host page's naming. (Concrete examples: ROSCALE's SSP workbench uses `oscal_ssp_artifact_entity_id`, the POA&M workbench uses `oscal_poam_artifact_entity_id`; the same panel hosted on a different consumer page could read from a different name.)
- `fallback` — an optional block describing the entity to pick when the URL var is empty. The block carries a discriminator field name + value (and optionally an `entity_type`); absent → panel returns its "no entity specified" error when the URL var is empty.

For single-entity panels the config shape is:

```json
{
  "entity_id_var": "<page-variable-name>",
  "fallback": {
    "entity_type": "<entity_type slug, default compliance_artifact>",
    "field":       "<discriminator field on the entity, default \"kind\">",
    "value":       "<the value of that field to match>"
  }
}
```

For the `compliance_artifact` originating case, `entity_type` and `field` both default to compliance-artifact-specific values, so the shorthand is:

```json
{
  "entity_id_var": "<page-variable-name>",
  "fallback": { "value": "<compliance_artifact.kind value>" }
}
```

The legal values of `compliance_artifact.kind` are owned by the samsite collector manifest (`plugins/samsite/collectors/compliance_collector/artifact_manifest.json`) — v0 values include `oscal_ssp`, `oscal_poam`, `iiw`. This spec does not enumerate them; new kinds added by the collector are usable through this config without spec revision.

For multi-entity panels (`req-web-panel-entity-resolution-multi`), there is one `<role>_entity_id_var` per role and the `fallback` block carries per-role values. Example from the samsite KSI scoreboard:

```json
{
  "ssp_entity_id_var":  "oscal_ssp_artifact_entity_id",
  "poam_entity_id_var": "oscal_poam_artifact_entity_id",
  "fallback": {
    "ssp":  { "value": "oscal_ssp" },
    "poam": { "value": "oscal_poam" }
  }
}
```

#### Status Details

Existing panels (ROSCALE SSP/POA&M workbenches, samsite KSI scoreboard, samsite VDR ingestion health) carry the older `artifact_entity_id_var` / `fallback.kind` config keys. The helper module migration (`req-web-panel-entity-resolution-helper`) will read both old and new keys for a deprecation window so existing grift configs don't break; the migration ACIDs include rewriting those configs to the new keys.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-config-1 | URL Var Name In Config | Proposed | The panel reads `panel.config[<role>_entity_id_var]` and uses that string as the key into `request.GET`. | |
| req-web-panel-entity-resolution-config-2 | Fallback Optional | Proposed | A panel config without a `fallback` block is valid; the resolver returns its "no entity specified" error if the URL var is empty. | |
| req-web-panel-entity-resolution-config-3 | Defaults For Compliance Artifact | Proposed | When `fallback.entity_type` is absent it defaults to `compliance_artifact`; when `fallback.field` is absent it defaults to `kind`. | |
| req-web-panel-entity-resolution-config-4 | Old Keys Read During Migration | Proposed | The helper reads both `entity_id_var` (new) and `artifact_entity_id_var` (legacy), and both `fallback.value` and `fallback.kind`, until consumer configs are migrated. | |

### Resolution Order
----
RID: `req-web-panel-entity-resolution-order`
Status: `Proposed`

Per role / per entity:

1. **Explicit URL deep link wins.** If `request.GET[var_name]` is non-empty (after stripping whitespace), look up that `entity_id` via Gryphon. If found → `EntityResolution(node=<n>, used_fallback=False)`. If not found → polished "<entity_type> not found for entity_id '<id>'" error.
2. **Fallback when URL var is empty AND `fallback` is configured.** Run a Gryphon query for all nodes of the configured `entity_type` filtered by `data.<field> = <value>`, sort by `data.fetched_at` desc in Python (default; configurable), take the first. If found → `EntityResolution(node=<n>, used_fallback=True, fallback_value=<value>)`. If no matches → polished "no <entity_type> matching <field>=<value> found yet; run the collector at least once" error.
3. **Neither URL var nor fallback configured** → polished "no entity specified; append `?<var_name>=<entity_id>` to the URL" error.

Explicit URL deep link MUST win even when fallback is configured. This is the bookmarkable-deep-link guarantee: a URL with an entity_id reproduces a specific historical view regardless of what's currently latest.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-order-1 | URL Wins | Proposed | When both URL var has a value AND `fallback` is configured, the resolver uses the URL value and never queries for the fallback. | |
| req-web-panel-entity-resolution-order-2 | Fallback Marks Itself | Proposed | When fallback fires, the result's `used_fallback` is True and `fallback_value` is populated. | |
| req-web-panel-entity-resolution-order-3 | Explicit URL Miss Is Distinct | Proposed | URL var supplied but entity_id not on the grid produces a different error message than "no entity specified." | |

### Shared Helper Module
----
RID: `req-web-panel-entity-resolution-helper`
Status: `Proposed`

The canonical helpers live at **`tap_web/panels/entity_resolution.py`** and consist of:

- `EntityResolution` (dataclass) — result shape (see `req-web-panel-entity-resolution-result-shape`).
- `_lookup_by_entity_id(entity_id, *, entity_type="compliance_artifact") -> dict | None` — Gryphon `MATCH (n:<entity_type>) WHERE n.entity_id = $entity_id`, returns the envelope node or `None`.
- `_lookup_latest_by_field(value, *, entity_type="compliance_artifact", field="kind", sort_field="fetched_at") -> dict | None` — Gryphon `MATCH (n:<entity_type>) WHERE n.data.<field> = $value`, sort-by-`data.<sort_field>` desc in Python, returns the top node or `None`.
- `resolve_entity(panel, request, *, role=None, default_var_name) -> EntityResolution` — the orchestrator panels call. Reads config, walks the resolution order from `req-web-panel-entity-resolution-order`, returns the result.

The generic shape supports `compliance_artifact` (the originating use) and any future entity type that fits the same shape. Existing callers using `compliance_artifact` need no per-call parameters because that's the default.

#### Status Details

Lift carried out alongside this spec landing. Before the lift the helpers lived at `plugins/roscale/panels/_common.py` under their old names (`resolve_artifact`, `ArtifactResolution`, `_lookup_latest_by_kind`). After: the canonical module is `tap_web/panels/entity_resolution.py` with the renamed symbols; the roscale module, the samsite KSI scoreboard, and the samsite VDR ingestion health panels all import from there.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-helper-1 | Canonical Module | Proposed | The helpers live at `tap_web/panels/entity_resolution.py`; no consumer plugin re-implements them. | |
| req-web-panel-entity-resolution-helper-2 | Generic Entity Type | Proposed | The helpers accept an `entity_type` kwarg defaulting to `compliance_artifact` so future entity types use the same shape. | |
| req-web-panel-entity-resolution-helper-3 | ROSCALE Migrated | Proposed | `plugins/roscale/panels/_common.py` imports from the canonical module instead of defining the helpers locally. | |
| req-web-panel-entity-resolution-helper-4 | Scoreboard Migrated | Proposed | `plugins/samsite/panels/ksi_scoreboard/__init__.py` imports from the canonical module. | |
| req-web-panel-entity-resolution-helper-5 | VDR Health Migrated | Proposed | `plugins/samsite/panels/vdr_ingestion_health/__init__.py` imports from the canonical module. | |

### Latest Sort Semantics
----
RID: `req-web-panel-entity-resolution-latest-sort`
Status: `Proposed`

The "latest" determination is done in **Python**, not in Gryphon. Gryphon returns all matching rows (bounded by `default_limit=500`, `max_limit=2000`); the helper sorts them by `data.<sort_field>` descending and takes the first. The default `sort_field` is `fetched_at` (matching `compliance_artifact`'s collector-stamped timestamp); other entity types may pass a different sort field via the helper's `sort_field` kwarg.

Rationale: doing the sort in Gryphon would require dialect-specific `ORDER BY ... LIMIT 1` support and a more complex query shape. The Python sort is simple, the row counts are small (the originating samsite collector emits one entity per kind per night; even at a year of retention that's ~365 rows per kind), and it avoids encoding sort semantics into the helper that can't be re-used for a different sort key. Future work may push the sort into Gryphon if row counts grow; this is a hot-path optimization, not a correctness change.

`fetched_at` on `compliance_artifact` is a `CharField` populated with an ISO 8601 UTC timestamp by the collector. Lexical sort of ISO 8601 strings is equivalent to chronological order when the format is consistent (which the samsite collector guarantees). Empty `<sort_field>` values sort to the bottom (lexically lowest) — acceptable for "latest" semantics since empties are the most-recently-stuck-or-broken rows, not the most-recently-fetched. Other entity types using this helper SHOULD also use ISO 8601 strings for their chosen sort field.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-latest-sort-1 | Python Sort | Proposed | Sort happens in Python after Gryphon returns the row set; the Gryphon query has no ORDER BY. | |
| req-web-panel-entity-resolution-latest-sort-2 | Empties Last | Proposed | Rows with empty `<sort_field>` sort to the bottom; they never win the "latest" pick when any non-empty row exists. | |
| req-web-panel-entity-resolution-latest-sort-3 | Limits Documented | Proposed | The `default_limit=500` / `max_limit=2000` choices are documented in the helper module; consumers needing higher limits raise a follow-up issue rather than overriding silently. | |
| req-web-panel-entity-resolution-latest-sort-4 | Sort Field Override | Proposed | The helper accepts a `sort_field` kwarg defaulting to `fetched_at`; other entity types may pass a different field. | |

### EntityResolution Dataclass
----
RID: `req-web-panel-entity-resolution-result-shape`
Status: `Proposed`

The result shape:

```python
@dataclass
class EntityResolution:
    entity_id: str                    # the entity_id that was resolved (or attempted)
    var_name: str                     # which URL var name was read
    node: dict[str, Any] | None       # the on-grid node (Gryphon envelope shape), or None on failure
    error: str | None                 # polished user-readable error, or None on success
    used_fallback: bool = False       # True iff the fallback path won
    fallback_value: str | None = None # the discriminator value used by the fallback, when applicable

    @property
    def ok(self) -> bool:
        return self.node is not None and self.error is None
```

The dataclass MUST NOT grow consumer-specific fields (no `oscal_root`, no `system_class`, etc.). Consumer-specific derived state lives on the consumer panel's context dict, not on `EntityResolution`. This keeps the result shape stable across panel types.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-result-shape-1 | Stable Fields | Proposed | The six fields + `ok` property listed above are the entire public surface; new fields require this spec to bump. | |
| req-web-panel-entity-resolution-result-shape-2 | No Consumer Coupling | Proposed | The dataclass does not carry consumer-specific derived state (e.g., parsed OSCAL document). Consumers do that downstream. | |

### Template Surface Conventions
----
RID: `req-web-panel-entity-resolution-template`
Status: `Proposed`

Consumer panels MUST propagate at minimum these fields from their `EntityResolution` to template context:

- `used_fallback` (bool)
- `fallback_value` (str | None)
- `entity_id` (str)
- `var_name` (str)

And render a "Showing latest" banner when `used_fallback` is True. The banner SHOULD identify:

- That the panel auto-resolved (not a deep link)
- Which URL var name would override the fallback (so users know how to deep-link to a specific entity)
- The fallback discriminator value (so users know what was searched)
- The entity_id that was picked (so users can copy it into a stable bookmark)

ROSCALE's existing `<section class="roscale-fallback-banner">` is the reference rendering; consumer panels MAY use their own CSS class names but the information density should match. Multi-entity panels render one banner-row that names which entities came from fallback.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-template-1 | used_fallback Propagated | Proposed | The bool reaches the template context unchanged. | |
| req-web-panel-entity-resolution-template-2 | Banner When True | Proposed | The template includes a visible banner when `used_fallback` is True. | |
| req-web-panel-entity-resolution-template-3 | Banner Identifies Override Path | Proposed | The banner tells the user which URL var to use to deep-link to a specific entity. | |

### Polished Error States
----
RID: `req-web-panel-entity-resolution-errors`
Status: `Proposed`

Five failure phases, each with a distinct `error` message on the `EntityResolution`:

| Phase | When | Error message shape |
| --- | --- | --- |
| `source` | No URL var set, no `fallback` configured | "No entity specified. Expected page variable '<var_name>' in the URL." |
| `load` (URL miss) | URL var supplied, entity_id not found on the grid | "<entity_type> not found for entity_id '<id>'." |
| `load` (fallback empty) | Fallback configured, no matches for the discriminator value | "No <entity_type> matching <field>='<value>' found on the grid yet. Run the collector at least once, then reload." |
| `load` (transient) | Gryphon raised | "Entity lookup failed: <exc>" or "Entity fallback lookup failed: <exc>" — logged with a stable short-id (`[ros1]`, `[ros2]`, …) for grep-ability |
| `parse` / `root-detect` | (downstream of resolution; not this helper's concern but the contract is that the resolver's error phase is `load` or `source`, never `parse`) | Handled by the consumer panel |

Templates SHOULD show the error phase as a small `[load]` tag adjacent to the error message so support / debugging conversations can quickly point at the failure layer. ROSCALE's existing error-state markup is the reference.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-errors-1 | Distinct Per Phase | Proposed | Each failure phase produces a distinguishable error string; templates can pattern-match. | |
| req-web-panel-entity-resolution-errors-2 | Echo The Inputs | Proposed | The error string includes the entity_id, var_name, or fallback discriminator that was attempted, so users can fix the URL or config. | |
| req-web-panel-entity-resolution-errors-3 | Short-Id Logging | Proposed | Transient (exception) failures log with a stable short-id so they're greppable in container logs. | |

### Multi-Entity Panels
----
RID: `req-web-panel-entity-resolution-multi`
Status: `Proposed`

Some panels need more than one entity to render (the samsite KSI scoreboard needs both an OSCAL SSP and an OSCAL POA&M; future scoreboards may need a VDR report too). For these:

- Each entity has a **role** name (`ssp`, `poam`, etc.) that prefixes its config keys: `<role>_entity_id_var`, and the role appears as a sub-block under `fallback` (`fallback.<role>`).
- Each entity is resolved independently. One can fall back while another deep-links; one can miss while another succeeds.
- The panel decides per role whether the entity is **required** (missing it is a hard error) or **degraded** (missing it lets the panel render in a reduced mode and surface a warning). The samsite KSI scoreboard treats SSP as required and POA&M as degraded (scoring proceeds with no POA&M coverage applied).
- Each role's `used_fallback` propagates separately to context (e.g. `ssp_used_fallback`, `poam_used_fallback`) so the template can show a combined "Showing latest" line that names which entities came from fallback.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-multi-1 | Per-Role Config | Proposed | The config carries one `<role>_entity_id_var` per role plus a `fallback` block with per-role sub-blocks. | |
| req-web-panel-entity-resolution-multi-2 | Independent Resolution | Proposed | Each role is resolved through `resolve_entity` separately; one role's failure does not short-circuit the other. | |
| req-web-panel-entity-resolution-multi-3 | Required vs Degraded | Proposed | The panel declares per-role whether absence is a hard fail or a degraded render; both modes are valid. | |

### Test Coverage Requirements
----
RID: `req-web-panel-entity-resolution-tests`
Status: `Proposed`

Each consumer panel MUST have unit tests (no Django/DB setup required) covering:

- **Explicit URL deep link wins over fallback** — both URL var and fallback configured; only `_lookup_by_entity_id` is called.
- **Fallback fires when URL var empty** — URL var absent, fallback configured; `_lookup_latest_by_field` is called and `used_fallback` is True.
- **No URL var, no fallback** — polished "no entity specified" error.
- **Fallback configured but no matches** — polished "no <entity_type> matching <field>=<value> yet" error.
- **Sort correctness** — `_lookup_latest_by_field` picks the highest sort-field value from a shuffled set (one test in `tap_web/tests/` suffices since the helper is shared).

Tests mock the two helper functions at the importing module's path (not at `tap_web.panels.entity_resolution`) — see ROSCALE's `tests/test_roscale_panels.py` for the pattern.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-tests-1 | Per-Consumer Coverage | Proposed | Each consumer panel has the four resolution-path tests listed above. | |
| req-web-panel-entity-resolution-tests-2 | Sort Test In Helper Home | Proposed | One sort-correctness test lives with the helper at `tap_web/tests/test_panel_entity_resolution.py`. | |

## Future Work

Not in v0 scope but worth naming as future seams:

- **Gryphon-side sort.** If row counts grow (10K+ entities of a type), push the sort into Gryphon via an explicit ORDER BY when the dialect supports it. Until then, Python sort is fine.
- **Edit-mode resolution.** The current resolution is read-only. If a panel ever needs to *write* to the resolved entity (e.g. ROSCALE's deferred OSCAL editing), the helper grows a `for_edit=True` mode that locks or branches per the data model's edit semantics. Out of scope.
- **History timeline panel.** A panel that resolves *N* versions rather than just the latest, for drift / regression visualization. Same `_lookup_latest_by_field` becomes `_lookup_recent_n_by_field`. Worth doing once a real use case appears (the KSI scoreboard's `req-samsite-scoreboard-history` is the candidate).
- **Drop the legacy config keys.** Once all consumer panels are migrated to `entity_id_var` / `fallback.value`, the helper stops reading `artifact_entity_id_var` / `fallback.kind`.
