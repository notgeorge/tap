# TAP GitHub Core

GitHub Actions deployment-plumbing models for the samsite demo path.

## What This Plugin Owns

- Six v0 models: `github_account`, `github_repository`, `github_workflow`,
  `github_actions_run`, `github_actions_job`, `github_runner`
- Six v0 edge types: `OWNS_REPO`, `DEFINES_WORKFLOW`, `EXECUTES_WORKFLOW`,
  `HAS_ACTIONS_JOB`, `EXECUTED_ON`, `REFERENCES_RESOURCE`
- `github_pat` secret kind (PAT credential validation)
- `GitHubCollector` — `CollectorBase` subclass; two-phase run (collection +
  link enrichment) against the configured `repos` list
- Workflow YAML parser (`.github/workflows/*.yml|*.yaml`) using `PyYAML`

## What This Plugin Does Not Own

- AWS resource models — `plugins/aws_core/`
- Compliance artifacts and KSI scoreboard — `plugins/fedramp_20x_ksi/`
- Repository inventory beyond Actions plumbing (issues, PRs, branches,
  permissions, org-level data — non-goals for v0)
- Variables and secret references (deferred — see backlog requirement
  `req-github-core-backlog-references` in `specs/spec-github-core-v0.md`)
- Multi-attempt run observation (deferred — see backlog requirement
  `req-github-core-backlog-run-attempts`)

## v0 Target

`notgeorge/samsite` — Sam's site cloned into the dev's own GitHub + AWS
accounts, per `plan/road-rampart.md` step `step-rampart-sam-demo`.

## Read First

- `specs/spec-github-core-v0.md` — full design spec (12 Proposed + 2 Backlog
  requirements; design rationale preserved for both backlog items)
- `tap_plugins/specs/spec-plugin-architecture.md` — plugin contract,
  `req-plugin-arch-python-deps` (github_core is the first proof of the uv
  workspace seam: see `plugins/github_core/pyproject.toml`)
- `tap_cares/specs/spec-tap-cares-secrets.md` — secret-kind validation
- `plugins/aws_core/specs/spec-aws-core-collector-v0.md` — sibling collector
  reference (prior art for `CollectorBase` subclass shape and manifest-driven
  collection)

## Plugin-Owned Python Dependency

`PyYAML>=6.0.2` is declared in `plugins/github_core/pyproject.toml` as a uv
workspace member. The root `uv.lock` resolves it; `uv sync --all-packages`
(run by `docker/entrypoint.sh`) installs it into the runtime venv.

## Validation

```
docker compose exec web uv run python -m tap_plugins.validate_plugin plugins/github_core
```
