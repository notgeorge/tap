# AWS Steampipe Tooling Specification

## Philosophy

The AWS Steampipe collector (`spec-aws-steampipe-collector-v0.md`) shells out
to the `steampipe` binary plus its native AWS plugin. Steampipe is a non-Python
external tool — not a pip/uv dependency, not a Debian package — so it cannot be
"loaded" the way a Python plugin's dependencies are, and per the
plugin-config-in-shared-infrastructure rule it must **not** be baked into the
core image or `docker-compose`.

This specification is the **aws_core-local proving ground** for acquiring and
configuring that tool. It documents *exactly* how `aws_core` does it — behind
the `req-plugin-load-v0-standup-hook` seam (`spec-plugin-load-lifecycle-v0.md`)
— so the system runs first and the reusable pattern is generalized later *from
this evidence*. It is deliberately **not** a general plugin tool framework: the
durable model (declarative manifest schema, a core resolver API, OS/arch and
multi-arch handling, sandboxed/outpost execution) is explicitly out of scope
and is generalized separately once this proving ground has yielded its lessons.

Grounded facts established by the Phase-0 spike and direct checks (2026-05-17),
which this spec is built on:

- The dev container is `linux/aarch64` (arm64), glibc 2.41.
- No `curl`/`wget` in the image — network fetch uses Python `urllib` (the
  confirmed-working path the KSI collector already uses).
- Steampipe is not apt-installable; it is distributed as a GitHub-release
  tarball. Its AWS plugin is steampipe-native (`steampipe plugin install aws`),
  never a system package.
- Steampipe is not a single static binary: it manages an embedded
  Postgres/FDW and needs a writable install/data dir
  (`STEAMPIPE_INSTALL_DIR`). The unit acquired is a *tool environment*, not a
  file.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Self-Contained | Every acquisition action, script, directory, and state file lives inside `plugins/aws_core/`; zero core image / compose / settings change |
| 2. | Standup-Driven | Provisioning runs through the plugin's standup hook — idempotent, fast-on-hit, never in `ready()` |
| 3. | Pinned & Verified | Exact Steampipe + AWS-plugin versions; sha256-verified download |
| 4. | Pure Self-Test | The collector self-test reports and points at standup; it never provisions |
| 5. | Honest Seams | Generalization candidates are recorded here as they are hit, not hand-waved |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-aws-steampipe-tooling-scope | [Proving-Ground Scope](#proving-ground-scope) | Proposed | aws_core-local, deliberately not general; generalized later from evidence |
| req-aws-steampipe-tooling-layout | [Plugin-Owned Layout](#plugin-owned-layout) | Proposed | Committed manifest/scripts + gitignored provisioned payload, all under the plugin |
| req-aws-steampipe-tooling-standup | [Standup Acquisition](#standup-acquisition) | Proposed | The aws_core standup hook: idempotent fetch + verify + plugin-install |
| req-aws-steampipe-tooling-resolution | [Tool Resolution & Pure Self-Test](#tool-resolution--pure-self-test) | Proposed | Collector/self-test resolve from the plugin path, never system PATH |
| req-aws-steampipe-tooling-platform | [Platform Pin](#platform-pin) | Proposed | Hard linux/arm64 pin; loud detected-vs-expected failure; multi-arch deferred |
| req-aws-steampipe-tooling-seams | [Generalization Seams](#generalization-seams) | Proposed | The running, non-hand-waved list feeding the deferred general framework |

### Proving-Ground Scope
----
RID: `req-aws-steampipe-tooling-scope`
Status: `Proposed`

This spec governs only how `aws_core` acquires and configures Steampipe for its
own collector. It is a deliberately scoped proving ground.

#### Implementation
- In scope: the aws_core standup hook implementation, the plugin-owned tool
  layout, version pinning + verification, tool resolution, the platform pin,
  and the recorded generalization seams.
- Out of scope (generalized later, from this evidence, not designed here): a
  declarative cross-plugin tool manifest schema, a core tool-resolver API,
  multi-arch matrices, gitignore conventions as a standard, and sandboxed
  "outpost" tool execution. These are tracked against the
  `req-plugin-load-v0-standup-hook` Future and the deferred general model.
- This spec depends on the `req-plugin-load-v0-standup-hook` seam for its
  invocation contract; it does not restate that seam.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-tooling-scope-1 | aws_core-Local Only | Proposed | This spec defines Steampipe acquisition for `aws_core` only; it does not define a general plugin tool mechanism. | |
| req-aws-steampipe-tooling-scope-2 | Evidence-First Generalization | Proposed | The reusable pattern is generalized later from this proving ground, not designed up front. | |
| req-aws-steampipe-tooling-scope-3 | Seam Dependency | Proposed | Invocation relies on `req-plugin-load-v0-standup-hook`; this spec does not restate or fork it. | |

### Plugin-Owned Layout
----
RID: `req-aws-steampipe-tooling-layout`
Status: `Proposed`

Everything Steampipe-tooling-related lives under `plugins/aws_core/`.

#### Implementation
- Committed (small, reviewable, in git):
  - a pinned tool manifest/lockfile (Steampipe version, AWS-plugin version,
    per-`(os,arch)` release URL + sha256) under the plugin;
  - the standup command and any helper scripts (Python; `urllib` fetch).
- Gitignored (provisioned payload, never committed — the Steampipe binary +
  AWS plugin run to ~150MB+):
  - the extracted `steampipe` binary, and
  - a plugin-owned writable `STEAMPIPE_INSTALL_DIR` (the AWS plugin and
    Steampipe's embedded-DB/config state).
- No file outside `plugins/aws_core/` changes for acquisition. The only core
  surface used is the generic `plugin_standup` runner from the lifecycle seam.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-tooling-layout-1 | All Within Plugin | Proposed | Every directory and state file used is under `plugins/aws_core/`. | Guardrail 2 from the design decision. |
| req-aws-steampipe-tooling-layout-2 | Manifest Committed, Payload Gitignored | Proposed | The pinned manifest + scripts are committed; the binary + writable install dir are gitignored. | Repo stays lean. |
| req-aws-steampipe-tooling-layout-3 | No Shared-Infra Change | Proposed | Acquisition changes no `Dockerfile`/`docker-compose`/core settings. | |

### Standup Acquisition
----
RID: `req-aws-steampipe-tooling-standup`
Status: `Proposed`

`aws_core` implements its `req-plugin-load-v0-standup-hook` as a plugin-owned
management command that idempotently makes Steampipe present at the pinned
state.

#### Implementation
On invocation the command:

1. **Fast check (hit path):** if the plugin-owned binary exists and reports the
   pinned Steampipe version, and the AWS plugin is present at its pinned
   version in the plugin-owned `STEAMPIPE_INSTALL_DIR`, return success without
   network I/O. This keeps every stand-up cheap.
2. **Acquire (miss path):** fetch the pinned `steampipe_linux_arm64` tarball
   from the manifest URL via `urllib`, verify sha256 against the manifest,
   extract into the plugin-owned tool dir.
3. **Configure:** run `steampipe plugin install aws@<pinned>` with
   `STEAMPIPE_INSTALL_DIR` pointed at the plugin-owned writable dir.
4. **Record:** write/refresh a plugin-owned state file recording the installed
   versions so step 1 is exact, not heuristic.

The command is idempotent and safe to run on every stand-up. It is invoked by
the generic `manage.py plugin_standup` runner (lifecycle seam), and may also be
run directly for debugging. It performs no graph-state mutation
(`req-plugin-load-v0-standup-hook-4`).

#### Development
The simplest thing that runs is documented first. Steampipe's embedded-service
and concurrency lifecycle (multiple sessions/jobs invoking `steampipe query`
against a plugin-local dir) is a known unknown — see
[Generalization Seams](#generalization-seams). v0 uses single-shot
`steampipe query` with a plugin-local dir and does not solve concurrent service
lifecycle.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-tooling-standup-1 | Idempotent | Proposed | Re-running with the pinned state already present is a fast no-op with no network I/O. | |
| req-aws-steampipe-tooling-standup-2 | Fetch + Verify | Proposed | The tarball is fetched via `urllib` and sha256-verified against the manifest before use. | No curl/wget in image. |
| req-aws-steampipe-tooling-standup-3 | Plugin Install | Proposed | `steampipe plugin install aws@<pinned>` runs into the plugin-owned `STEAMPIPE_INSTALL_DIR`. | |
| req-aws-steampipe-tooling-standup-4 | State Recorded | Proposed | A plugin-owned state file records installed versions for an exact hit-path check. | |
| req-aws-steampipe-tooling-standup-5 | No Graph Mutation | Proposed | Standup performs no TAP-managed graph-state mutation. | Per `req-plugin-load-v0-standup-hook-4`. |

### Tool Resolution & Pure Self-Test
----
RID: `req-aws-steampipe-tooling-resolution`
Status: `Proposed`

#### Implementation
- The collector and the self-test resolve the Steampipe binary from the
  plugin-owned path **only** — never system `PATH`. (v0: an aws_core-internal
  resolver helper; a core resolver API is a deferred generalization, not built
  here.)
- The collector self-test (`STEAMPIPE_AVAILABLE`) remains a **pure check**: if
  the binary/AWS-plugin is absent or off the pinned version it reports
  `error`/`fail` and points at the standup path. It never fetches, extracts, or
  installs. (This records the deliberately dropped "provision inside self-test"
  design — `req-plugin-load-v0-standup-hook-5`.)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-tooling-resolution-1 | Plugin Path Only | Proposed | Collector + self-test resolve Steampipe from the plugin-owned path, never system `PATH`. | |
| req-aws-steampipe-tooling-resolution-2 | Self-Test Is Pure | Proposed | Self-test reports + points at standup on a miss; it never provisions. | |

### Platform Pin
----
RID: `req-aws-steampipe-tooling-platform`
Status: `Proposed`

#### Implementation
- v0 ships exactly one manifest entry: `linux/arm64`, glibc (the confirmed dev
  container). Standup and self-test detect the running platform and **fail
  loudly with detected-vs-expected** on any mismatch — never a silent wrong
  binary.
- `linux/amd64` and multi-arch are explicitly a named future-seam (it bites the
  moment server-side CI or a non-Apple-Silicon runtime appears).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-tooling-platform-1 | Single Pinned Platform | Proposed | v0 pins `linux/arm64`; the manifest carries that one entry. | |
| req-aws-steampipe-tooling-platform-2 | Loud Mismatch | Proposed | A platform other than the pinned one fails loudly with detected-vs-expected, never silently. | |
| req-aws-steampipe-tooling-platform-3 | Multi-Arch Deferred | Proposed | `linux/amd64`/multi-arch is a named seam, not built in v0. | |

### Generalization Seams
----
RID: `req-aws-steampipe-tooling-seams`
Status: `Proposed`

The proving ground's primary output, besides a working collector, is this
honest list (guardrail 3: note seams as we go, never hand-wave). It feeds the
deferred general plugin tool/binary model; entries are appended as the
implementation hits them.

#### Implementation
Initial seams:

- **Resolver → core API.** The aws_core-internal binary resolver is the first
  candidate to promote to a shared `tap_plugins` tool-resolver.
- **Manifest/lockfile format.** The aws_core pinned-tool manifest is the
  prototype of a standard cross-plugin tool-manifest schema.
- **Generic runner relationship.** How the aws_core standup command behaves
  under `manage.py plugin_standup --all` informs the generic runner's contract
  (exit codes, partial failure, ordering).
- **Gitignore convention.** The pattern for ignoring provisioned payloads while
  committing manifests should become a documented standard.
- **Steampipe service/concurrency lifecycle.** Multiple sessions/jobs running
  `steampipe query` against a plugin-local dir — embedded-service startup,
  locking, port/socket contention — is a known unknown documented here, not
  solved in v0.
- **Self-test live-check budget vs. tool cold-start (surfaced by the proving
  ground, 2026-05-17).** A one-shot `steampipe query` cold-starts the embedded
  Postgres/FDW service, so the `AWS_IDENTITY` live check cannot meet
  `tap_cares` `req-tap-cares-collector-self-test-12`'s ≤5s per-live-check
  budget (observed: timeout at 5s while `STEAMPIPE_AVAILABLE` passed). This is
  a real spec-vs-reality tension, not a tunable to silently bump. Resolution is
  a deliberate decision recorded for the user/strategy: keep a warm
  `steampipe service`, make the self-test budget per-collector, or make
  `AWS_IDENTITY` not a phase-1 ≤5s live check. The tooling acquisition itself
  is proven independent of this.
- **Outpost execution.** The satellite/outpost vision (the tool runs off-host
  for a sandboxed collector) is the long-horizon seam this is a step toward.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-steampipe-tooling-seams-1 | Seams Recorded As Hit | Proposed | Generalization candidates are appended here when encountered, with enough context to act on later. | |
| req-aws-steampipe-tooling-seams-2 | Feeds The General Model | Proposed | This list is the explicit input to the deferred general plugin tool/binary spec; it is not itself that spec. | |

#### Future
When the general model is specified, it is built by consuming this list and the
`req-plugin-load-v0-standup-hook` Future, not by re-deriving requirements from
scratch. This spec then becomes the reference implementation / first adopter,
not the contract.
