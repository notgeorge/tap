# Grid Dimension Specification

## Philosophy

Entities are the base node of the grid / graph and the place where data about a thing is defined and resides. Dimensionality extends that core model by giving entities a formal way to describe the contexts, namespaces, and perspectives they occupy without losing the coherence of the base entity spine.

## Goals

|    |                    |                                                                                           |
| :---: | ---             | ---                                                                                       |
| 1. | Multi-Dimensional  | Entities can exist in multiple dimensions and contain the metadata to explain how / where |
| 2. | Hierarchical       | Dimensions can be nested via dot notation to form sub-namespaces                          |
| 3. | Accessible         | Entity dimensions are easily found, queried, indexed and will be leveraged lots of ways   |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-dimension-core | [Dimensionality Model](#dimensionality-model) | Approved for Development | Defines the core model and JSON shape for dimensions |
| req-grid-dimension-em | [Dimensions on Entity Model](#dimensions-on-entity-model) | Approved for Development | Adds the dimensions field to the canonical entity record |
| req-grid-dimension-dn | [Dimension Node](#dimension-node) | Approved for Development | Introduces a first-class node for dimension definitions |
| req-grid-dimension-de | [Default Entity Dimensions](#default-entity-dimensions) | Approved for Development | Defines default dimensions for existing entity definitions |
| req-grid-dimension-dc | [Dimension Check](#dimension-check) | Approved for Development | Preserves required default dimensions during validation |


### Dimensionality Model
----
RID: `req-grid-dimension-core`  
Status: `Approved for Development`

#### The Why
The concept of dimensionality is essential to the grid data model. The ability to formally establish a dimension for an entity, and for that entity to occupy multiple dimensions simultaneously, is what opens up a huge amount of optionality while maintaining coherence. If we're being honest here we're re-discovering namespaces and calling them something else because it sounds cooler and fits with the grid backronym of a "graphical representation of interesting dimensions".

#### Background
My first inclination was to have this be a simple database column with the dimension as a standard, user-defined value which could possibly be extended through naming conventions ala `env.staging.xyz` where the idea of an environment was meant to support teams running a single TAP instance to cover dev / stage / prod. At the same time, there's the fundamental concept of design -> config -> operation, which is another dimension, and there are other dimensions that data may itself operate in such as employees in the human dimension, machines in the computer dimension, and the collection of humans as teams managing fleets of computers.

The alternative to a column would be to have a dimension be a node and edges between nodes used to define which nodes point to which dimension. That would be leaning in super hard to the entity-edge paradigm, but it doesn't quite feel right. It would result in a ton of edges, which would choke up the database, and it also moves the concept of dimension out of the node itself. That distance feels wrong somehow versus having dimension directly encoded as a concept that exists slightly above the graph model itself.

After reading through how others have implemented namespaces in JSONb it seems like following that pattern makes the most sense and that philosophically, dimensions exist in a different conceptual space than nodes and edges (although we'll introduce the concept of a dimension node because it's going to come in handy much sooner than I think.)

#### Status Details
This requirement defines the overall model. The implementation work is intentionally split into the child requirements below so each implementation action can move independently.

#### Implementation
Dimensions are stored as JSON data on the canonical `Entity` model so the metadata lives on the universal node representation rather than on subtype-specific extension tables.

Dimensions exist in two distinct contexts:

| Context | Description |
| --- | --- |
| Definition Dimensions | Metadata that describes an entity definition object such as the definition for `Character` |
| Instance Dimensions | Metadata that describes a specific entity instance such as the entity for Frodo |

The JSON shape follows these constraints:

| Constraint | Description |
| --- | --- |
| Flat Object | Use a flat JSON object, not nested namespace objects |
| Namespaced Keys | Use namespaced keys separated by `.` |
| Value Types | Allow values to be `string`, `number`, `boolean`, or `array[string]` |

This walks a line between configuration and convention which allows both to co-exist. The use of JSON and extensibility makes the concept of dimensions truly multi-dimensional.

Dimensions and edges serve different purposes:

| Concept | Purpose |
| --- | --- |
| Dimensions | Stable, shared metadata used to partition, scope, index, and interpret entities across a dataset or across blended datasets |
| Edges | Graph-native relationships that model facts and links inside the dataset itself |

Rule of thumb: if representing something would require a bajillion edges applied across a large portion of the dataset, it is probably a dimension instead of an edge. Dimensions exist in part because that kind of broad, repeated scoping metadata is simpler and more coherent to represent directly than as an enormous set of repeated edges.

Dimensions should generally be closer to fixed and broadly shared. Edges should generally represent facts that can be traversed, updated, or reinterpreted over time.

Explaining and tracking dimensions is done through OPTIONAL dimension nodes which define a name and description entity with dimension metadata in JSON form, for example `"tap.meta": "dimension"`. This is an optional step for now and is intended as a convenience for people to define what they mean by a given dimension. Individual `Entity` instances can set whatever dimension values they need, which leans toward a tagging model in the initial implementation.

Example:

| Entity | Example Dimensions |
| --- | --- |
| `Character` definition entity | `{ "tap.meta": "entity" }` |
| Frodo instance entity | `{ "canon": "lotr" }` |

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-dimension-core-1 | Split Child Requirements | Approved for Development | The implementation actions for dimensionality are tracked as separate requirements with their own status and acceptance criteria. | Keeps implementation and verification staged. |
| req-grid-dimension-core-2 | JSON Shape Defined | Approved for Development | The spec defines a concrete JSON shape for dimensions including key conventions and supported value types. | |

#### Future
How are dimensions and projects related? Dimension, project, grid?  
How can dimensions be leveraged in a security context?  
Projects / grid installs that make dimension nodes required (or list a subset of required nodes that are security / app weight bearing)?

### Dimensions on Entity Model
----
RID: `req-grid-dimension-em`  
Status: `Approved for Development`

#### Status Details

#### Implementation
Add a `dimensions` column to the `Entity` model to store JSON data. The default value is an empty object and the field is not nullable.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-dimension-em-1 | Dimensions Column Exists | Approved for Development | `Entity` includes a `dimensions` JSON field with a default empty object. | |
| req-grid-dimension-em-2 | Dimensions Column Required | Approved for Development | The `dimensions` field is non-nullable at the model and database layer. | |


#### Future

### Dimension Node
----
RID: `req-grid-dimension-dn`  
Status: `Approved for Development`

#### Status Details

#### Implementation
Create a dimension node type used to describe a dimension. Its dimension data includes JSON metadata in the form `"tap.meta": "dimension"`.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-dimension-dn-1 | Dimension Node Exists | Approved for Development | A dimension node type exists for describing dimensions as first-class entities. | |
| req-grid-dimension-dn-2 | Dimension Nodes Tagged | Approved for Development | Dimension node instances include `"tap.meta": "dimension"` in their dimension metadata. | |

#### Future
Confirm that dimension nodes should remain optional in the initial implementation.


### Default Entity Dimensions
----
RID: `req-grid-dimension-de`  
Status: `Approved for Development`

#### Status Details

#### Implementation
Define a process to assign dimension definitions for entity models. The actual dimension data is stored on each `Entity` instance in the `dimensions` column. Definition-level dimension declarations live in code on the `BaseModel` subclass that defines that entity shape, in a standard class-level declaration that can be read when creating and saving entity definition objects. These definitions are for metadata such as `"tap.meta": "entity"` on the `Character` definition entity, not for ordinary per-instance dimension values such as `"canon": "lotr"` on Frodo.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-dimension-de-1 | Existing Entity Definitions Declared | Approved for Development | Existing `BaseModel` entity definitions have definition-level dimension metadata declared in code. | |
| req-grid-dimension-de-2 | Entity Definitions Tagged | Approved for Development | Entity definition objects include `"tap.meta": "entity"` in their dimension metadata. | |

#### Future

### Dimension Check
----
RID: `req-grid-dimension-dc`  
Status: `Approved for Development`

#### Status Details

#### Implementation
Entities whose `BaseModel` subclass defines required instance dimensions should validate that those dimensions are still applied when the backing `Entity` instance is being saved. Additional dimension information may be present on the instance, but the required instance dimensions cannot be removed without causing a validation error. Definition-level dimensions for entity definition objects are validated separately from ordinary entity instances.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-dimension-dc-1 | Required Dimensions Preserved | Approved for Development | Saving an entity with declared default dimensions fails if one of those required dimensions has been removed. | |
| req-grid-dimension-dc-2 | Additional Dimensions Allowed | Approved for Development | Saving an entity succeeds when additional dimensions are present alongside the required default dimensions. | |

#### Future



## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated |  |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: \`...\``  
`Status: \`...\``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
