# GitHub Core Pre-Plugin Specification

## Philosophy

`github_core` will model the GitHub side of the samsite deployment on the TAP
grid. The v0 target is deliberately narrow: make the plumbing from repository
content to live site visible for `notgeorge/samsite`, especially GitHub Actions
workflows, workflow runs, jobs, runners, variables, and secret references.

This is not a full GitHub inventory product. Broad repository introspection,
organization-wide governance, issue/PR modeling, permissions audits, Sigstore,
and Rekor all remain future work. v0 exists because the Sam demo needs to show
how the static site and compliance machinery move through GitHub Actions into
the running AWS-backed site.

This is a **pre-plugin** spec. It lives at the root while the plugin is still
being designed. When `github_core` is scaffolded, this content should move to
`plugins/github_core/specs/spec-github-core-v0.md` and the root pre-plugin file
should be removed or reduced to a pointer.

## Roadmap Alignment

Governing step: `step-rampart-sam-demo` in `plan/road-rampart.md`.

This work directly supports the active Done-Test by making Sam's reproduced
deployment legible as a connected system: GitHub repo -> workflow -> run -> job
-> runner -> referenced AWS resources. The minimum useful version is a collector
that populates the graph for `notgeorge/samsite`; everything else is deferred.

## Prior Art

Cartography's GitHub Actions module models workflows, environments, actions,
secrets, variables, and parsed workflow content as graph data. The useful
pattern for TAP is: fetch API resources, parse workflow YAML for permissions /
references, transform into typed graph objects, and preserve source payloads.
TAP does not copy Cartography's per-loader implementation or Neo4j schema; the
collector is clean-room and GRIFT-based.

CloudQuery and Steampipe both expose broad GitHub table/plugin surfaces. They
confirm the mainstream inventory categories: repositories, Actions workflows,
runs/jobs, self-hosted runners, repository variables, and repository secrets.
They also show the scope cliff. TAP v0 intentionally avoids their full table
surface and takes only the Actions plumbing path needed for samsite.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Plumbing-Visible | Show the path from repo content to GitHub Actions execution and referenced deployment resources. |
| 2. | Collector-Driven | Populate GitHub state through a `tap_cares` collector that emits GRIFT batches. |
| 3. | Manifest-Declared | Keep API/file collection and grid-link resolution declarative enough to inspect without reading collector code. |
| 4. | Scoped | Target `notgeorge/samsite` first; defer full GitHub account introspection. |
| 5. | Dimensioned | Use GitHub-specific dimensions so the GitHub platform can be sliced as its own environment. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-github-core-scope | [Plugin Scope](#plugin-scope) | Proposed | v0 is GitHub Actions deployment plumbing for `notgeorge/samsite` |
| req-github-core-models | [Model Set](#model-set) | Proposed | Account, repo, workflow, run, job, runner, variable, secret-ref |
| req-github-core-edges | [Edge Vocabulary](#edge-vocabulary) | Proposed | Repo/workflow/run/job/runner/reference spine plus conservative AWS links |
| req-github-core-dimensions | [Dimension Strategy](#dimension-strategy) | Proposed | GitHub-specific flat dimensions |
| req-github-core-secret | [PAT Secret Kind](#pat-secret-kind) | Proposed | `github_pat` data shape and collector knobs |
| req-github-core-collector | [Collector Runtime](#collector-runtime) | Proposed | `CollectorBase`, first run latest 10, later incremental |
| req-github-core-manifests | [Collection And Link Manifests](#collection-and-link-manifests) | Proposed | Separate API/file manifest and grid-link manifest |
| req-github-core-workflow-parse | [Workflow File Parsing](#workflow-file-parsing) | Proposed | PyYAML, workflow-only v0, warn on deferred local/composite actions |
| req-github-core-runner | [Runner Semantics](#runner-semantics) | Proposed | Durable self-hosted runner config when visible; job observations always |
| req-github-core-grid-links | [Existing Grid Links](#existing-grid-links) | Proposed | Exact unambiguous links to AWS nodes through Search/Gryphon |
| req-github-core-python-deps | [Plugin Python Dependency](#plugin-python-dependency) | Proposed | `PyYAML` is plugin-owned; activates plugin-local dependency shape |
| req-github-core-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Full GitHub inventory, Sigstore/Rekor, deletion/reaping, schedules |

### Plugin Scope
----
RID: `req-github-core-scope`
Status: `Proposed`

`github_core` models GitHub platform objects that matter to deployment and
compliance plumbing. v0 targets `notgeorge/samsite` and does not attempt to
inventory every repository, organization setting, issue, pull request, or
permission surface.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-scope-1 | Target Repo | Proposed | The v0 collector target is configured as `notgeorge/samsite`. | Via the `github_pat` secret `repos` array. |
| req-github-core-scope-2 | Actions Plumbing Focus | Proposed | v0 focuses on repository, workflow, run, job, runner, variable, and secret-reference data needed to explain deployment flow. | |
| req-github-core-scope-3 | No Broad Introspection | Proposed | Full GitHub account/org/repo introspection is deferred. | |

### Model Set
----
RID: `req-github-core-models`
Status: `Proposed`

The v0 model set is intentionally small but node-granular. Values that deserve
identity, edges, queryability, history, and graph-visible lifecycle become
dedicated node types rather than being jammed into workflow JSON.

Models:

- `github_account` — owner/user/org account.
- `github_repository` — repository shell; v0 only needs enough fields to show it exists and anchor Actions objects.
- `github_workflow` — workflow definition discovered from GitHub Actions API and parsed workflow file content.
- `github_actions_run` — one workflow run attempt.
- `github_actions_job` — one job within a workflow run. Step details live in `configuration` in v0.
- `github_runner` — durable registered self-hosted runner configuration when visible through the API.
- `github_actions_variable` — repository Actions variables, including non-secret values.
- `github_actions_secret_ref` — referenced secret names parsed from workflows/jobs; values are never available and never stored.

#### Identity

Natural-key inputs:

| Model | Natural Key |
| --- | --- |
| `github_account` | account login or GitHub numeric id |
| `github_repository` | `owner/repo` |
| `github_workflow` | `owner/repo` + workflow id/path |
| `github_actions_run` | `owner/repo` + run id + run attempt |
| `github_actions_job` | `owner/repo` + job id |
| `github_runner` | `owner/repo` + runner id for durable registered runners |
| `github_actions_variable` | `owner/repo` + variable scope + name |
| `github_actions_secret_ref` | `owner/repo` + secret scope + name |

Entity IDs are deterministic UUIDv5 values over the model type and natural key.
Runs include `run_attempt` so re-run attempts remain distinct observations.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-models-1 | V0 Models Declared | Proposed | The plugin declares the eight v0 model types listed above. | |
| req-github-core-models-2 | Dedicated Secret Ref Node | Proposed | Referenced secret names become `github_actions_secret_ref` nodes; secret values are never collected. | |
| req-github-core-models-3 | Job Steps Blobbed | Proposed | Workflow job steps remain structured data in `github_actions_job.configuration` in v0. | Future visualization target. |
| req-github-core-models-4 | Deterministic Identity | Proposed | Every model uses deterministic UUIDv5 identity based on the natural keys above. | |

### Edge Vocabulary
----
RID: `req-github-core-edges`
Status: `Proposed`

Edges express the GitHub Actions execution spine and dependency references.

V0 edge types:

| Edge | Direction | Meaning |
| --- | --- | --- |
| `OWNS_REPO` | `github_account` -> `github_repository` | Account owns repo. |
| `DEFINES_WORKFLOW` | `github_repository` -> `github_workflow` | Repo contains workflow definition. |
| `EXECUTES_WORKFLOW` | `github_actions_run` -> `github_workflow` | Run executes workflow. |
| `HAS_JOB` | `github_actions_run` -> `github_actions_job` | Run contains job. |
| `RUNS_ON` | `github_actions_job` -> `github_runner` | Job ran on a durable runner node when matchable. |
| `REFERENCES_SECRET` | workflow/job -> `github_actions_secret_ref` | Workflow/job references a secret by name. |
| `REFERENCES_VARIABLE` | workflow/job -> `github_actions_variable` | Workflow/job references a variable. |
| `REFERENCES_RESOURCE` | GitHub node -> external grid node | Conservative exact-match link to existing AWS nodes. |

`REFERENCES_RESOURCE` is intentionally conservative. It means "this GitHub
plumbing names or depends on this resource" and does not claim deployment,
ownership, or runtime control.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-edges-1 | Execution Spine | Proposed | The repo/workflow/run/job/runner edges are declared and constrained. | |
| req-github-core-edges-2 | Reference Edges | Proposed | Secret, variable, and resource references use explicit edge types. | |
| req-github-core-edges-3 | Conservative Resource Semantics | Proposed | `REFERENCES_RESOURCE` is used only for exact, unambiguous matches and does not overstate deployment semantics. | |

### Dimension Strategy
----
RID: `req-github-core-dimensions`
Status: `Proposed`

GitHub is treated as its own platform environment. The plugin uses flat,
GitHub-specific dimensions:

| Key | Example | Applies To |
| --- | --- | --- |
| `github.platform` | `github.com` | All GitHub nodes and edges |
| `github.owner` | `notgeorge` | Repo-scoped nodes and edges |
| `github.repo` | `samsite` | Repo-scoped nodes and edges |
| `github.surface` | `actions` | Actions workflows, runs, jobs, runners, variables, secret refs |
| `github.observation` | `execution` | Runs and jobs |

Static model defaults should include only dimensions that are true for all
instances, such as `github.platform = "github.com"`. The collector supplies
repo-specific dimensions in GRIFT envelopes.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-dimensions-1 | GitHub Platform Dimension | Proposed | All plugin-owned nodes and edges carry `github.platform = "github.com"`. | |
| req-github-core-dimensions-2 | Repo Scope Dimensions | Proposed | Collector-created repo-scoped objects carry `github.owner` and `github.repo`. | |
| req-github-core-dimensions-3 | Actions Surface Dimension | Proposed | Actions-related objects carry `github.surface = "actions"`. | |
| req-github-core-dimensions-4 | Execution Observation Dimension | Proposed | Run and job observations carry `github.observation = "execution"`. | |

### PAT Secret Kind
----
RID: `req-github-core-secret`
Status: `Proposed`

The first credential mode is a Personal Access Token. `github_core` owns the
`github_pat` secret kind data schema and validates it consumer-side via
`tap_cares` `require_secret_kind(..., data_schema=...)`.

Data fields:

| Field | Required | Default | Meaning |
| --- | :---: | --- | --- |
| `token` | Yes |  | GitHub PAT. Secret material; never logged or stored on grid. |
| `api_base_url` | No | `https://api.github.com` | GitHub API base URL. |
| `repos` | Yes |  | Array of `owner/repo` targets; v0 example is `["notgeorge/samsite"]`. |
| `initial_run_limit` | No | `10` | Number of latest workflow runs to seed on first collection. |
| `collect_runner_config` | No | `true` | Attempt durable registered runner collection. |
| `collect_variables` | No | `true` | Collect repository Actions variable names and values. |
| `collect_workflow_files` | No | `true` | Fetch and parse workflow YAML files. |
| `collect_grid_links` | No | `true` | Attempt conservative links to existing grid entities. |

GitHub App authentication is future work.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-secret-1 | PAT First | Proposed | v0 supports `github_pat` as the first and only credential kind. | |
| req-github-core-secret-2 | Plugin Owns Schema | Proposed | `github_core` ships and validates the `github_pat` JSON Schema. | |
| req-github-core-secret-3 | Repo Array Scope | Proposed | The secret carries the repo target list as `data.repos`. | |
| req-github-core-secret-4 | GitHub App Deferred | Proposed | GitHub App auth is deferred. | |

### Collector Runtime
----
RID: `req-github-core-collector`
Status: `Proposed`

The collector is a standard `CollectorBase` subclass registered by
`github_core`. It resolves one `github_pat` secret, validates its shape, fetches
GitHub data for each configured repo, assembles one GRIFT batch per run, and
submits via `CollectorBase.submit_grift`.

Collection policy:

- First population per repo collects the latest `initial_run_limit` workflow runs.
- Later runs collect workflow runs created since the latest
  `github_actions_run.created_at` already on the grid for that repo.
- The collector always refreshes previously non-terminal runs/jobs until they
  reach a terminal state.
- Runner-config collection degrades with a structured warning on permission
  failure; workflows/runs/jobs still collect.
- Missing repo/workflow/run access fails the run visibly.
- Runs and jobs are historical observations. v0 has no deletion/reaping:
  absence from a future GitHub response never deletes a node.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-collector-1 | CollectorBase | Proposed | The collector subclasses `CollectorBase` and uses the normal `tap_cares` runtime. | |
| req-github-core-collector-2 | First Run Seeds Ten | Proposed | Initial collection defaults to the latest 10 runs per repo. | Configurable by secret. |
| req-github-core-collector-3 | Incremental Later Runs | Proposed | Later runs collect runs created since the latest on-grid run for the repo. | |
| req-github-core-collector-4 | Non-Terminal Refresh | Proposed | Non-terminal prior runs/jobs are refreshed on each run. | |
| req-github-core-collector-5 | Runner Permission Degrades | Proposed | Runner-config permission failures record warnings and do not abort run/job collection. | |
| req-github-core-collector-6 | No Deletion Semantics | Proposed | v0 never deletes GitHub nodes based on absence from API responses. | |

### Collection And Link Manifests
----
RID: `req-github-core-manifests`
Status: `Proposed`

The collector uses two declarative JSON manifests, both schema-validated at
load. Invalid manifests fail the run visibly.

`github_collection_manifest.json` declares GitHub sources: REST endpoints,
workflow file fetches, item paths, target entity types, projected fields, and
edge rules within the GitHub graph. The source primitive set may include:

- `rest_endpoint`
- `repo_file`
- `custom_fn`

`github_grid_link_manifest.json` declares conservative cross-plugin link rules:
which collected GitHub fields or parsed variable values may be matched against
which existing TAP entity types and fields, and which edge type to emit on exact
unambiguous match.

Separating the files keeps "how to collect GitHub" apart from "how this
installation interprets GitHub data against the grid."

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-manifests-1 | Collection Manifest | Proposed | GitHub API/file collection is declared in a schema-validated JSON manifest. | |
| req-github-core-manifests-2 | Link Manifest | Proposed | Cross-grid link rules are declared in a separate schema-validated JSON manifest. | |
| req-github-core-manifests-3 | No Code Loading From Manifest | Proposed | `custom_fn` names resolve through a plugin-local registry; manifests never import code dynamically. | Mirrors AWS collector pattern. |

### Workflow File Parsing
----
RID: `req-github-core-workflow-parse`
Status: `Proposed`

Workflow parsing is v0 because the demo needs to explain the deployment
plumbing inside the workflow file. The plugin parses `.github/workflows/*.yml`
and `.github/workflows/*.yaml` using `PyYAML`, scoped as a plugin-owned Python
dependency.

The v0 parser extracts:

- workflow triggers
- top-level and job-level permissions
- job ids, names, `runs-on`, and `needs`
- `uses:` actions
- referenced `secrets.*`
- referenced `vars.*`

Composite/local action parsing under `.github/actions/**/action.yml` is not v0.
If the collector detects local/composite action references, it records a
structured info/warning that the shape was detected but not parsed, and the spec
flags it as a near-soon implementation target for the next GitHub-focused pass.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-workflow-parse-1 | Workflow YAML Parsed | Proposed | The collector parses `.github/workflows/*.yml|*.yaml` files. | |
| req-github-core-workflow-parse-2 | References Extracted | Proposed | Secret and variable references are extracted from workflow content. | |
| req-github-core-workflow-parse-3 | Local Actions Deferred Warning | Proposed | Local/composite action references produce a visible info/warning and are not silently ignored. | |
| req-github-core-workflow-parse-4 | Steps Not Nodes | Proposed | Step-level details remain in job/workflow configuration in v0. | Future visualization target. |

### Runner Semantics
----
RID: `req-github-core-runner`
Status: `Proposed`

GitHub runners have two relevant shapes:

- Durable registered self-hosted runner configuration, available through the
  runner API when the PAT has sufficient repo administration permissions.
- Observed runner execution data attached to workflow jobs.

v0 creates `github_runner` nodes only for durable registered runner
configuration. Workflow jobs always retain observed runner fields in
`configuration`. If a job's observed runner id matches a durable runner node,
the collector emits `RUNS_ON`; otherwise the job remains self-contained.

GitHub-hosted ephemeral runner observations do not become durable runner nodes
in v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-runner-1 | Durable Runner Nodes | Proposed | Registered self-hosted runners become `github_runner` nodes when visible. | |
| req-github-core-runner-2 | Job Runner Observation | Proposed | Every job stores observed runner fields in configuration when present. | |
| req-github-core-runner-3 | Matchable RUNS_ON | Proposed | `RUNS_ON` is emitted only when an observed job runner matches a durable runner node. | |
| req-github-core-runner-4 | GitHub-Hosted Blobbed | Proposed | GitHub-hosted ephemeral runner observations do not become runner nodes in v0. | |

### Existing Grid Links
----
RID: `req-github-core-grid-links`
Status: `Proposed`

When enabled, the collector resolves exact links from collected GitHub data to
existing TAP nodes using the canonical graph read/query surface. Raw ORM graph
queries are not the collector's normal path.

V0 link rules are conservative:

- only manifest-declared fields may be used for matching
- only exact matches are allowed
- one candidate emits one edge
- zero candidates records an optional warning/info, depending on the rule
- multiple candidates records a warning and emits no edge

Expected initial AWS-oriented link examples:

- `DOMAIN_NAME` -> Route 53 hosted zone `name`
- `AWS_REGION` -> AWS region `region_code`
- visible CloudFront distribution ids/domains -> CloudFront distribution fields

Secret values are never available, so secret references cannot resolve to AWS
nodes by value.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-grid-links-1 | Search/Gryphon Read Path | Proposed | Link resolution uses TAP's canonical search/Gryphon read surfaces. | |
| req-github-core-grid-links-2 | Exact Match Only | Proposed | Links are emitted only for exact unambiguous matches. | |
| req-github-core-grid-links-3 | Ambiguity Warns | Proposed | Multiple matches produce a structured warning and no edge. | |
| req-github-core-grid-links-4 | Secret Values Not Resolved | Proposed | Secret references never resolve by value because secret values are unavailable. | |

### Plugin Python Dependency
----
RID: `req-github-core-python-deps`
Status: `Proposed`

`PyYAML` is approved for this plugin's workflow-file parser and should be
declared as a plugin-owned dependency. This activates the existing
`req-plugin-arch-python-deps` direction: plugin-local `pyproject.toml`, root uv
workspace/member wiring, one resolved environment, and no dependency entries in
`tap-plugin.toml`.

This is dependency ownership, not runtime isolation. The TAP Python environment
will contain the package when the plugin is installed, but the dependency is
justified by and documented with `github_core`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-python-deps-1 | PyYAML Approved | Proposed | `PyYAML` is approved specifically for `github_core` workflow parsing. | |
| req-github-core-python-deps-2 | Plugin-Owned Declaration | Proposed | The dependency is declared in plugin-local Python dependency metadata, not `tap-plugin.toml`. | Requires implementing or using `req-plugin-arch-python-deps`. |
| req-github-core-python-deps-3 | No Isolation Claim | Proposed | The spec does not claim runtime isolation from other installed Python packages. | |

### v0 Non-Goals
----
RID: `req-github-core-nongoals`
Status: `Proposed`

Out of scope for v0:

- full GitHub account or organization inventory
- issue, pull request, branch, collaborator, team, package, release, or
  discussion modeling
- environments, environment variables, organization variables, and organization
  secrets
- Sigstore, Fulcio, Rekor, signed-artifact, or transparency-log models
- GitHub App authentication
- local/composite action parsing beyond visible deferred warnings
- `github_actions_step` nodes
- deletion/reaping of old runs/jobs
- scheduled automatic runs

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-nongoals-1 | Broad Inventory Deferred | Proposed | v0 does not attempt full GitHub introspection. | |
| req-github-core-nongoals-2 | Provenance Plugins Deferred | Proposed | Sigstore/Rekor belong to separate future plugin work. | |
| req-github-core-nongoals-3 | No Schedule | Proposed | v0 registers the collector capability but does not seed an automatic schedule. | Manual/demo run first. |

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`,
`Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`,
`Backlog`.
