# SBOM Emission Specification

## Philosophy

An SBOM (software bill of materials) is the machine-readable answer to "what exactly is
inside this artifact?" — per-component, per-version, diffable, consumable by scanners and
by Player-3 tooling without pulling the image apart. TAP's publish pipeline already proves
*who* built an artifact and *from which commit* (SLSA provenance,
`req-cicd-supply-chain-provenance`); the SBOM is the missing *what*.

Three facts, all established empirically (see
[doc-cicd-sbom-groundwork](../docs/misc/doc-cicd-sbom-groundwork.md)), shape every
requirement below:

1. **The published artifact is the version pin.** The OS package layer floats against
   rolling Wolfi at build time (`req-cicd-product-releases-3` groundwork): a version's
   images are that commit's source × the build day's packages, and a rebuild is not
   reproducible. Only an SBOM captured at build time records which packages a release
   actually shipped — release notes describe source changes; the package delta rides
   silently without it.
2. **The obvious one-liner produces a wrong SBOM for our images.** BuildKit's `sbom: true`
   runs a scanner locked to installed-package cataloging. Our web image deliberately
   contains no installed Python environment (wheel-cache + runtime `uv sync`), so the
   default scan misses the real closure (`uv.lock` is never parsed), inventories the wheel
   cache as ~101 phantom "installed" packages (missing `tap` itself; including build
   backends at multiple versions and a literal `my-test-package` test fixture), and drowns
   the result in ~1,012 Rust-crate entries from the `uv` binary. A plausible-but-wrong
   SBOM is worse than none: consumers diffing releases would chase ghosts.
3. **No scanner can see a hand-built component.** The single most compliance-significant
   binary in the image — the self-built OpenSSL 3.0.9 FIPS provider (`fips.so`, CMVP
   #4282) — appears in no package database and therefore in no scanned inventory. Honest
   SBOMs for TAP require deliberate augmentation, not just scanning.

The prior-art consensus (Kubernetes `bom`, Chainguard/apko, the cosign `attach sbom`
deprecation, GitHub's generate-and-attest flow) reduces to: **curate the generation, sign
the result, keep per-arch SBOMs standalone** — and TAP's digest-threading law
(`req-cicd-supply-chain-provenance-1`) extends unchanged: no mutable-name hop between
generation and signature.

Scope: the published `tap-web` and `tap-db` images today, extensible to **flavored
ready-made images** tomorrow (req-cicd-sbom-9). The durable boundary is NOT "core vs
plugins" — it is **baked-into-the-artifact vs added-at-runtime**: the image SBOM is the
*artifact-level* BOM (what every copy of this version contains everywhere); the boot
record is the *instance-level* BOM (what this running instance actually loaded). A
ready-made image that bakes a boot profile's plugin set moves that plugin closure across
the boundary — into the artifact, and therefore into its SBOM. Runtime-added plugins
remain the boot record's territory. The two compose; neither substitutes for the other.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Honest | The SBOM lists what the artifact actually carries — the true locked closure, no phantoms, hand-built components included |
| 2. | Signed | SBOMs travel only as signed attestations bound to content digests; an unsigned SBOM is a rumor |
| 3. | Diffable | SBOM(vN) − SBOM(vN−1) is the mechanical answer to "what changed under the version bump" — the upgrade-diff promise made machine-checkable |
| 4. | Guarded | A regression to a wrong-but-plausible SBOM fails the publish, loudly — accuracy is load-bearing, never accidental |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-cicd-sbom-1 | [Curated Standalone Generation](#curated-standalone-generation) | Proposed | Pinned standalone Syft against verified per-arch digests; BuildKit `sbom: true` is FORBIDDEN for these images |
| req-cicd-sbom-2 | [Closure Accuracy](#closure-accuracy) | Proposed | Locked Python closure IN (uv.lock cataloger); wheel-cache + uv-binary phantoms OUT (path excludes) |
| req-cicd-sbom-3 | [Out-of-Band Components Declared](#out-of-band-components-declared) | Proposed | Anything entering the image outside a package manager gets a hand-authored entry — first: `fips.so` (OpenSSL 3.0.9, CMVP #4282) |
| req-cicd-sbom-4 | [Signed Digest-Bound Home](#signed-digest-bound-home) | Proposed | `attest-sbom` per arch digest, GitHub attestation store; digest-threading law applies end to end; registry copy (if ever) must be a signed attestation, never an attachment |
| req-cicd-sbom-5 | [Per-Arch Standalone SBOMs](#per-arch-standalone-sboms) | Proposed | One SBOM per platform digest; no merged index-level SBOM exists |
| req-cicd-sbom-6 | [Single Derivation, Format as Serialization](#single-derivation-format-as-serialization) | Proposed | One Syft scan per digest is canonical; CycloneDX primary output; SPDX only ever as a second serialization of the SAME scan |
| req-cicd-sbom-7 | [Canary Guard](#canary-guard) | Proposed | Fail-closed publish check: expected components present, known phantoms absent — else no attestation |
| req-cicd-sbom-8 | [Release SBOM Diffs](#release-sbom-diffs) | Deferred | Human-readable package delta per release, feeding the customer upgrade-diff contract; consumer of 1–7, not a blocker |
| req-cicd-sbom-9 | [Flavored Ready-Made Images](#flavored-ready-made-images) | Proposed | Design constraint now, implementation with the appliance-image work: an image baking a boot profile's plugins ships an SBOM covering core + baked plugin closure, from the same declared-manifest principle |
| req-cicd-sbom-10 | [Plugin-Declared SBOMs](#plugin-declared-sboms) | Proposed | Declare-vs-decide: plugin release CI declares an attested per-release SBOM; the system verifies and composes, never re-derives blindly; bake-time combined lock is the single derivation for flavored images |

---

### Curated Standalone Generation
----
RID: `req-cicd-sbom-1`
Status: `Proposed`

SBOMs for the published images MUST be generated by a **pinned standalone Syft**
invocation running as a publish-pipeline step, scanning each **verified per-arch digest**
(the digests the merge step verified under `req-cicd-supply-chain-provenance-1`).

BuildKit's built-in generator (`sbom: true` on the build step) is **FORBIDDEN** for these
images and MUST NOT be enabled: `buildkit-syft-scanner` hardcodes installed-only
catalogers (all cataloger-selection overrides verified inert), pins an older Syft, and —
against our venv-less image layout — emits the phantom inventory described in the
Philosophy. This is not a preference; enabling it would publish a wrong SBOM that no
downstream consumer could distinguish from a right one.

The Syft version is pinned and Renovate-managed like every other pipeline dependency;
bumps ride PRs, never floats.

### Closure Accuracy
----
RID: `req-cicd-sbom-2`
Status: `Proposed`

The web image's SBOM MUST contain the **locked Python closure** — the packages `uv.lock`
resolves, which are byte-for-byte what runtime `uv sync` installs — sourced via Syft's
declared-package (lockfile) cataloger explicitly enabled for the scan.

The SBOM MUST NOT contain the wheel-cache or tool-binary phantom inventory. At minimum
the scan excludes `/opt/uv-cache-seed/**` (unpacked-wheel `dist-info` masquerading as
installed packages: build backends, vendored internals, multi-version duplicates, test
fixtures) and the `uv`/`uvx` binaries' embedded Rust-crate metadata. Rationale: the cache
is *available bytes*, not *running software*; its inventory approximates the closure
while missing real members (`colorama`, `tzdata`, `tap` itself) and adding ~31 phantoms —
and it vanishes entirely if the cache-seeding strategy changes. An SBOM must never be
load-bearing on an accident.

### Out-of-Band Components Declared
----
RID: `req-cicd-sbom-3`
Status: `Proposed`

Any component that enters a published image **outside a package manager** — compiled from
source in a build stage, copied from a builder, vendored by hand — MUST be declared in
the SBOM via a hand-authored supplemental entry, maintained alongside the Dockerfile that
introduces it.

First and motivating member: the self-built OpenSSL **3.0.9 FIPS provider**
(`/usr/lib/ossl-modules/fips.so`, CMVP certificate #4282) in both images. No scanner can
infer it (verified: it surfaces only as an uncataloged-file unknown), yet it is the most
compliance-significant binary TAP ships. Its SBOM entry is the first machine-readable
artifact of the crypto-BOM discipline (`req-fips-crypto-bom`, spec-fips.md): the crypto
provider inventory, in a standard format, per artifact.

This requirement is the general rule; the guard for it is req-cicd-sbom-7's canary check
(a missing declared component fails the publish).

### Signed Digest-Bound Home
----
RID: `req-cicd-sbom-4`
Status: `Proposed`

SBOMs are published as **signed attestations in the GitHub attestation store**
(`actions/attest-sbom`), subject = the verified per-arch image digest — the same home,
identity root, and `gh attestation verify` story as the existing SLSA provenance. No new
trust roots.

The digest-threading law (`req-cicd-supply-chain-provenance-1`) extends to SBOMs: between
generation and signature the SBOM and its subject MUST never be referenced through a
mutable name. The scan targets `ref@digest`; the attestation subject is that same digest;
the document travels within one job (or via integrity-held workflow artifacts, never via
registry round-trip).

A registry-side copy (OCI referrers, for mirrored/air-gapped consumers) is a named
deferral — if ever added it MUST be a signed attestation (`cosign attest`), never an
unsigned attachment: the ecosystem deprecated `cosign attach sbom` for exactly the
trust gap TAP's posture forbids.

### Per-Arch Standalone SBOMs
----
RID: `req-cicd-sbom-5`
Status: `Proposed`

Each platform variant (amd64, arm64) carries its **own standalone SBOM**, attested
against its own digest. No merged index-level SBOM is produced. Rationale (prior-art
consensus): consumers can and do pull a platform manifest directly, so its SBOM must
stand alone; and the per-arch closures genuinely differ (compiled wheels, arch-specific
apk packages). The multi-arch answer is "ask for the platform you run," not a synthetic
union document.

### Single Derivation, Format as Serialization
----
RID: `req-cicd-sbom-6`
Status: `Proposed`

One Syft scan per digest is the **single derivation**; formats are serializations of it.
Primary output: **CycloneDX** (security-consumer gravity: Dependency-Track, VEX-aware
triage, Trivy/Grype native). SPDX MAY be emitted later for a compliance consumer, but
only ever as a second serialization of the same scan — never a second independent scan
(two scanners drift, and a consumer holding both learns nothing except that we disagree
with ourselves). The derive-once rule, applied to CI artifacts.

### Canary Guard
----
RID: `req-cicd-sbom-7`
Status: `Proposed`

Before attesting, the pipeline MUST verify each generated SBOM **fail-closed** against a
canary list, refusing to publish on any miss:

* web MUST contain: `tap` at the built version, `django`, the `fips.so` supplemental
  entry, and a known apk canary (e.g. `openssl`);
* db MUST contain: `postgresql-16` and the `fips.so` supplemental entry;
* both MUST NOT contain known-phantom markers (e.g. `my-test-package`, any
  `/opt/uv-cache-seed` location).

Rationale: every failure mode observed in the groundwork was *silent plausibility* — a
scan that succeeds and emits confident garbage. The canary guard converts "the SBOM
quietly went wrong" (cataloger regressed in a Syft bump, cache path moved, augmentation
step dropped) into a red publish. At implementation time this check is a validation
surface and gets its Validation Map row (spec-dev-validation.md) in the same change.

### Release SBOM Diffs
----
RID: `req-cicd-sbom-8`
Status: `Deferred`

A human-readable package delta between consecutive release SBOMs (added / removed /
version-changed, OS layer and Python closure), attached to the release. This is the
machine-checkable half of the customer upgrade-diff promise: release notes describe
source changes; the SBOM diff surfaces the silent package drift underneath
(`req-cicd-product-releases`). Deferred: pure consumer of req-cicd-sbom-1..7, adds no
constraint on them, and should be built against real release cadence.

### Flavored Ready-Made Images
----
RID: `req-cicd-sbom-9`
Status: `Proposed`

TAP is tacking toward **ready-made appliance images**: a boot profile's plugin set baked
into a published image (e.g. a GitHub-configuration mapping instance), pulled from the
registry with everything installed — an adopter slots in secrets and boots. This
requirement is a **design constraint on req-cicd-sbom-1..7 now** and an implementation
obligation when those images ship:

* A flavored image's SBOM MUST cover the core closure **plus the baked plugin closure**
  (each plugin and its dependencies), derived by the same principle as everything else:
  from **declared, hash-verified manifests baked in the artifact** — the core `uv.lock`
  plus the flavor's boot-profile plugin manifest (the boot-record-as-BOM data, which
  already names each plugin at an exact version) — never by scanning materialized
  caches or installed trees (the wheel-cache phantom lesson applies with more force,
  since plugin wheels ride the same cache mechanism).
* Therefore the generation step (req-cicd-sbom-1) MUST be parameterized as *artifact ×
  list-of-declared-manifests*, not hardcoded to "two images, one lockfile each"; the
  canary guard (req-cicd-sbom-7) MUST take per-flavor canary lists (every baked plugin
  present; the flavor's profile named).
* The boot record of a ready-made instance SHOULD reference the image SBOM (by image
  digest) for the baked set rather than restating it, and record only runtime deltas —
  one fact, derived once, linked across layers.
* Naming/tagging of flavored images follows the existing pipeline disciplines unchanged
  (digest-threading, per-arch, signed attestation home).

Status rationale: no flavored image exists yet, so nothing here is buildable — but
req-cicd-sbom-1/-7's implementation must not foreclose it. The extensibility is cheap at
design time and expensive to retrofit (the security-posture asymmetry).

### Plugin-Declared SBOMs
----
RID: `req-cicd-sbom-10`
Status: `Proposed`

Plugins declare their own SBOMs, on the **declare-vs-decide** pattern the manifest
`[fips]` table established: the author's pipeline DECLARES, the system VERIFIES and
COMPOSES — it never re-derives blindly and never trusts blindly.

* **Declaration at release time.** The shared plugin release lane (plugin CI /
  `release-plugin.sh`) generates each plugin's SBOM from its own declared manifests
  (pyproject + lock), CycloneDX, published as a signed attestation against the release
  artifact — the same `attest-sbom` home and verify story as core (req-cicd-sbom-4).
  Identity keys on (package name, exact version): the boot-record entry key, so every
  layer joins on the same fact.
* **Composition, not re-scanning.** A flavored image build (req-cicd-sbom-9) VERIFIES
  each baked plugin's release-SBOM attestation; a running instance's boot record
  REFERENCES plugin SBOMs by digest/purl rather than restating them. Instance BOM =
  image-SBOM reference + per-plugin SBOM references + runtime deltas.
* **Derive-once at bake time.** A flavored image's true closure is the SINGLE bake-time
  resolution of core + plugins together (shared dependencies dedupe; version conflicts
  are the deps gate's job). The flavored artifact's SBOM therefore generates from that
  combined bake-time lock — one derivation. Plugin-declared release SBOMs serve the
  other two consumers: runtime (non-baked) installs, and the cross-check.
* **Declared-vs-derived cross-check.** What the bake derived MUST reconcile with what
  each baked plugin's author declared; a mismatch is a canary-guard red
  (req-cicd-sbom-7), never a silent preference for either side — disagreement between
  declaration and derivation is precisely the signal worth stopping for.
* **Trust rides the signing wave.** Plugin SBOM attestations inherit the org-rooted
  identity `req-plugin-extdev-signing` lands (spec-plugin-external-development.md);
  no new trust machinery is invented here, and nothing blocks on it — unsigned-but-
  attested-by-CI is the interim posture, upgraded when that wave ships.

## Non-Goals and Named Residuals

* **Runtime-added plugin SBOMs** — the boot record is the instance-level BOM for
  anything installed at boot rather than baked; out of scope here. The baked-plugin case
  is IN scope via req-cicd-sbom-9. Future seam (named, not built): the boot record
  references the image SBOM by digest rather than restating it — one fact, derived once,
  linked across layers.
* **Registry-side referrers copy** — deferred, see req-cicd-sbom-4.
* **Build-cache poisoning** — upstream of generation entirely; named and accepted at
  `req-cicd-supply-chain-provenance-1`. An SBOM inventories what was built; it cannot
  vouch that the build inputs were honest — that is provenance's job.
* **SPDX emission** — permitted as a second serialization (req-cicd-sbom-6), not planned
  until a consumer demands it.
