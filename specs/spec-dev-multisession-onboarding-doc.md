# Developer Onboarding Doc — Multi-Session Dev

## Philosophy

A developer (human or LLM) provisioning a new isolated TAP dev session needs a single procedural doc to follow — not a hunt across three feature specs. The feature specs (`spec-dev-multisession.md`, `spec-dev-multisession-smoketest.md`, `spec-dev-multisession-teardown.md`) define *what* the multi-session system does and *why*; this doc-spec owns the *how-to* surface — `docs/doc-dev-multisession-onboarding.md` — and tracks its alignment with the underlying behavior.

The doc is the trial run for the documentation system defined in [spec-docs.md](spec-docs.md). Any rough edges in the trial fold back into the meta-spec.

## Goals

|   |   |  |
| :---: | --- | --- |
| 1. | Single Procedural Surface | One doc walks the reader from "I want a new session" to "I have a running, smoke-tested session" without requiring spec navigation. |
| 2. | LLM-Actionable | An attached Claude Code session can follow the doc top-to-bottom and execute every command without ambiguity. |
| 3. | Spec-Aligned | The doc reflects current behavior of `scripts/dc`, `docker-compose.yml`, the port registry, and the smoke-test/teardown procedures. |
| 4. | Drift-Resistant | Every change to the underlying behavior (compose params, port band, scripts, smoke-test or teardown procedures) is captured in `update-triggers:` so a future editor knows the doc needs review. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-dev-multisession-onboarding-doc-exists | [Doc Exists at Canonical Path](#doc-exists-at-canonical-path) | Proposed | `docs/doc-dev-multisession-onboarding.md` |
| req-dev-multisession-onboarding-doc-procedure | [Procedure Reflects Current Behavior](#procedure-reflects-current-behavior) | Proposed | Steps match what `scripts/dc` and `docker-compose.yml` actually do |
| req-dev-multisession-onboarding-doc-frontmatter | [Frontmatter Per spec-docs](#frontmatter-per-spec-docs) | Proposed | Conforms to `req-docs-frontmatter` |
| req-dev-multisession-onboarding-doc-coverage | [Covers All Phase-1 Surfaces](#covers-all-phase-1-surfaces) | Proposed | Onboarding → smoke test → attached Claude |

### Doc Exists at Canonical Path
----
RID: `req-dev-multisession-onboarding-doc-exists`
Status: `Proposed`

The doc lives at `docs/doc-dev-multisession-onboarding.md`. The path is canonical; cross-references in other specs and docs link here.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-onboarding-doc-exists-1 | File present | Proposed | `docs/doc-dev-multisession-onboarding.md` exists in the repo. | |
| req-dev-multisession-onboarding-doc-exists-2 | Cross-references resolve | Proposed | Every link to the doc from other specs/docs resolves. | |

### Procedure Reflects Current Behavior
----
RID: `req-dev-multisession-onboarding-doc-procedure`
Status: `Proposed`

The doc's procedural steps must match the actual behavior of the system. Specifically:

- Worktree path matches [req-dev-multisession-spawn-script](spec-dev-multisession.md#spawn-script) (`~/tap-sessions/<name>`).
- Branch naming matches the spawn pattern (`session/<name>`).
- `.env.local` keys and example values match the [Fixed-by-Name Port Registry](spec-dev-multisession.md#fixed-by-name-port-registry).
- Compose invocation goes through [`scripts/dc`](spec-dev-multisession.md#env-file-cascade) so env-file cascading applies.
- TAP_GRID_ID generation uses Python 3.14's `uuid.uuid7()`.
- Migrate / seed commands match the management commands in `tap_grid/` and `tap_plugins/`.
- The smoke-test step links to [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md).
- The teardown reference links to [spec-dev-multisession-teardown.md](spec-dev-multisession-teardown.md).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-onboarding-doc-procedure-1 | Worktree path correct | Proposed | Doc uses `~/tap-sessions/<name>` and branch `session/<name>`. | |
| req-dev-multisession-onboarding-doc-procedure-2 | Override keys correct | Proposed | `.env.local` example contains exactly `COMPOSE_PROJECT_NAME`, `WEB_PORT`, `POSTGRES_PORT`, `TAP_GRID_ID`, `TAP_SESSION_LABEL`. | |
| req-dev-multisession-onboarding-doc-procedure-3 | Compose via wrapper | Proposed | All compose invocations use `scripts/dc`, not raw `docker compose`. | |
| req-dev-multisession-onboarding-doc-procedure-4 | Smoke + teardown linked | Proposed | Procedure ends with links to smoke-test and teardown specs. | |

### Frontmatter Per spec-docs
----
RID: `req-dev-multisession-onboarding-doc-frontmatter`
Status: `Proposed`

The doc carries the YAML frontmatter pattern defined in [req-docs-frontmatter](spec-docs.md#frontmatter-schema):

- Required: `spec` (this file), `audience`.
- Recommended: `covers` (the three multi-session specs and the meta-spec), `update-triggers`.
- Optional but included: `assumes`, `provides`, since the doc is LLM-targeted.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-onboarding-doc-frontmatter-1 | Required fields present | Proposed | `spec`, `audience` populated correctly. | |
| req-dev-multisession-onboarding-doc-frontmatter-2 | Update triggers populated | Proposed | `update-triggers:` lists the concrete change areas this doc depends on. | |

### Covers All Phase-1 Surfaces
----
RID: `req-dev-multisession-onboarding-doc-coverage`
Status: `Proposed`

A reader following the doc end-to-end ends up with:

1. A worktree at `~/tap-sessions/<name>`.
2. A `.env.local` carrying their port band and a fresh `TAP_GRID_ID`.
3. A running Docker stack on the assigned ports.
4. Migrations applied.
5. Plugin data seeded.
6. A Claude Code session attached inside the new worktree.
7. A clear handoff to [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md) for verification.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-onboarding-doc-coverage-1 | All seven outcomes covered | Proposed | Each numbered outcome above appears as a step or sub-step in the doc. | |

## Re-evaluation Triggers

The doc must be reviewed (and updated if needed) when any of the following change. This list is the narrative source for the doc's `update-triggers:` frontmatter; the two should stay in sync.

| Trigger | Why it matters |
| --- | --- |
| `scripts/dc` behavior or invocation | Doc tells readers to run `scripts/dc up -d --build` etc.; if the wrapper changes, examples drift. |
| `docker-compose.yml` env-var contract | Adding/removing parameterized vars (e.g. a new `REDIS_PORT`) means `.env.local` examples need updating. |
| Port registry table in `spec-dev-multisession.md` | Doc's `cli` example pulls from the registry; new bands or changes to existing ones require doc edits. |
| Worktree path or branch convention | If `~/tap-sessions/<name>` or `session/<name>` change, every step changes. |
| TAP_GRID_ID generation method | If we move off Python 3.14's `uuid.uuid7()` (e.g. to a management command), the doc's one-liner needs updating. |
| `TAP_SESSION_LABEL` convention or rendering | Doc tells readers to set `TAP_SESSION_LABEL=cli` and shows what the UI will look like; if rendering or var name changes, the doc drifts. |
| `.localhost` URL convention or `ALLOWED_HOSTS` handling | Doc tells readers to use `http://<name>.tap.localhost:<port>/`; if this breaks, instructions are misleading. |
| Migrate or seed command names | `import_plugin_grift --all` or `migrate` invocations changing breaks step 5 / step 6. |
| `spec-dev-multisession-smoketest.md` or `-teardown.md` reorganization | Doc links readers to those specs; structural changes need link audits. |
| `scripts/spawn-session.sh` shipping (Phase 2) | The manual procedure should be replaced with "run the spawn script"; this doc shifts from primary to fallback. |

When the spawn script lands (Phase 2), this doc-spec should be reviewed for whether the doc:

- becomes redundant and is deprecated, or
- is restructured to lead with the spawn-script invocation and keep the manual fallback as a secondary section.

## Linked Specs

The doc directly references:

- [spec-dev-multisession.md](spec-dev-multisession.md) — port registry, env cascade, spawn-script (future).
- [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md) — handoff target after onboarding.
- [spec-dev-multisession-teardown.md](spec-dev-multisession-teardown.md) — referenced for "how to clean up".
- [spec-docs.md](spec-docs.md) — frontmatter and conventions.

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`, `Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`, `Backlog`.
