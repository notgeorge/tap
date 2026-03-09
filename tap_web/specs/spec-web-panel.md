# Panel Spec


## Philosophy

Panels are the primary unit of data display in TAP. A panel is a self-contained view of data from the grid — a query, a visualization, a form, or any other render surface — that can be embedded into one or more pages. Panels are intentionally dumb about their host page; they receive a set of inputs, render their content, and surface outputs. Pages are responsible for wiring panels together.

Because panels are first-class entities on the grid, they can be shared across pages, versioned, queried, and used as the unit of curation for a dashboard-style UI.

## Goals

|    |                  |                                                                                                      |
| :---: | ---           | ---                                                                                                  |
| 1. |   Self-Contained  | A panel renders with only its declared inputs; no hidden ambient state                              |
| 2. |   Pluggable       | Plugin authors can register new panel types without modifying tap_web core                          |
| 3. |   Grid-Native     | Panels are entities — they can be linked, traversed, and queried like any other node, stored in the web dimension                |
| 4. |   Edit Included   | Panels come with a built-in way for users to edit the construction / configuration of that panel instance | 
| 5. |   Smart           | Panels are backed by code that can implement whatever complex processing is required to get to the right visualization and edit capabilities. | 


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-panel-obj | [Panel Objects](#panel-objects) | Implemented | Panel model with slug, view template path, and asset lists |
| req-web-panel-static | [Panel Static Assets](#panel-static-assets) | Proposed | Static assets live in Django static paths; no external URLs allowed |


## Invariants
HTMX-compliant - Designed to be looked up via htmx calls from the page 
Sanitized - Are sanitized using Django's built-in rendering functions, no unsafe html used.

---


### Panel Object
----
RID: `req-web-panel-obj`
Status: `Implemented`

A Panel object is the backing entity for a data-display component. It declares its panel renderer, static assets, and display metadata.

#### Fields

| Field | Type | Required | Notes |
| --- | --- | :---: | --- |
| `slug` | CharField (kebab-case) | Yes | Human-readable label used in the panel HTMX URL alongside the entity UUID. No uniqueness constraint — the UUID disambiguates. |
| `title` | CharField | Yes | Display name shown in UI |
| `description` | TextField | No | What the panel is for |
| `view` | CharField | Yes | Template path string (e.g. `"tap_plugins/lotr/templates/character_list.html"`). The panel view handler renders this template. |
| `js` | JSONField (list) | No | Flat list of static-relative JS paths (e.g. `["js/cytoscape.js"]`). Default: `[]`. |
| `css` | JSONField (list) | No | Flat list of static-relative CSS paths (e.g. `["css/panel.css"]`). Default: `[]`. |

Panels do not define or own `panel-id`. `panel-id` is a page-local slot identity defined in the page spec and used by page layout, page-panel links, and rendering.

#### Panel URL

Panels are served via HTMX from the page template at:

```
/panel/<slug>--<entity-uuid>/
```

The `slug` portion is the Panel's `slug` field value. The UUID is the Panel's `entity_id`. Together they form a URL that is both human-readable and unambiguously unique. The view handler parses the UUID suffix to look up the Panel; the slug is decorative.

#### Status Details

#### Implementation

`Panel` model in `tap_web/models.py` declares the fields above. The generic panel view handler in `tap_web/views.py` receives a request, looks up the Panel by entity UUID extracted from the URL, and calls `django.shortcuts.render(request, panel.view)` to render the panel's declared template. The panel error fragment is returned on any exception so the HTMX swap completes and the slot shows "Panel Error" rather than leaving the page broken.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-obj-1 | Panel Fields | Implemented | Panel declares `slug`, `title`, `description`, `view`, `js`, `css` as described above. | |
| req-web-panel-obj-2 | View Is Template Path | Implemented | `view` stores a template path string. The generic panel view handler renders it with `render(request, panel.view)`. | |
| req-web-panel-obj-3 | Asset Lists Default Empty | Implemented | `js` and `css` default to `[]` when not set. | |
| req-web-panel-obj-4 | Panel URL Format | Implemented | Panel HTMX endpoint is `/panel/<slug>--<entity-uuid>/`. UUID is used for lookup; slug is decorative. | |
| req-web-panel-obj-5 | Panel Error Fragment | Implemented | If the panel view raises any exception, the endpoint returns an HTML error fragment (HTTP 200) so HTMX swap completes with a "Panel Error" slot. | |
| req-web-panel-obj-6 | Web Dimension | Implemented | Panel carries `DEFAULT_DIMENSIONS = {"tap.graph": "web"}` (already implemented). | |

#### Future


### Panel Registry
----
RID: `req-web-panel-registry`
Status: `Proposed`

Panels are registered at load time in a run-time registry similar to the node's registry.

### Panel Static Assets
----
RID: `req-web-panel-static`
Status: `Proposed`

Panel static objects live in a django-standard static asset path which will make them accessible using standard static lookups.

Directory structure will be standardized as
* /js - javascript assets
* /css - css assets

A panel is allowed to reference assets from other plugins.
A panel is NOT ALLOWED to reference assets from the Internet at this time.

---

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: \`...\``
`Status: \`...\``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
