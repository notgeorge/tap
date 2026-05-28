# GitHub Core Plugin Specification

## Plugin Identity

- **Slug:** `github_core`
- **Display name:** TAP GitHub Core
- **Collector:** `GitHubCollector` — `CollectorBase` subclass; two-phase run (collection + enrichment). See `req-github-core-collector` and `req-github-core-grid-links`.
- **Secret kind:** `github_pat` — Personal Access Token. See `req-github-core-secret`.
- **v0 target:** `notgeorge/samsite` (configured via the secret's `repos` array).
- **Repo shape:** In-tree under `plugins/github_core/` for v0. No standalone git repo or submodule; may be split later if external consumers appear.
- **Default dimensions** (see `req-github-core-dimensions`):
  - `github.platform = "github.com"` on all plugin-owned nodes and edges
  - `github.owner` + `github.repo` on repo-scoped objects (set by the collector per envelope)
  - `github.surface = "actions"` on Actions-related objects
  - `github.observation = "execution"` on runs and jobs

## Philosophy

`github_core` models the GitHub side of the samsite deployment on the TAP
grid. The v0 target is deliberately narrow: make the plumbing from repository
content to live site visible for `notgeorge/samsite`, especially GitHub Actions
workflows, workflow runs, jobs, and runners. Variables and secret references
are deferred to a backlog requirement (`req-github-core-backlog-references`).

This is not a full GitHub inventory product. Broad repository introspection,
organization-wide governance, issue/PR modeling, permissions audits, Sigstore,
and Rekor all remain future work. v0 exists because the Sam demo needs to show
how the static site and compliance machinery move through GitHub Actions into
the running AWS-backed site.

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
| req-github-core-models | [Model Set](#model-set) | Implemented | Account, repo, workflow, run, job, runner — all six tables landed via 0001_initial |
| req-github-core-edges | [Edge Vocabulary](#edge-vocabulary) | Implemented | Repo/workflow/run/job/runner spine plus conservative AWS links — all six edge files registered |
| req-github-core-dimensions | [Dimension Strategy](#dimension-strategy) | Implemented | All four dimensions emitted: platform on every node/edge, repo on collector envelopes, surface on Actions models, observation on runs/jobs |
| req-github-core-secret | [PAT Secret Kind](#pat-secret-kind) | Implemented | `github_pat` data shape, additionalProperties: false; GitHub App auth still deferred |
| req-github-core-collector | [Collector Runtime](#collector-runtime) | Proposed | Two-phase run + degraded-runner + no-delete + single-attempt all implemented; incremental + non-terminal refresh still pending |
| req-github-core-manifests | [Collection And Link Manifests](#collection-and-link-manifests) | Implemented | Two manifests + JSON Schemas, validated at load; link manifest is data-driven |
| req-github-core-workflow-parse | [Workflow File Parsing](#workflow-file-parsing) | Proposed | YAML parse + raw retention + in-memory fetch implemented; local-action detection warning still pending |
| req-github-core-runner | [Runner Semantics](#runner-semantics) | Implemented | Durable runner nodes + matchable EXECUTED_ON + observed-runner-on-job + no-ephemeral-runner-nodes |
| req-github-core-grid-links | [Existing Grid Links](#existing-grid-links) | Implemented | Enrichment phase + exact-only + warn-only failures + Gryphon read path (via `=~` regex operator); OIDC link verified end-to-end against samsite + AWS |
| req-github-core-python-deps | [Plugin Python Dependency](#plugin-python-dependency) | Implemented | `PyYAML` is plugin-owned via root uv workspace; first proof of `req-plugin-arch-python-deps` |
| req-github-core-backlog-references | [Variables And Secret References (Backlog)](#variables-and-secret-references-backlog) | Backlog | Two-source-of-truth model, hotlink contract implication, provenance shape; pick up when critical path |
| req-github-core-backlog-run-attempts | [Multi-Attempt Run Observation (Backlog)](#multi-attempt-run-observation-backlog) | Backlog | Per-attempt run + job fan-out, re-run-failed-jobs subtlety, HAS_JOB lifecycle; pick up when critical path |
| req-github-core-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Full GitHub inventory, Sigstore/Rekor, deletion/reaping, schedules, references, multi-attempt runs |

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
| req-github-core-scope-2 | Actions Plumbing Focus | Proposed | v0 focuses on repository, workflow, run, job, and runner data needed to explain deployment flow. | Variables and secret references are deferred (`req-github-core-backlog-references`). |
| req-github-core-scope-3 | No Broad Introspection | Proposed | Full GitHub account/org/repo introspection is deferred. | |

### Model Set
----
RID: `req-github-core-models`
Status: `Implemented`

The v0 model set is intentionally small but node-granular. Values that deserve
identity, edges, queryability, history, and graph-visible lifecycle become
dedicated node types rather than being jammed into workflow JSON.

Models:

- `github_account` — owner/user/org account.
- `github_repository` — repository shell; v0 only needs enough fields to show it exists and anchor Actions objects.
- `github_workflow` — workflow definition discovered from GitHub Actions API and parsed workflow file content.
- `github_actions_run` — one workflow run (latest observed state; multi-attempt tracking deferred to `req-github-core-backlog-run-attempts`).
- `github_actions_job` — one job within a workflow run. Step details live in `configuration` in v0.
- `github_runner` — durable registered self-hosted runner configuration when visible through the API.

Variables (`github_actions_variable`) and secret references
(`github_actions_secret_ref`) are deferred to
`req-github-core-backlog-references`.

#### Identity

Natural-key inputs:

| Model | Natural Key |
| --- | --- |
| `github_account` | account login or GitHub numeric id |
| `github_repository` | `owner/repo` |
| `github_workflow` | `owner/repo` + workflow id/path |
| `github_actions_run` | `owner/repo` + run id |
| `github_actions_job` | `owner/repo` + job id |
| `github_runner` | `owner/repo` + runner id for durable registered runners |

Entity IDs are deterministic UUIDv5 values over the model type and natural key.

#### Configuration Field Shape

`github_workflow.configuration` and `github_actions_job.configuration` are
JSON fields holding parser output and observation data:

```
github_workflow.configuration = {
    "triggers":    [...],
    "permissions": {...},
    "raw_yaml":    "<full workflow file text as fetched>",
    ...
}

github_actions_job.configuration = {
    "name":     "...",
    "runs_on":  "...",
    "needs":    [...],
    "uses":     [...],
    "steps":    [...],   # structured per-step data; no node per step in v0
    ...
}
```

`raw_yaml` on `github_workflow` is the full workflow YAML body as fetched by
the collector during the collection phase (per `req-github-core-workflow-parse-5`).
Retaining the raw body lets parser logic evolve without re-fetching from
GitHub, and lets future panel work surface the actual workflow text inline.
This follows Cartography's "preserve source payloads" pattern called out in
this spec's Prior Art section.

**Caveat.** `raw_yaml` is the *current* workflow definition at collection
time, not the YAML that any specific historical run actually executed. A
run's `head_sha` field links to the commit that triggered it; fetching per-
run YAML snapshots from `/repos/{owner}/{repo}/contents/.github/workflows/<name>?ref=<head_sha>`
is a future enhancement, not v0. Panel work that surfaces "this run's YAML"
must not conflate the two.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-models-1 | V0 Models Declared | Implemented | The plugin declares the six v0 model types listed above. | |
| req-github-core-models-3 | Job Steps Blobbed | Implemented | Workflow job steps remain structured data in `github_actions_job.configuration` in v0. | Future visualization target. |
| req-github-core-models-4 | Deterministic Identity | Implemented | Every model uses deterministic UUIDv5 identity based on the natural keys above. | `collectors/github_collector/identity.py` mints UUIDv5 from `(entity_type, natural_key)` under a fixed namespace. |
| req-github-core-models-7 | Raw Workflow YAML Retained | Implemented | `github_workflow.configuration.raw_yaml` stores the full workflow YAML body fetched at collection time. | Parser stores raw bytes; collector base64-decodes the Contents-API `content` field and writes it. |

### Edge Vocabulary
----
RID: `req-github-core-edges`
Status: `Implemented`

Edges express the GitHub Actions execution spine and dependency references.

V0 edge types:

| Edge | Direction | Meaning |
| --- | --- | --- |
| `OWNS_REPO` | `github_account` -> `github_repository` | Account owns repo. |
| `DEFINES_WORKFLOW` | `github_repository` -> `github_workflow` | Repo contains workflow definition. |
| `EXECUTES_WORKFLOW` | `github_actions_run` -> `github_workflow` | Run executes workflow. |
| `HAS_JOB` | `github_actions_run` -> `github_actions_job` | Run contains job. v0 reflects the latest-attempt job set; multi-attempt tracking deferred. |
| `EXECUTED_ON` | `github_actions_job` -> `github_runner` | Job executed on a durable runner node when matchable. (Distinct from `computing_core.RUNS_ON`, which models program-on-compute-environment.) |
| `REFERENCES_RESOURCE` | GitHub node -> external grid node | Conservative exact-match link to existing AWS nodes. |

Secret and variable reference edges (`REFERENCES_SECRET`, `REFERENCES_VARIABLE`)
are deferred to `req-github-core-backlog-references`.

`REFERENCES_RESOURCE` is intentionally conservative. It means "this GitHub
plumbing names or depends on this resource" and does not claim deployment,
ownership, or runtime control.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-edges-1 | Execution Spine | Implemented | The repo/workflow/run/job/runner edges are declared and constrained. | |
| req-github-core-edges-2 | Resource Reference Edge | Implemented | The single v0 cross-grid reference edge is `REFERENCES_RESOURCE`. | Secret/variable reference edges deferred. |
| req-github-core-edges-3 | Conservative Resource Semantics | Implemented | `REFERENCES_RESOURCE` is used only for exact, unambiguous matches and does not overstate deployment semantics. | Enforced by the link-manifest schema (`match_mode: exact`-only enum) and the resolver's one-candidate-only emission rule. |

### Dimension Strategy
----
RID: `req-github-core-dimensions`
Status: `Implemented`

GitHub is treated as its own platform environment. The plugin uses flat,
GitHub-specific dimensions:

| Key | Example | Applies To |
| --- | --- | --- |
| `github.platform` | `github.com` | All GitHub nodes and edges |
| `github.owner` | `notgeorge` | Repo-scoped nodes and edges |
| `github.repo` | `samsite` | Repo-scoped nodes and edges |
| `github.surface` | `actions` | Actions workflows, runs, jobs, runners |
| `github.observation` | `execution` | Runs and jobs |

Static model defaults should include only dimensions that are true for all
instances, such as `github.platform = "github.com"`. The collector supplies
repo-specific dimensions in GRIFT envelopes.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-dimensions-1 | GitHub Platform Dimension | Implemented | All plugin-owned nodes and edges carry `github.platform = "github.com"`. | Set in `DEFAULT_DIMENSIONS` on every model and `default_dimensions` on every edge. |
| req-github-core-dimensions-2 | Repo Scope Dimensions | Implemented | Collector-created repo-scoped objects carry `github.owner` and `github.repo`. | Set on every node/edge envelope in `GithubCollector._collect_repo`. |
| req-github-core-dimensions-3 | Actions Surface Dimension | Implemented | Actions-related objects carry `github.surface = "actions"`. | Set on workflow/run/job/runner model defaults and Actions edge defaults. |
| req-github-core-dimensions-4 | Execution Observation Dimension | Implemented | Run and job observations carry `github.observation = "execution"`. | Set on run/job model defaults. |

### PAT Secret Kind
----
RID: `req-github-core-secret`
Status: `Implemented`

The first credential mode is a Personal Access Token. `github_core` owns the
`github_pat` secret kind data schema and validates it consumer-side via
`tap_cares` `require_secret_kind(..., data_schema=...)`.

The bare kind name (`github_pat`, not `github_core.github_pat`) follows the
established TAP convention — kind names describe the credential type itself,
not the owning plugin. See `plugins/aws_core/specs/spec-aws-core-secrets.md`
for the `aws_static_access_key` precedent.

Data fields:

| Field | Required | Default | Meaning |
| --- | :---: | --- | --- |
| `token` | Yes |  | GitHub PAT. Secret material; never logged or stored on grid. |
| `api_base_url` | No | `https://api.github.com` | GitHub API base URL. Rides with the credential because GitHub Enterprise Server (GHES) tenants have different base URLs and different PATs. |
| `repos` | Yes |  | Array of `owner/repo` targets; v0 example is `["notgeorge/samsite"]`. |
| `initial_run_limit` | No | `10` | Number of latest workflow runs to seed on first collection. |

GitHub App authentication is future work.

#### Pruned Knobs (Behavioral Decisions)

Earlier drafts included `collect_runner_config`, `collect_workflow_files`, and
`collect_grid_links`. All three are removed from the data shape because none
earned their keep:

- **`collect_workflow_files`** — workflow YAML parsing is the entire point of
  v0 for the Sam demo. Mandatory, not configurable. If the operator doesn't
  want it, they don't install the plugin.
- **`collect_runner_config`** — `req-github-core-collector-5` already
  specifies that runner-config collection auto-graceful-degrades with a
  structured warning on permission failure. "Always try; degrade on 403" is
  functionally identical to an explicit `false`, just with less ceremony.
- **`collect_grid_links`** — links are always attempted. When the grid has
  zero matching candidates (e.g., first install before `aws_core` lands its
  first batch), the existing zero-candidate warnings under
  `req-github-core-grid-links` provide the "off" affordance for free. An
  explicit kill-switch adds no value beyond what the resolver's no-match
  behavior already covers.

#### Credential vs Behavior Separation (Future Concern)

Mixing credential material and behavioral knobs on the same secret couples
PAT rotation to operational config — rotating a token means re-typing or
copy-preserving the knobs. For v0 the cost is small (one operator, one
behavioral knob, rare rotation), so the secret carries both. Re-evaluate
when *either*:

- the behavioral knob set grows past two or three flags, *or*
- the rotation cost actually bites (multiple operators rotating, or knobs
  that operators want to change without touching the credential).

The likely landing place is the same hypothetical on-grid plugin-config
model the `feedback_no_plugin_config_in_core_infra` memory item points at.
Do not pre-build it; wait for the trigger.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-secret-1 | PAT First | Implemented | v0 supports `github_pat` as the first and only credential kind. | `collectors/github_collector/secret.py:GITHUB_SECRET_KIND`. |
| req-github-core-secret-2 | Plugin Owns Schema | Implemented | `github_core` ships and validates the `github_pat` JSON Schema. | `GITHUB_PAT_SCHEMA` in `secret.py`; validated via `require_secret_kind`. |
| req-github-core-secret-3 | Repo Array Scope | Implemented | The secret carries the repo target list as `data.repos`. | Schema requires non-empty array of `owner/repo` patterns. |
| req-github-core-secret-4 | GitHub App Deferred | Proposed | GitHub App auth is deferred. | |
| req-github-core-secret-5 | Minimal Knob Set | Implemented | The only behavioral knob is `initial_run_limit`; `collect_workflow_files`, `collect_runner_config`, and `collect_grid_links` are not data fields. | Schema is `additionalProperties: false`; the three pruned names trigger validation errors at load. |

### Collector Runtime
----
RID: `req-github-core-collector`
Status: `Proposed`

The collector is a standard `CollectorBase` subclass registered by
`github_core`. It resolves one `github_pat` secret, validates its shape, and
runs in two sequential phases per execution:

1. **Collection phase** — fetch GitHub data for each configured repo, assemble
   a GRIFT batch, submit via `CollectorBase.submit_grift`. This is the main
   batch; on commit, GitHub nodes and execution-spine edges land.
2. **Enrichment phase** — once the main batch is committed, query the
   just-landed GitHub nodes for the configured repos, run the grid-link
   manifest rules against existing grid candidates, and submit a second small
   GRIFT batch containing only `REFERENCES_RESOURCE` edges. Detailed timing
   semantics live with `req-github-core-grid-links`.

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
- v0 does not model multiple run attempts. The collector uses GitHub's default
  jobs endpoint (`GET /runs/{run_id}/jobs`, not `/attempts/{n}/jobs`), which
  returns the latest-attempt snapshot. If a re-run happens between collections,
  the run node is upserted with the latest state and HAS_JOB reflects the
  newest job set — but old job nodes from the prior attempt persist (per the
  no-deletion rule) and can produce graph clutter. Multi-attempt tracking is
  deferred to `req-github-core-backlog-run-attempts`.
- The enrichment phase re-resolves links against all configured-repo GitHub
  nodes on every run, not just newly-changed ones, so AWS data landing later
  heals link coverage organically.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-collector-1 | CollectorBase | Implemented | The collector subclasses `CollectorBase` and uses the normal `tap_cares` runtime. | `GithubCollector` registered via `register_collector(key="github_core")` in `apps.py`. |
| req-github-core-collector-2 | First Run Seeds Ten | Implemented | Initial collection defaults to the latest 10 runs per repo. | Default from `initial_run_limit(data)` (returns 10 when absent); applied via `per_page` query + `[:run_limit]` slice. |
| req-github-core-collector-3 | Incremental Later Runs | Proposed | Later runs collect runs created since the latest on-grid run for the repo. | Future: filter by max `github_actions_run.created_at` on the grid. |
| req-github-core-collector-4 | Non-Terminal Refresh | Proposed | Non-terminal prior runs/jobs are refreshed on each run. | Future: re-fetch prior runs with `status != "completed"` until terminal. |
| req-github-core-collector-5 | Runner Permission Degrades | Implemented | Runner-config permission failures record warnings and do not abort run/job collection. | Collector catches `GithubAPIError.status == 403` on `/actions/runners` and emits a structured `RUNNER_CONFIG_FORBIDDEN` warn. |
| req-github-core-collector-6 | No Deletion Semantics | Implemented | v0 never deletes GitHub nodes based on absence from API responses. | Collector emits only upserts; no `deletes`/`purges` sections in batch. |
| req-github-core-collector-7 | Two-Phase Run | Implemented | Each collector run executes a collection phase followed by an enrichment phase, in that order. | `GithubCollector.run()` calls `submit_grift` twice; enrichment runs only if the first batch lands. |
| req-github-core-collector-8 | Single-Attempt v0 | Implemented | v0 does not model multiple run attempts; collector uses the default jobs endpoint returning the latest-attempt snapshot. | Uses `/runs/{run_id}/jobs` (no `/attempts/{n}/`). Multi-attempt tracking deferred to `req-github-core-backlog-run-attempts`. |
| req-github-core-collector-9 | Empty-Body 404 Retry | Implemented | The HTTP client retries GitHub's intermittent empty-body 404 responses with exponential backoff (0.5s → 8s, up to 5 retries). Real 404s — carrying a JSON `{"message": "..."}` body — propagate immediately. | GitHub docs for `/actions/runs` and `/list-jobs-for-workflow-run` document only `200 - OK`. Secondary rate limits are documented to return 403/429, not 404. Empty-body 404 with valid `X-GitHub-Request-Id` is observed and undocumented; the body presence is the discriminator. See `api_client.py` module docstring for the evidence trail. |
| req-github-core-collector-10 | Per-Run /jobs Graceful-Degrade | Implemented | When `/runs/{id}/jobs` returns a real (body-bearing) 404 for a specific run, the collector records a structured `RUN_JOBS_MISSING` warn including the response-body excerpt and continues with the next run rather than aborting the whole collection. | Mirrors `req-github-core-collector-5`'s degrade pattern for runner-config 403s. |

### Collection And Link Manifests
----
RID: `req-github-core-manifests`
Status: `Implemented`

The collector uses two declarative JSON manifests, both schema-validated at
load. Invalid manifests fail the run visibly.

`github_collection_manifest.json` declares GitHub sources: REST endpoints,
workflow file fetches, item paths, target entity types, projected fields, and
edge rules within the GitHub graph. The source primitive set may include:

- `rest_endpoint`
- `repo_file`
- `custom_fn`

`github_grid_link_manifest.json` declares conservative cross-plugin link rules:
which collected GitHub fields may be matched against which existing TAP entity
types and fields, and which edge type to emit on exact unambiguous match.

Separating the files keeps "how to collect GitHub" apart from "how this
installation interprets GitHub data against the grid."

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-manifests-1 | Collection Manifest | Implemented | GitHub API/file collection is declared in a schema-validated JSON manifest. | `github_collection_manifest.json` + `.schema.json`; validated at load by `manifest.load_collection_manifest()`. v0 manifest is an inspection document; the engine is procedural. Driving the engine off the manifest is a future refactor. |
| req-github-core-manifests-2 | Link Manifest | Implemented | Cross-grid link rules are declared in a separate schema-validated JSON manifest. | `github_grid_link_manifest.json` + `.schema.json`; loaded by `manifest.load_link_manifest()`. Resolver in `enrichment.py` is fully data-driven off this manifest. |
| req-github-core-manifests-3 | No Code Loading From Manifest | Implemented | `custom_fn` names resolve through a plugin-local registry; manifests never import code dynamically. | v0 doesn't use `custom_fn` (schema permits it but no rule references it). When/if added, the registry will live alongside the loader. |

### Workflow File Parsing
----
RID: `req-github-core-workflow-parse`
Status: `Proposed`

Workflow parsing is v0 because the demo needs to explain the deployment
plumbing inside the workflow file. The plugin parses `.github/workflows/*.yml`
and `.github/workflows/*.yaml` using `PyYAML`, scoped as a plugin-owned Python
dependency.

#### Fetch Shape

Workflow YAML bytes are fetched via the GitHub Contents API
(`GET /repos/{owner}/{repo}/contents/.github/workflows/`) and decoded from the
inline base64 `content` field of each file response. Bytes are held in memory
for the duration of one repo's collection pass, parsed with `yaml.safe_load`,
and persisted on the `github_workflow` row as `configuration.raw_yaml` per
`req-github-core-models-7`. No working copy, no on-disk write, no temp file.

This is sized for v0: workflow YAML for a single repo is bounded — a handful
of files at low tens of KB total — so in-memory parsing is the obvious shape.

The collector's fetch helper should be named explicitly
(`_fetch_workflow_yaml(owner, repo, path) -> bytes`) so the body can be swapped
later — e.g., shallow clone + tempdir-walk — without disturbing callers, if a
future fetch shape demands it.

**Future-work seam (Backlog, no implementation in v0).** When a future TAP
collector needs on-disk file layout — broader repo introspection
(terraform parsing, vendored config audits), payloads too large for memory,
or tools that expect a working tree (`terraform validate`, OPA bundle eval) —
define a small temp-file strategy at that time using Django/stdlib primitives
(`tempfile.TemporaryDirectory`, `django.core.files.storage.FileSystemStorage`
for the testable layer). Author a dedicated cross-cutting spec when the demand
signal arrives; do not pre-build the seam. v0 has none of these triggers and
deliberately ships without temp-file infrastructure.

**Future-work seam (per-run head_sha YAML snapshot).** v0's `raw_yaml`
captures the *current* workflow definition at collection time, not the YAML
that any specific historical run actually executed. Per-run snapshots would
fetch `/repos/{owner}/{repo}/contents/.github/workflows/<name>?ref=<head_sha>`
once per run — bounded but multiplies API calls. Pick this up when a panel
or compliance check actually needs per-run YAML fidelity; defer until then.

The v0 parser extracts:

- workflow triggers
- top-level and job-level permissions
- job ids, names, `runs-on`, and `needs`
- `uses:` actions

Extraction of `secrets.*` and `vars.*` references is deferred to
`req-github-core-backlog-references` — the design analysis (two-source-of-truth
shape, hotlink contract implications, scope rules) is captured there.

Composite/local action parsing under `.github/actions/**/action.yml` is not v0.
If the collector detects local/composite action references, it records a
structured info/warning that the shape was detected but not parsed, and the spec
flags it as a near-soon implementation target for the next GitHub-focused pass.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-workflow-parse-1 | Workflow YAML Parsed | Implemented | The collector parses `.github/workflows/*.yml|*.yaml` files. | `parser.parse_workflow_yaml` using PyYAML's `safe_load`; YAML 1.1 `on:` boolean gotcha handled. |
| req-github-core-workflow-parse-3 | Local Actions Deferred Warning | Proposed | Local/composite action references produce a visible info/warning and are not silently ignored. | Detector not yet implemented in `parser.py`. |
| req-github-core-workflow-parse-4 | Steps Not Nodes | Implemented | Step-level details remain in job/workflow configuration in v0. | Parser preserves the `steps` list verbatim under `configuration.jobs[i].steps`. |
| req-github-core-workflow-parse-5 | In-Memory Fetch | Implemented | Workflow YAML is fetched via the Contents API and parsed in memory; v0 writes no temp file and creates no working copy. | `GithubCollector._fetch_workflow_config` calls `/repos/{owner/repo}/contents/{path}`, decodes inline base64, never writes to disk. |

### Runner Semantics
----
RID: `req-github-core-runner`
Status: `Implemented`

GitHub runners have two relevant shapes:

- Durable registered self-hosted runner configuration, available through the
  runner API when the PAT has sufficient repo administration permissions.
- Observed runner execution data attached to workflow jobs.

v0 creates `github_runner` nodes only for durable registered runner
configuration. Workflow jobs always retain observed runner fields in
`configuration`. If a job's observed runner id matches a durable runner node,
the collector emits `EXECUTED_ON`; otherwise the job remains self-contained.

GitHub-hosted ephemeral runner observations do not become durable runner nodes
in v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-runner-1 | Durable Runner Nodes | Implemented | Registered self-hosted runners become `github_runner` nodes when visible. | Collector iterates `/actions/runners` response; one node per runner. |
| req-github-core-runner-2 | Job Runner Observation | Implemented | Every job stores observed runner fields in configuration when present. | `runner_id`, `runner_name`, `runner_group_id`, `labels` persisted on `github_actions_job.configuration`. |
| req-github-core-runner-3 | Matchable EXECUTED_ON | Implemented | `EXECUTED_ON` is emitted only when an observed job runner matches a durable runner node. | Collector keeps `runner_uuid_by_id` from collected runners and emits `EXECUTED_ON` only when `job.runner_id` is in that map. |
| req-github-core-runner-4 | GitHub-Hosted Blobbed | Implemented | GitHub-hosted ephemeral runner observations do not become runner nodes in v0. | No node creation in the job loop; observed runner data stays in `job.configuration`. |

### Existing Grid Links
----
RID: `req-github-core-grid-links`
Status: `Implemented`

The collector always attempts to resolve exact links from collected GitHub
data to existing TAP nodes using the canonical graph read/query surface. Raw
ORM graph queries are not the collector's normal path. There is no kill-switch
knob — when the grid has zero matching candidates (e.g., first install before
`aws_core` lands its first batch), the resolver emits no edges and the
zero-candidate rule below provides the "links are off" affordance for free.

The link manifest supports two source-side shapes:

- `source_field_path` — extract from the source node's nested attribute/JSON
  (the original shape, used by the YAML-ref rules: domain names, AWS regions,
  CloudFront distribution ids).
- `source_constant` — literal value applied to every source node, for
  structural rules where the join key isn't node-specific. First user:
  `repo_federates_with_github_oidc_provider` matches every collected
  `github_repository` against the canonical GitHub Actions OIDC issuer URL
  on `aws_iam_oidc_provider.url`.

Rules may also declare a `near_match_pattern` (case-insensitive regex). When
exact resolution returns zero candidates AND the target field of any row
matches the pattern, the resolver records a structured `LINK_NEAR_MATCH`
warn per row and emits no edge — surfacing "looks like what you meant but
isn't quite it" rows (URL scheme variants, GHES tenants, typos) so the
operator can investigate rather than silently miss the link.

#### Timing: Enrichment Phase

Link resolution runs as a **follow-on enrichment phase within the same
collector run**, executing *after* the main GitHub GRIFT batch has been
submitted and committed. A collector run has two phases:

```
GitHubCollector.run():
    1. Collection phase  — fetch API + workflow YAML, build GitHub GRIFT batch
    2. Submission        — submit_grift(github_batch); committed
    3. Enrichment phase  — query landed GitHub nodes for the configured repos,
                            run link manifest rules against grid candidates,
                            emit REFERENCES_RESOURCE edges as a second GRIFT
                            batch (edges only — sources and targets already exist)
```

This timing is deliberate:

- **GitHub batch is independent of grid state.** It succeeds even if no AWS
  data exists yet. Zero edges materialize that run, which is the correct
  observation.
- **Heals over re-runs.** Every `github_core` run re-resolves links against
  *all* configured-repo GitHub nodes — not just newly-changed ones — so AWS
  data landing later picks up links on the next `github_core` execution
  without needing GitHub data to have changed.
- **No new core infra.** Two sequential `CollectorBase.submit_grift` calls
  through the standard path. The pre-commit consistency phase
  (`req-grid-service-batch-precommit-consistency`) is *not* a v0 host for
  enrichment — its spec explicitly defers adding a second consumer.
- **Enrichment failures don't abort the run.** The GitHub batch is already
  committed; enrichment problems emit warnings only. Transient multiple-
  candidate warnings on flaky grid state self-heal on the next run.

`REFERENCES_RESOURCE` is **not** hotlink-backed. Hotlinks are for embedded
references that must match edges (the source node's own data is authoritative).
REFERENCES_RESOURCE is a *derived* link — the GitHub node has no embedded
knowledge of which AWS nodes exist; the link manifest plus grid state are
the authority. It is an enrichment derivation, not a source-of-truth
declaration. This is the structural distinction between v0's
`REFERENCES_RESOURCE` and the deferred hotlinked reference edges in
`req-github-core-backlog-references`.

#### Link Rules

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

Resolving collected GitHub Actions variable values against AWS nodes is a
future capability deferred with the rest of variable/secret-ref work in
`req-github-core-backlog-references`.

#### Future Work (Not v0)

- **Cross-collector triggering.** Today, fresh AWS data landing via
  `aws_core` does not ping `github_core` to re-resolve; links materialize
  organically on the next `github_core` run. Building a cross-collector
  dependency / trigger system is a real complexity bump and not justified by
  current demand. Revisit when an operator-visible "stale links" problem
  actually appears.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-grid-links-1 | Search/Gryphon Read Path | Implemented | Link resolution uses TAP's canonical search/Gryphon read surfaces. | `enrichment.py` runs four Gryphon Searches per rule: source-node fetch (`MATCH (n:<source_type>) WHERE n.data.full_name IN [...]`), exact-match candidate (`WHERE n.data.<field> = $value`), near-match (`WHERE n.data.<field> =~ $pattern AND NOT n.data.<field> = $exact`), and the labelless target-name lookup falls out of the spine envelope's `name` field (no extra query needed). The `=~` operator landed in `req-grid-traversal-lang-regex` on 2026-05-28. |
| req-github-core-grid-links-2 | Exact Match Only | Implemented | Links are emitted only for exact unambiguous matches. | Manifest schema constrains `match_mode` to the `exact` enum value; resolver emits only when `len(candidates) == 1`. |
| req-github-core-grid-links-3 | Ambiguity Warns | Implemented | Multiple matches produce a structured warning and no edge. | Resolver records a `LINK_AMBIGUOUS` warn per multi-candidate hit. |
| req-github-core-grid-links-4 | Enrichment Phase | Implemented | Link resolution executes as a follow-on phase after the main GitHub GRIFT batch commits, emitting a second GRIFT batch containing only `REFERENCES_RESOURCE` edges. | `GithubCollector.run()` submits collection batch, then `resolve_links()` runs, then a second `submit_grift` if any edges resolved. |
| req-github-core-grid-links-5 | Re-Resolve Every Run | Implemented | Every collector run re-resolves links against all configured-repo GitHub nodes, not just newly-changed ones. | `_source_queryset_for_repos` filters by `full_name__in=repos` and walks every matching landed node every run. |
| req-github-core-grid-links-6 | Enrichment Failures Warn Only | Implemented | Enrichment-phase failures emit structured warnings; they do not roll back the already-committed GitHub batch. | Enrichment has no abort path; missing target models log + skip, multi-candidate hits warn + skip. |
| req-github-core-grid-links-7 | Not Hotlink-Backed | Implemented | `REFERENCES_RESOURCE` is a derived link, not a hotlink: no `HOTLINKS` declaration, no pre-commit consistency-phase participation. | No HOTLINKS declared on any github_core model; resolver is a separate phase, not a model-level invariant. |

### Plugin Python Dependency
----
RID: `req-github-core-python-deps`
Status: `Implemented`

`PyYAML` is approved for this plugin's workflow-file parser and should be
declared as a plugin-owned dependency. `github_core` is the first proof of the
`req-plugin-arch-python-deps` seam (Status: In Development): plugin-local
`pyproject.toml`, root uv workspace/member wiring already in place, one
resolved environment, and no dependency entries in `tap-plugin.toml`.

This is dependency ownership, not runtime isolation. The TAP Python environment
will contain the package when the plugin is installed, but the dependency is
justified by and documented with `github_core`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-python-deps-1 | PyYAML Approved | Implemented | `PyYAML` is approved specifically for `github_core` workflow parsing. | Declared in `plugins/github_core/pyproject.toml`. |
| req-github-core-python-deps-2 | Plugin-Owned Declaration | Implemented | The dependency is declared in plugin-local Python dependency metadata, not `tap-plugin.toml`. | First proof of `req-plugin-arch-python-deps`; landed via root `[tool.uv.workspace]`. |
| req-github-core-python-deps-3 | No Isolation Claim | Implemented | The spec does not claim runtime isolation from other installed Python packages. | |

### Variables And Secret References (Backlog)
----
RID: `req-github-core-backlog-references`
Status: `Backlog`

GitHub Actions variables (`vars.X`) and secret references (`secrets.X`) are
deferred. The Sam demo path does not need them on critical path, and shaping
them properly tangles with TAP's hotlink contract, multi-source provenance,
and the future env/org scope vocabulary. Picking this up before it's
load-bearing risks shipping a half-baked shape that bakes assumptions we
won't be able to easily back out.

This requirement preserves the design analysis already performed so the next
pass starts from "here is what we figured out" rather than "what should we
even build." Pick it up when secret/variable visibility becomes critical
path — most likely when the second customer's deployment needs ref-tracing,
or when the Sam KSI scoreboard requires linking secret refs to compliance
controls.

#### Goal Shape (When Picked Up)

The end state is two models and two reference edges, hotlink-enforced for
correctness:

- `github_actions_variable` — repo-scoped Actions variables, with values when
  API-collected.
- `github_actions_secret_ref` — repo-scoped secret references. Values are
  never collected (GitHub API never returns them). The node is a target of
  reference edges only.
- `REFERENCES_SECRET`: workflow/job → `github_actions_secret_ref`
- `REFERENCES_VARIABLE`: workflow/job → `github_actions_variable`
- Both reference edges are hotlink-backed with `mode: exact` per
  `tap_grid/specs/spec-grid-hotlink.md`. The authoritative embedded view
  lives in `<source_node>.configuration.refs.{secrets,variables}`; the edge
  set must agree exactly, enforced by the pre-commit consistency phase.

#### What We Figured Out (Carry-Forward Notes)

**Two sources of truth per kind.** Each is independent and authoritative for
different aspects of identity/state:

| | API source | YAML source |
| --- | --- | --- |
| `github_actions_variable` | `GET /repos/{owner}/{repo}/actions/variables` — returns names **and values** | `vars.X` parsed from workflow/job/step YAML |
| `github_actions_secret_ref` | `GET /repos/{owner}/{repo}/actions/secrets` — returns names **only** | `secrets.X` parsed from workflow/job/step YAML |

**Hotlink contract forces every YAML-referenced name to become a node.**
Because `mode: exact` requires every name in `refs.secrets[]` / `refs.variables[]`
to map to an edge, and every edge needs a target node, the design choice
"warning-only, no node for unresolved YAML refs" is structurally incompatible
with the hotlink play. Options must be variants of "create the node, mark
provenance."

**Proposed provenance shape: `discovered_via: list[str]` on each node.**
Sorted array of strings; v0 values `["api"]`, `["yaml"]`, or `["api", "yaml"]`.
Array-not-enum so future sources (`org_api`, `env_api`, GraphQL) plug in
without a migration. `github_actions_variable.value` is nullable: populated
when API observation lands, null when only YAML-referenced — the
`discovered_via` array is the trustworthiness flag. `github_actions_secret_ref`
never has a value field.

**Reset each collection, do not accumulate.** `discovered_via` reflects the
current pass. If a secret was `["api", "yaml"]` last run and the operator
removed it from GitHub, next run finds it only in YAML and the field becomes
`["yaml"]`. Historic transitions live in node history (django-simple-history),
not on the current row.

**Natural-key uniqueness.** YAML reference and API observation for the same
`owner/repo + scope + name` resolve to the same node — different sources,
same identity.

**No deletion in v0** (per `req-github-core-collector-6`). A node observed
once persists if later collections don't see it; the `discovered_via` field
may shrink to `[]` for a fully-orphaned name. Deletion semantics are
themselves future work.

**Scope vocabulary.** For v0 of this backlog, the only valid value of "scope"
in the natural key is `repo`. Future env/org scopes add `env:<env-name>` and
`org` when those collection paths come online. Pin this explicitly when
shipping so the field doesn't sit ambiguous.

**Reference extraction scope rules (parser semantics).**

| Refs go onto... | ...when the textual reference appears at... |
| --- | --- |
| `github_workflow.configuration.refs` | top-level `env:`, top-level `permissions:` RHS, top-level `on.workflow_call.secrets:` / `.inputs:` (reusable workflows) |
| `github_actions_job.configuration.refs` | `job.env`, `job.with`, `job.secrets:` (when calling a reusable workflow), `step.env`, `step.with`, `step.run` body, `step.if` |

- Workflow-scope refs do **not** propagate to job `refs` lists.
- Job-scope refs do **not** propagate to workflow `refs` lists.
- Step-level refs roll up to their parent `github_actions_job` (Steps Not
  Nodes; the parent job is the smallest node that owns the reference).
- Each `refs` list is deduplicated at extract time — multiple textual
  references to the same name at the same scope produce one entry, hence
  one edge. Dedupe is structural, not policed.

The "no inheritance, no roll-down" rules fall out structurally: workflow node's
`refs.secrets` is extracted only from workflow-scope YAML positions; job
node's `refs.secrets` only from job+step positions. Wrong scope = wrong
field = no extraction. GitHub Actions resolves inheritance at runtime; the
grid models the textual YAML source-of-truth only.

**Collector warnings (when picked up).** When extracting a YAML ref name
that wasn't in the corresponding API list for that repo's pass, emit a
structured info/warning per-ref. Mirrors the existing
`req-github-core-workflow-parse-3` local-actions-deferred warning pattern.

**Consumer-side disclosure complement.** Secret-ref / variable panels should
surface `discovered_via` as ✓/✗ pills (api present, yaml referenced). Mirrors
the producer-side `feedback_disclose_shortcuts_machine_readably` /
consumer-side `feedback_consumer_side_disclosure_complement` discipline —
distinguish unknown (predates the field) from explicit `["yaml"]` (definitely
not in API). Future panel work, not part of model shape.

#### Discarded Options

- **"YAML ref → warning only, no node, no edge."** Breaks the `mode: exact`
  hotlink contract on the very first batch. Rejected.
- **"Single-source nodes — API-only, no YAML synthesis."** Same problem:
  YAML extraction populates `refs` lists; without target nodes for those
  refs, the hotlink validation fails.
- **Accumulated provenance (union-of-all-observations forever).** Lossy when
  observations actually disappear; node history already captures the timeline.
  Reset-per-pass is more truthful.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-backlog-references-1 | Two-Model Set | Backlog | `github_actions_variable` and `github_actions_secret_ref` are added with the natural keys and v0 scope vocabulary (`repo`) defined above. | |
| req-github-core-backlog-references-2 | Two-Edge Set | Backlog | `REFERENCES_SECRET` and `REFERENCES_VARIABLE` are added as workflow/job → ref-node edges. | |
| req-github-core-backlog-references-3 | Hotlink Enforcement | Backlog | Both reference edges are hotlink-backed (`mode: exact`) with HOTLINKS declarations on `github_workflow` and `github_actions_job` targeting `configuration.refs.secrets[*]` and `configuration.refs.variables[*]`. | Drift impossible by construction. |
| req-github-core-backlog-references-4 | Provenance Field | Backlog | Each ref-node carries `discovered_via: list[str]` reflecting the current collection pass. | Array-not-enum so future sources extend without migration. |
| req-github-core-backlog-references-5 | Variable Value Nullable | Backlog | `github_actions_variable.value` is nullable, populated only on API observation. | |
| req-github-core-backlog-references-6 | Secret Values Never Stored | Backlog | `github_actions_secret_ref` has no `value` field. | GitHub API never returns secret values. |
| req-github-core-backlog-references-7 | Parser Scope Rules | Backlog | Parser populates each node's `refs` lists per the scope-rule table above; step refs roll up to the parent job; no inheritance fan-out. | |
| req-github-core-backlog-references-8 | Collector Warning | Backlog | YAML-referenced names absent from the API list emit a structured info/warning per-ref. | |
| req-github-core-backlog-references-9 | No Deletion | Backlog | Reference nodes persist when no longer observed; `discovered_via` may shrink to `[]`. | Inherits from `req-github-core-collector-6`. |

### Multi-Attempt Run Observation (Backlog)
----
RID: `req-github-core-backlog-run-attempts`
Status: `Backlog`

GitHub workflow runs can be re-run, producing multiple "attempts" — each
attempt has its own job_ids (GitHub mints new job_ids per attempt) and its
own per-job lifecycle. v0 collapses this to a single observation per `run_id`
because the Sam demo path doesn't involve re-runs, and modeling attempts
adds non-trivial complexity around HAS_JOB lifecycle, "re-run failed jobs"
semantics, and orphan handling.

Pick this up when re-run visibility becomes critical path — most likely
during a real assessment where a customer's CI/CD involves frequent re-runs
and the operator wants to see "which attempt succeeded" or "which jobs were
re-run vs. inherited."

#### Goal Shape (When Picked Up)

The end state models each attempt as a distinct execution observation:

- `github_actions_run` natural key: `owner/repo + run_id + run_attempt`
- `github_actions_job` natural key remains `owner/repo + job_id` (job_ids
  are per-attempt at GitHub source, so they're naturally distinct without
  TAP-side synthesis)
- Each per-attempt run node has its own `HAS_JOB` fan-out to its own per-
  attempt job nodes
- Same logical-job-across-attempts query pattern via `job.name + run.run_id`
  (e.g., "all attempts of the deploy job for this run")

#### What We Figured Out (Carry-Forward Notes)

**GitHub mints new job_ids per attempt.** Re-running a workflow keeps the
same `run_id` but creates new `job_id` values for every job in the new
attempt. Job names are stable across attempts (e.g., both attempts' "deploy"
jobs are named `deploy`), but job_ids are not. The natural-key shape
(`owner/repo + job_id`) therefore needs no TAP-side synthesis to keep
attempts distinct.

**Two GitHub re-run UIs with different semantics.**

| UI mode | Behavior |
| --- | --- |
| Re-run all jobs | Every job gets a fresh attempt; attempt N's jobs endpoint returns the full fan-out |
| Re-run failed jobs only | Only failed jobs re-execute; attempt N's jobs endpoint returns only the re-run jobs, with previously-successful jobs staying attached to attempt N-1 |

A faithful model just records what each `/runs/{run_id}/attempts/{n}/jobs`
endpoint returns for that attempt — no synthesis, no "fill in the missing
successful jobs from earlier attempts onto the latest attempt." The "full
state of this run including the latest attempt of each job" is a derived
query (`GROUP BY job.name WHERE run.run_id == X ORDER BY run.run_attempt
DESC LIMIT 1 per name`), not a model concern.

**API endpoints:**
- `GET /runs/{run_id}/jobs` — returns latest-attempt jobs only (what v0 uses)
- `GET /runs/{run_id}/attempts/{n}/jobs` — returns that specific attempt's
  jobs (what the multi-attempt model uses per attempt)

**HAS_JOB lifecycle on re-collection.** With per-attempt run nodes, each
attempt's HAS_JOB edges are static — once observed, the attempt and its
jobs don't change. There's no "swap the edge set on re-run" problem because
each attempt is its own run node. This is structurally simpler than the v0
shape, which has the messy edge-clutter issue described in
`req-github-core-collector-8`.

**Same logical job across attempts.** Querying "which attempts of the deploy
job ran" is `job.name == "deploy" AND job.run.run_id == X`. No new model
machinery — `name` is already a queryable field on job nodes. Future panel
work might surface "this job has had 3 attempts" inline, but that's panel
concern, not model.

**v0's documented gap.** Under v0, a re-run between collections leaves the
graph in a slightly confusing state: the run node is upserted with the
latest-attempt status, HAS_JOB picks up the new attempt's jobs, but old
attempt-1 jobs persist (no deletion). The operator sees a run with more jobs
than ran in any single attempt. This is a known limitation, not a bug —
the demo doesn't hit it, and the fix lives here.

#### Discarded Options (For v0 Of This Backlog)

- **"Single shared job node across attempts" (synthetic key like
  `owner/repo + run_id + job_name`).** Rejected: GitHub's source-of-truth
  uses per-attempt job_ids. Inventing a shared identity loses per-attempt
  history (start/end times, conclusions) and misrepresents the upstream
  model.
- **"Latest-attempt-wins, drop old job nodes on re-run."** Rejected: violates
  `req-github-core-collector-6` (no deletion semantics). History matters
  for compliance / audit use cases — successful and failed attempts are
  both load-bearing observations.
- **"Build cross-attempt HAS_JOB edges so the run node fan-outs to all
  attempts' jobs."** Rejected for the per-attempt-run-node model: each
  attempt is its own run node, so HAS_JOB is naturally scoped. Cross-
  attempt navigation is a query, not a structural edge.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-github-core-backlog-run-attempts-1 | Per-Attempt Run Nodes | Backlog | `github_actions_run` natural key includes `run_attempt`; each attempt is a distinct node. | |
| req-github-core-backlog-run-attempts-2 | Per-Attempt Job Fan-Out | Backlog | Each per-attempt run node has its own `HAS_JOB` edges to that attempt's job nodes. | Job natural key stays `owner/repo + job_id`; GitHub job_ids are per-attempt. |
| req-github-core-backlog-run-attempts-3 | Attempts Endpoint | Backlog | Collector queries `GET /runs/{run_id}/attempts/{n}/jobs` per attempt instead of the default jobs endpoint. | |
| req-github-core-backlog-run-attempts-4 | Re-Run Failed Semantics | Backlog | The collector records exactly what each attempt's endpoint returns; no synthesis to fill in successful jobs from earlier attempts. | "Latest full state" is a derived query, not a stored shape. |
| req-github-core-backlog-run-attempts-5 | Static Per-Attempt Edges | Backlog | Once an attempt's HAS_JOB edges land, they are not modified by re-collection of that attempt. | Each attempt is immutable once terminal. |
| req-github-core-backlog-run-attempts-6 | v0 Graph Clutter Resolved | Backlog | Implementing this requirement resolves the documented v0 limitation in `req-github-core-collector-8` where re-runs cause HAS_JOB to span attempts. | |

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
- repository Actions variables and secret references (deferred to
  `req-github-core-backlog-references` with full design analysis preserved)
- multi-attempt run observation (deferred to
  `req-github-core-backlog-run-attempts`; v0 collects the latest-attempt
  snapshot only)
- Sigstore, Fulcio, Rekor, signed-artifact, or transparency-log models
- GitHub App authentication
- local/composite action parsing beyond visible deferred warnings
- `github_actions_step` nodes
- deletion/reaping of old runs/jobs
- scheduled automatic runs
- temp-file or working-copy fetch strategy (see Workflow File Parsing
  future-work seam)

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
