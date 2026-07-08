# Identity Core Plugin Specification

## Plugin Identity

- **Slug:** `identity_core`
- **Kind:** substrate library plugin — vocabulary + mechanism, **no collector in v0**.
- **Public surface:**
  - **Models** (see `req-identity-core-model`): `oidc_issuer`.
  - **Helpers** (see `req-identity-core-issuer-id`, `req-identity-core-canonical-url`,
    `req-identity-core-envelope`):
    - `identity_core.issuer.canonical_issuer_url(raw: str) -> str` — the one canonical
      normalization every observer runs before keying an issuer.
    - `identity_core.issuer.oidc_issuer_id(raw: str) -> UUID` — the deterministic entity
      id, derived from the canonical form. The **only** way to compute an issuer id.
    - `identity_core.issuer.oidc_issuer_node_envelope(raw: str, *, dimensions=None)
      -> <node envelope>` — mints a GRIFT node fragment a consumer merges into its own
      batch. (The `display_name` param from the original design is dropped in v0: the
      entity spine projects `get_name()`=issuer_url on save, so a divergent name would
      not survive — the node name is always the issuer_url.)
  - **Edge types:** **none owned in v0.** The issuer is a convergence *target*; every
    edge that touches it is owned by the plugin that *asserts* the relationship
    (`req-identity-core-edge-retargets`).
  - **Default dimensions** (see `req-identity-core-dimensions`): `identity.protocol: oidc`.

## Philosophy

Identity is cross-cutting substrate, not domain payload. An OIDC issuer is a
**convergence node**: github references its Actions issuer, AWS IAM federates trust
into an issuer, Sigstore binds signing certs to identities vouched by an issuer. In
v0 it landed inside `github_core` (`github_core__oidc_issuer`) purely because github
was the first plugin to need it — and the coupling shows: `samsite`'s compliance
collector reaches *into github's collector code*
(`from tap_plugin.github_core.collectors.github_collector.identity import
oidc_issuer_id`) just to compute the issuer's id. That is a domain plugin owning a
primitive three other plugins depend on. The fix is the substrate-core extraction
doctrine: hoist the issuer to a neutral plugin everyone depends on **downward**.

Three principles shape the design:

**Mechanism, not catalog.** identity_core ships the *general* capability to mint an
issuer node from a URL — not a seeded list of well-known issuers. A seed list is a
special-case that only defers the real question (*how does a non-well-known issuer
get in?*) to the worst possible moment: when it is blocking someone. We solve the
general case once, now. Any observer that sees an issuer URL synthesizes the node
through the one helper; observers converge on the same node by deterministic id.

**Existence is not trust.** An `oidc_issuer` node records only that *an issuer
identity was referenced*. It asserts nothing about whether the issuer exists in the
world, is reachable, or is trusted. Trust is a **separate, explicit edge** a specific
principal asserts (`aws_iam_oidc_provider —TRUSTS_ISSUER→`, `rekor_log_entry
—IDENTITY_VOUCHED_BY→`). The substrate never takes a position on trust; it only gives
identities a place to converge. This is the security posture applied: no trust is
smuggled in through the mere presence of a node.

**Convergence is owned here.** github keys the issuer by its full OIDC `iss`
(`https://token.actions.githubusercontent.com`); AWS IAM stores the scheme-less host
(`token.actions.githubusercontent.com`). For independent observers to land on **one**
node, the canonical form must be defined in exactly one place. identity_core owns that
normalization, so convergence is guaranteed rather than coincidental.

## Roadmap Alignment

Realizes the **substrate-core plugin extraction** doctrine (generic cross-cutting
vocabulary lives in neutral `*_core` substrate plugins that domain plugins depend on
downward). Sibling of the `compliance_core` extraction. Advances the cross-plugin
decoupling line: removes the `samsite → github_core` code import and makes
`github_core` independent of the identity primitive. Pre-eviction work — the
`entity_type` rename is namespace churn that must land before plugins are frozen at
released tags (`req-identity-core-migration`).

AI-integration posture: the issuer is machine-legible identity vocabulary with a
described, queryable node type; the "who does this identity converge" question becomes
a one-hop graph traversal rather than code-reading.

## Prior Art

- **OIDC issuer identifier** (OpenID Connect Core / RFC 8414): the `iss` is a
  case-sensitive URL, `https` scheme, no query or fragment, optional path — the natural
  key this node is built on.
- **Sigstore/Fulcio:** the signing certificate carries the issuer as a claim; Sigstore
  verification policy matches on it (samsite's `artifact_manifest` pins
  `oidc_issuer: https://token.actions.githubusercontent.com`).
- **AWS IAM OIDC provider:** stored scheme-less; the reason canonical normalization
  must span scheme'd and scheme-less forms.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Identity Substrate | A neutral home for cross-cutting identity vocabulary; `oidc_issuer` is the v0 tenant. |
| 2. | Library Plugin | No collector in v0. The public surface is the model + Python helpers consumer collectors call. |
| 3. | General-Case Synthesis | Any observer mints an issuer from a URL via one helper; no seeded well-known catalog, no assumption an issuer exists. |
| 4. | Existence ≠ Trust | The node records reference/existence only; trust lives on explicit edges owned by the asserting plugin. |
| 5. | Convergence Owned Here | One canonical URL normalization + one id derivation, so independent observers land on one node. |
| 6. | Downward-Only Deps | github / aws_core / sigstore_core / samsite depend on identity_core; identity_core depends on nothing above core. |
| 7. | Minimal Node | URL identity + a little observed metadata; no issuer-metadata fetch, no liveness, no policy. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-identity-core-scope | [Plugin Scope](#plugin-scope) | Implemented | Substrate library; `oidc_issuer` model + issuer helpers; no collector, no owned edges. |
| req-identity-core-model | [OIDC Issuer Model](#oidc-issuer-model) | Implemented | `identity_core__oidc_issuer`; keyed on canonical issuer host; minimal fields. `get_name()` is the `issuer_url` (no well-known catalog; `display_name` deferred — no backing field). |
| req-identity-core-canonical-url | [Canonical Issuer URL](#canonical-issuer-url) | Implemented | One normalization spanning scheme'd/scheme-less forms; the convergence guarantee. |
| req-identity-core-issuer-id | [Deterministic Issuer Id](#deterministic-issuer-id) | Implemented | `oidc_issuer_id(raw)` over the canonical form; the sole id path. Namespace is the per-plugin `IDENTITY_CORE_NAMESPACE` (no repo-wide `TAP_NAMESPACE` constant exists; per-plugin is the convention). |
| req-identity-core-envelope | [Node Envelope Helper](#node-envelope-helper) | Implemented | `oidc_issuer_node_envelope(raw, *, dimensions=None)` returns the `{entity, node}` GRIFT fragment consumers merge. `display_name` param dropped — the spine projects `get_name()`=issuer_url, so a divergent name would be overwritten (honest v0 deviation). |
| req-identity-core-synthesis-general | [General-Case Synthesis](#general-case-synthesis) | Partial | Mechanism shipped (any observer *may* mint via the helper; github + samsite do). Order-independence (general-3) NOT fully realized in v0: aws_core has no enrichment phase, so the AWS-side TRUSTS_ISSUER link still relies on github's collector minting the singleton in the same run. |
| req-identity-core-existence-not-trust | [Existence Is Not Trust](#existence-is-not-trust) | Implemented | Node asserts reference/existence only; no trust field/default/edge. Trust is a separate explicit edge. |
| req-identity-core-edge-retargets | [Consumer Edge Retargets](#consumer-edge-retargets) | Implemented | github `ENABLED_ON` (source retargeted), aws_core `TRUSTS_ISSUER` (ownership moved from github + target retargeted), sigstore `IDENTITY_VOUCHED_BY` (target retargeted). identity_core owns none. |
| req-identity-core-dimensions | [Dimension Strategy](#dimension-strategy) | Implemented | `identity.protocol: oidc` on the model default. |
| req-identity-core-deps | [Dependency Direction](#dependency-direction) | Implemented | Downward-only; declared in github/aws_core/sigstore_core/samsite `pyproject.toml` + `depends_on`. Only github + samsite import the helper (code dep); aws + sigstore are edge/vocabulary deps. |
| req-identity-core-migration | [Extraction & Migration](#extraction--migration) | Implemented | `github_core__oidc_issuer` → `identity_core__oidc_issuer`; id regenerates (collected, not seeded); samsite→github import killed. Old model dropped via a forward github `0004` DeleteModel (not a lineage rewrite). |
| req-identity-core-nongoals | [v0 Non-Goals](#v0-non-goals) | Implemented | Passkey/subject/credential nodes; issuer-metadata fetch; liveness; trust policy; well-known name catalog — all held out of v0. |

### Plugin Scope
----
RID: `req-identity-core-scope`
Status: `Implemented`

`identity_core` is a **library / substrate** plugin. Its v0 surface is one model
(`oidc_issuer`) plus the issuer helper module (`identity_core.issuer`). It registers
its node type and dimensions at load; it ships **no collector** (`apps.py` is `pass`;
no `tap_cares` registration) and **owns no edge types**. Consumers import only from
`identity_core.*`. The plugin is install-only: it stands up the vocabulary and the
minting mechanism that github_core, aws_core, sigstore_core, and samsite call into.

### OIDC Issuer Model
----
RID: `req-identity-core-model`
Status: `Implemented`

`ENTITY_TYPE = "identity_core__oidc_issuer"`, `ENTITY_NAME = "OIDC Issuer"`,
`ENTITY_DESCRIPTION = "An OpenID Connect identity provider (issuer)."` The node is the
convergence point for federated identity: it is referenced by github (issuer enabled
on a repo), AWS (a provider trusts it), and Sigstore (an entry is vouched by it).

Fields (carried forward from the github_core original, minus the well-known-name map —
see non-goals):

- `issuer_url` — the OIDC `iss` as observed (scheme'd when available); display/reference value.
- `host` — the canonical, scheme-less form (`req-identity-core-canonical-url`); the identity key and the value AWS IAM's provider `url` matches.
- `provider` — optional free-text provider label (e.g. `github-actions`), observed, non-authoritative.
- `configuration` — optional observed OIDC discovery metadata (JSON; described sub-keys when populated).
- `tags` — optional observed labels (JSON).

`CREATE_REQUIRED = ["issuer_url"]`. `get_name()` returns `issuer_url` (honest: for an
issuer we have no friendlier universal label), or an explicitly supplied per-node
`display_name` when a consumer provides one. Display: the amber/gold identity-anchor
palette (distinct from github-blue, AWS-beige, sigstore-green) — the hub all three
reference. The node carries `DEFAULT_DIMENSIONS = {"identity.protocol": "oidc"}`.

### Canonical Issuer URL
----
RID: `req-identity-core-canonical-url`
Status: `Implemented`

`canonical_issuer_url(raw)` defines the **single** canonical form so independent
observers converge. It:

1. strips the scheme (`https://` / `http://`),
2. lowercases the host,
3. strips a trailing slash,
4. preserves any path (the `iss` may carry one).

The result (e.g. `token.actions.githubusercontent.com`) is the identity key. Both
github's scheme'd `iss` and AWS IAM's scheme-less provider `url` normalize to the same
value. This is the convergence guarantee: it lives in one function, not duplicated
across collectors. (Scheme is intentionally dropped from the *key* because AWS stores
none; the scheme'd `iss` is retained as the `issuer_url` display field.)

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-identity-core-canonical-url-1 | Scheme-spanning | Implemented | Scheme'd and scheme-less inputs for the same issuer normalize to one key. |
| req-identity-core-canonical-url-2 | Single definition | Implemented | Exactly one implementation; consumers call it, never re-implement normalization. |
| req-identity-core-canonical-url-3 | Path-preserving | Implemented | A path in the `iss` is preserved (issuers may carry one); only scheme/case/trailing-slash are normalized. |

### Deterministic Issuer Id
----
RID: `req-identity-core-issuer-id`
Status: `Implemented`

`oidc_issuer_id(raw) -> UUID` is `uuid5(TAP_NAMESPACE, "identity_core__oidc_issuer:" +
canonical_issuer_url(raw))`. It is the **only** sanctioned way to compute an issuer
entity id. No consumer may hardcode an id or re-derive it from a different string —
that is the collector-identity-fragility lesson (a type/string rename silently breaks
hardcoded uuid5s). Because the id keys on the canonical form, github and AWS produce
the same id and their nodes merge; because it is a pure function of the URL, the node
is idempotent across runs and observers.

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-identity-core-issuer-id-1 | Canonical-keyed | Implemented | Id derives from `canonical_issuer_url`, so scheme'd/scheme-less inputs give one id. |
| req-identity-core-issuer-id-2 | Sole path | Implemented | All consumers obtain the id from this helper; none hardcode or re-derive it. |
| req-identity-core-issuer-id-3 | Idempotent | Implemented | Repeated synthesis of the same issuer yields the same node; no duplicates. |

### Node Envelope Helper
----
RID: `req-identity-core-envelope`
Status: `Implemented`

`oidc_issuer_node_envelope(raw, *, dimensions=None, display_name=None)` returns a GRIFT
node fragment (entity id from `oidc_issuer_id`, `entity_type =
identity_core__oidc_issuer`, `issuer_url`/`host` populated from `raw` +
`canonical_issuer_url`) that a consumer merges into its own GRIFT batch. It is the
minting mechanism referenced by `req-identity-core-synthesis-general`. Consumers supply
their own dimensions/anchor context; the helper does not write to the grid itself
(no parallel mutation path — GRIFT flows through the caller's normal batch).

### General-Case Synthesis
----
RID: `req-identity-core-synthesis-general`
Status: `Partial`

Issuer nodes are synthesized **generally**, by any observer, never seeded. There is no
well-known-issuer catalog and no boot-time seed record for issuers. A collector that
encounters an issuer URL — github reading its Actions issuer, aws reading its IAM OIDC
provider `url`, samsite reading a verification policy's `oidc_issuer` — mints the node
via `oidc_issuer_node_envelope` and merges it. Convergence is automatic: all observers
of the same issuer produce the same id (`req-identity-core-issuer-id`) and merge.

The **mechanism** is fully in place: the helper is the single mint path and any observer
may call it. Two of the three observers do — github's collector mints the singleton, and
samsite's compliance collector mints from the verification policy's issuer, both through
the shared helper, and they converge by id. **aws does NOT mint in v0**: aws_core's boto3
collector is single-phase with no grid-link engine, so the AWS-side `TRUSTS_ISSUER` link
is still resolved by github_core's enrichment, which relies on github having minted the
issuer earlier in the same run. So the **run-order hazard is reduced but not eliminated**
in v0 — general-3 below is Deferred until aws_core grows its own issuer-minting (or an
enrichment phase). This is the honest state; the vocabulary now lives where aws *could*
mint from without reaching into github.

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-identity-core-synthesis-general-1 | No seed | Implemented | No boot record or seed data creates issuer instances; identity_core ships mechanism only. |
| req-identity-core-synthesis-general-2 | Any observer mints | Implemented | Every consumer that sees an issuer URL can synthesize the node via the helper; github + samsite do. |
| req-identity-core-synthesis-general-3 | Order-independent convergence | Deferred | NOT realized in v0: aws_core has no minting/enrichment path, so the AWS TRUSTS_ISSUER link still depends on github's same-run synthesis. Realized when aws mints the issuer from its own observation. |

### Existence Is Not Trust
----
RID: `req-identity-core-existence-not-trust`
Status: `Implemented`

The presence of an `oidc_issuer` node conveys only that an issuer identity was
referenced by some observer. It is **not** an assertion that the issuer exists in the
world, is reachable, or is trusted by anyone. Trust and relationship semantics live
exclusively on explicit edges owned by the asserting plugin (`TRUSTS_ISSUER`,
`IDENTITY_VOUCHED_BY`, `ENABLED_ON`). identity_core defines no trust field, no trust
default, and no trust edge. A consumer that wants to reason about trust must follow an
explicit trust edge, never infer it from node existence.

### Consumer Edge Retargets
----
RID: `req-identity-core-edge-retargets`
Status: `Implemented`

identity_core owns no edges. Each consumer retargets its issuer-touching edge to
`identity_core__oidc_issuer`, and edge *ownership* follows the principal that asserts
the relationship:

- **github_core — `ENABLED_ON`** (`oidc_issuer → github_repository`): stays in github; retarget the source type.
- **aws_core — `TRUSTS_ISSUER`** (`aws_iam_oidc_provider → oidc_issuer`): **ownership moves from github_core to aws_core** — it is an AWS→issuer fact — and retargets the target type. (This is the Tier-A "github_core independent of aws_core" move; slug becomes `TRUSTS_ISSUER__aws_core`.)
- **sigstore_core — `IDENTITY_VOUCHED_BY`** (and any other issuer-referencing sigstore edge, e.g. `ATTESTED_BY` where it anchors the issuer): stays in sigstore; retarget the target type.

Endpoint constraints on these edges reference `identity_core__oidc_issuer`; where an
edge should accept any workflow/source (Bucket-1 wildcard precedent), it stays wildcard.

### Dimension Strategy
----
RID: `req-identity-core-dimensions`
Status: `Implemented`

The model default dimension is `{"identity.protocol": "oidc"}`, establishing the
`identity.*` dimension namespace as the home for identity-vocabulary scoping. Future
identity node types (deferred, see non-goals) extend this namespace rather than
inventing sibling ones.

### Dependency Direction
----
RID: `req-identity-core-deps`
Status: `Implemented`

identity_core depends on nothing above core (`tap_grid`/`tap` only). Consumers depend
**downward** on it: `github_core`, `aws_core`, `sigstore_core`, and `samsite` declare
`tap-plugin-identity-core` in `pyproject.toml` and list `identity_core` in their
`depends_on`. The AST import-graph guard (`tap/plugin_deps.py`) enforces that the
`from tap_plugin.identity_core...` imports are declared. The `samsite →
github_core` issuer import is deleted in the same change (samsite imports
`identity_core.issuer` instead).

### Extraction & Migration
----
RID: `req-identity-core-migration`
Status: `Implemented`

The move renames `github_core__oidc_issuer` → `identity_core__oidc_issuer`. That
changes the `entity_type` string and therefore the `uuid5`-derived issuer id — but the
issuer node is **collected** (re-produced each run via the envelope helper), not a
static seed, so it regenerates cleanly on the next collection (contrast the
uuid5-hash-token-fallout that bit a *static seed*). Steps:

As-built steps:

1. Stood up `identity_core`: `OidcIssuer` model + `identity_core.issuer` helper module + `0001_initial`.
2. Moved the id/normalization/envelope logic into `identity_core.issuer` (`canonical_issuer_url` is new — it did not exist before; github keyed the id on the raw scheme'd URL, samsite host-normalized ad hoc). github's collector + samsite's `sigstore_link` now call the shared helper. `github_core.collectors.github_collector.identity.oidc_issuer_id` was removed.
3. Dropped `github_core/models/oidc_issuer.py` via a **forward** `github_core/0004` `DeleteModel` (the create-then-drop lineage is left intact rather than rewritten — standard, and migrations squash on eviction anyway). Updated `spec-github-core-v0.md` (7 models, 8 edges).
4. Retargeted consumer edges (`req-identity-core-edge-retargets`) and moved the `TRUSTS_ISSUER` type from github_core to aws_core. The `aws_oidc_provider_trusts_issuer` **enrichment rule stays in github's manifest** (edge types resolve globally, so github may emit an aws_core-owned type; aws_core has no enrichment engine to host the rule) — only its `edge_type`/`target_entity_type` strings + comment changed.
5. Replaced the `samsite → github_core` issuer import with `identity_core.issuer` (samsite's `sigstore_link` wrappers now delegate to it).
6. Updated the github enrichment rule's comment to the new architecture (issuer vocabulary in identity_core; github still mints the singleton in v0, so the same-run ordering note is honest, not obsolete — general-3 is Deferred).
7. Registered identity_core in `boot/test_all.boot.json` (install-only, ordered before its consumers).

Ordering: this is namespace churn (a new `entity_type`, a new edge owner), so it landed
**before eviction** freezes the plugins at released tags; otherwise the rename would have
become a coordinated multi-repo re-tag across identity_core + github + aws + sigstore +
samsite. (The evicted-tag demo profile `boot/samsite.boot.json` still references the old
world; it resyncs at plugin re-release, like the compliance_core extraction before it.)

### v0 Non-Goals
----
RID: `req-identity-core-nongoals`
Status: `Implemented`

Explicitly out of scope for v0:

- **Passkey / subject / credential identity nodes.** TAP does not model its own
  passkey/authenticator implementation on the grid in v0 (auth lives sub-grid). When
  such nodes are wanted, identity_core is their natural home and extends the
  `identity.*` namespace — but nothing is built for them now.
- **Issuer-metadata fetch / discovery.** No network call to `/.well-known/openid-configuration`; `configuration` is populated only from what a collector already observed.
- **Issuer liveness / reachability.** The node makes no claim the issuer is reachable.
- **Trust policy.** No trust fields, defaults, or edges (`req-identity-core-existence-not-trust`).
- **Well-known name catalog.** The github_core original hardcoded a
  `_WELL_KNOWN_NAMES` map (`token.actions.githubusercontent.com` → "GitHub Actions
  OIDC"). It is **dropped**: it is the same special-case-the-known-issuer pattern at the
  cosmetic layer, and it fails the "don't assume other issuers exist" test. The node's
  name is its `issuer_url` (or a consumer-supplied `display_name`), honest for every
  issuer including unknown ones.
