# TAP Logging Specification

## Philosophy

TAP runs as a Django web process plus a Steady Queue supervisor (`docker/entrypoint.sh`), with first-party apps (`tap_grid`, `tap_api`, `tap_cares`, `tap_web`, `tap_viz`, `tap_plugins`) and third-party plugins (`plugins/<slug>/...`) all running in the same Python process. Today every one of those components emits log records through `logging.getLogger(__name__)` to Python's root logger, which has no configured handlers or formatters in `tap/settings.py` — so output lands on container stdout/stderr through Django's default handler with no per-component levels and no consistent format. That works for "tail and read" but breaks down as soon as you want to crank `tap_cares.scheduler` to DEBUG, silence `django.db.backends`, or tell at a glance whether a noisy line came from `plugins.fedramp_20x_ksi` or `plugins.genericom`.

This spec defines the v0 logging configuration: a single `LOGGING` dict in `tap/settings.py` that names each first-party app and each registered plugin as its own logger, applies a consistent text format that includes source file and line on every record, and exposes per-logger level overrides through environment variables. It also defines a call-site site-ID convention — a stable hex token of the form `[a8f3]` that travels with the log statement across refactors, where the unique callsite *path* is the logger name (already on every record), not a human-authored slug — enforced by a scanner test with a baseline-ratchet so existing code isn't broken on day one. Library log levels are owned where they make sense: foundational libraries used transitively by anything (`urllib3`, `django.*`) stay top-level; libraries pulled in for a specific component's job (`steady_queue` for `tap_cares`, `boto3` for an AWS plugin) are owned by that component through an `app_logger_config()` helper.

The canonical artifact is a **structured message object** (`req-tap-logging-message-object`), not a text line. Every record is that object; rendering is a per-handler concern — the `console` handler renders the human-readable text line you read in `scripts/dc logs web`, and a structured sink serializes the same object as JSON. Text-versus-JSON is therefore a handler choice, not a format migration: there is no in-band micro-syntax to parse back out, because the structure was never flattened into the string in the first place. Disk retention, request/trace correlation IDs, and external aggregators remain deferred (see [Future](#future)); those are additive handler/field changes on top of the object, not a rewrite.

Logging is read-only by construction. Nothing in this spec describes capturing application telemetry into the TAP grid (`Entity`, `Edge`, `ScheduleFire`, `CollectionJob`); the grid already records application decisions and outcomes, and infrastructure log lines belong in the log stream, not the graph.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Per-Component Visibility | Every first-party app and every registered plugin has a named logger whose level can be tuned independently. |
| 2. | Plugin Disambiguation | Plugin log records are visibly attributable to a specific plugin slug without grepping for module paths. |
| 3. | Source Traceability | Every log record points back to the exact file, line, and stable site ID that emitted it without inferring location from message content. |
| 4. | Ownership-Aligned Library Config | Third-party library log levels live with the component that owns the library (foundational libs top-level, component-pulled libs scoped to that component). |
| 5. | Runtime Tunability | Operators can raise or lower individual logger levels via environment variables without code changes. |
| 6. | Object-First | The record is a structured object; text and JSON are per-handler renderings of it. Adding a file handler, a JSON sink, or an external shipper is a handler addition, not a call-site rewrite. |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-logging-config-location | [Configuration Location](#configuration-location) | Proposed | Single `LOGGING` dict in `tap/settings.py`, built by `tap/logging.py`'s helper |
| req-tap-logging-message-object | [Structured Message Object](#structured-message-object) | Proposed | Canonical record object: `v`/`ts`/`level`/`site` envelope, `message`/`message_code`/`message_data` cluster, optional `entity_id`/`task_result_id`; `message_code` discriminates `message_data` |
| req-tap-logging-entity-ref | [Grid Entity Reference](#grid-entity-reference) | Proposed | Optional `entity_id` envelope field — the record's grid subject (run/job node), not every entity touched |
| req-tap-logging-task-ref | [Task Result Reference](#task-result-reference) | Proposed | Optional `task_result_id` envelope field — the executing task's `TaskResult.id` for records emitted within a task |
| req-tap-logging-format | [Object Rendering](#object-rendering) | Proposed | Per-handler rendering of the message object — text on `console`, JSON on a structured sink |
| req-tap-logging-app-loggers | [First-Party App Loggers](#first-party-app-loggers) | Proposed | One logger per `tap_*` app with a sensible default level |
| req-tap-logging-plugin-loggers | [Plugin Loggers](#plugin-loggers) | Proposed | `plugins.<slug>` namespace; per-plugin level + wildcard default |
| req-tap-logging-foundational-loggers | [Foundational Third-Party Loggers](#foundational-third-party-loggers) | Proposed | `urllib3`, `django.*` — pan-system libs with no single owner |
| req-tap-logging-component-libs | [Component-Owned Library Loggers](#component-owned-library-loggers) | Proposed | Apps and plugins own levels for libs they pulled in (e.g. `steady_queue` → `tap_cares`) |
| req-tap-logging-callsite-convention | [Call-Site Convention](#call-site-convention) | Proposed | `logger = logging.getLogger(__name__)`, `%s` placeholders, `.exception` in `except` |
| req-tap-logging-site-ids | [Call-Site Site IDs](#call-site-site-ids) | Proposed | Stable `[<hex>]` token on **every** committed log call at all levels; the unique callsite path is the derived logger name, never an authored slug |
| req-tap-logging-site-id-scanner | [Site-ID Scanner](#site-id-scanner) | Proposed | Pytest scanner: format + within-file hex-uniqueness; baseline-ratchet enforcement |
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

### Structured Message Object
----
RID: `req-tap-logging-message-object`
Status: `Proposed`

Every log record is a structured object. Producers do not assemble in-band micro-syntax inside a string; they populate named fields. Text and JSON are renderings of this object (`req-tap-logging-format`), not competing source formats. This is the spec's response to structure-creep: site IDs, grid references, and task references are *fields*, not substrings a consumer has to parse back out.

#### Implementation

The object has exactly these fields. No others in v0.

| Field | Required | Group | Description |
| --- | :---: | --- | --- |
| `v` | Yes | envelope | Schema version integer. `1` in v0. Lets a consumer branch when the shape evolves. |
| `ts` | Yes | envelope | ISO-8601 timestamp with timezone offset. |
| `level` | Yes | envelope | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`. |
| `site` | Yes | envelope | Stable 4-hex callsite token, e.g. `a8f3` (`req-tap-logging-site-ids`). Required at **all** levels. The full callsite *path* is the logger name (derived); it is not duplicated into `site`. |
| `entity_id` | No | envelope | Grid subject of the record (`req-tap-logging-entity-ref`). Absent when the record has no grid subject. |
| `task_result_id` | No | envelope | Executing task's `TaskResult.id` (`req-tap-logging-task-ref`). Absent outside a task. |
| `message` | Yes | message | Human-readable run-specific prose. |
| `message_code` | Yes | message | `UPPER_SNAKE` category. Also the `message_data` discriminator (below). |
| `message_data` | Yes | message | Free-form structured object. `{}` when there is no extra payload. |

- **`message_code` is the `message_data` discriminator.** A consumer that parses `message_data` keys off `message_code` to know the payload's shape. A consumer that does not recognize the `message_code` treats `message_data` as opaque. There is no separate type tag inside `message_data` — a discriminator is a contract field, not opaque payload, so it lives in the envelope-adjacent `message_code`, never as a reserved key inside the bag.
- **Codes must be shape-specific.** If `message_code` discriminates `message_data`, then `code → message_data shape` must be a function. This is a soft per-producer `UPPER_SNAKE` naming discipline (`STEAMPIPE_DEBUG_DUMP`, `KSI_INDICATOR_LOOKUP`), not a centrally-registered code — producers namespace their own codes by convention.
- **Rendering is per-handler** (`req-tap-logging-format`). The object is the source of truth; the `console` handler renders the human text line, a structured sink serializes the object as JSON.
- **Redaction is mandatory before any handler sees the object.** Producer-side streaming redaction (the `redact_credential_values()` pattern) is primary for high-volume capture; a serialization-time `tap_cares.secrets.redact()` pass over `message_data` is the required backstop. `message_data` is the only field that can carry secret-shaped values; the envelope and `message`/`message_code` do not.

#### Development

The structural principle, stated so future field placement is self-answering: **`message` / `message_code` / `message_data` are the message; `v` / `ts` / `level` / `site` / `entity_id` / `task_result_id` are metadata *about* the message** (origin, correlation, addressing). Correlation identifiers are envelope fields. They are deliberately **not** `message_*` and **never** live inside `message_data` — the `message_*` parallelism must not tempt a future `message_site` or `message_entity_id`; those would destroy the distinction. A correlation id buried in the opaque `message_data` bag (whose contract is "treat unrecognized keys as opaque") cannot be reliably joined on; that is why `entity_id`, `task_result_id`, and `message_code` are all outside it.

These are *messages about things that are running*, not events. Multiple messages can describe one underlying happening, which is why the per-message category is `message_code` and not `event_code` — `event_*` would imply a granularity the system does not have. Wrapping messages in an event envelope to correlate bundled messages is a named [Future](#future) seam, not v0.

The object is the same vocabulary as `CollectionJob.results` entries in [`spec-tap-cares-collector.md`](spec-tap-cares-collector.md): same `site` / `message_code` / `message` / `message_data` shape, plus the optional `entity_id` / `task_result_id`. Same shape, different sink — the log stream is ephemeral; `CollectionJob.results` is durable grid state. They converge on one vocabulary deliberately; neither is the [activity stream](#future), which is a grid projection, not a log artifact.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-message-object-1 | Fixed Field Set | Proposed | The object has exactly the nine fields listed; producers populate fields, not in-band string syntax. | |
| req-tap-logging-message-object-2 | Schema Version | Proposed | `v` is present and integer; `1` in v0. | |
| req-tap-logging-message-object-3 | message_code Discriminates | Proposed | `message_code` identifies the category and the `message_data` shape. Unrecognized code ⇒ `message_data` is opaque. No type tag inside `message_data`. | |
| req-tap-logging-message-object-4 | Envelope/Message Boundary | Proposed | Correlation fields (`site`, `entity_id`, `task_result_id`) are envelope, never `message_*`, never inside `message_data`. | |
| req-tap-logging-message-object-5 | Redaction Before Handlers | Proposed | `message_data` is redacted (producer-streaming + serialization-time `tap_cares.secrets.redact()` backstop) before any handler receives the object. | |
| req-tap-logging-message-object-6 | Collector Vocabulary Convergence | Proposed | The object shares `site`/`message_code`/`message`/`message_data` with `CollectionJob.results` per `spec-tap-cares-collector.md`. | Same shape, different sink. |

### Grid Entity Reference
----
RID: `req-tap-logging-entity-ref`
Status: `Proposed`

`entity_id` is the optional envelope field naming the record's grid subject, so an operator can pivot log→grid and grid→log.

#### Implementation

- `entity_id` is the canonical UUID of the record's **subject** — the run / job / capability node the record is about (e.g. the `CollectionJob`), not every entity the operation touched. Fan-out to touched nodes is the grid's job via edges (`HAS_JOB`, GRIFT batch links).
- At most one `entity_id` per record. A record with no grid subject omits the field; producers do not synthesize one.
- It is an envelope field, the navigational counterpart to `req-tap-logging-no-grid-mutation`: logs *point at* grid entities, they never *write* them.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-entity-ref-1 | Subject Only | Proposed | `entity_id` is the record's grid subject, not every entity touched. At most one per record. | |
| req-tap-logging-entity-ref-2 | Optional, Not Synthesized | Proposed | Absent when there is no grid subject; producers never invent one. | |

### Task Result Reference
----
RID: `req-tap-logging-task-ref`
Status: `Proposed`

`task_result_id` is the optional envelope field naming the executing task, completing the trace chain: code line (`site`) → task executed (`task_result_id`) → grid node (`entity_id`) → human (`message`).

#### Implementation

- Any record emitted **within a task execution** carries that execution's `TaskResult.id` (Django Tasks' backend-defined string; see `spec-tap-cares-collector.md`). Records outside a task omit the field.
- It is a correlation identifier, hence an envelope field beside `entity_id` — not inside `message_data`, not `message_*`. It is a backend opaque string, not secret-bearing.
- How the id reaches a deep call site (a context var bound at task entry, read by the object builder) is a propagation concern shared with the deferred request-correlation work; v0 may start with explicit passing or a thin helper without precluding the contextvar approach.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-task-ref-1 | Within-Task Records | Proposed | Records emitted within a task carry that task's `TaskResult.id`; records outside a task omit it. | |
| req-tap-logging-task-ref-2 | Envelope Placement | Proposed | `task_result_id` is an envelope field, never inside `message_data` or named `message_*`. | |

### Object Rendering
----
RID: `req-tap-logging-format`
Status: `Proposed`

Handlers render the message object. The `console` handler renders a human-readable text line; a structured sink serializes the object as JSON. Choosing text or JSON is a per-handler decision, not a format migration, because the object — not a string — is the record.

#### Implementation

- One formatter named `tap` is defined under `LOGGING["formatters"]`; it renders the message object to the v0 text line.
- Text line shape: `%(asctime)s %(levelname)-8s %(name)s %(pathname)s:%(lineno)d — [<site>] <message>`, where `<site>` is the bare 4-hex token (`[a8f3]`) — the full callsite path is already carried by `%(name)s`/`%(pathname)s`, so it is not repeated inside the token. `entity_id` / `task_result_id` / `message_code` are appended as trailing `key=value` tokens when present, and `message_data` rendered compactly (or elided when `{}`).
- `datefmt`: `"%Y-%m-%dT%H:%M:%S%z"` (ISO-8601 with timezone) — the `ts` envelope field.
- One handler named `console` writes to `sys.stderr` using `class: logging.StreamHandler` with `formatter: tap`. All configured loggers route to `console`.
- Levelname is left-padded to 8 characters so lines align visually.
- A JSON sink is a second formatter that serializes the object's fields verbatim. It is additive — a handler/formatter addition, no call-site change — and is the mechanism behind the [Future](#future) file/aggregator work.

Example `console` line:

```
2026-05-14T14:32:11+0000 INFO     tap_cares.scheduler /app/tap_cares/scheduler.py:307 — [tap_cares-a8f3] scheduler_tick: produced 2 fire(s)
```

#### Development

The console text rendering is preserved exactly so `scripts/dc logs web` stays readable without tooling — the object-first model costs the human reader nothing. `%(pathname)s` (full path) over `%(filename)s` because terminals/IDEs offer click-through on the full-path-with-line pattern; inside the container `pathname` is `/app/...` and resolves to the host path via the IDE's project mapping. `%(name)s` is preserved alongside `%(pathname)s` so grepping by logger name stays as easy as grepping by file. Writing to stderr (not stdout) follows the Unix convention that logs are a sideband; Docker captures both so it is operationally invisible but matters for any future tee/redirect.

`%s`-style placeholders at call sites still matter (`req-tap-logging-callsite-convention`): the unformatted message plus args is what the object builder captures into `message`; f-strings would pre-flatten it and lose the structured arguments the object needs.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-format-1 | Object Is The Record | Proposed | Handlers render the message object; the object, not a string, is the source of truth. | |
| req-tap-logging-format-2 | ISO Timestamp | Proposed | The text rendering emits the `ts` field as ISO-8601 with timezone offset. | |
| req-tap-logging-format-3 | Padded Level | Proposed | Levelname is left-padded to 8 characters in the text rendering. | |
| req-tap-logging-format-4 | Source Location | Proposed | The text rendering includes `pathname:lineno` on every record. | |
| req-tap-logging-format-5 | Stderr | Proposed | The `console` handler writes to `sys.stderr`. | |
| req-tap-logging-format-6 | JSON Is Additive | Proposed | A JSON sink is a second formatter over the same object; adding it requires no call-site change. | |

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
| `tap_ai` | `INFO` | Reserved; emits records once the app exists. |

Sub-loggers (e.g. `tap_cares.scheduler`, `tap_grid.services`) inherit from their parent and do not need explicit entries unless they require a different level than the parent app.

#### Development

Per-app loggers are declared explicitly rather than relying on the root logger's default because the env-override mechanism (`req-tap-logging-env-overrides`) needs a known set of logger names to attach to. A wildcard root + propagation would work but makes "raise `tap_cares` to DEBUG" harder to wire as a single env var.

`tap_ai` is listed for forward compatibility — its entry is inert until the app exists, and adding it now means the env-override convention works the moment it lands. (FLIP is intentionally absent: it is a `tap_grid` capability, not a separate app, so its records are already covered by the `tap_grid` logger. An earlier draft listed a `tap_flip` app; that was initial-architecture cruft.)

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
- Other levels use `logger.info / warning / error / critical` with `%s` placeholders, not f-strings, so the object builder captures the unformatted message and its arguments into the `message` field (`req-tap-logging-message-object`) rather than a pre-flattened string.

#### Development

The `__name__` convention is what makes the env-override mechanism work and what makes the plugin-disambiguation goal trivial — every logger name is predictable from the module path, and the logger tree's inheritance does the right thing without explicit per-module entries in `LOGGING["loggers"]`.

`%s`-style formatting (`logger.info("scheduler_tick: produced %d fire(s)", count)`) instead of f-strings (`logger.info(f"scheduler_tick: produced {count} fire(s)")`) is non-obvious but matters: under f-strings the message is pre-flattened before the object builder sees it, so the structured arguments are lost and the JSON rendering of `message` degrades to an opaque pre-rendered string.

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

Every committed log statement, at every level, carries a stable hex site token — a short identifier that survives refactors, line shifts, and file moves so logs can be referenced from specs, alerts, runbooks, and docs by a token that doesn't drift. It is the `site` field of the message object (`req-tap-logging-message-object`). The unique callsite *path* is the logger name, already on every record; `site` is only the hex.

#### Implementation

- Format: `[<XXXX>]` at the start of the message — exactly four lowercase hex characters, nothing else. Full pattern: `\[[0-9a-f]{4}\] `. There is no slug, no prefix.
- The callsite *path* is the logger name. `getLogger(__name__)` (`req-tap-logging-callsite-convention`) makes it the module import path, which the logging machinery has on every record (`%(name)s`). It is **derived, never authored** — a developer never types a slug, so a slug can never be wrong or collide.
- No level exemption: required on `logger.debug`, `logger.info`, `logger.warning`, `logger.error`, `logger.critical`, and `logger.exception`. Committed code at every level is part of the system's documented operational surface.
- Escape hatch: a `# noqa: TAP-LOG-ID` comment on the same line as the log call exempts that single call from the requirement. Used sparingly and visible in code review — the narrow valve for the genuine rare case (e.g. a tight high-volume loop).

Example:

```python
logger.info("[a8f3] scheduler_tick: produced %d fire(s)", count)
```

The hex only needs to be unique **within its file** — the logger name (the module path) namespaces it, so a duplicated hex in the same module fails the scanner, while copy-pasting a log line into a *different* module is automatically fine: the path re-derives from that module and the hex only has to be unique in its new file. This is a strictly smaller uniqueness invariant than a globally-unique token.

#### Path Is Derived, Not Authored

The structurally-unique identity of a call site is its Python import path (`tap_cares.scheduler`, `plugins.fedramp_20x_ksi.collectors.steampipe_runner`). It is unique by construction — two packages cannot occupy the same import path, and Django will not load two apps with the same module — with no registry to keep in sync and nothing for a human to mint.

Earlier drafts put a human-chosen app/plugin *slug* in the token. That was abandoned because it has a social failure mode with no good resolution: two independent plugin authors can pick the same clever slug, and the only fixes are forcing one of them to rename (awful) or maintaining a shadow uniqueness registry (the thing the design was trying to avoid). Deriving the path from the import system removes the problem entirely — the only authored part is the hex, and its uniqueness scope is one file.

The path is not duplicated into `site` because it is already in the line: `%(name)s` and `%(pathname)s:%(lineno)d` carry it (`req-tap-logging-format`). `site` is deliberately just the hex; grepping the hex finds the call site, and the logger name on the same record tells you which module it is.

#### Generating a Site ID

`scripts/log-site-id` mints a fresh token: it generates `secrets.token_hex(2)`, greps the source tree for that hex, regenerates on any collision, and prints the result. A broad tree-wide grep is intentional — a globally-unique hex is never wrong even though only file-local uniqueness is required, so there is no scope subtlety to get wrong. It is surfaced as an agent-runnable tool the same way `scripts/uuid7` is (CLAUDE.md / AGENTS.md), because plugin authors increasingly drive development through agents and a deterministic collision-checked generator removes the one remaining footgun.

#### Development

The DEBUG exemption was removed deliberately, and the reasoning is worth recording because the original exemption seemed obviously right. It was protecting *ephemeral scaffolding* — the `logger.debug("HERE")` a developer sprinkles in for twenty minutes and deletes before committing. But scaffolding is deleted before commit, so the scanner (which only runs on committed code) never sees it anyway: the exemption protected something that didn't need protecting, while creating a real inconsistency in *committed* DEBUG logging. Committed DEBUG is by definition an operational surface — it is shipped precisely so an operator can raise `TAP_LOG_LEVELS` in production and trace an issue, and an operational surface with no callsite traceability is exactly what site IDs exist to prevent. The structured `message_data` field (`req-tap-logging-message-object`) also removes the old "DEBUG is messy spew" premise: noisy capture is self-contained in the object, not smeared across the log. So the rule is uniform at every level, with `# noqa: TAP-LOG-ID` as the narrow documented valve — strictly fewer rules than a level-gated exemption plus a structured/transient carve-out, and more consistent.

The hex being random rather than sequential is the part most worth defending in design review. Sequential numbers feel cleaner and are tempting; they also make the most common failure mode (copy-paste of a whole log call within a file) silent. Random hex makes that failure visible — the same suffix appearing twice in one module fails the scanner's within-file uniqueness check and is visibly suspicious to a human reviewer.

Deriving the path instead of authoring a slug prefix is the design's load-bearing simplification. It dissolves rather than solves the slug-uniqueness problem: there is no uniqueness to enforce because nothing is minted, no `tap_plugins.manifest` slug-rejection check to depend on (none exists; an earlier draft of this spec wrongly asserted one), and no locality check for the scanner to run (a derived path cannot be the "wrong" path). The whole prefix apparatus — prefix table, slug registry assumptions, locality enforcement — is deleted, not reworked.

The `# noqa: TAP-LOG-ID` escape hatch exists for cases like high-volume diagnostic loops where every iteration logs and a stable token per iteration adds no signal. It is not a general "I don't want to think about it" exit — code review should treat its appearance as worth a sentence of justification, the same way `# noqa: E501` does.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-site-ids-1 | Format | Proposed | Site tokens match the regex `\[[0-9a-f]{4}\] ` and populate the `site` field of the message object. No slug, no prefix. | |
| req-tap-logging-site-ids-2 | All Levels | Proposed | Every committed log call at every level (DEBUG through CRITICAL, plus exception) requires a site token. No level exemption. | Supersedes the prior INFO-and-above tiering. |
| req-tap-logging-site-ids-3 | Path Derived | Proposed | The callsite path is the logger name (`__name__`), derived by the machinery and never authored. No slug, no registry, no prefix table. | Dissolves the slug-uniqueness problem rather than enforcing it. |
| req-tap-logging-site-ids-4 | Within-File Uniqueness | Proposed | The hex need only be unique within its file; the module path namespaces it. Cross-module copy-paste is inherently safe. | |
| req-tap-logging-site-ids-5 | NoQA Escape | Proposed | `# noqa: TAP-LOG-ID` on the same line exempts a single call from the requirement. | |

### Site-ID Scanner
----
RID: `req-tap-logging-site-id-scanner`
Status: `Proposed`

A pytest scanner enforces site-token format and within-file hex-uniqueness. Enforcement is soft on day one and ratchets to strict over time via a baseline file, so existing code isn't broken on introduction. There is no locality check and no prefix derivation — the path is the derived logger name (`req-tap-logging-site-ids`), which cannot be authored wrong, so there is nothing for the scanner to validate about it.

#### Implementation

- Scanner module: `tap/logging.py` exports `scan_log_sites(roots: list[Path]) -> ScanResult`. Uses Python's `ast` module to walk every `.py` file under each root, identifies `logger.<level>(...)` calls, and extracts the first string-literal argument.
- For each call (every level, DEBUG included — there is no level exemption per `req-tap-logging-site-ids-2`):
  - If the call has a `# noqa: TAP-LOG-ID` comment on the same line → skipped (counted in the `noqa` bucket so it's visible).
  - Otherwise, attempt to parse a leading `[<hex>]` token from the start of the string literal:
    - Missing → recorded in `missing_ids`.
    - Present but malformed (not exactly `[0-9a-f]{4}`) → recorded in `malformed_ids`.
    - Present and well-formed → recorded with its hex and the file it appears in.
- After scanning:
  - **Within-file uniqueness**: no hex appears more than once among the well-formed tokens in the same file. (Cross-file reuse is not a violation — the logger name namespaces the hex, so the same hex in two different modules is two distinct call sites.)
  - **Missing-count ratchet**: the count of `missing_ids` is compared against a baseline file (`tap/tests/_log_site_id_baseline.txt`) and must not exceed it. The baseline file lists the currently-uncovered call sites by `<pathname>:<lineno>`; new ID-less call sites cause the count to exceed baseline and fail.
- Test entry point: `tap/tests/test_log_site_ids.py` calls `scan_log_sites([...])` over the project source roots and asserts each property separately so failure messages are specific.
- Existing call sites at the moment this requirement lands are added to the baseline as part of the first commit that introduces the scanner. Because DEBUG calls are no longer exempt, existing ID-less DEBUG calls are part of that initial baseline rather than failures — the ratchet drives them to zero opportunistically like any other uncovered site.
- Eventually the baseline reaches zero and the test flips to strict mode (an empty baseline that asserts `len(missing_ids) == 0`).
- `pyproject.toml` adds `"tap"` to `testpaths` so the new test directory is collected.

The scanner module also enforces `req-tap-logging-callsite-convention-1` and `-3`: a module-level `logging.getLogger` call not using `__name__`, or a log call using an f-string as its message argument, are both recorded as `convention_violations` and counted toward the baseline ratchet.

#### Development

The baseline-ratchet pattern is borrowed from the way teams introduce strict mypy or strict ruff rules to existing codebases — record the current debt, refuse to let it grow, drive it down opportunistically, then flip to strict once it bottoms out. This is the only realistic path that satisfies "as mandatory as possible without breaking things on landing."

`ast`-based scanning rather than regex is worth the extra ~100 lines: it correctly handles multi-line log calls, calls split across statements, and concatenated string literals. Regex is fine for the easy cases and silently wrong for the hard ones; given that this scanner is the only thing standing between us and a copy-paste-friendly identifier scheme, accuracy matters.

Option A removed an entire class of scanner complexity. The previous design needed filesystem prefix derivation (walking up to the first `apps.py`/`tap-plugin.toml`), a locality check, and assumptions about plugin-slug uniqueness. None of that exists now: the path is the logger name, derived at runtime by Python itself, so there is nothing to walk, nothing to match, and no registry to be independent of. The scanner is now a pure lexical check over string literals — format and per-file hex-uniqueness — which is both simpler and impossible to get wrong by being out of sync with plugin registration state.

The choice to keep the scanner inside `tap/logging.py` rather than a separate `tap/scanners/` module is so the `build_logging_config()` builder and the scanner share one file — the meta-system for logging lives in one place, easy to find, easy to modify together.

A future Django management command (`manage.py check_log_sites`) is not part of v0 because `tap` is not yet registered as a Django app and registering it solely to host the command is friction without benefit. Developers running `pytest tap/tests/test_log_site_ids.py -v` get the same information in roughly the same time. See [Future](#future) for the deferred command.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-site-id-scanner-1 | Scanner Location | Proposed | `tap/logging.py` exports `scan_log_sites(...)`. | |
| req-tap-logging-site-id-scanner-2 | Test Location | Proposed | `tap/tests/test_log_site_ids.py` invokes the scanner and asserts per-property. | |
| req-tap-logging-site-id-scanner-3 | Format Check | Proposed | Site tokens not matching `\[[0-9a-f]{4}\] ` are flagged. | Aligned with `req-tap-logging-site-ids-1`; no slug/prefix component. |
| req-tap-logging-site-id-scanner-4 | Within-File Uniqueness | Proposed | No hex appears more than once among well-formed tokens in the same file. Cross-file reuse is not a violation. | Replaces the prior global `(prefix, suffix)` uniqueness; no locality check exists. |
| req-tap-logging-site-id-scanner-5 | Baseline Ratchet | Proposed | A baseline file records currently-uncovered call sites; the test fails when missing-count exceeds baseline. | |
| req-tap-logging-site-id-scanner-6 | NoQA Honored | Proposed | Lines with `# noqa: TAP-LOG-ID` are skipped and counted separately. | |
| req-tap-logging-site-id-scanner-7 | Convention Violations | Proposed | The scanner also detects non-`__name__` `getLogger` calls and f-string message arguments, counted against the baseline. | |
| req-tap-logging-site-id-scanner-8 | Pyproject Testpath | Proposed | `pyproject.toml` includes `"tap"` in `testpaths`. | |

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

This requirement is also the standing boundary against an *activity stream* being grown out of the log stream. A subscribable real-time feed of grid activity (for a TAP instance assessing another) is a real future shape — but it is a **projection of the grid**, sourced from the ordered auditable substrate the grid already has, never scraped from stdout or synthesized by a log handler. The message object's `entity_id` makes such a grid-sourced stream cheap to correlate; it does not make the log stream the stream. See the [Future](#future) activity-stream seam.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-logging-no-grid-mutation-1 | No Grid Writes | Proposed | No handler in `LOGGING["handlers"]` writes to TAP-managed models. | |
| req-tap-logging-no-grid-mutation-2 | No Task Enqueue | Proposed | No handler enqueues a Steady Queue task. | |

## Out Of Scope (v0)

- **File handlers and on-disk retention.** Container stdout/stderr is the only sink in v0. (Note: JSON itself is *not* out of scope — the message object is structured by construction and a JSON sink is an additive formatter per `req-tap-logging-format`; what is deferred is *where* JSON gets written and shipped.)
- **Log rotation.** No rotation is configured because there's no file output to rotate.
- **External aggregators** (Datadog, BetterStack, Loki, Axiom, ELK). Out of scope; the format and namespace decisions here are the prerequisites, not the integration.
- **Correlation IDs / request IDs.** No `RequestIdMiddleware`, no `extra={"request_id": ...}` injection. Future.
- **Per-request access logs.** Django's request logging is at WARNING in v0, so 4xx/5xx surface but 2xx requests do not.
- **Audit logging.** Compliance-grade audit trails belong on the grid (history tables, FLIP, provenance) — not in the log stream.
- **Test-time log capture conventions.** Pytest's built-in `caplog` is fine; no spec-level rules for tests.
- **`manage.py check_log_sites` management command.** Deferred — pytest covers the validation surface, and registering `tap` as a Django app solely to host the command is friction without benefit.
- **`tap` as a registered Django app.** Deferred until something concrete demands it (management commands, system checks needing an `AppConfig` home, etc.). The scanner and helpers live in `tap/logging.py` as a regular Python module in the meantime.

## Future

- **JSON sink wiring.** The message object is already structured (`req-tap-logging-message-object`) and a JSON formatter is `req-tap-logging-format-6`; what remains is wiring a concrete JSON-sink handler (formatter over the object, no `extra={}` retrofit, no call-site change). This is configuration, not a format migration.
- **File handler with rotation.** Add a `file` handler using `logging.handlers.RotatingFileHandler` (or `TimedRotatingFileHandler`) writing to `/var/log/tap/` mounted from a Docker volume. Per-logger entries gain `handlers: ["console", "file"]`.
- **External aggregator integration.** With the JSON sink wired, a sidecar / platform shipper (Fly machines syslog, Cloud Run logs, Loki Promtail) can pick up the serialized object and ship it. No app-side change beyond the sink.
- **Activity stream endpoint.** A durable, ordered, subscribable projection *of the grid's* change feed (Entity/Edge/history/GRIFT batches are already ordered auditable events) that another TAP instance can tail to assess this one in real time. This is the *push* shape of the federation read side (versus *pull* / on-demand query) and belongs to the satellite/federation design space, **not** to logging. Recorded here only to fix the boundary: the system log MUST NOT grow retention or shipping to become this (see `req-tap-logging-no-grid-mutation`). The `entity_id` field makes a grid-sourced stream cheap to correlate, but the stream is sourced from the grid, never the log. Wait for a federation demand signal.
- **`message_data` format declarator.** If `message_code` granularity ever proves too coarse to discriminate `message_data` — e.g. some payloads are non-JSON blobs, NDJSON, or base64 — add a dedicated declarator field (CloudEvents `datacontenttype`-shaped), as an **envelope field**, never encoded into a field name and never a reserved key inside `message_data`. Not v0; `message_code` is the discriminator until a real case forces the split. Wait for demand signal.
- **Event wrapper for cross-message correlation.** Multiple messages can describe one underlying happening; wrapping a bundle under a shared correlation id would let consumers group them. That id would be an `event_id`-shaped **envelope** field (the envelope/message boundary in `req-tap-logging-message-object` pre-decides its placement — never `message_*`, never inside `message_data`). Clever but premature; named so it isn't relearned. Wait for demand signal.
- **Request correlation.** Middleware that generates a UUID per request, injects it into a `contextvars.ContextVar`, and a formatter / filter that attaches it as a structured field on every record emitted during that request.
- **`SchedulerTickRun` entity.** A grid-side entity that records every scheduler tick (started_at, ended_at, fires_count, error). Closes the "crashing tick produces no grid artifact" gap without overloading `ScheduleFire`, and replaces the need to grep stderr for scheduler exceptions.
- **`manage.py check_log_sites`.** When `tap` is registered as a Django app for another reason, expose the scanner as a management command alongside the pytest test. Both consume the same `tap.logging.scan_log_sites` implementation.
- **Strict mode.** Once the baseline file reaches zero, flip the scanner to strict mode (`assert len(missing_ids) == 0` with no baseline allowance).
- **Spec-driven logger enumeration test.** A repository scanner that asserts every `tap_*` app and every registered plugin slug has a corresponding entry in `LOGGING["loggers"]` (or is covered by the wildcard). Catches a new app or plugin being added without a logger entry.
- **Per-test log capture for spec ACIDs.** Optional convention for tests linked to logging ACIDs (`@pytest.mark.spec("req-tap-logging-...-N")`) using `caplog` to assert specific log records are emitted.
