# Security Posture Doctrine

## Philosophy

This spec is a standing **doctrine**, not a feature: it states how TAP decides *when to build security in*. It is the security-engineering center of gravity, consulted whenever a piece of work touches a surface where a defensive edge could be laid down.

The core doctrine is:

> When a security foundation can be built at minimal marginal cost — especially while already working on the surface it would protect — build it, even speculatively. The cost is asymmetric: cheap now, expensive or impossible later. Over-restriction is cheaply relaxed; under-restriction is expensively retrofitted after the code (or the attack) has spread.

Three observations drive this:

- **The cost of a defensive edge is lowest at construction time.** Making "every operation has a named actor" a structural invariant *before* anonymous code paths exist is far cheaper than paring them out after they have spread (`req-tap-auth-actor-model`). Naming plugin tables `<slug>__*` *during* a rename we're already doing costs ~nothing and unlocks per-plugin DB guards forever (`spec-plugin-type-ownership-v0.md`). The same edge added a year later is a migration, an audit, and a coordination problem.
- **You cannot enumerate future attack classes, but cheap edges are insurance against the whole space.** We do not know which attacks we will want to defend against. A foundational, build-once edge laid now is coverage we did not have to predict — it is there when the threat materializes, without an emergency.
- **Asymmetric reversibility.** If a cheap edge turns out to be over-built, *relaxing* it later is a small, safe change. If a needed edge was omitted, *adding* it later is a large, risky retrofit (often after an incident). When unsure, prefer the edge — you can always relax.

This doctrine deliberately **coexists with accepted risk.** TAP is not trying to be secure against everything now — plugins, for example, still have broad execution leeway, and that is a knowingly-accepted v0 posture. The doctrine is not "build all security"; it is "take the *cheap, foundational, build-once* edges when they pass the door, and let the expensive ones wait for demand." The discriminator is **marginal cost × foundational/build-once × relax-ability**, not "is it security."

And where an edge cannot be built at all yet — a harm we *recognize* but are (for now) powerless to *prevent*, the recurring case being a rogue plugin running arbitrary Python — we neither shrug it off nor pretend it is closed. We **formalize the recognition in the running code as a `CONCERN`** (`req-sec-concern-gaps`): a structured, machine-routable "this permitted-but-suspicious thing just happened" signal an internal security AI can monitor and act on, and a durable map of exactly where to build the real prevention later. Detection is the cheap edge available when prevention is not.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Take Cheap Edges | When a foundational defensive edge is near-free at construction time, build it. |
| 2. | Favor The Edge When Unsure | Prefer building a cheap edge over omitting it, since over-restriction relaxes cheaply and omission retrofits expensively. |
| 3. | Stay Honest About Accepted Risk | Name the risks deliberately left open; the doctrine is selective, not maximalist. |
| 4. | Concern What You Can't Yet Prevent | Where prevention isn't buildable yet, formalize the recognized harm as a runtime `CONCERN` — detection instead of silence. |

## Prior Art

This is the security-engineering form of well-known principles: **secure-by-default / secure-by-design** (build the safe path as the default state), **defense in depth** (independent layers, each cheap on its own), **least privilege** (grant the minimum, widen on demand), and **shift-left** (the defect/omission is cheapest to fix at authoring time). The `CONCERN` discipline (`req-sec-concern-gaps`) is the **detective-control / tripwire** tradition — canary tokens, IDS, `WARN_ON_ONCE`, audit-and-alert where a hard block is impossible or too costly — made a first-class, in-code habit. The novel framing here is the explicit **reversibility argument**: in a codebase authored and maintained primarily by AI, laying a speculative edge and relaxing it later is cheaper than it has ever been, which tilts the build/skip decision further toward *build*.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-sec-cheap-edges | [Build Cheap Foundational Edges](#build-cheap-foundational-edges) | Proposed | Take near-free build-once defensive foundations when working the surface |
| req-sec-reversibility | [Favor The Edge When Unsure](#favor-the-edge-when-unsure) | Proposed | Over-restriction relaxes cheaply; omission retrofits expensively |
| req-sec-honest-risk | [Name Accepted Risk](#name-accepted-risk) | Proposed | Doctrine is selective; deliberately-open risks are stated, not hidden |
| req-sec-concern-gaps | [Concern The Gaps You Can't Yet Close](#concern-the-gaps-you-cant-yet-close) | Proposed | Formalize recognized-but-unpreventable harms as runtime `CONCERN` signals — detection now, root-fix map for later |
| req-sec-email-not-identity | [Email Is Not Identity](#email-is-not-identity) | Proposed | Email (and any mutable, non-unique attribute) is never a reliable key for identifying, selecting, or authorizing a user; key off a stable internal id |

---

### Build Cheap Foundational Edges
----
RID: `req-sec-cheap-edges`
Status: `Proposed`

When work already touches a surface where a foundational defensive edge can be laid at minimal marginal cost, lay it — even if no current threat requires it.

#### Implementation

- The trigger is **opportunity + low marginal cost**, not a present threat. "We are already renaming these tables" or "we are already routing every write through one chokepoint" is exactly when the edge is cheapest.
- The edge should be **foundational and build-once**: it makes a class of future defense *possible* or *cheap*, even if the enforcement is added later. Laying `<slug>__*` table naming now makes per-plugin DB grants/RLS a later config change rather than a schema migration.
- Prefer making the safe path the **default/structural** state (secure-by-default) over a checked rule that a developer must remember — a structural invariant cannot be forgotten.

#### TAP edges already laid under this doctrine

These were chosen *because* they were cheap-at-construction and build-once, not because a threat demanded them:

- **No `User=None` landed first** (`req-tap-auth-actor-model`) — a structural invariant from the first round, far cheaper than retrofitting attribution later.
- **On-by-default authorization backstop** (`req-tap-auth-policy`) — the gate is structural; a forgotten `authorize()` fails closed rather than silently opening.
- **Least-privilege bootloader bundle** (`req-boot-phases`) — boot gets exactly what it needs, no `grid.purge`/`grid.delete`, bounding the blast radius of a boot bug.
- **`is_superuser` is not a TAP-service bypass** (`req-tap-auth-policy`) — the recovery floor is preserved in Django admin while the service boundary refuses the god-bit.
- **Bidirectional built-in-key constraint** (`req-tap-auth-builtins`) — closed a privilege-escalation path (an ordinary user reserving a built-in key) at the cost of one DB constraint.
- **Per-plugin DB-table naming** (`spec-plugin-type-ownership-v0.md`, `req-plugin-type-db-affordance`) — near-free during the plugin refactor's rename; foundation for per-plugin DB guards.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sec-cheap-edges-1 | Opportunity Trigger | Proposed | A near-free, foundational, build-once defensive edge is taken when work already touches its surface, without waiting for a present threat. | |
| req-sec-cheap-edges-2 | Secure By Default | Proposed | Prefer structural/default safe states over remember-to-check rules where the cost is comparable. | |

---

### Favor The Edge When Unsure
----
RID: `req-sec-reversibility`
Status: `Proposed`

When uncertain whether a cheap edge is worth it, build it — because the reversibility is asymmetric.

#### Implementation

- Relaxing an over-built restriction later is a small, safe change (widen a grant, drop a constraint, loosen a default).
- Retrofitting an omitted restriction later is a large, risky change (audit every callsite, migrate data, coordinate plugins) — and often happens under incident pressure.
- Therefore the default under uncertainty, *for cheap edges*, is **build it and relax later if over-built**, not "skip it and add later if needed."
- This is bounded by `req-sec-cheap-edges` (cheap + foundational) and `req-sec-honest-risk` (do not build expensive speculative machinery).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sec-reversibility-1 | Relax Over Retrofit | Proposed | For cheap foundational edges, uncertainty resolves toward building (relax later) rather than omitting (retrofit later). | |

---

### Name Accepted Risk
----
RID: `req-sec-honest-risk`
Status: `Proposed`

The doctrine is selective. Risks deliberately left open are named honestly, not hidden behind the impression of completeness.

#### Implementation

- This doctrine does **not** imply TAP is hardened against everything. v0 knowingly accepts, for example, broad plugin execution leeway, raw-DB-write-is-full-compromise, and a trusted-by-design boot config (`req-boot-trust`).
- When a cheap edge is *not* taken, or a class of risk is accepted, say so where the decision lives — so "we didn't build this" is a recorded choice, not a silent gap.
- The complement of taking cheap edges is being honest that the expensive ones are deferred by design.

#### Named open edges (deliberately deferred)

- **Read-only search write path — prevention is single-mechanism (detection now added).** The Gryphon/Search executor runs raw SQL on the `search_readonly` connection, which the ORM read/write backstops (`tap_grid/read_guard.py`, `write_guard.py`) structurally do not see — the write guard is scoped to `BaseModel`/`Entity` `save`/`delete` (ORM methods), not raw cursor SQL. *Prevention* on that path therefore rests on a single mechanism: PostgreSQL's `default_transaction_read_only=on` (`req-grid-search-readonly.sec`). That mechanism is strong and absolute (it covers every table, temp tables, and side-effecting functions, with no pattern-matching to evade), so an application-layer write-SQL prevention wrapper — the write analog of the read guard's Layer-2 execute_wrapper — is deferred, not built. What *is* now built is **detection**: a write reaching that connection emits a `security` Flaw (`req-grid-search-readonly.sec-6`, `search_readonly_write_blocked`) before the DB rejection propagates, so the previously-silent block is a response-triggering alert. Residual accepted risk: no in-app write *prevention* depth on the raw-executor path (single-mechanism prevention + detection). Decision home: `req-grid-search-readonly.sec`.
- **Un-schema'd JSONB blobs.** Concrete `BaseModel` subclasses must declare every field in `FIELD_CRUD_SCHEMA` (enforced at class definition), but a `JSONField` may declare itself as bare `{"type": "object"}` with no `properties` — its sub-keys are then as undescribed as a free-text blob (e.g. `pg_node.tags`). This blocks two things until closed: (1) verifiable declared-vs-actual on JSON *content*, and (2) type-strictness for Gryphon predicates on JSON sub-paths (`n.data.tags.zone`) — the executor's type oracle can resolve a column's declared type but bottoms out at OPEN inside an un-typed object, so JSON-sub-path predicates stay coercion-tolerant while typed columns are strict (the interim asymmetry recorded in `spec-grid-traversal-language.md`). The design is forward-compatible: the Gryphon type resolver already walks `FIELD_CRUD_SCHEMA` into the JSON object and applies strictness *iff* a concrete type is declared, so replacing `{"type": "object"}` with real `properties` lights up JSON-lane strictness with zero executor change. Closing the gap grid-wide (a class-definition guard requiring JSON fields to declare their sub-schema or explicitly opt into open-blob status, plus a backfill, minus genuinely-open blobs like `flip_map`/`dimensions`/`metadata`) is a deliberate convention thread, not a near-free edge, so it is deferred until that surface is worked. Decision home: `req-grid-entity-validation` (the field-schema machinery).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sec-honest-risk-1 | Deliberate Gaps Are Stated | Proposed | Accepted risks / un-taken edges are recorded as choices where the decision lives. | |

---

### Concern The Gaps You Can't Yet Close
----
RID: `req-sec-concern-gaps`
Status: `Proposed`

When you recognize a way the system could be harmed that you **cannot prevent yet** — the archetype being a rogue or buggy plugin doing something malicious with the arbitrary Python it is (by v0 design) allowed to run — do not let the recognition evaporate into a code comment or a good intention. **Formalize it in the running code as a `CONCERN`** (`spec-tap-logging.md`, the reserved `CONCERN` `message_code`): a structured, machine-routable "this permitted-but-suspicious thing just happened" record, emitted at the exact point the suspicious thing is observable.

This is the detective companion to `req-sec-cheap-edges` (the *preventive* cheap edge) and the active-monitoring companion to `req-sec-honest-risk` (which *names* the accepted risk in prose): the same gap gets **stated in the spec and instrumented in the code**.

#### Why this is worth the habit

- **The recognition is the valuable part, and it is perishable.** Spotting "a plugin could resolve another consumer's secret / reach that surface / write there" is real security insight; losing it to a comment wastes it. A `CONCERN` turns the insight into a durable, first-class, greppable artifact that travels with the code.
- **It resolves the standing tension** — "I can see how a rogue plugin could hurt the system, but I'm powerless (for now) to stop it." You are not powerless: where prevention is expensive or impossible today, **detection is the cheap edge that is available**. Baking the `CONCERN` in scratches the itch honestly — it fails *open* (the operation proceeds) but *loud and structured*.
- **The set of `CONCERN` sites is a map of where to harden at the root later.** Because they live *in code*, not a wiki, they cannot rot out of sync, and each one marks a concrete future preventive control — ideally paired with a deferred enforcement requirement (e.g. `req-tap-cares-secrets-future-access-control`) so the `CONCERN` is explicitly the interim tripwire for a named future fix.
- **Interim monitorability by an internal security AI.** Until the root fix lands, the `CONCERN` stream is shaped for a security-system/on-call consumer (eventually AI) to monitor and evaluate case-by-case — the same machine-routing affordance as `FLAW` (shared `security` domain tag, `req-tap-logging-domain-tags`).

#### When it's a CONCERN (the discriminator)

- **`CONCERN`** — behavior that is *permitted but suspicious* and not (yet) preventable. No invariant is violated, because we do not yet guarantee against it. Non-fatal, best-effort, fails open. ("Somebody's being sus.")
- Distinct from **`FLAW`** (`spec-tap-flaw-v0.md`) — a violated guarantee, steady-state-empty, every fire actionable-and-patchable. Filing permitted-but-suspicious behavior as a Flaw would corrode the Flaw stream's meaning; that is precisely why `CONCERN` is its own category.
- Distinct from **`ABORT`** — a fatal, stop-now lifecycle signal.
- A `CONCERN` may carry false positives by nature; that is acceptable because it blocks nothing. Aim for signal, but the bar is lower than `FLAW`'s "wake a human."

#### Implementation

- Emit through the `concern(...)` helper (`spec-tap-logging.md`), `security`-tagged (or the apt `req-tap-logging-domain-tags` tag), with a stable `concern_type` token so the stream is routable.
- Detective, non-blocking, fail-open-but-loud. Best-effort detection is fine — a determined attacker may evade it; name that residual per `req-sec-honest-risk` at the callsite. The value is the recognition captured, not an airtight gate.
- Pair each `CONCERN`, where one exists, with the deferred preventive requirement it stands in for — so "detection now" and "prevention later" are two ends of one recorded decision.
- First instance: the cross-scope secret-access tripwire — a plugin resolving the install-system `tap_plugins.source` scope emits a `CONCERN`, the interim detective control for the deferred least-privilege enforcement (`req-tap-cares-secrets-future-access-control`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sec-concern-gaps-1 | Formalize, Don't Shrug | Proposed | A recognized-but-unpreventable harm is captured as an in-code `CONCERN` at the observable point, not left as a comment or dropped. | Recognition made durable. |
| req-sec-concern-gaps-2 | Detective, Fail-Open | Proposed | A `CONCERN` is non-blocking and fails open; its value is the structured signal, and the residual (the flagged op still ran) is named per `req-sec-honest-risk`. | Best-effort detection acceptable. |
| req-sec-concern-gaps-3 | Map To Root Fix | Proposed | A `CONCERN` marks where to build real prevention later, paired where possible with a deferred preventive requirement it stands in for. | The `CONCERN` sites are the hardening backlog. |
| req-sec-concern-gaps-4 | Monitorable | Proposed | `CONCERN`s are machine-routable (reserved `message_code`, `security` domain tag) so an internal security AI / on-call can monitor and evaluate the stream. | Shares FLAW's routing vocabulary. |

---

### Email Is Not Identity
----
RID: `req-sec-email-not-identity`  
Status: `Proposed`

**Email — and any mutable, non-unique, or externally-controlled attribute — is not a reliable source of user identification.** It MUST NOT be used as the key to *identify*, *select*, *look up*, *authorize*, or *grant* to a user. Identity keys off a **stable, internal, unique identifier** (the `User` id, or for federated identity the durable `(provider, sub)` pair — `spec-tap-auth-v0.md` `req-tap-auth-external-identity`). This is a concrete instance of secure-by-default (`req-sec-cheap-edges`): choosing the right key at authoring time is free; retrofitting it after a subsystem has pinned email is expensive and, once ambiguous data exists, security-relevant.

#### Why email fails as an identity key

- **Mutable** — a person's email changes; anything keyed to it silently follows or breaks.
- **Not unique** — TAP permits duplicate emails at the DB level by design (`req-tap-auth-external-identity`), so an email can resolve to zero, one, or several users.
- **Externally controlled** — for federated identity the provider owns the address; only the verified `(provider, sub)` is a durable anchor.
- **The failure is silent** — a lookup that resolves an ambiguous email by picking the first row mis-identifies a user with no error. On an account-impacting operation that is account takeover (mint a credential for the wrong person) or wrong-account denial-of-service (deactivate / log out the wrong person).

#### The rule

- **Identify / select / target by stable internal id.** User-targeting operations (management commands, service verbs, admin actions) key off the internal `User` id — never email.
- **Email is at most an ambiguity-refusing convenience.** Where a human-friendly lookup is genuinely useful, email MAY be *offered* only as a convenience that **fails loud on zero or multiple matches** — never a silent `.first()`-style pick. A unique username is an acceptable stable selector; email is not.
- **Email as an authorization *filter* is fine; as an identity *key* is not.** Matching a provider-asserted **verified** email against an allow-list (`allowed_emails`) is a legitimate gate enforced every login; using email to *decide which user this is* is not. Keep the distinction explicit.
- **Applies system-wide, not just to auth.** Any subsystem that names a user — plugins, AI/machine actors, audit trails, grid provenance — inherits this rule.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-sec-email-not-identity-1 | Stable-Id Keying | Proposed | User identification / selection / authorization keys off a stable internal id (or federated `(provider, sub)`), never email or another mutable/non-unique attribute. | |
| req-sec-email-not-identity-2 | No Silent Ambiguous Pick | Proposed | Where email is offered as a convenience lookup, it fails loud on zero or multiple matches; a silent first-match pick is a defect. | |
| req-sec-email-not-identity-3 | Filter ≠ Key | Proposed | Email used as a verified authorization filter (allow-list) is permitted; email used as an identity key is not. The distinction is stated where email appears. | |

---

## Relationship To Other Specs

- **`spec-tap-auth-v0.md`** — the densest application of this doctrine (named actors, on-by-default authz, least privilege, recovery floor). Many of its choices are this doctrine in action; in particular it instantiates `req-sec-email-not-identity` via `req-tap-auth-email-not-identity` (the express auth rule), the `req-tap-auth-user-lookup` id-keyed selector convention, and `req-tap-auth-external-identity` (durable `(provider, sub)`).
- **`spec-plugin-type-ownership-v0.md`** — the per-plugin DB-guard foundation (`req-plugin-type-db-affordance`) is a canonical "cheap edge during work already underway."
- **`spec-tap-boot-v0.md`** (`req-boot-trust`) — the explicit statement of where trust is *granted* by design; the honest-accepted-risk counterpart.
- **`spec-tap-flaw-v0.md`** — the mechanism for surfacing when a structural edge is violated at runtime (e.g. `unguarded_operation`).
- **`spec-tap-logging.md`** — hosts the reserved `CONCERN` `message_code` and the `concern(...)` helper that `req-sec-concern-gaps` builds on, plus the shared `req-tap-logging-domain-tags` routing vocabulary that `CONCERN` and `FLAW` both inherit.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed | Requirement has been designed but not yet accepted for implementation. |
| Approved for Development | Requirement is accepted and ready to be implemented. |
| In Development | Actively being worked on. |
| Implemented | Has been written. |
| Verified | Has met the acceptance criteria. |
| Refactoring | In the process of being re-worked. |
| Deprecating | In the process of being deprecated. |
| Deprecated | No longer part of the current architecture. |
