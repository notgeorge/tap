# ROSCALE Plugin Specification

## Plugin Identity

- **Slug:** `roscale`
- **Display name:** ROSCALE (Read OSCAL Edit)
- **Panel types provided:**
  - `roscale-oscal-workbench` — OSCAL SSP workbench; default page variable `oscal_ssp_artifact_entity_id`
  - `roscale-oscal-poam-workbench` — OSCAL POA&M workbench; default page variable `oscal_poam_artifact_entity_id`
- **Repo shape:** In-tree under `plugins/roscale/` for v0. No standalone git repo or submodule; may be split later if external consumers appear.
- **Default dimensions:** N/A. ROSCALE contributes no TAP-managed entities (no models, edges, or GRIFT seed data) in v0 — the default-dimensions requirement does not apply.

## Philosophy

ROSCALE stands for **Read OSCAL Edit**. Other TAP plugins ingest OSCAL documents from upstream sources and store them as on-grid compliance artifacts (the `fedramp_20x_ksi.compliance_artifact` model is the convention). ROSCALE's job is the presentation layer: parse, validate, and render those artifacts inside a TAP Web workbench panel so a human can actually read what the document says about a system.

The first ROSCALE demand signal is sharp: make on-grid OSCAL readable and visually compelling without re-modeling its content. The fastest path is parse-to-page from the existing on-grid artifact node — no separate ingest, no graph decomposition, no per-field nodes. ROSCALE owns the parser, validator, panel types, templates, static assets, and rendering behavior. **Consumers** — other plugins that have OSCAL artifacts on the grid — contribute the pages and panel instances that host ROSCALE's panels.

ROSCALE recognizes two OSCAL document types in v0, each with its own panel type because they tell different stories:

- **System Security Plan** (`system-security-plan`) — what the system is, what it claims, and how controls are implemented. Rendered by `roscale-oscal-workbench`.
- **Plan of Action and Milestones** (`plan-of-action-and-milestones`) — what remains open, what has been risk-accepted, what assets/controls are implicated, and what remediation plan is recorded. Rendered by `roscale-oscal-poam-workbench`.

This is a deliberate update to the earlier stance in `plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-compliance-artifacts-v0.md` that OSCAL renderings stay blobbed and are not decomposed. That stance was correct before a presentation demand existed: the KSI signal was the canonical source and OSCAL was a downstream rendering. ROSCALE does not make OSCAL the canonical source either. It adds a presentation and parsing layer so humans can read the OSCAL document that already exists on the grid.

The implementation order is:

1. Render a useful OSCAL workbench from the existing artifact node.
2. Add validation and polished partial-error behavior.
3. Parse deeper into a reusable internal structure.
4. Later, decompose OSCAL pieces into first-class grid nodes and edges where the graph value is clear.
5. Much later, explore editing and re-emitting OSCAL documents.

## Goals

|   | Goal | Description |
| :---: | --- | --- |
| 1. | Workbench First | Render a visually appealing one-page OSCAL workbench from an existing on-grid artifact node. |
| 2. | Consumer Fast Path | Let consumer plugins define only the page and panel instance (via GRIFT or equivalent); ROSCALE owns all implementation code. |
| 3. | Best-Effort Parsing | Parse and render what can be understood, while showing validation and parser errors clearly. |
| 4. | Validation Built In | Validate against official OSCAL schemas where possible and supplement with TAP-authored semantic checks. |
| 5. | Future Decomposition | Prepare for deep OSCAL grid decomposition without blocking the first visible page. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-roscale-scope | [Plugin Scope](#plugin-scope) | Implemented | Helper/presentation plugin, no schedule; manifest declares no models/edges/grift |
| req-roscale-panel | [OSCAL SSP Workbench Panel](#oscal-ssp-workbench-panel) | Implemented | `roscale-oscal-workbench` registered in `apps.py` `ready()`; class at `panels/oscal_workbench/__init__.py` |
| req-roscale-poam-panel | [OSCAL POA&M Workbench Panel](#oscal-poam-workbench-panel) | Implemented | `roscale-oscal-poam-workbench` registered in `apps.py` `ready()`; class at `panels/oscal_poam_workbench/__init__.py` |
| req-roscale-input | [Panel Input Contract](#panel-input-contract) | Implemented | Panel reads `config['artifact_entity_id_var']` then `request.GET[<var_name>]`; URL-backed per `req-roscale-input-3`. Optional `config.fallback.kind` makes the panel resolve the latest emission when the URL var is empty (`req-roscale-input-5`) |
| req-roscale-source | [Generous Source Handling](#generous-source-handling) | Implemented | Accepts artifact nodes and raw OSCAL values |
| req-roscale-validation | [OSCAL Validation](#oscal-validation) | Implemented | Official schemas plus TAP semantic checks. `pattern` keyword skipped (ECMA-262 `\p{...}` unsupported by Python `re`); surfaced via `ValidationResult.unsupported_keywords`. Open: whether semantic checks become a public API later |
| req-roscale-rendering | [Workbench Rendering](#workbench-rendering) | Implemented | All required sections rendered (provenance, metadata, headline stats, system overview, system implementation, control implementation by friendly family, back matter, JSON fallback). v0 choice: control-family sections default `<details open>` (native browser collapsible). Open: client-side filter/search day one |
| req-roscale-poam-rendering | [POA&M Rendering](#poam-rendering) | Implemented | Action register table + headline stats + JSON fallback. v0 choice: references rendered as plain text per "unresolved references remain visible" branch of ACID-3; active grid-linking deferred. Open: depth of per-item parsing in v0 |
| req-roscale-errors | [Error And Fallback Behavior](#error-and-fallback-behavior) | Implemented | Polished error state shows phase + message + entity-id context; partial sections still render when others fail; JSON fallback included whenever raw content is available |
| req-roscale-vendor | [Vendored OSCAL Assets](#vendored-oscal-assets) | Proposed | Full official schema bundle and public examples under `vendor/`; prior-art and source-boundary discipline documented inline |
| req-roscale-decompose | [Future Grid Decomposition](#future-grid-decomposition) | Backlog | Deep parse-to-grid after the page works. Open: ROSCALE-alone vs. coordinate with a future compliance-core plugin |
| req-roscale-edit | [Future Editing](#future-editing) | Backlog | Editing is deep backburner |

### Plugin Scope
----
RID: `req-roscale-scope`
Status: `Implemented`

ROSCALE is a TAP helper and presentation plugin for OSCAL documents.

In v0 it contributes:

- pure Python OSCAL parsing helpers
- pure Python OSCAL validation helpers
- registered web panel types (SSP and POA&M)
- templates and static assets for the panels
- vendored official OSCAL schemas and public examples for validation/tests
- tests for parser, validation, and panel-facing behavior

In v0 it does not contribute:

- scheduled collectors
- TAP-managed models
- edge types
- bundled GRIFT
- autonomous actions
- editing workflows

Consumers own the page instances that host ROSCALE's panels (through GRIFT or their own page-contribution mechanism). ROSCALE owns all implementation code used by those panels. The initial consumer is the `samsite` plugin — see [`plugins/samsite/specs/spec-samsite-compliance-pages-v0.md`](../../samsite/specs/spec-samsite-compliance-pages-v0.md) for that wiring.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-scope-1 | No Schedule | Implemented | ROSCALE registers no scheduled collector or tap_cares run. | Manifest has no `[grift]`, no models, no schedule; `apps.py` `ready()` registers only panel types |
| req-roscale-scope-2 | Implementation Lives In ROSCALE | Implemented | Parser, validator, panel types, templates, and static assets live in ROSCALE. | `parser.py`, `validator.py`, `panels/`, `templates/roscale/panels/`, `static/roscale/css/` |
| req-roscale-scope-3 | Consumers Own Page GRIFT | Implemented | Consumers contribute the pages and panel instances as GRIFT (or equivalent); ROSCALE ships none. | ROSCALE has no `grift/` dir, manifest has no `[grift]` table. Consumer-side wiring is captured per-consumer (initial: `samsite` plugin's compliance-pages spec) |

### OSCAL SSP Workbench Panel
----
RID: `req-roscale-panel`
Status: `Implemented`

ROSCALE registers a reusable TAP Web panel type: `roscale-oscal-workbench`.

The panel is designed for visual appeal and immediate comprehension. It should feel like a compliance workbench, not a raw JSON browser. The first viewport should make clear what document is being viewed, where it came from, whether it validated, and what the document says about the system.

The panel should be reusable by any consumer plugin that has an OSCAL artifact on the grid. It must not contain consumer-specific branching; FedRAMP-conventional OSCAL fields (FedRAMP profile control IDs, FedRAMP POA&M props, etc.) are recognized when present but are domain conventions inside OSCAL, not consumer-specific.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-panel-1 | Panel Registered | Implemented | ROSCALE registers panel type `roscale-oscal-workbench`. | `panel_type_registry.register(...)` in `apps.py` `ready()` |
| req-roscale-panel-2 | Reusable Panel | Implemented | The panel can be instantiated by any plugin page through a normal Panel node. | No consumer-specific branching in panel code; reads its source through page-variable config |
| req-roscale-panel-3 | Workbench Feel | Implemented | The panel prioritizes summary, grouping, navigation, and readable sections over raw JSON. | Validation strip → provenance → metadata → headline stats → system overview → components/users → controls grouped by friendly family → back matter → JSON fallback (in a closed `<details>`) |

### OSCAL POA&M Workbench Panel
----
RID: `req-roscale-poam-panel`
Status: `Implemented`

ROSCALE registers a second reusable TAP Web panel type: `roscale-oscal-poam-workbench`.

The POA&M panel is separate from the SSP panel because it tells a different story. The SSP is a system/security-plan document. The POA&M is an action and risk register. Keeping a distinct panel type lets the rendering language, headline stats, grouping, and future interactions fit the document rather than forcing one generic OSCAL display to do everything.

OSCAL surface this panel handles:

- root document key: `plan-of-action-and-milestones`
- OSCAL version: `1.1.2` (vendored schema target)
- FedRAMP POA&M conventions are recognized when present (see [OSCAL Validation](#oscal-validation) for the prop names)

The first POA&M experience should "put the pieces on the board": a readable, groupable register of POA&M items with enough summary and provenance to orient the user. More opinionated visual analysis can follow after the first pass is visible.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-poam-panel-1 | Panel Registered | Implemented | ROSCALE registers panel type `roscale-oscal-poam-workbench`. | `panel_type_registry.register(...)` in `apps.py` `ready()` |
| req-roscale-poam-panel-2 | Sibling Panel Types | Implemented | SSP and POA&M are distinct panel types, not a single combined OSCAL display; consumers can host them on separate sibling pages. | Two registered slugs (`roscale-oscal-workbench`, `roscale-oscal-poam-workbench`); each owns its own template, context shape, and rendering language |
| req-roscale-poam-panel-3 | Register First | Implemented | v0 renders a readable POA&M item register before deeper analysis or editing. | Table view with ID/title/status/category/risk/controls/asset/detector/scheduled-completion + description/remediation detail row |

### Panel Input Contract
----
RID: `req-roscale-input`
Status: `Implemented`

The panels read OSCAL artifact entity ids through document-specific page variables. ROSCALE's defaults:

- SSP page variable: `oscal_ssp_artifact_entity_id`
- POA&M page variable: `oscal_poam_artifact_entity_id`

Consumer pages expose these as URL-backed page variables, consistent with the TAP Web page-variable specs. Each panel config only needs to name the variable it reads (the default applies when the config doesn't override it). This keeps the panels reusable and keeps page-level state mapping in the page system where it belongs.

**Latest-emission fallback.** When the URL page variable is empty AND the panel config supplies a `fallback.kind`, the panel resolves the most-recently-fetched `compliance_artifact` node of that kind (sorted by `fetched_at` descending) and renders it, surfacing a "showing latest emission" banner so the user knows they're not on a deep link. Explicit URL entity_id always wins over the fallback. This means a bookmarkable bare-URL view (e.g. `/<consumer>/<page>` with no query string) Just Works for the "current state" case, while specific-emission deep links remain reproducible. The fallback is opt-in — without `fallback.kind` in the config, the panel returns its original "no artifact specified" error when the URL var is empty.

Expected SSP panel config shape:

```json
{
  "artifact_entity_id_var": "oscal_ssp_artifact_entity_id"
}
```

Expected POA&M panel config shape:

```json
{
  "artifact_entity_id_var": "oscal_poam_artifact_entity_id"
}
```

The exact config schema can be refined during implementation, but the principle stands: the panel receives an entity id through an explicit page variable.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-input-1 | Expressive SSP Variable Name | Implemented | The SSP page variable is named `oscal_ssp_artifact_entity_id`. | `DEFAULT_VAR_NAME` in `panels/oscal_workbench/__init__.py` |
| req-roscale-input-2 | Config Names Variable | Implemented | The panel config names the variable to read rather than hardcoding a source. | `config['artifact_entity_id_var']` consulted in `panels/_common.py:resolve_artifact` |
| req-roscale-input-3 | URL Backed | Implemented | Consumer pages expose the variable as URL-backed. | ROSCALE reads `request.GET[var_name]` per the convention; the consumer page is responsible for wiring the URL-backed variable. Confirmed pattern via `panels/_common.py:resolve_artifact` |
| req-roscale-input-4 | Expressive POA&M Variable Name | Implemented | The POA&M page variable is named `oscal_poam_artifact_entity_id`. | `DEFAULT_VAR_NAME` in `panels/oscal_poam_workbench/__init__.py` |
| req-roscale-input-5 | Latest-Emission Fallback | Implemented | When the URL var is empty and `config.fallback.kind` is set, the panel resolves the most-recently-fetched `compliance_artifact` of that kind and surfaces a "showing latest emission" banner. Explicit URL entity_id wins. | `_lookup_latest_by_kind()` + `resolve_artifact()` in `panels/_common.py`; `ArtifactResolution.used_fallback` carries the signal; banner block in both `templates/roscale/panels/*.html` |

### Generous Source Handling
----
RID: `req-roscale-source`
Status: `Implemented`

ROSCALE should be generous in what it accepts.

The panel/parser should accept:

- a `compliance_artifact` entity whose `content` field contains OSCAL JSON
- a node of another entity type whose payload has an OSCAL root
- a raw Python dict containing an OSCAL document
- a JSON string containing an OSCAL document

The preferred source is a `fedramp_20x_ksi.compliance_artifact` node (TAP's convention for fetched compliance documents kept whole). The panel should warn when the source entity type or artifact kind is unexpected, but root OSCAL detection is the actual acceptance gate.

Immediate v0 coverage:

- OSCAL `system-security-plan` documents
- OSCAL `plan-of-action-and-milestones` documents
- OSCAL version targeted: `1.1.2` (vendored schemas)

Future target:

- broader OSCAL document-type detection and handling for the remaining roots (catalog, profile, component-definition, assessment-plan, assessment-results)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-source-1 | Artifact Node Supported | Implemented | The panel can load OSCAL from a `compliance_artifact.content` field. | Duck-typed against `.content`; entity-model import not required by parser |
| req-roscale-source-2 | Raw Dict Supported | Implemented | The parser accepts a raw Python dict in tests and helper use. | |
| req-roscale-source-3 | Raw JSON String Supported | Implemented | The parser accepts a JSON string in tests and helper use. | |
| req-roscale-source-4 | Warnings Not Hard Gating | Implemented | Unexpected entity types or artifact kinds produce warnings rather than hard failure when an OSCAL root is present. | |

### OSCAL Validation
----
RID: `req-roscale-validation`
Status: `Implemented`

ROSCALE provides a pure Python OSCAL validation capability.

Validation is best-effort and layered:

1. JSON parse validation.
2. OSCAL document root detection.
3. Official OSCAL JSON Schema validation using vendored `1.1.2` schemas.
4. TAP-authored semantic checks for display-critical structure.

The first SSP semantic checks should stay small:

- root document is recognized, especially `system-security-plan`
- `metadata` exists
- `metadata.title` and `metadata.oscal-version` are readable when present
- `system-characteristics` can be found for SSP documents
- `control-implementation.implemented-requirements` is a list when present
- implemented requirements have `control-id` where possible
- control families can be derived from `control-id`

The first POA&M semantic checks should also stay small:

- root document is `plan-of-action-and-milestones`
- `metadata` exists
- `poam-items` is a list when present
- each `poam-item` can expose a title/description when present
- FedRAMP POA&M props can be read when present, especially `poam-id`, `status`, `category`, `controls`, `original-risk-rating`, `adjusted-risk-rating`, `asset-identifier`, `weakness-detector-source`, `scheduled-completion-date`, and `remediation-plan-summary`

Schema validation should not be treated as complete OSCAL semantic validation. NIST notes that some OSCAL constraints are not expressible in JSON Schema alone. ROSCALE should report schema errors and semantic warnings separately.

**Implementation note — `pattern` keyword skipped.** OSCAL 1.1.2 schemas use ECMA-262 regex patterns with `\p{...}` Unicode property escapes; Python's stdlib `re` does not support these and raises `re.PatternError`. Rather than add a third-party regex library, the validator skips the `pattern` keyword. The carve-out is disclosed machine-readably via `ValidationResult.unsupported_keywords = ("pattern",)` so the panel and consumers can surface it. Semantic checks compensate for the most display-critical structure `pattern` would have caught (control-id presence, metadata fields, poam-item title/description).

**Open question.** Whether semantic checks become a public API later (importable from outside the plugin). v0 keeps them internal; promote on demand.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-validation-1 | Schema Validation | Implemented | ROSCALE validates against vendored official OSCAL `1.1.2` JSON Schemas where possible. | `pattern` keyword skipped (see Implementation note); surfaced via `unsupported_keywords` |
| req-roscale-validation-2 | Semantic Warnings | Implemented | ROSCALE adds TAP-authored semantic checks for display-critical structure. | SSP + POA&M covered in v0; other roots get schema-only validation |
| req-roscale-validation-3 | Best Effort | Implemented | Validation errors do not block rendering unless the root document is unusable. | Only `root_recognized=False` is hard fail |
| req-roscale-validation-4 | Error Locations | Implemented | Validation and parser errors include useful location/path information when available. | Schema errors carry instance + schema paths; semantic warnings carry document path |
| req-roscale-validation-5 | POA&M Semantic Checks | Implemented | ROSCALE recognizes and validates display-critical POA&M structure. | |

### Workbench Rendering
----
RID: `req-roscale-rendering`
Status: `Implemented`

The first SSP workbench is one large panel. It may use internal sections, sticky navigation, collapsible areas, or tabs as needed, but the panel renders as a single workbench rather than splitting across multiple consumer pages.

The panel should render:

- artifact-node provenance:
  - source URL
  - fetched time
  - signature verification status
  - signer
  - Rekor log index where present
- OSCAL document metadata:
  - title
  - OSCAL version
  - last modified
  - document version
  - remarks
- prominent self-attestation / not-authorized warnings when present
- headline stats:
  - control count by family
  - implementation status counts
  - control origination counts
  - system component count
  - back-matter resource count
  - party count
  - FedRAMP class / impact level when present
- system overview:
  - system name
  - short name
  - description
  - authorization boundary
  - security impact / sensitivity fields
- system implementation:
  - users
  - components
- control implementation:
  - implemented requirements grouped by friendly control family name
  - control id
  - implementation status
  - origination
  - statements/remarks summary
  - evidence/reference links
- back matter:
  - resources and links
- pretty-printed JSON fallback

Control-family display should use friendly names where obvious, for example `AC - Access Control`, while preserving OSCAL-native control ids and field names in parsed data.

**Open questions.** (1) Whether control-family sections render expanded or collapsed by default. (2) Whether the panel includes client-side filtering/search on day one or defers to v1. Decide both during implementation.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-rendering-1 | Provenance Visible | Implemented | Artifact provenance and OSCAL metadata are visible as distinct concepts. | Two separate `<section>` cards in `templates/roscale/panels/oscal_workbench.html` |
| req-roscale-rendering-2 | Validation Strip | Implemented | A compact validation strip shows valid/warning/error state with expandable details. | Color-coded strip at top; clean / warn / error variants; `<details>` block for schema + semantic issue lists |
| req-roscale-rendering-3 | Friendly Families | Implemented | Implemented requirements are grouped by friendly control-family labels. | `constants.NIST_800_53_FAMILIES` + `control_family_label()`; rendered as one `<details open>` per family |
| req-roscale-rendering-4 | Self-Attestation Prominent | Implemented | Self-attested or not-authorized language is surfaced prominently when detected. | `ssp_self_attestation_signal()` scans `metadata.remarks`, `system-characteristics.remarks`, `metadata.title` for "self-attest" / "not authorized" phrases; renders an amber banner above the cards |
| req-roscale-rendering-5 | One Big Page | Implemented | v0 starts as one workbench page rather than split subpages. | All sections stack vertically in one template; collapsible via `<details>` but no separate subpages |

### POA&M Rendering
----
RID: `req-roscale-poam-rendering`
Status: `Implemented`

The POA&M workbench renders the plan of action and milestones as an action register. It should start practical rather than overly clever: put the items on screen, make them groupable and readable, and expose the fields that matter.

The panel should render:

- artifact-node provenance:
  - source URL
  - fetched time
  - signature verification status
  - signer
  - Rekor log index where present
- OSCAL document metadata:
  - title
  - OSCAL version
  - last modified
  - document version
- validation strip with schema/semantic errors and warnings
- headline stats:
  - total POA&M items
  - open vs risk-accepted counts
  - risk rating counts
  - category counts
  - control-family counts
  - detector-source counts
  - due-date / scheduled-completion summary
- a readable POA&M register:
  - POA&M id
  - title
  - status
  - category
  - original and adjusted risk
  - controls
  - asset identifiers
  - detector/source
  - point of contact
  - original detection date
  - scheduled completion date
  - status date
  - remediation summary
  - description
- pretty-printed JSON fallback

Where possible, the POA&M panel should connect references back to the grid. In v0 that means best-effort links/searches, not guaranteed edge creation:

- controls can link/search toward SSP implemented requirements or future control nodes when available
- asset identifiers can link/search toward on-grid resource nodes contributed by other plugins (e.g. an AWS resource collected by `aws_core`) when they resolve cleanly
- detector/source identifiers can remain plain text unless a matching finding or VDR node is discoverable
- unresolved references remain visible as plain text, never hidden

**Open question.** How deep into individual `poam-item` content the v0 register goes. Bias toward shallow per-item rendering (the fields above) with the JSON fallback for full detail; promote individual fields to dedicated UI when use-cases appear.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-poam-rendering-1 | Action Register | Implemented | The POA&M panel renders each `poam-item` as a readable action/risk-register row or card. | Table view with description + remediation detail row beneath each item |
| req-roscale-poam-rendering-2 | Headline Stats | Implemented | The panel shows status, risk, category, control-family, detector-source, and due-date summaries. | `poam_headline_stats()`; summary tiles + breakdown `<details>` block |
| req-roscale-poam-rendering-3 | Best-Effort Grid Links | Implemented | Controls, assets, and findings link/search to grid nodes where they resolve; unresolved references remain visible. | v0 implements the "unresolved references remain visible as plain text" branch; active grid-linking deferred. References never hidden |
| req-roscale-poam-rendering-4 | JSON Fallback | Implemented | The POA&M panel includes the same pretty JSON fallback behavior as the SSP panel. | Shared template pattern; `pretty_json()` helper in `panels/_common.py` |

### Error And Fallback Behavior
----
RID: `req-roscale-errors`
Status: `Implemented`

The panel should fail kindly but visibly.

When parsing, validation, or rendering hits trouble, the panel should:

- show a polished explanation in the panel body
- show the error phase where possible: load, JSON parse, root detection, schema validation, semantic validation, or render
- show location/path details where available
- render any sections it can still understand
- include a pretty-printed JSON fallback when raw content is available

Only truly unusable input should prevent the workbench sections from rendering. Even then, the user should get a useful explanation and a JSON/raw content fallback if possible.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-errors-1 | Polished Errors | Implemented | Parser and validation errors are shown in a user-readable panel state. | Error-state block shows phase (`load` / `json-parse` / `root-detect`), human message, and the requested entity_id + page-variable name |
| req-roscale-errors-2 | Partial Rendering | Implemented | Valid sections render even when other sections have errors or warnings. | Template only suppresses sections whose context is `None`/empty; validation issues render alongside the rest of the workbench rather than blocking it |
| req-roscale-errors-3 | Pretty JSON Fallback | Implemented | Raw OSCAL content can be shown as pretty-printed JSON. | `pretty_json()` helper; rendered inside a closed `<details>` at the bottom; populated even on wrong-root errors so users still see the document |

### Vendored OSCAL Assets
----
RID: `req-roscale-vendor`
Status: `Proposed`

ROSCALE should vendor the complete official OSCAL `1.1.2` JSON Schema bundle and public examples under a provenance-obvious path:

```text
plugins/roscale/vendor/nist/oscal/1.1.2/
```

Public NIST OSCAL examples and any OSCAL documents available from consumer plugins (e.g. the on-grid `compliance_artifact` content) should be used as fixtures. Start with full upstream examples. If fixture volume or churn becomes weird, drop down to a smaller fixture set and record the limitation.

The vendor directory should include a provenance manifest that records:

- upstream repository URL
- upstream release/tag or commit
- fetch date
- license/source status
- which files were vendored

No upstream parser implementation code should be vendored.

#### Prior Art And Source Boundaries

ROSCALE should study open-source OSCAL tooling and examples for shape, terminology, and fixture coverage. It must not copy or lightly adapt parser implementation code into TAP.

Useful prior art:

- NIST OSCAL documentation and release artifacts: <https://pages.nist.gov/OSCAL/>
- NIST OSCAL repository: <https://github.com/usnistgov/OSCAL>
- NIST OSCAL content examples: <https://github.com/usnistgov/oscal-content>
- Compliance Trestle: <https://github.com/oscal-compass/compliance-trestle>

Boundary:

- Upstream examples are acceptable test fixtures.
- Official OSCAL JSON Schemas are acceptable validation assets if vendored with clear provenance.
- Upstream parser code is inspiration only, not an implementation source.
- Parser behavior must be TAP-authored, small, inspectable, and tested against public examples plus consumer-sourced fixtures.

Licensing note: the official NIST OSCAL and `oscal-content` repositories are public-domain / CC0-style sources. Vendoring official schemas and examples is expected to be license-clean with provenance retained. If this changes, remove or replace the vendored assets before implementation.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-vendor-1 | Vendor Path | Implemented | Official assets live under `vendor/nist/oscal/1.1.2/`. | |
| req-roscale-vendor-2 | Complete Schema Bundle | Implemented | The complete `1.1.2` JSON schema bundle is vendored initially. | All 8 schemas (catalog, profile, component, ssp, ap, ar, poam, complete) |
| req-roscale-vendor-3 | Public Examples | Proposed | Public NIST OSCAL examples and on-grid consumer OSCAL documents are used as fixtures. | A consumer-sourced SSP+POA&M pair lives in `tests/fixtures/`; NIST public examples not yet pulled |
| req-roscale-vendor-4 | Provenance Manifest | Implemented | Vendored assets carry a provenance manifest. | `vendor/nist/oscal/1.1.2/PROVENANCE.md` |
| req-roscale-vendor-5 | No Parser Code Vendored | Implemented | Upstream parser implementation code is not vendored or copied. | Only schemas under `vendor/.../schemas/` |
| req-roscale-vendor-6 | TAP-Authored Parser | Implemented | Parser behavior is TAP-authored, small, inspectable, and tested against public examples plus consumer-sourced fixtures. | `parser.py` + `validator.py`; 22 parser/validator tests covering the consumer-sourced SSP+POA&M fixtures |

### Future Grid Decomposition
----
RID: `req-roscale-decompose`
Status: `Backlog`

After the workbench exists, ROSCALE should define how OSCAL documents decompose into first-class grid nodes and edges.

Direction:

- go deep when structure is parseable and queryable
- create dedicated node types rather than jamming structured content into JSON corners
- preserve OSCAL-native field names at first
- use edges for real relationships, such as document-to-section, implemented-requirement-to-component, implemented-requirement-to-evidence, party responsibility, and back-matter references
- avoid modeling low-value or extremely fiddly details until a page/query/user need appears

Candidate future node types:

- `oscal_document`
- `oscal_metadata`
- `oscal_party`
- `oscal_role`
- `oscal_system`
- `oscal_system_component`
- `oscal_implemented_requirement`
- `oscal_statement`
- `oscal_back_matter_resource`
- `oscal_poam_item`
- document-type-specific nodes for POA&M and other OSCAL roots

This is intentionally backlog. The first demand is visibility, not graph normalization.

**Open question.** Whether future ROSCALE grid decomposition should live in ROSCALE alone or coordinate with a broader compliance-core plugin. Decide before starting decomposition work.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-decompose-1 | Backlog Only | Backlog | Full grid decomposition is not required for the first workbench. | |
| req-roscale-decompose-2 | Dedicated Nodes Preferred | Backlog | Future decomposition uses dedicated node types for structured queryable content. | |

### Future Editing
----
RID: `req-roscale-edit`
Status: `Backlog`

Editing OSCAL is the "Edit" in ROSCALE, but it is deep backburner until there is a clear demand signal. Do not design a full editor in v0.

When editing becomes real, the likely path is:

1. Preserve raw OSCAL and parsed structure.
2. Edit one bounded section or field family.
3. Validate with schema and semantic checks.
4. Recompose a full OSCAL document.
5. Compare original vs generated output.
6. Only then consider broad authoring workflows.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-roscale-edit-1 | Deferred | Backlog | v0 does not include OSCAL editing. | |
