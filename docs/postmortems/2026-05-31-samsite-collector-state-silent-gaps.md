---
id: pm-2026-05-31-samsite-collector-state-silent-gaps
date: 2026-05-31
title: Samsite landing page silently incomplete — collector-harvested state missing
status: resolved
severity: medium
tags:
  - seed-data-integrity
  - collector-dependency
  - runtime-issue
  - silent-failure
  - frontend-ux
  - dev-tooling
failure_class: >
  A missing upstream dependency produces a silently-incomplete result that is
  indistinguishable from a correct one. No error is raised; the artifact simply
  has less in it than it should, and nothing on the artifact says so.
surfaces:
  - scripts/spawn-session.sh
  - boot/samsite.json
  - plugins/samsite/grift/landing.grift.json
  - plugins/samsite/collectors/compliance_collector/sigstore_link.py
  - tap_grid/grift/importer.py
fix_commits:
  - ec8339f      # remove 4 orphan edges left by the bootstrap-layout retirement
  - this-commit  # boot-profile note + sigstore_link visibility logging + this write-up (a commit cannot embed its own final hash)
related:
  - specs/spec-grid-import-grift.md
  - specs/spec-dev-boot-collectors.md
---

# Samsite landing page silently incomplete — collector-harvested state missing

## Summary

The samsite landing diagram on a freshly-spawned session (`newstart`, :8080)
rendered visibly different from an older session (`nitpick`, :8070): it was
missing the entire GitHub lane (`github.com → notgeorge/samsite`, the workflow
nodes, Dependabot) and, after the lane was restored, still missing the
`SIGNED_BY_IDENTITY` / `REQUESTS_SIGSTORE_SIGNATURE` edges from the Deploy
Website workflow to Sigstore.

Neither symptom was a rendering bug or a seed-data difference — the seed bundles
were byte-identical between the two sessions. Both were **absent
collector-harvested state**, caused by two independent triggers that share one
failure shape: a missing upstream dependency yielding a silently-incomplete
result. No error was ever raised on the rendered page.

## Timeline

1. Earlier session: `spawn-session.sh` for `newstart` failed during Step 6 (GRIFT
   seed import) with `CommandError: Completed with 1 error(s)` — the samsite
   `landing` bundle had 4 `dangling_edge` issues. Root-caused to 4 orphan edges
   left behind when `samsite-bootstrap-layout` + its 3 arrangements were retired
   (commit 43f0cd8): the node defs were dropped and the nodes tombstoned, but the
   `USES_LAYOUT` / `USES_ARRANGEMENT` edges into them were never removed. Fixed
   by removing the orphan edges (commit `ec8339f`).
2. 2026-05-31: comparing the two rendered landing pages, `newstart` was missing
   the GitHub lane entirely. Grid census: `newstart` 1380 live nodes vs `nitpick`
   1638 — the gap was ~42 `github_*` nodes (+ ~94 edges) plus extra
   `compliance_artifact` / `collection_job` accumulation.
3. The GitHub nodes are **harvested live by the `github_core` collector**, not
   seeded by any GRIFT bundle; `landing.grift.json` only *projects* them via
   `MATCH (gapp:github_app)` and workflow MATCHes. On a grid where the collector
   never ran, those MATCHes return nothing and the lane silently vanishes.
4. Manually running the collectors restored the lane — but the
   `SIGNED_BY_IDENTITY` / `REQUESTS_SIGSTORE_SIGNATURE` edges were still 0,
   because the collectors had been run **compliance-before-github**, and
   `sigstore_link` resolves the signing identity by content-matching an existing
   `github_workflow` node. Re-running in boot order (`boto3 → github → ksi →
   compliance`) wired the edges.

## Root causes

### RC1 — Orphan-edge seed self-contradiction, and its blast radius

The `landing` bundle contained 4 edges pointing at nodes the same retirement had
dropped + tombstoned. On a *warm* grid this is masked: the dangling check
(`importer.py`, `Entity.objects.filter(pk=...).exists()`) is satisfied by the
tombstoned rows (`Entity.objects` returns live + tombstoned by default). Only a
*cold* seed exposes it, where the import runs `dangling_edge_mode="warn"` but the
overall command still exits non-zero on the issue count.

**Blast radius (the under-weighted part):** `spawn-session.sh` runs under
`set -euo pipefail`, with Step 6 `import_plugin_grift --all` *upstream* of Step
6.5 `fire_boot_collectors`. The non-zero exit aborted the entire spawn before the
boot-collector phase. So 4 dangling edges did not cost "4 edges" — they cost the
**entire collector-population phase**: the session came up with no `github_*`
nodes, no fresh AWS/compliance state, just the hand-authored seed.

### RC2 — Undocumented collector ordering dependency

`samsite-compliance` depends on `github_core` having run first:
`sigstore_link.resolve_workflow_entity_id` does a Gryphon content-match
(`MATCH (w:github_workflow) WHERE w.data.full_name=$fn AND w.data.path=$path`)
and, on zero matches, **deliberately omits** the signing-identity edges rather
than guess. The boot profile's declared order satisfies this, but its note only
documented the `boto3` dependency (for `SCOPED_TO_BOUNDARY`), not the
`github_core` one — so running the collectors by hand out of order silently
dropped the edges with no hint why.

## The unifying failure class

Three manifestations, one shape — **missing upstream dependency → silently
incomplete result, indistinguishable from correct:**

| Manifestation | Missing upstream | Silent result |
|---|---|---|
| Spawn aborted at seed | boot-collector phase skipped (RC1 blast radius) | session populated with seed only; no error visible later |
| GitHub lane absent | `github_core` collector never ran | landing MATCH returns ∅; lane just not drawn |
| Signing edges absent | `github_workflow` node not yet on grid (RC2) | `sigstore_link` omits edge; same as "artifact unsigned" |

In every case the consumer did the locally-correct thing (don't seed a dangling
edge / don't render a node that isn't there / don't guess a signing identity),
and the *aggregate* outcome was a quietly degraded instance with nothing
asserting "this is incomplete."

## Detection gaps

- **No DB-free file-structural lint for GRIFT self-contradiction.**
  `validate_grift_document()` is schema-only; the one semantic edge check
  (dangling) is DB-bound and warm-DB-maskable. An edge-create whose endpoint is
  deleted/absent *within the same document* is deterministically detectable from
  the file alone — and isn't checked. (Backlog: `spec-grid-import-grift.md`.)
- **Boot ordering rationale under-documented.** The profile order was correct;
  the *why* (compliance-after-github) was not written down, so a manual
  out-of-order run had no guardrail.
- **`sigstore_link` omitted edges with no log.** "No workflow matched" was
  indistinguishable from "artifact genuinely unsigned."

## Fixes applied

- `ec8339f` — removed the 4 orphan edges from `landing.grift.json`; future cold
  spawns pass Step 6 and reach Step 6.5.
- `boot/samsite.json` — profile description + `samsite-compliance` note now
  document the `github_core` dependency (resolve-signing-workflow) alongside the
  `boto3` one, and state that out-of-order runs silently drop the edges.
- `sigstore_link.py` — `logger.info` (`[3e92]`) when no workflow matches (the
  ordering case) and `logger.warning` (`[5b05]`) on ambiguous multi-match, so
  the omission is visible.
- Operational repair of the `newstart` grid: re-ran `fire_boot_collectors` in
  order; `SIGNED_BY_IDENTITY` 5, `REQUESTS_SIGSTORE_SIGNATURE` 1, `GENERATES_FILE`
  5 now present; landing page matches `nitpick`.

## What Paladin would need

The healer-relevant generalization of each manifestation — the observable signal
and the safe remediation:

- **Seed-vs-spawn integrity.** Signal: a spawn that aborted at the seed step, or
  a grid whose `collection_job` history is empty for profile-declared collectors.
  Remediation (safe, idempotent): re-run `fire_boot_collectors` for the grid's
  boot profile. Detect the *self-contradiction* upstream with a DB-free GRIFT
  lint so the abort never happens.
- **Projection completeness.** Signal: a landing/elevation projection whose
  `MATCH` clauses reference node types with zero live instances on the grid (the
  lane "should" exist per the projection but the source nodes are absent).
  Remediation: identify the collector that owns that node type and check whether
  it has ever run; re-run or escalate. The deeper fix is a projection that can
  *declare* "this lane requires collector X" and render a visible
  "collector-not-run" placeholder instead of silently empty space.
- **Derived-edge dependency satisfaction.** Signal: a collector run that resolved
  zero targets for a content-match it expected to resolve (now loggable via
  `[3e92]`). Remediation: re-run the dependency collector, then the dependent one
  — i.e. Paladin needs a model of inter-collector dependencies (a DAG) so it can
  re-run in topological order rather than whatever order a human typed.

The throughline Paladin must internalize: **silent incompleteness is the
default failure mode of a graph assembled from independent producers.** Health
is not "no errors" — it is "every declared dependency was satisfied, and every
gap is disclosed on the artifact." (Mirrors the `disclose-shortcuts-machine-
readably` producer rule and its `consumer-side-disclosure-complement`.)
