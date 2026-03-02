# tap_plugins Design

## Purpose

tap_plugins provides the infrastructure for extending TAP with domain-specific functionality. Plugins are Django apps that subclass `TapPluginConfig` to declare entity types, edge types, and domain models.

## Key Decisions

**Plugins are Django apps.** No custom discovery mechanism — INSTALLED_APPS is the registry. This leverages Django's mature app loading, migrations, and management commands.

**TapPluginConfig auto-registers types.** Plugins declare `entity_types` and `edge_types` as class attributes. The `ready()` hook registers them into the EntityType table via `get_or_create` (idempotent).

**Edge types live in EntityType.** Both entity types and edge types share the same registry table. This is intentional — edges ARE entities in TAP, so their types belong in the same catalog.

**Registration is database-safe.** Catches OperationalError/ProgrammingError for cases where the DB table doesn't exist yet (first migration run).

## Plugin Anatomy

A TAP plugin is a Django app with:
- `apps.py` subclassing `TapPluginConfig` (declares types)
- `models.py` with domain models inheriting `BaseModel` (optional)
- Tests
- Eventually: API routers (registered via tap_api, step 3)

## What Lives Here vs Other Apps

- **tap_plugins**: Plugin base class, registration infrastructure
- **tap_grid**: Entity, Edge, EntityType, BaseModel (the schema plugins build on)
- **tap_api**: Mounts plugin API routers under namespaced prefixes (step 3)
