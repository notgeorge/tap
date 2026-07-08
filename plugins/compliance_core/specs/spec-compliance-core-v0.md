# Compliance Core Plugin Specification

> **Status: Phase A + B implemented (2026-07-08).** All six models
> (`compliance_artifact`, `compliance_context`, `compliance_evidence`,
> `compliance_finding`, `compliance_exception`, `compliance_boundary`) and all five edges
> (`HAS_COMPLIANCE_EVIDENCE`, `COVERS_COMPLIANCE_FINDING`, `HAS_COMPLIANCE_FINDING`,
> `SCOPED_TO_COMPLIANCE_BOUNDARY`, `CONCERNS_COMPLIANCE_CONTROL`) now live in compliance_core,
> with the regime-neutral type-marker dimension fix on the moved evidence/finding/exception
> nodes. fedramp/samsite retarget onto them. The former fedramp bridge edge
> `RELATED_INDICATOR` (finding → ksi_indicator) was **generalized** into
> `CONCERNS_COMPLIANCE_CONTROL` (finding → wildcard control target) so a finding can concern
> controls across regimes; fedramp's panels supply the `ksi_indicator` target. Migrations `0001`/`0002`
> (compliance_core) + `0004`/`0005` (fedramp deletes) apply clean; all targeted suites +
> mypy ratchet green.

## Plugin Identity

- **Slug:** `compliance_core`
- **Kind:** substrate library plugin — regime-agnostic compliance vocabulary. **No
  collector in v0.**
- **Public surface:**
  - **Models** (see `req-compliance-core-models`): `compliance_artifact`,
    `compliance_context`, `compliance_evidence`, `compliance_finding`,
    `compliance_exception`, `compliance_boundary`.
  - **Edge types** (see `req-compliance-core-edges`): `HAS_COMPLIANCE_EVIDENCE`,
    `COVERS_COMPLIANCE_FINDING`, `HAS_COMPLIANCE_FINDING`,
    `SCOPED_TO_COMPLIANCE_BOUNDARY`, `CONCERNS_COMPLIANCE_CONTROL`.
  - **Default dimensions** (see `req-compliance-core-regime-neutral`): a neutral
    per-type marker under the `compliance` key (e.g. `compliance: finding`); the
    **regime** dimension (`fedramp-20x`, `soc2`, …) is layered per-instance by the
    consumer, never baked into the model.

## Philosophy

Compliance vocabulary is regime-agnostic substrate, not FedRAMP payload. Evidence,
findings, exceptions, fetched artifacts, authorization boundaries, and per-regime
posture exist in **every** compliance program — FedRAMP 20x, SOC2, CMMC, ISO 27001.
They live in `fedramp_20x_ksi` today only because it was the first regime plugin, and
the coupling shows: samsite's compliance collector creates `compliance_artifact`s and
~15 grift/panel queries read them, while fedramp barely touches them and roscale (the
OSCAL renderer) references them zero times. "OSCAL shouldn't carry over to FedRAMP."
The fix is the substrate-core extraction doctrine: hoist the generic layer into a
neutral plugin that every regime/renderer/integration depends on **downward**.

Three principles shape the design:

**Regime lives on the instance, not the model.** A generic node must not hardcode a
regime. Today `evidence`/`finding`/`exception` default to `{"compliance":
"fedramp-20x"}` — a regime baked into a model that is supposed to be regime-agnostic.
In compliance_core the model default is a neutral **type marker** (`compliance:
evidence`); a regime dimension, when needed, is applied per-instance by the collector
that mints the node (a future FedRAMP collector would stamp `fedramp-20x`; a SOC2 one
`soc2`). v0 ships no such collector, so today only the neutral marker is set — see
`req-compliance-core-regime-neutral`. The `compliance_context` node is where a Grid's
regime posture is recorded, and it is already regime-generic (its `regime` field
discriminates FedRAMP/SOC2/CMMC/ISO).

**The `compliance_` name prefix disambiguates domain.** Node names carry a
`compliance_` qualifier (`compliance_evidence`, not bare `evidence`) so the vocabulary
is unambiguous system-wide — distinct from a future `crime_scene_evidence` or another
kind of `exception`. Ownership (the `compliance_core` plugin slug) and semantic domain
(the `compliance_` name qualifier) are **distinct axes**; the resulting
`compliance_core__compliance_evidence` entity_type is deliberately explicit. Edge
verbs name their object with the same qualifier (`HAS_COMPLIANCE_EVIDENCE`) so a slug
reads unambiguously and tracks the node type it targets.

**Substrate, depended on downward.** `compliance_core` depends on nothing above core.
`fedramp_20x_ksi` (regime vocabulary), `roscale` (OSCAL renderer), and `samsite`
(deployment integration) depend downward on it. Framework owns the regime-specific
vocabulary; the substrate owns the generic primitives; deployment owns the wiring.

## Roadmap Alignment

Realizes the **substrate-core plugin extraction** doctrine; sibling of the
`identity_core` extraction. Advances cross-plugin decoupling and removes a latent bug
(regime hardcoded into generic model defaults). Pre-eviction work — the `entity_type`
renames are namespace churn that must land before plugins freeze at released tags
(`req-compliance-core-migration`).

**Forward note (captured, not built).** `fedramp_20x_ksi` currently hosts two tenants:
strictly-KSI vocabulary (`ksi_*`) and broader FedRAMP-20x vocabulary (`vdr_finding`,
`vdr_report`). A coming **fedramp_20x** plugin will take the non-`ksi_`-prefixed
vocabulary; the `ksi_` prefix is the mechanical discriminator. `vdr_*` and `ksi_*`
both stay in `fedramp_20x_ksi` for now — compliance_core takes only the regime-agnostic
layer.

## Prior Art

- **OSCAL** (NIST): assessment findings, evidence/observations, system components, the
  authorization boundary / system-security-plan scope — the generic shapes this
  vocabulary mirrors.
- **NIST SP 800-53A / POA&M**: findings + risk acceptances (exceptions) as first-class
  assessment artifacts.
- **The cross-regime pattern**: SOC2, CMMC, ISO 27001 all carry evidence, findings,
  exceptions, and a scoping boundary — the reason the layer is regime-agnostic.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Compliance Substrate | A neutral home for regime-agnostic compliance vocabulary; six v0 node types. |
| 2. | Library Plugin | No collector in v0. Models + edge types; consumers mint instances via their own collectors. |
| 3. | Regime On The Instance | Generic models carry a neutral type-marker dimension; the regime is layered per-instance, never baked into the model. |
| 4. | Disambiguating Names | `compliance_`-prefixed node names; edge verbs name their object with the same qualifier. |
| 5. | Downward-Only Deps | fedramp_20x_ksi / roscale / samsite depend on compliance_core; it depends on nothing above core. |
| 6. | Faithful Carry-Forward | Fields move unchanged; the only behavior change to samsite is the type/edge rename (and the regime-dimension fix). |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-compliance-core-scope | [Plugin Scope](#plugin-scope) | Implemented | Substrate library; six models + five edges; no collector. |
| req-compliance-core-models | [Model Set](#model-set) | Implemented | `compliance_artifact`, `compliance_context`, `compliance_evidence`, `compliance_finding`, `compliance_exception`, `compliance_boundary`. |
| req-compliance-core-edges | [Edge Vocabulary](#edge-vocabulary) | Implemented | `HAS_COMPLIANCE_EVIDENCE`, `COVERS_COMPLIANCE_FINDING`, `HAS_COMPLIANCE_FINDING`, `SCOPED_TO_COMPLIANCE_BOUNDARY`, `CONCERNS_COMPLIANCE_CONTROL` (wildcard target). |
| req-compliance-core-regime-neutral | [Regime On The Instance](#regime-on-the-instance) | Implemented | Model default is a neutral type marker; regime layered per-instance. Fixes the hardcoded `fedramp-20x` default. |
| req-compliance-core-naming | [Naming Discipline](#naming-discipline) | Implemented | `compliance_` node-name prefix; edge object noun tracks the node type. |
| req-compliance-core-deps | [Dependency Direction](#dependency-direction) | Implemented | Downward-only; declared in consumers' `pyproject.toml` + `depends_on`. |
| req-compliance-core-consumer-retargets | [Consumer Retargets](#consumer-retargets) | Implemented | fedramp/samsite retarget type strings + edges; the fedramp bridge edge `RELATED_INDICATOR` was generalized into `CONCERNS_COMPLIANCE_CONTROL` (compliance_core, wildcard target). |
| req-compliance-core-migration | [Extraction & Migration](#extraction--migration) | Implemented | Rename `fedramp_20x_ksi__*` → `compliance_core__compliance_*`; ids regenerate (collected, not seeded); phased first slice; pre-eviction. |
| req-compliance-core-nongoals | [v0 Non-Goals](#v0-non-goals) | Implemented | `ksi_*` and `vdr_*` stay in fedramp; no collector; no regime logic; generic `component` deferred. |

### Plugin Scope
----
RID: `req-compliance-core-scope`
Status: `Implemented`

`compliance_core` is a **library / substrate** plugin. Its v0 surface is six models and
four edge types plus their dimension defaults. It registers node/edge types and
dimensions at load; it ships **no collector** (`apps.py` is `pass`; no `tap_cares`
registration) and seeds no GRIFT. Consumers import only from `compliance_core.*` and
mint instances through their own collectors. It is the generic layer beneath every
compliance regime plugin.

### Model Set
----
RID: `req-compliance-core-models`
Status: `Implemented`

Six node types, `entity_type = compliance_core__<name>`, fields carried forward
faithfully from the `fedramp_20x_ksi` originals:

| entity_type | from | key fields |
| --- | --- | --- |
| `compliance_core__compliance_artifact` | `fedramp_20x_ksi__compliance_artifact` | `kind` (oscal_ssp/oscal_poam/iiw), `source_url`, `content` (blob), signature-verification metadata |
| `compliance_core__compliance_context` | `fedramp_20x_ksi__compliance_context` | `regime` (discriminator), `fedramp_class` (+ future per-regime posture fields) |
| `compliance_core__compliance_evidence` | `fedramp_20x_ksi__evidence` | `name`, `description`, `kind` |
| `compliance_core__compliance_finding` | `fedramp_20x_ksi__finding` | `name`, `summary`, `description`, `status` |
| `compliance_core__compliance_exception` | `fedramp_20x_ksi__exception` | `name`, `description`, `status` |
| `compliance_core__compliance_boundary` | `fedramp_20x_ksi__boundary` | `name`, `description` |

`compliance_artifact` and `compliance_context` keep their names (already
`compliance_`-prefixed). `boundary` moves here because every compliance regime scopes
to some authorization/system boundary — it is not FedRAMP-specific. Display, icons,
CRUD/validation schemas, and `CREATE_REQUIRED` carry forward from the originals
unchanged except the `entity_type`/`db_table` rename and the dimension fix
(`req-compliance-core-regime-neutral`).

### Edge Vocabulary
----
RID: `req-compliance-core-edges`
Status: `Implemented`

Five edges, renamed so the object noun tracks the (now `compliance_`-prefixed) node
type. Four move directly with their generic endpoints; the fifth
(`CONCERNS_COMPLIANCE_CONTROL`) is the generalized bridge (see Consumer Retargets):

| edge (compliance_core) | from | endpoints |
| --- | --- | --- |
| `HAS_COMPLIANCE_EVIDENCE` | `HAS_EVIDENCE` | `compliance_finding` → `compliance_evidence` |
| `COVERS_COMPLIANCE_FINDING` | `COVERS_FINDING` | `compliance_exception` → `compliance_finding` |
| `HAS_COMPLIANCE_FINDING` | `HAS_FINDING` | any asset (wildcard source) → `compliance_finding` |
| `SCOPED_TO_COMPLIANCE_BOUNDARY` | `SCOPED_TO_BOUNDARY` | any component (wildcard source) → `compliance_boundary` |
| `CONCERNS_COMPLIANCE_CONTROL` | `RELATED_INDICATOR` | `compliance_finding` → any control (wildcard target) |

Wildcard **sources** on `HAS_COMPLIANCE_FINDING` and `SCOPED_TO_COMPLIANCE_BOUNDARY` are
deliberate: any asset can carry a finding, any component can be in scope for a boundary,
across regimes. The wildcard **target** on `CONCERNS_COMPLIANCE_CONTROL` is the mirror
image: a finding can concern a control in any regime's catalog — a FedRAMP `ksi_indicator`
today, a SOC2 criterion tomorrow, or several at once. Keeping the target open lets the
edge live in compliance_core (it names no regime type, so no upward dependency) without a
generic `compliance_control` supertype, which is deferred until a second regime justifies
designing it (`req-compliance-core-nongoals`). Until then the source is the only typed end;
consumers constrain the target in their own queries.

### Regime On The Instance
----
RID: `req-compliance-core-regime-neutral`
Status: `Implemented`

Generic models MUST NOT bake a regime into their default dimensions. The model default
is a neutral per-type marker under the `compliance` key: `compliance: artifact`,
`compliance: context`, `compliance: evidence`, `compliance: finding`, `compliance:
exception`, `compliance: boundary`. The **regime** (`fedramp-20x`, `soc2`, …) is a
distinct dimension applied **per-instance** by whatever collector mints the node (a
future compliance collector would stamp `fedramp-20x` / `soc2` on the instances it
produces). This fixes the current `evidence`/`finding`/`exception` models defaulting to
`{"compliance": "fedramp-20x"}` — a regime hardcoded into a regime-agnostic model.

**v0 reality (honest note):** no collector mints `compliance_finding` / `compliance_evidence`
today (`req-compliance-core-nongoals` — no collector in v0), so no regime dimension is
stamped yet and nothing reads one. The guarantee delivered now is the *negative* one —
the model no longer bakes a regime; the neutral type marker is the only default. Positive
per-instance regime stamping lands with the first minting collector.

| ACID | Title | Status | Description |
| --- | --- | :---: | --- |
| req-compliance-core-regime-neutral-1 | Neutral model default | Implemented | Each model defaults to a type marker, not a regime slug. |
| req-compliance-core-regime-neutral-2 | Regime per-instance | Deferred | Regime is an instance-level dimension, not a model default; the mechanism (per-node dimensions) is in place. No v0 collector mints these nodes, so no regime is stamped yet — lands with the first minting collector. |
| req-compliance-core-regime-neutral-3 | No fedramp default remains | Implemented | No compliance_core model carries `fedramp-20x` (or any regime) as its default. |

### Naming Discipline
----
RID: `req-compliance-core-naming`
Status: `Implemented`

Node names carry the `compliance_` domain qualifier for system-wide disambiguation
(`compliance_evidence` vs a future `crime_scene_evidence`). Edge slugs name their
object with the same qualifier so the verb tracks the node type it targets
(`HAS_COMPLIANCE_EVIDENCE`, not `HAS_EVIDENCE`). This is the "name the specific object"
discipline from the add-edge skill, not redundant endpoint repetition: the object's
actual type name *is* `compliance_evidence`. The doubled `compliance_core__compliance_*`
entity_type is intentional — the plugin slug is ownership, the name qualifier is
semantic domain.

### Dependency Direction
----
RID: `req-compliance-core-deps`
Status: `Implemented`

compliance_core depends on nothing above core (`tap_grid`/`tap`). Consumers depend
**downward**: `fedramp_20x_ksi`, `roscale`, and `samsite` declare
`tap-plugin-compliance-core` in `pyproject.toml` and list `compliance_core` in
`depends_on`. The AST import-graph guard (`tap/plugin_deps.py`) enforces that any
`from tap_plugin.compliance_core…` import is declared.

### Consumer Retargets
----
RID: `req-compliance-core-consumer-retargets`
Status: `Implemented`

- **samsite** — the compliance collector, `decompose.py`, the `ksi_scoreboard` panel,
  landing/compliance/iiw grift, and `artifact_manifest` retarget
  `fedramp_20x_ksi__compliance_artifact` → `compliance_core__compliance_artifact` (~15
  string sites), and evidence/finding/exception/boundary type strings + the moved edge
  slugs to their compliance_core forms. (No regime dimension is stamped in v0 — see the
  honest note in `req-compliance-core-regime-neutral`.)
- **fedramp_20x_ksi** — drops the six moved models + their migrations; keeps `ksi_*`
  and `vdr_*`. Any fedramp query/edge referencing the moved types retargets.
- **Bridge edge (generalized)** — the former `RELATED_INDICATOR` (`finding →
  ksi_indicator`) was **not** kept as a fedramp-specific edge: "a finding concerns a
  compliance control" is a cross-regime relationship, so it became
  `CONCERNS_COMPLIANCE_CONTROL` in **compliance_core** with a typed source
  (`compliance_finding`) and a **wildcard target**. A finding can now concern controls in
  any regime's catalog — a FedRAMP `ksi_indicator`, a SOC2 criterion, several at once.
  fedramp's panels/grift still constrain the target to `ksi_indicator` in their queries.
  This also removes a Phase-B awkwardness (fedramp owning an edge sourced from a
  compliance_core node). The generic `compliance_control` supertype that would let the
  target be *constrained* rather than wildcard is deferred to the second regime.
- **roscale** — no change (references the generic concepts by string zero times today).

### Extraction & Migration
----
RID: `req-compliance-core-migration`
Status: `Implemented`

Renames `fedramp_20x_ksi__{compliance_artifact, compliance_context, evidence, finding,
exception, boundary}` → `compliance_core__compliance_*`. The `entity_type` change
shifts the `uuid5`-derived ids, but every one of these nodes is **collected**
(re-produced each run by samsite's compliance collector), not a static seed, so ids
regenerate cleanly on the next collection (contrast the uuid5-hash-token-fallout that
bit a *static* seed).

Phased first slice (bounds blast radius):

1. **Phase A (proven-cheap):** stand up compliance_core with `compliance_artifact` +
   `compliance_context` (artifact is the ~15 samsite swaps; context is already
   regime-generic and moves free). Models + one migration + pyproject + `apps.py=pass`.
2. **Phase B:** add `compliance_evidence` + `compliance_finding` + `compliance_exception`
   + `compliance_boundary` and their four edges; apply the regime-dimension fix. Then
   generalize the fedramp bridge edge `RELATED_INDICATOR` into the fifth compliance_core
   edge `CONCERNS_COMPLIANCE_CONTROL` (wildcard target); retarget consumers.

Ordering: this is namespace churn (new `entity_type`s, new edge owners), so it MUST
land **before eviction** freezes plugins at released tags; otherwise the rename becomes
a coordinated multi-repo re-tag across compliance_core + fedramp + samsite.

### v0 Non-Goals
----
RID: `req-compliance-core-nongoals`
Status: `Implemented`

- **`ksi_*` vocabulary** (signal/theme/indicator/component/validation/violation) stays
  in fedramp_20x_ksi — strictly KSI-framework, KSI-signal-native. `ksi_component` in
  particular is one entry of a KSI signal's `components[]` array (keyed by
  `component_id` that KSI validations join on), not an OSCAL primitive — OSCAL is
  downstream of the signal.
- **`vdr_finding` / `vdr_report`** stay in fedramp_20x_ksi — welded to Sam's
  PAIN/IRV/LEV/KEV/SLA evaluation schema. They may later become a `compliance_finding`
  specialization + VDR eval fields (the coming fedramp_20x split), but not now.
- **Generic `compliance_component`** — deferred; `ksi_component` remains KSI-bound in v0.
- **No collector, no regime logic, no assessment engine.** compliance_core is
  vocabulary only; regimes and deployments own the wiring.
