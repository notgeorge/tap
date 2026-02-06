# tap_api Design

## Purpose

tap_api owns the Django Ninja API instance, core CRUD endpoints, plugin router discovery, and authentication. No models — pure routing and presentation.

## Key Decisions

**NinjaAPI lives in `api.py`.** Single assembly point: creates the API, mounts core routers, discovers plugin routers. Mounted at `/api/v1/` in urls.py.

**Unversioned `/api/` alias.** Path-preserving redirect to `/api/v1/`. When v2 ships, change the redirect target. Explicit-version clients keep working.

**ModelSchema for output schemas.** `EntityOut`, `EdgeOut`, `EntityTypeOut` derive from Django models — eliminates drift between models and API responses. Input schemas are hand-written since they intentionally differ from model shape.

**Core routers = graph infrastructure.** Entity, Edge, and EntityType endpoints work for all types. `GET /entities/?entity_type=concept` covers what most plugins need. Plugin routers are for domain-specific operations beyond generic CRUD.

**Plugin router discovery.** `TapPluginConfig.get_api_router()` returns a `ninja.Router` or `None`. `TapApiConfig.ready()` iterates all app configs, finds TapPluginConfig subclasses, and mounts their routers at `/plugins/<label>/...`. Lazy imports in `get_api_router()` prevent circular dependencies.

**Session auth for v0.** Global `django_auth` on the NinjaAPI instance. Log in via `/admin/`, session cookie carries to API. `tap_api/auth.py` is the single evolution point when token auth is needed.

**All mutations go through `tap_core.services`.** The API layer handles validation, HTTP concerns, and response formatting. When FLIP is built, provenance recording slots into the service layer without changing API code.

## What Lives Here vs Other Apps

- **tap_api**: NinjaAPI instance, schemas, routers, auth, plugin router discovery
- **tap_core**: Models, service layer (mutation logic), EntityType registry
- **tap_plugins**: `TapPluginConfig` base class with `get_api_router()` hook
- **Plugins**: Override `get_api_router()` to expose domain-specific endpoints
