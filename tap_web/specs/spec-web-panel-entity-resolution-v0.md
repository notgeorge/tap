# Panel Entity Resolution Specification

## Philosophy

Several TAP panels render content derived from a single on-grid entity. The entity is picked one of two ways: either the caller deep-links by passing the entity's `entity_id` as a URL query parameter (bookmarkable, stable across time), or the panel falls back to *a specific entity of a configured shape* when the URL is bare (always-render-something default). Either way, the rendered page should make it clear which path was taken so the user knows whether they're looking at a deep-linked entity or one picked by the fallback.

A *configured shape* is the combination of three things: which entity type to look in, what filter narrows the candidates, and — when the filter matches more than one candidate — what **selection strategy** picks the winner. Temporal ordering ("the latest one by some timestamp field") is one common selection strategy, not the only one. Other consumers may want "the single match, error if ambiguous," or future strategies we haven't enumerated. The spec lays out the contract; the platform doesn't assume a winner.

This spec governs **panel-side resolution**. Per-emission identity semantics for the *entities themselves* (why nodes accumulate over time rather than upserting in place, when and why a discriminator field carries a particular value) live with the relevant collector spec. This spec does not govern those decisions; it governs what panels do once those nodes exist.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Bookmarkable | A bare URL like `/<consumer>/<page>` (no query string) renders the fallback entity the panel's config describes. |
| 2. | Deep-linkable | A URL with the canonical entity_id query parameter renders that specific entity. |
| 3. | Honest About Source | When the panel resolved the entity via fallback rather than explicit URL, the template context exposes a `used_fallback` flag so the rendered page can surface a "showing fallback selection" banner. Users never see "the entity" without knowing which one. |
| 4. | One Helper, N Callers | The resolution code is one named module under `tap_web`, not duplicated per consumer panel. Consumer panels import the helpers and call them; they do not re-implement the Gryphon query, the filter, or the selection. |
| 5. | Polished Failures | Missing URL var with no fallback configured, fallback filter matching zero entities, fallback filter matching multiple entities when the selection strategy expects one, transient Gryphon errors, and "entity_id doesn't exist on the grid" all render distinct, user-readable error states — not stack traces. |
| 6. | No Privileged Defaults | The helper does not bake in domain-specific entity types, field names, sort fields, or selection strategies. Every panel config supplies its own values; the platform spec stays neutral. |
| 7. | Explicit Selection Strategy | The strategy used to pick from filter matches is named in the config, never assumed. "Temporal latest" is one strategy among many; the platform doesn't presume it's the default. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-panel-entity-resolution-config | [Panel Config Contract](#panel-config-contract) | Proposed | `entity_id_var` + optional `fallback` block; fallback names entity_type, filter, and selection strategy |
| req-web-panel-entity-resolution-order | [Resolution Order](#resolution-order) | Proposed | URL deep link wins; fallback runs only when URL var is empty |
| req-web-panel-entity-resolution-helper | [Shared Helper Module](#shared-helper-module) | Proposed | `tap_web.panels.entity_resolution` — `_lookup_by_entity_id`, `_lookup_single_by_field`, `_lookup_latest_by_field`, `EntityResolution`, `resolve_entity` |
| req-web-panel-entity-resolution-selection | [Selection Strategies](#selection-strategies) | Proposed | v0 strategies: `single` (one match expected) and `latest_by` (sort + first). Strategy is named in the config, never assumed. |
| req-web-panel-entity-resolution-result-shape | [EntityResolution Dataclass](#entityresolution-dataclass) | Proposed | Fields: `entity_id`, `var_name`, `node`, `error`, `used_fallback`, `fallback_value`, `ok` (derived) |
| req-web-panel-entity-resolution-template | [Template Surface Conventions](#template-surface-conventions) | Proposed | `used_fallback` propagates to context; "Showing fallback selection" banner when true |
| req-web-panel-entity-resolution-errors | [Polished Error States](#polished-error-states) | Proposed | Distinct messages per failure phase including ambiguous-match for `selection=single`; entity_id and var_name echoed |
| req-web-panel-entity-resolution-multi | [Multi-Entity Panels](#multi-entity-panels) | Proposed | Per-entity resolution + per-entity fallback config when a panel needs more than one |
| req-web-panel-entity-resolution-tests | [Test Coverage Requirements](#test-coverage-requirements) | Proposed | Each consumer mocks the helpers and exercises explicit-URL / fallback / no-fallback / no-matches / ambiguous paths |

### Panel Config Contract
----
RID: `req-web-panel-entity-resolution-config`
Status: `Proposed`

A panel using this resolution pattern declares two config fields:

- `<role>_entity_id_var` — the **name** of the URL query parameter the panel reads. The panel does not hardcode the URL parameter name; consumers pick whatever fits the host page's naming.
- `fallback` — an optional block describing the entity to pick when the URL var is empty. When present, the block carries the entity type, a filter (`field` + `value`), and a selection strategy (`selection`). Strategy-specific fields are required when that strategy is named. Absent `fallback` block → panel returns its "no entity specified" error when the URL var is empty.

The fallback block is shaped:

```json
{
  "entity_id_var": "<page-variable-name>",
  "fallback": {
    "entity_type": "<entity_type slug>",
    "field":       "<discriminator field on the entity>",
    "value":       "<the value of that field to match>",
    "selection":   "<strategy name>",
    "...strategy-specific fields..."
  }
}
```

For example, with the `latest_by` selection strategy (which requires a `sort_field`):

```json
{
  "entity_id_var": "<page-variable-name>",
  "fallback": {
    "entity_type": "<entity_type slug>",
    "field":       "<discriminator field>",
    "value":       "<filter value>",
    "selection":   "latest_by",
    "sort_field":  "<timestamp field used to pick the latest>"
  }
}
```

Or with the `single` selection strategy (which expects the filter to match exactly one entity and has no strategy-specific fields):

```json
{
  "entity_id_var": "<page-variable-name>",
  "fallback": {
    "entity_type": "<entity_type slug>",
    "field":       "<discriminator field>",
    "value":       "<filter value>",
    "selection":   "single"
  }
}
```

All four core fallback fields (`entity_type`, `field`, `value`, `selection`) are required when the `fallback` block is present. The platform has no defaults — every consumer states explicitly what it's resolving and how. A panel that wants no fallback omits the `fallback` block entirely.

For multi-entity panels (`req-web-panel-entity-resolution-multi`), there is one `<role>_entity_id_var` per role and the `fallback` block carries per-role sub-blocks:

```json
{
  "<role-a>_entity_id_var": "<page-variable-name-a>",
  "<role-b>_entity_id_var": "<page-variable-name-b>",
  "fallback": {
    "<role-a>": {
      "entity_type": "...",
      "field":       "...",
      "value":       "...",
      "selection":   "...",
      "...strategy-specific fields..."
    },
    "<role-b>": {
      "entity_type": "...",
      "field":       "...",
      "value":       "...",
      "selection":   "...",
      "...strategy-specific fields..."
    }
  }
}
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-config-1 | URL Var Name In Config | Proposed | The panel reads `panel.config[<role>_entity_id_var]` and uses that string as the key into `request.GET`. | |
| req-web-panel-entity-resolution-config-2 | Fallback Optional | Proposed | A panel config without a `fallback` block is valid; the resolver returns its "no entity specified" error if the URL var is empty. | |
| req-web-panel-entity-resolution-config-3 | Core Fallback Fields Required | Proposed | When `fallback` is present, the four core fields (`entity_type`, `field`, `value`, `selection`) MUST be set. A partially-specified fallback is a config error. | |
| req-web-panel-entity-resolution-config-4 | Strategy-Specific Fields Required | Proposed | Fields required by the named selection strategy (e.g., `sort_field` for `latest_by`) MUST be set. Missing them is a config error. | |

### Resolution Order
----
RID: `req-web-panel-entity-resolution-order`
Status: `Proposed`

Per role / per entity:

1. **Explicit URL deep link wins.** If `request.GET[var_name]` is non-empty (after stripping whitespace), look up that `entity_id` via Gryphon. If found → `EntityResolution(node=<n>, used_fallback=False)`. If not found → polished "<entity_type> not found for entity_id '<id>'" error.
2. **Fallback when URL var is empty AND `fallback` is configured.** Run a Gryphon query for all nodes of the configured `entity_type` filtered by `data.<field> = <value>`, then apply the configured `selection` strategy to the result set (see `req-web-panel-entity-resolution-selection`). If the strategy yields a winner → `EntityResolution(node=<n>, used_fallback=True, fallback_value=<value>)`. If the strategy yields no winner → polished error specific to the failure mode (no matches at all, ambiguous matches for `single`, etc.).
3. **Neither URL var nor fallback configured** → polished "no entity specified; append `?<var_name>=<entity_id>` to the URL" error.

Explicit URL deep link MUST win even when fallback is configured. This is the bookmarkable-deep-link guarantee: a URL with an entity_id reproduces a specific historical view regardless of what's currently in the fallback's selection window.

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
- `_lookup_by_entity_id(entity_id, *, entity_type) -> dict | None` — Gryphon `MATCH (n:<entity_type>) WHERE n.entity_id = $entity_id`, returns the envelope node or `None`. `entity_type` is required; the helper has no platform default.
- `_lookup_single_by_field(value, *, entity_type, field) -> dict | tuple[None, int]` — Gryphon `MATCH (n:<entity_type>) WHERE n.data.<field> = $value`, expects exactly one match. Returns the matched node, or a sentinel (`None, count`) when zero or multiple matched so the caller can distinguish "no entity found" from "ambiguous filter."
- `_lookup_latest_by_field(value, *, entity_type, field, sort_field) -> dict | None` — Gryphon `MATCH (n:<entity_type>) WHERE n.data.<field> = $value`, sort-by-`data.<sort_field>` desc in Python, returns the top node or `None`. All three kwargs are required.
- `resolve_entity(panel, request, *, role=None, default_var_name) -> EntityResolution` — the orchestrator panels call. Reads config, walks the resolution order from `req-web-panel-entity-resolution-order`, dispatches on `selection` to pick the right lookup helper, returns the result.

No consumer plugin re-implements these helpers. Consumer plugins migrate any local equivalents to import from this canonical module; the per-plugin migration steps live in each consumer plugin's spec.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-helper-1 | Canonical Module | Proposed | The helpers live at `tap_web/panels/entity_resolution.py`; no consumer plugin re-implements them. | |
| req-web-panel-entity-resolution-helper-2 | No Privileged Defaults | Proposed | Helper kwargs (`entity_type`, `field`, `sort_field`) are required — no default values. | |
| req-web-panel-entity-resolution-helper-3 | Stable Return Shape | Proposed | The lookup helpers return either an envelope node dict or `None` (with strategy-specific extra signal for ambiguity); none raise on "not found." Transient Gryphon errors raise. | |
| req-web-panel-entity-resolution-helper-4 | Strategy Dispatch In Orchestrator | Proposed | `resolve_entity` reads `fallback.selection` and dispatches to the appropriate `_lookup_*` helper; new strategies are added by extending the dispatch, not by changing the orchestrator's signature. | |

### Selection Strategies
----
RID: `req-web-panel-entity-resolution-selection`
Status: `Proposed`

When the URL var is empty and the fallback filter narrows the entity_type to a candidate set, a **selection strategy** decides which candidate (if any) the panel renders. The strategy is named in the panel config (`fallback.selection`); the platform does not assume one. v0 enumerates two strategies; future strategies are added by extending the dispatch in `resolve_entity` and adding a sibling `_lookup_*` helper.

#### v0 selection strategies

| Strategy | Required strategy-specific fields | Behavior |
| --- | --- | --- |
| `single` | (none) | The filter is expected to identify exactly one entity. Zero matches → "no entity matching <field>=<value>" error. Multiple matches → "ambiguous: <N> entities match <field>=<value> with selection=single" error (with a hint to refine the filter or pick a different strategy). |
| `latest_by` | `sort_field` (string — the field on `data` to sort by) | Sort the filter's candidate set by `data.<sort_field>` descending in Python, take the first. Empties sort to the bottom (lexically lowest), so they never win when any non-empty value exists. Suitable for ISO 8601 timestamps where lexical and chronological order agree. |

#### Why `latest_by` sorts in Python, not Gryphon

Doing the sort in Gryphon would require dialect-specific `ORDER BY ... LIMIT 1` support and a more complex query shape. Python sort is simple, the row counts in v0 use cases are small (low hundreds at most), and it keeps the helper general — no sort semantics baked into the Gryphon query that can't be re-used. Future work may push the sort into Gryphon if row counts grow; this is a hot-path optimization, not a correctness change. The Gryphon query is bounded by `default_limit=500`, `max_limit=2000`.

#### Adding a new strategy (future)

To add a strategy like `min_by` or `highest_priority`:

1. Add a sibling `_lookup_<strategy>_by_field` helper (or a more specific name) with whatever extra kwargs the strategy needs.
2. Extend the `resolve_entity` dispatch to call the new helper when `fallback.selection == "<new-strategy>"`.
3. Document the new strategy's required fields in the table above.

The orchestrator signature does not change. The `EntityResolution` dataclass does not grow strategy-specific fields.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-selection-1 | Strategy Named | Proposed | `fallback.selection` is required when `fallback` is present; the platform does not default it. | |
| req-web-panel-entity-resolution-selection-2 | v0 Strategies Available | Proposed | `single` and `latest_by` are implemented and documented. | |
| req-web-panel-entity-resolution-selection-3 | Single Surfaces Ambiguity | Proposed | When `selection=single` matches multiple entities, the resolver produces an ambiguity error distinct from "no match." | |
| req-web-panel-entity-resolution-selection-4 | Python Sort For latest_by | Proposed | The `latest_by` strategy sorts in Python after Gryphon returns the candidate set; the Gryphon query has no ORDER BY. | |
| req-web-panel-entity-resolution-selection-5 | latest_by Empties Last | Proposed | Rows with empty `<sort_field>` sort to the bottom under `latest_by`; they never win when any non-empty value exists. | |
| req-web-panel-entity-resolution-selection-6 | Limits Documented | Proposed | The `default_limit=500` / `max_limit=2000` Gryphon limits are documented in the helper module; consumers needing higher limits raise a follow-up issue rather than overriding silently. | |
| req-web-panel-entity-resolution-selection-7 | Strategy Dispatch Open To Extension | Proposed | New strategies are added by extending the dispatch in `resolve_entity` + adding a sibling helper, without changing the orchestrator signature or the `EntityResolution` dataclass. | |

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

The dataclass MUST NOT grow consumer-specific fields. Consumer-specific derived state lives on the consumer panel's context dict, not on `EntityResolution`. This keeps the result shape stable across panel types.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-result-shape-1 | Stable Fields | Proposed | The six fields + `ok` property listed above are the entire public surface; new fields require this spec to bump. | |
| req-web-panel-entity-resolution-result-shape-2 | No Consumer Coupling | Proposed | The dataclass does not carry consumer-specific derived state. Consumers derive that downstream from `node`. | |

### Template Surface Conventions
----
RID: `req-web-panel-entity-resolution-template`
Status: `Proposed`

Consumer panels MUST propagate at minimum these fields from their `EntityResolution` to template context:

- `used_fallback` (bool)
- `fallback_value` (str | None)
- `entity_id` (str)
- `var_name` (str)

And render a "Showing fallback selection" banner when `used_fallback` is True. The banner SHOULD identify:

- That the panel auto-resolved (not a deep link)
- Which URL var name would override the fallback (so users know how to deep-link to a specific entity)
- The fallback discriminator value (so users know what was searched)
- The entity_id that was picked (so users can copy it into a stable bookmark)

Multi-entity panels render one banner row per role that fell back, or a combined banner that names which entities came from fallback.

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

Six failure phases, each with a distinct `error` message on the `EntityResolution`:

| Phase | When | Error message shape |
| --- | --- | --- |
| `source` | No URL var set, no `fallback` configured | "No entity specified. Expected page variable '<var_name>' in the URL." |
| `load` (URL miss) | URL var supplied, entity_id not found on the grid | "<entity_type> not found for entity_id '<id>'." |
| `load` (fallback empty) | Fallback configured, filter matched zero entities | "No <entity_type> matching <field>='<value>' found on the grid yet." |
| `load` (fallback ambiguous) | `selection=single`, filter matched multiple entities | "Ambiguous: <N> <entity_type> entities match <field>='<value>' with selection=single. Refine the filter or use a different selection strategy." |
| `load` (transient) | Gryphon raised | "Entity lookup failed: <exc>" or "Entity fallback lookup failed: <exc>" — logged with a stable short-id for grep-ability |
| `parse` / `root-detect` | (downstream of resolution; not this helper's concern but the contract is that the resolver's error phase is `load` or `source`, never `parse`) | Handled by the consumer panel |

Templates SHOULD show the error phase as a small `[load]` tag adjacent to the error message so support / debugging conversations can quickly point at the failure layer.

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

Some panels need more than one entity to render. For these:

- Each entity has a **role** name that prefixes its config keys: `<role>_entity_id_var`, and the role appears as a sub-block under `fallback` (`fallback.<role>`).
- Each entity is resolved independently. One can fall back while another deep-links; one can miss while another succeeds.
- The panel decides per role whether the entity is **required** (missing it is a hard error) or **degraded** (missing it lets the panel render in a reduced mode and surface a warning).
- Each role's `used_fallback` propagates separately to context (e.g. `<role-a>_used_fallback`, `<role-b>_used_fallback`) so the template can show a combined banner that names which entities came from fallback.

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
- **Fallback fires when URL var empty** — URL var absent, fallback configured; the strategy-specific lookup helper is called and `used_fallback` is True.
- **No URL var, no fallback** — polished "no entity specified" error.
- **Fallback configured but no matches** — polished "no <entity_type> matching <field>=<value> yet" error.
- **Fallback ambiguous (when `selection=single`)** — filter matches multiple entities; polished "ambiguous: N matches with selection=single" error. Skip this test for consumers that don't use `selection=single`.
- **Strategy-specific correctness** — for `selection=latest_by`, `_lookup_latest_by_field` picks the highest sort-field value from a shuffled set. For `selection=single`, `_lookup_single_by_field` returns the single match and surfaces ambiguity. One sort + one single-match correctness test in `tap_web/tests/` suffices since the helpers are shared.

Tests mock the two helper functions at the importing module's path (not at `tap_web.panels.entity_resolution`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-entity-resolution-tests-1 | Per-Consumer Coverage | Proposed | Each consumer panel has the four resolution-path tests listed above. | |
| req-web-panel-entity-resolution-tests-2 | Sort Test In Helper Home | Proposed | One sort-correctness test lives with the helper at `tap_web/tests/test_panel_entity_resolution.py`. | |

## Future Work

Not in v0 scope but worth naming as future seams:

- **Gryphon-side sort.** If row counts grow (10K+ entities of a type), push the sort into Gryphon via an explicit ORDER BY when the dialect supports it. Until then, Python sort is fine.
- **Edit-mode resolution.** The current resolution is read-only. If a panel ever needs to *write* to the resolved entity, the helper grows a `for_edit=True` mode that locks or branches per the data model's edit semantics. Out of scope.
- **History timeline panel.** A panel that resolves *N* versions rather than just the latest, for drift / regression visualization. Same `_lookup_latest_by_field` becomes `_lookup_recent_n_by_field`. Worth doing once a real use case appears.
