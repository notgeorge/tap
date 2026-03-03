# Grid Entity Specification

## Philosophy

Entities are the base node of the grid / graph and the place where data about a thing is defined and resides.  Each entity type has its own table in the database for the base entity which is extended via a specific column for inheritance / extensions / specialized types.

## Goals

|    |                    |                                                                                           |
| :---: | ---             | ---                                                                                       |
| 1. |  Consistent        | Entities present a standard format for placement on the entity spine                      |
| 2. |  Multi-Dimensional | Entities can exist in multiple dimensions and contain the metadata to explain how / where |
| 3. |  Extensible        | Can be extended ala OOP concepts to create sub-types, without creating new tables         |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
|  |  |  |  |

### Dimensionality Baked In
----
RID: `req-grid-entity-dim`
Status: `Proposed`

#### They Why
The concept of dimensionality is essential to the grid data model - the ability to formally establish a dimension for an entity and for that entity to occpuy multiple dimensions simultaneously is what opens up a huge amount of optionalitity while maintaining coherence.  If we're being honest here we're just re-discovering namespaces and calling them something else because it sounds cooler and fits with the grid backronym of a "graphical representation of interesting dimensions".

#### Background
My first inclination was to have this be a simple database column with the dimension as a standard, user-defined value which could possibly be extended through naming conventions ala env-staging-xyz (where the idea of an environment was meant to support teams running a single TAP instance to cover dev / stage / prod).  At the same time, there's the fundamental concept of design -> config -> operation, which is another dimension, and there are other dimensions that data may itself operate in such as employees in the human dimension, machines in the computer, and the collection of humans as teams maaging fleets of computers.

The alternative to a column would be to have a dimension be a node and edges between nodes used to define which nodes point to which dimension.  That would be leaning in super hard to the entity - edge paradigm, but it doesn't quite feel right.  It would result in a ton of edges, which would choke up the database (not really a concern and could be placed in their own table if i cared that much) and it also moves the concept of dimension out of the node itself - and that distance feels wrong somehow vs having dimnesion directly encoded as a concept that exists sub / super the graph model itself.


#### Status Details

#### Implementation
I propose that we include dimension as a jsonb column on the Entity Model, then we can create conventions as needed to distinguish elements as needed.  This feels like it walks a line between configuration vs convention which would allow both approaches to co-exist.

The use of JSONb and extensibility makes the concept of dimensions truly multi-dimensional.

Specific constraints of the JSON dimension information:
1. Use a flat JSON object, not nested namespace objects.
2. Use namespaced keys separated by '.'
3. Allow values to be string | number | boolean | array[string].


First pass will require several adjustments throughout the codebase to the core entity model, test cases, and test data.  Good to take it on now.

Defining dimensions is done through dimension nodes which define a name and description entity with the `tap_meta: dimension`.  This is an optional step and is intended as a convenience for people to define what the hell they mean by a given dimension.  Entities can create their own dimensions as they see fit, so this also seems to be implying more of a tagging situation but at this point I'm inclined towards flexibility over mandated consistency.

Requiring and applying dimensions is another consideration.  In the initial implementation we'll default to an empty object if there is no dimension information and allow the specific application implementation / plugin / whatever to define appropriate dimension information.  Entities should register the dimensions that they occupy by default during registration and those will be automatically applied to the nodes of that type when they are created.

#### Development


#### Acceptance Criteria

| Status | Action | Status | Implementation | ACID | Notes | 
| -- | -- | -- | -- | -- | -- |
| `Proposed`    |   Dimension on Entity Model | Add a dimnesions column to the Entity Model to store JSONb data, the default is an empty object, this field is not nullable.     | req-grid-entity-dim-i-bm | |
| `Propsed`     |  Dimension Check          | Entities that define default dimensions should validate that enties still have that dimension applied when they are being saved (other dimension information may be present).  If it is missing the dimension then it will throw an error | req-grid-entity-dim-i-dc | | 
| `Proposed`    | Entities are Entities     | Convert the existing EntityType definition into a full-fledged Entity object and adjust all previously defined entities to suit   | req-grid-entity-dim-i-ee | | 
| `Proposed`    | Default Entity Dimensions | Define appropriate dimension information defaults for existing entities.  entity definitions are in the `tap_meta: entity` dimension. | req-grid-entity-dim-i-de | | 
| `Proposed`    | Dimension Node    | Create a dimension node type which we'll use to describe a dimension, state it's dimension data as `tap_meta: dimension` | req-grid-entity-dim-i-dn | | 

#### Future
* How are dimensions and projects related? - Dimension, project, grid?

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
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
