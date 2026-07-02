---
title: Plugin Slug — Load-Bearing Register
spec: tap_plugins/specs/spec-plugin-architecture.md
covers:
  - req-plugin-arch-slug-register
  - req-plugin-arch-identity
  - req-plugin-arch-isolation
  - req-plugin-arch-dependencies
  - req-boot-install-section
audience:
  - llm
  - developer
status: reference
---

# Plugin Slug — Load-Bearing Register

The plugin **slug** is *the one stable identity* of a plugin (`req-plugin-arch-identity-1`):
`slug == tap.plugins entry-point key == tap_plugin.<slug> namespace segment == tap-plugin-<slug>
dist`, all four cross-checked by the pre-boot `conformance_gate`. Everything else about a plugin —
where its modules live, how its code is organized, which files hold what — is free to move *as long
as the slug holds*. That decoupling is deliberate and valuable, but it has a price: the slug is the
most load-bearing identifier in the plugin system, so **a slug change is a first-class breaking
operation** (a coordinated rename plus, for the data-tier couplings below, a migration) — never a
casual edit.

This page is the **register of every place the slug is load-bearing**, so the blast radius of a
slug change is knowable rather than rediscovered, and so we *notice* each time we lean on the slug
harder. It is governed by `req-plugin-arch-slug-register`: **any change that adds a new
slug-dependent coupling must add its row here in the same change.** Guardrail already in place: the
conformance gate makes accidental slug drift impossible — you cannot change the slug without changing
the dist, entry-point key, and namespace in lockstep, which it fails closed on. So the slug is
treated as immutable-by-guardrail; this register documents *why that matters*.

## The anchor

| Coupling | Where | On a slug change |
| --- | --- | --- |
| The identity quadruple: slug == entry-point key == namespace segment == `tap-plugin-<slug>` dist | `req-plugin-arch-identity-1`, `tap/preboot.py:conformance_gate` | All four move in lockstep or the gate fails closed. This *is* the rename. |

## Current couplings (mechanical — coordinated rename)

| Coupling | Where | On a slug change |
| --- | --- | --- |
| Boot profile `install` entries (keyed by slug) | `req-boot-install-section`, `boot/*.boot.json` | Every profile that installs the plugin must update. |
| Boot profile `population` seed-plugin steps | `req-boot-install-section`, `boot/*.boot.json` | Every seed/collector step naming the slug must update. |
| `TAP_PLUGINS` / reconciliation guard (keyed by slug) | `req-boot-install-section-5`, `tap/preboot.py` | Discovery + declared-vs-actual reconciliation re-key. |
| Other plugins' manifest `depends_on` | `req-plugin-arch-dependencies`, `tap-plugin.toml` | Every dependent's declaration + the consistency gate must update. |
| Plugin report / registry surface | `tap_plugins/report.py`, `manage.py plugins` | Report rows re-key (read-only, mechanical). |
| Collector registry key → on-grid `entity_id` | `register_collector(key="<slug>")`, `entity_id = uuid5(NAMESPACE_COLLECTOR, key)` (`spec-tap-cares-collector`) | **Persistent identity shift.** The collector key is conventionally the slug; changing it moves the collector's grid entity. This is the class the fedramp package-mode move hit (`e75aba38`). |

## Current couplings (data — persistent identity, migration)

| Coupling | Where | On a slug change |
| --- | --- | --- |
| Grift batch `source` provenance (`plugins.<slug>`) | `Batch.source`, `plugins/*/grift/*.grift.json` | **Not a functional key** — descriptive provenance only. Old batches keep the old label (honest history); new imports get the new one. A discontinuity, not breakage. Listed for completeness. |

## Proposed / incoming couplings (actively loading the slug up)

These do not fully bind the slug *yet*, but are designed to — and are the reason this register is
tracked rather than written once.

| Coupling | Where / status | Once landed, a slug change… |
| --- | --- | --- |
| **Secret paths** `tap_plugin/<slug>/…` (a plugin finds its own secrets by slug; namespace anchored on slug, key authored) | Proposed (the plugin-source-secret / consumer-first-scoping design; `spec-security-posture`) | silently relocates operator-provisioned secret files — an external contract. This is why secret paths anchor on the slug (stable, gated) and never on `__name__`. |
| **Owner-namespaced entity types** `<slug>__<name>` (nodes), `NAME__<slug>` (edges), tables `<slug>__*` | `req-plugin-arch-isolation`, `spec-plugin-type-ownership-v0` — **Proposed** (types are author-chosen today, e.g. `aws_account`) | becomes a data migration whose *dominant* cost is string references to the type slugs (test corpora, GRIFT/fixture/expected data, Gryphon query strings, cross-plugin edge endpoints), not the model files — per that spec's own cost model. |
| **Per-plugin DB guards / RLS** on `<slug>__*` tables | `req-plugin-arch-isolation`, `req-plugin-type-db-affordance` | grants/RLS scoped to the old table prefix must move. |
| **Plugins-as-grid-nodes** (sub-grid → grid north star) | Deferred | a plugin's on-grid node identity keys off the slug. |

## Deliberate NON-couplings (for contrast)

| Identifier | Anchored on | Why not the slug |
| --- | --- | --- |
| Logger name / `[<hex>]` site token | Import/module path + a minted per-file hex (`spec-tap-logging`) | An internal observability label is free to travel with the code; it explicitly avoids the slug (and the shadow-uniqueness-registry problem the conformance gate later solved elsewhere). Module-path derivation is *correct* here precisely because the identifier is not an external contract. |

## The discriminator (why some things anchor on the slug and some don't)

Anchor on the slug when the identifier is an **external contract** (operator-provisioned path) or a
**persistent identity** (on-grid `entity_id`, entity-type name): those must survive internal
refactors, and the slug is the stable, conformance-gated, enforced-unique identity that does.
Anchor on the **module path** only when the identifier is an **internal-only label** free to move
with the code (logger names). Never derive a slug-anchored path by string-splitting `__name__` — that
re-introduces the mutability the anchor exists to avoid; resolve the slug from the declared identity
(manifest / AppConfig / registry) instead.
