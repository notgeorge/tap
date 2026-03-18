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
| req-grid-thirdparty-manifest.sec | [Third-Party Vendored Component Manifest](#third-party-vendored-component-manifest) | Proposed | Platform-level contract for tracking vendored third-party code and assets included in TAP source |

---

### Third-Party Vendored Component Manifest
----
RID: `req-grid-thirdparty-manifest.sec`
Status: `Proposed`
Tags: `Security`

Third-party code or assets vendored into TAP source control must be tracked in a machine-readable manifest. This is a platform-level supply-chain security requirement: once code is copied into the repository and shipped by TAP, its provenance, version, and license must not rely on memory, commit archaeology, or informal comments.

#### Status Details
New cross-cutting security requirement proposed so subsystems such as `tap_web` can vendor browser libraries while still adhering to one TAP-wide manifest contract.

#### Implementation
- This requirement applies to vendored third-party components stored in TAP source control, including:
  - JavaScript libraries
  - CSS libraries
  - front-end assets
  - copied Python code from external projects
  - other shipped third-party source artifacts
- Each vendored third-party component must have an entry in a machine-readable manifest maintained in the repository.
- The manifest is the canonical TAP record for vendored component provenance.
- Each TAP app or plugin that vendors third-party components maintains its own manifest file at the app root named `third_party_manifest.toml`.
- The canonical authoring format is TOML.
- The manifest must record, at minimum:
  - component name
  - version
  - local file path or file set
  - upstream source location
  - license identifier or license reference
  - integrity data such as checksum for the vendored file set
- The manifest uses one `[[component]]` entry per vendored third-party component.
- Each `[[component]]` entry must define:
  - `name`
  - `version`
  - `files`
  - `source_url`
  - `license`
  - `checksum_sha256`
- `files` is an array of repository-relative file paths.
- `license` should use an SPDX license identifier when one exists; otherwise it must use a clear license reference string.
- `checksum_sha256` represents the integrity value recorded for the vendored component as defined by implementation guidance.
- `version` should record the upstream component version. If a legacy vendored artifact does not expose a determinable version, `version = "unknown"` may be used temporarily until provenance is cleaned up.
- SPDX or CycloneDX may be generated from the canonical manifest later, but they are not required as the hand-authored source format in v1.
- Higher-level TAP subsystems that vendor third-party components must comply with this requirement rather than define incompatible local tracking formats.

Canonical TOML shape:

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

#### Development
Keep the first requirement focused on provenance and auditability, not full vulnerability management. The immediate problem is knowing what third-party code is present in the repo, where it came from, and what version and license it carries.

This requirement is intentionally broader than browser JavaScript. If TAP defines the contract only for `js/lib/`, the same problem will reappear for vendored CSS, copied Python helpers, or other embedded third-party assets.

Keep the manifest intentionally small and hand-maintainable. It should be realistic for contributors to update when vendoring one library, while still being strict enough for future validation tooling.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-thirdparty-manifest.sec-1 | Machine-Readable Manifest Required | Proposed | Vendored third-party components checked into TAP source control must be represented in a machine-readable manifest. | |
| req-grid-thirdparty-manifest.sec-2 | Canonical Location And Format | Proposed | Each app or plugin that vendors third-party components keeps a `third_party_manifest.toml` file at its own root and uses TOML as the authoring format. | |
| req-grid-thirdparty-manifest.sec-3 | Minimum Provenance Fields | Proposed | Manifest entries record name, version, repository-relative files, upstream source, license, and integrity data. | |
| req-grid-thirdparty-manifest.sec-4 | Fixed Component Entry Shape | Proposed | Each vendored component is represented by one `[[component]]` TOML entry using the required canonical keys. | |
| req-grid-thirdparty-manifest.sec-5 | Temporary Unknown Version Escape Hatch | Proposed | Legacy vendored artifacts may use `version = "unknown"` only when a concrete upstream version cannot currently be determined. | |
| req-grid-thirdparty-manifest.sec-6 | Platform-Level Contract | Proposed | Higher-level TAP subsystems that vendor third-party components adhere to this grid-level requirement instead of inventing incompatible local rules. | |
| req-grid-thirdparty-manifest.sec-7 | Not Limited To JavaScript | Proposed | The requirement applies to all vendored third-party components shipped in TAP source, not only browser libraries. | |
| req-grid-thirdparty-manifest.sec-8 | SPDX Or CycloneDX Compatible Future | Proposed | TAP may later generate SPDX or CycloneDX artifacts from the canonical manifest without changing the core requirement. | |

#### Future
- Add tooling to validate that vendored files and manifest entries stay in sync.
- Consider SBOM export generation in SPDX and/or CycloneDX format.
- Consider attaching vulnerability scanning and license-policy enforcement to manifest entries.

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
