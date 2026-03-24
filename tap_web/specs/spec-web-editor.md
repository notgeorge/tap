# Web Editor Specification

## Philosophy

TAP Web needs a generic editor shell for graph-native objects. The editor should work for simple model-backed nodes first, remain compatible with richer objects later, and avoid forcing every editable thing into a bespoke one-off page.

The editor is graph-aware rather than form-only. Editing an object should always show the object in graph context, because meaning in TAP is carried by both the object and its immediate relationships.

The first implementation target is a simple object such as a LOTR character. More advanced artifacts such as layouts, pages, and panels should be able to extend the same editor shell with richer object-specific preview behavior.

Hotlink editing is intentionally deferred. It requires additional relationship-aware logic and should be handled as a separate backlog concern rather than folded into the first generic editor contract.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Generic | One editor shell works for simple node objects and can be extended for richer TAP artifacts |
| 2. | Graph-Aware | The edited object is always shown in immediate graph context |
| 3. | Typed | Forms should model real fields first, not default to raw JSON editing |
| 4. | Previewable | Users can apply draft changes to a preview without saving |
| 5. | Progressive | Start with simple model-backed objects; defer hotlinks and other relationship-heavy editing |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-editor-shell | [Editor Shell](#editor-shell) | Proposed | Shared editor page structure for editable TAP objects |
| req-web-editor-graph | [Graph Context Preview](#graph-context-preview) | Proposed | Cytoscape hub-and-spoke view of the edited object and its immediate relationships |
| req-web-editor-object-preview | [Object Preview](#object-preview) | Proposed | Type-aware preview of what the edited object looks like |
| req-web-editor-preview-exec | [Preview Execution](#preview-execution) | Proposed | Preview applies draft changes without persisting them |
| req-web-editor-typed | [Typed Editor Contract](#typed-editor-contract) | Proposed | Editor descriptors provide typed forms, initial values, preview behavior, and save behavior |
| req-web-editor-fields | [Field Strategy](#field-strategy) | Proposed | Start with Django Forms / ModelForms; structured-object fields may layer on later |
| req-web-editor-hotlinks | [Hotlink Editing Deferral](#hotlink-editing-deferral) | Backlog | Hotlinks require more complex editor logic and are explicitly deferred |
| req-web-editor-form.sec | [Editor Form Security](#editor-form-security) | Proposed | Generic editor security contract superseding panel-only wording |

### Editor Shell
----
RID: `req-web-editor-shell`
Status: `Proposed`

TAP Web provides a standard editor shell for editable objects. The shell is generic and not owned by any one object type.

#### Implementation
- The editor page is composed of three conceptual regions:
  - graph context preview at the top
  - object preview beneath it when the edited type supports one
  - typed editor form beneath the preview regions
- The shell provides standard actions:
  - `Preview`
  - `Save`
- The shell owns page chrome, action placement, and request lifecycle.
- Edited object types provide only typed editor content and preview behavior.

#### Development
Keep the shell stable and make object types plug into it. The shell should not need to be rewritten for each new node or edge editor.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-editor-shell-1 | Shared Editor Shell Exists | Proposed | TAP Web defines one standard editor page shell rather than per-type page structures. | |
| req-web-editor-shell-2 | Standard Actions | Proposed | The shell exposes both `Preview` and `Save` actions. | |
| req-web-editor-shell-3 | Type Supplies Editor Content | Proposed | Edited object types provide typed editor fields inside the shared shell rather than replacing the shell itself. | |

### Graph Context Preview
----
RID: `req-web-editor-graph`
Status: `Proposed`

The top of the generic editor always shows a Cytoscape representation of the edited object in immediate graph context.

#### Implementation
- The graph preview uses a hub-and-spoke representation.
- The edited object is the hub.
- The graph includes:
  - the edited object
  - immediate outbound edges and connected nodes
  - immediate inbound edges and connected nodes
- The preview uses TAP-managed Cytoscape assets rather than CDN assets.
- The graph preview is read-only in the first implementation.

#### Development
Make graph context mandatory in the editor shell. TAP objects should not be edited as if they were disconnected rows in a CRUD admin.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-editor-graph-1 | Graph Region Exists | Proposed | The top region of the generic editor contains a Cytoscape graph preview. | |
| req-web-editor-graph-2 | Edited Object Is Hub | Proposed | The edited object is centered conceptually as the hub in the graph preview. | Visual centering strategy may vary by layout implementation. |
| req-web-editor-graph-3 | Immediate Relationships Included | Proposed | The graph preview includes immediate inbound/outbound edges and connected nodes only. | |
| req-web-editor-graph-4 | Read Only In V1 | Proposed | The first graph preview does not mutate graph structure. | |

### Object Preview
----
RID: `req-web-editor-object-preview`
Status: `Proposed`

The generic editor may show an object-specific preview beneath the graph preview when the edited type has a meaningful human-facing representation.

#### Implementation
- Simple model-backed objects may omit a rich object preview and rely on the graph preview plus form fields.
- More advanced objects such as layouts, pages, and panels should provide an object preview showing what the object looks like.
- Object preview behavior is type-aware and optional at the contract level.

#### Development
Do not force every editable type to invent a visual preview. Reserve rich object previews for artifacts whose visible output is a core part of the editing task.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-editor-object-preview-1 | Type-Aware Preview Supported | Proposed | Edited object types may provide an object-specific preview region. | |
| req-web-editor-object-preview-2 | Rich Artifacts Show What They Look Like | Proposed | Layouts, pages, panels, and similar artifacts may render a visual object preview in the generic editor shell. | |
| req-web-editor-object-preview-3 | Simple Types May Omit Rich Preview | Proposed | Simple model-backed objects are not required to provide a second rich preview surface beyond graph context. | |

### Preview Execution
----
RID: `req-web-editor-preview-exec`
Status: `Proposed`

Preview applies pending editor changes without saving them.

#### Implementation
- `Preview` submits the current editor state through the same validation path used for save.
- Preview constructs a draft object state in memory.
- Preview does not persist database changes.
- Preview may render:
  - graph preview based on current persisted relationships in v1
  - object preview using draft field values
- `Save` persists validated changes after the user chooses to commit them.

#### Development
Preview should mean "apply the current draft," not "show the last saved object." This distinction matters most once the editor becomes more than a readonly inspector with a form attached.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-editor-preview-exec-1 | Preview Does Not Save | Proposed | Preview applies changes without persisting them. | |
| req-web-editor-preview-exec-2 | Preview Uses Validation Path | Proposed | Preview validates the current editor payload before rendering draft output. | |
| req-web-editor-preview-exec-3 | Save Remains Explicit | Proposed | Persistence occurs only through the explicit `Save` action. | |
| req-web-editor-preview-exec-4 | Draft Object Preview Supported | Proposed | Preview rendering may use unsaved draft object state. | |

### Typed Editor Contract
----
RID: `req-web-editor-typed`
Status: `Proposed`

Editable object types plug into the generic editor through a typed editor descriptor rather than raw JSON by default.

#### Implementation
- A typed editor descriptor may provide:
  - `form_class`
  - `get_editor_initial(obj)`
  - `build_preview(form, obj, request)` or equivalent draft-construction hook
  - `handle_save(form, obj, request)`
  - optional preview template/context hooks for object-specific previews
- Typed editor descriptors are the standard extension path for node, edge, and richer object editors.
- Raw JSON editing is a fallback/debug path rather than the primary editor contract.

#### Development
This keeps TAP editors grounded in domain fields and model semantics rather than encouraging every new editor to become a generic JSON blob surface.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-editor-typed-1 | Typed Descriptor Contract Exists | Proposed | Editable object types integrate with the shell through a typed editor descriptor contract. | |
| req-web-editor-typed-2 | Initial State Hook | Proposed | Typed editors can provide initial field values for an existing object. | |
| req-web-editor-typed-3 | Preview Hook | Proposed | Typed editors can construct draft preview state without persisting it. | |
| req-web-editor-typed-4 | Save Hook | Proposed | Typed editors can persist validated changes through a dedicated save hook. | |
| req-web-editor-typed-5 | Raw JSON Is Fallback | Proposed | Raw JSON editing is not the default editor mode for typed objects. | |

### Field Strategy
----
RID: `req-web-editor-fields`
Status: `Proposed`

The editor system starts with Django Forms / ModelForms for ordinary fields and adds more specialized structured-object controls only when needed.

#### Implementation
- The preferred first-pass field strategies are:
  - `forms.ModelForm` for simple model-backed objects
  - `forms.Form` for mixed editors that combine model fields with related-edge or config fields
- Typical scalar fields should use standard Django form fields and widgets.
- Structured embedded objects should not force immediate adoption of a full schema-form system.
- If embedded object editing becomes necessary, TAP may add a focused structured-object widget later.

#### Development
This keeps the initial editor stack aligned with TAP's server-rendered Django + HTMX approach and avoids overcommitting to schema-form tooling that often becomes awkward for authored domain objects.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-editor-fields-1 | Django Forms First | Proposed | Standard Django Forms / ModelForms are the default field editing mechanism. | |
| req-web-editor-fields-2 | Scalar Fields Use Standard Widgets | Proposed | Common scalar model fields use ordinary Django form fields and widgets in v1. | |
| req-web-editor-fields-3 | Structured Objects Layer Later | Proposed | Embedded structured-object editing may be added later without redefining the base editor contract. | |

### Hotlink Editing Deferral
----
RID: `req-web-editor-hotlinks`
Status: `Backlog`

Editing hotlinks requires relationship-aware logic beyond the first generic editor pass and is explicitly deferred.

#### Implementation
Future work must define:
- how hotlink-backed relationships are surfaced in the editor
- how preview applies hotlink changes before save
- how hotlink editing interacts with graph preview and related-object mutation

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-editor-hotlinks-1 | Hotlink Editing Deferred Explicitly | Backlog | Hotlink editing is tracked as backlog work rather than assumed by the first editor contract. | |

### Editor Form Security
----
RID: `req-web-editor-form.sec`
Status: `Proposed`

Generic editor submissions must use standard Django form security protections. This requirement generalizes the earlier panel-only wording to all TAP Web editors.

#### Implementation
- CSRF protection is provided by Django middleware and required in all editor forms.
- Submitted values are validated server-side before preview or save.
- Untrusted input is written to persisted storage only from validated form data, never directly from raw request payloads.
- Rendered preview output uses the same default Django escaping rules unless a future hardened spec explicitly allows trusted HTML.

#### Development
Editor security should be defined once at the generic editor layer and then referenced by panel, node, and edge editors.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-editor-form.sec-1 | CSRF Required | Proposed | All generic editor forms include CSRF protection. | |
| req-web-editor-form.sec-2 | Server Validation Required | Proposed | Preview and save both use server-side validation before applying editor input. | |
| req-web-editor-form.sec-3 | Untrusted Input Handling | Proposed | Persisted changes originate from validated form data rather than raw request payloads. | |
| req-web-editor-form.sec-4 | Default Escaping Applies | Proposed | Preview and later rendering use standard Django escaping by default. | |

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
