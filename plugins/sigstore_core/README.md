# TAP Sigstore Core

Library plugin that owns Sigstore-ecosystem models and the canonical TAP-side
helpers for verifying Sigstore signature bundles and decomposing them into
graph data.

**No collector. No panel. No page.** v0 is a library plugin: other plugins'
collectors (samsite's compliance collector first) fetch signed artifacts +
their sibling `.bundle` files through their own collection paths and call
into `sigstore_core` to verify and decompose.

## What this plugin owns

- Models — `rekor_log_entry`, `sigstore_ca`
- Edge types — `ATTESTED_BY`, `CERT_ISSUED_BY`, `SIGNED_BY_IDENTITY`
- Python API:
  - `sigstore_core.verify.verify_bundle(body, bundle, *, policy)` — canonical Sigstore-bundle verifier
  - `sigstore_core.decompose.bundle_to_grift_fragment(...)` — turn a verified bundle into a GRIFT fragment callers merge into their own batch

The `sigstore` Python library is plugin-owned (declared in
`plugins/sigstore_core/pyproject.toml` via the root uv workspace, mirroring
`github_core`'s `PyYAML` pattern). Consumers MUST import only from
`sigstore_core.*`, never from `sigstore.*` directly.

## What this plugin does NOT own

- Live Rekor pulling (`rekor.sigstore.dev` queries) — v1 candidate
- An `oidc_issuer` node or `IDENTITY_VOUCHED_BY` edge — near-soon follow-up
- `rekor_log_checkpoint` nodes — v1
- intoto / DSSE attestation statement modeling — future
- Signing anything — TAP only verifies and decomposes
- A `sigstore_verification` observation node — v1 candidate when multi-policy / re-verification history becomes load-bearing

Full non-goal list lives in the spec.

## Trust chain on the grid

After consumer collectors call into `bundle_to_grift_fragment`, the demo
story walks:

```
signed_entity --[ATTESTED_BY]--> rekor_log_entry --[CERT_ISSUED_BY]--> sigstore_ca
                                       |
                                       +--[SIGNED_BY_IDENTITY]--> github_workflow
                                          (caller-supplied entity id)
```

`SIGNED_BY_IDENTITY` is caller-supplied — the decompose helper does no
cross-plugin graph reads. Consumers parse the bundle's SAN URI to extract
`(full_name, path)` and resolve to a `github_workflow` node via their own
search/Gryphon read before calling.

## Verification verdict lives on the edge

The `rekor_log_entry` node stores only immutable transparency-log facts
(`log_key_id`, `log_index`, `integrated_time`, etc.). The verification
verdict — `signature_verified`, the policy that produced it, the applied
predicates, the failure code and detail — lives as **attributes on the
`ATTESTED_BY` edge**. This is intentional: verification is a fact about
`(artifact bytes + bundle + policy + verification time)`, not an immutable
property of the Rekor entry.

## Important specs to read

- `plugins/sigstore_core/specs/spec-sigstore-core-v0.md` — canonical spec
- `tap_plugins/specs/spec-plugin-architecture.md` — plugin package conventions
- `tap_grid/specs/spec-grift-v0.md` — GRIFT interchange (consumed via fragments returned by decompose)

## Install and validate

Until `sigstore_core` is in `INSTALLED_APPS`, only structure-level validation
is meaningful:

```
python -m tap_plugins.validate_plugin plugins/sigstore_core
```

Once integrated, the full validation surface (`loads` + `runs`) becomes
useful.

## Status

v0 live. Plugin shape, manifest, models, edges, and icons are in place;
`verify_bundle` and `bundle_to_grift_fragment` are fully implemented (not
stubs). The plugin is installed (`INSTALLED_APPS`), migrated, and consumed
in production by samsite's `compliance_collector`, which fetches signed
`/.well-known/` artifacts, calls `verify_bundle`, and merges the
`bundle_to_grift_fragment` output into its batch — so `rekor_log_entry` /
`sigstore_ca` nodes and the trust-chain edges are live on the grid. `sigstore`
is plugin-owned via the uv workspace (`members` entry; removed from the root
`pyproject.toml`).

Deferred to the live-integration harness: happy-path / log-metadata
verification against a real bundle (`req-sigstore-core-testing-backlog`); v0
ships hermetic unit tests only.
