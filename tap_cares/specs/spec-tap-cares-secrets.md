# tap-cares Secrets Specification

## Philosophy

tap-cares secrets are local runtime inputs for collectors, receivers, emitters, actions, and other tap-cares capabilities that need sensitive material to interact with external systems.

v0 secrets are deliberately boring. Secret values live off-grid in a dedicated mounted secrets directory. tap-cares loads explicitly named JSON files from that directory into an internal scoped registry at Django startup. Runtime code resolves secrets through tap-cares helper functions rather than reading files directly or passing raw `scope:key` strings through capability code.

The grid may eventually know about secret references, health, usage, policy, and schema metadata. The grid does not store secret values in v0.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Local-first   | Support local/offline deployments with secrets mounted into the TAP container |
| 2. | Obvious       | Make secret files visually unmistakable and easy to ignore in git |
| 3. | Controlled    | Route secret access through one tap-cares resolver and registry |
| 4. | Minimal       | Avoid premature vault, encryption, and schema infrastructure |
| 5. | Future-ready  | Leave room for on-grid Secret metadata and generated secret files |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-cares-secrets-scope | [Secrets Scope](#secrets-scope) | Implemented | Secret material is off-grid runtime data |
| req-tap-cares-secrets-files | [Secret Files](#secret-files) | Implemented | Recursive `*.secret.json` discovery under a configured secrets root |
| req-tap-cares-secrets-resilient-load | [Resilient Load And Failure Surfacing](#resilient-load-and-failure-surfacing) | Implemented | Bad files are recorded (not crash-raised); `required_for_boot` escalates to blocking; surfaced via system check + the `tap_health` secrets probe |
| req-tap-cares-secrets-shape | [Secret JSON Shape](#secret-json-shape) | Implemented | Minimal required JSON object fields |
| req-tap-cares-secrets-registry | [Secret Registry And Resolution](#secret-registry-and-resolution) | Implemented | Internal `ScopedRegistry` plus `SecretRef` / `resolve_secret` helpers |
| req-tap-cares-secrets-validation | [Consumer Validation](#consumer-validation) | Implemented | Consumers validate kind-specific secret data |
| req-tap-cares-secrets-redaction | [Redaction And Failure Behavior](#redaction-and-failure-behavior) | Implemented | Secret material must not leak into logs or run records |
| req-tap-cares-secrets-consumer-kinds | [Consumer-Defined Secret Kinds](#consumer-defined-secret-kinds) | Implemented | Kind `data` shapes are owned by consuming plugin/collector specs, not here |
| req-tap-cares-secrets-conditional-validation | [Conditional Validation Lives In Health Probes](#conditional-validation-lives-in-health-probes) | Implemented | Whether a secret is *needed* is per-consumer conditional logic owned by health probes, not a static declaration; tap_cares owns only generic file-level load/format |
| req-tap-cares-secrets-rotation | [Rotation Semantics](#rotation-semantics) | Implemented | v0 is restart-to-rotate; atomic reload / staleness / rotation-due are named-deferred |
| req-tap-cares-secrets-leak-guard | [Source-Control Leak Guard](#source-control-leak-guard) | Implemented | A committed `*.secret.json` (or an envelope-shaped file outside the mount) fails a CI-guarded scan — push-protection beyond `.gitignore` |
| req-tap-cares-secrets-size-guard | [Secret Size Guard](#secret-size-guard) | Implemented | 1 MiB default ceiling per secret file, raised per-file via `metadata.max_bytes` — guards the dumb/malicious-oversize case while allowing a deliberately large secret |
| req-tap-cares-secrets-future-secret-model | [Future Secret BaseModel](#future-secret-basemodel) | Backlog | Future on-grid Secret metadata and file generation |
| req-tap-cares-secrets-future-encryption | [Future Encryption At Rest](#future-encryption-at-rest) | Backlog | Encrypted file format explicitly deferred |

## Secrets Scope
----
RID: `req-tap-cares-secrets-scope`
Status: `Implemented`

tap-cares secrets are off-grid runtime material loaded from the local filesystem. The secret registry is an in-process runtime registry, not TAP-managed graph state.

Secret values must not be stored in:

- TAP-managed node fields
- TAP-managed edge properties
- GRIFT batches
- CollectionJob results
- scheduler configuration
- plugin manifests
- source-controlled fixtures

On-grid objects may later store non-secret references such as `aws:prod-readonly`, but those references are not secret material.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-scope-1 | Off-Grid Material | Implemented | Secret values live outside the TAP grid in mounted files. | |
| req-tap-cares-secrets-scope-2 | References Only | Implemented | On-grid objects may store secret references, but not secret values. | Future collector config/authenticator work. |
| req-tap-cares-secrets-scope-3 | No Direct File Reads | Implemented | Collectors and other consumers resolve secrets through tap-cares, not by reading secret files directly. | |

## Secret Files
----
RID: `req-tap-cares-secrets-files`
Status: `Implemented`

The runtime secret root is configured by deployment settings, with a Docker Compose secrets mount as the expected local/container mechanism.

At Django startup, tap-cares scans the configured secrets root recursively. Directories are non-semantic and exist only to help operators organize multiple sets of secrets. Only files whose basename matches:

```text
<key>.secret.json
```

are loaded. Non-matching files are ignored. Dotfiles are ignored.

The `*.secret.json` suffix is mandatory so secret files are visually obvious and can be ignored by source control. The repository-level `.gitignore` must ignore `*.secret.json`. Example or template files must use a non-matching suffix such as `.secret.example.json`.

The file declares its canonical identity. Directory names do not contribute to identity. The basename `<key>` must match the JSON object's `key` field so humans browsing the mounted folder see the same local key that tap-cares registers.

Duplicate `scope:key` values are configuration errors even when they appear in different directories. Like other per-file faults they are recorded, not crash-raised, per the resilient-load contract (`req-tap-cares-secrets-resilient-load`).

### Shared Resolver (Development)

The low-level mechanics of reading this store — discovering a `<key>.secret.json` by `scope`/`key` and validating the canonical envelope shape — live in the app-neutral `tap/runtime_secrets.py`, **not** in tap_cares. tap_cares is the *major* secrets manager: it owns the registry, the resilient-load report, the system check, the health probe, the basename/key match, and `required_for_boot` semantics, and it builds the rich `Secret` on top of the shared envelope. tap_auth resolves provider client credentials from the same store at settings-import time (before `tap_cares.ready()` runs) and so calls the shared resolver directly rather than importing tap_cares — keeping the two apps free of a cross-dependency. The resolver is import-safe (no Django settings access at import); each caller supplies the secrets root and re-wraps the resolver's neutral `RuntimeSecretError` in its own domain exception.

### Example Layout

```text
/run/tap-secrets/
  aws/prod-readonly.secret.json
  aws/dev-sandbox.secret.json
  github/fedramp-source.secret.json
```

### Multi-Session Host Convention

In the multi-session dev workflow (`specs/spec-dev-multisession.md`),
docker-compose.yml bind-mounts `./tap_secrets` (relative to each session's
worktree) into `/run/tap-secrets:ro`. `scripts/spawn-session.sh` provisions
that host path before `dc up` runs:

- If `$HOME/tap-secrets/` exists, the spawn script symlinks
  `<worktree>/tap_secrets -> $HOME/tap-secrets/` so a single host-side
  secrets directory feeds every session. `rm -rf` and `git worktree remove`
  do not follow the symlink, so despawn never touches the shared directory.
- Otherwise the spawn script creates an empty per-session directory; the
  loader no-ops cleanly and the operator can populate the session's
  `tap_secrets/` later. Despawn deletes any `*.secret.json` files it finds
  there — the despawn plan output flags this so a forgotten real secret is
  not silently nuked.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-files-1 | Recursive Discovery | Implemented | tap-cares recursively scans the configured secrets root at startup. | |
| req-tap-cares-secrets-files-2 | Secret Suffix | Implemented | Only `*.secret.json` files are loaded. | |
| req-tap-cares-secrets-files-3 | Git Ignore | Implemented | The repository ignores `*.secret.json`. | |
| req-tap-cares-secrets-files-4 | Directory Non-Semantic | Implemented | Directories help organization but do not define scope, key, or kind. | |
| req-tap-cares-secrets-files-5 | Basename Matches Key | Implemented | The filename's `<key>` portion must match the JSON object's `key` field. | |
| req-tap-cares-secrets-files-6 | Duplicate Guard | Implemented | Duplicate `scope:key` values are recorded as load failures (degraded unless `required_for_boot`), not crash-raised. | See `req-tap-cares-secrets-resilient-load`. |

## Resilient Load And Failure Surfacing
----
RID: `req-tap-cares-secrets-resilient-load`
Status: `Implemented`

Secret loading at Django startup is **resilient, not crash-fast**. A single
malformed, mis-keyed, invalid-token, or duplicate secret file must never abort
`django.setup()` and crash-loop the instance — doing so kills the very surfaces
(`manage.py`, `manage.py health`, a shell) an operator needs to diagnose and fix it.

Instead the loader registers every valid file and records each bad file as a
non-secret `SecretLoadFailure` (source path, redacted structural reason, the
`scope:key` when determinable, and the file's `required_for_boot` flag) in a
process-wide `secret_load_report`. Exactly one fault still raises: a `root`
that exists but is not a directory — a gross mount/deploy misconfiguration of
the root itself, not a per-file fault.

**One load, three readers.** The single report populated in
`TapCaresConfig.ready` is consumed by three independent surfaces, separating
*validation* (strict, at the gate) from *process startup* (resilient):

| Reader | Degraded failure | `required_for_boot` failure |
| --- | --- | --- |
| `tap_cares` system check (`manage.py check`, `runserver`, validation gate) | `Warning` `tap_cares.W001` | `Error` `tap_cares.E001` — fails the build |
| `tap_health` secrets probe (running instance; WSGI/ASGI runs no checks) | `degraded` | `unhealthy` |
| boot | proceeds | refuses |

The `required_for_boot` boolean (see Secret JSON Shape) is what escalates a
recorded failure from degrade to blocking. It is read from the file's
`metadata` — best-effort even from a malformed-but-parseable file, since a bad
file can still self-declare that its failure must block standup; only a literal
`true` escalates. A file too broken to parse at all degrades (it cannot be
proven required) and is still recorded loudly.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-resilient-load-1 | No Crash-Loop | Implemented | A per-file load fault is recorded in `secret_load_report`, never raised, so startup does not crash-loop. | Non-directory root is the sole still-raising case. |
| req-tap-cares-secrets-resilient-load-2 | Failure Record Shape | Implemented | Each failure carries source path, redacted reason, optional `scope:key`, and `required_for_boot`; no secret material. | |
| req-tap-cares-secrets-resilient-load-3 | Blocking Escalation | Implemented | A failure whose file declared `required_for_boot: true` is blocking; others degrade. | |
| req-tap-cares-secrets-resilient-load-4 | System Check Surface | Implemented | The `tap_cares` check emits `E001` for blocking failures and `W001` for degraded ones. | Fails `manage.py check` / the validation gate. |
| req-tap-cares-secrets-resilient-load-5 | Health Surface | Implemented | The `tap_health` secrets probe (via `run_health()` / `manage.py health`) reports `unhealthy` on a blocking failure and `degraded` otherwise. | Covers running instances where system checks do not run; the unauthenticated `/healthz` was parked (`req-tap-health-exposure-4`). |

## Secret JSON Shape
----
RID: `req-tap-cares-secrets-shape`
Status: `Implemented`

Each v0 secret file must contain one JSON object with these top-level fields:

| Field | Required | Description |
| --- | :---: | --- |
| `scope` | Yes | Scoped registry scope, e.g. `aws` |
| `key` | Yes | Local key within the scope, e.g. `prod-readonly` |
| `kind` | Yes | Consumer-defined secret kind, e.g. `aws_static_access_key` |
| `description` | Yes | Free-form operator note explaining what this secret is and why it exists |
| `data` | Yes | Secret material object consumed by capability-specific code |
| `metadata` | No | Non-secret operator metadata useful for diagnostics |

v0 tap-cares validates only the minimal structural shape needed for registration. It does not validate kind-specific schemas.

#### Reserved metadata: `required_for_boot`

`metadata.required_for_boot` is a reserved boolean (default `false`). It
declares the *consequence of this file failing to load*, not a property of the
secret — chosen as an explicit boolean rather than an opaque policy enum so its
full meaning is visible at the file. When `true`, a load failure for this file
is **blocking** (fails the build / 503s health); when absent or `false`, a
load failure merely **degrades** the instance. It governs the present-but-
malformed (and duplicate) case; an entirely absent secret is handled at run
time by `resolve_secret` (`req-tap-cares-secrets-redaction-3`). When present it
must be a boolean (a non-boolean is itself a structural load failure). See
`req-tap-cares-secrets-resilient-load`.

#### Reserved metadata: `max_bytes`

`metadata.max_bytes` is a reserved positive integer that **raises** this file's
size ceiling above the 1 MiB default (`req-tap-cares-secrets-size-guard`). It is
raise-only — it cannot lower the default — and a non-positive-integer value is a
structural load failure. Absent, the default applies.

### Example

```json
{
  "scope": "aws",
  "key": "prod-readonly",
  "kind": "aws_static_access_key",
  "description": "Read-only AWS credentials used by the TAP AWS inventory collector.",
  "data": {
    "access_key_id": "AKIA...",
    "secret_access_key": "...",
    "region": "us-east-1"
  },
  "metadata": {
    "account_id": "123456789012",
    "required_for_boot": false
  }
}
```

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-shape-1 | JSON Object | Implemented | A secret file contains exactly one JSON object. | |
| req-tap-cares-secrets-shape-2 | Declared Identity | Implemented | The object declares `scope` and `key`. | |
| req-tap-cares-secrets-shape-3 | Kind Declared | Implemented | The object declares a `kind` string for consumer-side validation. | |
| req-tap-cares-secrets-shape-4 | Description Required | Implemented | The object includes free-form `description` text explaining the secret. | |
| req-tap-cares-secrets-shape-5 | Data Object | Implemented | The object includes a `data` object containing the secret material. | |
| req-tap-cares-secrets-shape-6 | No Kind Schema In Core | Implemented | tap-cares v0 does not ship or enforce kind-specific schemas. | Consumers validate their own shapes. |
| req-tap-cares-secrets-shape-7 | Required-For-Boot Flag | Implemented | `metadata.required_for_boot`, when present, is a boolean declaring that a load failure for this file is blocking. | See `req-tap-cares-secrets-resilient-load`. |

## Secret Registry And Resolution
----
RID: `req-tap-cares-secrets-registry`
Status: `Implemented`

tap-cares exposes an internal `secret_registry` backed by TAP's existing `ScopedRegistry` pattern. The registry value is a rich runtime object, not a raw dictionary, so label/description/kind/source-path metadata travels with the secret while the generic registry stays unchanged.

Consumers should use typed helpers rather than raw strings:

```python
ref = SecretRef(scope="aws", key="prod-readonly")
secret = resolve_secret(ref)
```

`SecretRef` is the stable non-secret reference shape. `resolve_secret(...)` returns a runtime `Secret` object that exposes metadata and secret data to trusted runtime code. Direct access to `secret_registry` is reserved for the secrets subsystem and tests.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-registry-1 | Scoped Registry | Implemented | Secrets are loaded into a dedicated `ScopedRegistry`. | |
| req-tap-cares-secrets-registry-2 | Rich Runtime Object | Implemented | Registry values carry `SecretRef`, `kind`, `description`, `data`, optional metadata, and source path. | |
| req-tap-cares-secrets-registry-3 | SecretRef Helper | Implemented | Runtime code can pass `SecretRef` objects instead of raw `scope:key` strings. | |
| req-tap-cares-secrets-registry-4 | Resolver Helper | Implemented | `resolve_secret(ref)` is the public access path for secret consumers. | |

## Consumer Validation
----
RID: `req-tap-cares-secrets-validation`
Status: `Implemented`

Kind-specific validation belongs to the consumer that understands the external system. tap-cares v0 does not centralize secret schemas because plugins and collectors will define many different secret shapes.

A consumer that requires AWS static credentials must validate that a resolved secret has the expected `kind` and required `data` fields before using it. Invalid consumer-specific shape fails the run visibly.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-validation-1 | Core Minimal Validation | Implemented | tap-cares validates only registration-level shape. | |
| req-tap-cares-secrets-validation-2 | Consumer Owns Kind Validation | Implemented | Consumers validate `kind` and `data` requirements before use. | `require_secret_kind(...)` accepts a consumer-owned JSON Schema. |
| req-tap-cares-secrets-validation-3 | Visible Invalid Shape | Implemented | A malformed-for-consumer secret fails the capability run with a structured redacted error. | |

## Redaction And Failure Behavior
----
RID: `req-tap-cares-secrets-redaction`
Status: `Implemented`

Secrets must not leak through logs, exceptions, run records, debug payloads, or rendered UI. tap-cares should provide a recursive redaction helper for structured diagnostics. At minimum, keys containing sensitive words such as `secret`, `token`, `password`, `private_key`, or `credential` are redacted.

Missing secrets do not prevent TAP from starting and do not remove collector capability nodes. A run that requires a missing secret fails visibly with a structured, redacted error in the run record. A *malformed* secret behaves the same way for non-blocking files — it is recorded, the instance degrades, and a run that needs it fails at run time — extending this missing-secret philosophy to bad files rather than crash-looping startup (`req-tap-cares-secrets-resilient-load`).

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-redaction-1 | Redaction Helper | Implemented | tap-cares provides a helper to redact secret-shaped values from structured diagnostics. | |
| req-tap-cares-secrets-redaction-2 | No Secret Logs | Implemented | Secret material is never intentionally logged or persisted in run records. | Enforced by consumer discipline and redaction helpers. |
| req-tap-cares-secrets-redaction-3 | Missing Secret Run Failure | Implemented | Missing required secrets fail the run visibly rather than failing registration or startup. | `resolve_secret(...)` raises at runtime; consumers record failures. |

## Consumer-Defined Secret Kinds
----
RID: `req-tap-cares-secrets-consumer-kinds`
Status: `Implemented`

The secrets subsystem is kind-agnostic. `tap_cares` owns the *mechanics* —
`*.secret.json` discovery, the in-process registry, `SecretRef` /
`resolve_secret`, the `require_secret_kind` validation harness, redaction, and
string-keyed `kind` dispatch — and enumerates **no** kind-specific `data`
fields.

The *shape* of a given kind's `data` (its fields, which are required, and the
JSON Schema it validates against) is defined and owned by the consuming plugin
or collector spec. The consumer supplies that schema at its own boundary via
`require_secret_kind(secret, "<kind>", data_schema=<consumer schema>)`
(`req-tap-cares-secrets-validation`). Adding a new secret kind is therefore a
consumer-side spec + schema change, not an edit to this spec.

The reference example is the AWS static-credentials kind
(`aws_static_access_key`), owned by
`plugins/aws_core/specs/spec-aws-core-secrets.md`
(`req-aws-core-secret-aws-static`). It was previously enumerated here as
`req-tap-cares-secrets-aws-static`; that requirement and its ACIDs were
relocated to `aws_core` when this ownership boundary was made explicit, so the
generic subsystem carries no AWS-specific shape.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-consumer-kinds-1 | Subsystem Owns Mechanics | Implemented | File discovery, registry, resolution, `require_secret_kind`, redaction, and string `kind` dispatch are `tap_cares`-owned and kind-agnostic. | |
| req-tap-cares-secrets-consumer-kinds-2 | Consumer Owns Shape | Implemented | A kind's `data` fields and validation JSON Schema live in the consuming plugin/collector spec and are supplied to `require_secret_kind(..., data_schema=...)`; this spec enumerates none. | `data_schema` is a caller-supplied parameter, not a `tap_cares` constant. |
| req-tap-cares-secrets-consumer-kinds-3 | Reference Example | Implemented | `aws_static_access_key` is owned by `spec-aws-core-secrets.md` `req-aws-core-secret-aws-static`; this spec links it as the example, not the definition. | Relocated from `req-tap-cares-secrets-aws-static`. |

## Conditional Validation Lives In Health Probes
----
RID: `req-tap-cares-secrets-conditional-validation`
Status: `Implemented`

Whether a given secret is *needed* is not a static fact that can be written down once — it is a predicate over a consumer's configuration and grid state. The github collector pulling only public repos needs no token; the aws collector used only to ingest GRIFT files from another service, or to model a system on the design dimension, needs no credentials; an auth provider needs its `oidc_client` secret only when that provider is configured. A flat "expected secrets" list cannot express "required *if* …" without becoming a logic engine.

TAP already has that logic engine: the `tap_health` probe system (`spec-tap-health-v0.md`). So TAP does **not** maintain a static expected-secret declaration — no on-grid `SecretReference` table in v0 (that stays [Future Secret BaseModel](#future-secret-basemodel)), and no code-level required-secret list. **Conditional necessity is evaluated by the consuming app's own health probe**, reusing its existing self-test logic where it has one. The probe runs the consumer's own conditional check and validates presence + shape against the kind schema the consumer owns — which is also where the "validate known kinds earlier" goal is satisfied: a malformed *present* AWS or OIDC secret is reported at health time, before the consumer's next run, not as a mystery failure later.

**Division of labor (the boundary):**

- **`tap_cares` + `tap/runtime_secrets` (necessity-agnostic, generic):** file discovery, envelope load/format validation, and surfacing a *present-but-malformed* file — via the `secrets` health probe and the resilient-load system check (`req-tap-cares-secrets-resilient-load`). This layer never opines on whether a given secret is *needed*.
- **Per-consumer health probe (auth, each collector — owned by the consumer that knows its own config/state):** conditional necessity ("do I even need a key, given how I'm configured?") + presence + kind-shape. Reuses the consumer's offline self-test as the single source of truth so boot-time and runtime checks cannot drift.

`required_for_boot` (`req-tap-cares-secrets-shape-7`) stays **narrow** and must not be conflated with this: it means "if this file is *present* and fails to load, that failure is blocking." It does **not** mean "this file must exist." Conditional must-exist is the probe's job.

The auth providers health probe (`spec-tap-auth-v0.md` `req-tap-auth-providers`) is the worked reference; collectors mirror it through the `CollectorBase` offline self-test.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-conditional-validation-1 | Necessity Is Conditional | Implemented | Whether a secret is needed is a per-consumer predicate over config/state, not a static declaration; TAP keeps no static expected-secret list and no on-grid `SecretReference` in v0. | |
| req-tap-cares-secrets-conditional-validation-2 | Probe Ownership | Implemented | The consuming app's health probe evaluates conditional necessity + presence + kind-shape, reusing its offline self-test as the single source of truth. | Auth is the reference; collectors mirror via `CollectorBase`. |
| req-tap-cares-secrets-conditional-validation-3 | Generic Layer Stays Necessity-Agnostic | Implemented | `tap_cares`/`tap.runtime_secrets` own only discovery + format + present-but-malformed surfacing; they never opine on necessity. | |
| req-tap-cares-secrets-conditional-validation-4 | required_for_boot Stays Narrow | Implemented | `required_for_boot` means "a present-but-broken file blocks boot," never "this file must exist." | Prevents conflation with conditional presence. |

## Rotation Semantics
----
RID: `req-tap-cares-secrets-rotation`
Status: `Implemented`

**v0 contract: restart to rotate.** Secrets are read exactly **once per process, at startup** — `tap_cares` loads the mount into `secret_registry` in `ready()`, and `tap_auth` resolves provider secrets even earlier, at settings-import. A change to a secret file on disk therefore has **no effect on a running process**. To rotate a secret: replace the file on the mount, then restart the process (container).

This is acceptable for v0 and is written down deliberately rather than left implicit. It matches TAP's broader restart-to-reload posture (no external cache; code changes already require a restart) and the rotation cadence of dev and early single-tenant deployments is low enough that a restart is cheap. Prior art points the other way for later: Kubernetes mounted-secret volumes update *eventually*; AWS/Vault emphasize caching, TTLs, leases, rotation, and revocation. TAP does none of that yet, by choice.

**Named-deferred (the risks left open, deliberately):**

- **Atomic in-process reload** — re-read the mount into the registry without a restart.
- **Staleness detection** — source `mtime` / content digest so the instance can know its in-memory value has diverged from disk.
- **Health surfacing** — a probe reporting a loaded secret as `stale` (differs from disk) or `rotation_due`. (The `rotation_due` notion is coupled to rotation existing; it is *not* built ahead of it.)
- **Vault-style lifecycle** — TTL / lease / revocation and short-lived credential exchange (relates to the short-lived-credentials backlog and [Future Secret BaseModel](#future-secret-basemodel)).

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-rotation-1 | Restart To Rotate | Implemented | Secrets load once at process startup; rotating a secret requires replacing the file and restarting the process. | The documented v0 contract. |
| req-tap-cares-secrets-rotation-2 | No Hot Reload | Implemented | A change to a secret file does not affect a running process; there is no in-process reload in v0. | Stated as an explicit limitation, not a gap. |
| req-tap-cares-secrets-rotation-3 | Staleness Detection | Proposed | Detect that an in-memory secret has diverged from disk (mtime/digest). | Backlog |
| req-tap-cares-secrets-rotation-4 | Rotation Health Surface | Proposed | A health probe surfaces `stale` / `rotation_due`. | Backlog; gated on rotation existing. |
| req-tap-cares-secrets-rotation-5 | Atomic Reload / Lifecycle | Proposed | In-process atomic reload and vault-style TTL/lease/revocation. | Backlog |

## Source-Control Leak Guard
----
RID: `req-tap-cares-secrets-leak-guard`
Status: `Implemented`

The repository `.gitignore` ignores `*.secret.json` (`req-tap-cares-secrets-files-3`), but an ignore rule is bypassable (`git add -f`) and does nothing about a real secret renamed to dodge the suffix. The leak guard is **push-protection beyond ignore**, modeled on GitHub secret-scanning / push-protection: a scan that refuses to let a secret enter version control in the first place. It keeps secret *values* out of source control, the same way `req-tap-cares-secrets-scope` keeps them off the grid.

The scan is a CI-guarded `pytest` surface, mirroring the log-site-token and JSON-filename scanners (`tap.runtime_secrets` hosts the scan logic; `tap/tests/` is the enforcement). It is a **filesystem walk** (no git dependency, so it runs in-container like the sibling scanners) over the repository tree's `*.json` files, **excluding** vendored/cache dirs and the live secrets mount (`tap_secrets` — a gitignored symlink to the off-grid store). It fails on:

1. **Any `*.secret.json` file** — a secret file in the tree. High-signal, zero false positives.
2. **Any `*.json` file whose content is envelope-shaped** — a top-level object carrying the full canonical secret envelope (`scope` + `key` + `kind` + `data`) — outside allowed locations. Allowed: test fixtures/scaffolding and explicit `*.secret.example.json` templates. This catches a real secret renamed to evade the `.secret.json` suffix.

A hit is therefore either a committed leak or a stray real secret a developer dropped in the tree outside the mount — both must be removed (and the credential rotated). This surface is registered in the Validation Map (`spec-dev-validation.md`). Guard status today: CI-guarded (`pytest`); a pre-commit hook and the promote/push gate are the natural future homes.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-leak-guard-1 | No Secret Files In The Tree | Implemented | A `*.secret.json` file anywhere in the scanned tree fails the scan. | Push-protection beyond `.gitignore`. |
| req-tap-cares-secrets-leak-guard-2 | No Disguised Secrets | Implemented | A file whose content is the canonical secret envelope fails, outside test fixtures and `*.secret.example.json` templates. | Catches suffix-evasion. |
| req-tap-cares-secrets-leak-guard-3 | Mount + Vendored Dirs Excluded | Implemented | The walk excludes the live secrets mount (`tap_secrets`) and vendored/cache dirs, so the legitimate off-grid store is never flagged. | |
| req-tap-cares-secrets-leak-guard-4 | Map-Registered Surface | Implemented | The guard has a row in the `spec-dev-validation.md` Validation Map. | Co-change discipline. |

## Secret Size Guard
----
RID: `req-tap-cares-secrets-size-guard`
Status: `Implemented`

A single secret file is size-checked before it is trusted: `tap/runtime_secrets` rejects a file larger than **1 MiB** (`DEFAULT_SECRET_MAX_BYTES`) unless the file **raises its own ceiling** with an optional `metadata.max_bytes` field (a positive integer). The effective limit is the larger of the default and the declared value, so the field is **raise-only** — it cannot lower the default or reject a sub-default file. A consumer that legitimately needs a large secret (a future collector consuming a deliberately big credential blob) opts in by declaring `metadata.max_bytes` on that secret file; everything else is guarded at 1 MiB against an accidental or malicious oversize file (a misnamed log, a runaway write, a bad paste).

The override lives in the secret file's `metadata` (it travels with the secret and the loader reads it anyway), so the guard is uniform across both load paths with no per-caller wiring:

- `load_secret_envelope` — the **bulk-load path** the tap_cares loader uses for every discovered secret — honors the per-file `metadata.max_bytes` override.
- `find_secret_file` — tap_auth's small-reference-secret discovery path — applies the fixed 1 MiB cap to each candidate *before* reading it, so discovery cannot slurp an oversized file; the file it returns is already within the cap.

**Threat model (named, honest).** The secrets mount is operator-controlled, so this guard targets the *dumb/accidental* oversize case, not a hostile actor who already controls the mount (such an actor would simply supply malicious credential *values*). It is not a hard DoS defense: on the override path a file over the default is read once before its declared ceiling is checked. A **pre-read absolute ceiling** that fails truly pathological files (multi-GB) before any read is the general `req-tap-json-size-guard` on `load_json_file`, deferred there.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-size-guard-1 | Default Ceiling | Implemented | A secret file larger than 1 MiB is rejected with a `RuntimeSecretError`. | `DEFAULT_SECRET_MAX_BYTES`. |
| req-tap-cares-secrets-size-guard-2 | Per-File Override | Implemented | `metadata.max_bytes` (a positive integer) raises the ceiling for that file; the effective limit is `max(default, declared)`. | Raise-only; enables deliberately large secrets. |
| req-tap-cares-secrets-size-guard-3 | Malformed Override Rejected | Implemented | A `metadata.max_bytes` that is not a positive integer fails envelope parsing. | |
| req-tap-cares-secrets-size-guard-4 | Uniform Across Paths | Implemented | The override is honored on the bulk-load path; the discovery path applies the fixed default before reading each candidate. | |
| req-tap-cares-secrets-size-guard-5 | Hostile-Mount Ceiling Deferred | Proposed | A pre-read absolute ceiling that fails pathological files before any read. | Folds into `req-tap-json-size-guard`. |

## Future Secret BaseModel
----
RID: `req-tap-cares-secrets-future-secret-model`
Status: `Backlog`

A future TAP-managed `Secret` or `SecretReference` BaseModel may make secrets grid-accessible without placing secret values on the grid. This model would exercise the dual-existence pattern: an on-grid node for metadata, policy, references, health, usage edges, and schema intent; an off-grid registry/file entry for the actual secret material.

The future model is also a likely place to define or reference a schema for a secret kind. A management command could use that schema and on-grid metadata to generate a starter `<key>.secret.json` file for an operator to fill in outside source control.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-future-secret-model-1 | Backlog Requirement Exists | Backlog | On-grid secret metadata is tracked as a named future requirement. | |
| req-tap-cares-secrets-future-secret-model-2 | Values Stay Off-Grid | Backlog | Any future Secret BaseModel stores references and metadata, not secret values. | |
| req-tap-cares-secrets-future-secret-model-3 | Schema Home Candidate | Backlog | A future Secret BaseModel may define or reference a schema used to generate secret files. | |
| req-tap-cares-secrets-future-secret-model-4 | Generator Command Candidate | Backlog | A future management command may generate starter `<key>.secret.json` files from Secret metadata/schema. | |

## Future Encryption At Rest
----
RID: `req-tap-cares-secrets-future-encryption`
Status: `Backlog`

Encryption at rest for mounted secret files is explicitly deferred. v0 does not define the encrypted file format, key derivation, envelope shape, cipher choice, or reload behavior.

Future encryption work should preserve the v0 runtime contract: after successful decryption, tap-cares receives the same logical secret object shape described in [Secret JSON Shape](#secret-json-shape).

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-future-encryption-1 | Backlog Requirement Exists | Backlog | File encryption is tracked without committing to a format in v0. | |
| req-tap-cares-secrets-future-encryption-2 | Runtime Shape Preserved | Backlog | Future decryption yields the v0 logical secret object shape before registration. | |
