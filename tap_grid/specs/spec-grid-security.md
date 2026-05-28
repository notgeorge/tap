# Grid Security Specification

## Philosophy

Some security requirements in TAP are local to one subsystem, but others are platform-level contracts that higher-level functionality must inherit rather than redefine. These requirements belong close to the grid/platform layer so web, plugins, APIs, and future runtimes can reference one authoritative security baseline.

The first requirement in this specification addresses third-party vendored components checked into the TAP repository. Once external code is copied into TAP and shipped as part of the platform, TAP needs a consistent provenance and tracking contract rather than ad hoc comments or undocumented downloads.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Platform-Level | Define security contracts that apply across TAP subsystems rather than only one app |
| 2. | Traceable | Third-party vendored code and assets have explicit provenance and version tracking |
| 3. | Auditable | Humans and tooling can inspect what external components are present in TAP |
| 4. | Reusable | Higher-level specs such as web and plugins can delegate to one grid-level requirement |
| 5. | Evolvable | Lightweight manifest tracking today does not block later SPDX or CycloneDX adoption |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-thirdparty-manifest.sec | [Third-Party Component Manifest](#third-party-component-manifest) | Proposed | Platform-level contract for tracking third-party code and assets — both vendored in TAP source AND downloaded by the build process |
| req-grid-icon-static-svg.sec | [Static Svg Icon Security](#static-svg-icon-security) | Proposed | Security contract for shipped app/plugin SVG icons |
| req-grid-icon-upload-svg.sec | [Uploaded Svg Icon Security](#uploaded-svg-icon-security) | Backlog | Future security contract for user-uploaded SVG icons |
| req-grid-flip-write-batch.sec | [Domain Writes Must Use Batch Context](#domain-writes-must-use-batch-context) | Backlog | All domain object mutations must occur within an active batch context for auditability |

---

### Third-Party Component Manifest
----
RID: `req-grid-thirdparty-manifest.sec`
Status: `Proposed`
Tags: `Security`

Third-party code or assets shipped as part of a TAP runtime image must be tracked in a machine-readable manifest. This is a platform-level supply-chain security requirement: once a component is part of what TAP runs, its provenance, version, and license must not rely on memory, commit archaeology, or informal comments.

The contract covers two artifact-delivery modes:

- **Source-vendored components** — files committed under the owning app's static / vendor tree (browser libraries, CSS, copied Python code, etc.). Integrity is verified against the committed file at audit time.
- **Build-time-downloaded components** — artifacts pulled by the build process (a Dockerfile `RUN`, an installer script) that land inside the runtime image without entering source control (build tools, runtime binaries that are too large to vendor sensibly). Integrity is enforced at build time by verifying the downloaded artifact against a manifest-pinned checksum before installing.

Both modes use the same `third_party_manifest.toml` at the owning app's root, with `[[component]]` entries that share most of the same fields and diverge only on how the integrity hash is named and where the artifact lives.

#### Status Details
New cross-cutting security requirement proposed so subsystems such as `tap_web` can vendor browser libraries AND pin build-time-downloaded binaries (e.g. the `tailwindcss` CLI) under one TAP-wide manifest contract.

#### Implementation
- This requirement applies to third-party components shipped as part of a TAP runtime image, including:
  - JavaScript libraries
  - CSS libraries
  - front-end assets
  - copied Python code from external projects
  - other shipped third-party source artifacts
  - build-time-downloaded binaries (CLIs, tools) installed into the image at build time
- Each third-party component must have an entry in a machine-readable manifest maintained in the repository.
- The manifest is the canonical TAP record for component provenance.
- Each TAP app or plugin that ships third-party components maintains its own manifest file at the app root named `third_party_manifest.toml`.
- The canonical authoring format is TOML.
- The manifest must record, at minimum:
  - component name
  - version
  - local file path or file set (empty when the component is build-time-downloaded and not in source)
  - upstream source location
  - license identifier or license reference
  - integrity data — either a single `checksum_sha256` for source-vendored files OR per-platform `checksum_sha256_<os>_<arch>` keys for build-time-downloaded binaries
- The manifest uses one `[[component]]` entry per third-party component.
- Each `[[component]]` entry must define:
  - `name`
  - `version`
  - `files`
  - `source_url`
  - `license`
  - one of: `checksum_sha256` (source-vendored) OR one-or-more `checksum_sha256_<os>_<arch>` (build-time-downloaded)
- `files` is an array of repository-relative file paths. For build-time-downloaded components it is `[]`.
- `license` should use an SPDX license identifier when one exists; otherwise it must use a clear license reference string.
- `checksum_sha256` represents the integrity value of the committed file set.
- `checksum_sha256_<os>_<arch>` keys (one per supported platform variant) capture the integrity hash of the corresponding upstream release artifact. The build step that downloads each variant MUST compute its SHA-256 and compare against the manifest-pinned value before installing; mismatch MUST abort the build (`req-grid-thirdparty-manifest.sec-10`). Platform suffixes use the convention `<os>_<arch>` with underscores (e.g. `linux_x64`, `linux_arm64`, `macos_arm64`) so the key is a valid bare TOML identifier and grep-friendly.
- `version` should record the upstream component version. If a legacy vendored artifact does not expose a determinable version, `version = "unknown"` may be used temporarily until provenance is cleaned up.
- SPDX or CycloneDX may be generated from the canonical manifest later, but they are not required as the hand-authored source format in v1.
- Higher-level TAP subsystems that ship third-party components must comply with this requirement rather than define incompatible local tracking formats.

Canonical TOML shape — **source-vendored** variant (committed files):

```toml
[[component]]
name = "tabulator"
version = "6.3.0"
files = [
  "tap_web/static/tap_web/js/lib/tabulator.min.js",
  "tap_web/static/tap_web/css/lib/tabulator.min.css",
]
source_url = "https://github.com/olifolkerd/tabulator/releases/tag/6.3.0"
license = "MIT"
checksum_sha256 = "..."
```

Canonical TOML shape — **build-time-downloaded** variant (binary installed into the image by the Dockerfile):

```toml
[[component]]
name = "tailwindcss"
version = "3.4.17"
# Build-time CLI binary. The Dockerfile downloads the per-arch release
# from source_url at image build, verifies its SHA-256 against the
# matching checksum_sha256_<os>_<arch> below, and installs to
# /usr/local/bin/tailwindcss. Nothing is committed to source.
files = []
source_url = "https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.17"
license = "MIT"
checksum_sha256_linux_x64 = "..."
checksum_sha256_linux_arm64 = "..."
```

#### Development
Keep the first requirement focused on provenance and auditability, not full vulnerability management. The immediate problem is knowing what third-party code is present in the repo, where it came from, and what version and license it carries.

This requirement is intentionally broader than browser JavaScript. If TAP defines the contract only for `js/lib/`, the same problem will reappear for vendored CSS, copied Python helpers, or other embedded third-party assets.

Keep the manifest intentionally small and hand-maintainable. It should be realistic for contributors to update when vendoring one library, while still being strict enough for future validation tooling.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-thirdparty-manifest.sec-1 | Machine-Readable Manifest Required | Proposed | Third-party components shipped in a TAP runtime image must be represented in a machine-readable manifest, regardless of whether they are vendored in source or downloaded at build time. | |
| req-grid-thirdparty-manifest.sec-2 | Canonical Location And Format | Proposed | Each app or plugin that ships third-party components keeps a `third_party_manifest.toml` file at its own root and uses TOML as the authoring format. | |
| req-grid-thirdparty-manifest.sec-3 | Minimum Provenance Fields | Proposed | Manifest entries record name, version, repository-relative files (empty for build-time-downloaded), upstream source, license, and integrity data. | |
| req-grid-thirdparty-manifest.sec-4 | Fixed Component Entry Shape | Proposed | Each component is represented by one `[[component]]` TOML entry using the required canonical keys for the appropriate delivery mode. | |
| req-grid-thirdparty-manifest.sec-5 | Temporary Unknown Version Escape Hatch | Proposed | Legacy vendored artifacts may use `version = "unknown"` only when a concrete upstream version cannot currently be determined. | |
| req-grid-thirdparty-manifest.sec-6 | Platform-Level Contract | Proposed | Higher-level TAP subsystems that ship third-party components adhere to this grid-level requirement instead of inventing incompatible local rules. | |
| req-grid-thirdparty-manifest.sec-7 | Not Limited To JavaScript | Proposed | The requirement applies to all third-party components shipped in TAP runtime images, not only browser libraries. | |
| req-grid-thirdparty-manifest.sec-8 | SPDX Or CycloneDX Compatible Future | Proposed | TAP may later generate SPDX or CycloneDX artifacts from the canonical manifest without changing the core requirement. | |
| req-grid-thirdparty-manifest.sec-9 | Build-Time-Downloaded Components Recorded | Proposed | Components downloaded by the build process (not committed to source) MUST still appear in the manifest with `files = []`, per-platform `checksum_sha256_<os>_<arch>` keys for each supported variant, and the same name/version/source_url/license fields as source-vendored entries. | |
| req-grid-thirdparty-manifest.sec-10 | Build-Time Integrity Verification | Proposed | The build step that installs a build-time-downloaded component MUST compute the SHA-256 of the downloaded artifact and compare against the manifest-pinned `checksum_sha256_<os>_<arch>` for the platform it is installing, aborting the build on mismatch. | The manifest is the single source of truth for the expected hash; build scripts read from it rather than carrying duplicate hardcoded values. |

#### Future
- Add tooling to validate that vendored files and manifest entries stay in sync.
- Consider SBOM export generation in SPDX and/or CycloneDX format.
- Consider attaching vulnerability scanning and license-policy enforcement to manifest entries.

---

### Static Svg Icon Security
----
RID: `req-grid-icon-static-svg.sec`
Status: `Proposed`
Tags: `Security`

Shipped TAP SVG icons are safer than arbitrary user-supplied SVG content, but they still require a clear security contract because SVG is an XML-based format that can carry active or unsafe constructs. Static SVG icons must be constrained to trusted app/plugin assets and rendered through a narrow image-oriented path.

#### Status Details
New cross-cutting security requirement proposed to support the grid icon specification while keeping the threat model explicit.

#### Implementation
- This requirement applies to shipped static SVG icons owned by TAP apps and plugins.
- Static SVG icons must resolve only from validated app/plugin static icon directories defined by the icon specification.
- Static SVG icons must not be loaded from remote URLs.
- V1 static SVG icons should be rendered as image assets rather than inline executable markup.
- Static icon consumers must not require arbitrary raw SVG markup injection to render an icon.
- Validation must reject icon path traversal outside the owning app/plugin icon directory.

This requirement exists because SVG can carry:
- script elements
- event handler attributes
- embedded foreign content
- external references
- unexpectedly expensive rendering payloads

Keeping shipped icons as trusted static assets referenced through constrained image-style rendering significantly narrows the risk surface.

#### Development
This requirement does not claim that every shipped SVG has been sanitized. Its purpose is to constrain lookup, source, and rendering behavior so TAP does not accidentally widen the SVG attack surface by treating icons as arbitrary markup.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-icon-static-svg.sec-1 | Trusted Static Source Only | Proposed | Shipped SVG icons resolve only from validated app/plugin static icon directories. | |
| req-grid-icon-static-svg.sec-2 | No Remote Icon Sources | Proposed | Static SVG icon resolution rejects remote URLs and other non-local sources. | |
| req-grid-icon-static-svg.sec-3 | Constrained Rendering Path | Proposed | V1 static SVG icons are rendered as image assets rather than inline arbitrary SVG markup. | |
| req-grid-icon-static-svg.sec-4 | Path Traversal Rejected | Proposed | Icon path validation rejects traversal outside the owning app/plugin icon directory. | |

#### Future
If TAP later allows richer SVG rendering modes, define separate hardening rules for those modes rather than silently broadening this requirement.

---

### Uploaded Svg Icon Security
----
RID: `req-grid-icon-upload-svg.sec`
Status: `Backlog`
Tags: `Security`

User-uploaded SVG icons are a distinct security surface and require stricter controls than shipped static app/plugin icons. Even if early rendering uses only image-style embedding, TAP should not accept arbitrary uploaded SVGs without a dedicated sanitization and publication contract.

#### Status Details
Backlog security requirement created now so future user-uploaded icon support does not silently inherit the looser trust assumptions used for shipped static icons.

#### Implementation
Future work must define:
- sanitization of uploaded SVG content before storage or publication
- stripping or rejecting active content such as scripts, event handlers, `foreignObject`, unsafe CSS, and external references
- behavior when sanitization fails
- storage and serving rules for uploaded SVGs
- approved rendering modes for uploaded SVGs
- file size and complexity limits to reduce denial-of-service or rendering abuse risks

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-icon-upload-svg.sec-1 | Uploaded Svg Security Requirement Exists | Backlog | TAP tracks a dedicated security requirement for user-uploaded SVG icons. | |
| req-grid-icon-upload-svg.sec-2 | Sanitization Required Before Publication | Backlog | Future uploaded SVG support must sanitize or reject unsafe SVG content before publication. | |
| req-grid-icon-upload-svg.sec-3 | External References Controlled | Backlog | Future uploaded SVG support must strip or reject remote references and other unsafe linked resources. | |
| req-grid-icon-upload-svg.sec-4 | Rendering Contract Explicit | Backlog | Future uploaded SVG support must define and constrain allowed rendering modes explicitly. | |

#### Future
Define the upload pipeline, sanitization toolchain, and storage/publication model once user-uploaded icons become an active product feature.

---

### Domain Writes Must Use Batch Context
----
RID: `req-grid-flip-write-batch.sec`
Status: `Backlog`
Tags: `Security`, `FLIP`

All mutations to domain objects (BaseModel subclasses) must occur within an active batch context so that every change is attributable to a known operational unit with actor, source, and timing metadata.

#### Status Details
Partially enforced: FLIP-enabled models already raise `NoBatchContextError` if saved without a batch context. The remaining gap is that models without FLIP enabled can still be saved without a batch, bypassing provenance entirely.

#### Implementation
The full enforcement requires:

1. A `pre_save` hook (signal or ORM override) that checks for an active batch context before any `BaseModel` save.
2. An explicit opt-out mechanism for legitimate batch-free writes such as migrations, fixtures, and one-time setup commands.
3. Audit tooling to detect and flag writes that bypass the batch contract.

#### Development
A codebase audit is needed to identify all current write paths that operate outside batch context and either wrap them in `batch_context()` or formally exempt them. Until full enforcement is in place, FLIP-enabled models provide the strongest guarantee.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-flip-write-batch.sec-1 | FLIP Models Enforce Batch | Backlog | FLIP-enabled models raise NoBatchContextError when saved without an active batch context. | Already implemented |
| req-grid-flip-write-batch.sec-2 | All BaseModel Writes Require Batch | Backlog | A pre-save gate prevents any BaseModel subclass from being saved without a batch context, regardless of FLIP enablement. | Requires codebase audit first |
| req-grid-flip-write-batch.sec-3 | Exemption Mechanism Exists | Backlog | Legitimate batch-free writes (migrations, fixtures, setup) have an explicit, auditable opt-out rather than silently bypassing the gate. | |
| req-grid-flip-write-batch.sec-4 | Codebase Audit Complete | Backlog | All existing write paths have been reviewed and either wrapped in batch_context() or formally exempted. | |

#### Future
Once the batch gate is in place, TAP may add monitoring or alerting for writes that use the exemption path in production.

---

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: `...``
`Status: `...``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
