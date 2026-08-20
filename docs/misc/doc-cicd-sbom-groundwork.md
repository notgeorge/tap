---
spec: ../../specs/spec-cicd-sbom.md
audience: [llm, developer]
covers:
  - ../../specs/spec-cicd-sbom.md
  - ../../specs/spec-cicd-hardening.md
assumes:
  - Reader knows the publish pipeline shape (publish-images.yml + publish-release-tags.yml, req-cicd-build-once-artifact) and the digest-threading law (req-cicd-supply-chain-provenance-1).
---

# SBOM Groundwork — Findings, Prior Art, and Decisions

The empirical and research record behind [spec-cicd-sbom.md](../../specs/spec-cicd-sbom.md),
gathered 2026-08-18 → 2026-08-20 during the v0.1.2 publish-gap incident and its follow-up.
Everything in the spec's requirements traces to a finding or a precedent recorded here.

## 1. The incident context that motivated this

The chain (full detail in spec-cicd-hardening's req-cicd-product-releases-1 and
req-cicd-supply-chain-provenance-1 notes):

1. **v0.1.2 publish gap** — publish-images' newest-main-wins cancellation killed the
   release commit's build 13s after merge; `:sha-153f6d7` never existed; the version-tag
   promotion starved; nobody noticed for 4 days because compose's `build:` fallback
   silently substituted from-source rebuilds. Fixes: isolated concurrency for release
   builds + `ref` backfill (PR #75), pull-only base compose (PR #76), CI rides `:latest`
   (PR #78).
2. **Digest threading** (PR #77) — the staging-tag hops between build and manifest jobs
   were TOCTOU windows where a `packages:write` holder could swap content and the
   attestation would then SIGN the tampered bytes. Now: push-by-digest, digests ride
   workflow artifacts, merge consumes `ref@digest`, fail-closed children-equality check
   before attesting. `provenance: false` on build legs is LOAD-BEARING (bare manifests
   make strict equality checkable; the provenance lane is GitHub attestations).
3. **The reproducibility discussion** that surfaced the SBOM need — see §2.

## 2. Reproducibility: what floats, what pins

Layer-by-layer truth for both images (established 2026-08-19):

| Layer | Pinned? | Mechanism |
| --- | --- | --- |
| Base image (wolfi-base) | yes | tag@digest in both Dockerfiles; Renovate bumps |
| OS packages (`apk add`) | **floats** | resolves Chainguard's CURRENT index at build time — both images |
| OpenSSL FIPS provider | yes (exactly) | version-pinned source URL; 3.0.9 is the CMVP #4282 artifact |
| Python closure (web) | yes | uv.lock, hash-verified, installed at runtime by `uv sync` |

Consequences:

* **A version's images = that commit's source × the build day's packages.** Rebuilding is
  not reproducible; the published artifact is the only pin. Live proof: the 0.1.2
  backfill built the 08-12 release commit on 08-19 — same source, that day's packages.
* **apk version-pinning is not a fix**: Wolfi is rolling; Chainguard drops old package
  versions from the index (their CVE model — the fix for a vulnerable package is that it
  ceases to exist). Pinning trades silent float for constant breakage with no
  rebuildability gained. Decision: option (a) — artifact-is-the-pin — is coherent, not
  merely cheap.
* **Chainguard's actual guarantees** (verified 2026-08-19): provenance/signatures/SBOMs
  for THEIR builds (melange/apko, Sigstore), minimal CVE surface, fast remediation.
  Consumer-side reproducibility is NOT offered — the rolling repo structurally opposes
  it; version retention is the paid product. Free-tier notes: Wolfi repo free;
  ~50 Starter images `:latest`-only; **Catalog Starter (2026-03): any team picks 5 free
  images from the full catalog** — back-pocket card for a maintained postgresql base
  (FIPS variants stay enterprise). No standing OSS-org grant program found.

So: release notes describe source changes; the OS-package delta between releases is
invisible without a build-time SBOM. That is the gap the spec closes.

## 3. Empirical findings: what scanners actually see in our images

Agent-verified 2026-08-20 against `tap-web:latest` (syft v1.51.0 standalone;
buildkit-syft-scanner stable-1 embedding syft v1.42.3). Raw data preserved in the session
scratchpad at time of writing; the numbers below are the durable summary.

### 3.1 BuildKit `sbom: true` is a dead end for these images

* Syft's lockfile parser (`python-package-cataloger`) is a "declared/directory"
  cataloger — **excluded from image scans**. Full image scan: 1,229 artifacts, ZERO
  citing `/app/uv.lock`.
* `buildkit-syft-scanner` **hardcodes** installed-only cataloging: minimal-image tests
  (`COPY uv.lock`, `requirements.txt` control) → 0 packages; every cataloger-selection
  env override (`SYFT_SELECT_CATALOGERS`, `SYFT_CATALOGERS`, `SYFT_DEFAULT_CATALOGERS`)
  verified inert. Not configurable from build-push-action.
* The cataloger itself works when reachable: `dir:` scan of uv.lock → 69 packages
  (django 6.0.8 et al.).

### 3.2 What a default scan DOES emit — plausible garbage

* **~101 "installed" Python packages that are actually the wheel cache**: unpacked wheels
  under `/opt/uv-cache-seed/**` carry dist-info, so they masquerade as installed.
  vs the lock: 31 phantoms (maturin; setuptools ×2 versions; wheel ×3; setuptools'
  vendored jaraco-*/autocommand/inflect; a literal `my-test-package 1.0` test fixture)
  and 3 real members MISSING (colorama, tzdata, and **`tap` itself**).
* **1,012 Rust-crate entries** from cargo-auditable metadata inside `/usr/bin/uv` and
  `/usr/bin/uvx` — the tool's own closure drowning the artifact's.
* The wheel-cache inventory is load-bearing on an accident: change the cache-seeding
  strategy and the Python inventory silently vanishes.
* Sanity: the apk (Wolfi) side catalogs cleanly — 100 packages.

### 3.3 fips.so is invisible

`/usr/lib/ossl-modules/fips.so` appears only as an uncataloged-file "unknown"; the apk
`openssl` package does not claim it (correct — we build it). In a production attestation
the most compliance-significant binary in the image would appear nowhere. Hence
req-cicd-sbom-3 (hand-authored supplemental entries) — no scanner will ever fix this.

## 4. Prior art — the five patterns in the wild

1. **Generate-and-attest, GitHub-native** (anchore/sbom-action → actions/attest-sbom):
   GitHub's documented flow; Syft generates, GitHub Sigstore-signs into the attestation
   store, `gh attestation verify` verifies. De-facto default for GitHub-hosted OSS.
2. **BuildKit in-registry attestations** (`sbom: true`): Docker's pattern; per-arch SBOMs
   as `unknown/unknown` index entries. Field lessons: attestations do NOT survive naive
   manifest merges, and content assumes conventional installed layouts (§3 rules it out
   for us).
3. **Signed registry attestations via cosign** (`cosign attest`): Chainguard's pattern
   (apko emits exact SBOMs, cosign signs them as OCI referrers). Key data point:
   **`cosign attach sbom` was deprecated 2024** because unsigned SBOMs are unverifiable —
   the ecosystem converged on signed-or-nothing, independently validating TAP's
   TOCTOU/signing posture.
4. **Purpose-built first-party generator** (kubernetes-sigs/bom): k8s wrote its own SPDX
   tool because generic scanners missed project reality. Transferable lesson: mature
   projects CURATE and AUGMENT generation rather than trusting a default scan — the
   k8s-scale response (own tool) is overkill for TAP; the posture is not.
5. **Multi-arch consensus** (Chainguard's "SBOMs in a multi-architecture world"): each
   platform variant carries its own standalone SBOM (consumers pull arch images
   directly); no standard merged index-level SBOM exists.

Format sidebar: CycloneDX (OWASP) owns security tooling — Dependency-Track, VEX triage,
Trivy/Grype native, the safer EU-CRA bet; SPDX (Linux Foundation) owns license/legal and
government adoption (k8s ships it). Both satisfy CISA 2026 minimum elements. Syft emits
both from one scan → format is a serialization choice, not lock-in (req-cicd-sbom-6).

## 5. Decisions and their reasoning (the trail to each requirement)

| Decision | Reasoning | Req |
| --- | --- | --- |
| Standalone pinned Syft, buildx `sbom:true` forbidden | §3.1: hardcoded catalogers make the one-liner emit wrong content, unconfigurably | sbom-1 |
| Lockfile closure in, cache/binary noise out | §3.2: uv.lock IS what runs (hash-verified `uv sync`); cache inventory ≈ closure but wrong both directions | sbom-2 |
| Hand-authored out-of-band entries | §3.3; crypto-BOM discipline gets its first standard-format artifact | sbom-3 |
| GitHub attest-sbom home; digest subjects; no mutable-name hops | Matches existing provenance lane (one verify story, zero new trust roots); digest-threading law extends; TOCTOU analysis: a signature binds identity to bytes, not bytes to origin — an unsigned mutable hop lets the signer launder a tamper | sbom-4 |
| Per-arch standalone, no index merge | Pattern 5 consensus + our verified per-arch digests are the natural subjects | sbom-5 |
| CycloneDX primary, SPDX as re-serialization only | Security-consumer gravity; derive-once (two independent scans WILL drift) | sbom-6 |
| Fail-closed canary guard | Every observed failure mode was silent plausibility; convert quiet wrongness into a red publish | sbom-7 |
| Release diffs deferred | Pure consumer of the rest; the customer upgrade-diff promise, machine-checkable | sbom-8 |
| Extensible to ready-made appliance images | George 2026-08-20: profile-baked plugin images are on the roadmap; the artifact/runtime boundary (not core/plugin) is the durable line — baked plugin closures enter the image SBOM via the same declared-manifest principle (boot-record data as the manifest); parameterize generation + canaries per flavor now, cheap at design time / expensive to retrofit | sbom-9 |

Layered-BOM model (scope boundary, refined 2026-08-20): the durable line is
BAKED-IN-ARTIFACT vs ADDED-AT-RUNTIME, not core-vs-plugin. The image SBOM is the
ARTIFACT-level inventory (universal — every copy of a version, everywhere; for a flavored
ready-made image that includes its baked plugin closure); the boot record is the
INSTANCE-level BOM (particular — what this running instance actually loaded; for a
ready-made instance, ideally a digest-reference to the image SBOM plus runtime deltas
only). They compose; neither substitutes for the other.

## 6. Named residuals (declared, not solved here)

* **Build-cache poisoning** — buildcache tags are mutable; a forged cache entry injects
  content BEFORE the first digest exists, upstream of SBOM and provenance alike.
  Accepted at req-cicd-supply-chain-provenance-1; blast radius = our own
  `packages:write` surface.
* **Compromised runner** — tampered bytes at birth; no downstream digest/signature
  discipline helps. Addressed by pinned actions, least-privilege tokens, provenance.
* **db-Dockerfile PR coverage** — a PR editing docker/postgres/Dockerfile is not
  exercised by CI (db image never built from the PR tree). Pre-existing, named at PR #78.
* **Registry-side SBOM copy** for mirrored/air-gapped consumers — deferred; signed-only
  if ever (Pattern 3's deprecation lesson).

## 7. Sources

* anchore/sbom-action: https://github.com/anchore/sbom-action
* GitHub artifact attestations: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
* kubernetes-sigs/bom: https://github.com/kubernetes-sigs/bom
* cosign attach-sbom deprecation: https://github.com/sigstore/cosign/issues/2755
* cosign SBOM spec: https://github.com/sigstore/cosign/blob/main/specs/SBOM_SPEC.md
* Chainguard, "SBOMs in a multi-architecture world": https://www.chainguard.dev/unchained/sboms-in-a-multi-architecture-world
* Chainguard SBOM/attestation distinction: https://edu.chainguard.dev/open-source/sbom/sboms-and-attestations/
* CycloneDX vs SPDX (2026 landscape): https://www.interlynk.io/resources/cyclonedx-vs-spdx-sbom-format
* CISA minimum-elements mapping: https://runsafesecurity.com/blog/sbom-minimum-elements-cyclonedx-spdx/
* BuildKit attestation storage (unknown/unknown platform entries): https://github.com/goharbor/harbor/issues/22848
