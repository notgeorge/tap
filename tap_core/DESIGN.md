# tap_core Design

## Purpose

tap_core is the foundation of TAP. It defines the core data model that everything else builds on: Entity, Edge, and the custom User model.

## Key Design Decisions

### Entity as Authoritative System of Record

Entity is the single source of truth in TAP, similar to how Wikidata treats items. Every domain object in the system is an Entity. ORM models and API endpoints reference Entity via foreign key - they do not introduce parallel sources of truth.

All Entity IDs are UUIDv7, which provides:
- Global uniqueness (no collisions across federated instances)
- Time-ordering (UUIDv7 embeds a timestamp, so IDs sort chronologically)
- Python 3.14 includes `uuid.uuid7()` in stdlib

### Edge Table for Graph Capabilities

Rather than using a graph database, TAP implements graph capabilities in PostgreSQL using:
- An Entity table as the node spine
- A dedicated Edge table for directed, typed relationships between entities

This gives us the ACID guarantees and type safety of SQL while enabling graph traversals via recursive CTEs when needed.

### Grid ID for Installation Identity

Every TAP installation has a globally unique Grid ID (UUIDv7) stored in settings. This is stamped on every Entity as `originating_grid_id`, enabling future federation. One install = one Grid, similar to WordPress.

### Custom User Model from Day One

Django strongly recommends defining a custom user model before creating any migrations, even if it's identical to the default. Changing AUTH_USER_MODEL after migrations exist is extremely painful. Our User model extends AbstractUser and can grow as needed.

### BaseModel for Domain ORM Models

All domain ORM models (excluding Entity, Edge, Grid, and Django auth models) inherit from a BaseModel that enforces:
- `created_at` and `updated_at` timestamps
- `originating_grid_id` for federation tracking
- FLIP compliance (when tap_flip is implemented)

## What Lives Here vs. Other Apps

- **tap_core**: Entity, Edge, User, BaseModel, Grid identity, core services
- **tap_plugins**: Entity type registration, plugin discovery, plugin-defined models
- **tap_api**: API routing, versioning, authentication middleware
- **tap_web**: Templates, static assets, dashboard helpers
- **tap_viz**: Cytoscape integration, graph visualization
- **tap_flip**: Provenance recording, history tracking, realms, environments
- **tap_ai**: RAG surfaces, graph summarization, suggestion helpers
