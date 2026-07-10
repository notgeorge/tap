---
spec: ../../specs/spec-cicd-hardening.md
audience: [llm, developer, assessor]
covers:
  - ../../specs/spec-cicd-hardening.md
  - req-cicd-base-image-lifecycle-5
  - req-cicd-base-image-lifecycle-6
update-triggers:
  - The FIPS recipe is productionized into the real Dockerfile / docker-compose
  - A dependency bump introduces a bare hashlib.md5() in a runtime dependency
  - The compliance authority rules on vendor-affirmed Operational Environment portability
  - OpenSSL publishes a newer free/upstream validated FIPS provider (post-#4282)
  - The base image changes away from Wolfi
assumes:
  - Reader may be an AI assistant validating or extending TAP's FIPS posture
  - Wolfi is the standard base (req-cicd-base-image-lifecycle-3)
provides: |
  The complete FIPS decision record, lessons learned, assessment methodology, and a
  re-runnable verification suite for TAP's self-built OpenSSL 3.0 #4282 FIPS provider.
  Written as a handoff artifact: an AI (or human) assessor should be able to validate
  the implementation, or resume the assessment, using only this document plus spikes/.
---

# TAP FIPS Assessment Record

**Status:** recipe **spike-proven end-to-end** (2026-07-09); productionization targeted ~2026-09.
**Requirements:** `req-cicd-base-image-lifecycle-5` (the recipe), `-6` (the build flag, default ON).
**Executable evidence:** `spikes/fips/` and `spikes/distroless/`.

## 0. How to use this document

If you are an **AI assistant** asked to validate, extend, or productionize TAP's FIPS posture:

1. Read §1 (what FIPS means here) so you don't conflate the two very different bars.
2. Read §2 (decisions) — these are settled; do not silently re-litigate them. Each carries its
   reversal trigger.
3. Read §4 (lessons) **before writing any code**. Several are fail-*open* traps: the system looks
   compliant while enforcing nothing. They cost real debugging and will recur.
4. Run §6 (the verification suite) to establish ground truth on the current image. **Do not trust
   this document's measurements over a fresh run** — they were true on 2026-07-09 against specific
   image digests, and base images move.
5. Consult §7 (open risks) for what is genuinely unresolved. Do not report those as closed.

If you are a **human**: §1, §2, §4, and §7 are the substance. §3 is the recipe, §6 is how to check it.

The governing principle throughout, from `specs/spec-security-posture.md`:

> **Assert, don't assume.** A configuration that "parses cleanly" is not a configuration that
> *took effect*. Every FIPS claim in this document is backed by a negative control — proof that a
> non-approved primitive is actually *refused* — not merely by the absence of an error.

## 1. What "FIPS" actually means here (two different bars)

FIPS 140-3 compliance is not a flag. It is a **NIST CMVP-validated cryptographic *module*** (a
specific compiled artifact), operated **in FIPS mode**, inside a defined **cryptographic boundary**,
with power-on self-tests and approved-algorithms-only. Two very different bars hide under the word:

| Bar | What it means | Achievable by us? |
| --- | --- | --- |
| **"Use FIPS-validated crypto"** | A technical control: crypto operations execute inside a validated module. | **Yes, DIY.** This is what we built and proved. |
| **"Be a FIPS-certified platform"** | An audit posture (FedRAMP, DoD): the module's CMVP certificate covers *your* Operational Environment, and a 3PAO signs off. | Partly. Depends on the OE question — see §7.1. |

TAP targets the first bar and positions itself for the second. **When someone says "we need FIPS,"
find out which bar they mean before designing anything.** The answer changes the base image.

### The relevant CMVP certificates

- **#4282** — OpenSSL 3.0 FIPS Provider (covers OpenSSL 3.0.8 / 3.0.9). **Free, upstream, self-buildable.** ← what we use.
- **#5102** — OpenSSL 3.1.2 FIPS Provider (Chainguard rebrand). Paid. Not needed.
- **#5132** — OpenSSL 3.4.0 FIPS Provider (Chainguard). Paid. Not needed.

## 2. Decisions (settled — each with its reversal trigger)

| # | Decision | Rationale | Reverses if… |
| --- | --- | --- | --- |
| D1 | **FIPS is a hard requirement**, targeted ~2026-09; not demand-gated. | Frontlined by George, 2026-07-09. | — |
| D2 | Use the **free upstream OpenSSL 3.0 #4282** provider. No vendor/Chainguard module. | #4282 is sufficient and costs $0. Vendor modules buy nothing we need. | A validated module is required for an OE we cannot vendor-affirm (§7.1). |
| D3 | **Build `fips.so` ourselves** in a builder stage, per the #4282 security policy's build instructions. | The build recipe is part of what is validated. | — |
| D4 | Run the **frozen 3.0.9 `fips.so` against the base's modern libcrypto.** | OpenSSL guarantees a certified `fips.so` is binary-compatible with **any later** libcrypto. Verified: Wolfi's OpenSSL **3.6.3** `fipsinstall`ed and self-tested our 3.0.9 module. **Therefore OpenSSL 3.0's Sept-2026 LTS-EOL is irrelevant** — base libs stay patched; only the validated module is frozen. | OpenSSL revokes the compatibility guarantee. |
| D5 | Activate via **`openssl fipsinstall` in-image** + an `openssl.cnf` + `ENV OPENSSL_CONF`. | `fipsinstall` runs self-tests and writes the module's integrity **MAC**. It must run in the final image; if `fips.so`'s bytes change without re-running it, the provider refuses to load. | — |
| D6 | **Strict provider set: `fips` + `base` only. No `default` provider.** | Loading `default` would silently re-supply every non-approved algorithm. | Never, for convenience. Only if an unavoidable non-security consumer cannot use `usedforsecurity=False`. |
| D7 | Build **`cryptography` `--no-binary`** against the system OpenSSL — **in both FIPS and non-FIPS modes.** | Its wheel *statically bundles its own OpenSSL* and would bypass the system FIPS provider entirely. Building it the same way in both modes means only *provider activation* differs; otherwise non-FIPS passes on a bundled wheel and FIPS breaks at the far end of the pipeline. | — |
| D8 | Set **`CRYPTOGRAPHY_OPENSSL_NO_LEGACY=1`**. | Otherwise `cryptography` loads OpenSSL's legacy provider, silently re-enabling MD5/DES. | — |
| D9 | **No Python rebuild.** | Wolfi's `python-3.14` dynamically links the *system* libcrypto, so `hashlib`/`ssl`/`hmac` inherit the activated provider for free. Verified. | The base ships a statically-linked or vendored-OpenSSL Python. |
| D10 | **Postgres gets the identical recipe** on a minimal `wolfi-base` + `apk postgresql-16`. | Postgres links the system OpenSSL for TLS + `pgcrypto`. One provider artifact, one recipe, both containers. | — |
| D11 | **Wolfi is the standard base**; in-image FIPS chosen over RHEL's host-derived FIPS. | We ship a self-hosted product onto **customer-controlled hosts**. An in-image FIPS container is FIPS anywhere. A RHEL container **cannot enable FIPS by itself** (§4.10). | The compliance authority rejects vendor-affirmed OE (§7.1) → move to UBI + FIPS-mode hosts. |
| D12 | **`ARG TAP_FIPS`, default `1`.** FIPS-on is the published artifact. | Secure by default. | — |
| D13 | `TAP_FIPS=0` is an **explicitly-requested escape hatch, never a silent fallback.** CI builds and gates both variants so the non-FIPS lane cannot rot. | — | — |
| D14 | The image **declares its mode machine-legibly**: OCI label `org.tap.fips=true\|false` + `ENV TAP_FIPS_MODE`. | CI, the boot record, `/healthz`, and an AI operator can read posture **without executing crypto** (`specs/spec-ai-integration.md`). | — |
| D15 | **Boot must PROVE the declared mode** (fips provider active **and** a non-approved primitive actually refused) or emit `TAP-ABORT` and refuse to serve. | Fail closed. See L1 — a config can parse cleanly and enforce nothing. | Never. |
| D16 | **Alternatives are parked, not eliminated**, with named reopen triggers. | The distroless bases work (proven); they lost on Python currency + FIPS model, not on capability. | §7.1, bake-once adoption, or Wolfi regression. |

## 3. The proven recipe

Five steps. Reproducible via `spikes/fips/Dockerfile.fips` (three stages, all green).

1. **Builder stage — build the validated provider.** Compile OpenSSL **3.0.9** with
   `./Configure enable-fips && make && make install_fips`. Output: `fips.so`.
2. **Drop it into the runtime base's `ossl-modules/` dir**, then run
   `openssl fipsinstall -out /etc/ssl/fipsmodule.cnf -module /usr/lib/ossl-modules/fips.so`.
   This runs the module self-tests and writes the integrity MAC. **Must happen in the final image.**
3. **Point OpenSSL at a FIPS config** and export `OPENSSL_CONF`. Exact content, **ordering is
   load-bearing** (see L1):

   ```ini
   config_diagnostics = 1
   openssl_conf = openssl_init

   .include /etc/ssl/fipsmodule.cnf

   [openssl_init]
   providers = provider_sect
   alg_section = algorithm_sect

   [provider_sect]
   fips = fips_sect
   base = base_sect

   [base_sect]
   activate = 1

   [algorithm_sect]
   default_properties = fips=yes
   ```

4. **Python stdlib inherits it with no rebuild.** `hashlib`, `ssl`, `hmac` route through the
   activated provider because Wolfi's CPython dynamically links the system libcrypto.
5. **Build `cryptography` `--no-binary`** against the system OpenSSL, with
   `CRYPTOGRAPHY_OPENSSL_NO_LEGACY=1`, baked at build time (so the runtime carries no Rust/C
   toolchain). In uv: `[tool.uv] no-binary-package = ["cryptography"]`.

Both Python stdlib crypto and `cryptography`/`webauthn` then execute inside the validated 3.0.9
module. **TAP's algorithms are all FIPS-approved** (P-256/ECDSA, SHA-256, HMAC, PBKDF2, AES-GCM),
so nothing is redesigned.

## 4. Lessons learned

Ordered by how badly each will bite you. **L1, L2, and L5 are fail-*open*: the system appears
compliant while enforcing nothing.** These are the dangerous ones.

### L1 — `openssl.cnf` directive order silently disables FIPS entirely ⚠️ FAIL-OPEN

**Symptom:** Config parses with no error. `openssl list -providers` shows only *"OpenSSL Default
Provider"*. `md5` succeeds. FIPS is not enforced anywhere, including in Python.

**Root cause:** `openssl_conf = openssl_init` must live in the **default (pre-section) block**. The
`.include /etc/ssl/fipsmodule.cnf` pulls in a file that **starts with `[fips_sect]`** — so if the
`.include` comes first, every subsequent directive (including `openssl_conf`) is parsed as belonging
to `[fips_sect]`. OpenSSL never sees a global `openssl_conf`, ignores the provider config, and falls
back to its built-in default provider.

**Fix:** `openssl_conf` first, `.include` after. See §3 step 3.

**Detection:** Never conclude FIPS is on because the build succeeded. Assert
`openssl list -providers` contains `fips` **and** that `md5` is refused.

### L2 — Hand-rolling a shared-library closure with `ldd` fails open on Wolfi ⚠️ FAIL-OPEN

**Symptom:** A staged rootfs looks complete; binaries mysteriously fail at runtime with
`error while loading shared libraries: libpcre2-8.so.0`.

**Root cause:** **Wolfi ships no `ldd` binary.** A staging script of the shape
`ldd "$bin" 2>/dev/null | ... || true` copies **zero** libraries and reports success. Some binaries
still work because their libs happen to exist in the base — masking the bug.

**Fix:** Never hand-roll the closure. Use the package manager's own install-into-a-root flow:
`apk add --root /rootfs --initdb` (Wolfi) or `dnf install --installroot=/rootfs` (Red Hat). These
resolve the dependency closure correctly by construction.

**Meta-lesson:** `2>/dev/null || true` around a *discovery* step converts a hard failure into a
silent wrong answer. Never suppress errors on a step whose output you then trust.

### L3 — `git` is not one binary; its porcelain are shell scripts

**Symptom:** `git ls-remote` works; `uv pip install git+https://…` dies with `sed: command not found`.

**Root cause:** Helpers in `/usr/libexec/git-core` (`git-submodule`, `git-sh-setup`, …) are **shell
scripts** that shell out to `sed`/`grep`. `uv`'s git install runs `git submodule update --init`.

**Fix:** A minimal image carrying `git` must also carry `sed`, `grep`, `coreutils`. These are now
named as non-optional in `req-cicd-base-image-lifecycle-3`.

### L4 — `/bin`, `/sbin`, `/lib`, `/lib64` are symlinks into `/usr/`

**Symptom:** `COPY --from=builder /rootfs /` fails with `cannot copy to non-directory: …/bin`.

**Root cause:** Distroless bases (Chainguard, and RHEL's usr-merge) symlink these into `/usr/`. A
staged rootfs that materializes them as real directories cannot overlay a symlink.

**Fix:** Merge staged content into the real `/usr/bin`, `/usr/lib` before the `COPY`.

### L5 — `hashlib.md5` has a builtin fallback that masks non-enforcement ⚠️ FAIL-OPEN (in tests)

**Symptom:** You "prove" FIPS blocks MD5 in Python via `hashlib.md5()`. On a different base it
passes even with FIPS off, because CPython falls back to a built-in `_md5`.

**Root cause:** `hashlib` is a façade. It prefers `_hashlib` (OpenSSL) but can fall back to
compiled-in `_md5`/`_sha1`/`_sha2` modules.

**Fix:** Probe the **lowest layer that cannot fall back**: `_hashlib.new("md5", b"x")`. On Wolfi's
CPython the builtins `_md5`/`_sha1`/`_sha2`/`_sha3` are **absent** (verified), so `hashlib.sha256`
genuinely is `_hashlib`-backed — but do not rely on that on another base. Assert the module:
`type(hashlib.sha256()).__module__ == "_hashlib"`.

### L6 — SHA-1 is FIPS-**approved**. Do not assume "not SHA-256 ⇒ banned."

SHA-1 is an approved hash under FIPS 140-3 (restricted only for *signature generation*). It is
served by the `fips` provider. `hashlib.sha1()` works under FIPS. **Only MD5 hard-fails** among the
common hashes. Auditing for "any non-SHA-256 hash" produces a large false-positive list.

### L7 — `uuid5` is SHA-1 and `uuid3` is MD5: crypto hides in the stdlib

This was the **real landmine**. TAP mints deterministic node/edge ids with `uuid5` in **17 files**.
Had `uuid5` broken, FIPS-default-on would have bricked boot.

It is **safe**, for two independent reasons: SHA-1 is approved (L6), *and* CPython 3.14's `uuid5`
passes `usedforsecurity=False` internally. Verified directly.

**Generalize this:** grep for `hashlib`/`hmac` is *not* a sufficient crypto audit. Hashing hides in
`uuid3`/`uuid5`, cache-key derivation, ETag generation, template fragment keys, and DB index-name
digests. Enumerate the *primitives reached*, not the *call sites named*.

### L8 — `usedforsecurity=False` reaches MD5 via a separate non-FIPS library context

`hashlib.md5(b"x", usedforsecurity=False)` **succeeds** under a strict `fips`+`base` provider set,
and is served by `_hashlib` (OpenSSL) — *not* a Python builtin (which doesn't exist on Wolfi).
CPython maintains a **separate non-FIPS `OSSL_LIB_CTX`** for exactly this purpose.

FIPS 140-3 **permits** non-approved algorithms for non-security purposes, and `usedforsecurity=False`
is the auditor-recognized signal. This is legitimate — **but it is a reachable, non-validated path.**
Name it in the risk register; do not imply MD5 is absent from the process.

### L9 — `cryptography`'s wheel bundles its own OpenSSL

The single biggest integration trap for a Python FIPS story. `pip install cryptography` gives you a
wheel with a **statically linked, private OpenSSL** that ignores the system provider config entirely.
Everything else can be perfectly configured and `webauthn` will still not be doing FIPS crypto.
`--no-binary cryptography` is mandatory (D7).

### L10 — Vendors implement FIPS in incompatible ways: **in-image vs host-derived**

The discovery that decided the base image.

- **Upstream OpenSSL (Wolfi):** `openssl fipsinstall` works. FIPS is configured **in the image** and
  is **host-independent**. A container we ship is FIPS anywhere.
- **Red Hat (UBI):** `openssl fipsinstall` is **deliberately disabled** —
  *"This command is not enabled in the Red Hat Enterprise Linux OpenSSL build."* RH ships
  `/usr/lib64/ossl-modules/fips.so` but **no `fipsmodule.cnf`**; `openssl.cnf` defers to
  `/etc/crypto-policies/back-ends/opensslcnf.config`, and the container inherits FIPS from the
  **host kernel** (`fips=1`, `/proc/sys/crypto/fips_enabled`).

**The trade:** RHEL 9 *is* a CMVP-**tested** OE for Red Hat's validated module, which would resolve
our OE risk (§7.1). But a RHEL container **cannot turn FIPS on by itself** — fatal when you don't
control the customer's host. Hence D11.

**Check `openssl fipsinstall` availability on any candidate base, early.** It tells you which model
you're in, in one command.

### L11 — Ecosystem facts we got wrong until we measured them

Every one of these was asserted confidently (by me, or by a research pass) and was **false**:

| Claim | Reality (measured 2026-07-09) |
| --- | --- |
| "TAP's runtime install requires a package manager in the runtime image." | False. `uv sync` / `uv pip install git+…` are *Python-package* ops. Proven: a runtime with no `apk`/`apt` and **no `/bin/sh`** does both. |
| "RHEL caps at Python 3.12." | False. `dnf install python3.14` on UBI9 → **3.14.5**. |
| "Google Distroless ships Python 3.14." | False. `python3-debian13` → **3.13.5**. (The 3.11.2 I first measured was the *deprecated* debian12 line.) |
| "DHI is at some `docker.io` namespace." | False. It is **`dhi.io`**, and anonymous pull returns **HTTP 401**. |
| "Fixed/distroless images can't have packages added." | False. Every one supports build-time addition (`apk --root`, `dnf --installroot`, multi-stage `COPY`, apko, Nix). |

### L12 — Verify you are reading the *right* exit code

A background build wrapper reported `exit 0` because the last command in the pipeline was `tail`.
The build had actually **failed**. Use `set -o pipefail`, capture `$?` immediately after the command
under test, and print it explicitly. An assessment harness that lies about pass/fail is worse than none.

## 5. TAP's actual crypto surface (audit result, 2026-07-09)

| Surface | Finding |
| --- | --- |
| **TAP's own code** | Clean. **Zero** `md5`, **zero** `sha1`, **zero** `uuid3`. Only `hashlib.sha256` (13 call sites) and `hmac.compare_digest` (2). |
| **`uuid5`** | 17 files (collectors, `identity_core`, `github_core`, `samsite`, `fedramp_20x_ksi`). SHA-1-based. **Safe** (L7). |
| **Django** | Bare `hashlib.md5()` exists **only** in the legacy `MD5PasswordHasher`, which is **not** in Django's default `PASSWORD_HASHERS`, and TAP does not override them → **unreachable**. |
| **`faker`** | Bare `md5()`/`sha1()` — **test-only** dependency. |
| **`cryptography`, `webauthn`, `oauthlib`, `django.template.loaders.cached`** | Bare `sha1()` — approved, all work. |
| **Verdict** | **No runtime hard-fail surface.** `TAP_FIPS=1` by default is safe. |

TAP's algorithms — P-256/ECDSA (passkeys), SHA-256, HMAC, PBKDF2, AES-GCM — are **all
FIPS-approved**. No crypto redesign is required by FIPS.

## 6. Verification suite (re-runnable ground truth)

**Run this before trusting any measurement in this document.** Base images move.

```sh
# Full recipe, three stages. Every assertion prints EXPECTED: when green; the build fails otherwise.
docker build -f spikes/fips/Dockerfile.fips --target ossl-builder   -t tap-fips:builder .
docker build -f spikes/fips/Dockerfile.fips --target fips-runtime   -t tap-fips:runtime .
docker build -f spikes/fips/Dockerfile.fips --target crypto-runtime -t tap-fips:crypto  .

# The distroless / package-manager disproof (context for the base-image decision).
docker build -f spikes/distroless/Dockerfile.distroless --target proof -t tap-distroless:proof .
docker build -f spikes/distroless/Dockerfile.ubi-micro  --target proof -t tap-ubi:proof .
```

### The assertions that must hold

Each is stated as a **falsifiable check with a negative control**. A FIPS claim backed only by
"the approved thing worked" is worthless; you must also show the non-approved thing was *refused*.

| ID | Check | Expected |
| --- | --- | --- |
| `F1` | `openssl list -providers` | contains `fips` **active**, version `3.0.9`; `default` **absent** |
| `F2` | `openssl fipsinstall … -module fips.so` | self-tests pass, MAC written (proves binary-compat) |
| `F3` | `echo x \| openssl dgst -sha256` | succeeds (approved) |
| `F4` | `echo x \| openssl dgst -md5` | **fails** — `evp_generic_fetch: unsupported` (negative control) |
| `F5` | `python -c "import ssl; print(ssl.OPENSSL_VERSION)"` | matches the **system** OpenSSL (proves dynamic linkage, no rebuild) |
| `F6` | `_hashlib.new("md5", b"x")` | raises `ValueError` (negative control, no builtin fallback) |
| `F7` | `type(hashlib.sha256()).__module__` | `"_hashlib"` (proves OpenSSL-backed, not a builtin) |
| `F8` | `hashlib.sha1(b"x")` | succeeds (SHA-1 is approved — L6) |
| `F9` | `uuid.uuid5(uuid.NAMESPACE_DNS, "x")` | succeeds (L7 — the boot-critical one) |
| `F10` | `cryptography` `backend.openssl_version_text()` | matches **system** OpenSSL (proves `--no-binary` worked, not the bundled wheel) |
| `F11` | `ec.generate_private_key(ec.SECP256R1())` + sign + verify | succeeds (the passkey path, through FIPS) |
| `F12` | `hashes.Hash(hashes.MD5())` via `cryptography` | raises `InternalError` (negative control) |
| `F13` | grep the installed dep closure for `hashlib.md5(` without `usedforsecurity=False` | only `MD5PasswordHasher` (unreachable) + `faker` (test-only) |

Machine-readable form for an automated assessor:

```json
{
  "assessment": "tap-fips-openssl-4282",
  "recorded": "2026-07-09",
  "provider_set": ["fips", "base"],
  "module": {"cert": "CMVP #4282", "version": "3.0.9", "self_built": true},
  "host_libcrypto": {"measured": "3.6.3", "binary_compat_verified": true},
  "checks": [
    {"id": "F1",  "kind": "positive", "target": "openssl-cli",   "assert": "fips provider active"},
    {"id": "F4",  "kind": "negative", "target": "openssl-cli",   "assert": "md5 refused"},
    {"id": "F6",  "kind": "negative", "target": "python-_hashlib","assert": "md5 raises ValueError"},
    {"id": "F7",  "kind": "positive", "target": "python-hashlib", "assert": "sha256 backed by _hashlib"},
    {"id": "F9",  "kind": "positive", "target": "python-uuid",    "assert": "uuid5 works (SHA-1 approved)"},
    {"id": "F10", "kind": "positive", "target": "cryptography",   "assert": "links system OpenSSL"},
    {"id": "F11", "kind": "positive", "target": "cryptography",   "assert": "P-256 ECDSA sign+verify"},
    {"id": "F12", "kind": "negative", "target": "cryptography",   "assert": "MD5 raises InternalError"}
  ],
  "invariant": "every positive check MUST be paired with a negative control; a passing positive check alone does not evidence enforcement"
}
```

## 7. Open risks — do NOT report these as closed

### 7.1 Operational Environment (OE) vendor-affirmed portability ⚠️ the one that matters

**Status: unresolved. Non-technical. Highest leverage.**

#4282's security policy lists the platforms on which the module was **tested**. Wolfi is not among
them. We therefore rely on **FIPS 140-3 vendor-affirmed portability** (same CPU architecture, same
libc; the vendor — us — affirms correct operation). This is common and widely accepted, **but the
3PAO / compliance authority has final say.**

**Action:** confirm acceptance *before* productionizing. If rejected, the landing spot is the
already-proven `ubi-micro` + `dnf --installroot` path (`spikes/distroless/Dockerfile.ubi-micro`),
accepting RHEL's **host-derived** FIPS — which means the deployment host must run `fips=1`.

This single answer determines the base image. It is worth asking early and explicitly.

### 7.2 `usedforsecurity=False` is a reachable non-validated path

Documented in L8. Permitted by FIPS for non-security use. Must be **named** in the risk register,
not implied absent. An assessor will ask.

### 7.3 `_blake2` remains a built-in, non-validated implementation

Wolfi's CPython omits `_md5`/`_sha1`/`_sha2`/`_sha3` but **ships `_blake2`**. An in-process
non-validated hash implementation is therefore importable. Not used by TAP; disclose it.

### 7.4 Dependency drift is a boot-breaking regression class

Under `TAP_FIPS=1`, a **new bare `hashlib.md5()` in a runtime dependency crashes boot.** This is
exactly what the fail-closed boot check (D15) is designed to catch, but it should be caught earlier:
**re-run check `F13` on every Renovate auto-patch PR** (`req-cicd-base-image-lifecycle-1`).

### 7.5 `fipsinstall` reproducibility

The MAC pins the exact `fips.so` bytes. It must run **in the final image**, and must re-run if the
module is rebuilt. Fits the build-stage model; noted so nobody "optimizes" it into a cached layer.

### 7.6 Not yet done

The recipe is **spike-proven, not productionized.** Still outstanding:

- Fold into the real `Dockerfile` + `docker-compose` Postgres image.
- `[tool.uv] no-binary-package = ["cryptography"]`.
- `ARG TAP_FIPS` wiring, the `org.tap.fips` label, `TAP_FIPS_MODE` env (D12–D14).
- The fail-closed boot assertion (D15) + its **Validation Map row** (`req-dev-validation-map`).
- Full boot + test-lane validation under `TAP_FIPS=1`.
- CI gating of **both** variants (D13).

## 8. The assessment methodology (reusable)

How the above was established, stated generally so it can be re-applied.

1. **Separate the two bars first** (§1). "We need FIPS" is ambiguous and the answer changes the
   architecture. Ask which one.
2. **Find the load-bearing claim and test *it*, not its neighbours.** Here it was: *can a frozen,
   validated 3.0.9 `fips.so` load into a modern libcrypto?* Everything else was downstream of that
   one yes/no. It was tested in the first build.
3. **Every positive check needs a negative control.** "sha256 works" evidences nothing about
   enforcement. "md5 is *refused*" does. A FIPS assessment without negative controls is theatre.
4. **Probe the lowest layer that cannot fall back.** `hashlib` façades over `_hashlib`; `_hashlib`
   cannot fall back. Test at the layer where a silent alternative implementation does not exist (L5).
5. **Distinguish "parsed" from "took effect."** Ask the system to *report its state*
   (`openssl list -providers`), don't infer state from the absence of an error (L1).
6. **Suppressing errors on a discovery step converts failure into a silent wrong answer.**
   `2>/dev/null || true` around anything whose output you subsequently trust is a bug (L2).
7. **Measure; don't cite.** Every ecosystem claim in L11 was confidently asserted and false. Pull the
   image, run the binary, read the version. A research pass proposes; a `docker run` disposes.
8. **Enumerate primitives reached, not call sites named.** Grepping `hashlib` misses `uuid5` (L7).
   Ask "what crypto executes," then find who calls it.
9. **Audit the dependency closure, not just first-party code.** The one real MD5 risk lived in
   Django and `faker`, not in TAP.
10. **Verify the harness itself.** Confirm you're reading the exit code of the thing under test (L12).
11. **Record what is *not* proven.** §7 exists so the next assessor doesn't inherit false confidence.

## 9. Provenance

All measurements 2026-07-09, arm64 (Apple Silicon), on:
`cgr.dev/chainguard/wolfi-base` (system OpenSSL **3.6.3**, CPython **3.14.6**),
self-built OpenSSL **3.0.9** FIPS provider (**CMVP #4282**), `cryptography` **49.0.0** built
`--no-binary`. Comparators: `cgr.dev/chainguard/python:latest{,-dev}`,
`registry.access.redhat.com/ubi9/{ubi,ubi-minimal,ubi-micro,python-312}`, `ubi10/ubi-minimal`,
`gcr.io/distroless/python3-debian13`, `dhi.io/python` (401, unverified).

Evidence: `spikes/fips/`, `spikes/distroless/`.
Commits: `1fbadf11` (FIPS spike), `53e7b15a` (distroless disproof), `08ec2905` (spec + FIPS default-on).

## References

- [OpenSSL `fips_module(7)`](https://docs.openssl.org/3.3/man7/fips_module/) — the binary-compatibility guarantee (D4)
- [OpenSSL README-FIPS](https://github.com/openssl/openssl/blob/master/README-FIPS.md)
- [CMVP #4282](https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/4282)
- [OpenSSL 3.0.9 FIPS validated](https://www.openssl.org/blog/blog/2024/01/23/fips-309/)
- [pyca/cryptography installation (system OpenSSL)](https://cryptography.io/en/latest/installation/)
- [pyca/cryptography bundled-OpenSSL FIPS issue #5008](https://github.com/pyca/cryptography/issues/5008)
- [Red Hat: adding software to a UBI container (`dnf --installroot`)](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/building_running_and_managing_containers/assembly_adding-software-to-a-ubi-container_building-running-and-managing-containers)
- Companion doc: [doc-hardened-base-image-landscape](doc-hardened-base-image-landscape.md)
