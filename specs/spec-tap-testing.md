# TAP Testing Specification

## Philosophy

Tests are how we know TAP works. The testing strategy should be simple enough that running the full suite is a single command, organized enough that a developer can run a subset for fast feedback, and structured enough that each application's tests are self-contained and focused on the behavior that application owns.

TAP is a Django project with multiple applications and a plugin system. Each application owns its domain behavior and should own its tests. The testing framework should make it easy to write good tests and hard to write tests that depend on hidden state or cross-application coupling.

In v0 all tests are developer-facing. User-facing verification and self-test capabilities are a future concern.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Single Command | `pytest` at the repo root runs every test in the project |
| 2. | Scoped Runs   | A developer can run tests for a single application or plugin in isolation |
| 3. | Clear Ownership | Every test lives in the application or plugin that owns the behavior it validates |
| 4. | Service-Layer First | Application-level tests prefer the service layer for setup and assertions over direct ORM manipulation |
| 5. | Spec Linkage  | Tests link to spec acceptance criteria via `@pytest.mark.spec` markers |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-test-discovery | [Test Discovery](#test-discovery) | Implemented | pytest configuration and test path layout |
| req-tap-test-layout | [Test Layout By Application](#test-layout-by-application) | In Development | Where tests live and what they cover |
| req-tap-test-fixtures | [Shared Fixtures](#shared-fixtures) | In Development | Root conftest and application-level conftest patterns |
| req-tap-test-conventions | [Test Conventions](#test-conventions) | In Development | Naming, style, and structural conventions |
| req-tap-test-spec-linkage | [Spec Linkage](#spec-linkage) | In Development | Connecting tests to acceptance criteria |
| req-tap-test-plugins | [Plugin Test Integration](#plugin-test-integration) | In Development | How plugin tests fit into the overall suite |

### Test Discovery
----
RID: `req-tap-test-discovery`
Status: `Implemented`

pytest discovers and runs all project tests from a single invocation.

#### Status Details
Implemented in `pyproject.toml` under `[tool.pytest.ini_options]`.

#### Implementation

**Configuration** (`pyproject.toml`):

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "tap.settings"
testpaths = ["tap_grid", "tap_plugins", "tap_api", "tap_web", "tap_viz", "plugins"]
python_files = ["test_*.py", "*_test.py"]
addopts = "-v --tb=short"
```

**Running tests:**

| Scope | Command |
| --- | --- |
| Full suite | `docker compose exec web uv run pytest` |
| Single app | `docker compose exec web uv run pytest tap_grid/` |
| Single plugin | `docker compose exec web uv run pytest plugins/lotr/` |
| Single file | `docker compose exec web uv run pytest tap_grid/tests/test_services.py` |
| Single test | `docker compose exec web uv run pytest tap_grid/tests/test_services.py::test_name` |
| By marker | `docker compose exec web uv run pytest -m "spec"` |

The `testpaths` list is ordered to match the application scaffolding priority. New applications should be added here when they gain tests.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-test-discovery-1 | Single Command Full Suite | Implemented | `pytest` at repo root discovers and runs all application and plugin tests. | |
| req-tap-test-discovery-2 | Per-App Isolation | Implemented | `pytest <app>/` runs only that application's tests. | |
| req-tap-test-discovery-3 | Per-Plugin Isolation | Implemented | `pytest plugins/<name>/` runs only that plugin's tests. | |
| req-tap-test-discovery-4 | Standard File Patterns | Implemented | Test files match `test_*.py` or `*_test.py`. | |

#### Future
As the project grows, pytest markers or labels may be added for categorizing tests (e.g. `slow`, `integration`) beyond spec linkage.

### Test Layout By Application
----
RID: `req-tap-test-layout`
Status: `In Development`

Each Django application owns a `tests/` directory containing tests for the behavior it is responsible for.

#### Implementation

| Application | `tests/` Directory | Owns |
| --- | --- | --- |
| `tap_grid` | `tap_grid/tests/` | Entity, Edge, BaseModel, service layer, FLIP, batch, history, dimensions, search, registry, GRIFT import, validation, constraints, icons |
| `tap_plugins` | `tap_plugins/tests/` | Plugin system machinery: discovery, manifest loading, registration, validation harness |
| `tap_api` | `tap_api/tests/` | API endpoints, serialization, auth, versioning, plugin API mounting |
| `tap_web` | `tap_web/tests/` | Web shell, panels, editors, page rendering, template behavior |
| `tap_viz` | `tap_viz/tests/` | Visualization models, views, Cytoscape integration |
| `plugins/<name>` | `plugins/<name>/tests/` | Plugin-specific behavior: custom editors, search runners, domain logic. See `spec-plugin-testing.md`. |

Each `tests/` directory must contain an `__init__.py`.

**Ownership rule:** A test belongs to the application that owns the behavior under test, not the application that triggers it. For example, a test that verifies search execution belongs in `tap_grid/tests/`, even if a plugin search runner is the subject, because search execution is grid-owned behavior.

**Exception:** Plugin-specific tests that validate a plugin's unique functionality (e.g. a custom editor's form validation logic) belong in that plugin's `tests/` directory.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-test-layout-1 | Tests Dir Per App | In Development | Each application with testable behavior has a `tests/` directory with `__init__.py`. | |
| req-tap-test-layout-2 | Ownership By Behavior | In Development | Tests live in the application that owns the behavior being tested. | |
| req-tap-test-layout-3 | No Cross-App Test Dependencies | In Development | Application tests do not import from other applications' test modules. | |

#### Future
If test count grows large within an application, subdirectories within `tests/` (e.g. `tests/search/`, `tests/service/`) may be introduced.

### Shared Fixtures
----
RID: `req-tap-test-fixtures`
Status: `In Development`

Shared test fixtures live in `conftest.py` files at the appropriate scope.

#### Implementation

**Root `conftest.py`:** Contains fixtures used across all applications. Currently provides `default_caller_context` (autouse) which sets up a `CallerContext` with a fresh `batch_id` for every test so FLIP-enabled models work without manual setup.

**Application `conftest.py`:** Contains fixtures specific to that application's test needs. Example: `tap_api/tests/conftest.py` provides API client fixtures.

**Plugin `conftest.py`:** Plugins may provide their own `conftest.py` in `tests/` for plugin-specific fixtures.

Fixtures should be placed at the narrowest scope that makes sense:
- Root conftest: truly universal fixtures (caller context, database setup)
- App conftest: app-specific helpers (API clients, web request factories)
- Test file: fixtures used only in that file

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-test-fixtures-1 | Root Caller Context | Implemented | Root conftest provides autouse `default_caller_context` fixture. | |
| req-tap-test-fixtures-2 | Narrowest Scope Placement | In Development | Fixtures live at the narrowest conftest scope that covers their usage. | |
| req-tap-test-fixtures-3 | No Fixture Leakage | In Development | App-level fixtures do not depend on other apps' conftest files. | |

#### Future
Factory-based test data generation (e.g. factory_boy) may be introduced when the number of model types makes manual setup painful.

### Test Conventions
----
RID: `req-tap-test-conventions`
Status: `In Development`

Tests follow consistent naming, style, and structural conventions.

#### Implementation

**Naming:**
- Test files: `test_<topic>.py` (e.g. `test_services.py`, `test_search_orm.py`)
- Test functions: `test_<what_it_does>` — describe the behavior, not the method (e.g. `test_create_entity_assigns_uuid` not `test_create`)
- Test classes: optional, use when grouping related tests (e.g. `TestSearchExecution`)

**Style:**
- Arrange-Act-Assert structure
- One logical assertion per test where practical
- Use early returns and `pytest.raises` for negative scenarios
- Prefer service-layer setup over direct ORM writes for TAP-managed data (per CLAUDE.md)
- Direct ORM setup is appropriate when intentionally testing model-level behavior

**Database:**
- Tests use Django's test database (created and destroyed per test run)
- PostgreSQL features (JSON fields, constraints) are available and should be tested
- Tests requiring cross-database-alias visibility (e.g. search readonly) must declare `databases=["default", "search_readonly"]` and use `transaction=True`

**What to test:**
- Test behavior, not implementation
- Test both positive and negative scenarios
- Test boundary conditions and edge cases for critical paths
- Do not test Django framework behavior (e.g. that `CharField` enforces `max_length`)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-test-conventions-1 | Service Layer Setup Preferred | In Development | Application-level tests prefer service-layer setup over direct ORM writes. | |
| req-tap-test-conventions-2 | Behavior Over Implementation | In Development | Tests validate observable behavior rather than internal implementation details. | |
| req-tap-test-conventions-3 | Positive And Negative Scenarios | In Development | Tests cover both success and failure paths. | |

#### Future
Linting or custom pytest plugins may enforce naming conventions automatically.

### Spec Linkage
----
RID: `req-tap-test-spec-linkage`
Status: `In Development`

Tests are connected to spec acceptance criteria through pytest markers.

#### Implementation

Tests reference acceptance criteria using `@pytest.mark.spec`:

```python
@pytest.mark.spec("req-grid-dimension-core-1")
def test_dimensions_json_shape():
    ...
```

A single test may reference multiple ACIDs. A requirement moves to `Verified` status when all of its acceptance criteria have passing, linked tests.

The `spec` marker is registered in `pyproject.toml`:

```toml
markers = [
    "spec: link a test to one or more spec acceptance criteria by ACID",
]
```

Not every test needs a spec link. Tests that cover implementation details, edge cases beyond the spec, or exploratory scenarios may omit the marker.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-test-spec-linkage-1 | Marker Registered | Implemented | `spec` marker is registered in pytest config. | |
| req-tap-test-spec-linkage-2 | ACID As Argument | In Development | The marker takes one or more ACID strings as arguments. | |
| req-tap-test-spec-linkage-3 | Verified Status Convention | In Development | A requirement reaches Verified when all ACIDs have linked passing tests. | |

#### Future
A spec-coverage report tool could scan tests for `@pytest.mark.spec` and cross-reference with spec files to identify untested acceptance criteria.

### Plugin Test Integration
----
RID: `req-tap-test-plugins`
Status: `In Development`

Plugin tests are discovered and run as part of the full test suite alongside application tests.

#### Implementation

Plugin tests live in `plugins/<name>/tests/` and are discovered via the `plugins` entry in `testpaths`. They participate in the same pytest run as application tests and have access to the same root fixtures.

Plugin tests fall into two categories:

1. **Plugin validation tests** — standardized tests provided by the plugin system (`tap_plugins`) that any plugin can run to verify structural correctness. See `spec-plugin-testing.md` in `tap_plugins/specs/`.

2. **Plugin-specific tests** — hand-written tests for net-new functionality unique to the plugin (custom editors, search runners, domain logic).

The plugin system's own machinery tests (manifest loading, registration, validation harness) live in `tap_plugins/tests/`, not in individual plugins.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-test-plugins-1 | Plugins In Test Paths | Implemented | `plugins` is included in pytest `testpaths`. | |
| req-tap-test-plugins-2 | Plugin Tests Discovered | In Development | Tests in `plugins/<name>/tests/` are discovered by `pytest`. | |
| req-tap-test-plugins-3 | Root Fixtures Available | In Development | Plugin tests have access to root conftest fixtures (e.g. `default_caller_context`). | |
| req-tap-test-plugins-4 | Two Categories | In Development | Plugin testing is split between standardized validation and plugin-specific behavior tests. | |

#### Future
User-facing verification testing (running self-tests on a live system) is explicitly deferred. When it is introduced, it will likely be specified as a separate requirement in this spec or in a dedicated product-level testing spec.
