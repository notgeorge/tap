# TAP Logging Specification

## Philosophy

TAP runs as a Django web process plus a Steady Queue supervisor (`docker/entrypoint.sh`), with first-party apps (`tap_grid`, `tap_api`, `tap_cares`, `tap_web`, `tap_viz`, `tap_plugins`) and third-party plugins (`plugins/<slug>/...`) all running in the same Python process. Today every one of those components emits log records through `logging.getLogger(__name__)` to Python's root logger, which has no configured handlers or formatters in `tap/settings.py` — so output lands on container stdout/stderr through Django's default handler with no per-component levels and no consistent format. That works for "tail and read" but breaks down as soon as you want to crank `tap_cares.scheduler` to DEBUG, silence `django.db.backends`, or tell at a glance whether a noisy line came from `plugins.fedramp_20x_ksi` or `plugins.genericom`.

This spec defines the v0 logging configuration: a single `LOGGING` dict in `tap/settings.py` that names each first-party app and each registered plugin as its own logger, applies a consistent text format that includes source file and line on every record, and exposes per-logger level overrides through environment variables. It also defines a call-site site-ID convention — a stable identifier of the form `[tap_cares-a8f3]` that travels with the log statement across refactors — enforced by a scanner test with a baseline-ratchet so existing code isn't broken on day one. Library log levels are owned where they make sense: foundational libraries used transitively by anything (`urllib3`, `django.*`) stay top-level; libraries pulled in for a specific component's job (`steady_queue` for `tap_cares`, `boto3` for an AWS plugin) are owned by that component through an `app_logger_config()` helper.

The spec is intentionally **stdout-only and text-format** for v0 — disk retention, structured (JSON) logging, correlation IDs, and external aggregators are deferred (see [Future](#future)). The configuration is structured so those later upgrades are formatter / handler swaps and structured-field additions, not a rewrite.

Logging is read-only by construction. Nothing in this spec describes capturing application telemetry into the TAP grid (`Entity`, `Edge`, `ScheduleFire`, `CollectionJob`); the grid already records application decisions and outcomes, and infrastructure log lines belong in the log stream, not the graph.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Per-Component Visibility | Every first-party app and every registered plugin has a named logger whose level can be tuned independently. |
| 2. | Plugin Disambiguation | Plugin log records are visibly attributable to a specific plugin slug without grepping for module paths. |
| 3. | Source Traceability | Every log record points back to the exact file, line, and stable site ID that emitted it without inferring location from message content. |
| 4. | Ownership-Aligned Library Config | Third-party library log levels live with the component that owns the library (foundational libs top-level, component-pulled libs scoped to that component). |
| 5. | Runtime Tunability | Operators can raise or lower individual logger levels via environment variables without code changes. |
| 6. | Upgrade-Friendly | The v0 shape is a stepping stone — switching to JSON, adding a file handler, or attaching an external shipper is a localized change, not a rewrite. |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-logging-config-location | [Configuration Location](#configuration-location) | Proposed | Single `LOGGING` dict in `tap/settings.py`, built by `tap/logging.py`'s helper |
| req-tap-logging-format | [Log Format](#log-format) | Proposed | Text formatter — timestamp, level, logger, pathname:lineno, message |
| req-tap-logging-app-loggers | [First-Party App Loggers](#first-party-app-loggers) | Proposed | One logger per `tap_*` app with a sensible default level |
| req-tap-logging-plugin-loggers | [Plugin Loggers](#plugin-loggers) | Proposed | `plugins.<slug>` namespace; per-plugin level + wildcard default |
| req-tap-logging-foundational-loggers | [Foundational Third-Party Loggers](#foundational-third-party-loggers) | Proposed | `urllib3`, `django.*` — pan-system libs with no single owner |
| req-tap-logging-component-libs | [Component-Owned Library Loggers](#component-owned-library-loggers) | Proposed | Apps and plugins own levels for libs they pulled in (e.g. `steady_queue` → `tap_cares`) |
| req-tap-logging-callsite-convention | [Call-Site Convention](#call-site-convention) | Proposed | `logger = logging.getLogger(__name__)`, `%s` placeholders, `.exception` in `except` |
| req-tap-logging-site-ids | [Call-Site Site IDs](#call-site-site-ids) | Proposed | Stable `[<slug>-<hex>]` IDs at INFO and above; prefix is the containing app/plugin slug |
| req-tap-logging-site-id-scanner | [Site-ID Scanner](#site-id-scanner) | Proposed | Pytest scanner with slug-locality and uniqueness checks; baseline-ratchet enforcement |
| req-tap-logging-env-overrides | [Environment Overrides](#environment-overrides) | Proposed | `TAP_LOG_LEVELS` (comma-separated) + `TAP_LOG_LEVEL` (root) |
| req-tap-logging-no-grid-mutation | [No Grid Mutation From Logging](#no-grid-mutation-from-logging) | Proposed | Handlers must not write to TAP-managed entities or edges |

## Requirements

### Configuration Location
----
RID: `req-tap-logging-config-location`
Status: `Proposed`

All logging configuration assembly lives in `tap/logging.py`; the assembled dict is exposed as `LOGGING` in `tap/settings.py`. `tap/test_settings.py` may override or extend it (e.g. silence noisy loggers under pytest), but the canonical shape is built once.

#### Implementation

- `tap/logging.py` exports `build_logging_config()` which returns a `dictConfig`-shaped dict:
  - `version: 1`, `disable_existing_loggers: False`.
  - One `formatters` section containing the `tap` formatter.
  - One `handlers` section containing the `console` handler.
  - One `loggers` section assembled by merging, in order:
    1. Top-level defaults for first-party apps (`req-tap-logging-app-loggers`).
    2. Top-level defaults for foundational third-party libraries (`req-tap-logging-foundational-loggers`).
    3. Per-app contributions via each app's `<app>.logging.app_logger_config()` helper (`req-tap-logging-component-libs`).
    4. Per-plugin contributions via the manifest registry helper (`req-tap-logging-plugin-loggers`).
    5. Environment-variable overrides applied last (`req-tap-logging-env-overrides`).
  - A `root` entry at `WARNING` so anything not explicitly named still produces output for unhandled cases.
- `tap/settings.py` contains `LOGGING = build_logging_config()`. Django picks the dict up automatically because Django reads `settings.LOGGING` and applies it via `logging.config.dictConfig` during startup.
- The Steady Queue supervisor process and the Django web process share the same settings module, so both processes get the same logger tree.
- `disable_existing_loggers: False` is required so loggers created by imported modules before `LOGGING` is applied (Django itself, Steady Queue, plugins) keep working.

#### Development

A single source for the config matters more than the config's complexity. Splitting the *top-level* config across each app's `apps.py` would scatter level decisions and make it hard to silence one component when triaging a noisy log stream. The pattern here keeps a central assembly point in `tap/logging.py` while letting each app contribute through a well-defined helper — central enough to read in one place, decentralized enough that adding a new app or plugin doesn't require editing settings.

`test_settings.py` is allowed to override the dict to keep pytest output readable — e.g. setting the `tap_grid` and `tap_cares` loggers to WARNING under tests — but the override should be a localized diff, not a full re-spec of the tree.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-config-location-1 | Builder Module | Proposed | `tap/logging.py` exports `build_logging_config()` returning a `dictConfig`-shaped dict. | |
| req-tap-logging-config-location-2 | Settings Assignment | Proposed | `tap/settings.py` assigns `LOGGING = build_logging_config()`. | |
| req-tap-logging-config-location-3 | Test Override Allowed | Proposed | `tap/test_settings.py` may override individual logger levels or handlers without redefining the whole dict. | |
| req-tap-logging-config-location-4 | Disable-Existing False | Proposed | The config uses `"disable_existing_loggers": False`. | |
| req-tap-logging-config-location-5 | Merge Order | Proposed | The builder merges in the documented order so env-var overrides win last. | |

### Log Format
----
RID: `req-tap-logging-format`
Status: `Proposed`

A single text formatter governs every record routed through the configured handler. The format includes the source file and line on every record so a developer can navigate from a log line to the emitting source without inferring location from message content.

#### Implementation

- One formatter named `tap` is defined under `LOGGING["formatters"]`.
- Format string: `"%(asctime)s %(levelname)-8s %(name)s %(pathname)s:%(lineno)d — %(message)s"`.
- `datefmt`: `"%Y-%m-%dT%H:%M:%S%z"` (ISO-8601 with timezone).
- One handler named `console` writes to `sys.stderr` using `class: logging.StreamHandler` with `formatter: tap`.
- All configured loggers route to the `console` handler.
- Levelname is left-padded to 8 characters so log lines line up visually (`INFO    `, `WARNING `, `ERROR   `).

Example line (with a site ID from `req-tap-logging-site-ids`):

```
2026-05-14T14:32:11+0000 INFO     tap_cares.scheduler /app/tap_cares/scheduler.py:307 — [tap_cares-a8f3] scheduler_tick: produced 2 fire(s)
```

#### Development

Text format is the v0 choice because it's readable in `scripts/dc logs web` without tooling, and the migration path to JSON (see [Future](#future)) is swapping the formatter — no call-site changes. Records continue using `logger.info("text with %s", arg)` rather than `logger.info("text", extra={"arg": ...})` until the structured-format requirement lands, since `extra={}` payloads are invisible in text format and add cost without buying anything in v0.

`%(pathname)s` (full path) is used rather than `%(filename)s` (basename) because most terminals and IDEs offer click-through navigation on the full-path-with-line pattern. Inside the container `pathname` will be `/app/tap_cares/scheduler.py`; that's correct because the project root is bind-mounted at `/app`, and terminal click-through resolves to the host path through the IDE's project mapping. `%(name)s` is preserved alongside `%(pathname)s` so grepping logs by logger name remains as easy as grepping by file.

Writing to stderr (not stdout) follows the long-standing Unix convention that logs are a sideband, not the program's primary output. Docker captures both into the same stream so this is invisible operationally, but it matters for any future tee/redirect setup.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-format-1 | Single Formatter | Proposed | Exactly one formatter (`tap`) is defined in v0. | |
| req-tap-logging-format-2 | ISO Timestamp | Proposed | The formatter emits ISO-8601 timestamps with timezone offset. | |
| req-tap-logging-format-3 | Padded Level | Proposed | Levelname is left-padded to 8 characters. | |
| req-tap-logging-format-4 | Source Location | Proposed | The formatter includes `pathname:lineno` on every record. | |
| req-tap-logging-format-5 | Stderr | Proposed | The `console` handler writes to `sys.stderr`. | |

### First-Party App Loggers
----
RID: `req-tap-logging-app-loggers`
Status: `Proposed`

Each first-party Django app has a named logger whose default level is set explicitly in `LOGGING["loggers"]`.

#### Implementation

The following loggers are declared explicitly. Each entry sets `level`, `handlers: ["console"]`, and `propagate: False` (so each app's records hit the console handler exactly once and don't bubble through the root logger).

| Logger | Default Level | Rationale |
| --- | --- | --- |
| `tap_grid` | `INFO` | Service-layer mutations and migration events are useful in dev; per-record overhead is low. |
| `tap_api` | `INFO` | Request-level errors at the API boundary. |
| `tap_cares` | `INFO` | Scheduler tick decisions, collector dispatch events; one info line per tick is acceptable cadence. |
| `tap_web` | `INFO` | Page / panel rendering errors. |
| `tap_viz` | `INFO` | Visualization rendering errors. |
| `tap_plugins` | `INFO` | Plugin manifest loading, GRIFT import progress. |
| `tap_flip` | `INFO` | Reserved; emits records once the app exists. |
| `tap_ai` | `INFO` | Reserved; emits records once the app exists. |

Sub-loggers (e.g. `tap_cares.scheduler`, `tap_grid.services`) inherit from their parent and do not need explicit entries unless they require a different level than the parent app.

#### Development

Per-app loggers are declared explicitly rather than relying on the root logger's default because the env-override mechanism (`req-tap-logging-env-overrides`) needs a known set of logger names to attach to. A wildcard root + propagation would work but makes "raise `tap_cares` to DEBUG" harder to wire as a single env var.

`tap_flip` and `tap_ai` are listed for forward compatibility — their entries are inert until those apps exist, and adding the entries now means the env-override convention works the moment those apps land.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-app-loggers-1 | All Apps Declared | Proposed | Every `tap_*` first-party app has an entry in `LOGGING["loggers"]`. | |
| req-tap-logging-app-loggers-2 | INFO Default | Proposed | The default level for every first-party app logger is `INFO`. | |
| req-tap-logging-app-loggers-3 | No Propagation | Proposed | Each app logger sets `propagate: False`. | |

### Plugin Loggers
----
RID: `req-tap-logging-plugin-loggers`
Status: `Proposed`

Plugins are addressable through the logger tree by slug, so a noisy plugin can be silenced without touching its code.

#### Implementation

- All plugins follow the call-site convention (`req-tap-logging-callsite-convention`); their module-level `getLogger(__name__)` calls produce loggers named `plugins.<plugin_slug>.<module>`.
- `LOGGING["loggers"]` declares one entry per registered plugin slug, plus a wildcard fallback at `plugins`:
  - `plugins`: `INFO` — catches any plugin that hasn't been individually listed.
  - `plugins.<slug>`: explicit per-plugin entry for each plugin shipped with the platform.
- Per-plugin entries set `propagate: False` so a plugin's records don't double-emit through both `plugins` and `plugins.<slug>`.
- The list of explicit plugin slugs is generated from the registered plugin set at settings-load time. `tap/logging.py` exposes `plugin_logger_config()` which iterates the plugin manifest registry and returns the per-slug `{logger: {level, handlers, propagate}}` map; the builder merges it into `LOGGING["loggers"]`.

Currently shipping plugins (snapshot at spec authoring):

| Plugin Slug | Logger | Default Level |
| --- | --- | --- |
| `administrivia` | `plugins.administrivia` | `INFO` |
| `fedramp_20x_ksi` | `plugins.fedramp_20x_ksi` | `INFO` |
| `genericom` | `plugins.genericom` | `INFO` |
| `aws_core` | `plugins.aws_core` | `INFO` |
| `computing_core` | `plugins.computing_core` | `INFO` |

The list updates automatically as plugins are registered or removed.

#### Development

Plugin disambiguation is the second goal of this spec because it's the dimension dev pain shows up along — when triaging a noisy log stream, "which plugin is this?" is the first question and the current logger name (`plugins.fedramp_20x_ksi.panels.finding_strip`) already answers it once the format is in place. The wildcard `plugins` entry exists so a plugin that's mid-development and not yet registered still gets its records formatted and shipped — it just shares the default level until it's added explicitly.

Generating the per-slug entries from the manifest registry (rather than a hand-maintained list in settings) means adding a plugin doesn't require a settings edit. The builder calls the helper lazily — if the manifest registry isn't available at settings load time (e.g. circular import), the helper falls back to the wildcard-only config and a warning is logged.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-plugin-loggers-1 | Wildcard Plugin Logger | Proposed | `LOGGING["loggers"]` declares a `plugins` entry at `INFO`. | |
| req-tap-logging-plugin-loggers-2 | Per-Slug Entries | Proposed | Each registered plugin slug has a `plugins.<slug>` entry. | |
| req-tap-logging-plugin-loggers-3 | Helper-Driven | Proposed | Per-slug entries are generated by `tap/logging.py::plugin_logger_config()` reading the manifest registry, not hand-maintained in settings. | |
| req-tap-logging-plugin-loggers-4 | No Propagation | Proposed | Per-plugin loggers set `propagate: False`. | |

### Foundational Third-Party Loggers
----
RID: `req-tap-logging-foundational-loggers`
Status: `Proposed`

A *foundational* third-party library is one used transitively by anything in the platform, with no single component owning its lifecycle. Foundational loggers are configured at the top level of `LOGGING["loggers"]` because no app or plugin can own them.

#### Implementation

Foundational libraries shipped by the platform:

| Logger | Default Level | Foundational Because |
| --- | --- | --- |
| `django` | `INFO` | The web framework itself. |
| `django.db.backends` | `WARNING` | Used by every model. DEBUG emits every SQL query — invaluable when explicitly investigating, deafening by default. |
| `django.server` | `WARNING` | The dev server's per-request log line is noise once the app is past hello-world. |
| `urllib3` | `WARNING` | The underlying sync HTTP layer used by `requests`, `botocore`, `httpx` (sync), Kubernetes/Docker SDKs, Elasticsearch, and most other HTTP-speaking libraries. No single component owns it. |

All entries route to the `console` handler with `propagate: False`.

#### Development

The distinction between foundational and component-owned libraries is the second key axis of this spec (after the loggers-by-component axis). Drawing the line by *ownership*, not by *origin*, means new libraries added to the platform have a clear home: if one app pulls it in for a specific job, that app owns it; if it's used everywhere by everything, it's foundational.

`urllib3` is the canonical foundational case worth calling out explicitly. The library that most often emits the *signal* a developer cares about is the wrapper (`botocore`, `requests`, `httpx`), not `urllib3` itself — wrappers are component-owned because the AWS plugin pulled in `boto3`, the HTTP-fetching plugin pulled in `requests`, etc. So `urllib3`-at-WARNING-globally is a backstop; raising or silencing the per-component wrapper is where actual triage happens.

`django.db.backends` is called out specifically because DEBUG-level SQL logging is one of the most-toggled levels in dev, and it should be a one-env-var change (see `req-tap-logging-env-overrides`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-foundational-loggers-1 | Django Framework | Proposed | `django` logger is configured at `INFO`. | |
| req-tap-logging-foundational-loggers-2 | Django DB Backends | Proposed | `django.db.backends` is configured at `WARNING` by default. | |
| req-tap-logging-foundational-loggers-3 | Django Server | Proposed | `django.server` is configured at `WARNING` by default. | |
| req-tap-logging-foundational-loggers-4 | urllib3 | Proposed | `urllib3` is configured at `WARNING` by default. | |
| req-tap-logging-foundational-loggers-5 | Ownership Rule | Proposed | A library is configured here only if no first-party app or plugin owns it. Libraries with a clear owner go through `req-tap-logging-component-libs`. | |

### Component-Owned Library Loggers
----
RID: `req-tap-logging-component-libs`
Status: `Proposed`

Third-party libraries pulled in for a specific component's job have their log levels configured by that component, not at the top level. The mechanism is symmetric between first-party apps and plugins.

#### Implementation

- Any app or plugin that pulls in a third-party library *and* wants to set its default log level exports an `app_logger_config()` (apps) or `plugin_logger_config()` (plugins) function from a `logging` submodule.
- Signature: `def app_logger_config() -> dict[str, dict]:` — returns a mapping of `{logger_name: {level, handlers, propagate}}` entries that will be merged into `LOGGING["loggers"]`.
- The builder in `tap/logging.py` discovers app helpers by attempting `from <app>.logging import app_logger_config` for each installed first-party app. Missing modules are silently skipped — an app that doesn't pull in any third-party libraries doesn't need a `logging` module.
- For plugins, the same discovery runs through the manifest registry rather than a hardcoded list of apps.
- The component that pulls in the library owns the helper that configures it.

Initial usage:

| Component | Helper | Owned Libraries |
| --- | --- | --- |
| `tap_cares` | `tap_cares/logging.py` | `steady_queue` (INFO) |

`steady_queue` is `tap_cares`-owned because `tap_cares` is the only consumer — it imports `steady_queue` for the `@recurring` decorator (`tap_cares/task_backend.py`) and the entrypoint runs the `manage.py steady_queue` supervisor. If a second consumer ever emerges, `steady_queue` becomes a candidate for promotion to foundational.

#### Development

This mirrors the architectural rule already in CLAUDE.md: plugins own their surface, apps own their domain. Logging is just one more surface, and configuring a library's log level is part of taking responsibility for that library.

The discovery pattern (look for `<app>.logging.app_logger_config`) means there's no manifest of which apps configure which libraries — it's discoverable by code search and follows whoever imports the library. If `tap_cares` ever stops using `steady_queue`, removing the helper removes the level config in the same change.

A plugin that pulls in `boto3` (AWS plugin) would export `boto3` and `botocore` levels through the same mechanism. Currently no plugin ships such a helper because no plugin currently uses `boto3` from running code, but the path is clear when it does.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-component-libs-1 | Helper Signature | Proposed | Apps export `<app>.logging.app_logger_config() -> dict[str, dict]`; plugins export the equivalent through the manifest registry. | |
| req-tap-logging-component-libs-2 | Builder Discovery | Proposed | `build_logging_config()` discovers app helpers by import attempt; missing helpers are silently skipped. | |
| req-tap-logging-component-libs-3 | Steady Queue Owned By tap_cares | Proposed | `steady_queue` log level is configured in `tap_cares/logging.py`, not at the top level of the platform config. | |

### Call-Site Convention
----
RID: `req-tap-logging-callsite-convention`
Status: `Proposed`

Every module that emits log records does so through a logger whose name equals the module path, uses `%s`-style placeholders, and emits tracebacks via `logger.exception` in `except` blocks.

#### Implementation

- At the top of every Python module that emits log records:
  ```python
  import logging
  logger = logging.getLogger(__name__)
  ```
- No module hardcodes a logger name (`logging.getLogger("tap_cares")` is wrong; `logging.getLogger(__name__)` is right).
- Plugins follow the same convention — `plugins.fedramp_20x_ksi.scheduler` gets a logger named `plugins.fedramp_20x_ksi.scheduler` automatically.
- Exception emission inside `except` blocks uses `logger.exception(...)` so the traceback is attached.
- Other levels use `logger.info / warning / error / critical` with `%s` placeholders, not f-strings, so the formatter sees the unformatted message and arguments — this preserves the option to switch to JSON without rewriting call sites.

#### Development

The `__name__` convention is what makes the env-override mechanism work and what makes the plugin-disambiguation goal trivial — every logger name is predictable from the module path, and the logger tree's inheritance does the right thing without explicit per-module entries in `LOGGING["loggers"]`.

`%s`-style formatting (`logger.info("scheduler_tick: produced %d fire(s)", count)`) instead of f-strings (`logger.info(f"scheduler_tick: produced {count} fire(s)")`) is non-obvious but matters: under f-strings the formatter receives a pre-formatted string and loses access to the structured arguments, which blocks any future JSON-format upgrade.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-callsite-convention-1 | `__name__` Loggers | Proposed | All module-level `getLogger` calls use `__name__`. | Enforced by the scanner test alongside the site-ID checks. |
| req-tap-logging-callsite-convention-2 | Exception Helper | Proposed | Exception handlers use `logger.exception(...)` to attach the traceback. | |
| req-tap-logging-callsite-convention-3 | `%s` Formatting | Proposed | Log calls use `logger.info("text %s", arg)` rather than `logger.info(f"text {arg}")`. | |

### Call-Site Site IDs
----
RID: `req-tap-logging-site-ids`
Status: `Proposed`

Every log statement at INFO and above carries a stable site ID — an identifier that survives refactors, line shifts, and file moves so logs can be referenced from specs, alerts, runbooks, and docs by a name that doesn't drift.

#### Implementation

- Format: `[<SLUG>-<XXXX>]` at the start of the message, where:
  - `<SLUG>` is the containing app or plugin slug — the first-party app name (e.g. `tap_cares`) for files under `tap_*/`, or the plugin slug (e.g. `fedramp_20x_ksi`) for files under `plugins/<slug>/`. Regex: `[a-z][a-z0-9_]*`.
  - `<XXXX>` is exactly four lowercase hex characters drawn from a random generator. Regex: `[0-9a-f]{4}`.
  - Full pattern: `\[[a-z][a-z0-9_]*-[0-9a-f]{4}\] `.
- Tiering: required on `logger.info`, `logger.warning`, `logger.error`, `logger.critical`, and `logger.exception`. Exempt on `logger.debug` (transient, often removed; not part of the system's documented operational surface).
- Escape hatch: a `# noqa: TAP-LOG-ID` comment on the same line as the log call exempts that single call from the requirement. Used sparingly and visible in code review.

Example:

```python
logger.info("[tap_cares-a8f3] scheduler_tick: produced %d fire(s)", count)
```

Site IDs are random hex, not sequential, so accidental copy-paste of a complete log call produces a duplicate suffix that the scanner catches by uniqueness. Sequential numbers (`tap_cares-0001`) would silently survive copy-paste; `tap_cares-a8f3` duplicated to a new spot is visibly suspicious *and* fails the uniqueness check.

#### Prefix Derivation

There is no separate registry of site-ID prefixes — the prefix **is** the containing app or plugin slug, derived directly from the file's location:

| File Location | Site-ID Prefix |
| --- | --- |
| `tap_grid/...` | `tap_grid` |
| `tap_api/...` | `tap_api` |
| `tap_cares/...` | `tap_cares` |
| `tap_web/...` | `tap_web` |
| `tap_viz/...` | `tap_viz` |
| `tap_plugins/...` | `tap_plugins` |
| `tap_flip/...` (reserved) | `tap_flip` |
| `tap_ai/...` (reserved) | `tap_ai` |
| `plugins/<slug>/...` | `<slug>` |

This means uniqueness is automatic — first-party app names are unique by Django `INSTALLED_APPS` constraints, and plugin slugs are unique by the plugin manifest's existing uniqueness check (`tap_plugins.manifest` rejects duplicate slugs at registration). There is no shadow registry to keep in sync, no `tap-plugin.toml` field to declare, and no possibility of two plugins picking the same prefix.

The tradeoff against shorter codes (`CARES`, `KSI`) is verbosity — `[fedramp_20x_ksi-a8f3]` is longer than `[KSI-a8f3]` — accepted because the file location is already in the log line, so the redundancy is bounded and the simplification is worth it.

#### Generating a Site ID

A developer adding a new log statement generates a fresh suffix via:

```bash
python -c "import secrets; print(secrets.token_hex(2))"
```

A short alias (`scripts/log-site-id` or similar) can be added later if muscle memory warrants. v0 keeps the workflow as a one-liner because the act is rare per developer-day.

#### Development

Tiering at DEBUG-exempt aligns with how DEBUG actually gets used in practice: a developer wraps a section with `logger.debug` calls while investigating a problem, then either deletes them or leaves them for the next investigation. Demanding stable IDs on DEBUG calls would impose bookkeeping cost on the most transient log category in the codebase. INFO and above is operator-facing signal that has earned the bookkeeping.

The hex suffix is the part most worth defending in design review. Sequential numbers feel cleaner and are tempting; they also make the most common failure mode (copy-paste) silent. Random hex makes the failure mode visible to the scanner (the same suffix can't appear twice) *and* to the human eye (a `tap_cares-a8f3` showing up in `tap_grid/` is visibly wrong because the prefix doesn't match the containing app).

The choice to use the full app/plugin slug as the prefix (rather than a short uppercase code from a registry) is for uniqueness-by-construction. A registry-of-short-codes design introduces a shadow uniqueness rule the platform has to enforce: two plugins both wanting `AWS` is a conflict that manifest validation has to catch, and a renamed plugin can drift between its slug and its registered code. Using the slug directly removes the shadow rule entirely — the platform already enforces slug uniqueness, so site-ID prefix uniqueness comes free.

The `# noqa: TAP-LOG-ID` escape hatch exists for cases like high-volume diagnostic loops where every iteration logs at INFO and a stable ID per iteration adds no signal. It is not a general "I don't want to think about it" exit — code review should treat its appearance as worth a sentence of justification, the same way `# noqa: E501` does.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-site-ids-1 | Format | Proposed | Site IDs match the regex `\[[a-z][a-z0-9_]*-[0-9a-f]{4}\] ` and appear at the start of the log message. | |
| req-tap-logging-site-ids-2 | Required Levels | Proposed | INFO, WARNING, ERROR, CRITICAL, and exception calls require a site ID. | |
| req-tap-logging-site-ids-3 | DEBUG Exempt | Proposed | DEBUG-level calls do not require a site ID. | |
| req-tap-logging-site-ids-4 | Slug As Prefix | Proposed | The prefix is the containing app/plugin slug derived from the file's location. No separate registry. | |
| req-tap-logging-site-ids-5 | NoQA Escape | Proposed | `# noqa: TAP-LOG-ID` on the same line exempts a single call from the requirement. | |

### Site-ID Scanner
----
RID: `req-tap-logging-site-id-scanner`
Status: `Proposed`

A pytest scanner enforces site-ID format, global uniqueness, and prefix-app locality. Enforcement is soft on day one and ratchets to strict over time via a baseline file, so existing code isn't broken on introduction.

#### Implementation

- Scanner module: `tap/logging.py` exports `scan_log_sites(roots: list[Path]) -> ScanResult`. Uses Python's `ast` module to walk every `.py` file under each root, identifies `logger.<level>(...)` calls, and extracts the first string-literal argument.
- For each call:
  - If the level is DEBUG → skipped.
  - If the call has a `# noqa: TAP-LOG-ID` comment on the same line → skipped (counted in the `noqa` bucket so it's visible).
  - Otherwise, attempt to parse a site-ID prefix from the start of the string literal:
    - Missing → recorded in `missing_ids`.
    - Present but malformed → recorded in `malformed_ids`.
    - Present and well-formed → recorded with its prefix and suffix.
- Prefix derivation for the locality check: the scanner walks up from the file's path to find the first directory that is either a registered first-party app (`tap_*` directory in the project root containing an `apps.py`) or a plugin (any directory under `plugins/` containing `tap-plugin.toml`). The slug for that directory is the expected prefix.
- After scanning:
  - **Uniqueness**: every `(prefix, suffix)` pair appears at most once across all scanned files.
  - **Locality**: every well-formed ID's prefix must match the slug of the file's containing app or plugin. A `fedramp_20x_ksi-a8f3` ID in `tap_cares/` fails locality because the expected prefix for that file is `tap_cares`.
  - **Missing-count ratchet**: the count of `missing_ids` is compared against a baseline file (`tap/tests/_log_site_id_baseline.txt`) and must not exceed it. The baseline file lists the currently-uncovered call sites by `<pathname>:<lineno>`; new ID-less call sites cause the count to exceed baseline and fail.
- Test entry point: `tap/tests/test_log_site_ids.py` calls `scan_log_sites([...])` over the project source roots and asserts each property separately so failure messages are specific.
- Existing call sites at the moment this requirement lands are added to the baseline as part of the first commit that introduces the scanner.
- Eventually the baseline reaches zero and the test flips to strict mode (an empty baseline that asserts `len(missing_ids) == 0`).
- `pyproject.toml` adds `"tap"` to `testpaths` so the new test directory is collected.

The scanner module also enforces `req-tap-logging-callsite-convention-1` and `-3`: a module-level `logging.getLogger` call not using `__name__`, or a log call using an f-string as its message argument, are both recorded as `convention_violations` and counted toward the baseline ratchet.

#### Development

The baseline-ratchet pattern is borrowed from the way teams introduce strict mypy or strict ruff rules to existing codebases — record the current debt, refuse to let it grow, drive it down opportunistically, then flip to strict once it bottoms out. This is the only realistic path that satisfies "as mandatory as possible without breaking things on landing."

`ast`-based scanning rather than regex is worth the extra ~100 lines: it correctly handles multi-line log calls, calls split across statements, and concatenated string literals. Regex is fine for the easy cases and silently wrong for the hard ones; given that this scanner is the only thing standing between us and a copy-paste-friendly identifier scheme, accuracy matters.

Filesystem-based prefix derivation (walking up to find the first `apps.py` or `tap-plugin.toml`) keeps the scanner independent of the runtime plugin registry. A plugin can be mid-development with code on disk but no manifest registration yet, and the scanner still produces correct locality checks. This matters during plugin authoring — the scanner runs in pytest, which is exactly when a developer is iterating on a new plugin and hasn't run `import_plugin_grift` yet.

The choice to keep the scanner inside `tap/logging.py` rather than a separate `tap/scanners/` module is so the `build_logging_config()` builder and the scanner share one file — the meta-system for logging lives in one place, easy to find, easy to modify together.

A future Django management command (`manage.py check_log_sites`) is not part of v0 because `tap` is not yet registered as a Django app and registering it solely to host the command is friction without benefit. Developers running `pytest tap/tests/test_log_site_ids.py -v` get the same information in roughly the same time. See [Future](#future) for the deferred command.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-site-id-scanner-1 | Scanner Location | Proposed | `tap/logging.py` exports `scan_log_sites(...)`. | |
| req-tap-logging-site-id-scanner-2 | Test Location | Proposed | `tap/tests/test_log_site_ids.py` invokes the scanner and asserts per-property. | |
| req-tap-logging-site-id-scanner-3 | Format Check | Proposed | Site IDs not matching `\[[A-Z]+-[0-9a-f]{4}\] ` are flagged. | |
| req-tap-logging-site-id-scanner-4 | Uniqueness Check | Proposed | No `(prefix, suffix)` pair appears in source more than once. | |
| req-tap-logging-site-id-scanner-5 | Locality Check | Proposed | Every site ID's prefix matches the slug of its file's containing app or plugin, derived by walking up to the first `apps.py` or `tap-plugin.toml`. | |
| req-tap-logging-site-id-scanner-6 | Baseline Ratchet | Proposed | A baseline file records currently-uncovered call sites; the test fails when missing-count exceeds baseline. | |
| req-tap-logging-site-id-scanner-7 | NoQA Honored | Proposed | Lines with `# noqa: TAP-LOG-ID` are skipped and counted separately. | |
| req-tap-logging-site-id-scanner-8 | Convention Violations | Proposed | The scanner also detects non-`__name__` `getLogger` calls and f-string message arguments, counted against the baseline. | |
| req-tap-logging-site-id-scanner-9 | Pyproject Testpath | Proposed | `pyproject.toml` includes `"tap"` in `testpaths`. | |

### Environment Overrides
----
RID: `req-tap-logging-env-overrides`
Status: `Proposed`

Operators can change any logger's level by setting an environment variable, without editing `settings.py` or restarting the deployment pipeline.

#### Implementation

- `tap/logging.py` reads two environment variables:
  - **`TAP_LOG_LEVELS`** — comma-separated list of `<logger>=<level>` pairs. Logger names appear **verbatim** (no encoding); levels are case-insensitive but normalized to uppercase before application.
  - **`TAP_LOG_LEVEL`** — single value, applied to the root logger. Coarse but useful for "give me everything."
- Examples:
  - `TAP_LOG_LEVELS=tap_cares=DEBUG`
  - `TAP_LOG_LEVELS=tap_cares=DEBUG,django.db.backends=DEBUG,plugins.fedramp_20x_ksi=INFO`
  - `TAP_LOG_LEVEL=DEBUG`
- Parsing rules:
  - Whitespace around tokens is stripped.
  - Empty entries (e.g. trailing comma) are skipped silently.
  - Entries without `=` are skipped with a startup warning to stderr.
  - Level values are validated against `{DEBUG, INFO, WARNING, ERROR, CRITICAL}`; invalid values are skipped with a startup warning.
- Overrides are applied after per-logger defaults, app contributions, and plugin contributions are merged — the env var always wins.

#### Development

The earlier draft of this requirement used a `TAP_LOG_LEVEL__<NAME>` family with dots-encoded-as-underscores. That scheme couldn't unambiguously round-trip logger names that contain literal underscores (e.g. `tap_cares` and the hypothetical `tap.cares` would share an env-var spelling). The comma-separated single-variable form drops the encoding entirely — logger names appear exactly as Python sees them — at the cost of being one shared list rather than a family of independent variables.

The two-variable split (`TAP_LOG_LEVELS` for per-logger, `TAP_LOG_LEVEL` for root) keeps "give me everything" a one-knob action while keeping the per-logger surface tidy. They can be set together — root level is applied independently of the per-logger map.

Validation-on-bad-values rather than crash-on-bad-values is a deliberate choice: a typo in an env var should produce a warning at startup, not refuse to boot the app.

The override applies equally to top-level loggers, app-contributed loggers, component-owned third-party loggers, and plugin loggers — it's keyed on logger name only and is unaware of which layer of the builder declared the default.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-env-overrides-1 | TAP_LOG_LEVELS | Proposed | `TAP_LOG_LEVELS=<name>=<level>,<name>=<level>,...` overrides per-logger levels at process start. | |
| req-tap-logging-env-overrides-2 | Verbatim Names | Proposed | Logger names in `TAP_LOG_LEVELS` appear verbatim — no encoding. | |
| req-tap-logging-env-overrides-3 | Global Override | Proposed | `TAP_LOG_LEVEL` (singular) sets the root logger level. | |
| req-tap-logging-env-overrides-4 | Invalid Skipped | Proposed | Invalid level names and malformed entries are skipped with a startup warning to stderr. | |
| req-tap-logging-env-overrides-5 | Wins Last | Proposed | Env overrides are applied after all other contributions in the builder merge order. | |

### No Grid Mutation From Logging
----
RID: `req-tap-logging-no-grid-mutation`
Status: `Proposed`

Logging is read-only with respect to TAP-managed graph state.

#### Implementation

- No log handler writes to `Entity`, `Edge`, `Schedule`, `ScheduleFire`, `CollectionJob`, or any other TAP-managed model.
- No log handler queues a Steady Queue task as a side effect of a log record.
- Capturing infrastructure log lines as TAP-managed entities is out of scope for v0 (see [Future](#future) for the deferred `SchedulerTickRun` discussion).

#### Development

This rule is preventative — the grid already records application decisions (`ScheduleFire`) and execution outcomes (`CollectionJob`). Mirroring log lines into entities would pollute the spine with operational telemetry that has nothing to do with the user-facing graph, and would couple log levels to grid write throughput.

The one real visibility gap — a crashing `scheduler_tick` produces no grid artifact — is better addressed by a dedicated entity type (e.g. `SchedulerTickRun`) authored as a real domain concept, not by a logging-side mirror.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-no-grid-mutation-1 | No Grid Writes | Proposed | No handler in `LOGGING["handlers"]` writes to TAP-managed models. | |
| req-tap-logging-no-grid-mutation-2 | No Task Enqueue | Proposed | No handler enqueues a Steady Queue task. | |

## Out Of Scope (v0)

- **Structured (JSON) format.** The text formatter ships first. JSON is a future requirement; the call-site convention preserves the option without committing to it.
- **File handlers and on-disk retention.** Container stdout/stderr is the only sink in v0.
- **Log rotation.** No rotation is configured because there's no file output to rotate.
- **External aggregators** (Datadog, BetterStack, Loki, Axiom, ELK). Out of scope; the format and namespace decisions here are the prerequisites, not the integration.
- **Correlation IDs / request IDs.** No `RequestIdMiddleware`, no `extra={"request_id": ...}` injection. Future.
- **Per-request access logs.** Django's request logging is at WARNING in v0, so 4xx/5xx surface but 2xx requests do not.
- **Audit logging.** Compliance-grade audit trails belong on the grid (history tables, FLIP, provenance) — not in the log stream.
- **Test-time log capture conventions.** Pytest's built-in `caplog` is fine; no spec-level rules for tests.
- **`manage.py check_log_sites` management command.** Deferred — pytest covers the validation surface, and registering `tap` as a Django app solely to host the command is friction without benefit.
- **`tap` as a registered Django app.** Deferred until something concrete demands it (management commands, system checks needing an `AppConfig` home, etc.). The scanner and helpers live in `tap/logging.py` as a regular Python module in the meantime.

## Future

- **Structured JSON format.** Add a `tap_json` formatter using `python-json-logger`, swap the `console` handler's formatter, and start passing structured fields via `extra={}` at scheduler / service-layer call sites (`schedule_id`, `fire_id`, `collector_registry`, `caller_id`, `site_id`). Requires the text-format → structured-format migration to be a single settings change because every call site already uses `%s` placeholders, not f-strings, and site IDs are stable identifiers that can become structured fields cleanly.
- **File handler with rotation.** Add a `file` handler using `logging.handlers.RotatingFileHandler` (or `TimedRotatingFileHandler`) writing to `/var/log/tap/` mounted from a Docker volume. Per-logger entries gain `handlers: ["console", "file"]`.
- **External aggregator integration.** Once JSON is in place, a sidecar / platform shipper (Fly machines syslog, Cloud Run logs, Loki Promtail) can pick up stdout and ship it. No app-side change required beyond the format.
- **Request correlation.** Middleware that generates a UUID per request, injects it into a `contextvars.ContextVar`, and a formatter / filter that attaches it as a structured field on every record emitted during that request.
- **`SchedulerTickRun` entity.** A grid-side entity that records every scheduler tick (started_at, ended_at, fires_count, error). Closes the "crashing tick produces no grid artifact" gap without overloading `ScheduleFire`, and replaces the need to grep stderr for scheduler exceptions.
- **`manage.py check_log_sites`.** When `tap` is registered as a Django app for another reason, expose the scanner as a management command alongside the pytest test. Both consume the same `tap.logging.scan_log_sites` implementation.
- **Strict mode.** Once the baseline file reaches zero, flip the scanner to strict mode (`assert len(missing_ids) == 0` with no baseline allowance).
- **Spec-driven logger enumeration test.** A repository scanner that asserts every `tap_*` app and every registered plugin slug has a corresponding entry in `LOGGING["loggers"]` (or is covered by the wildcard). Catches a new app or plugin being added without a logger entry.
- **Per-test log capture for spec ACIDs.** Optional convention for tests linked to logging ACIDs (`@pytest.mark.spec("req-tap-logging-...-N")`) using `caplog` to assert specific log records are emitted.
