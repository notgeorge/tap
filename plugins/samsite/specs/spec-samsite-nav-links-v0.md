# Samsite Nav Links Panel Specification

## Philosophy

`samsite-nav-links` is a small, generic panel type that renders a configurable list of link cards from `panel.config.links`. It exists because Samsite needed one-click nav discoverability between its pages (`req-samsite-pages-discovery`) and no shipped `tap_web` panel type fit the use case — the closest, `text_panel`, auto-escapes its body and so can't render `<a>` tags.

The panel is intentionally **boring**: no Python view-context logic, no Gryphon queries, no behavior beyond rendering the config as cards. Django auto-escaping handles the security boundary; every field in every link object is escaped on render. There is no `|safe` filter and no HTML-in-config path.

It lives in `plugins/samsite/` for now because samsite is its only consumer. The code is consumer-neutral; if a second plugin needs the same panel, it should be lifted to a shared location (likely `tap_web.panels.nav_links` rather than another plugin) — but per [[future-seam-discipline]], don't pre-lift on one use.

## Goals

|   | Goal | Description |
| :---: | --- | --- |
| 1. | Pure GRIFT Wiring | A consumer page references the panel by slug and supplies the link list in panel config — no Python required by the consumer. |
| 2. | Safe by Default | All user-visible content runs through Django auto-escaping; no template uses `|safe` on link fields. |
| 3. | No Logic | The panel does no DB queries, no Gryphon, no `get_view_context` override; the template reads `panel.config.links` directly. |
| 4. | Reusable Where it Fits | The panel can be instantiated on any Samsite page that wants a row of nav cards; it knows nothing samsite-specific. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-samsite-nav-links-panel | [Panel Type Contract](#panel-type-contract) | Implemented | `panels/nav_links/__init__.py`; registered in `SamsiteConfig.ready()` |
| req-samsite-nav-links-config | [Config Shape](#config-shape) | Implemented | `{links: [{label, href, description?}]}` |
| req-samsite-nav-links-security | [Safe Rendering](#safe-rendering) | Implemented | Django auto-escape; no `\|safe` on link fields; no HTML-in-config |
| req-samsite-nav-links-css | [Visual Style](#visual-style) | Implemented | Responsive `grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr))` |
| req-samsite-nav-links-lift | [Future Lift](#future-lift) | Backlog | Promote to `tap_web` when a second consumer plugin needs the same panel |

### Panel Type Contract
----
RID: `req-samsite-nav-links-panel`
Status: `Implemented`

Slug **`samsite-nav-links`**, registered in `tap_web.registry.panel_type_registry` via `SamsiteConfig.ready()`. The panel type class is the standard duck-typed shape (slug, label, view, css, js, config_defaults), with **no `get_view_context` classmethod** — the template renders directly from the Panel object's config.

```python
class NavLinksPanelType:
    slug = "samsite-nav-links"
    label = "Samsite Nav Links"
    view = "samsite/panels/nav_links.html"
    css = ["samsite/css/panel-nav-links.css"]
    js = []
    config_defaults = {"links": []}
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-nav-links-panel-1 | Registered | Implemented | The panel type is registered in `panel_type_registry` at plugin ready time. | |
| req-samsite-nav-links-panel-2 | No View-Context Logic | Implemented | The panel type class has no `get_view_context` method; the template reads `panel.config.links` directly. | |
| req-samsite-nav-links-panel-3 | Default Config | Implemented | `config_defaults = {"links": []}` so a misconfigured panel renders an "empty" state, not a crash. | |

### Config Shape
----
RID: `req-samsite-nav-links-config`
Status: `Implemented`

`panel.config.links` is a list of link objects. Each link object:

| Field | Type | Required | Description |
| --- | --- | :---: | --- |
| `label` | string | yes | The clickable card title; rendered as `<span class="samsite-nav-link-label">`. |
| `href` | string | yes | The link target; rendered as the `<a>` element's `href` attribute. Auto-escaped by Django on render. |
| `description` | string | no | Optional second-line text below the label; rendered when non-empty. |

Example (from `compliance-landing.grift.json` nav-additions batch):

```json
{
  "links": [
    {"label": "OSCAL SSP Workbench", "href": "/samsite/compliance/oscal", "description": "Render the latest OSCAL System Security Plan as a readable workbench."},
    {"label": "OSCAL POA&M Workbench", "href": "/samsite/compliance/poam", "description": "Render the latest OSCAL Plan of Action and Milestones as an action register."},
    {"label": "KSI Scoreboard", "href": "/samsite/compliance/scoreboard", "description": "Synthesized FedRAMP 20x KSI status — joins the indicator catalog against the latest SSP + POA&M for passing/in-progress/accepted/gap per KSI."}
  ]
}
```

Missing-field tolerance: if a link object lacks `label` or `href`, Django's template renders the empty string for the missing field. The panel does not validate — that's the GRIFT importer's job (if it ever needs strict validation, it'd live in a JSON Schema on the config, per [[json-formats-need-schema]]).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-nav-links-config-1 | Required Fields | Implemented | `label` and `href` are required per link; `description` optional. | |
| req-samsite-nav-links-config-2 | Empty List | Implemented | An empty `links` array renders a "No links configured." placeholder. | |

### Safe Rendering
----
RID: `req-samsite-nav-links-security`
Status: `Implemented`

Every link field is rendered through Django's default auto-escaping. The template does NOT use `|safe`, `mark_safe`, or any `{% autoescape off %}` block. Concretely:

```html
<a href="{{ link.href }}" class="samsite-nav-link">
  <span class="samsite-nav-link-label">{{ link.label }}</span>
  {% if link.description %}<span class="samsite-nav-link-desc">{{ link.description }}</span>{% endif %}
</a>
```

If `link.href` contained `javascript:alert(1)` or `link.label` contained `<script>`, both would be escaped on render. The panel does no URL-scheme allow-listing or other validation — Django's escaping is the security boundary.

This stance is appropriate because **GRIFT is operator-authored config**, not user input. The threat model is "an operator mistypes a link," not "an attacker injects into a GRIFT file." If/when a future use case puts user-supplied content into a nav-links panel (which would be a weird shape), the safety story changes and this requirement gets revisited.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-nav-links-security-1 | Auto-Escape | Implemented | The template renders link fields with default Django auto-escaping; no `|safe` or `autoescape off`. | |
| req-samsite-nav-links-security-2 | No HTML in Config | Implemented | The config field semantics are plain text only — operators don't put `<a>` tags into `label` or `description`. | The template structures the `<a>` element; config supplies its attribute values |

### Visual Style
----
RID: `req-samsite-nav-links-css`
Status: `Implemented`

The cards lay out as a responsive grid (`repeat(auto-fit, minmax(15rem, 1fr))`) and reflow naturally on narrow viewports. Hover state colors the border + background per `:hover, :focus-visible`. Stylesheet is `samsite/css/panel-nav-links.css`; class prefix `samsite-nav-link*` scopes from host pages.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-nav-links-css-1 | Responsive Grid | Implemented | Cards reflow via `grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr))`. | |
| req-samsite-nav-links-css-2 | Focusable | Implemented | Cards style on `:focus-visible` (keyboard nav) in addition to `:hover`. | |

### Future Lift
----
RID: `req-samsite-nav-links-lift`
Status: `Backlog`

If a second plugin needs the same shape, the lift target is `tap_web.panels.nav_links` (slug `tap-web-nav-links` or similar), not another consumer plugin. The panel is consumer-neutral; only its current home is samsite-specific. Per [[future-seam-discipline]], wait for the second consumer before lifting.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-samsite-nav-links-lift-1 | Document the Lift | Backlog | When promoted, the spec moves into `tap_web/specs/` and this spec gets a one-line pointer. | |
