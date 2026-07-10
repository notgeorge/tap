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
| req-cicd-base-image-sourcing | [Source Base Images Off Anonymous Docker Hub](#source-base-images-off-anonymous-docker-hub) | Implemented | Container base images resolve from AWS's credential-free public ECR mirror, not docker.io — removes the anonymous-pull `429` single point of failure on the promote gate. First cheap edge landed. |
| req-cicd-base-image-lifecycle | [Self-Host Base-Image Currency + Minimization](#self-host-base-image-currency--minimization) | Proposed | **Wolfi is the standard base** (`-3`, decided 2026-07-09; spike: OS-CVEs 311→0), carrying exactly TAP's runtime binaries, plus a self-hosted auto-patch loop + CVE gate instead of a managed hardened catalog. **FIPS is on by default** (`-6`), via the self-built OpenSSL 3.0 #4282 provider (`-5`, spike-proven end-to-end 2026-07-09), selected by `ARG TAP_FIPS=1` and asserted fail-closed at boot. Alternatives (DHI, UBI-micro) are **parked, not eliminated**. Docs: [doc-hardened-base-image-landscape](../docs/misc/doc-hardened-base-image-landscape.md) (landscape) · [doc-fips-assessment-record](../docs/misc/doc-fips-assessment-record.md) (FIPS decisions, lessons, verification suite). |
| req-cicd-branch-protection | [Enforce The Gate Server-Side](#enforce-the-gate-server-side) | Proposed | Protect `main` at the forge with a bypass for the promote identity; the gate stops being bypassable. Closes the biggest hole. |
| req-cicd-security-scanning | [Shift-Left Security Scanning](#shift-left-security-scanning) | Proposed | SAST + dependency audit + secret scan + container scan as a standing CI layer. The table-stakes layer TAP conspicuously lacks. |
| req-cicd-dep-automation | [Automate Dependency Updates](#automate-dependency-updates) | Proposed | Dependabot/Renovate on `uv.lock` — pinned deps rot without it. |
| req-cicd-build-once-artifact | [Build Once, Promote The Artifact](#build-once-promote-the-artifact) | Proposed | Build one immutable, versioned image → registry (ECR); promote the same bytes. Foundation for the deploy half. |
| req-cicd-supply-chain-provenance | [Sign Artifacts, Emit SBOM](#sign-artifacts-emit-sbom) | Proposed | Sigstore/cosign signing + CycloneDX/SPDX SBOM; connect the boot-record BOM to standard formats. |
| req-cicd-continuous-delivery | [Continuous Delivery](#continuous-delivery) | Proposed | Environments (staging/prod), progressive delivery, and a rollback path. The unbuilt deploy half. |
| req-cicd-pipeline-observability | [Measure The Pipeline](#measure-the-pipeline) | Proposed | The four DORA metrics + systematic flaky-test tracking. |

### Source Base Images Off Anonymous Docker Hub

RID: `req-cicd-base-image-sourcing`

The promote gate's cloud CI (`product-lines.yml`, the `test_all` lane gating **every** promote
to `origin/main`) builds the web image on a GitHub Actions runner, and that build pulled its
base image **anonymously from `docker.io`**. GHA's hosted runners share a pool of egress IPs
across all of GitHub's customers, so Docker Hub's anonymous per-IP pull limit is frequently
already exhausted at push time → `429 Too Many Requests` on the manifest HEAD → `buildx` dies
in ~25s → the promote aborts. This is a **nondeterministic single point of failure on the
critical path to shipping anything** — not specific to any one change (it blocked a passkey
promote three times running, 2026-07-09), with no backpressure we control. Two base images
were exposed: `python:3.14-slim` (`Dockerfile`) and `postgres:16-alpine` (`docker-compose.yml`).

**Fix (the cheap, foundational edge):** resolve Docker Official Images through **AWS's public
ECR mirror** (`public.ecr.aws/docker/library/<image>`) — a credential-free mirror not subject
to Docker Hub's limit. Two one-line base changes; no new secret, no new infra; self-applying
(the commit that swaps the base is the commit whose CI uses it, so it lands through the gate
without a lucky retry) and it fixes local dev too. This is the `spec-security-posture.md`
cheap-edge play: near-zero marginal cost now, removes a class of availability failure.

| RID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-base-image-sourcing-1 | No anonymous Docker Hub base pulls | Implemented | No build/dev/CI base image is pulled anonymously from `docker.io`; all Docker Official Images resolve via `public.ecr.aws/docker/library/*`. | `Dockerfile` (`python:3.14-slim`) + `docker-compose.yml` (`postgres:16-alpine`). |
| req-cicd-base-image-sourcing-2 | Rate-limit-free promote gate | Implemented | The promote gate's image build no longer depends on Docker Hub's anonymous quota, so a shared-runner IP exhaustion cannot red the gate. | Removes the observed `429` SPOF. |

**Named residual (deferred, not hidden):** we still trust AWS's mirror rather than a copy we
pin and control, and tags are mutable. Full supply-chain control — a **private ECR pull-through
cache with digest-pinned bases** (and, later, hardened/minimized base images; see the
base-image-strategy survey) — is deferred and composes with `req-cicd-build-once-artifact` /
`req-cicd-supply-chain-provenance`. The v0 edge buys availability now; provenance is the next
layer when air-gap/attestation demand arrives.

### Self-Host Base-Image Currency + Minimization

RID: `req-cicd-base-image-lifecycle`

Sourcing base images off a rate-limit-free mirror (`req-cicd-base-image-sourcing`) fixes
*availability*; it does nothing for *attack surface* or *CVE currency*. The market answer is a
paid managed-hardened-image catalog (Chainguard, Docker Hardened Images, Red Hat Hardened
Images, Minimus). TAP's answer is to **self-host the same two properties — currency and
minimization — with free/OSS tooling**, keeping the runtime-install architecture intact and
avoiding a per-image subscription — even the hard FIPS requirement (`-5`) is met by
**self-building the free OpenSSL 3.0 #4282 provider**, not by buying a validated image. The
full landscape survey, the decision criteria, the re-evaluation triggers, and the FIPS
recipe live in the doc: [doc-hardened-base-image-landscape](../docs/misc/doc-hardened-base-image-landscape.md).
The **FIPS decision record, lessons learned, assessment methodology, and a re-runnable
verification suite** — written as a handoff artifact for a future AI or human assessor —
live in [doc-fips-assessment-record](../docs/misc/doc-fips-assessment-record.md).

**Grounding evidence (spike, 2026-07-09).** A real build of `cgr.dev/chainguard/wolfi-base`
+ `apk add python-3.14 git bash postgresql-client curl` + the copied `uv` binary: Python
**3.14.6** present (Wolfi tracks latest — Google Distroless / UBI lag on Debian/RHEL Python),
TAP's full dependency closure `uv sync`'d cleanly (glibc manylinux wheels, no source builds —
the Alpine/musl trap avoided), the from-git plugin path worked (`git ls-remote` over TLS), and
Trivy OS-package CVEs came in at **0, versus 311 (8 critical / 63 high) on `python:3.14-slim`** —
*with* git/bash/uv still on board.

**Corrected decision criterion (2026-07-09).** An earlier draft claimed the base must ship a
**package manager** because TAP installs deps + plugins at runtime, and on that basis ruled out
every fixed/distroless image. **That reasoning is wrong and is retracted.** `uv sync` and
`uv pip install git+https://…` are *Python-package* operations, not *OS-package* operations:
they need `python`, `uv`, `git`, `bash` (+ `sed`/`grep`/`coreutils`), all of which can be baked at
**build** time by any means. TAP's own `Dockerfile` already demonstrates this —
`COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/` installs `uv` with no package manager
involved. Proven by spike (`spikes/distroless/`, both `BUILD_EXIT=0`): a **true distroless**
runtime (`cgr.dev/chainguard/python:latest` — no `apk`, no `apt`, not even `/bin/sh`) and a
`ubi9/ubi-micro` runtime built via Red Hat's `dnf --installroot` both run `uv sync` of TAP's real
closure *and* the from-git plugin install with **zero package manager present**.

Wolfi is therefore chosen on criteria that actually hold, not on a false constraint:

1. **Python-3.14 currency.** `requires-python = ">=3.14"` is the hard filter. Measured: Wolfi
   **3.14.6**, UBI9 `python3.14` **3.14.5**, Google Distroless `python3-debian13` **3.13.5** (out).
2. **In-image, host-independent FIPS.** The load-bearing difference (see `-5`). Upstream OpenSSL
   lets the *image* turn FIPS on. Red Hat **deliberately disables `openssl fipsinstall`** and
   derives FIPS from the **host kernel** (`fips=1`) — a container we ship cannot enable it alone.
   For a self-hosted product on customer-controlled hosts, in-image FIPS is the only portable answer.
3. **A measured zero-CVE floor** and a vendor that rebuilds nightly, with `apko`/`melange` as the
   free, OSS, vendor-independence hedge (build our own image from the Wolfi feed, no subscription).

**Alternatives are PARKED, not eliminated** (2026-07-09) — see the doc for the full measured
matrix and `spikes/distroless/README.md` for the working builds. Reopen if: (a) the compliance
authority **rejects vendor-affirmed OE** portability (then the RHEL/host-FIPS path becomes
correct, and `ubi-micro` + `dnf --installroot` is already proven to work); (b) we adopt a
bake-once model; or (c) Wolfi's Python currency or CVE floor regresses. Docker Hardened Images
live at **`dhi.io`** (not `docker.io`) and require an authenticated pull (**HTTP 401** anonymous),
which cuts against `req-cicd-base-image-sourcing`'s anonymous-pull property; their free
`3.14-fips` variant is **unverified**.

| RID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-base-image-lifecycle-1 | Digest-pinned auto-patch loop | Proposed | Base images are digest-pinned; **Renovate** (self-hosted GHA cron, not the Mend app — keeps repo-write in-house) opens digest + `uv.lock` bump PRs and **auto-merges on a green `test_all` lane**. | Composes `req-cicd-dep-automation`. **Depends on `req-cicd-branch-protection`**: bot auto-merge to `main` must be CI-gated server-side, else it bypasses the promote gate. Dependabot can't update `uv.lock` or track `cgr.dev` → Renovate. Keep Dependabot *Alerts* on for the native advisory feed. |
| req-cicd-base-image-lifecycle-2 | Image CVE gate | Proposed | A Trivy (or Grype) High/Critical OS+dep CVE gate runs in CI on the built image; optional Copacetic in-place patch for the upstream-lag window. | Realizes `req-cicd-security-scanning-4`. The spike's 311→0 is this gate's baseline signal. |
| req-cicd-base-image-lifecycle-3 | Curated-minimal Wolfi base — **the standard base** | Proposed · **decided 2026-07-09** | The web **and** DB image bases become a curated-minimal **Wolfi** base carrying exactly TAP's runtime binaries (`python-3.14 git bash coreutils sed grep postgresql-client` + copied `uv`). **Wolfi is now the standard base; alternatives are parked** (see the corrected criterion above). Start: `wolfi-base` + `apk` (digest-pinned via `-1`). Graduate: self-built **apko/melange** image (reproducible, our registry, self-generated SBOM) — this is also the vendor-independence hedge, since the Wolfi feed is Apache-2.0 and free of any subscription. | `git`/`bash`/`curl` are **named, itemized attack-surface line-items**, present because the runtime-plugin-install architecture requires them and kept current by `-1`. `sed`/`grep`/`coreutils` are **not optional**: git's porcelain in `/usr/libexec/git-core` are shell scripts, so `uv pip install git+https://…` (which runs `git submodule update`) fails with `sed: command not found` without them (spike-found). The base need not ship a package manager at runtime (`spikes/distroless/`) — Wolfi is chosen on Python-3.14 currency, in-image FIPS, and CVE floor, not on `apk`. |
| req-cicd-base-image-lifecycle-4 | Minimal-binary off-ramps | Proposed | Named levers to shrink the binary set when cost/benefit flips — **not now** (`git` = 0 CVEs on Wolfi today). (A) Watch **uv #12324** (embedded git via gitoxide): if it ships, delete `git` for free. (B) An `archive`-tarball plugin source type (`https://forge/.../archive/<sha>.tar.gz`, fetched by uv's own HTTPS, sha256-pinned like the boot record) drops **both `git` and `curl`** — take it when we adopt the bake-once variant. | End-state minimum runtime = `python + uv + app` (+ psql for snapshot, a POSIX-sh/Python entrypoint instead of bash). Off-ramps are byproducts of the bake-once move, not standalone chores. |
| req-cicd-base-image-lifecycle-5 | FIPS crypto — self-built OpenSSL 3.0 #4282 | **Spike-proven** · targeted ~2026-09 | **Hard requirement (not demand-gated).** Web + DB containers execute crypto through the **free upstream OpenSSL 3.0.9 FIPS provider (CMVP #4282)** — no vendor/Chainguard module. Build the validated `fips.so` per the #4282 security policy in a builder stage; run it against the base's **modern libcrypto** (OpenSSL guarantees a certified `fips.so` is binary-compatible with any *later* libcrypto → no OpenSSL-3.0-LTS-EOL exposure); activate with `openssl fipsinstall` (integrity MAC, run **in-image**) + an `openssl.cnf` setting `default_properties = fips=yes` + `ENV OPENSSL_CONF`. Python stdlib crypto inherits it with **NO Python rebuild** (Wolfi's python dynamically links system OpenSSL); `cryptography`/`webauthn` need **`--no-binary cryptography`** (its wheel bundles its own OpenSSL) built against system OpenSSL, baked at build time, with `CRYPTOGRAPHY_OPENSSL_NO_LEGACY=1`. Algorithms (P-256, SHA-256, HMAC, PBKDF2, AES-GCM) all FIPS-approved → no redesign. **Spike (2026-07-09, `spikes/fips/Dockerfile.fips`) proved every step end-to-end:** 3.0.9 `fips.so` built on Wolfi; Wolfi's system OpenSSL **3.6.3** `fipsinstall`'d + self-tested it (binary-compat confirmed); providers activate (md5 refused); Python stdlib `_hashlib` md5 blocked with no rebuild; `cryptography 49.0.0 --no-binary` links system OpenSSL and does **P-256 ECDSA verify** (the passkey path) through FIPS while md5 → `InternalError`. Config gotchas now in the recipe: (a) `openssl_conf` MUST precede `.include fipsmodule.cnf` (else it's swallowed into `[fips_sect]` and no providers activate); (b) re-`.include /etc/ssl/ca.cnf`, which pointing `OPENSSL_CONF` at our file otherwise displaces (breaks `openssl req`; TLS trust unaffected); (c) **an empty `ossl-modules/` is NOT evidence of the crypto boundary** — `default`/`base` are compiled into `libcrypto`, not files, so the *config* is the boundary and must be treated as an integrity-critical asset. See [doc-hardened-base-image-landscape](../docs/misc/doc-hardened-base-image-landscape.md) § Spike evidence. | Named risks: (1) **OE vendor-affirmed portability** — Wolfi isn't a tested operational environment in #4282's policy. **ACCEPTED + OWNED (George, 2026-07-09)**, not a blocker: the fallback is a base-image swap (Chainguard validated-FIPS image, same family) rather than a rewrite. See the residuals below for the full escalation ladder; (2) `fips=yes` disables non-approved algos globally — audit Django/deps for import-time MD5/etc. (`usedforsecurity=False`); (3) `fipsinstall` must run in-image + re-run if `fips.so` bytes change. Postgres = identical recipe on a minimal `wolfi-base` + `apk postgresql-16` image. |
| req-cicd-base-image-lifecycle-6 | FIPS build mode — flagged, **default on** | Proposed | The `-5` recipe is selected by a single build flag, `ARG TAP_FIPS` (**default `1`**), on both the web and DB images. `TAP_FIPS=1` builds the validated 3.0.9 `fips.so`, runs `openssl fipsinstall` in-image, writes the FIPS `openssl.cnf`, and sets `ENV OPENSSL_CONF`; `TAP_FIPS=0` skips all of it and leaves the stock provider set. **`cryptography` is built `--no-binary` in BOTH modes** so the dependency closure and the system-OpenSSL linkage are identical and only *provider activation* differs — otherwise non-FIPS silently passes on a bundled-OpenSSL wheel and FIPS breaks at the far end of the pipeline. The image **declares its own mode machine-legibly**: OCI label `org.tap.fips=true|false` + `ENV TAP_FIPS_MODE`, so CI, the boot record, `/healthz`, and an AI operator can all read the posture without executing crypto. **FIPS-on is the default and the published artifact; `TAP_FIPS=0` is an explicitly-requested escape hatch, never a silent fallback.** | **Assert, don't assume (fail closed).** A boot check must *prove* the declared mode: when `TAP_FIPS_MODE=1`, verify the `fips` provider is active **and** that a non-approved primitive is actually refused (`_hashlib.new("md5")` raises), else emit `TAP-ABORT` and refuse to serve. Never infer FIPS from the absence of an error — the spike's first pass "parsed" a config that activated **nothing** and silently ran the default provider. Adds a validation surface ⇒ needs a [Validation Map](spec-dev-validation.md) row (`req-dev-validation-map`) in the implementing change. CI builds and gates **both** variants so `TAP_FIPS=0` cannot rot. |

**Named residuals + triggers (deferred, not hidden):**
- We own the **rebuild cadence + break-glass** when an auto-patch PR reds (the price of not buying an SLA).
- Until `-3` graduates to self-built apko, we trust `cgr.dev`'s `wolfi-base` (mutable tag → digest-pin via `-1`).
- **FIPS is decided** (`-5`/`-6`): self-built OpenSSL 3.0 #4282 provider, no vendor module, **on by default**. **OE vendor-affirmed portability is an ACCEPTED, OWNED risk (George, 2026-07-09)** — not a blocker. It is cheap to be wrong about because every fallback is a **base-image swap, not a rewrite** (the payoff of staying in the Wolfi family). Ladder, cheapest first: (1) swap to **Chainguard's validated FIPS image** — same family, our `fips.so`/`fipsinstall` steps fall away, `--no-binary cryptography` + the fail-closed boot assertion still mandatory, near-zero switching cost; (2) evaluate **DHI's free `3.14-fips`** (`dhi.io`, $0 — **UNVERIFIED**: 401 on pull, FIPS activation model unconfirmed); (3) last resort **UBI + host-derived FIPS** (already-proven `ubi-micro` + `dnf --installroot`; RHEL 9 *is* a tested OE, but the deployment host must run `fips=1`, which we cannot guarantee on customer infrastructure). Full analysis: [doc-fips-assessment-record](../docs/misc/doc-fips-assessment-record.md) § 7.1.
- **`fips=yes` vs non-approved primitives — audited, not assumed** (spike `spikes/fips/` + a full call-site sweep, 2026-07-09). Under a strict `fips`+`base` provider set with **no `default` provider**:
  - **SHA-1 is FIPS-approved as a hash** and is served by the `fips` provider. `hashlib.sha1()` works. Only MD5 hard-fails.
  - `hashlib.md5()` → `UnsupportedDigestmodError`; `hashlib.md5(usedforsecurity=False)` **succeeds**, served by `_hashlib` from a **separate non-FIPS `OSSL_LIB_CTX`** that CPython maintains for exactly this purpose. FIPS 140-3 permits non-approved algorithms for non-security uses, and `usedforsecurity=False` is the auditor-recognized signal — but it is a **reachable non-validated path**, and should be named as such rather than implied absent.
  - `hashlib.sha256()` is `_hashlib`-backed (genuinely the validated module); Wolfi's CPython ships **no** `_md5`/`_sha1`/`_sha2`/`_sha3` built-ins to silently fall back to. `_blake2` *is* built in — a small non-validated in-process implementation remains importable.
  - **TAP's own code is clean:** zero `md5`, zero `sha1`, zero `uuid3`; the only primitives are `hashlib.sha256` (13 call sites) and `hmac.compare_digest` (2). **`uuid5` (17 files, deterministic node/edge ids) is SHA-1-based and is safe** — CPython 3.14's `uuid5` passes `usedforsecurity=False`, and SHA-1 is approved regardless.
  - **Dependency closure:** the only bare `hashlib.md5()` calls are Django's legacy `MD5PasswordHasher` (**not** in Django's default `PASSWORD_HASHERS`, and TAP does not override them → unreachable) and `faker` (test-only). Bare `sha1()` in `cryptography`, `webauthn`, `oauthlib`, `django.template.loaders.cached` all work (approved). **No runtime hard-fail surface.**
  - Loading the `default` provider to widen the escape hatch is **not** required and should be resisted. Re-run the sweep on dependency bumps (`-1` auto-patch PRs) — a new bare `md5()` in a runtime dep is a boot-breaking regression under `TAP_FIPS=1`.
- **Alternatives are parked, not eliminated** (2026-07-09; measured matrix in the survey doc, working builds in `spikes/distroless/`). Reopen when: (a) the compliance authority rejects vendor-affirmed OE (→ RHEL/host-FIPS); (b) we adopt a bake-once/distroless variant (the runtime-install architecture does **not** block this — proven); (c) Wolfi's Python-3.14 currency or CVE floor regresses. `dhi.io` needs an authenticated pull (**401**), which conflicts with `req-cicd-base-image-sourcing`; its free `3.14-fips` variant is **unverified**.

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

**Plugin release signing lands here.** `req-plugin-extdev-signing`
(`spec-plugin-external-development.md`) — signed plugin release tags / boot-record digests
verified at install, closing the moved-tag / compromised-repo gap — is the plugin-artifact
face of this same signing capability. It is **pinned to the GitHub-org refactor** because the
publisher/signing identity is org-rooted: building it before the org exists means rebuilding
it against the new identity root. So plugin signing is deferred to this requirement's wave,
not built speculatively now; for the Aug-1 friendly-developer phase the trust boundary
(TAP-controlled org, repos, read-only PAT, known developers) is tight enough to defer
enforcement. Grafana (signed plugins) and Terraform (GPG-verified provider tags) are the
precedents for both faces — one signing story, two layers (image artifact + plugin tag).

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
