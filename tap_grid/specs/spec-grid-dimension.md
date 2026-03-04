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
| req-grid-dimension-em | [Dimensions on Entity Model](#dimensions-on-entity-model) | Approved for Development | Adds the dimensions field to the canonical entity record |
| req-grid-dimension-dc | [Default Dimension Application](#default-dimension-application) | Approved for Development | Applies declared default dimensions when an entity is created |
| req-grid-dimension-dn | [Dimension Node](#dimension-node) | Approved for Development | Introduces a first-class node for dimension definitions |


## Explanation
#### The Why
The concept of dimensionality is essential to the grid data model. The ability to formally establish a dimension for an entity, and for that entity to occupy multiple dimensions simultaneously, is what opens up a huge amount of optionality while maintaining coherence. If we're being honest here we're re-discovering namespaces and calling them something else because it sounds cooler and fits with the grid backronym of a "graphical representation of interesting dimensions".

This walks a line between configuration and convention which allows both to co-exist. The use of JSON and extensibility makes the concept of dimensions truly multi-dimensional.

Individual `Entity` instances can set whatever dimension values they need, which leans toward a tagging model in the initial implementation. Default dimensions will be applied automatically if they are defined on the entity model. This is a convenience for entity types that we know will always need a given dimension, such as web pages, which will always be on the `tap.graph: web` dimension.

#### Important Distinction: Dimensions and edges serve different purposes:

| Concept | Purpose |
| --- | --- |
| Dimensions | Stable, shared metadata used to partition, scope, index, and interpret entities across a dataset or across blended datasets |
| Edges | Graph-native relationships that model facts and links inside the dataset itself |

Dimensions should generally be closer to fixed and broadly shared. Edges should generally represent facts that can be traversed, updated, or reinterpreted over time.

**Rule of thumb**: If representing a collection would require a bajillion edges applied across a large portion of the dataset and most / all entity types, it is probably a dimension instead of an edge. Dimensions exist in part because that kind of broad, repeated scoping metadata is simpler and more coherent to represent directly than as an enormous set of repeated edges.

#### Edges have Dimensions Too
Since edges are entities they can have dimensions applied to them as well. This will be useful in situations where a `page-LEVERAGES_PANEL->panel` relationship uses a `LEVERAGES_PANEL` edge with the `tap.graph: web` dimension applied automatically to keep these entities in the same namespace.  Edge dimensions live on the backing Entity, and the DEFAULT_DIMENSIONS mechanism handles this automatically.

#### Background
My first inclination was to have this be a simple database column with the dimension as a standard, user-defined value which could possibly be extended through naming conventions ala `env.staging.xyz` where the idea of an environment was meant to support teams running a single TAP instance to cover dev / stage / prod. At the same time, there's the fundamental concept of design -> config -> operation, which is another dimension, and there are other dimensions that data may itself operate in such as employees in the human dimension, machines in the computer dimension, and the collection of humans as teams managing fleets of computers, and layout / search / panels / page entities which I want to manage as nodes and edges but don't want them to get in the way of the actual data.

The alternative to a column would be to have a dimension be a node and edges between nodes used to define which nodes point to which dimension. That would be leaning in super hard to the entity-edge paradigm, but it doesn't quite feel right. It would result in a ton of edges, which would choke up the database, and it also moves the concept of dimension out of the node itself. That distance feels wrong somehow versus having dimension directly encoded as a concept that exists slightly above the graph model itself.

After reading through how others have implemented namespaces in `JSONField`, it seems like following that pattern makes the most sense and that philosophically, dimensions exist in a different conceptual space than nodes and edges (although we'll introduce the concept of a dimension node because it's going to come in handy much sooner than I think).

#### Questions for the Future
How are dimensions and projects related? Dimension, project, grid?  
How can dimensions be leveraged in a security context?  
Projects / grid installs that make dimension nodes expected (or list a subset of preferred nodes that are security / app weight bearing)?


### Dimensions on Entity Model
----
RID: `req-grid-dimension-em`  
Status: `Approved for Development`

#### Status Details

#### Implementation
Add a `dimensions` column to the `Entity` model using Django `models.JSONField`. In Postgres this is stored as JSONField. The default value is an empty object and the field is not nullable.

If defined, the JSON shape follows these constraints:

| Constraint | Description |
| --- | --- |
| Flat Object | Use a flat JSON object, not nested namespace objects |
| Namespaced Keys | Use namespaced keys separated by `.` |
| Lower Case | Always use lower case |
| Value Types | Allow values to be `string` |

In the current implementation the dimenions are not validated beyond ensuring lower-case and string values.


#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-dimension-em-1 | Dimensions Column Exists | Approved for Development | `Entity` includes a `dimensions` JSON field with a default empty object. | |
| req-grid-dimension-em-2 | Dimensions Column Required | Approved for Development | The `dimensions` field is non-nullable at the model and database layer. | |


#### Future
Consider reserved dimensions or the ability for plugins / apps to reserve them.
Dimension validation options - can be applied 



### Default Dimension Application
----
RID: `req-grid-dimension-dc`  
Status: `Approved for Development`

There will be entities that will always want to set a default dimension. The example driving the initial implementation is pages and panels on a web interface. Each will be entities so we can leverage nodes and edges, but I don't want them mucking up the data they're being used to describe.

Having pages in a separate dimension is helpful because that distinction meets our rule of thumb: all the pages and all the panels will be in a self-contained graph, with limited / no interplay with the data (beyond accessing search nodes), and the pages will never change dimensions to become data.

In order to simplify / standardize that we'll define a `DEFAULT_DIMENSIONS` field that will be applied whenever an entity is created.

#### Status Details

#### Implementation
Entities whose `BaseModel` subclass defines `DEFAULT_DIMENSIONS` should apply those dimensions when the backing `Entity` instance is created. These defaults are a convenience and are not mandatory after creation. Additional dimension information may be present on the instance, and default dimensions may be changed or removed later without causing a validation error.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-dimension-dc-1 | Defaults Applied On Create | Approved for Development | Creating an entity whose model defines `DEFAULT_DIMENSIONS` applies those defaults to the new `Entity` instance. | |
| req-grid-dimension-dc-2 | Defaults Are Not Mandatory | Approved for Development | After creation, default dimensions may be changed or removed without causing a validation error. | |


#### Future


### Dimension Node
----
RID: `req-grid-dimension-dn`  
Status: `Approved for Development`

#### Status Details

#### Implementation
Create a dimension node as an entity derived from `BaseModel` that is used to describe a dimension. It contains a name and description, and its `DEFAULT_DIMENSIONS` includes `"tap.meta": "dimension"`.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-dimension-dn-1 | Dimension Node Exists | Approved for Development | A simple `Entity` with the type `dimension` exists for describing dimensions as first-class entities. Its model is declared along with nodes and edges. | |
| req-grid-dimension-dn-2 | Dimension Nodes Tagged | Approved for Development | Dimension node definitions include `"tap.meta": "dimension"` in their `DEFAULT_DIMENSIONS`. | |
| req-grid-dimension-dn-3 | Dimension Node Carries Core Fields | Approved for Development | A dimension node includes a name and description. | |

#### Future
Confirm that dimension nodes should remain optional in the initial implementation.  
Define whether dimension nodes should eventually constrain specific inbound or outbound edge types. For the initial implementation, allow any inbound and outbound edges.


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
