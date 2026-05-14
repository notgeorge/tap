# TAP Development Guide 

Technology Stack
    Backend: Django 6+ with Django Ninja for API
    Database: PostgreSQL
    Async Tasks: Django Tasks (used sparingly in v0; primarily for ingestion and long-running read-only analysis)
    Containerization: Docker with docker-compose for development

Key Directories - each are their own Django app, this is also the scaffolding priority order for v0
1. tap_grid - Core data model - we define entity and edge tables connecting to standard ORM data tables and decide how to best structure where that standardized logic lives, including service-layer decisions that touch multiple tables
2. tap_plugins - plugin management - minimal implementation designed to seed data types for testing / implementation, this will grow and evolve, shooting bare minimum to add data objects, edges to prove core is working properly
3. tap_api - Manages API versioning, auth, and global API behavior, building out django ninja so there's an api layer that is minimal and effective and decide how to refactor plugins to support adding api endpoints in a sane way
4. tap_web - Assets and helpers for building expressive dashboards and UIs which plugins will extend, once this is baked we can refactor the plugin from built in step 2 to include some pages to see things
5. tap_viz - Visualization - present views of the data in visual graphical format (cytoscape), once we can see web pages we'll add cool visuals that will be a joyful thing to see
6. tap_ai - Initial RAG / LLM Surfaces - read-only graph traversal, summarization, and suggestion helpers, the super-awesome stretch goal which takes this whole project to the next level

TAP Core Architectural Rules
    Specifications are the canonical source of truth; this guide is a high-level operational summary and must be kept aligned with the specs.
    Entity is the graph spine and cross-cutting metadata layer for TAP-managed nodes and edges; typed BaseModel tables hold domain-specific data.
    ORM models refer to entity via foreign key relationships
    Use a BaseModel for all domain ORM models (excluding Entity, Edge, Grid and Django auth models) so every TAP-managed node has a backing Entity on the spine.
    The TAP service layer is the canonical path for TAP-managed node and edge reads and writes.
    Any application code, plugin code, or background task that mutates TAP-managed node or edge data must do so through the service layer rather than direct ORM writes.
    Direct ORM access is acceptable only for migrations, intentional low-level/model tests, and explicitly out-of-scope admin/infrastructure behavior.
    Dimensions live on Entity and are the current implemented scoping/partitioning model for TAP-managed graph data.
    FLIP and provenance integrate with the service layer and caller context; do not invent parallel mutation APIs.
    History, FLIP, and future perspectives are core grid concepts, not separate architectural product domains; implementation modules should not be treated as independent system boundaries.
    TAP-managed node and edge types should publish discoverable schemas and capabilities through the registry-backed service-layer discovery system.
    
TAP Plugin Rules
    Plugins may register API routers only under a namespaced prefix controlled by tap_api (e.g. /api/v1/plugins/<plugin_slug>/...)
    Plugins expose API routers via an explicit registration interface; tap_api is responsible for discovery, mounting, and lifecycle management.

TAP AI Rules
    tap_ai must not write to core graph state in v0.

Code Quality Standards
    Formatting: black
    Linting: ruff with Django-specific rules
    Type Checking: mypy with mostly-strict settings and Django plugin
    Docstrings: Google-style docstrings for public interfaces and non-trivial functions
    Coverage: High coverage is encouraged; critical paths must be tested
    Avoid Any where practical:  Allow it at system boundaries and plugin interfaces with justification
    Use early returns:  Avoid nested conditionals
    Prefer composition over inheritance
    Use double quotes for Python strings
    Sort imports with isort
    Use f-strings for string formatting

Testing Framework
    pytest with Django integration
    Factory-based test data generation
    Separate functional and unit test suites
    Write unit tests for new features where behavior is well-defined
    Test both positive and negative scenarios
    Tests should accompany new functionality where behavior is clear.
    Test behavior, not implementation
    Application-level tests for TAP-managed node/edge behavior should prefer service-layer setup over direct ORM writes.
    Direct ORM setup in tests is appropriate only when intentionally testing model-level or below-service-layer behavior.

Django Best Practices
    Follow Django's "batteries included" philosophy - use built-in features before third-party packages
    Prioritize security and follow Django's security best practices
    Prefer ORM for standard operations and data models; use raw SQL or CTEs where graph traversal or performance requires it.
    Use Django signals sparingly, require approval before writing them, and document them well.
    Background tasks must not silently mutate core graph state in v0; all graph mutations must remain explicit and auditable.
    For TAP-managed graph data, prefer the service layer over ad hoc ORM mutation even when the ORM would be simpler in the moment.

Authentication & Authorization
    Use Django’s built-in authentication system
    Use a custom User model extending AbstractUser
    Do not implement custom authentication logic without explicit instruction
    Authorization should use Django permissions or explicit checks; avoid ad-hoc logic

Templates
    Use template inheritance with base templates
    Use template tags and filters for common operations
    Use static files properly with {% load static %}
    Implement CSRF protection in all forms

Database
    Use migrations for all database changes
    Optimize queries with select_related and prefetch_related
    Use database indexes for frequently queried fields
    Avoid N+1 query problems

Development Environment
    Python 3.14+ required
    UV for dependency management (use uv add/uv remove - NEVER use pip directly)
    Single Docker for all services (Django, Postgresql)
    Virtual environment automatically created in .venv/
    Follow PEP 8 with 120 character line limit
    Use environment variables in a single settings.py file
    Never commit secrets to version control

Development Commands
    # Start all services
    docker compose up

    # Start services in background
    docker compose up -d

    # Stop services
    docker compose down

    # Run Django management commands
    docker compose exec web uv run python manage.py <command>

    # Run tests
    docker compose exec web uv run pytest

    # Linting and formatting
    docker compose exec web uv run black .
    docker compose exec web uv run ruff check --fix .
    docker compose exec web uv run mypy .

    # Create migrations
    docker compose exec web uv run python manage.py makemigrations

    # Apply migrations
    docker compose exec web uv run python manage.py migrate

    # Seed plugin data (required after migrate — plugins no longer auto-import in ready();
    # see req-plugin-load-v0-ready-readonly. Spawn script does this automatically.)
    docker compose exec web uv run python manage.py import_plugin_grift --all

    # Create superuser
    docker compose exec web uv run python manage.py createsuperuser

    # Open Django shell
    docker compose exec web uv run python manage.py shell

    # View logs
    docker compose logs -f web

Multi-session worktrees
    Worktrees under /Users/george/tap-sessions/<label>/ are isolated Compose stacks.
    Per-session config lives in .env.local (COMPOSE_PROJECT_NAME, WEB_PORT, POSTGRES_PORT, TAP_GRID_ID).
    Always use `scripts/dc` instead of `docker compose` directly — it merges .env + .env.local
    so commands target this session's containers, not the primary `tap` stack on 8000/5432.
    Lifecycle scripts (canonical implementations of the multi-session workflow):
        scripts/spawn-session.sh          — create a new session worktree + Compose stack
        scripts/despawn-session.sh        — tear it down
        scripts/promote-to-main.sh        — push this session into origin/main (pre-push merge + atomic dual-refspec push + main sync)
        scripts/promote-all-sessions.sh   — run promote-to-main.sh across every session in the registry
    When the user says "consolidate sessions", "ship the sessions", or otherwise asks to advance
    origin/main from session branches, run the promote scripts rather than retyping the git steps.
    See spec-dev-multisession.md for port bands, spawn/despawn, and the push workflow.

Documentation (specs ↔ docs alignment)
    Specs (specs/, <app>/specs/) are authoritative for behavior. Docs (docs/) are derived how-to surfaces.
    See specs/spec-docs.md for the full documentation system contract.

    Naming:
        Doc files: docs/doc-<system>-<name>.md (doc- prefix on the filename)
        Doc-owning specs: specs/spec-<system>-<doc-name>-doc.md (-doc suffix on the spec filename)

    Drift prevention — when editing a SPEC:
        1. Search docs/ for any reference to the requirement RID(s) you are changing:
               grep -r "req-foo-bar" docs/
        2. Read each hit. If the doc no longer matches behavior, update the doc in the same PR.
        3. Doc-only commits when the doc change is independent of behavior; bundled commits when paired with a behavior change.

    Drift prevention — when editing a DOC:
        1. Read its frontmatter `spec:` and skim its `covers:` list.
        2. Confirm the procedure / claims still match what the linked specs require.
        3. If a referenced requirement has changed, update the doc; if the doc-spec's `update-triggers:` list is incomplete, expand it.

    Versioning:
        last-edited and version are derived from git (git log -1 --format=%cI / %h <file>); never store these in a doc.
        last-reviewed is NOT used; the git log is the source of truth.

    See req-docs-drift-conventions and req-docs-change-history in specs/spec-docs.md.
