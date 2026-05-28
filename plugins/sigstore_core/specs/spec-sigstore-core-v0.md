# Sigstore Core Plugin Specification

## Plugin Identity

- **Slug:** `sigstore_core`
- **Display name:** TAP Sigstore Core
- **Description:** Library plugin that owns Sigstore-ecosystem models, edges, and the canonical TAP-side helpers for verifying Sigstore signature bundles and decomposing them into graph data.
- **Shape:** Library plugin. v0 registers no collector, no panel, and no page.
- **Public Python API:**
  - `sigstore_core.verify.verify_bundle(body, bundle, *, policy)` — verifies a Sigstore bundle; returns a `VerificationResult`. See `req-sigstore-core-verify`.
  - `sigstore_core.decompose.bundle_to_grift_fragment(result, *, anchor_entity_id, policy, dimensions, signing_identity_entity_id=None)` — turns a verified bundle into a `GriftFragment` callers merge into their own GRIFT batch. See `req-sigstore-core-decompose`.
- **Models** (see `req-sigstore-core-models`): `rekor_log_entry`, `sigstore_ca`.
- **Edge types** (see `req-sigstore-core-edges`): `ATTESTED_BY`, `CERT_ISSUED_BY`, `SIGNED_BY_IDENTITY`.
- **Default dimensions** (see `req-sigstore-core-dimensions`):
  - `sigstore.platform = "public-good"` on every `sigstore_core`-owned node and edge.
  - `sigstore.ca_kind = "fulcio"` on `sigstore_ca` nodes.
  - `sigstore.log_kind = "rekor"` on `rekor_log_entry` nodes.

## Philosophy

`sigstore_core` makes demo-visible Sigstore verification evidence navigable on
the TAP grid as graph data, and owns the canonical Python helpers other
plugins call to verify Sigstore signature bundles and decompose them into
nodes and edges. The plugin is deliberately narrower than "full Sigstore
root-of-trust modeling" — v0 captures the public-good Rekor-backed bundle
shape that current TAP consumers actually emit, and explicitly defers
adjacent shapes (RFC3161 timestamp-only bundles, witness consensus,
multi-policy re-verification, etc.).

It is a **library plugin**. v0 does not register a `tap_cares` collector.
Consumer plugins fetch signed artifacts through their own collection paths and
call into `sigstore_core` to (a) verify the bundle and (b) turn the verified
bundle into GRIFT fragments that slot into the consumer's own batch.

The shape exists because Sigstore concepts — Rekor log entries, the Fulcio CA,
the trust chain that ties a signed artifact to a signing identity — are
ecosystem concepts. They deserve their own home so any consumer that ingests
cosign-signed evidence (GitHub Actions attestations, container-image
signatures, signed compliance artifacts, etc.) can reuse the models, edges,
and verification helpers without re-inventing them.

## Roadmap Alignment

Governing step: `step-rampart-sam-demo` in `plan/road-rampart.md`.

This work directly supports the active Done-Test by making the trust chain
behind signed evidence navigable in the graph. After this plugin lands and
the relevant consumer collector is migrated to use it, the demo story becomes:
click a signed artifact entity -> walk one hop to the Rekor log entry that
recorded its signature -> walk one more hop to the Sigstore CA that issued the
signing cert and to the workflow identity that signed it.

## Prior Art

`sigstore-python` is the upstream verification library. An equivalent helper
already exists inside a consumer plugin and is the proof-of-shape for the v0
public API; this plugin lifts that helper to `sigstore_core.verify`
essentially unchanged, and adds a sibling `sigstore_core.decompose` module
that turns a verified bundle into a GRIFT fragment. The plugin does not
re-implement Sigstore primitives; it wraps them. Consumer-side migration
steps (removing the inline verify module, switching imports) live in each
affected consumer plugin's own spec, not here.

Cartography, CloudQuery, Steampipe, and ScoutSuite do not model Sigstore or
Rekor as graph data. The closest prior art is `cosign`'s own command surface
(`cosign verify`, `cosign tree`) and the structure of the Sigstore bundle
format itself, which the plugin treats as input. There is no broader OSS
template to borrow from here.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Trust-Chain-Visible | Rekor entries and the Sigstore CA become first-class graph nodes; the chain from a signed artifact through Rekor and the CA to the signing workflow identity is walkable. |
| 2. | Library Plugin | v0 ships no collector. The plugin's public surface is Python helpers consumer collectors call. |
| 3. | Single Verify Surface | One canonical `verify_bundle` helper that every TAP plugin uses to verify a Sigstore bundle. |
| 4. | Bundle-Decompose Helper | One canonical helper that turns a verified bundle into a GRIFT fragment consumers merge into their batch. |
| 5. | Plugin-Owned Dep | The `sigstore` Python library is declared in `plugins/sigstore_core/pyproject.toml` via the root uv workspace pattern, following the precedent github_core landed for `PyYAML` (first proof of `req-plugin-arch-python-deps`). Consumers import only from `sigstore_core.*`. |
| 6. | Polymorphic Anchor | The "signed entity" side of `ATTESTED_BY` is intentionally polymorphic; the plugin does not constrain which entity types may anchor a Rekor entry. |
| 7. | Rekor-Backed Bundles Only | v0 supports Sigstore bundles whose verification rests on a Rekor transparency-log inclusion proof. Timestamp-only bundles (RFC3161) and non-Rekor transparency networks are explicitly deferred. |
| 8. | Verdict Lives On The Edge | Verification is a fact about (artifact bytes + bundle + policy + verification time), not an immutable property of the Rekor entry. The verdict and the policy that produced it live on the `ATTESTED_BY` edge; the Rekor entry node stores only immutable transparency-log facts. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-sigstore-core-scope | [Plugin Scope](#plugin-scope) | Implemented | Library plugin; models + edges + verify/decompose helpers — scaffolded, structural validation green |
| req-sigstore-core-models | [Model Set](#model-set) | Implemented | `rekor_log_entry`, `sigstore_ca` |
| req-sigstore-core-edges | [Edge Vocabulary](#edge-vocabulary) | Implemented | `ATTESTED_BY`, `CERT_ISSUED_BY`, `SIGNED_BY_IDENTITY` |
| req-sigstore-core-no-collector | [No Collector In v0](#no-collector-in-v0) | Implemented | `apps.py` is `pass`; no `tap_cares` registration |
| req-sigstore-core-verify | [Verify Helper](#verify-helper) | Implemented | `sigstore_core.verify.verify_bundle(...)` exists with documented signature, three-state result, failure codes, and Rekor-only enforcement. Consumer migration (samsite) is `-8`, still Proposed. |
| req-sigstore-core-decompose | [Decompose Helper](#decompose-helper) | Implemented | `sigstore_core.decompose.bundle_to_grift_fragment(...)` exists; returns `GriftFragment` with the documented 4-or-5 pieces |
| req-sigstore-core-policy | [Verification Policy Shape](#verification-policy-shape) | Implemented | `GitHubWorkflowPolicy` dataclass + translation to `sigstore-python` policy live in `verify.py` |
| req-sigstore-core-dimensions | [Dimension Strategy](#dimension-strategy) | Implemented | `sigstore.platform`, `sigstore.ca_kind`, `sigstore.log_kind` set on model defaults and edge defaults |
| req-sigstore-core-python-deps | [Plugin Python Dependency](#plugin-python-dependency) | Proposed | `plugins/sigstore_core/pyproject.toml` declared; root-pyproject cleanup + uv-workspace member registration gated on this branch merging with the github_core workspace setup on main |
| req-sigstore-core-disclosure | [Verification Disclosure](#verification-disclosure) | Implemented | Verdict + failure code/detail + applied policy live as `ATTESTED_BY` edge attributes per the spec |
| req-sigstore-core-testing-backlog | [Live-Bundle Verification Testing (Backlog)](#live-bundle-verification-testing-backlog) | Backlog | v0 ships hermetic unit tests only; happy-path verification against a real Rekor-backed bundle waits for the platform live-integration harness |
| req-sigstore-core-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | RFC3161 bundles, dedicated verification node, live Rekor pull, OIDC issuer node, checkpoint nodes, witness/cosigning, attestations |

### Plugin Scope
----
RID: `req-sigstore-core-scope`
Status: `Implemented`

`sigstore_core` is a library plugin that ships:

- Two TAP model types: `rekor_log_entry` and `sigstore_ca`.
- Three edge type declarations: `ATTESTED_BY`, `CERT_ISSUED_BY`, and `SIGNED_BY_IDENTITY`.
- A `sigstore_core.verify` Python module exposing the canonical
  `verify_bundle(...)` function.
- A `sigstore_core.decompose` Python module exposing the canonical
  `bundle_to_grift_fragment(...)` function.
- Plugin-local declaration of the `sigstore` Python library dependency.

The plugin does not run a collector in v0. It does not poll Rekor, Fulcio, or
any other endpoint. Its runtime surface is its Python helper modules; its
graph surface is the model and edge types other plugins write to.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-scope-1 | Library Shape | Proposed | The plugin registers no collectors; its public Python API is `sigstore_core.verify` and `sigstore_core.decompose`. | |
| req-sigstore-core-scope-2 | Models Owned Here | Proposed | `rekor_log_entry` and `sigstore_ca` are owned by `sigstore_core`, not by any consumer plugin. | |
| req-sigstore-core-scope-3 | Edges Owned Here | Proposed | `ATTESTED_BY`, `CERT_ISSUED_BY`, and `SIGNED_BY_IDENTITY` are declared by `sigstore_core`. | Consumer plugins emit instances. |

### Model Set
----
RID: `req-sigstore-core-models`
Status: `Implemented`

The v0 model set is intentionally small. Two node types cover the trust chain
visible in any Sigstore bundle today.

Models:

- `rekor_log_entry` — one node per `(log_key_id, log_index)` pair. Represents one signed-artifact entry in a Rekor transparency log. Stores only immutable facts about the Rekor entry; verification verdict lives on the `ATTESTED_BY` edge.
- `sigstore_ca` — one node per CA URL. Represents a certificate authority (v0: only the Sigstore public-good Fulcio instance, but `ca_kind` and `ca_url` leave room for private Fulcio deployments and future non-Fulcio CAs).

#### Identity

Natural-key inputs:

| Model | Natural Key |
| --- | --- |
| `rekor_log_entry` | `(log_key_id, log_index)` |
| `sigstore_ca` | `ca_url` |

Entity IDs are deterministic UUIDv5 values over the model type and natural key.
`log_key_id` is the Rekor log's signing-key identifier as carried in the
bundle's inclusion proof (a hex digest, sometimes called the log ID). It is
the strongest canonical identifier because it identifies *which* log signed
the inclusion proof; the public-good log has one well-known value but private
Rekor deployments each have their own. The log's URL (display-origin) is
captured as a regular field but is not used for identity, because the same
log can be reachable through multiple URLs and a URL alone cannot disambiguate
between logs that happen to be hosted at the same address over time. The
Rekor entry UUID is captured as a regular field when present but is not used
for entity identity (it does not survive re-shaping of the entry).

#### Fields

`rekor_log_entry` (immutable transparency-log facts only):

| Field | Type | Required | Meaning |
| --- | --- | :---: | --- |
| `log_key_id` | string | yes | Rekor log signing-key identifier from the inclusion proof. |
| `log_index` | int | yes | Position in the Rekor log. |
| `rekor_log_url` | string | no | Display-origin URL the bundle was logged against (e.g. `https://rekor.sigstore.dev`) when known. |
| `integrated_time` | string | yes | ISO 8601 UTC; when Rekor accepted the entry. |
| `entry_uuid` | string | no | Rekor's own entry UUID, when present in the bundle. |
| `tree_id` | string | no | Merkle tree id at inclusion. |
| `tree_size_at_inclusion` | int | no | Tree size at inclusion. |
| `root_hash_at_inclusion` | string | no | Signed root hash at inclusion. |
| `entry_kind` | string | yes | `hashedrekord`, `dsse`, `intoto`, etc. |
| `artifact_digest_alg` | string | no | e.g. `sha256`. |
| `artifact_digest` | string | no | Hex digest of the artifact this entry attests to. |
| `signing_identity_uri` | string | yes | SAN URI from the signing cert (e.g. workflow identity). |
| `signing_identity_issuer` | string | yes | OIDC issuer URL embedded in the cert. |

Verification verdict, the policy that produced it, the verification time, and
failure code/detail are *not* fields on this node — they live on the
`ATTESTED_BY` edge from the signed entity to this entry. See [Edge
Vocabulary](#edge-vocabulary).

`sigstore_ca`:

| Field | Type | Required | Meaning |
| --- | --- | :---: | --- |
| `ca_url` | string | yes | CA endpoint URL (e.g. `https://fulcio.sigstore.dev`). |
| `ca_name` | string | yes | Human-friendly name (e.g. `Sigstore Public Good Fulcio`). |
| `ca_kind` | string | yes | `fulcio` in v0; leaves room for non-Fulcio CAs. |
| `trust_root_source` | string | yes | Where the verifier obtained the trust root for this CA (`tuf-public-good` in v0). |
| `trust_root_fetched_at` | string | no | ISO 8601 UTC when the verifier last refreshed the TUF trust root, when known. |

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-models-1 | Models Declared | Proposed | The plugin declares the two v0 model types listed above. | |
| req-sigstore-core-models-2 | Deterministic Identity | Proposed | Both models use deterministic UUIDv5 identity based on their natural keys. | |
| req-sigstore-core-models-3 | Immutable Facts Only | Proposed | `rekor_log_entry` stores only immutable transparency-log facts; verification verdict and policy-applied attributes live on the `ATTESTED_BY` edge, not the node. | A `rekor_log_entry` only exists if `verify_bundle` parsed the bundle. |
| req-sigstore-core-models-4 | CA Kind Field | Proposed | `sigstore_ca.ca_kind` is a string field that defaults to `fulcio` in v0 but is not constrained to it at the model level. | Future non-Fulcio CAs need no schema change. |

### Edge Vocabulary
----
RID: `req-sigstore-core-edges`
Status: `Implemented`

Edges express the trust chain a verifier walks from a signed entity to the CA
that issued its signing cert.

V0 edge types:

| Edge | Direction | Meaning |
| --- | --- | --- |
| `ATTESTED_BY` | signed entity -> `rekor_log_entry` | "This entity's signature was logged in Rekor at this entry, verified under this policy at this time." |
| `CERT_ISSUED_BY` | `rekor_log_entry` -> `sigstore_ca` | "The signing cert for this entry was issued by this CA." |
| `SIGNED_BY_IDENTITY` | `rekor_log_entry` -> `github_workflow` | "The Fulcio cert for this entry asserts this GitHub workflow as the signing identity." |

The source side of `ATTESTED_BY` is intentionally polymorphic. The plugin
declares the edge type but does not constrain which entity types may anchor a
Rekor entry. Consumer collectors emit `ATTESTED_BY` from whatever they signed
(signed evidence documents, container images, IaC artifacts, attestation
statements, etc.).

#### ATTESTED_BY Edge Attributes

`ATTESTED_BY` carries the verification verdict and the policy that produced
it. The Rekor entry node is immutable; the same entry can be verified under
different policies, at different times, with different results, and each
verdict belongs to the relationship rather than the entry. The edge
attributes:

| Attribute | Type | Required | Meaning |
| --- | --- | :---: | --- |
| `signature_verified` | bool | yes | The absolute verdict from `verify_bundle`. `True` if all checks passed under the supplied policy; `False` otherwise. |
| `verified_at` | string | yes | ISO 8601 UTC of the verification call that produced this verdict. |
| `policy_kind` | string | yes | The kind of policy applied. v0 emits only `github_workflow`. |
| `policy_oidc_issuer` | string | yes | OIDC issuer URL the policy required. |
| `policy_github_repository` | string | no | GitHub repo the policy required (when `policy_kind = github_workflow`). |
| `policy_workflow_identity_uri` | string | no | Exact SAN URI the policy required, when supplied. |
| `policy_workflow_ref` | string | no | Git ref the policy required, when supplied. |
| `policy_workflow_sha` | string | no | Commit SHA the policy required, when supplied. |
| `verification_failure_code` | string | no | Short machine-readable failure tag when `signature_verified` is `False` (e.g. `policy_mismatch`, `cert_chain`, `rekor_proof`, `signature`, `bundle_parse`, `unexpected`). Empty when verified. |
| `verification_failure_detail` | string | no | Human-readable detail string from the verifier when `signature_verified` is `False`. Empty when verified. |

Re-verification under the same policy updates the edge attributes (verdict +
verified_at + any new failure detail) in place. Verifying the same bundle
under a *different* policy is a v0 surface limitation: there is one
`ATTESTED_BY` edge per `(signed entity, rekor_log_entry)` pair, so the second
verification overwrites the first. A dedicated `sigstore_verification` node
type is the v1 candidate for multi-policy / full-history verification (see
non-goals).

#### SIGNED_BY_IDENTITY Edge

`SIGNED_BY_IDENTITY` targets `github_workflow` in v0 because that is the
identity shape `GitHubWorkflowPolicy` enforces and the only identity kind any
TAP consumer currently signs against. The target side is open to future
identity-node types (raw email identities, GitLab workflows, etc.) as those
policy descriptors and identity nodes arrive; v0 does not enumerate them.

The edge is **caller-supplied**, not internally resolved. The decompose
helper accepts an optional `signing_identity_entity_id: str | None` parameter;
when supplied, the helper emits one `SIGNED_BY_IDENTITY` edge to that entity.
The caller is responsible for resolving the bundle's `signing_identity_uri`
to a concrete entity before calling the helper. This keeps `sigstore_core`
out of cross-plugin graph reads and avoids embedding identity-resolution
policy in the verification helper.

For the `github_workflow` target specifically (the v0 shape), the SAN URI
encodes `(owner, repo, workflow_path, ref)` — for example
`https://github.com/<owner>/<repo>/.github/workflows/<file>@refs/heads/main`.
`github_core` keys `github_workflow` on `(full_name, workflow_id_int)` where
`full_name = "owner/repo"` and `workflow_id_int` is GitHub's numeric
workflow id; that numeric id is *not* in the SAN URI. The supported
resolution path for callers is therefore:

1. Parse the SAN URI to extract `full_name` (`<owner>/<repo>`) and `path` (`.github/workflows/<file>`).
2. Search `github_workflow` for a node matching both `full_name` and `path` (`github_workflow.path` is `db_index=True` in github_core v0).
3. Pass the resolved entity id as `signing_identity_entity_id` to `bundle_to_grift_fragment`.

The `@<ref>` suffix is not part of `github_workflow` identity — one workflow
definition runs on many refs — so it is not used for matching here. Callers
that want ref-level binding express it via `GitHubWorkflowPolicy.workflow_ref`
(verifier-side enforcement) and via the `policy_workflow_ref` attribute on
the `ATTESTED_BY` edge (so the bound ref is visible without re-running
verification).

A declarative grid-link-manifest path (mirroring github_core's
`github_grid_link_manifest.json` shape) is open as a follow-up: the
composite `(full_name, path)` lookup is a tighter fit for a `custom_fn`
resolver than for the existing single-`source_field_path` rule shape, so
v0 keeps the resolution in caller code rather than declaring a manifest rule
inside sigstore_core. Hotlink-based auto-resolution remains an option
callers may build on top of the helper, not something the helper drives
itself.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-edges-1 | Trust Chain | Proposed | The three edge types are declared and constrained. | |
| req-sigstore-core-edges-2 | Polymorphic Anchor | Proposed | `ATTESTED_BY` does not constrain its source entity type at the platform level. | |
| req-sigstore-core-edges-3 | Decompose Emits CA Chain | Proposed | `bundle_to_grift_fragment` emits exactly one `ATTESTED_BY` and exactly one `CERT_ISSUED_BY` per call. | |
| req-sigstore-core-edges-4 | Verdict On Edge | Proposed | The verification verdict, the policy that produced it, and the verification time are recorded as attributes of the `ATTESTED_BY` edge, not as fields on `rekor_log_entry`. | |
| req-sigstore-core-edges-5 | Identity Edge Caller-Supplied | Proposed | `SIGNED_BY_IDENTITY` is emitted only when the caller passes a resolved identity entity id to the decompose helper. The helper performs no cross-plugin graph reads of its own. | |
| req-sigstore-core-edges-6 | Github_Core Optional For Helper | Proposed | The decompose helper runs without `github_core` installed; in that mode `SIGNED_BY_IDENTITY` is simply not emitted (no caller can supply a target entity id). | The `signing_identity_uri` field on the Rekor entry remains, so the identity is still visible as data. |

### No Collector In v0
----
RID: `req-sigstore-core-no-collector`
Status: `Implemented`

The plugin registers no `tap_cares` collector capability in v0. Bundle
fetching is done by whoever owns the signed artifact's source — the collector
that pulls the underlying signed evidence also pulls its sibling bundle. The
plugin's role is to verify the bundle a caller already has, and to decompose
it into graph data the caller stitches into their own GRIFT batch.

Live Rekor pulling — querying `rekor.sigstore.dev` independently to confirm an
entry, or to search by digest — is the natural v1 collector candidate and is
explicitly deferred in non-goals.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-no-collector-1 | No Collector Registered | Proposed | `plugins/sigstore_core/apps.py` registers no collector capability with `tap_cares` in v0. | |
| req-sigstore-core-no-collector-2 | No Network Calls | Proposed | The plugin's helpers issue no outbound network calls of their own beyond the TUF trust-root refresh that `sigstore-python` performs internally. | |

### Verify Helper
----
RID: `req-sigstore-core-verify`
Status: `Implemented`

`sigstore_core.verify` exposes the canonical verification function every TAP
plugin uses to verify a Sigstore signature bundle.

Signature shape (v0; subject to refinement during implementation):

```python
def verify_bundle(
    body: bytes,
    bundle: bytes,
    *,
    policy: VerificationPolicy,
) -> VerificationResult
```

`VerificationResult` is a structured object (dataclass or `TypedDict`) with at
minimum:

| Field | Type | Meaning |
| --- | --- | --- |
| `signature_verified` | `bool \| None` | `True` if all of signature, cert chain, Rekor inclusion proof, and policy match. `False` if any check fails. `None` only if the bundle itself was unparseable. |
| `signed_by` | string | SAN URI from the signing cert. Empty string when the bundle was unparseable. |
| `signing_issuer` | string | OIDC issuer URL from the cert, when extractable. |
| `log_key_id` | string | Rekor log signing-key identifier from the inclusion proof. |
| `rekor_log_url` | string | Display-origin URL the bundle was logged against, when known. |
| `rekor_log_index` | string | The Rekor log index, when extractable from the bundle. |
| `integrated_time` | string | ISO 8601 UTC of the Rekor inclusion, when extractable. |
| `entry_kind` | string | `hashedrekord`, `dsse`, `intoto`, etc., when extractable. |
| `verified_at` | string | ISO 8601 UTC of the verification call. |
| `failure_code` | string | Short machine-readable failure tag when `signature_verified` is `False`; empty otherwise. v0 codes: `bundle_parse`, `no_rekor_proof`, `policy_mismatch`, `cert_chain`, `rekor_proof`, `signature`, `unexpected`. |
| `failure_detail` | string | Human-readable detail string from the verifier when verification fails; empty otherwise. |
| `parsed_bundle` | opaque | The parsed `sigstore.models.Bundle` (or `None`); passed to `decompose` to avoid double-parsing. Not serialized. |

Behavior:

- A bundle that fails to parse yields `signature_verified=None`,
  `failure_code="bundle_parse"`, and empty identity/log fields. Callers can
  distinguish "unknown" (parse failure) from "no" (policy or crypto failure)
  on `signature_verified`.
- A bundle that parses but contains no Rekor inclusion proof (e.g. a
  timestamp-only RFC3161 bundle) yields `signature_verified=False`,
  `failure_code="no_rekor_proof"`. v0 does not verify timestamp-only bundles.
- A bundle that parses with a Rekor proof but fails any check yields
  `signature_verified=False`, with `signed_by` and `signing_issuer` populated
  from the cert (so the failed identity is still visible on the resulting
  node), and `failure_code` set to the most-specific tag the verifier can
  report.
- Verification never raises on a parseable-but-failed bundle. Unexpected
  exceptions from `sigstore-python` are caught and recorded as
  `signature_verified=False`, `failure_code="unexpected"`.
- The internal `Verifier.production()` instance is cached per worker lifetime
  (TUF trust root fetching is expensive; one verifier per process is plenty).

The function does not write to the graph. Its only effects are the trust-root
refresh side-effect inside `sigstore-python` and the returned result.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-verify-1 | Canonical Function | Proposed | `sigstore_core.verify.verify_bundle` is the single entry point TAP plugins use to verify a Sigstore bundle. | |
| req-sigstore-core-verify-2 | Three-State Result | Proposed | `signature_verified` is `True`, `False`, or `None`, distinguishing parse failure from verification failure. | |
| req-sigstore-core-verify-3 | Never Raises On Verification Failure | Proposed | A parseable bundle that fails verification yields `signature_verified=False`, not an exception. | |
| req-sigstore-core-verify-4 | Failure Code Surfaced | Proposed | A failed verification populates `failure_code` and `failure_detail` so callers can distinguish failure modes without parsing the detail string. | |
| req-sigstore-core-verify-5 | Rekor-Backed Only | Proposed | A parseable bundle lacking a Rekor inclusion proof yields `signature_verified=False`, `failure_code="no_rekor_proof"`. RFC3161 timestamp-only verification is deferred. | |
| req-sigstore-core-verify-6 | Verifier Cached | Proposed | The `sigstore.verify.Verifier` instance is cached per worker lifetime. | |
| req-sigstore-core-verify-7 | No Graph Writes | Proposed | `verify_bundle` performs no graph reads or writes. | |
| req-sigstore-core-verify-8 | Consumers Migrated | Proposed | Once this helper is live, any pre-existing in-consumer verify modules are removed and their callers switched to `sigstore_core.verify.verify_bundle`. | Per-consumer migration steps live in each consumer plugin's own spec. |

### Decompose Helper
----
RID: `req-sigstore-core-decompose`
Status: `Implemented`

`sigstore_core.decompose` exposes the canonical decomposition function that
turns a verified bundle into the four pieces of graph data the plugin owns: a
`rekor_log_entry` node, a `sigstore_ca` upsert, a `CERT_ISSUED_BY` edge, and
an `ATTESTED_BY` edge.

Signature shape (v0; subject to refinement during implementation):

```python
def bundle_to_grift_fragment(
    result: VerificationResult,
    *,
    anchor_entity_id: str,
    policy: VerificationPolicy,
    dimensions: dict[str, str],
    signing_identity_entity_id: str | None = None,
) -> GriftFragment
```

`GriftFragment` is a typed object whose `entities` and `edges` lists slot into
the caller's GRIFT batch. The fragment contains:

- One `sigstore_ca` upsert (deduplicated on `ca_url`; v0 defaults to the
  public-good Fulcio instance when no other CA is detected).
- One `rekor_log_entry` node with the immutable transparency-log fields described under [Model Set](#model-set), populated from `result`.
- One `CERT_ISSUED_BY` edge: `rekor_log_entry` -> `sigstore_ca`.
- One `ATTESTED_BY` edge: anchor entity -> `rekor_log_entry`, with verdict + policy attributes populated from `result` and `policy`.
- Zero or one `SIGNED_BY_IDENTITY` edge: `rekor_log_entry` -> identity entity. Emitted only when the caller passed a non-`None` `signing_identity_entity_id`. The helper performs no graph reads of its own to resolve this.

Behavior:

- The function refuses to operate on an unparseable bundle (`result.parsed_bundle is None`). The caller decides whether to skip this artifact or record a "no Rekor entry observed" state on the anchor node by some other means.
- The function emits the rekor_log_entry node and the `ATTESTED_BY` edge even when `result.signature_verified is False`. A failed verdict is still useful graph data (the bundle existed, the entry was logged, the policy rejected it for reason X); silently dropping it would violate the disclosure rule.
- The function does not fetch anything. All data is drawn from `result` and `policy`.
- Dimensions on emitted nodes and edges are the caller's responsibility; the
  helper applies the `dimensions` dict it was given. Plugin-owned static
  defaults (`sigstore.platform`, `sigstore.ca_kind`, `sigstore.log_kind`) are
  set on the models themselves and require no caller action.
- The helper does not write to the graph. The caller merges the returned
  fragment into its own GRIFT batch and submits via the normal collector path.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-decompose-1 | Returns Fragment | Proposed | `bundle_to_grift_fragment` returns a typed object the caller merges into its batch; the helper does not submit GRIFT itself. | |
| req-sigstore-core-decompose-2 | Four Or Five Pieces | Proposed | The fragment contains the CA upsert, the log-entry node, `CERT_ISSUED_BY`, `ATTESTED_BY`, and (when the caller supplies `signing_identity_entity_id`) `SIGNED_BY_IDENTITY`, and nothing else in v0. | |
| req-sigstore-core-decompose-3 | Unparseable Refused | Proposed | The helper raises if `result.parsed_bundle` is `None`. | Callers must check `verify_bundle` parsed successfully before decomposing. |
| req-sigstore-core-decompose-4 | No Network Calls | Proposed | The helper reads only `result`; it makes no outbound calls. | |
| req-sigstore-core-decompose-5 | Failed Verdicts Emitted | Proposed | The helper emits the Rekor entry node and the `ATTESTED_BY` edge with `signature_verified=False` when verification failed but the bundle parsed; it does not silently drop failed verdicts. | |

### Verification Policy Shape
----
RID: `req-sigstore-core-policy`
Status: `Implemented`

The `policy` argument to `verify_bundle` is a typed descriptor that names the
identity-shape the caller wants enforced. v0 ships one concrete policy class
because the only identity shape any current consumer signs against is
GitHub-Actions-signed artifacts; the descriptor shape leaves room for
additional policies later without changing `verify_bundle`'s signature.

V0 policy:

```python
@dataclass(frozen=True)
class GitHubWorkflowPolicy:
    oidc_issuer: str                            # e.g. "https://token.actions.githubusercontent.com"
    github_repository: str                      # e.g. "<owner>/<repo>"
    workflow_identity_uri: str | None = None    # exact SAN URI, e.g. "https://github.com/<owner>/<repo>/.github/workflows/<file>@refs/heads/main"
    workflow_ref: str | None = None             # e.g. "refs/heads/main" or "refs/tags/v1.2.3"
    workflow_sha: str | None = None             # commit SHA the workflow ran against (carried in the Fulcio cert; matches a `github_actions_run.head_sha`-style value on the github_core side)
```

`oidc_issuer` and `github_repository` are required (repo-level binding is the
weakest useful identity check). The optional fields tighten the check:

- `workflow_identity_uri` — verifies the exact workflow file + ref the cert's SAN must match. Strongest predicate.
- `workflow_ref` — verifies the Git ref the workflow ran on, independent of which workflow file.
- `workflow_sha` — verifies the commit SHA.

Callers supply whichever predicates they want enforced. Repo-only callers
keep the optional fields `None` and accept the weaker "some workflow in this
repo" verdict; demos that need "this specific workflow signed it" supply the
exact identity URI and the verdict tightens accordingly. The applied policy
predicates are recorded on the `ATTESTED_BY` edge attributes so the verdict
is interpretable later without re-running verification.

Internally `sigstore_core.verify` translates this into the equivalent
`sigstore.verify.policy.AllOf([...])` expression composed of `OIDCIssuer`,
`GitHubWorkflowRepository`, and (when supplied) `Identity`,
`GitHubWorkflowRef`, `GitHubWorkflowSHA` predicates. The translation is the
only place `sigstore-python`'s policy API appears in the public TAP-side
surface.

Future policy descriptors (e.g. `EmailIdentityPolicy(issuer, identity)`,
`GitLabWorkflowPolicy(...)`) are added in their own changes as new consumers
arrive. The v0 spec does not attempt to enumerate them.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-policy-1 | Typed Descriptor | Proposed | The `policy` argument is a typed dataclass, not a raw `sigstore-python` policy object. | Keeps `sigstore-python` out of consumer plugins' imports. |
| req-sigstore-core-policy-2 | GitHub Workflow Policy Shipped | Proposed | `GitHubWorkflowPolicy` is the one concrete policy in v0, with required `oidc_issuer` and `github_repository` plus optional `workflow_identity_uri`, `workflow_ref`, and `workflow_sha` predicates. | |
| req-sigstore-core-policy-3 | Applied Predicates Recorded | Proposed | The applied policy predicates are captured on the `ATTESTED_BY` edge attributes so a reader can tell which checks the verdict relied on. | Required: `policy_kind`, `policy_oidc_issuer`. Optional: repo, identity URI, ref, SHA. |
| req-sigstore-core-policy-4 | Open To Extension | Proposed | Adding a new policy descriptor does not require changing `verify_bundle`'s signature. | |

### Dimension Strategy
----
RID: `req-sigstore-core-dimensions`
Status: `Implemented`

Sigstore is treated as its own platform. The plugin uses flat,
Sigstore-specific dimensions:

| Key | Example | Applies To |
| --- | --- | --- |
| `sigstore.platform` | `public-good` | All `sigstore_core`-owned nodes and edges |
| `sigstore.ca_kind` | `fulcio` | `sigstore_ca` nodes |
| `sigstore.log_kind` | `rekor` | `rekor_log_entry` nodes |

Static model defaults set only the dimensions that are true for all instances
of a given type (e.g. every `rekor_log_entry` carries `sigstore.log_kind =
"rekor"`). `sigstore.platform` defaults to `public-good` in v0 because the
only CA and log we encounter are the Sigstore public-good instances; private
Sigstore deployments add their own platform-name values without a schema
change.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-dimensions-1 | Platform Dimension | Proposed | All `sigstore_core`-owned nodes and edges carry `sigstore.platform`. | Default `public-good` in v0. |
| req-sigstore-core-dimensions-2 | CA Kind Dimension | Proposed | `sigstore_ca` nodes carry `sigstore.ca_kind`. | Default `fulcio` in v0. |
| req-sigstore-core-dimensions-3 | Log Kind Dimension | Proposed | `rekor_log_entry` nodes carry `sigstore.log_kind`. | Default `rekor` in v0. |

### Plugin Python Dependency
----
RID: `req-sigstore-core-python-deps`
Status: `Proposed`

The `sigstore` Python library is owned by `sigstore_core` and declared in
`plugins/sigstore_core/pyproject.toml` via the root uv workspace pattern.
This follows the precedent github_core landed for `PyYAML` (the first proof
of `req-plugin-arch-python-deps`): plugin-local dependency metadata, root
uv workspace/member wiring, one resolved environment, no dependency entries
in `tap-plugin.toml`.

The root `pyproject.toml`'s previous `sigstore` dependency (carried over from
the pre-`sigstore_core` era) is removed in the same change that scaffolds
this plugin, since the package is now declared by the workspace member that
actually uses it.

Consumer plugins (and the rest of the codebase) MUST import only from
`sigstore_core.*` and never from `sigstore.*` directly. This keeps
`sigstore-python`'s surface contained to a single plugin and lets future
shifts (e.g. swapping verifier libraries, sub-vendoring trust roots) happen
behind the canonical TAP-side API.

This is dependency ownership, not runtime isolation. The TAP Python
environment will contain the package when the plugin is installed; the
dependency is justified by and documented with `sigstore_core`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-python-deps-1 | Sigstore Approved | Proposed | `sigstore` is approved specifically for `sigstore_core`. | The plugin formalizes ownership of an existing TAP dependency. |
| req-sigstore-core-python-deps-2 | Plugin-Owned Declaration | Proposed | The `sigstore` dependency is declared in `plugins/sigstore_core/pyproject.toml`, registered through the root uv workspace, and not declared in the root `pyproject.toml` or in `tap-plugin.toml`. | Mirrors github_core's `PyYAML` pattern. |
| req-sigstore-core-python-deps-3 | Root Pyproject Cleaned | Proposed | The root `pyproject.toml`'s `sigstore` entry is removed in the same change that scaffolds this plugin. | The dependency now flows through the workspace member that uses it. |
| req-sigstore-core-python-deps-4 | No Direct Sigstore Imports In Consumers | Proposed | Consumer plugins import only from `sigstore_core.*`, not from `sigstore.*`. | Keeps the `sigstore-python` surface contained. |

### Verification Disclosure
----
RID: `req-sigstore-core-disclosure`
Status: `Implemented`

Per [[disclose-shortcuts-machine-readably]], the verification result the
plugin records must be machine-readable on the artifact itself rather than
implied by absence.

The decompose helper encodes verification status this way:

- `ATTESTED_BY.signature_verified` is the absolute verdict: `True` (verified
  end-to-end against the supplied policy) or `False` (parseable bundle that
  failed some check). The attribute is never `None` on an edge the plugin
  emits; unparseable bundles never produce an `ATTESTED_BY` edge.
- `ATTESTED_BY.verification_failure_code` and `verification_failure_detail`
  surface *why* a `False` verdict landed, in a machine-readable shape.
  Consumers MUST NOT rely on log scraping to surface failure modes.
- `ATTESTED_BY.policy_kind` + `policy_*` attributes record *which policy* the
  verdict relied on, so a reader can interpret "verified=True" without
  re-running verification.

Downstream panels and views that read this verdict MUST distinguish the four
meaningful states explicitly:

- signed entity has an `ATTESTED_BY` edge with `signature_verified=True` -> verified under the recorded policy
- signed entity has an `ATTESTED_BY` edge with `signature_verified=False` -> failed under the recorded policy (surface `failure_code`)
- signed entity has no `ATTESTED_BY` edge but the underlying source advertised a bundle -> not observed (parse failed, or upstream omitted the bundle entirely)
- signed entity has no `ATTESTED_BY` edge and the source advertised no bundle -> not applicable

Treating "no ATTESTED_BY edge" as silent success is the disclosure failure
mode this requirement exists to prevent.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-disclosure-1 | Absolute Fact On Edge | Proposed | `ATTESTED_BY.signature_verified` records the absolute verdict; consumers derive interpretation, do not store it. | |
| req-sigstore-core-disclosure-2 | No Implicit Success | Proposed | Absence of an `ATTESTED_BY` edge is "not observed" (or "not applicable"), not "verified." Consumer panels must surface this distinction explicitly. | |
| req-sigstore-core-disclosure-3 | Failure Reason Machine-Readable | Proposed | A `False` verdict carries `verification_failure_code` and `verification_failure_detail` on the edge so consumers can branch on the failure mode. | |
| req-sigstore-core-disclosure-4 | Applied Policy On Edge | Proposed | The applied policy descriptor is recorded on the edge attributes so the verdict is interpretable later. | |

### Live-Bundle Verification Testing (Backlog)
----
RID: `req-sigstore-core-testing-backlog`
Status: `Backlog`

v0 ships **hermetic unit tests only**. The set of behaviors exercised at v0 ship is intentionally limited to what can be tested without touching the network, without reaching into another plugin's artifacts, and without publishing anything to the public-good Rekor log:

- `verify_bundle` returns `signature_verified=None, failure_code="bundle_parse"` when fed garbage bytes — exercised against a literal `b"not a bundle"` fixture.
- `GitHubWorkflowPolicy` constructs cleanly with required fields, and with each combination of optional predicates.
- `_classify_failure` maps representative exception class names to the documented v0 failure codes.
- `bundle_to_grift_fragment` produces the documented 4-piece (no caller identity) and 5-piece (with caller identity) fragment shapes, with deterministic UUIDv5 IDs, dimension propagation, and failed-verdict edges still emitted. These tests synthesize a `VerificationResult` directly; the `parsed_bundle` field is a sentinel object the helper does not introspect.

Three behaviors require a real Rekor-backed Sigstore bundle to test end-to-end and are **deferred to the live-integration test harness** (`req-tap-test-live-integration-backlog` in `specs/spec-tap-testing.md`):

1. **Happy-path verification** — `verify_bundle` returning `signature_verified=True` against a real bundle whose Fulcio cert, signature, Rekor inclusion proof, and policy all match. This is the load-bearing assertion that the helper actually works; v0 cannot prove it without reaching across to another plugin's published artifacts (which would violate `req-tap-test-hermetic-plugins`) or publishing TAP-owned entries to the public-good Rekor log (which leaves permanent records and isn't appropriate for routine testing).
2. **Policy-mismatch verification** — `verify_bundle` returning `signature_verified=False, failure_code="policy_mismatch"` against a real bundle with a wrong-repo or wrong-identity policy. Requires the same real bundle as the happy path.
3. **`no_rekor_proof` enforcement** — `verify_bundle` returning `signature_verified=False, failure_code="no_rekor_proof"` against a parseable bundle that lacks a Rekor inclusion proof (e.g. an RFC3161 timestamp-only bundle). Requires either an RFC3161-shaped bundle in hand or synthetic-bundle construction; both are deferred.

Until the live-integration harness exists, any developer who wants to validate the happy path locally can:

- Mark a workflow-machine-local test as `@pytest.mark.live_fetch` (already configured to skip by default in the root `pyproject.toml`).
- Vendor a real Sigstore bundle into `plugins/sigstore_core/tests/fixtures/` **only** with a sibling `SOURCE` note documenting which artifact it was lifted from, when, and under which license — this counts as an explicit vendor of a third-party artifact, not a coincidental cross-plugin dependency.

The right long-term shape is the harness, not vendored fixtures. Vendoring is the fallback; it shouldn't be the v0 plan.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-testing-backlog-1 | Hermetic Tests Shipped | Implemented | v0 ships hermetic unit tests for bundle_parse, dataclass shape, _classify_failure, and the full decompose surface (with mocked VerificationResult). | |
| req-sigstore-core-testing-backlog-2 | Happy Path Deferred | Backlog | Happy-path `verify_bundle` validation against a real Rekor-backed bundle waits for `req-tap-test-live-integration-backlog`. | |
| req-sigstore-core-testing-backlog-3 | Policy Mismatch Deferred | Backlog | Policy-mismatch verification against a real bundle waits for the same harness. | |
| req-sigstore-core-testing-backlog-4 | no_rekor_proof Deferred | Backlog | RFC3161-only or otherwise-no-proof bundle verification waits for the harness or a vendored fixture with a `SOURCE` note. | |
| req-sigstore-core-testing-backlog-5 | No Coincidental Cross-Plugin | Implemented | v0 tests do not reach into any other plugin's `grift/`, `static/`, `tests/fixtures/`, or `.well-known/` artifacts, per `req-tap-test-hermetic-plugins`. | |

### v0 Non-Goals
----
RID: `req-sigstore-core-nongoals`
Status: `Proposed`

Out of scope for v0:

- RFC3161 timestamp-only bundles (Sigstore bundles that carry a signed
  timestamp instead of a Rekor inclusion proof). v0 explicitly rejects these
  with `failure_code="no_rekor_proof"`. Supporting timestamp-only verification
  is a v1 candidate.
- A dedicated `sigstore_verification` node type for multi-policy / full-history
  verification observations. v0 keeps the verdict as `ATTESTED_BY` edge
  attributes; one verdict per `(signed entity, rekor_log_entry)` pair. If a
  later consumer needs to record multiple verdicts (different policies,
  re-verification history) for the same pair, the right shape is a dedicated
  observation node, lifted under its own requirement.
- Live Rekor pulling. Querying `rekor.sigstore.dev` independently for a digest
  or log index is the natural v1 collector candidate; v0 trusts the inclusion
  proof shipped in the bundle.
- An `oidc_issuer` node. The OIDC issuer URL is captured as a string field on
  `rekor_log_entry.signing_identity_issuer`; lifting it to its own node and
  adding an `IDENTITY_VOUCHED_BY` edge from `rekor_log_entry` is near-soon
  work for a follow-up pass.
- `rekor_log_checkpoint` nodes. The checkpoint fields are captured on the entry
  in v0; if the demo or a later consumer wants checkpoint sharing visible as
  its own node, that is a v1 addition.
- Witness/cosigning consensus checks. Cross-referencing entries against
  witness signatures is v1+ work.
- Consistency proofs. Re-verifying historical entries against fresh Rekor log
  state is v1+ work.
- Private Fulcio or alternate transparency log instances beyond the schema's
  ability to represent them via `ca_kind` and `rekor_log_url`. The plugin's
  models accommodate them; v0 does not exercise that path.
- intoto / DSSE attestation statement modeling. `entry_kind` distinguishes the
  shape on the entry; lifting attestation statements to their own node type
  is a future plugin or future expansion of this one.
- Producing signatures. TAP verifies and decomposes; it never signs anything.
- Running a collector of any kind. `sigstore_core` is a library plugin in v0;
  any collector that arrives later does so under its own requirement.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sigstore-core-nongoals-1 | RFC3161 Bundles Deferred | Proposed | v0 rejects timestamp-only bundles with `failure_code="no_rekor_proof"`. | Honest demo fence. |
| req-sigstore-core-nongoals-2 | Dedicated Verification Node Deferred | Proposed | v0 keeps verdict on the `ATTESTED_BY` edge; a `sigstore_verification` node is a v1 candidate for multi-policy / re-verification history. | |
| req-sigstore-core-nongoals-3 | Live Rekor Deferred | Proposed | v0 does not query Rekor over the network. | |
| req-sigstore-core-nongoals-4 | OIDC Issuer Deferred | Proposed | v0 captures the OIDC issuer as a field, not a node. | Near-soon follow-up. |
| req-sigstore-core-nongoals-5 | Checkpoint Node Deferred | Proposed | v0 captures checkpoint fields on the entry, not as their own node. | |
| req-sigstore-core-nongoals-6 | Attestation Models Deferred | Proposed | v0 does not lift intoto / DSSE statements to their own node types. | |
| req-sigstore-core-nongoals-7 | No Signing | Proposed | The plugin never produces a Sigstore signature. | |
| req-sigstore-core-nongoals-8 | No Collector | Proposed | No `tap_cares` collector is registered in v0. | |

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`,
`Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`,
`Backlog`.
