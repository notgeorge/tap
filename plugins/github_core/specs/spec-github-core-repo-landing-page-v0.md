# GitHub Core Repo Landing Page Specification

## Philosophy

This spec defines the **one-page-per-repository landing page** that surfaces
everything worth saying about a collected GitHub repository on the TAP grid.
It is the first concrete "mapping the tao" page for `github_core`: take a
complicated ecosystem (GitHub Actions deployment plumbing), collect its data
into typed nodes and edges, and surface exactly what an operator needs to
see — identity, recent activity, deploy health, what's defined, what's
connected downstream — in a single pane of glass.

The spec is feature-scoped, not platform-generic. The page is a github_core
contribution; the panel types it hosts also live in github_core. Future
refactors may lift individual panel types into shared platform machinery
once a second consumer appears (see `feedback_panel_latest_emission_fallback_pattern`
for the established lift-on-third-use discipline).

The Sam-demo arc is the v0 driver: when an operator navigates to the page
for `notgeorge/samsite`, they should recognize their own deploys, see the
workflows that gate them, and — once `aws_core` has landed data on the
grid — see the cross-system links that prove TAP is stitching ecosystems
rather than storing two silos.

## Story Sentence

> **"This is *<repo>*'s GitHub side: who deploys it, what's running, whether
> it stays green, and what it touches downstream in AWS."**

Every panel earns its place by advancing that plot in reading order. Panels
that do not advance the plot do not appear on the v0 page — see
`req-github-core-repo-page-nongoals` for the explicit cutting-room floor.

## Page Identity

- **Route:** `/github_core/repo`
- **Page variable:** `repository_entity_id` (URL-backed; the resolved
  `github_repository` node's `entity_id` UUID)
- **Canonical deep link:** `/github_core/repo?repository_entity_id=<entity_id>`
- **Page dimensions:** `github.platform = "github.com"` always; per-repo
  scoping comes from the resolved repository node's `github.owner` and
  `github.repo` dimensions, not page-level

## Goals

|   | Goal | Description |
| :---: | --- | --- |
| 1. | Story-Driven | Panels appear in story order (identity → activity → health → catalog → cross-system → history) and any panel that doesn't advance the story is dropped. |
| 2. | Repo-Parameterized | A single page route serves every collected repository; the resolved repo comes from a URL-backed page variable so deep links reproduce exactly what the user saw. |
| 3. | Empty-State Honest | Panels that depend on data not yet on the grid (e.g., cross-grid links before `aws_core` runs) show explicit empty states with the actionable next step, not blank space. |
| 4. | Holy-Shit Demo Moment | The cross-grid references panel is the v0 demo payoff — the moment AWS data lands, that panel lights up with a real `REFERENCES_RESOURCE` edge, proving the link manifest stitched two siloed datasets. |
| 5. | History-Aware | The page surfaces (at least) the count of workflow-definition changes via `HistoricalGithubWorkflow`, anchoring the broader history/FLIP demo moment. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-github-core-repo-page-route | [Page Route + Page Variable](#page-route--page-variable) | Implemented | `/github_core/repo` + `repository_entity_id` URL-backed page variable |
| req-github-core-repo-page-resolution | [Entity Resolution](#entity-resolution) | Implemented | Page variable resolves to a `github_repository` node; latest-by-`entity__updated_at` fallback when absent |
| req-github-core-repo-page-hero | [Repo Hero Panel](#repo-hero-panel) | Implemented | `github-repo-hero` panel type; identity strip across top |
| req-github-core-repo-page-activity | [Recent Activity Panel](#recent-activity-panel) | Implemented | `github-recent-activity` panel type; last N runs ordered by run_started_at |
| req-github-core-repo-page-health | [Deploy Health Panel](#deploy-health-panel) | Implemented | `github-deploy-health` panel type; per-workflow sparkline scoreboard |
| req-github-core-repo-page-catalog | [Workflow Catalog Panel](#workflow-catalog-panel) | Implemented | `github-workflow-catalog` panel type; list + click-to-expand parsed config |
| req-github-core-repo-page-cross-grid | [Cross-Grid References Panel](#cross-grid-references-panel) | Implemented | Outbound REFERENCES_RESOURCE edges grouped by target type; OIDC link verified end-to-end against samsite + AWS |
| req-github-core-repo-page-history | [History Strip Panel](#history-strip-panel) | Implemented | History row count + latest change implemented; optional cadence line still pending |
| req-github-core-repo-page-layout | [Page Layout](#page-layout) | Implemented | Vertical reading order implemented; paired activity-health row deferred (currently single-column stack) |
| req-github-core-repo-page-nav | [Navigation Discoverability](#navigation-discoverability) | Implemented | Deferred — page reachable via URL only for v0; nav-link card is a small follow-up |
| req-github-core-repo-page-grift | [GRIFT Layout](#grift-layout) | Implemented | `plugins/github_core/grift/repo-landing-page.grift.json` declares page + six panel instances + six USES_PANEL edges |
| req-github-core-repo-page-nongoals | [v0 Non-Goals](#v0-non-goals) | Implemented | Non-goal boundaries hold in shipped v0 |

### Page Route + Page Variable
----
RID: `req-github-core-repo-page-route`
Status: `Implemented`

The page is mounted at the fixed route `/github_core/repo`. It is
**repository-parameterized** rather than path-namespaced (no
`/github_core/<owner>/<repo>` route), because TAP's v0 page-variable
machinery is URL-query-backed and the `github_repository.entity_id` is a
stable UUID that survives renames.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-route-1 | Fixed Route | Implemented | A GRIFT-declared `page` node has route `/github_core/repo`. | |
| req-github-core-repo-page-route-2 | URL-Backed Page Variable | Implemented | The page declares a `repository_entity_id` page variable bound to the URL's `?repository_entity_id=<uuid>` query parameter. | UUID type; format-checked at resolution time. |
| req-github-core-repo-page-route-3 | Deep Link Reproducible | Implemented | A page URL with `repository_entity_id` set deterministically reproduces the same panel contents on any session for the same grid state. | All panels read the same resolved entity. |

### Entity Resolution
----
RID: `req-github-core-repo-page-resolution`
Status: `Implemented`

Every panel on this page consumes a single resolved entity: the
`github_repository` node whose `entity_id` matches the `repository_entity_id`
page variable. Resolution rides on `tap_web/specs/spec-web-panel-entity-resolution-v0.md`
— the platform panel-entity-resolution surface.

A v0 fallback is required so the page is reachable without already knowing
an entity_id: when `repository_entity_id` is absent, resolve to the
most-recently-collected `github_repository` node (latest-by-updated_at).
This mirrors the `config.fallback.kind` pattern called out in
`feedback_panel_latest_emission_fallback_pattern`. The samsite demo path
relies on this — the operator navigates to `/github_core/repo` from a nav
link and lands on samsite's repo automatically.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-resolution-1 | Explicit Resolution | Implemented | When `repository_entity_id` is supplied, panels load data scoped to that exact `github_repository` node. | |
| req-github-core-repo-page-resolution-2 | Fallback To Latest | Implemented | When `repository_entity_id` is absent, the page resolves to the most-recently-collected `github_repository` node (latest `updated_at`). | Uses the `config.fallback.kind` pattern; if zero repos exist, surfaces an empty-state with a pointer to running the collector. |
| req-github-core-repo-page-resolution-3 | Missing Repo Empty State | Implemented | If `repository_entity_id` is supplied but the entity does not exist on the grid, all panels render a unified "repository not found" empty state with the supplied entity id. | No silent fallback in this case; the operator gave us a specific id. |

### Repo Hero Panel
----
RID: `req-github-core-repo-page-hero`
Status: `Implemented`

A horizontal strip across the top of the page. The single anchor that says
"you're in the right place."

Panel type slug: `github-repo-hero`. v0 ships one panel-instance with no
configuration beyond the resolved repository entity.

Surface:

- `full_name` — large, primary identifier
- `default_branch`, `visibility` — secondary labels
- `owner_login` — links to the owner's `github_account` node (clickable if
  a panel/page for that exists; plain label otherwise)
- `html_url` — link out to GitHub
- "Last collected: <age>" — derived from `updated_at` on the entity row,
  formatted as a relative duration

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-hero-1 | Identity Fields Shown | Implemented | The panel shows `full_name`, `default_branch`, `visibility`, `owner_login`, and an `html_url` link-out. | |
| req-github-core-repo-page-hero-2 | Last-Collected Age | Implemented | The panel shows a relative duration derived from the entity's `updated_at`. | Operator sees freshness at-a-glance. |
| req-github-core-repo-page-hero-3 | Anchor Position | Implemented | The panel is the first vertical slot on the page. | Hero strip; full width. |

### Recent Activity Panel
----
RID: `req-github-core-repo-page-activity`
Status: `Implemented`

A chronological list of the most recent workflow runs for the resolved
repository. The headline "those are my deploys" moment.

Panel type slug: `github-recent-activity`.

Surface (one row per run, latest first):

- Run number (`#NNN`), workflow name (joined via `EXECUTES_WORKFLOW`)
- Trigger event (`push`, `pull_request`, `workflow_dispatch`, …)
- Status pill: success / failure / in_progress / cancelled / skipped, color-coded
- Short head_sha (first 8 chars), branch
- Relative age from `run_started_at`
- Duration if terminal
- Click row → drill into the run's page (future) or link out to GitHub for now

Default limit: 10. Configurable per panel-instance.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-activity-1 | Ordered By Latest | Implemented | Rows are sorted by `github_actions_run.run_started_at` descending. | |
| req-github-core-repo-page-activity-2 | Workflow Name Joined | Implemented | Each row shows the parent `github_workflow.name` resolved via the run's `EXECUTES_WORKFLOW` edge. | |
| req-github-core-repo-page-activity-3 | Status Pill Vocabulary | Implemented | Each row's status pill maps GitHub's `status` + `conclusion` fields to a stable visual vocabulary: in-progress, success, failure, cancelled, skipped, neutral, timed_out. | Cross-attempt aggregation deferred per `req-github-core-backlog-run-attempts`. |
| req-github-core-repo-page-activity-4 | Configurable Limit | Implemented | The panel's `config.limit` controls how many rows appear. Default `10`. Maximum bounded so the panel cannot accidentally render thousands. | Maximum: 100 in v0. |
| req-github-core-repo-page-activity-5 | Empty State | Implemented | When the repository has zero collected runs, the panel renders an explicit "no runs collected yet" state. | Not blank. |

### Deploy Health Panel
----
RID: `req-github-core-repo-page-health`
Status: `Implemented`

A compact per-workflow scoreboard: at-a-glance "are we shipping clean?"

Panel type slug: `github-deploy-health`.

Surface (one row per `github_workflow` defined on the repo):

- Workflow name
- A horizontal strip of N small colored boxes representing the latest N
  runs of that workflow (default N=30), oldest-left, newest-right
- Box color follows the same status vocabulary as
  `req-github-core-repo-page-activity-3`
- Trailing summary: "X/N success" count

Workflows with zero runs render an explicit "no runs" row (kept visible to
make absence legible).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-health-1 | Per-Workflow Row | Implemented | Each workflow defined on the repo (`DEFINES_WORKFLOW` outbound) renders one row in the scoreboard. | |
| req-github-core-repo-page-health-2 | Shared Status Vocabulary | Implemented | Box color uses the same vocabulary as the recent-activity panel. | Single source of truth for status colors in this plugin. |
| req-github-core-repo-page-health-3 | Configurable Window | Implemented | The window size N is configurable per panel-instance. Default `30`. | |
| req-github-core-repo-page-health-4 | No-Run Workflow Visible | Implemented | A workflow defined on the repo but with zero collected runs renders an explicit "no runs" row, not omitted. | Absence is legible. |

### Workflow Catalog Panel
----
RID: `req-github-core-repo-page-catalog`
Status: `Implemented`

What's defined to run on this repo, with an expand-to-see-detail affordance
for the deploy-relevant fields parsed from each workflow's YAML.

Panel type slug: `github-workflow-catalog`.

Surface (one row per `github_workflow` defined on the repo):

- Collapsed row: `name · path · state · last conclusion · last run age`
- Click row → expand inline to show:
  - Parsed triggers (`configuration.triggers`)
  - Parsed top-level permissions (`configuration.permissions`)
  - Per-job summary: `id · name · runs_on · needs · uses`
  - A "show raw YAML" toggle that reveals `configuration.raw_yaml` inline
    (or in a modal — leave to panel implementation)

v0 default expansion: the most-recently-run workflow expands automatically
on first load. Other workflows collapsed.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-catalog-1 | Per-Workflow Row | Implemented | Each `github_workflow` reachable via the repo's `DEFINES_WORKFLOW` edges renders one collapsed row. | |
| req-github-core-repo-page-catalog-2 | Expanded Parsed Detail | Implemented | The expanded view surfaces parsed triggers, permissions, and per-job summary fields from `configuration`. | Pulled from already-parsed fields; no client-side YAML parsing. |
| req-github-core-repo-page-catalog-3 | Raw YAML Toggle | Implemented | The expanded view exposes a toggle that reveals `configuration.raw_yaml` inline. | Workflows with empty `raw_yaml` (e.g. GitHub's dependabot pseudo-workflow) disable the toggle with a tooltip. |
| req-github-core-repo-page-catalog-4 | Default Expansion | Implemented | On first page load, the workflow with the most recent run is expanded; others collapsed. | Single-expand at a time — clicking another collapses the current. |

### Cross-Grid References Panel
----
RID: `req-github-core-repo-page-cross-grid`
Status: `Implemented`

**The "mapping the tao" payoff panel.** Shows outbound `REFERENCES_RESOURCE`
edges from the resolved repository's own nodes (the repo, its workflows,
its runs, its jobs), grouped by target entity type.

Panel type slug: `github-cross-grid-references`.

Surface:

- One group per distinct target entity type (e.g. `aws_iam_oidc_provider`,
  `aws_route53_zone`, `aws_cloudfront_distribution`)
- Per group: type icon + label + count, expandable into a list of target
  node display names with click-through to the target's own page (when one
  exists; plain label otherwise)
- Each row also shows the link-rule name + the matched value (from the
  edge's `properties.link_rule` and `properties.matched_value`) so the
  operator can see why the link exists
- Empty state: when there are zero outbound `REFERENCES_RESOURCE` edges
  from any of this repo's nodes, render an explicit "0 cross-grid links yet"
  panel with the actionable next step: *"Run an `aws_core` collection
  against the AWS account this repo's workflows deploy to, then re-run the
  `github_core` collector to enrich."*

The empty-to-populated transition is the demo arc: on first load samsite's
page shows zero links; after `aws_core` lands its first batch and the
`github_core` collector re-runs the enrichment phase, the panel populates.
That transition is itself a demo moment.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-cross-grid-1 | Outbound REFERENCES_RESOURCE Aggregation | Implemented | The panel collects `REFERENCES_RESOURCE` edges whose source is the resolved repository OR any of its workflows / runs / jobs. | Source-side scoping by `full_name` on each model. |
| req-github-core-repo-page-cross-grid-2 | Grouped By Target Type | Implemented | Edges are grouped by `target.entity_type`; each group renders as a labeled section with a count. | |
| req-github-core-repo-page-cross-grid-3 | Link-Rule Surfacing | Implemented | Each row shows the `properties.link_rule` name and `properties.matched_value` from the edge envelope. | Operator sees why the link was emitted. |
| req-github-core-repo-page-cross-grid-4 | Actionable Empty State | Implemented | When zero cross-grid edges exist, the panel renders an explicit empty state naming the next collector run that would populate it. | Demo arc relies on this transition being legible. |

### History Strip Panel
----
RID: `req-github-core-repo-page-history`
Status: `Proposed`

A compact strip surfacing the "this is honest-to-god audit evidence" demo
moment, scoped to the resolved repo's workflows.

Panel type slug: `github-history-strip`.

Surface:

- Total `HistoricalGithubWorkflow` row count for workflows in this repo
- Most-recent workflow-definition change: workflow name + timestamp +
  click-through to a per-workflow diff view (the diff view itself is
  future panel work; v0 may stub the click target as the workflow's
  GitHub URL)
- Optional: "X observation cycles in the last 7 days" as a freshness/cadence
  signal

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-history-1 | Workflow Change Count | Implemented | The panel shows the total count of `HistoricalGithubWorkflow` rows for workflows defined on this repo. | |
| req-github-core-repo-page-history-2 | Latest Change Surface | Implemented | The panel highlights the most-recent workflow-definition change (workflow name + timestamp). | Click target may be a stub (GitHub URL) in v0; per-workflow diff page is future work. |
| req-github-core-repo-page-history-3 | Optional Cadence Line | Proposed | The panel may show "X observation cycles in the last N days" derived from history rows across all of this repo's nodes. | Optional; not in v0. |

### Page Layout
----
RID: `req-github-core-repo-page-layout`
Status: `Proposed`

Top-to-bottom vertical reading order. The activity + health panels share a
single horizontal row because they are story-adjacent (both are "what just
happened, were we okay") and benefit from side-by-side reading. Every other
panel takes the full page width.

```
+--------------------------------------------------+
|                   1. Hero                        |
+-------------------------+------------------------+
|                         |                        |
|   2. Recent Activity    |   3. Deploy Health     |
|                         |                        |
+-------------------------+------------------------+
|              4. Workflow Catalog                 |
+--------------------------------------------------+
|         5. Cross-Grid References                 |
+--------------------------------------------------+
|             6. History Strip                     |
+--------------------------------------------------+
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-layout-1 | Vertical Reading Order | Implemented | Panels appear in the documented story order on every render. | Hero → (Activity + Health row) → Catalog → Cross-Grid → History. |
| req-github-core-repo-page-layout-2 | Paired Activity-Health Row | Proposed | The recent-activity and deploy-health panels share a horizontal row, side-by-side on viewports wide enough; they stack vertically on narrow viewports. | v0 ships single-column vertical stack; pair-row requires extending the page layout grammar (nested columns) and is a follow-up. |

### Navigation Discoverability
----
RID: `req-github-core-repo-page-nav`
Status: `Proposed`

The page must be reachable from at least one existing navigation surface so
the demo path doesn't depend on the operator typing a URL. For v0 the
simplest hook is a samsite nav-link entry pointing at
`/github_core/repo?repository_entity_id=<samsite's entity_id>`, declared in
the existing samsite nav-links GRIFT.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-nav-1 | Reachable From Nav | Proposed | At least one nav-link card exists somewhere in TAP Web that opens this page (with `repository_entity_id` pre-filled for v0's single repo). | Deferred — page reachable via URL only in v0; nav-link card is a small follow-up once a natural host page is picked. |

### GRIFT Layout
----
RID: `req-github-core-repo-page-grift`
Status: `Implemented`

The page and its panel instances are declared as a single GRIFT batch:
`plugins/github_core/grift/repo-landing-page.grift.json`. The batch creates
one `page` node and six `panel` nodes connected via `USES_PANEL` edges.
Panel-type slugs (`github-repo-hero` etc.) MUST be registered by the
github_core plugin's tap-plugin.toml before this GRIFT can import.

The GRIFT file is referenced from the plugin's `tap-plugin.toml` `[grift]`
table and validated against `grift-document.schema.json` at load.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-grift-1 | Single GRIFT Batch | Implemented | The page + all six panel instances + all `USES_PANEL` edges land via one GRIFT batch. | |
| req-github-core-repo-page-grift-2 | Manifest-Declared | Implemented | The GRIFT file is declared in `plugins/github_core/tap-plugin.toml` under `[grift]`. | |
| req-github-core-repo-page-grift-3 | Stable Entity Ids | Implemented | Page and panel entity_ids are stable values authored as literal strings in the GRIFT JSON so re-import upserts in place. | UUIDv7 minted once via `scripts/uuid7` and recorded in the JSON. UUIDv5-from-natural-key is the convention for collected entities (see `plugins/github_core/collectors/github_collector/identity.py`); hardcoded page/panel ids are authored, not collected, so UUIDv7 is the right shape. |
| req-github-core-repo-page-grift-4 | Schema Validates | Implemented | The GRIFT batch passes `grift-document.schema.json` validation at load. | |

### v0 Non-Goals
----
RID: `req-github-core-repo-page-nongoals`
Status: `Implemented`

Out of scope for v0 of this page:

- **Per-job step detail panel** — drill-down, not landing. Future per-run
  page may host this.
- **Self-hosted runners panel** — samsite has zero `github_runner` nodes;
  panel would be noise. Once a repo with non-zero runners is collected,
  consider adding a conditional runner panel.
- **Per-run page** — clicking into a run from the activity panel currently
  links out to GitHub; a TAP-native per-run page is future work.
- **Per-workflow diff page** — the history strip's "latest change" click
  target may stub to the workflow's GitHub URL in v0.
- **Secret-ref / variable panels** — those models are deferred entirely
  per `req-github-core-backlog-references`.
- **Multi-attempt run rendering** — v0 collects only the latest attempt per
  `req-github-core-collector-8`; multi-attempt visualization is deferred
  with the underlying model work in `req-github-core-backlog-run-attempts`.
- **Multi-repo aggregate landing** — this spec is per-repo. A
  "samsite's GitHub footprint" or "every repo on the grid" page is a
  different page with different panels; not v0.
- **Editable affordances** — the page is read-only. Any "modify the
  workflow" or "trigger a run" interaction is out of scope.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-repo-page-nongoals-1 | Drill-Down Deferred | Implemented | Per-run and per-job pages are not v0. | |
| req-github-core-repo-page-nongoals-2 | Conditional Panels Deferred | Implemented | Self-hosted runner and secret/variable panels are not in v0. | |
| req-github-core-repo-page-nongoals-3 | Read-Only | Implemented | The page is strictly read-only; no edit affordances. | |

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`,
`Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`,
`Backlog`.
