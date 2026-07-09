# Distroless spikes — does TAP's runtime plugin-install need an OS package manager?

Evidence for `req-cicd-base-image-lifecycle` (`specs/spec-cicd-hardening.md`).
Companion to `spikes/fips/` (the OpenSSL 3.0 #4282 FIPS recipe).

## The claim under test

The doc originally asserted: *"TAP installs deps + plugins at runtime → the base MUST ship a
package manager → curated Wolfi, NOT fixed-distroless."*

**That criterion is wrong.** `uv sync` and `uv pip install git+https://…` are *Python-package*
operations, not *OS-package* operations. They need `python`, `uv`, `git`, `bash` (+ `sed`/`grep`
/`coreutils`) — all of which can be baked at **build** time by any means. The runtime image
needs **no package manager at all**. TAP's own Dockerfile already demonstrates the principle:
`COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/` installs `uv` with zero package manager.

## What was proven (2026-07-09), both `BUILD_EXIT=0`

| Spike | Runtime base | Result |
| --- | --- | --- |
| `Dockerfile.distroless` | `cgr.dev/chainguard/python:latest` (true distroless — no apk/apt, no `/bin/sh`) | Python 3.14.6, git 2.55.0, uv 0.11.28; `uv sync` of TAP's real closure OK (`django 6.0.2`, `webauthn`); from-git install OK (`click 8.1.7`); **no package manager present** |
| `Dockerfile.ubi-micro` | `registry.access.redhat.com/ubi9/ubi-micro` (no package manager) | Python 3.14.5, git 2.52.0, uv; OpenSSL 3.5.5, `_ssl` → `/lib64/libcrypto.so.3`; `uv sync` OK; from-git install OK; **no dnf/rpm present** |

Each uses the vendor's **own** install-into-a-rootfs flow, then COPYs the rootfs into a
package-manager-less runtime:

- Wolfi: `apk add --root /rootfs --initdb …`
- Red Hat: `dnf -y install --installroot=/rootfs --releasever=9 …` (Red Hat's documented distroless build)

## Traps found (all cost real debugging — record them)

1. **`ldd` does not exist on Wolfi.** Hand-rolling the shared-library closure with
   `ldd … 2>/dev/null || true` **fails open**: it copies zero libraries and the image looks
   fine until a binary runs. Use the package manager's `--root`/`--installroot` instead — it
   resolves the closure correctly by construction.
2. **`git` is not one binary.** Its porcelain in `/usr/libexec/git-core` (`git-submodule`,
   `git-sh-setup`, …) are **shell scripts** that shell out to `sed`/`grep`. `git ls-remote`
   works without them; `uv pip install git+https://…` runs `git submodule update` and dies with
   `sed: command not found`. A distroless image carrying git must bake `sed`, `grep`, `coreutils`.
3. **`/bin`, `/sbin`, `/lib`, `/lib64` are symlinks into `/usr/`** in both distroless bases.
   A staged rootfs that materializes them as real dirs makes `COPY` fail with
   `cannot copy to non-directory`. Merge into the real `/usr/*` dirs first.
4. **Red Hat disabled `openssl fipsinstall`** — see below. This is the load-bearing difference.

## The FIPS split (the actual decision)

Both families ship **OpenSSL 3.x** with Python dynamically linked to the *system* `libcrypto.so.3`,
so the FIPS precondition holds on both. But they activate FIPS in **incompatible ways**:

- **Wolfi / upstream OpenSSL — FIPS is *in-image* and host-independent.** `openssl fipsinstall`
  works; our self-built #4282 `fips.so` activates via `OPENSSL_CONF`. Proven end-to-end in
  `spikes/fips/`. Portable to any host. Cost: Wolfi is not a #4282-*tested* Operational
  Environment → relies on FIPS 140-3 **vendor-affirmed** OE portability.
- **Red Hat — FIPS is *host-derived*.** `openssl fipsinstall` is **deliberately disabled**
  (*"This command is not enabled in the Red Hat Enterprise Linux OpenSSL build"*). RH ships
  `/usr/lib64/ossl-modules/fips.so` but **no `fipsmodule.cnf`**; `openssl.cnf` defers to
  `/etc/crypto-policies/back-ends/opensslcnf.config`, and the container inherits FIPS from the
  **host kernel** (`fips=1`, `/proc/sys/crypto/fips_enabled`). Upside: RHEL 9 *is* a tested OE
  for Red Hat's validated module — the vendor-affirmation risk largely disappears. Downside: it
  is **not self-contained** — a container we ship cannot turn FIPS on by itself.

For a **self-hosted product shipped to customers whose hosts we do not control**, in-image FIPS
(Wolfi + #4282) is portable; RHEL's host-derived FIPS is not — unless the customer already runs
FIPS-mode hosts (which FedRAMP/DoD customers frequently do).

## Other measured facts

- **Python 3.14 availability** (our `requires-python = ">=3.14"` is the hard filter):
  Chainguard `python:latest` **3.14.6** (anon-pullable) · UBI9 `dnf install python3.14` → **3.14.5**
  · Google Distroless `python3-debian13` → **3.13.5** (out; the debian12 line showing 3.11.2 is deprecated)
  · UBI9 default python → 3.9.25.
- **DHI** lives at **`dhi.io`** (not any `docker.io` namespace) and returns **HTTP 401** — a free
  Docker Hub login is genuinely required, which cuts against `req-cicd-base-image-sourcing`'s
  anonymous-pull property. Reported to publish Python 3.14 + a free `-fips` variant: **unverified**.
- **UBI9 Postgres client caps at 13.23**; TAP's pre-boot snapshot (`req-boot-snapshot`) shells out
  to `pg_dump`/`pg_restore` against a **PG16** server, and `pg_dump` 13 refuses a newer server.
  Wolfi ships `pg_isready 18.4`. Fixable on UBI via the PGDG repo, but it is real friction.
- **CVE posture on the UBI path is unmeasured.** Wolfi measured 0 OS-CVEs vs 311 on `python:3.14-slim`.
  No equivalent Trivy scan has been run for `ubi-micro` + our rootfs. Do not assume parity.

## Reproduce

```sh
docker build -f spikes/distroless/Dockerfile.distroless --target proof -t tap-distroless:proof .
docker build -f spikes/distroless/Dockerfile.ubi-micro  --target proof -t tap-ubi:proof .
```

Both print `EXPECTED:` on every assertion when green.
