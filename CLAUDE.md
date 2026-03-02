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
6. tap_flip - FLIP - to include data provenance, history tracking, realms, and environments, by this point we should know what we're doing and can knock out an initial version that is elegant and leverages the core model
7. tap_ai - Initial RAG / LLM Surfaces - read-only graph traversal, summarization, and suggestion helpers, the super-awesome stretch goal which takes this whole project to the next level

TAP Core Architectural Rules
    Entity is the authoritative system of record; ORM models and APIs must not introduce parallel sources of truth.
    ORM models refer to entity via foreign key relationships
    Use a BaseModel for all domain ORM models (excluding Entity, Edge, Grid and Django auth models) to manage consistency of created_at, updated_at, originating_grid, and related fields and enforce compliance with FLIP
    Any application code or background task that mutates domain data must do so explicitly via FLIP APIs and never bypass provenance recording.
    
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

Django Best Practices
    Follow Django's "batteries included" philosophy - use built-in features before third-party packages
    Prioritize security and follow Django's security best practices
    Prefer ORM for standard operations and data models; use raw SQL or CTEs where graph traversal or performance requires it.
    Use Django signals sparingly, require approval before writing them, and document them well.
    Background tasks must not silently mutate core graph state in v0; all graph mutations must remain explicit and auditable.

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

    # Create superuser
    docker compose exec web uv run python manage.py createsuperuser

    # Open Django shell
    docker compose exec web uv run python manage.py shell

    # View logs
    docker compose logs -f web

