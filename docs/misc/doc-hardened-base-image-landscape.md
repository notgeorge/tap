---
spec: ../../specs/spec-cicd-hardening.md
audience: [developer, llm]
covers:
  - ../../specs/spec-cicd-hardening.md
  - req-cicd-base-image-lifecycle
update-triggers:
  - A base-image provider materially changes free-tier / Python-version / extensibility posture
  - TAP adopts the bake-once/distroless runtime variant (re-evaluate DHI / Red Hat Hardened)
  - A customer/engagement introduces a FIPS / FedRAMP / STIG requirement
  - uv ships embedded git (issue #12324) — the git off-ramp opens
assumes:
  - TAP's runtime-install architecture (deps + plugins installed at container start, not baked at build)
provides: |
  The decision record behind req-cicd-base-image-lifecycle: the 2026 hardened-base-image
  landscape, why Wolfi fits TAP's architecture, when to re-evaluate the alternatives, the
  git-binary off-ramps, and the FIPS-crypto analysis (buy vs. DIY OpenSSL-3-FIPS-provider).
---

# Hardened Base Image Landscape + FIPS Analysis

This is the **decision record** for `req-cicd-base-image-lifecycle`. The spec states the
decision (curated-minimal Wolfi base + self-hosted patch loop, demand-gated FIPS); this doc
holds the *why*, the alternatives evaluated, and the triggers for revisiting them — so a future
reader (human or agent) doesn't re-litigate settled ground or miss a re-evaluation moment.

## The decision criterion (read this first)

TAP installs its dependencies **and** its plugins at container **start**, not at image build
(runtime `uv sync`; from-git plugin install at pre-boot; the `--from` bootstrap-pointer boot).
That single architectural fact is the filter that decides everything below:

> **We need a hardened base that ships a *package manager*, so we can `add` exactly TAP's
> runtime binaries onto it.**

This cleanly splits the 2026 field into two models:

| Model | Examples | Fits TAP's runtime-install architecture? |
| --- | --- | --- |
| **Base + package manager** (you `add` binaries) | **Wolfi (`apk`)**, Red Hat UBI (`dnf`), SUSE BCI (`zypper`), Alpine (`apk`), Debian slim (`apt`) | **Yes** — our lane |
| **Fixed / distroless image** (no package manager) | Docker Hardened `python`, Red Hat Hardened micro, Google Distroless, Ubuntu Chiseled | No — bake-once only; you can't `add git` to them |

Most of the exciting *new* free hardened images are **fixed/distroless** — excellent for a future
bake-once variant, useless for adding our binaries today. That, plus the **Python 3.14** filter
(we run bleeding-edge Python; Debian/RHEL-derived bases lag), is why Wolfi wins now.

## Provider matrix (2026)

| Provider | Model | libc | Free? | Python 3.14? | Fit now | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| **Chainguard / Wolfi** | pkg-mgr base (`apk`) **and** fixed images | glibc | Yes (`wolfi-base`, apko/melange OSS; catalog free tier is `:latest`-only) | **Yes** (spike: 3.14.6) | **✅ chosen** | Tracks latest; apko/melange = build-your-own for free; commercial catalog adds pinning + SLA + FIPS. |
| **Docker Hardened Images (DHI)** | fixed/distroless | glibc/musl | **Yes** — free + Apache-2.0 since 2025-12-17 | examples show 3.13 | Bake-once only | Docker-native, OSS. **First to benchmark for the bake-once variant.** Enterprise = SLA/FIPS. |
| **Red Hat Hardened Images** | fixed/micro | glibc | **Yes** — GA 2026-05-12, `images.redhat.com` | built-from-upstream (fresher than UBI; 3.14 TBD) | Bake-once only | Distinct from UBI (upstream-built → faster CVE fixes). |
| **Red Hat UBI (micro/minimal)** | pkg-mgr base (`dnf`/`microdnf`) | glibc | Yes, redistributable | RHEL-lagged (no 3.14) | Version-lagged | The RHEL-shop option; Python tracks RHEL, so unfit for 3.14. |
| **Canonical Ubuntu Chiseled** | fixed/distroless | glibc | Yes | Ubuntu-release-tied | Bake-once only | Distroless slices of Ubuntu. |
| **SUSE BCI** | pkg-mgr base (`zypper`) | glibc | Yes | SLE-lagged | Version-lagged | Free SUSE base images. |
| **BellSoft Alpaquita** | pkg-mgr base | musl/glibc | Free tier | varies | Java-leaning | musl variant = the Python trap. |
| **Google Distroless** | fixed/distroless | glibc | Yes | Debian-lagged; experimental | Bake-once only | **Worst-CVE-of-three** (Debian-stable lag); Python is experimental. Rejected. |
| **Iron Bank (DoD P1)** | fixed | glibc | Free, access-gated | varies | Niche | For DoD supply chains. |
| **Stagex** | source-built | musl | Yes, OSS | limited catalog | Niche | Fully reproducible/bootstrappable; supply-chain purist option. |
| **Minimus / Echo / WizOS** | fixed | glibc | Commercial | varies | Commercial | Chainguard challengers; SLA + FIPS/STIG evidence. |

Sources: [RedMonk "Why Hardened Images are Suddenly Everywhere"](https://redmonk.com/kholterhoff/2026/06/01/why-hardened-images-are-suddenly-everywhere/),
[Free DHI challenges Chainguard (TechTarget)](https://www.techtarget.com/searchitoperations/news/366636656/Free-Docker-Hardened-Images-challenge-Chainguard),
[Red Hat UBI vs Hardened Images](https://developers.redhat.com/articles/2026/06/29/red-hat-ubi-vs-red-hat-hardened-images-how-to-choose),
[Distroless vs Chainguard vs Wolfi](https://safeguard.sh/resources/blog/distroless-vs-chainguard-vs-wolfi-base-images),
[Minimus: Chainguard alternatives](https://www.minimus.io/post/chainguard-alternatives-hardened-image-providers).

## Spike evidence (2026-07-09)

Real build of `cgr.dev/chainguard/wolfi-base` + `apk add python-3.14 git bash postgresql-client curl` + copied `uv`:

- **Python 3.14.6** present; git 2.55.0, bash 5.3.0, uv 0.11.26, pg_isready 18.4, curl 8.21 — all modern.
- TAP's **full dependency closure `uv sync`'d cleanly** (glibc manylinux wheels incl. native `rpds-py`, our `webauthn 3.0.0`; `django 6.0.2` imports). No source builds — the Alpine/musl trap avoided.
- **from-git plugin path works** (`git ls-remote` over TLS — DNS/TLS/git all functional).
- **Trivy OS-package CVEs: 0** (vs **311** on `python:3.14-slim`: 8 critical / 63 high / 122 medium / 118 low) — *with* git/bash/uv still installed.

Caveats: (1) `0` is *OS-package* CVEs at a moment in time — Python *dependency* CVEs are identical
on both bases (Renovate + Trivy-on-deps handle those). (2) It stays near-0 by *motion* (nightly
Wolfi rebuilds + our auto-patch loop), not magic. (3) `git` is present and CVE-prone, but Wolfi's
is current (2.55.0, 0 CVEs today) vs. Debian's lagged copy.

### Reproducing the spike

`Dockerfile` (two stages): `--target base` = `apk` binaries only (apples-to-apples OS-CVE scan
vs the current venv-less slim web image); `--target full` = `+ uv sync --frozen --no-install-project`
(proves the dep closure installs). Scan with Trivy via `ghcr.io/aquasecurity/trivy` (not Docker
Hub — avoids the 429): `trivy image --scanners vuln --pkg-types os --severity CRITICAL,HIGH,MEDIUM,LOW <img>`.

## Re-evaluation triggers

Revisit the provider choice — do **not** treat Wolfi as permanent — when any of these fire:

1. **We adopt the bake-once / distroless runtime variant.** Then a fixed hardened image becomes
   viable. **Benchmark free DHI `python` first** (Docker-native, Apache-2.0), then Google Distroless
   / Red Hat Hardened. The `req-cicd-base-image-lifecycle-4` off-ramps (drop git/curl) land here.
2. **A FIPS / FedRAMP / STIG requirement lands** (see below) — price Chainguard `python-fips` vs. the DIY path.
3. **We settle off bleeding-edge Python** (the version-lag filter stops mattering) — UBI / DHI / Chiseled re-open.

## The git-binary off-ramps

`git` is on the image solely so `uv` can install from-git plugins (uv shells out to the system
`git` binary; it does **not** bundle one). Two off-ramps, neither worth taking now (git = 0 CVEs on Wolfi):

- **(A) uv embedded git — passive.** [uv issue #12324](https://github.com/astral-sh/uv/issues/12324)
  tracks embedding a minimal git (likely [gitoxide](https://github.com/GitoxideLabs/gitoxide), the
  pure-Rust git already used by cargo/Helix). If it ships, delete `git` from the `apk` line — a free win. **Watch it.**
- **(B) archive-tarball plugin source — active, ours.** Replace `git+https://forge/org/repo@<sha>`
  with `https://forge/org/repo/archive/<sha>.tar.gz`. uv fetches it over **its own HTTPS client**
  (no `git`, and no `curl` either) and builds it; we verify against our own `sha256` pin (the same
  `tap/boot_records.py` `canonical_digest_bytes` pattern), which is *stronger* provenance than git's
  object hashing. Cost: a TAP-side `archive` source type in the boot `install` section. **Take it
  with the bake-once variant** — where dropping `git` + `curl` is a free byproduct and the end-state
  runtime minimum becomes `python + uv + app`.

## FIPS analysis: buy vs. DIY OpenSSL-3-FIPS

The question: TAP principally needs **Python executing FIPS-validated crypto**. Is there a shorter
path than buying a fully FIPS-validated image, using OpenSSL 3's modular FIPS provider?

### What FIPS actually requires

FIPS 140-3 compliance is not a flag — it's a **NIST CMVP-validated crypto *module*** (a specific
compiled build), operated **in FIPS mode**, within a defined **cryptographic boundary**, with
startup self-tests and approved-algorithms-only. Two very different bars hide under "FIPS":

- **"Use FIPS-validated crypto"** — a technical control. Achievable DIY.
- **"Be FIPS-certified / attested"** (FedRAMP, DoD) — an audit posture needing the module's CMVP
  cert, STIG evidence, SBOM/VEX for *your* platform. Usually wants the **vendor's** validated image.

### OpenSSL 3 FIPS provider state (2026)

OpenSSL 3 ships a **modular FIPS provider** (`fips.so`) loaded via `openssl.cnf` (provider-based,
not the legacy `FIPS_mode_set`). Validated modules:

- **#4282** — OpenSSL 3.0 FIPS provider (the upstream, self-buildable one; older crypto).
- **#4985 / #5102** — OpenSSL 3.1.2 FIPS Provider (Chainguard rebrand, no crypto changes, 2026-01-07).
- **#5132** — **OpenSSL 3.4.0** FIPS provider (Chainguard, 2026-03-17) — *the only 3.4-based module with FIPS 140-3 validation*.
- 3.6 (adds PQC: ML-KEM/ML-DSA/SLH-DSA/LMS) submitted, pending.

**Key fact:** the validated modules for *modern* OpenSSL are largely **Chainguard's**. Upstream's
freely-buildable validated module is OpenSSL **3.0** (#4282). So "DIY with a validated module"
means either accepting OpenSSL 3.0-era crypto, or using Chainguard's (paid) modules for 3.1.2/3.4.
([Chainguard FIPS 3.1.2/#5102](https://www.chainguard.dev/unchained/chainguard-fips-enters-2026-with-openssl-3-1-2-and-better-cmvp-visibility),
[Chainguard FIPS 3.4.0/#5132](https://www.chainguard.dev/unchained/introducing-the-chainguard-fips-provider-for-openssl-3-4-0),
[CMVP #4282](https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/4282)).

### TAP's crypto surface — the good news

Everything TAP does is **already FIPS-approved algorithms**, so *no crypto redesign* either path:

- passkey / `webauthn`: **ECDSA P-256, SHA-256** — approved.
- Django sessions/CSRF/passwords: **AES-GCM, HMAC, PBKDF2-SHA256** — approved.
- our digests/compares: **SHA-256, HMAC** — approved.
- `secrets`/`os.urandom` → kernel getrandom (entropy source; strict validation prefers a validated DRBG — a boundary detail, not an algorithm problem).

### The one real technical gotcha: `cryptography` bundles its own OpenSSL

The `cryptography` package (which `webauthn` uses) **statically bundles its own OpenSSL** in wheels —
so by default it does **not** use the system (FIPS) OpenSSL at all. To route it through a FIPS
module you must **rebuild it from source against the system OpenSSL**: `uv pip install cryptography
--no-binary cryptography`. That single rebuild is the whole DIY integration point (and a standing
maintenance cost on every `cryptography` bump). ([pyca/cryptography + system OpenSSL](https://cryptography.io/en/latest/installation/),
[Python + FIPS OpenSSL discussion](https://discuss.python.org/t/python-3-with-openssl-3-fips-enabled/20287)).

### The two paths

- **Path A — buy (Chainguard `python-fips`).** FIPS-validated + STIG-hardened + FedRAMP-ready,
  daily rebuilds under SLA, SBOM/VEX evidence included. Not in the free tier (contact sales).
  Right when the ask is a **certified/attested platform**. Saves the 2-weeks-to-3-months-per-engineer
  STIG effort. ([Chainguard python-fips](https://images.chainguard.dev/directory/image/python-fips/overview),
  [STIG-hardened FIPS images](https://www.chainguard.dev/unchained/chainguards-stig-hardened-fips-images-now-generally-available)).
- **Path B — DIY-short (OpenSSL 3 FIPS provider).** Base with OpenSSL 3 + validated `fips.so`,
  Python linked to it, `cryptography` rebuilt `--no-binary` against it, FIPS mode enabled in
  `openssl.cnf`, self-tests passing. Yields **FIPS-validated crypto operations** — but *not* a
  platform CMVP certificate. Right when the ask is **"our crypto uses a validated module,"** not a
  formal certification. Ceiling: with free tooling you're on upstream OpenSSL **3.0** (#4282); modern
  (3.4) validated modules are Chainguard's.

### Recommendation

**Defer — demand-gated.** No current FIPS requirement, so build neither now. When one lands, the
decision is a single question to the customer/engagement: **"FIPS-validated crypto" (Path B suffices,
cheap) or "FIPS-certified platform with CMVP + STIG evidence" (Path A / buy)?** Because we're already
on the **Wolfi lineage**, both futures are smooth: DIY against Wolfi's OpenSSL, or buy the
Wolfi-family `python-fips`. Choosing Wolfi now is itself the FIPS-hedge.
