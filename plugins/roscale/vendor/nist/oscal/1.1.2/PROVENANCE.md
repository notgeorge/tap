# OSCAL 1.1.2 Vendor Provenance

This directory holds vendored official OSCAL `1.1.2` JSON Schemas published by NIST. No upstream parser implementation code is vendored or copied — only schemas. See [`plugins/roscale/specs/spec-roscale-v0.md`](../../../../specs/spec-roscale-v0.md) (`req-roscale-vendor`) for the boundary.

## Upstream

- **Repository:** <https://github.com/usnistgov/OSCAL>
- **Release tag:** `v1.1.2`
- **Release page:** <https://github.com/usnistgov/OSCAL/releases/tag/v1.1.2>
- **Fetch date:** 2026-05-26
- **License / source status:** NIST OSCAL is a US Government work in the public domain (per `LICENSE.md` in the upstream repo, citing 17 USC §105). Vendoring is license-clean; provenance retained here.

## Files vendored

All eight official JSON Schemas from the v1.1.2 release. Per-document schemas plus the combined schema.

| File | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `schemas/oscal_assessment-plan_schema.json` | 126071 | `43464ad048b711c735934b66015bcf8239782c6263d377a742c6b205ea796ecb` |
| `schemas/oscal_assessment-results_schema.json` | 133015 | `d033da70154cf6625ae46a746199e88e58f2928b1387dfac051d381b92f41b0d` |
| `schemas/oscal_catalog_schema.json` | 43204 | `5b069afa4f4ecc38d59914dab56098566d4247d3578a2123c030c80d36fc5104` |
| `schemas/oscal_complete_schema.json` | 216673 | `f0b24aef59190cb2649b404976f1677b546e6bb1982597d8bccb9e6b1244e18c` |
| `schemas/oscal_component_schema.json` | 67640 | `7b74710940ad39b6b63d4ddccbadf2c7d2e9bf11b07808d41d2aa27a4616e5ce` |
| `schemas/oscal_poam_schema.json` | 129396 | `906725163d767036c6189aec51252109b203214e121fc1acaff494b4d2dfbc04` |
| `schemas/oscal_profile_schema.json` | 53876 | `c910ea1a852e9d4ccfb7f6a8d0898b0cd4f137e48f88886412a083c8d87d540a` |
| `schemas/oscal_ssp_schema.json` | 92768 | `08d3faeb12f0fab7705dec15fb648c72400c7ab6ac0056222d49d21507e02a69` |

Each file is the verbatim release artifact. To re-verify against upstream:

```bash
curl -sLO https://github.com/usnistgov/OSCAL/releases/download/v1.1.2/oscal_ssp_schema.json
shasum -a 256 oscal_ssp_schema.json
```

## What is not vendored

- Metaschema XML (`*_metaschema_RESOLVED.xml`), XSD schemas, and XSL converters from the same release — ROSCALE works with JSON only in v0.
- OSCAL content examples from `usnistgov/oscal-content`. The Samsite OSCAL SSP and POA&M fixtures (collected by the samsite plugin) are the primary fixtures; public examples may be added later under `examples/` if needed.
- Any upstream Python/Java/etc. parser implementation code. Per `req-roscale-vendor-6`, ROSCALE's parser is TAP-authored.

## Refreshing for a new OSCAL version

When OSCAL releases a new minor/patch version:

1. Create a sibling directory at `vendor/nist/oscal/<new-version>/schemas/`.
2. Re-fetch the eight schemas from the new release tag's URL pattern.
3. Update this provenance file (new SHA-256s, new fetch date, new release tag).
4. Bump `req-roscale-validation` / `req-roscale-vendor` notes in the spec if shape changed materially.
5. Old vendored versions stay until validation against the new version has soaked.
