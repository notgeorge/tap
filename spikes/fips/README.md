# FIPS spike — self-built OpenSSL 3.0 #4282 on Wolfi

Executable proof for `req-cicd-base-image-lifecycle-5` (`specs/spec-cicd-hardening.md`).
Answers: *how do we run the free upstream OpenSSL 3.0.9 FIPS provider (CMVP #4282) on the
web/DB containers such that Python — including `cryptography`/`webauthn` — routes crypto
through it?* Full analysis + evidence: `docs/misc/doc-hardened-base-image-landscape.md`
§ "FIPS analysis" / § "Spike evidence".

This is a **spike artifact**, not production wiring. The real image work (fold into the
actual `Dockerfile` + `docker-compose` Postgres, `[tool.uv] no-binary-package`, boot + full
test-lane validation) is the ~2026-09 productionization tracked by the requirement.

## Reproduce

```sh
# 0. Postgres: does the recipe transplant to the DB container? (+ the collation hazard)
docker build -f spikes/fips/Dockerfile.postgres --target proof -t tap-pg-fips:proof .

# 1. Build the validated 3.0.9 fips.so on Wolfi (retires "can we build it ourselves").
docker build -f spikes/fips/Dockerfile.fips --target ossl-builder  -t tap-fips:builder .

# 2. Activate it on Wolfi's MODERN system OpenSSL + prove Python stdlib inherits it (no rebuild).
docker build -f spikes/fips/Dockerfile.fips --target fips-runtime  -t tap-fips:runtime .

# 3. The TAP-specific proof: cryptography (webauthn's engine) --no-binary through FIPS.
docker build -f spikes/fips/Dockerfile.fips --target crypto-runtime -t tap-fips:crypto  .
```

Each stage's build log prints `EXPECTED:` on every assertion when green. Proven 2026-07-09:
3.0.9 `fips.so` builds; Wolfi's system OpenSSL 3.6.3 `fipsinstall`s + self-tests it
(binary-compat linchpin); providers activate (md5 refused); Python `_hashlib` md5 blocked
with no rebuild; `cryptography 49.0.0 --no-binary` does P-256 ECDSA verify through FIPS while
md5 → `InternalError`. All at $0 license on the free #4282 certificate.
