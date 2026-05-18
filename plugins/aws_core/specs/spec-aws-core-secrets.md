# AWS Core Secrets Specification (v0)

## Philosophy

The `tap_cares` secrets subsystem owns the *mechanics* of secret handling —
file discovery, the in-process registry, `resolve_secret`, the
`require_secret_kind` validation harness, redaction, and string-keyed kind
dispatch — and is deliberately kind-agnostic
(`tap_cares` `req-tap-cares-secrets-consumer-kinds`).

The *shape* of a given secret kind's `data` — which fields exist, which are
required, and the JSON Schema it validates against — is owned by the consuming
plugin or collector, not by `tap_cares`. This spec is the canonical owner of
the AWS credential kind(s) consumed by `aws_core` collectors. It is the first
concrete instance of the consumer-owned-shape contract.

`aws_core` supplies its schema to the subsystem at the consumer boundary via
`require_secret_kind(secret, "aws_static_access_key", data_schema=<aws_core schema>)`;
`tap_cares` enumerates none of these fields.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-aws-core-secret-aws-static | [AWS Static Access Key Kind](#aws-static-access-key-kind) | Approved for Development | `aws_static_access_key` `data` shape + region scope; relocated from `req-tap-cares-secrets-aws-static` |

## AWS Static Access Key Kind
----
RID: `req-aws-core-secret-aws-static`
Status: `Approved for Development`

The first AWS collector credential mode is static AWS access keys. The
`aws_static_access_key` secret kind carries:

- `kind`: `aws_static_access_key`
- `data.access_key_id` — required
- `data.secret_access_key` — required
- optional `data.session_token`
- optional `data.region` — single default/fallback region
- optional `data.regions_allowed` — list of regions to scope the sweep to

`data.region` / `data.regions_allowed` are the operator's region-scoping knob.
Region scope is operationally bound to the credential set (a key is intended
for the regions it should touch), so it travels in `data` next to the
credentials rather than in descriptive `metadata`. The plural list is named
`regions_allowed` (not bare `regions`) so it is never confused with the
singular `data.region` or the superseded steampipe `metadata.target_regions`
interim shape.

Region-scope *semantics* are specified by the consuming collector in
`spec-aws-core-collector-v0.md` (`req-aws-collector-credentials` /
`req-aws-collector-regions`): a non-empty `data.regions_allowed` scopes
regional collection to exactly those regions; absent, the singular
`data.region` is the sole swept region; with neither, the collector fails the
run visibly. Global
services are collected once regardless.

`aws_core` owns the JSON Schema for this `data` shape and applies it
consumer-side via `require_secret_kind(..., data_schema=...)`
(`tap_cares` `req-tap-cares-secrets-validation`). A missing or malformed
secret fails the run visibly with a structured, redacted error
(`tap_cares` `req-tap-cares-secrets-redaction-3`); secret material is never
logged and the collector capability is never disabled by a bad secret.

Assume-role and other AWS credential modes are backlog for the AWS collector
family — deferred until a collector needs them.

#### Lineage

This requirement was relocated from `tap_cares` `req-tap-cares-secrets-aws-static`
(and its ACIDs `-1`..`-4`) when the subsystem/shape ownership boundary was
made explicit: the AWS credential *shape* belongs to `aws_core`, not the
generic secrets subsystem. The `tap_cares` requirement is now the generic
`req-tap-cares-secrets-consumer-kinds`, which links here as its reference
example.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-secret-aws-static-1 | Static Key First | Approved for Development | The first AWS collector credential mode is static access keys (`access_key_id` + `secret_access_key`, optional `session_token`). | Was `req-tap-cares-secrets-aws-static-1`. |
| req-aws-core-secret-aws-static-2 | aws_core Owns The Schema | Approved for Development | `aws_core` defines the `data` JSON Schema and validates consumer-side via `require_secret_kind(..., data_schema=...)`. | Was `req-tap-cares-secrets-aws-static-2`; built in the source-driver increment. |
| req-aws-core-secret-aws-static-3 | Assume Role Deferred | Backlog | AWS assume-role support is deferred until a collector needs it. | Was `req-tap-cares-secrets-aws-static-3`. |
| req-aws-core-secret-aws-static-4 | Region Scope Carried | Approved for Development | The kind carries optional `data.region` (single) and `data.regions_allowed` (list); region-scope semantics are owned by the collector spec. | Was `req-tap-cares-secrets-aws-static-4`. |
