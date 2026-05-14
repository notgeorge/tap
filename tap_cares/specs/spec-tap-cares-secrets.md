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
| req-tap-cares-secrets-scope | [Secrets Scope](#secrets-scope) | Proposed | Secret material is off-grid runtime data |
| req-tap-cares-secrets-files | [Secret Files](#secret-files) | Proposed | Recursive `*.secret.json` discovery under a configured secrets root |
| req-tap-cares-secrets-shape | [Secret JSON Shape](#secret-json-shape) | Proposed | Minimal required JSON object fields |
| req-tap-cares-secrets-registry | [Secret Registry And Resolution](#secret-registry-and-resolution) | Proposed | Internal `ScopedRegistry` plus `SecretRef` / `resolve_secret` helpers |
| req-tap-cares-secrets-validation | [Consumer Validation](#consumer-validation) | Proposed | Consumers validate kind-specific secret data |
| req-tap-cares-secrets-redaction | [Redaction And Failure Behavior](#redaction-and-failure-behavior) | Proposed | Secret material must not leak into logs or run records |
| req-tap-cares-secrets-aws-static | [AWS Static Credentials](#aws-static-credentials) | Proposed | First concrete consumer shape for AWS collection |
| req-tap-cares-secrets-future-secret-model | [Future Secret BaseModel](#future-secret-basemodel) | Backlog | Future on-grid Secret metadata and file generation |
| req-tap-cares-secrets-future-encryption | [Future Encryption At Rest](#future-encryption-at-rest) | Backlog | Encrypted file format explicitly deferred |

## Secrets Scope
----
RID: `req-tap-cares-secrets-scope`
Status: `Proposed`

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
| req-tap-cares-secrets-scope-1 | Off-Grid Material | Proposed | Secret values live outside the TAP grid in mounted files. | |
| req-tap-cares-secrets-scope-2 | References Only | Proposed | On-grid objects may store secret references, but not secret values. | Future collector config/authenticator work. |
| req-tap-cares-secrets-scope-3 | No Direct File Reads | Proposed | Collectors and other consumers resolve secrets through tap-cares, not by reading secret files directly. | |

## Secret Files
----
RID: `req-tap-cares-secrets-files`
Status: `Proposed`

The runtime secret root is configured by deployment settings, with a Docker Compose secrets mount as the expected local/container mechanism.

At Django startup, tap-cares scans the configured secrets root recursively. Directories are non-semantic and exist only to help operators organize multiple sets of secrets. Only files whose basename matches:

```text
<key>.secret.json
```

are loaded. Non-matching files are ignored. Dotfiles are ignored.

The `*.secret.json` suffix is mandatory so secret files are visually obvious and can be ignored by source control. The repository-level `.gitignore` must ignore `*.secret.json`. Example or template files must use a non-matching suffix such as `.secret.example.json`.

The file declares its canonical identity. Directory names do not contribute to identity. The basename `<key>` must match the JSON object's `key` field so humans browsing the mounted folder see the same local key that tap-cares registers.

Duplicate `scope:key` values are configuration errors even when they appear in different directories.

### Example Layout

```text
/run/tap-secrets/
  aws/prod-readonly.secret.json
  aws/dev-sandbox.secret.json
  github/fedramp-source.secret.json
```

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-files-1 | Recursive Discovery | Proposed | tap-cares recursively scans the configured secrets root at startup. | |
| req-tap-cares-secrets-files-2 | Secret Suffix | Proposed | Only `*.secret.json` files are loaded. | |
| req-tap-cares-secrets-files-3 | Git Ignore | Proposed | The repository ignores `*.secret.json`. | |
| req-tap-cares-secrets-files-4 | Directory Non-Semantic | Proposed | Directories help organization but do not define scope, key, or kind. | |
| req-tap-cares-secrets-files-5 | Basename Matches Key | Proposed | The filename's `<key>` portion must match the JSON object's `key` field. | |
| req-tap-cares-secrets-files-6 | Duplicate Guard | Proposed | Duplicate `scope:key` values fail startup secret loading. | |

## Secret JSON Shape
----
RID: `req-tap-cares-secrets-shape`
Status: `Proposed`

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
    "account_id": "123456789012"
  }
}
```

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-shape-1 | JSON Object | Proposed | A secret file contains exactly one JSON object. | |
| req-tap-cares-secrets-shape-2 | Declared Identity | Proposed | The object declares `scope` and `key`. | |
| req-tap-cares-secrets-shape-3 | Kind Declared | Proposed | The object declares a `kind` string for consumer-side validation. | |
| req-tap-cares-secrets-shape-4 | Description Required | Proposed | The object includes free-form `description` text explaining the secret. | |
| req-tap-cares-secrets-shape-5 | Data Object | Proposed | The object includes a `data` object containing the secret material. | |
| req-tap-cares-secrets-shape-6 | No Kind Schema In Core | Proposed | tap-cares v0 does not ship or enforce kind-specific schemas. | Consumers validate their own shapes. |

## Secret Registry And Resolution
----
RID: `req-tap-cares-secrets-registry`
Status: `Proposed`

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
| req-tap-cares-secrets-registry-1 | Scoped Registry | Proposed | Secrets are loaded into a dedicated `ScopedRegistry`. | |
| req-tap-cares-secrets-registry-2 | Rich Runtime Object | Proposed | Registry values carry `SecretRef`, `kind`, `description`, `data`, optional metadata, and source path. | |
| req-tap-cares-secrets-registry-3 | SecretRef Helper | Proposed | Runtime code can pass `SecretRef` objects instead of raw `scope:key` strings. | |
| req-tap-cares-secrets-registry-4 | Resolver Helper | Proposed | `resolve_secret(ref)` is the public access path for secret consumers. | |

## Consumer Validation
----
RID: `req-tap-cares-secrets-validation`
Status: `Proposed`

Kind-specific validation belongs to the consumer that understands the external system. tap-cares v0 does not centralize secret schemas because plugins and collectors will define many different secret shapes.

A consumer that requires AWS static credentials must validate that a resolved secret has the expected `kind` and required `data` fields before using it. Invalid consumer-specific shape fails the run visibly.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-validation-1 | Core Minimal Validation | Proposed | tap-cares validates only registration-level shape. | |
| req-tap-cares-secrets-validation-2 | Consumer Owns Kind Validation | Proposed | Consumers validate `kind` and `data` requirements before use. | |
| req-tap-cares-secrets-validation-3 | Visible Invalid Shape | Proposed | A malformed-for-consumer secret fails the capability run with a structured redacted error. | |

## Redaction And Failure Behavior
----
RID: `req-tap-cares-secrets-redaction`
Status: `Proposed`

Secrets must not leak through logs, exceptions, run records, debug payloads, or rendered UI. tap-cares should provide a recursive redaction helper for structured diagnostics. At minimum, keys containing sensitive words such as `secret`, `token`, `password`, `private_key`, or `credential` are redacted.

Missing secrets do not prevent TAP from starting and do not remove collector capability nodes. A run that requires a missing secret fails visibly with a structured, redacted error in the run record.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-redaction-1 | Redaction Helper | Proposed | tap-cares provides a helper to redact secret-shaped values from structured diagnostics. | |
| req-tap-cares-secrets-redaction-2 | No Secret Logs | Proposed | Secret material is never intentionally logged or persisted in run records. | |
| req-tap-cares-secrets-redaction-3 | Missing Secret Run Failure | Proposed | Missing required secrets fail the run visibly rather than failing registration or startup. | |

## AWS Static Credentials
----
RID: `req-tap-cares-secrets-aws-static`
Status: `Proposed`

The first concrete secret consumer is expected to be an AWS collector that uses static AWS access keys.

The initial AWS collector should support a secret with:

- `kind`: `aws_static_access_key`
- `data.access_key_id`
- `data.secret_access_key`
- optional `data.session_token`
- optional `data.region`

Assume-role and other AWS credential modes are backlog for the AWS collector family, not tap-cares secrets v0.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-secrets-aws-static-1 | Static Key First | Proposed | The first AWS collector secret mode is static access key credentials. | |
| req-tap-cares-secrets-aws-static-2 | Consumer Validation | Proposed | The AWS collector validates required AWS fields before use. | |
| req-tap-cares-secrets-aws-static-3 | Assume Role Deferred | Backlog | AWS assume-role support is deferred until the collector needs it. | |

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
