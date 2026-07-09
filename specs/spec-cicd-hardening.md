# CI/CD Pipeline Hardening

## Philosophy

TAP's development pipeline reached a good place by instinct: trunk-based development, an
automated fail-closed gate before `main` advances, cloud CI on AWS CodeBuild, and a
parallelized promote (`~8 min`, gryphon corpus deferred to the cloud). Measured against
professional git/build/deploy practice, the **integration and testing** halves are
pro-grade to ahead of the field. What is missing is **enforcement** (the gate is a
client-side convention, not a server-enforced invariant) and the entire **deploy** half
(no artifacts, no environments, no continuous delivery, no supply-chain provenance).

This spec is a standing **doctrine + backlog**, in the same spirit as
[spec-security-posture.md](spec-security-posture.md): it states the guiding principles for
a professional CI/CD pipeline, records honestly where TAP already complies, and holds the
prioritized ladder of work to close the gaps. It is the thing a session "works through" —
requirement by requirement — to lock the pipeline down.

The core doctrine:

> A pipeline's guarantees must be **enforced where they cannot be bypassed** (server-side
> at the forge), **shifted left** (security and correctness caught at authoring/merge, not
> in production), and **built once and promoted** (immutable, versioned, signed artifacts
> move through environments — never rebuilt per environment). Measure the pipeline so its
> health is a fact, not a feeling.

The synthesizing insight that motivates most of this backlog: TAP's promote flow
**orchestrates the pipeline client-side, in a bash script** (`scripts/promote-to-main.sh`).
That script is genuinely sophisticated — atomic dual-refspec push, a transient-tolerant
CI join-poll, fail-closed gating — but because it runs on a laptop, its guarantees are a
*convention*: a direct `git push origin HEAD:main` bypasses every gate, and each session
runs its own copy of the script (they converge late). In effect TAP **hand-built a merge
queue.** The forge now ships that as a product (GitHub merge queue; Mergify; Bors), and
TAP's nearest neighbors — Backstage, Grafana, dbt, Supabase, Temporal, Hasura — nearly all
run *PR → required checks → merge queue → semver release → signed artifact*, server-enforced.
The strategic question this spec keeps live is **how long to keep hand-rolling versus
adopting forge-native primitives.** Hand-rolling buys offline capability, zero lock-in, and
total control (real assets for a solo, AI-driven flow); it costs server-side enforcement and
convergence consistency. Both are defensible — the point is to make it a *decision*.

This doctrine coexists with accepted, deliberately-deferred risk (see **Accepted Risk**
below). Pre-launch, with no customers and a solo maintainer, the deploy half is rightly
parked; this spec names it so it is tracked, not forgotten.

## What TAP Already Does Right

Named honestly so the doctrine measures against a real baseline, and so these are not
regressed while closing the gaps:

- **Trunk-based development** — short-lived session branches, frequent integration to one
  trunk. The model DORA/*Accelerate* identifies as the highest-performing.
- **Automated pre-merge gate, fail-closed** — red never advances `main`
  (`req-dev-validation-promote-hook`, `req-dev-multisession-ci-gate`).
- **Atomic pushes** — both refs advance or neither (`req-dev-multisession-push-workflow-3`).
- **Infrastructure as Code** — Terraform, state out of the repo, secret *shells* not values
  (`ci/terraform/codebuild-runners/`).
- **Least-privilege, per-lane IAM** — each CI lane grants only what it tests
  (`req-dev-validation-product-line-lanes-4`).
- **Secrets discipline** — none in the repo, a pluggable Secrets-Manager seam, health-probe
  validation (`req-plugin-depres-sources`, [spec-tap-cares-secrets](../tap_cares/specs/spec-tap-cares-secrets.md)).
- **Dependency pinning** — `uv.lock`.
- **Environment parity** — one Docker image across dev and CI.
- **Testing depth ahead of the field** — the gryphon correctness ladder (differential
  oracle + metamorphic + fuzzing) and the honest, machine-generated
  [Validation Map](spec-dev-validation.md) (`req-dev-validation-map`).

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Enforce Server-Side | The gate must be un-bypassable at the forge, not a client-side convention. |
| 2. | Shift Security Left | SAST, dependency, secret, and container scanning run as a standing CI layer, not post-incident. |
| 3. | Build Once, Promote | Produce immutable, versioned, signed artifacts and move the *same* bytes through environments. |
| 4. | Deliver Continuously | Environments, progressive delivery, and rollback — the unbuilt deploy half. |
| 5. | Measure The Pipeline | Track the four DORA metrics and flaky tests; pipeline health is a fact, not a feeling. |
| 6. | Decide, Don't Default | Choose hand-rolled vs forge-native (merge queue) deliberately; don't drift into either. |

## Prior Art

Standard, current practice this spec draws on: **trunk-based development** and the **four
DORA metrics** (deployment frequency, lead time, change-failure rate, MTTR) from
*Accelerate*; **branch protection / required status checks / merge queues** (GitHub, GitLab,
Mergify, Bors); **shift-left security** — SAST (CodeQL, Semgrep, Bandit), SCA / dependency
audit (Dependabot, `pip-audit`, Renovate), secret scanning (gitleaks, trufflehog), container
scanning (Trivy, Grype); **build-once-deploy-many** and config-in-env (12-factor); **supply
chain** — SLSA provenance levels, Sigstore/cosign signing, CycloneDX/SPDX SBOMs; **progressive
delivery** (canary, blue-green). Nearest neighbors — Backstage (changesets, versioned plugin
releases), Grafana (signed plugins + catalog), dbt (PR-gated DAG tests), Supabase / Temporal /
Hasura — share the *PR → required checks → merge queue → semver → signed artifact* shape.
TAP's **boot-record-as-BOM** is conceptually *ahead* of the SBOM curve; this spec ties it to
the standard formats and signing the ecosystem expects.

## Requirements

Ordered as the recommended sequence: the first three are cheap, foundational, build-once
edges (an afternoon each) squarely in the [security-posture](spec-security-posture.md)
cheap-edge doctrine; the rest are the larger deploy-half build, rightly deferred toward launch.

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-cicd-branch-protection | [Enforce The Gate Server-Side](#enforce-the-gate-server-side) | Proposed | Protect `main` at the forge with a bypass for the promote identity; the gate stops being bypassable. Closes the biggest hole. |
| req-cicd-security-scanning | [Shift-Left Security Scanning](#shift-left-security-scanning) | Proposed | SAST + dependency audit + secret scan + container scan as a standing CI layer. The table-stakes layer TAP conspicuously lacks. |
| req-cicd-dep-automation | [Automate Dependency Updates](#automate-dependency-updates) | Proposed | Dependabot/Renovate on `uv.lock` — pinned deps rot without it. |
| req-cicd-build-once-artifact | [Build Once, Promote The Artifact](#build-once-promote-the-artifact) | Proposed | Build one immutable, versioned image → registry (ECR); promote the same bytes. Foundation for the deploy half. |
| req-cicd-supply-chain-provenance | [Sign Artifacts, Emit SBOM](#sign-artifacts-emit-sbom) | Proposed | Sigstore/cosign signing + CycloneDX/SPDX SBOM; connect the boot-record BOM to standard formats. |
| req-cicd-continuous-delivery | [Continuous Delivery](#continuous-delivery) | Proposed | Environments (staging/prod), progressive delivery, and a rollback path. The unbuilt deploy half. |
| req-cicd-pipeline-observability | [Measure The Pipeline](#measure-the-pipeline) | Proposed | The four DORA metrics + systematic flaky-test tracking. |

### Enforce The Gate Server-Side

RID: `req-cicd-branch-protection`

`origin/main` is **not** branch-protected (confirmed: the GitHub API returns *"Branch not
protected"*). TAP's entire safety story — tests, gates, atomic push — lives in
`scripts/promote-to-main.sh`, so a direct `git push origin HEAD:main`, a buggy script, or a
second contributor bypasses 100% of it. Add a forge **branch protection rule / ruleset** on
`main`: no direct pushes, require the product-lines CI status check to pass, require linear
history. This turns the gate from *"the way we do it"* into *"the only way it can be done."*

| RID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-branch-protection-1 | Protect main | Proposed | Ruleset on `main`: block direct pushes, require the CI check, require linear history / signed commits (optional). | Server-enforced floor for *everyone and everything* else. |
| req-cicd-branch-protection-2 | Bypass for the promote identity | Proposed | The promote does a direct atomic push, which "require PR" would block. Grant a ruleset **bypass** to the promote/bot identity so the hand-rolled flow survives while the floor holds for all else. | Keeps the client-side flow; adds the server-side backstop. The alternative — adopt a PR/merge-queue flow — is the [Goal 6](#goals) decision, tracked but not forced here. |

### Shift-Left Security Scanning

RID: `req-cicd-security-scanning`

Confirmed: **zero** SAST / SCA / secret-scan / container-scan / SBOM tooling in the repo.
For a project whose [CLAUDE.md](../CLAUDE.md) makes security a standing filter, this is the
loud omission — the cheap, standard layer everyone runs. Each sub-requirement is roughly a
half-day to wire and directly serves the [security posture](spec-security-posture.md).

| RID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-security-scanning-1 | Secret scanning | Proposed | gitleaks/trufflehog in CI (and ideally pre-commit) — catch a committed credential before it is public. | Cheapest, highest-value. Complements the "no secrets in repo" discipline. |
| req-cicd-security-scanning-2 | Dependency / vuln audit | Proposed | `pip-audit` (and/or GitHub Dependabot alerts) over `uv.lock`. | Pairs with `req-cicd-dep-automation`. |
| req-cicd-security-scanning-3 | SAST | Proposed | CodeQL (free for this repo) or Semgrep/Bandit on the Python surface. | Shift-left static analysis. |
| req-cicd-security-scanning-4 | Container image scan | Proposed | Trivy/Grype on the built web image. | Pairs with `req-cicd-build-once-artifact` once images are published. |

### Automate Dependency Updates

RID: `req-cicd-dep-automation`

TAP pins (`uv.lock`) but pinned dependencies rot — security patches do not land until
someone notices. Enable **Dependabot or Renovate** to open update PRs (grouped, on a cadence).
Composes with `req-cicd-security-scanning-2` (the audit tells you *what* is vulnerable; the
bot *fixes* it) and, once server-side gating exists, the update PRs flow through the same
required checks.

### Build Once, Promote The Artifact

RID: `req-cicd-build-once-artifact`

Confirmed: CI builds an image and throws it away; every environment rebuilds. The
professional pattern is **build one immutable, versioned artifact → push to a registry
(ECR) → promote that exact bytes through environments** (build-once-deploy-many). This is
the foundation the whole deploy half sits on, and the natural home for the parked
template-bake idea (bake the migrated DB into the image). Requires image versioning/tagging
and a registry; ties to eventual product release versioning (semver for the app, not just
plugins).

### Sign Artifacts, Emit SBOM

RID: `req-cicd-supply-chain-provenance`

No artifact signing (Sigstore/cosign — notable given a `sigstore_core` plugin exists), no
SLSA provenance, no SBOM (CycloneDX/SPDX). TAP's **boot-record-as-BOM** is conceptually
ahead — it is a declarative, verified bill of materials — but it is not yet connected to the
standard formats and signing the ecosystem consumes. Grafana signing every plugin is the
nearest-neighbor precedent. Sequenced after `req-cicd-build-once-artifact` (you sign and
attest the artifact you publish).

### Continuous Delivery

RID: `req-cicd-continuous-delivery`

The entire deploy half is unbuilt: no staging/prod **environments**, no deploy automation,
no **progressive delivery** (canary/blue-green), no **rollback** path, no product-level
release versioning. This is *expected* pre-launch and is parked by the
[Rampart roadmap](../plan/road-rampart.md) for post-launch — named here so it is tracked,
not a blind spot. TAP has **CI, not CI/CD**: "promote to main" is *integration*, not
*deployment*. Depends on `req-cicd-build-once-artifact` (you deploy the artifact you built).

### Measure The Pipeline

RID: `req-cicd-pipeline-observability`

No measurement of the four **DORA metrics** (deployment frequency, lead time for changes,
change-failure rate, MTTR) and no systematic **flaky-test tracking** (flakes are fixed
reactively today). The instinct already exists in the gryphon findings/fuzz-campaign ledgers
— this applies the same pattern to the pipeline itself. Lower priority pre-launch; it becomes
load-bearing once there is a delivery cadence to improve.

## Accepted Risk (deliberately deferred, not hidden)

- **The deploy half** (`req-cicd-continuous-delivery`, `req-cicd-supply-chain-provenance`,
  `req-cicd-build-once-artifact`) is parked pre-launch — no customers, no environments to
  deliver to yet. Right call; tracked for launch-time.
- **Client-side orchestration** remains the model for now (Goal 6). Its bypassability is
  mitigated the moment `req-cicd-branch-protection` lands; its convergence lag (per-session
  script copies) is accepted for a solo flow.
- **Tier-0 local Postgres** runs with `fsync=off` — a corruption-on-unclean-shutdown risk
  and a minor dev/prod parity divergence, accepted because the dev/test cluster is
  reproducible (see `docker-compose.yml`).

## Relationship To Other Specs

- [spec-dev-validation.md](spec-dev-validation.md) owns the *validation surfaces* and the
  Validation Map (what runs, what it proves, honest guard status). This spec owns the
  *pipeline enforcement + delivery* posture around them.
- [spec-dev-multisession.md](spec-dev-multisession.md) owns the promote/push workflow this
  spec proposes to enforce server-side.
- [spec-security-posture.md](spec-security-posture.md) is the parent doctrine: the first
  three requirements here are its cheap-foundational-edges applied to the pipeline.
- [plan/road-rampart.md](../plan/road-rampart.md) sequences the deploy half toward launch.
