# Grid Hotlink Specification

## Philosophy

Hotlinks standardize the case where a node stores one or more references in its own data, while the graph also materializes those same relationships as typed edges. Without a formal contract, the node payload and the edge set can drift apart: a node may name things that no longer have edges, or edges may continue to exist after the node stops referencing them.

The hotlink system makes this relationship explicit at the model level. Models declare `HOTLINKS` as authoritative metadata describing where references live inside their fields and how those references map onto edges. The service layer uses that declaration to validate graph consistency during writes.

Hotlinks do not replace edges and do not make embedded references authoritative. The edge remains the graph-level relationship. The hotlink declaration exists to define the contract between a node's embedded reference data and the corresponding edge set.

In addition to the model-level declaration, participating edges carry explicit hotlink instance data in `properties.hotlink`. This makes hotlink participation obvious when inspecting an edge directly, without secondary inference from ad hoc property keys.

## Goals

|    |               |                                                                                              |
| :---: | ---        | ---                                                                                          |
| 1. | Standardized   | Models declare node-to-edge reference mappings in one consistent structure                    |
| 2. | Validated      | Service-layer writes can verify that embedded references and edge materialization agree       |
| 3. | Extensible     | Multiple selector backends can be supported over time without changing the top-level contract |
| 4. | Incremental    | Existing model behavior can adopt hotlinks declaratively without rewriting read-time logic    |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-hotlink-model | [Hotlink Model Declaration](#hotlink-model-declaration) | Implemented | `HOTLINKS` on `BaseModel` subclasses is the source of truth |
| req-grid-hotlink-edge-data | [Hotlink Edge Instance Data](#hotlink-edge-instance-data) | Implemented | Participating edges carry explicit `properties.hotlink` metadata |
| req-grid-hotlink-selector | [Hotlink Selector System](#hotlink-selector-system) | Implemented | v1 uses a simple TAP path selector; selector backends are pluggable |
| req-grid-hotlink-validation | [Hotlink Validation Semantics](#hotlink-validation-semantics) | Implemented | Service layer validates extracted references against edges |
| req-grid-hotlink-mutation | [Hotlink Mutation Boundaries](#hotlink-mutation-boundaries) | Proposed | Reverse edge-mutation protection is a planned next phase |

## Explanation

The canonical motivating example is the page-to-panel mapping in `tap_web`. A `Page` stores panel identifiers inside its `layout` JSON field. The actual graph linkage is expressed by outbound `USES_PANEL` edges. Today the join is performed through `properties["panel-id"]`. The hotlink system replaces that loose property convention with an explicit `properties.hotlink` object and a model-level declaration that formalizes:

1. which field contains the embedded references,
2. how to extract the identifiers from that field,
3. which edge type the identifiers correspond to, and
4. how the edge's hotlink instance data identifies the hotlink definition and carries the matched value.

With that declaration in place, the service layer can validate hotlink consistency when saving the node. For `Page`, the intended invariant is `exact`: the set of panel IDs extracted from `layout` must exactly match the set of `hotlink.value` values found on the page's relevant `USES_PANEL` edges whose `hotlink.model` is `page` and whose `hotlink.spec` is `page-panels`.

The hotlink system is intentionally defined as a generic `tap_grid` feature, not a page-specific validator. Other models will eventually use other selector backends, such as structured extraction from XML or free text. The top-level contract should stay stable while selector implementations evolve underneath it.

### Hotlink Model Declaration
----
RID: `req-grid-hotlink-model`
Status: `Implemented`

Concrete `BaseModel` subclasses may declare a class-level `HOTLINKS` registry describing embedded references that correspond to graph edges. `HOTLINKS` is the authoritative declaration of hotlink behavior. Participating edges carry instance-level hotlink data, but they do not define hotlink meaning on their own.

#### Status Details
Implemented in `tap_grid`. `HOTLINKS` is a `ClassVar[list[dict]]` on `BaseModel`. Startup validation runs in `__init_subclass__` via `_check_hotlinks`. `Page` in `tap_web` carries the first concrete declaration.

#### Implementation
`HOTLINKS` is a class variable on a `BaseModel` subclass. It is a list of hotlink definition objects. Each definition describes one mapping between embedded references in the node and one family of edges.

Each hotlink definition includes:

| Key | Required | Description |
| --- | --- | --- |
| `name` | Yes | Stable identifier for the hotlink definition within the model |
| `field` | Yes | Model field name containing the source data to inspect |
| `selector_type` | Yes | Extraction backend identifier, such as `path` in v1 |
| `selector` | Yes | Selector string interpreted by the chosen backend |
| `edge_direction` | Yes | Direction of the corresponding edges relative to the node, such as `outbound` |
| `edge_type` | Yes | Edge type that materializes the embedded references |
| `mode` | Yes | Validation mode: `exists`, `unique`, or `exact` |

Optional metadata may be added later, but v1 should remain intentionally narrow.

Conceptual example for `Page`:

```python
HOTLINKS = [
    {
        "name": "page-panels",
        "field": "layout",
        "selector_type": "simple_path",
        "selector": "columns.*.rows.*.panel-id",
        "edge_direction": "outbound",
        "edge_type": "USES_PANEL",
        "mode": "exact",
    }
]
```

This declaration does not change the existing read path. It only formalizes the contract that the service layer can enforce.

#### Development
Keeping `HOTLINKS` separate from `FIELD_SCHEMAS` is intentional. `FIELD_SCHEMAS` governs field shape and field-level validation. Hotlinks govern graph consistency between a node payload and materialized edges. Mixing the two would blur schema validation and relationship validation.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-hotlink-model-1 | Model-Level Registry | Implemented | A `BaseModel` subclass may declare `HOTLINKS` as a class-level list of definition objects. | |
| req-grid-hotlink-model-2 | Authoritative Definition | Implemented | `HOTLINKS` is the authoritative declaration of hotlink meaning; edge hotlink data identifies participation but does not redefine the contract. | |
| req-grid-hotlink-model-3 | Narrow Required Keys | Implemented | Each hotlink definition must declare `name`, `field`, `selector_type`, `selector`, `edge_direction`, `edge_type`, and `mode`. | |
| req-grid-hotlink-model-4 | Multiple Definitions Supported | Implemented | A model may declare more than one hotlink definition when multiple embedded reference systems exist. | |

#### Future
Startup validation of `HOTLINKS` declarations is now implemented alongside `FIELD_SCHEMAS` via `_check_hotlinks` in `__init_subclass__`.


### Hotlink Edge Instance Data
----
RID: `req-grid-hotlink-edge-data`
Status: `Implemented`

Edges that participate in a hotlink carry explicit instance data in `properties.hotlink`. This makes the hotlink visible on the edge itself and provides enough information for readers to resolve the owning model and hotlink definition through the entity model registry.

#### Status Details
Implemented. Seeder and service layer write `properties.hotlink`. `page_service.get_page_panels()` reads `hotlink.value`. Data migration `tap_web/migrations/0005` backfills existing edges.

#### Implementation
Participating edges store a reserved `hotlink` object inside `properties`:

```json
{
  "hotlink": {
    "model": "page",
    "spec": "page-panels",
    "value": "main"
  }
}
```

Field meanings:

| Key | Description |
| --- | --- |
| `model` | The entity type slug of the model that declared the hotlink definition, such as `page` |
| `spec` | The `HOTLINKS[].name` value on that model, such as `page-panels` |
| `value` | The specific identifier value this edge materializes for that hotlink instance |

The resolution path is:

1. read `properties.hotlink.model`,
2. resolve the model class via the entity model registry,
3. inspect that model's `HOTLINKS`,
4. find the definition whose `name` matches `properties.hotlink.spec`.

The edge-side hotlink object is intentionally narrow. It should not duplicate selector configuration, validation mode, field names, or other model-level contract data.

This change requires the current page/panel implementation to migrate away from the loose `properties["panel-id"]` convention. The `USES_PANEL` edge payload and the surrounding panel-id handling code will need to write and read `properties.hotlink.value` instead. The page layout format remains the source of embedded panel identifiers, but the join contract between layout and edges now uses the explicit hotlink object.

#### Development
Making hotlink participation explicit on the edge improves debuggability and future mutation protection. A reader inspecting an edge no longer has to infer that a field like `panel-id` is participating in a hotlink contract.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-hotlink-edge-data-1 | Explicit Edge Object | Implemented | An edge participating in a hotlink stores a `properties.hotlink` object rather than relying on an ad hoc top-level join key. | |
| req-grid-hotlink-edge-data-2 | Globally Qualified Reference | Implemented | `properties.hotlink` includes `model` and `spec`, allowing readers to resolve the hotlink definition without hidden context. | |
| req-grid-hotlink-edge-data-3 | Value Stored On Edge | Implemented | `properties.hotlink.value` stores the identifier value materialized by that edge instance. | |
| req-grid-hotlink-edge-data-4 | No Redundant Contract Data | Implemented | Edge-side hotlink data does not duplicate selector rules, validation mode, or other model-level contract fields. | |
| req-grid-hotlink-edge-data-5 | Page Panel Migration Required | Implemented | The existing page/panel implementation must migrate from `properties[\"panel-id\"]` to `properties.hotlink` and update the panel-id handling path accordingly. | |

#### Future
If needed, additional edge-side metadata may be added under `properties.hotlink`, but only when it clearly represents edge-instance state rather than duplicated model definition.


### Hotlink Selector System
----
RID: `req-grid-hotlink-selector`
Status: `Implemented`

Hotlink extraction is selector-based. The selector system must be pluggable, but v1 should start with a deliberately simple selector backend for structured JSON traversal.

#### Status Details
Implemented. `_simple_path_extract` in `tap_grid/hotlink.py` handles `simple_path` traversal. `extract_identifiers` dispatches by `selector_type`. Additional backends can be added without changing the top-level contract.

#### Implementation
The selector system is defined by two fields on each hotlink definition:

| Field | Meaning |
| --- | --- |
| `selector_type` | Identifies which extraction backend interprets the selector |
| `selector` | Backend-specific expression describing where identifiers are found |

V1 uses `selector_type = "simple_path"`. This selector type is a TAP-native traversal syntax intended for deterministic extraction from structured JSON. It is not JSONPath, and it should not be described as a JSONPath subset.

For the page layout example, the selector:

```text
columns.*.rows.*.panel-id
```

means:

1. start at the `layout` field root,
2. descend into every entry under `columns`,
3. descend into every entry under `rows`,
4. collect the value at `panel-id`.

The v1 path selector should support straightforward object traversal and wildcard fan-out. It should remain intentionally constrained so model declarations are stable, easy to review, and easy to reason about.

Future selector backends may include:

| `selector_type` | Intended Use |
| --- | --- |
| `jsonpath` | Standardized JSON querying when a model truly needs richer selection semantics |
| `xml` | Attribute or node extraction from XML payloads |
| `text` | Structured extraction from free text using a dedicated parser |

#### Development
The decision to start with a simple path selector is pragmatic. Hotlink validation needs stable ID extraction, not general-purpose query semantics. Standard JSONPath libraries vary in behavior and would add complexity before the project has a demonstrated need for that flexibility.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-hotlink-selector-1 | Selector Type Required | Implemented | Every hotlink definition declares a `selector_type`. | |
| req-grid-hotlink-selector-2 | V1 Simple Path Selector | Implemented | `selector_type = "simple_path"` is supported for deterministic traversal of structured JSON fields. | |
| req-grid-hotlink-selector-3 | Backend-Pluggable Contract | Implemented | Additional selector backends may be added later without changing the top-level `HOTLINKS` contract. | |
| req-grid-hotlink-selector-4 | No Implicit JSONPath Claim | Implemented | The v1 path selector is TAP-specific and is not presented as JSONPath compatibility. | |

#### Future
When a concrete use case requires it, define a separate requirement for `selector_type = "jsonpath"` with an explicitly chosen library or dialect and a compatibility policy.


### Hotlink Validation Semantics
----
RID: `req-grid-hotlink-validation`
Status: `Implemented`

The service layer uses `HOTLINKS` declarations to validate that embedded references and materialized edges stay synchronized. Validation operates on identifiers extracted from the node field and identifiers collected from matching edges.

#### Status Details
Implemented. `validate_hotlinks` in `tap_grid/hotlink.py` is called from `BaseModel.full_validate()`. Skips validation when `entity_id is None` (first save, Option A). All three modes (`exact`, `exists`, `unique`) are implemented.

#### Implementation
For each hotlink definition on a model instance being saved, the validator:

1. reads the declared `field` value from the node,
2. extracts zero or more identifiers using the declared selector backend,
3. queries the corresponding edge set for that node using `edge_direction` and `edge_type`,
4. filters to edges whose `properties.hotlink.model` and `properties.hotlink.spec` identify the current hotlink definition,
5. collects the value of `properties.hotlink.value` from each matching edge,
6. applies the declared `mode` to compare extracted identifiers against edge identifiers.

Validation modes:

| Mode | Meaning |
| --- | --- |
| `exists` | Every extracted identifier must have at least one matching edge identifier |
| `unique` | Every extracted identifier must have exactly one matching edge identifier |
| `exact` | The extracted identifier set and the matching edge identifier set must be equal |

The `exact` mode is the intended invariant for page-to-panel mappings. It prevents both kinds of drift:

- missing edges for identifiers still referenced by the node, and
- lingering edges whose identifiers are no longer referenced by the node.

Hotlink validation is graph-consistency validation. It does not replace schema validation of the underlying field. For example, a page `layout` still needs its own JSON-schema-based shape validation independent of any hotlink definition.

#### Development
This separation of concerns is important:

- `FIELD_SCHEMAS` or equivalent validators answer: "Is the field structurally valid?"
- `HOTLINKS` answer: "Does this field's embedded reference contract agree with the graph?"

The system should validate against the node's current persisted edges at save time. That keeps the first implementation simple and allows existing models to adopt hotlinks declaratively.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-hotlink-validation-1 | Extract Then Compare | Implemented | Validation extracts identifiers from the declared field and compares them against identifiers collected from matching edges. | |
| req-grid-hotlink-validation-2 | Direction-Aware Edge Query | Implemented | The validator uses `edge_direction` and `edge_type` to identify which edges participate in the hotlink comparison. | |
| req-grid-hotlink-validation-3 | Join via Hotlink Object | Implemented | The validator uses `properties.hotlink.model`, `properties.hotlink.spec`, and `properties.hotlink.value` to identify and match participating edges. | |
| req-grid-hotlink-validation-4 | Exact Mode Enforces Equality | Implemented | In `exact` mode, validation fails unless the identifier sets from the node and edges are equal. | |
| req-grid-hotlink-validation-5 | Independent of Field Shape Validation | Implemented | Hotlink validation does not replace or weaken existing field-structure validation. | |

#### Future
Consider exposing a reusable reconciliation helper that computes both identifier sets and returns a structured diff for admin tooling, diagnostics, and future write orchestration.


### Hotlink Mutation Boundaries
----
RID: `req-grid-hotlink-mutation`
Status: `Proposed`

Validating hotlinks only when saving the node catches invalid node writes, but it does not fully prevent desynchronization. Edge deletion or mutation can still invalidate a node that is not currently being saved. A later phase should define reverse protection for edge mutations that impact declared hotlinks.

#### Status Details
This is intentionally deferred. The first milestone is node-save validation based on `HOTLINKS`. Reverse edge-mutation enforcement will be specified separately once the initial implementation exists.

#### Implementation
Future edge-mutation protection should use the model-level `HOTLINKS` registry as its source of truth, while consulting explicit `properties.hotlink` data on participating edges.

For an affected hotlink definition, mutating any of the following may need protection or coordinated reconciliation:

| Mutation Kind | Why It Matters |
| --- | --- |
| edge deletion | Can remove the only materialized relationship for an embedded reference |
| `from_entity` / `to_entity` changes | Can move the relationship away from the node whose payload still references it |
| `edge_type` changes | Can move the edge out of the hotlink's declared edge family |
| `properties.hotlink.model` / `spec` / `value` changes | Can break the identifier match or detach the edge from the intended hotlink contract without deleting the edge |

The likely long-term model is:

1. generic validators prevent invalid low-level writes, and
2. higher-level reconciling services update node payloads and edge sets together when a coordinated change is intended.

#### Development
Edge-side hotlink metadata is now part of the design, but it remains instance-level participation data rather than a second source of truth for hotlink meaning.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-hotlink-mutation-1 | Model Registry Remains Source of Truth | Proposed | Future reverse mutation protection derives hotlink meaning from model `HOTLINKS`, not from user-authored edge flags. | |
| req-grid-hotlink-mutation-2 | Edge Writes Recognize Contract Fields | Proposed | Future reverse mutation protection treats deletion, endpoint changes, edge-type changes, and join-key changes as contract-sensitive operations when a hotlink depends on them. | |
| req-grid-hotlink-mutation-3 | Coordinated Reconciliation Path | Proposed | The system should eventually support a higher-level write path that updates node payload references and edge materialization together. | |

#### Future
If reverse lookup cost becomes significant, consider derived edge metadata or a reverse index to accelerate "which hotlinks depend on this edge?" queries without making that metadata authoritative.
