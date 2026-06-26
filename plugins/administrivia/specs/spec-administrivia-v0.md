# Administrivia Specification

## Philosophy

Administrivia is TAP's first-party administrative web plugin. It exists to host practical, human-facing administration surfaces for TAP subsystems using TAP's own page and panel system rather than relying on Django admin as the primary operator experience.

Administrivia is an implementation home and navigation shell, not the canonical owner of every subsystem's operational semantics. When an administrative surface belongs conceptually to another TAP app or plugin, the owning subsystem keeps the canonical requirements in its own `specs/` directory. Administrivia references those specs and hosts the page, panel, template, static asset, and route code needed to make the surface usable.

This keeps subsystem requirements close to the models and services they govern while still letting TAP grow a coherent administrative UI.

## Goals

|    |                  |                                                                 |
| :---: | ---           | ---                                                             |
| 1. | Administrivia Shell | Provide a first-party home for TAP operator pages and panels |
| 2. | Spec-Referenced | Point each hosted surface to the canonical spec that owns its behavior |
| 3. | Subsystem-Neutral | Host administration for core apps and plugins without taking over their domain semantics |
| 4. | TAP-Native       | Use TAP pages, panels, GRIFT, and service-layer patterns where practical |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-administrivia-v0-scope | [Plugin Scope](#plugin-scope) | Implemented | Defines Administrivia as the first-party TAP operator-pages plugin |
| req-administrivia-v0-spec-index | [Hosted Surface Spec Index](#hosted-surface-spec-index) | Implemented | Administrivia keeps references to canonical subsystem specs |
| req-administrivia-v0-code-layout | [Code Layout](#code-layout) | Implemented | Hosted subsystem code lives under app/package-aligned directories |
| req-administrivia-v0-navigation | [Administrivia Navigation](#administrivia-navigation) | Implemented | Administrivia pages should be reachable through stable TAP Web routes and navigation |
| req-administrivia-v0-plugin-contrib | [Plugin-Contributed Administrivia Paths](#plugin-contributed-administrivia-paths) | Backlog | Formalize how other plugins contribute `/administrivia/...` pages |

### Plugin Scope
----
RID: `req-administrivia-v0-scope`
Status: `Implemented`

Administrivia hosts administrative pages, panels, templates, static assets, and supporting view or panel code for TAP's operator-facing UI.

Administrivia should be used when a feature is primarily an administrative or operator surface and when TAP's page/panel system is a better fit than Django admin. Django admin remains useful for low-level development, emergency inspection, and Django-standard model administration, but it is not the desired long-term UX for normal TAP administration.

Administrivia must not become a dumping ground for subsystem semantics. If a page administers `tap_cares`, `tap_grid`, `tap_api`, or another owning app/plugin, the owning subsystem's spec defines the behavior and Administrivia implements the surface.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-administrivia-v0-scope-1 | First-Party Administrivia Plugin | Implemented | Administrivia is documented as TAP's first-party operator-pages plugin. | |
| req-administrivia-v0-scope-2 | Subsystem Semantics Stay Owned | Implemented | Administrative behavior for another subsystem remains specified in that subsystem's specs. | |
| req-administrivia-v0-scope-3 | Django Admin Not Primary UX | Implemented | Specs may use Administrivia pages instead of Django admin for operator workflows. | |

### Hosted Surface Spec Index
----
RID: `req-administrivia-v0-spec-index`
Status: `Implemented`

Administrivia maintains a lightweight index of administrative surfaces it hosts and points each one at its canonical owning spec.

This index is intentionally not a duplicate specification. It should answer: where is the code, where is the route, and which spec owns the behavior?

| Surface | Code Location | Canonical Spec | Route |
| --- | --- | --- | --- |
| Administrivia landing/grid overview | `plugins/administrivia/grift/grid-landing.grift.json` | This spec; TAP Web page/panel specs | `/administrivia` |
| CARES homepage (collectors table) | `plugins/administrivia/tap_cares/panels/collector_table/`, `plugins/administrivia/grift/cares-administrivia.grift.json` | `tap_cares/specs/spec-tap-cares-administrivia.md` | `/administrivia/cares` |
| CARES collector detail | `plugins/administrivia/tap_cares/panels/collector_detail/`, `plugins/administrivia/grift/cares-administrivia.grift.json` | `tap_cares/specs/spec-tap-cares-administrivia.md` | `/administrivia/cares/collector?entity_id=<uuid>` |
| CARES run detail (per-run deep dive) | `plugins/administrivia/tap_cares/panels/run_detail/`, `plugins/administrivia/grift/cares-administrivia.grift.json` | `tap_cares/specs/spec-tap-cares-administrivia.md` | `/administrivia/cares/run?entity_id=<job_uuid>` |
| User management (roster + control) — *Proposed, not yet built* | _planned_ `plugins/administrivia/tap_auth/panels/...` | `tap_auth/specs/spec-tap-auth-user-management-v0.md` | _planned_ `/administrivia/users` |

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-administrivia-v0-spec-index-1 | Hosted Surfaces Listed | Implemented | Administrivia lists the administrative surfaces it hosts. | |
| req-administrivia-v0-spec-index-2 | Canonical Specs Linked | Implemented | Each hosted subsystem surface references the spec that owns its requirements. | |
| req-administrivia-v0-spec-index-3 | No Requirement Duplication | Implemented | The index summarizes ownership and routing without duplicating subsystem requirements. | |

### Code Layout
----
RID: `req-administrivia-v0-code-layout`
Status: `Implemented`

Administrivia code for subsystem-specific Administrivia surfaces should live under directories named after the exact Django app or plugin package that owns the administered subsystem.

Expected v0 pattern:

```text
plugins/administrivia/
  tap_cares/
    panels/
    templates/
    static/
```

The directory uses `tap_cares`, matching the Django app/package name. Human-facing copy may continue to use "tap-cares" or "CARES" where that reads better.

When a hosted surface needs GRIFT page or panel seeds, those seeds may live in `plugins/administrivia/grift/` or a subsystem subdirectory if the plugin's GRIFT loader supports it. The route and code location should be documented in the hosted surface index.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-administrivia-v0-code-layout-1 | App-Aligned Directories | Implemented | Subsystem-specific Administrivia implementation code lives under `plugins/administrivia/<app-or-plugin-package>/`. | |
| req-administrivia-v0-code-layout-2 | Code Location Documented | Implemented | Each hosted surface records its implementation location in the hosted surface index. | |
| req-administrivia-v0-code-layout-3 | GRIFT Location Clear | Implemented | GRIFT seeds for administrative pages have a documented plugin-owned location. | |

### Administrivia Navigation
----
RID: `req-administrivia-v0-navigation`
Status: `Implemented`

Administrivia pages should have stable TAP Web routes. Top-level Administrivia surfaces should be reachable from `/administrivia` or a future Administrivia navigation menu.

Subsystem surfaces should use route prefixes that make ownership obvious to humans:

```text
/administrivia/cares
/administrivia/cares/collector
```

Route design should follow TAP Web page slug and parameter conventions. If a desired route shape cannot be represented by the current TAP Web page routing model, the owning subsystem spec should explicitly choose between query parameters, a new parameterized page route, or a small custom view.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-administrivia-v0-navigation-1 | Stable Routes | Implemented | Administrivia surfaces expose stable TAP Web routes. | |
| req-administrivia-v0-navigation-2 | Prefix Conventions | Implemented | Subsystem Administrivia pages use `/administrivia/<subsystem>` route prefixes. | |
| req-administrivia-v0-navigation-3 | Routing Gaps Named | Implemented | Specs call out when current TAP Web routing cannot express a desired URL shape. | |

### Plugin-Contributed Administrivia Paths
----
RID: `req-administrivia-v0-plugin-contrib`
Status: `Backlog`

Domain plugins should eventually be able to ship their own Administrivia pages under the shared `/administrivia/...` route space without moving all implementation code into the Administrivia plugin.

The current TAP Web and plugin GRIFT machinery already permits a plugin to declare a Page with a slug such as:

```text
/administrivia/ksi
```

provided the slug is unique and does not use a TAP Web reserved prefix. Current reserved prefixes are `/admin`, `/api`, and `/panel`; `/administrivia` is not reserved.

What remains unspecified is the governance and discovery contract:

- who owns a contributed Administrivia route
- how collisions under `/administrivia/...` are detected before import
- how contributed pages appear in Administrivia navigation
- whether Administrivia keeps a central hosted-surface index for externally contributed pages
- whether route prefixes should use plugin package names, human-friendly slugs, or declared Administrivia aliases
- how specs in the contributing plugin reference Administrivia as the hosting route family

Until this backlog requirement is implemented, first-party subsystem Administrivia surfaces may live in `plugins/administrivia/<app-or-plugin-package>/`, and domain plugins may still seed ordinary TAP Web pages under `/administrivia/...` when the route ownership is explicitly reviewed.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-administrivia-v0-plugin-contrib-1 | Contribution Contract Defined | Backlog | A future spec defines how non-Administrivia plugins contribute `/administrivia/...` pages. | |
| req-administrivia-v0-plugin-contrib-2 | Collision Handling | Backlog | Contributed Administrivia paths have a deterministic collision detection and resolution process. | |
| req-administrivia-v0-plugin-contrib-3 | Navigation Integration | Backlog | Contributed Administrivia paths can appear in Administrivia navigation without hand-editing a central page each time. | |
| req-administrivia-v0-plugin-contrib-4 | Spec Ownership Preserved | Backlog | Contributed pages keep their canonical behavioral specs in the owning plugin or app. | |

## Future

- Define a first-class Administrivia navigation menu once `tap_web` navigation behavior stabilizes.
- Decide whether Administrivia should own shared UI primitives such as status badges, empty states, and run-history tables.
- Consider an Administrivia landing page that groups hosted surfaces by subsystem and health state.
