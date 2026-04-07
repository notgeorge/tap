# Plugin Testing Specification

## Philosophy

Plugins extend TAP with new node types, edge types, editors, searches, and seed data. Every plugin should be verifiable — both that its structural declarations are correct and that its custom behavior works as intended. The plugin system should make structural validation free: if you followed the conventions, a standardized test suite catches your mistakes. Custom behavior tests are the plugin author's responsibility, but the framework should make them easy to write.

This spec covers the plugin validation harness provided by `tap_plugins` and the conventions for per-plugin tests. The overall testing strategy is defined in `specs/spec-tap-testing.md`.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Free Validation | A plugin gets structural validation tests automatically by following conventions |
| 2. | Clear Boundary | Plugin system tests (in `tap_plugins`) are distinct from individual plugin tests (in `plugins/<name>`) |
| 3. | Actionable Failures | Validation failures tell the plugin author exactly what is wrong and where |
| 4. | Composable | Plugin authors can mix standardized validation with their own custom tests |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-plugin-test-system | [Plugin System Tests](#plugin-system-tests) | In Development | Tests for the plugin machinery itself |
| req-plugin-test-harness | [Plugin Validation Harness](#plugin-validation-harness) | Proposed | Standardized validation that any plugin can run |
| req-plugin-test-custom | [Plugin-Specific Tests](#plugin-specific-tests) | In Development | Conventions for hand-written plugin tests |

### Plugin System Tests
----
RID: `req-plugin-test-system`
Status: `In Development`

The plugin system's own machinery is tested in `tap_plugins/tests/`.

#### Status Details
In Development. The plugin system exists and is functional but its test coverage is evolving.

#### Implementation

Plugin system tests live in `tap_plugins/tests/` and validate the framework, not any specific plugin. They answer: "does the plugin machinery work?"

These tests cover:

- **Manifest loading:** TOML parsing, field validation, unknown key rejection
- **Plugin discovery:** `TapPluginConfig` auto-derivation of `name`, `label`, `verbose_name`
- **Model registration:** Manifest-declared models resolve to concrete TAP-managed classes
- **Edge type loading:** `.edge.json` parsing, schema validation, constraint registration
- **Editor registration:** Descriptor class resolution and entity type matching
- **Search runner registration:** Callable resolution and scoped registry integration
- **GRIFT auto-import:** Bundle path validation, upsert idempotency, database-not-ready tolerance
- **Path validation:** Required directories, undeclared file warnings, path traversal rejection

These tests use real plugins (e.g. LOTR, administrivia) as test fixtures, but the subject under test is the framework behavior, not the plugin content.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-test-system-1 | Tests In tap_plugins | In Development | Plugin system tests live in `tap_plugins/tests/`. | |
| req-plugin-test-system-2 | Framework Not Plugin | In Development | System tests validate plugin machinery, not individual plugin content. | |
| req-plugin-test-system-3 | Real Plugin Fixtures | In Development | System tests may use real installed plugins as test fixtures. | |

#### Future
A minimal test-only fixture plugin (not LOTR) may be introduced to decouple system tests from the example plugins.

### Plugin Validation Harness
----
RID: `req-plugin-test-harness`
Status: `Proposed`

`tap_plugins` provides a standardized validation harness that any plugin can run to verify its structural correctness.

#### Status Details
Proposed. This is the "free validation" that plugin authors get for following conventions.

#### Implementation

The validation harness is a pytest base class (or set of fixtures) that lives in `tap_plugins`. A plugin's test suite can use it to automatically validate:

**Manifest integrity:**
- `tap-plugin.toml` parses as valid TOML
- All required top-level fields are present and non-empty
- `manifest_version` matches the expected version
- No unknown top-level keys

**Model declarations:**
- Every `[models]` entry resolves to a concrete TAP-managed model class
- Each resolved class has an `ENTITY_TYPE` matching the manifest slug key
- Each model class has a corresponding migration

**Edge declarations:**
- Every `[edges]` entry points to an existing `.edge.json` file
- Each edge definition file parses as valid JSON
- Each edge definition has required fields (`slug`, `name`, `description`)
- Each edge file `slug` matches its manifest key
- `sources` and `targets` (when present) reference entity types declared in this plugin or in registered plugins
- No unknown keys in edge definition files

**Editor declarations:**
- Every `[editors]` entry resolves to a concrete `EditorDescriptor` class
- Each descriptor's entity type matches the manifest key

**Search declarations:**
- Every `[searches]` entry resolves to a callable
- Each callable is registered (or registrable) in the scoped search runner registry

**GRIFT declarations:**
- Every `[grift]` entry points to an existing `.grift.json` file
- Each GRIFT file parses as valid JSON
- Each GRIFT file conforms to the GRIFT v0 envelope schema
- Node references within GRIFT files reference entity types declared in this plugin or in registered plugins

**Full load cycle:**
- The plugin can complete a full registration and GRIFT import cycle without errors
- After import, entities declared in GRIFT files exist on the grid

#### Usage

A plugin author adds a single test file to get all structural validation:

```python
# plugins/my_plugin/tests/test_plugin_validation.py

from tap_plugins.testing import PluginValidationTestCase


class TestMyPluginValidation(PluginValidationTestCase):
    plugin_slug = "my_plugin"
```

The base class discovers the plugin by slug, loads its manifest, and runs all applicable structural checks. Checks are skipped gracefully when a manifest section is absent (e.g. no `[editors]` means editor checks are skipped).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-test-harness-1 | Base Class Exists | Proposed | `tap_plugins.testing` provides `PluginValidationTestCase`. | |
| req-plugin-test-harness-2 | Manifest Integrity Checks | Proposed | The harness validates manifest TOML structure and field presence. | |
| req-plugin-test-harness-3 | Model Resolution Checks | Proposed | The harness validates that declared model classes resolve and match slugs. | |
| req-plugin-test-harness-4 | Edge File Checks | Proposed | The harness validates edge definition files parse, have required fields, and match slugs. | |
| req-plugin-test-harness-5 | Editor Resolution Checks | Proposed | The harness validates editor descriptor resolution and entity type matching. | |
| req-plugin-test-harness-6 | Search Callable Checks | Proposed | The harness validates search runner callable resolution. | |
| req-plugin-test-harness-7 | GRIFT File Checks | Proposed | The harness validates GRIFT files parse and conform to the v0 envelope schema. | |
| req-plugin-test-harness-8 | Full Load Cycle | Proposed | The harness validates the plugin can complete registration and GRIFT import. | |
| req-plugin-test-harness-9 | Graceful Section Skip | Proposed | Missing manifest sections (e.g. no `[editors]`) cause checks to be skipped, not to fail. | |
| req-plugin-test-harness-10 | Actionable Failure Messages | Proposed | Validation failures include the manifest key, file path, or class path that failed. | |

#### Future
The validation harness may evolve into a `manage.py validate_plugin <slug>` management command for non-test-suite usage. A `--strict` flag could treat warnings (undeclared files) as errors.

### Plugin-Specific Tests
----
RID: `req-plugin-test-custom`
Status: `In Development`

Plugins may include hand-written tests for behavior unique to that plugin.

#### Status Details
In Development. LOTR currently has custom tests in `plugins/lotr/tests/`.

#### Implementation

Plugin-specific tests live in `plugins/<name>/tests/` and validate net-new functionality that the standardized harness cannot cover:

- **Custom editor logic:** Form validation rules, field transformations, save behavior
- **Custom search runners:** Runner callable returns expected results for known data
- **Domain constraints:** Plugin-specific business rules beyond what edge/model declarations encode
- **Complex edge scenarios:** Multi-hop or conditional relationships unique to the plugin's domain

**Conventions:**
- Test files follow the standard `test_*.py` naming pattern
- Tests have access to root conftest fixtures (e.g. `default_caller_context`)
- Tests may use `conftest.py` in the plugin's `tests/` directory for plugin-specific fixtures
- Tests should use the service layer for entity/edge setup, not direct ORM writes
- Test file names should be prefixed with the plugin slug for clarity when viewing full-suite output (e.g. `test_lotr_constraints.py` not `test_constraints.py`)

**What not to test in plugins:**
- Framework behavior (manifest loading, GRIFT import mechanics) — that belongs in `tap_plugins/tests/`
- Core grid behavior (entity creation, edge constraints) — that belongs in `tap_grid/tests/`
- The standardized validation checks — use the harness instead

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-plugin-test-custom-1 | Tests In Plugin Directory | In Development | Plugin-specific tests live in `plugins/<name>/tests/`. | |
| req-plugin-test-custom-2 | Slug-Prefixed File Names | In Development | Test file names are prefixed with the plugin slug. | |
| req-plugin-test-custom-3 | Service Layer Setup | In Development | Plugin tests use the service layer for TAP-managed data setup. | |
| req-plugin-test-custom-4 | No Framework Testing | In Development | Plugin tests do not duplicate framework or core grid test coverage. | |

#### Future
If plugins grow complex enough to warrant integration test suites (e.g. testing a plugin's API endpoints), conventions for those will be added here.
