---
title: The Guard & Validation-Surface System
spec: specs/spec-dev-validation.md
audience:
  - developer
  - llm
covers:
  - req-dev-validation-map
  - req-dev-validation-map-2
  - req-dev-validation-ratchet-harness
  - req-dev-validation-known-broken-5
  - req-tap-callsite-identity-remediation-unit
  - req-tap-auth-policy-9
update-triggers:
  - A new guard *mechanism* or base class is added (something beyond hard-lint / CeilingRatchet / CallsiteRatchet)
  - The honesty vocabulary changes — a new `cadence` or `status` label enters the Map
  - A new *category* of declared surface appears in `tap/guards/surfaces.py`
  - The shared machinery moves (the file map in "Where the mechanics live" goes stale)
  - Guard discovery, the honesty meta-tests, or the Map generation changes shape
assumes:
  - Reader is adding, reviewing, or reasoning about a build/CI-time check in TAP
  - Reader will consult `spec-dev-validation.md` for exact requirements — this is the doctrine/orientation layer over it, not a restatement
provides: |
  The mental model for TAP's validation system: what a "surface" is, the two kinds
  of surface (auto-discovered guards vs. hand-listed declared surfaces), the two
  guard mechanisms (hard lint vs. ratchet), the honesty vocabulary (cadence +
  status), the shared machinery, and how to add a guard or a surface. After reading,
  you can place any entry in `manage.py guards --map`, choose the right shape for a
  new check, and know which files it touches.
status: reference
---

# The Guard & Validation-Surface System

> Owning spec: [`specs/spec-dev-validation.md`](../specs/spec-dev-validation.md) — the governing spec and system of record. This doc is the orientation layer over it; the spec's requirements and the **generated** Validation Map are authoritative where they differ.

## The one idea: an honest inventory of what TAP enforces

Everything in this system exists to answer one question truthfully: **what invariants does TAP enforce — how, when, and where are the gaps?** The answer is a single generated table, the **Validation Map** (`manage.py guards --map`).

The governing rule (`req-dev-validation-map-2`, *honest guard status*) is that **gaps must be visible, not hidden behind a green checkmark**. A rule that is not enforced yet still appears on the Map, labeled `Named, deferred`. That honesty is the point — the Map is the system of record, and the design does not let a green CI run imply coverage that does not exist.

## "Surface" = any place an invariant is validated

A **validation surface** is the general concept: *anything that checks a rule about the system.* Deliberately broad — a surface can be a static lint, a runtime backstop, a behavioral test, a CI lane, a pre-push gate, or a written-down manual procedure. "Surface" is the umbrella noun; "guard" is one specific kind of surface. The Map inventories every surface, whatever its form.

## Two kinds of surface

**Guards — the self-describing kind.** A guard is a `Guard` subclass (in `tap/guards/` or any `<app>/guards/`) that carries its own metadata — `slug`, `map_row`, `rid`, `cadence`, `description` — and a `check()` method. `tap/tests/test_guards.py` **auto-discovers** every guard by walking the filesystem and runs each `check()` as its own parametrized case. Because a guard *is* code that describes itself, its Map row is **generated** — it cannot drift. Drop a new module in a `guards/` folder and it appears; there is no registry to edit.

**Declared surfaces — the negative space.** Things that validate but are *not* `Guard` subclasses: runtime backstops, tests that need a live DB or render, the cold-boot gate, the CI lanes, and deliberately-manual or not-yet-built procedures. They cannot self-describe, so they are **hand-listed** in [`tap/guards/surfaces.py`](../tap/guards/surfaces.py) — because a Map showing only the auto-guards would silently erase every gap. Adding one is a reviewable decision.

**The Map is the union of the two.** Both guards and declared surfaces carry a `rid` that is machine-checked to resolve to a real requirement in some spec, so nothing on the Map points at a fiction.

## How a guard works

Every guard's `check()` asserts an invariant and raises `AssertionError` (or a subclass) on violation. Three meta-tests in `test_guards.py` keep the *system itself* honest:

1. every guard's `rid` must resolve to a requirement actually **defined** in a spec (an `RID:` heading or a requirements-table cell — an inline reference does not count) — no guard pointing at a made-up rule;
2. every guard must carry a non-trivial `description` saying why it exists;
3. the committed Map must equal the freshly-generated Map — the two cannot drift.

## Guards come in two mechanisms

This is the distinction worth internalizing when you build one.

**Hard lints — pass / fail, zero tolerance.** `check()` fails if *any* violation exists. Use when there is no legitimate existing offender to grandfather. Examples: the credential-bind provenance guard, the dev-passkey-import containment guard, secret-leak, JSON-naming.

**Ratchets — a baseline that only shrinks toward zero.** A `CeilingRatchet` compares a freshly-measured set against a committed **baseline file**: a *new* violation fails the build; pre-existing debt is frozen (grandfathered) and allowed only to shrink. Use when you have debt you cannot fix all at once but must stop growing. Examples: direct-write coverage, authz coverage, the log-site-token scanners, and mypy (a large frozen error set that ratchets down as files are cleaned). A sub-kind, `CallsiteRatchet`, gives each finding a **drift-proof identity** — an anchor built from `path::qualname::construct`, never a line number (`req-tap-callsite-identity-remediation-unit`) — so the baseline does not churn when unrelated edits move code, and findings can export to SARIF for GitHub code-scanning.

The whole type hierarchy:

```
Validation surface                     — anything that checks a rule
├── Guard                              — self-describing, auto-discovered, run by test_guards.py
│   ├── Hard-lint Guard                — pass / fail, no tolerance
│   └── CeilingRatchet                 — measured set ≤ frozen baseline (ratchets to zero)
│       └── CallsiteRatchet            — drift-proof per-offense identity → SARIF
└── DeclaredSurface                    — hand-listed in tap/guards/surfaces.py
```

## The honesty vocabulary

Two columns on the Map carry the truth. **Cadence** says *when* a surface runs. **Status** says *how honestly guarded* it is. The crux is that a rule can sit on the Map *without being enforced yet* — that is honest precisely because it is visible.

| Status | Meaning |
| --- | --- |
| `CI-guarded` | Runs on every commit via `pytest` (the default for harness guards). |
| `Gate-guarded` | Enforced at the pre-push / promote gate (`scripts/gate`, `promote-to-main.sh`). |
| `Manual (CI-unguarded by design)` | A real check, deliberately run by hand (e.g. a multi-hour instrumented run, a per-spawn procedure). |
| `Named, deferred` | Acknowledged and on the Map, but not yet built. |

Cadence values follow the same vocabulary: `Per-commit (pytest)`, `Pre-push (gate)`, `Per-spawn`, on-demand script, or `Deferred`.

## The landscape, by intent

The ~40 surfaces group into a handful of intents. **The authoritative, live list is `manage.py guards --map`** — do not hardcode it here, it is generated and would drift. The intents, with a few exemplars each:

- **Auth & mutation integrity** — *every graph mutation and identity bind goes through a sanctioned, gated path.* Authz coverage, direct-write coverage (+ exemption freshness), credential-bind provenance, dev-passkey-import-shell-only, read-only search, service-layer boundary.
- **Boot & deploy integrity** — *a fresh instance boots from zero.* Cold-boot cycle, lean-boot core-independence, migration completeness, per-profile boot resolution, plugin dependency consistency, health.
- **Code & logging hygiene** — *authoring conventions that keep the code machine-legible.* Log-site tokens, mypy typing, JSON naming, plugin type-ownership, collection completeness.
- **Query-engine correctness (Gryphon)** — *the graph query engine returns correct results.* Differential fuzzer, metamorphic TLP, stage/branch coverage, findings ledger.
- **CI, process & runtime** — *the whole thing is gated before main advances.* CodeBuild product-line lanes, canary tier, secret-leak, async-delivery tiers, recurring-task uniqueness, spawn/teardown, web-render smoke.

## Why it isn't a pile: the doctrine

The system grew one guard per incident — each solved a specific finding — which is why it can feel accreted. But there is a single doctrine underneath, the **house convention** (`req-dev-validation-known-broken-5`): *a bounded, reviewed, in-repo check — a hard lint or a ratchet — with a Map row and a resolving `rid`* is TAP's canonical mechanism for honest coverage accounting, and new mechanisms **follow that shape rather than invent a parallel one** (and, per `req-dev-validation-ratchet-harness`, increasingly share the *implementation*, not just the shape). That is why a new guard slots in cleanly: same base class, same discovery, same honesty meta-tests.

## Where the mechanics live

| File | Role |
| --- | --- |
| [`tap/source_scan.py`](../tap/source_scan.py) | The AST tree-scanner substrate — parse driver, scope-stack visitor, import binder. Written once; every static guard reuses it. |
| [`tap/ratchet.py`](../tap/ratchet.py) | The compare-against-baseline core (ceiling and floor directions). |
| [`tap/guards/base.py`](../tap/guards/base.py) | The `Guard` base, `CeilingRatchet`, filesystem discovery, and rid-resolution. |
| [`tap/guards/callsite.py`](../tap/guards/callsite.py) | `CallsiteRatchet` plus the drift-proof per-offense identity for SARIF. |
| [`tap/guards/surfaces.py`](../tap/guards/surfaces.py) | The declared (non-guard) surfaces — the Map's negative space. |
| [`tap/tests/test_guards.py`](../tap/tests/test_guards.py) | Runs every guard's `check()`, plus the three honesty meta-tests. |

## Using it

```
manage.py guards --map          # print the whole Validation Map (guards ∪ declared surfaces)
manage.py guards --sync-map     # regenerate the committed Map block after adding/changing a guard
pytest tap/tests/test_guards.py # run every guard + the honesty meta-tests
```

**To add a guard:** drop a module in any `<app>/guards/` folder — discovery finds it automatically — set its `slug` / `map_row` / `rid` / `description` / `cadence` and implement `check()`, then define the requirement it enforces in a spec so its `rid` resolves. Choose the shape: a **hard lint** if there is no debt to grandfather, a **ratchet** if there is. Run `--sync-map` and commit the Map delta.

**To add a non-guard surface:** add a `DeclaredSurface` row to `tap/guards/surfaces.py` with a resolving `rid`, then `--sync-map`. That row *is* the reviewable decision that the Map's negative space is honestly recorded.
