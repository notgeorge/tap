# tap_core Design

## Purpose

tap_core defines the foundational data model: Entity, Edge, EntityType, BaseModel, and User.

## Key Decisions

**Entity PK = UUIDv7.** Entity's ID IS the UUID (`UUIDField(primary_key=True)`). No separate BigAutoField. UUIDv7 is time-ordered so B-tree index performance is fine. 16 bytes vs 8 bytes is worth the architectural simplicity.

**Edges are Entities.** Edge inherits BaseModel, which gives it a OneToOneField to Entity. Edges are first-class objects that can be referenced, federated, and traversed like any other entity. "No edges between edges" is enforced at the service layer, not the schema — we don't have a grounded philosophical argument to prevent it structurally.

**entity_type is a CharField, not an FK.** Entity.entity_type stores a plain string (e.g., "server"). EntityType is a separate registry table that plugins populate. The connection is logical, not relational — validated at the service layer. This decouples Entity from the plugin system at the DB level and keeps queries fast.

**display_name on Entity, icon on EntityType.** Names are per-instance ("prod-web-01"), icons are per-type (all servers share an icon).

**BaseModel includes the Entity FK.** Every domain ORM model inherits BaseModel, which provides the OneToOneField to Entity plus timestamps and originating_grid_id. The `related_name="%(class)s"` pattern enables `entity.server`, `entity.edge`, etc.

**originating_grid_id is nullable.** Allows the system to function before a Grid ID is configured. Stored as a native UUID type (16 bytes) rather than a 36-char string.

**Edge properties via JSONField.** Lightweight metadata (weight, confidence, notes) without premature schema design. Plugins can promote hot fields to columns later.

**No unique constraint on Edge.** Multiple edges of the same type between entities are valid. Uniqueness enforced at service layer if needed.

**Realm/Environment deferred.** These are tap_flip concerns (step 6). BaseModel is the extension point.

## What Lives Here vs Other Apps

- **tap_core**: Entity, Edge, EntityType, BaseModel, User, Grid identity
- **tap_plugins**: Type registration, plugin discovery, plugin-defined domain models
- **tap_api**: API routing, versioning, auth middleware
- **tap_web**: Templates, static assets, dashboards
- **tap_viz**: Cytoscape, graph visualization
- **tap_flip**: Provenance, history, realms, environments
- **tap_ai**: RAG surfaces, summarization, suggestions
