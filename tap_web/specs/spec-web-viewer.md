# Web Viewer Specification

## Philosophy

TAP Web needs a default human-facing viewer for graph-native objects. The viewer should present the same core information model as the editor, but in a readable non-editable form optimized for understanding rather than mutation.

The viewer is not just a CRUD detail page. TAP objects are graph-native, so the default viewer should always provide contextual understanding of the object and allow richer object types to substitute a more semantically meaningful context surface where appropriate.

The first implementation target is a simple default object viewer for ordinary model-backed nodes. More advanced object types such as locations, pages, panels, and layouts should be able to extend the same viewer shell with richer context and body rendering.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Readable | The default viewer presents object information clearly without editing affordances |
| 2. | Consistent | Viewer and editor share the same core object information model |
| 3. | Contextual | Every viewer includes a top context region for situating the object |
| 4. | Extensible | Object types may provide richer context and body views when a generic fallback is insufficient |
| 5. | Progressive | A simple default viewer works first; richer type-specific viewers layer on later |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-viewer-shell | [Viewer Shell](#viewer-shell) | Proposed | Shared non-editable viewer page structure for TAP objects |
| req-web-viewer-context | [Context Region](#context-region) | Proposed | Default top region situates the object and may be overridden by richer type-specific context |
| req-web-viewer-fields | [Default Field Rendering](#default-field-rendering) | Proposed | Generic readable rendering for object fields |
| req-web-viewer-enhanced | [Enhanced Type-Specific Views](#enhanced-type-specific-views) | Proposed | Object types may provide richer context and body rendering |
| req-web-viewer-parity | [Viewer Editor Information Parity](#viewer-editor-information-parity) | Proposed | Viewer and editor expose the same core object information model |
| req-web-viewer-fallback | [Fallback Rendering Strategy](#fallback-rendering-strategy) | Proposed | Disabled-form style rendering may exist as an implementation fallback but is not the preferred UX |
| req-web-viewer-render.sec | [Viewer Rendering Security](#viewer-rendering-security) | Proposed | Viewer output uses standard Django escaping by default |

### Viewer Shell
----
RID: `req-web-viewer-shell`
Status: `Proposed`

TAP Web provides a standard viewer shell for object display. The shell is generic and not owned by any one object type.

#### Implementation
- The viewer page is composed of two conceptual regions:
  - a top context region
  - an object body region
- The shell owns page structure and navigation chrome.
- Object types may supply custom content for one or both regions.
- The viewer contains no editing affordances by default.

#### Development
Keep the shell stable and let object types extend it. Simple objects should get a useful default view without requiring custom templates.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-viewer-shell-1 | Shared Viewer Shell Exists | Proposed | TAP Web defines one standard object viewer shell rather than requiring per-type detail page structures. | |
| req-web-viewer-shell-2 | Non-Editable By Default | Proposed | The default viewer presents object information without edit controls. | |
| req-web-viewer-shell-3 | Type Content Plugs Into Shared Shell | Proposed | Object types may supply context and body content inside the shared viewer shell. | |

### Context Region
----
RID: `req-web-viewer-context`
Status: `Proposed`

Every viewer includes a top context region that situates the object for a human reader.

#### Implementation
- The default top context region is graph context.
- The default graph context may use a Cytoscape representation of the object and its immediate relationships.
- Object types may replace the default graph context with a more semantically meaningful context surface.
- The context region is read-only in the first implementation.

Examples of richer context surfaces:
- a location may show a map
- a panel may show a rendered panel preview
- a page may show a page preview
- a layout may show a layout or scene preview

#### Development
The top region should answer "what kind of thing is this in context?" before the user reads field details.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-viewer-context-1 | Top Context Region Exists | Proposed | Every object viewer includes a top context region. | |
| req-web-viewer-context-2 | Graph Context Is Default | Proposed | The default context region uses graph context for objects without a richer override. | |
| req-web-viewer-context-3 | Type May Replace Context Surface | Proposed | Object types may replace the default graph context with a more semantically meaningful context surface. | |
| req-web-viewer-context-4 | Context Region Is Read Only | Proposed | The first viewer context region does not mutate object or graph state. | |

### Default Field Rendering
----
RID: `req-web-viewer-fields`
Status: `Proposed`

The default viewer body renders object fields in readable HTML rather than editable controls.

#### Implementation
- Scalar fields render as label/value content blocks.
- Long text fields render as readable text blocks.
- Boolean, date, and numeric fields render in human-readable display forms.
- Related objects may render as links, badges, or summary references when appropriate.
- Structured values may render as formatted blocks when no richer renderer exists.
- The default viewer body should not require a custom template for simple model-backed objects.

#### Development
The default viewer should look like a basic web page, not a disabled admin form, even if some implementation details reuse form metadata under the hood.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-viewer-fields-1 | Readable Field Display | Proposed | The default viewer renders fields as readable HTML content rather than editable inputs. | |
| req-web-viewer-fields-2 | Common Scalar Types Supported | Proposed | The generic viewer body supports common scalar field types without requiring custom type-specific templates. | |
| req-web-viewer-fields-3 | Structured Values Fallback | Proposed | Structured values have a readable fallback rendering when no richer type-specific rendering exists. | |

### Enhanced Type-Specific Views
----
RID: `req-web-viewer-enhanced`
Status: `Proposed`

Object types may provide richer viewer behavior when the generic fallback is not sufficient.

#### Implementation
- Object types may provide:
  - a custom top context region
  - a custom object body region
  - both
- Enhanced viewer behavior should still fit inside the shared viewer shell.
- Type-specific viewers should be used when the object has a strong human-facing representation that would be poorly served by generic field display alone.

#### Development
Use enhanced viewers to improve comprehension, not merely to make every type bespoke. Simple objects should keep the default view unless there is a clear gain from customization.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-viewer-enhanced-1 | Custom Context Surface Allowed | Proposed | Object types may provide a custom context region in place of the default graph context. | |
| req-web-viewer-enhanced-2 | Custom Body View Allowed | Proposed | Object types may provide a custom object body renderer. | |
| req-web-viewer-enhanced-3 | Shared Shell Preserved | Proposed | Enhanced viewers still render within the shared viewer shell. | |

### Viewer Editor Information Parity
----
RID: `req-web-viewer-parity`
Status: `Proposed`

Viewer and editor should present the same core object information model even though they serve different purposes.

#### Implementation
- The viewer should expose the same core object fields the editor treats as important.
- The viewer is optimized for readable presentation.
- The editor is optimized for mutation, validation, preview, and save.
- Type-specific overrides in one surface should not silently omit core object meaning from the other surface.

#### Development
Parity does not mean identical layout. It means the viewer and editor should agree on what information defines the object.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-viewer-parity-1 | Shared Core Information Model | Proposed | Viewer and editor present the same core object information model. | |
| req-web-viewer-parity-2 | Purpose-Specific Presentation | Proposed | Viewer and editor may differ in layout and interaction model while still presenting the same core information. | |

### Fallback Rendering Strategy
----
RID: `req-web-viewer-fallback`
Status: `Proposed`

The viewer may use form-derived metadata or even disabled-control rendering as an implementation fallback, but that fallback is not the preferred UX contract.

#### Implementation
- Form definitions may be reused internally for labels, help text, and field ordering.
- A disabled-form style rendering may be used temporarily as a low-effort fallback.
- The intended default viewer UX is readable HTML content, not a frozen editor form.

#### Development
This requirement allows fast scaffolding without baking a weak presentation model into the specification itself.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-viewer-fallback-1 | Form Metadata Reuse Allowed | Proposed | Viewer implementations may reuse form-derived metadata to avoid duplicating labels and ordering logic. | |
| req-web-viewer-fallback-2 | Disabled Form Not Canonical UX | Proposed | Disabled-form rendering may exist as a fallback but is not the intended long-term viewer presentation model. | |

### Viewer Rendering Security
----
RID: `req-web-viewer-render.sec`
Status: `Proposed`

Viewer output uses standard Django escaping by default and does not treat object content as trusted HTML unless a future hardened requirement explicitly permits it.

#### Implementation
- Django template auto-escaping applies by default to viewer templates.
- Viewer templates must not mark user-sourced or object-sourced values as safe unless explicitly allowed by a separate hardened specification.
- Richer context surfaces such as maps or rendered previews must still respect TAP-managed asset and rendering safety constraints.

#### Development
Viewer richness should not widen the default trust boundary for object content.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-viewer-render.sec-1 | Default Escaping Applies | Proposed | Viewer output uses standard Django escaping by default. | |
| req-web-viewer-render.sec-2 | No Implicit Trusted HTML | Proposed | Viewer surfaces do not implicitly treat object content as trusted HTML. | |

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

`RID: `...``
`Status: `...``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
