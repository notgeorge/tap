# Requirement Traceability — Implementation Ownership

## Philosophy

TAP's specifications and its code are already connected by `req-*` citations — thousands of them.
But those citations are **narrative, not ownership**. Measured across the tree: of 1,919 RID
mentions in `.py` files, 71% sit in docstrings and 28% in comments as explanatory
cross-references — *"related to req-X"* — and 1% in code identifiers. That is a many-to-many
explanatory relation, and it cannot answer the one question that matters for a single-source-of-
truth codebase:

> **Which function *is* the authoritative implementation of this requirement?**

`req-docs-rid-integrity` closed the first half of the gap: every citation now resolves to a
requirement that exists. This spec closes the second: a small, deliberate set of citations are
promoted from *mention* to **claim** — a `TAP-IMPLEMENTS` tag asserting that this function is where
a requirement's fact is derived, and that no other function may derive it.

The demand signal is concrete. A duplication audit found 18 instances of the same fact derived in
more than one place, six of them on security surfaces. Four carried a docstring in which the author
*admitted the copy while making it* — "Mirrors tap.settings", "identical contract to
tap.plugin_source_auth". Awareness was never the gap. The gap is that nothing made the ownership of
a fact structural, so a second derivation cost nothing to add and nothing pointed at its partner.

Three properties follow from that diagnosis, and they shape every requirement below:

- **A claim is scarce.** This is not a coverage program. The regulated-traceability field is
  unanimous that broad tracing decays into ceremony, and SQLite's corpus shows why: 60–90% coverage
  where a human deliberately targeted it, 0–20% everywhere else. TAP tags the requirements where a
  *canonical derivation* actually matters, and leaves the rest alone.
- **A claim can go stale, and must say so.** ASPICE 4.0 states the principle directly:
  *"Traceability alone, e.g., the existence of links, does not necessarily mean that the information
  is consistent."* A link that merely exists is the failure mode, not the goal.
- **A claim needs a consumer that visibly breaks.** Every durable tag convention in the wild — the
  kernel's `Fixes:`, Conventional Commits, Gerrit's `Change-Id`, SPDX — earned its accuracy from a
  consumer that broke or omitted when the tag was wrong. Inert tags rot. The consumer here is
  derived status (`spec-dev-validation.md`'s generated-Map discipline, pointed at the spec corpus).

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | One Fact, One Derivation | A requirement's authoritative implementation is declared, machine-checked, and unique. |
| 2. | Scarce And Targeted | Claims are made where a canonical derivation matters, never as a coverage sweep. |
| 3. | Stale Claims Are Loud | A claim whose requirement changed underneath it fails, rather than reading as sound. |
| 4. | Declared Duplicates, Never Silent Ones | A second derivation is possible only as a documented, reviewed act. |
| 5. | Minted, Not Typed | The tag is emitted by a tool; hand-authoring an identifier is how conventions rot. |

## Prior Art

The traceability field has solved most of this, and TAP borrows deliberately rather than inventing.

**OpenFastTrace** supplies the defect vocabulary this spec adopts wholesale — `Duplicate`,
`Orphaned`, `Unwanted`, `Outdated`, `Predated` — and the insight that a link needs a *staleness
state*, not just existence. Notably it names copy-paste propagation twice in that vocabulary
("copy-paste error", "copy-paste error likely"), which is precisely the hazard a tag that travels
with copied code creates.

**SQLite** demonstrates content-hash staleness at scale: requirement identity *is* the hash of the
requirement text, so editing a requirement mechanically orphans every reference to it — 971 marks
in the shipped tree, zero drift. TAP takes the mechanism but not the identity model: readable slugs
are kept (ISO 26262 8-6.4.2.5 a's stable-identifier property, and 1,800+ existing citations depend
on them) and the hash moves into the *claim*. SQLite's affordability tricks are copied directly:
the tool emits the tag pre-hashed, and evidence from a single class is not treated as verification.

**StrictDoc** already models this exact semantic for Python — `@relation(REQ-1, scope=function,
role=Implementation)` — including the `role` field that distinguishes *this is THE implementation*
from *this merely relates*. Its docstring-over-comment choice for Python is independently the right
one here: `ast.get_docstring()` reads it without importing, while comments require `tokenize` and
share a line that other tools rewrite.

**LOBSTER** (BMW) contributes two rules adopted below: store the link once and derive the reverse
(duplicated links are how matrices rot), and make the escape hatch's payload a mandatory reason
rather than a bare flag.

**Rust's `// SAFETY:` + clippy** supplies the enforcement lessons: ship the inverse lint alongside
the lint (`unnecessary_safety_comment` shipped with `undocumented_unsafe_blocks`), and lint for
near-miss spellings, because a misspelled tag fails *open* — `// SAFTEY:` reports "no comment" and
the typo goes unnoticed. Roughly 60% of real-world failures in that ecosystem are shape, not
staleness.

**Within TAP**, this is the complement of `req-tap-known-dupes`: that convention declares a
duplicate that must exist; this one declares the original that must not be duplicated. They compose
directly — see `req-tap-traceability-uniqueness`.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-traceability-claim | [The Implementation Claim](#the-implementation-claim) | Implemented | `TAP-IMPLEMENTS:` in the docstring of the one function that derives a requirement's fact |
| req-tap-traceability-roles | [Role Vocabulary](#role-vocabulary) | Implemented | A closed set — a requirement is often realized at several layers, all legitimately |
| req-tap-traceability-uniqueness | [One Claim Per Role](#one-claim-per-role) | Implemented | Duplicate claims fail unless every site carries a `TAP-KNOWN-DUPE` group |
| req-tap-traceability-staleness | [Claims Detect Requirement Change](#claims-detect-requirement-change) | Implemented | Content hash of the requirement; a changed requirement orphans its claims |
| req-tap-traceability-minting | [Minted, Not Typed](#minted-not-typed) | Implemented | `scripts/implements-tag` emits the complete pre-hashed line |
| req-tap-traceability-scope | [Scarce And Targeted](#scarce-and-targeted) | Implemented | Claims are opt-in per requirement; absence is never a defect |
| req-tap-traceability-status | [Status Follows Evidence](#status-follows-evidence) | Implemented | A generated evidence report; `Verified` requires two independent evidence classes |
| req-tap-traceability-disputed | [The Disputed Status](#the-disputed-status) | Implemented | A fourth status bucket for spec-versus-implementation disagreement — claims are pointers, never resolution; every entry pairs with a review-ledger row |

---

### The Implementation Claim
----
RID: `req-tap-traceability-claim`
Status: `Implemented`

A **claim** is a tag in the docstring of the single function that is the authoritative derivation of
a requirement's fact:

```python
def grid_tables() -> set[str]:
    """Every table the grid owns.

    TAP-IMPLEMENTS: req-example-alpha@a3f9c1d2e5b7 (derivation) — the read backstop and the
        search-role grant both read this; neither may re-derive the set.
    """
```

Grammar: `TAP-IMPLEMENTS: <rid>@<hash> (<role>) — <reason>`.

#### Implementation

- **Docstring, parsed from source.** `ast.get_docstring()` reads it without importing the module,
  which keeps the scanner pre-boot-safe. The claim is **never** read from `obj.__doc__` at runtime:
  `python -OO` discards docstrings, and `functools.wraps` copies them, so a wrapper would silently
  inherit its wrapped function's claim.
- **The token is namespaced.** `IMPLEMENTS` alone means *interface conformance* to every human and
  model trained on JSDoc, Java or TypeScript; every surveyed traceability tool kept a tool-specific
  token for exactly this reason. `TAP-IMPLEMENTS` also distinguishes a claim from the ~1,800
  pre-existing prose RID citations, which must never be mistaken for one.
- **Em-dash before the reason**, matching `TAP-KNOWN-DUPE`, `TAP-CRED-BIND` and `guard-allow`.
- **Near-misses fail closed.** A malformed variant — wrong case, `TAP-IMPLEMENT:`, a missing `@`,
  an unparseable role — is a *failure*, not a silently-ignored line. A tag convention whose typos
  fail open is a tag convention that quietly does nothing.
- The scanner's needle is assembled by string concatenation so the scanner module and its tests
  never match their own source (the `known_dupes.py` idiom).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-traceability-claim-1 | Claim grammar | Implemented | A claim is `TAP-IMPLEMENTS: <rid>@<hash> (<role>) — <reason>` in a function, class or module docstring. | |
| req-tap-traceability-claim-2 | Parsed from source | Implemented | Claims are read via `ast.get_docstring()` from source, never from `__doc__` at runtime. | `-OO` and `functools.wraps` both corrupt the runtime reading. |
| req-tap-traceability-claim-3 | Near-misses fail closed | Implemented | A malformed claim fails the shape guard rather than being skipped. | ~60% of real-world tag failures are shape, not staleness. |

---

### Role Vocabulary
----
RID: `req-tap-traceability-roles`
Status: `Implemented`

A claim names a **role** from a closed vocabulary. Uniqueness is scoped per `(requirement, role)`,
because a requirement is frequently realized at more than one layer, all legitimately.

| Role | Means |
| --- | --- |
| `derivation` | The one place the requirement's *fact* is computed. The default and the common case. |
| `enforcement` | The guard, check or constraint that makes the requirement hold. |
| `surface` | The API, view or CLI through which the requirement is exposed. |

#### Implementation

- The vocabulary is **closed and validated**, following `TAP-CRED-BIND`'s provenance model: an
  unrecognized role fails rather than passing as free text.
- Scoping uniqueness to a role is a deliberate correction to strict single-claim uniqueness. In a
  layered architecture one requirement is often realized by a service function *and* a guard *and*
  an endpoint; a global one-claim rule would manufacture false failures and push legitimate cases
  into the duplicate escape hatch, corroding its meaning.
- OpenFastTrace and LOBSTER both assume *many* code sites per requirement; only StrictDoc's
  `role=Implementation` expresses "this is THE one." The role field is how that distinction is kept
  without over-constraining.
- Start narrow. Adding a role later is cheap; removing one after claims exist is not.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-traceability-roles-1 | Closed vocabulary | Implemented | A claim's role is one of `derivation`, `enforcement`, `surface`; anything else fails. | Free-text roles cannot be reasoned about. |
| req-tap-traceability-roles-2 | Role scopes uniqueness | Implemented | Uniqueness is evaluated per `(requirement, role)`, not per requirement. | Prevents false failures in a layered architecture. |

---

### One Claim Per Role
----
RID: `req-tap-traceability-uniqueness`
Status: `Implemented`

**Two claims naming the same `(requirement, role)` is a defect** — that is the anti-pattern this
spec exists to make structural. It fails unless *every* site in the group also carries a
`TAP-KNOWN-DUPE(<group-id>)` tag.

#### Implementation

- The escape hatch is not new machinery: it is the existing `req-tap-known-dupes` convention, whose
  guard independently requires every group to have **≥2 code sites and ≥1 spec mention**. So a
  permitted duplicate derivation is, by composition, one that is *documented in a spec* — "duplicate
  with an explanation" comes free, and neither guard has to grow an escape vocabulary of its own.
- Uniqueness keys on `(module, rid, role)`, deduplicated **within** a module. Conditional
  definitions (`if sys.version_info >= …:`) otherwise manufacture false duplicates — a failure mode
  mypy's ignore-tracking has a decade of open issues about.
- **Copy-paste propagation is the hazard this targets.** A tag travels with the code it is attached
  to, so duplicating a tagged function duplicates its claim. Clippy's original safety-comment
  request anticipated exactly this and never implemented it; OpenFastTrace names it twice in its
  status vocabulary. A uniqueness check is the countermeasure, and it is the reason this guard is
  worth more than the referential-integrity one.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-traceability-uniqueness-1 | Duplicate claims fail | Implemented | Two claims for one `(requirement, role)` in different modules fail the uniqueness guard. | The `Duplicate` defect. |
| req-tap-traceability-uniqueness-2 | Documented duplicates pass | Implemented | The failure clears when every site in the group carries a `TAP-KNOWN-DUPE(<group>)` tag, which is itself spec-documented. | Composition, not a second escape hatch. |
| req-tap-traceability-uniqueness-3 | Within-module dedup | Implemented | Multiple claims for one `(rid, role)` inside a single module are one claim, not a duplicate. | Conditional definitions. |

---

### Claims Detect Requirement Change
----
RID: `req-tap-traceability-staleness`
Status: `Implemented`

A claim carries a **content hash of the requirement it claims**. When the requirement's text
changes, every claim still carrying the old hash reports `Outdated` — the implementation must be
re-verified against the new text, then re-stamped.

#### Implementation

- The hash is `semantic_hash` (SHA-256, 12 hex) over the requirement's normalized body:
  whitespace-collapsed, with the `Status:` line **excluded** — status moves on its own lifecycle and
  is machine-derived, so including it would make every claim self-churn the moment a status advanced.
- **SHA-256, never MD5.** SQLite's scheme uses MD5; TAP runs FIPS-mode default-ON, where
  `hashlib.md5()` raises `UnsupportedDigestmodError`. The house digest already exists and is
  FIPS-clean.
- The hash lives in the **claim**, not in the RID. Baking a revision into the identifier is
  OpenFastTrace's model and works when adopted from day one; TAP has 1,800+ citations and a spec
  corpus keyed on readable slugs, so the identifier stays stable and only claim sites carry the
  hash — of which there are few by construction.
- Re-stamping is one command (`req-tap-traceability-minting`). The friction is deliberately in the
  *review* — deciding whether the change invalidates the implementation — not in the mechanics.

**Named residual.** The hash covers the whole requirement body, so a typo fix or a reworded sentence
invalidates claims exactly as a semantic change does. That is the accepted cost of the aggressive
setting: precision over churn, chosen because everything is in version control and re-stamping is
cheap. If the churn proves worse than the signal, the narrower variant is to hash only the
acceptance-criteria table — meaning lives there, narrative does not.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-traceability-staleness-1 | Changed requirement orphans claims | Implemented | Editing a requirement's body makes every claim carrying the prior hash report `Outdated`. | The ASPICE "existence is not consistency" principle. |
| req-tap-traceability-staleness-2 | Status and reflow do not churn | Implemented | A status change or pure whitespace reflow leaves the hash unchanged. | |
| req-tap-traceability-staleness-3 | FIPS-clean digest | Implemented | The hash is SHA-256 via `semantic_hash`; MD5 is never used. | `hashlib.md5()` raises under `TAP_FIPS=1`. |

---

### Minted, Not Typed
----
RID: `req-tap-traceability-minting`
Status: `Implemented`

`scripts/implements-tag` emits the complete, pre-hashed claim line. **A claim is never hand-typed.**

#### Implementation

- The shape is `scripts/log-site-id`'s exactly: bash plus inline stdlib `python3`, anchored at the
  git toplevel, bare copy-pasteable output, a header naming its RID and spec.
- Modes: emit a claim for a RID and role; `--check` to list stale and dangling claims; `--resync` to
  re-stamp a claim after a reviewed spec change.
- Advertised in the **Developer token tools** block of both `CLAUDE.md` and `AGENTS.md`, alongside
  `scripts/uuid7` and `scripts/log-site-id`. This is not decoration: the AGENTS.md evaluation
  measured tools *named* in the context file being used 1.6 times per instance versus under 0.01
  when unnamed.
- The rationale is Gerrit's `Change-Id`, which essentially never rots and draws no complaints
  because a hook mints it — versus the kernel's hand-typed `Fixes:`, which a bot has been correcting
  daily since 2013.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-traceability-minting-1 | Tool emits the complete line | Implemented | `scripts/implements-tag <rid> [role]` prints a full claim with the current hash. | |
| req-tap-traceability-minting-2 | Re-stamp is one command | Implemented | `--resync` updates a stale claim's hash after review. | Friction belongs in the review, not the mechanics. |
| req-tap-traceability-minting-3 | Advertised to agents | Implemented | The tool is listed in the developer-token-tools block of `CLAUDE.md` and `AGENTS.md`. | Named tools get used; unnamed ones do not. |

---

### Scarce And Targeted
----
RID: `req-tap-traceability-scope`
Status: `Implemented`

**Claims are opt-in per requirement. The absence of a claim is never, by itself, a defect.** This is
deliberately not a coverage program.

#### Implementation

- The initial target set is requirements that designate a **canonical derivation of a fact** —
  where a second implementation would be a real defect rather than a style question. The seed set is
  the collapses the duplication audit already proved: the grid-table classification, the
  secrets-root resolution, and the caller-context requirement. Tagging those locks in fixes that
  have already shipped.
- Security-surface, FIPS and service-boundary requirements are the natural next tranche.
- Rationale: SQLite's corpus measures 60–90% coverage on documents where a human deliberately built
  evidence, and 0–20% everywhere else — coverage does not accrete from ordinary work. A uniform
  thin layer is a worse position than a deep one where it matters. The regulated-traceability
  literature agrees from the other direction: mandated broad tracing is the thing that decays into
  ceremony, and assessors explicitly discourage tracing below the unit level.
- **What is deliberately not built:** a "needs no code" marker (`derived: true` in Doorstop terms).
  It becomes necessary only when coverage is *reported as a fraction*, which is the derived-status
  work; until a denominator exists there is nothing for it to correct.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-traceability-scope-1 | Absence is not a defect | Implemented | No guard fails because a requirement lacks a claim. | Opt-in by construction. |
| req-tap-traceability-scope-2 | Seed set is the proven collapses | Implemented | The first claims are placed on the single-source functions the duplication audit created. | Locks in already-shipped fixes. |

---

### Status Follows Evidence
----
RID: `req-tap-traceability-status`
Status: `Implemented`

A generated report shows every requirement's **declared** status beside the status its
**evidence** supports. And one status is gated: **`Verified` requires two independent evidence
classes** — an implementation claim *and* at least one acceptance criterion cited by a test.

#### Implementation

- **Two evidence classes**, deliberately: a requirement evidenced only by its own implementation
  is not verified. The implementation is the thing under test, not a check on it. SQLite renders
  a requirement green only at 2+ independent classes for the same reason, and grades evidence
  across four of them.
- The report is generated into this spec between `BEGIN/END GENERATED EVIDENCE` markers by
  `manage.py guards --sync-evidence`, with a drift test asserting the committed copy equals what
  the tree produces — the Validation Map's discipline, pointed at the requirement corpus. **That
  drift test is what makes this a consumer rather than an optional dashboard**: every durable tag
  convention in the wild earned its accuracy from something that visibly breaks when the tag is
  wrong, and inert tags rot.
- It lists only requirements that *carry* evidence, plus the contradictions — not all ~1,100 rows.
  A report nobody can read is a report nobody reads.

**What is deliberately not gated.** A requirement declared `Implemented` with no evidence does
**not** fail. Claims are opt-in and scarce (`req-tap-traceability-scope`), so faulting their
absence would contradict the convention and turn a targeted tool into a coverage program. That
number is reported as context — how much of the corpus has been deliberately targeted — and the
report says so in as many words. Similarly, evidence on a requirement still declared `Proposed`
is surfaced but never failed: a requirement can be partly built, and doctrine requirements are
cited as guidance rather than implemented.

What *is* gated is the strongest assertion the vocabulary offers. `Verified` was unused across
the entire corpus when this landed — zero occurrences — so the gate starts at a zero baseline,
fails closed from day one, carries no debt, and makes the terminal state earnable for the first
time.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-traceability-status-1 | Verified needs two classes | Implemented | A requirement declared `Verified` without both an implementation claim and a verified acceptance criterion fails. | Zero baseline; `Verified` was unused when this landed. |
| req-tap-traceability-status-2 | Report is generated and drift-tested | Implemented | The evidence report is regenerated by `manage.py guards --sync-evidence` and a test fails when the committed copy drifts. | The consumer that keeps the convention honest. |
| req-tap-traceability-status-3 | Missing claims are context, not defects | Implemented | No check fails because a requirement lacks a claim; the count is reported as targeting context. | Preserves `req-tap-traceability-scope-1`. |

---

### The Disputed Status
----
RID: `req-tap-traceability-disputed`
Status: `Implemented`

`Disputed` marks a requirement whose spec text and implementation **disagree**, where a human
has not yet ruled which is right. It is the state where "code exists" and "requirement
satisfied" have come apart — which is exactly why it fits none of the existing buckets, whose
shared function is to collapse those two questions into one.

#### Implementation

- **A fourth bucket, disjoint from built, unbuilt, and doctrine** (`DISPUTED_STATUSES` in
  `tap/spec_trace.py`). Each existing bucket's machinery is wrong for a dispute: the built
  bucket would blend a claimless dispute into awaiting-evidence debt and read a claimed one as
  satisfied; the unbuilt bucket treats attached evidence as an anomaly, when a dispute *should*
  carry a pointer to the contested code; the doctrine bucket rejects claims outright, erasing
  that pointer.
- **Claims are pointers, never resolution.** A claim on a `Disputed` requirement validates
  (unlike doctrine) and the report shows it — that is how a reader finds the disputing
  implementation — but no amount of evidence exits the status. The only exits are a human
  ruling that edits the **spec** (the content hash changes, every claim reports `Outdated`,
  the implementation is re-read against the new text) or the **code** (the re-stamp-after-review
  ceremony). Both exits force the re-read; the staleness machinery
  (`req-tap-traceability-staleness`) already implements the resolution workflow.
- **Every `Disputed` requirement pairs with a record**: a row in the requirement-review ledger
  (`docs/misc/doc-tap-requirement-review-ledger.md`) and a `Requirement Review Needed` section
  in the owning spec naming the code site and the disagreement. A dispute with no record is a
  label, not a dispute.
- The evidence report carries a dedicated `Disputed` section and a headline count. The count is
  the one number that matters for this bucket, and it should trend to zero. Statuses outside
  the four buckets are invisible to every derived count — for a status whose entire purpose is
  visibility, falling into the invisible pile is the failure mode this bucket exists to avoid.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-traceability-disputed-1 | Own bucket, own count | Implemented | A `Disputed` requirement appears in none of the built/unbuilt/doctrine coverage counts; the report carries a dedicated section and headline count. | Visibility is the point. |
| req-tap-traceability-disputed-2 | Claims are pointers, never resolution | Implemented | A claim on a `Disputed` requirement validates and is listed, but no evidence exits the status — only a human ruling that edits spec or code does. | Both exits force a re-read via the staleness hash. |
| req-tap-traceability-disputed-3 | Ledger pairing | Implemented | Every `Disputed` requirement has a row in the requirement-review ledger and a section in the owning spec naming the code site and the disagreement. | The record is the dispute; process-checked in review, not guard-enforced yet. |

## Evidence Report

Generated — do not hand-edit. Regenerate with `manage.py guards --sync-evidence`.

<!-- BEGIN GENERATED EVIDENCE — manage.py guards --sync-evidence -->

**1129** requirements · **19** standing doctrine · **0** disputed · **20** carry evidence · **1** carry both classes · **503** declared built with none.

Separate facts, deliberately not blended into one percentage. **Doctrine** is outside the coverage question — in force now, never "completed", expecting conformance rather than an implementation. **Disputed** marks a spec-versus-implementation disagreement awaiting a human ruling — its claims are pointers to the contested code, never resolution, and the count should trend to zero. **Declared built with none** is context, not a defect list: claims are opt-in and scarce by design (`req-tap-traceability-scope`), so it measures how much of the corpus has been deliberately targeted, not how much is wrong. Collapsing these into a single coverage score is what makes such a score meaningless.

| Requirement | Declared | Derived | Implementation | Verified by |
| --- | --- | --- | --- | --- |
| `req-cicd-dco-signoff` | — | Tested | — | `req-cicd-dco-signoff-2`, `req-cicd-dco-signoff-3`, `req-cicd-dco-signoff-4` |
| `req-grid-edge-schema-required` | Proposed | Implemented | `validate_edge_properties` | — |
| `req-grid-service-pipeline-context` | Implemented | Implemented | `require_caller_context` | — |
| `req-grid-table-classification.sec` | Implemented | Verified | `classified_models` | `req-grid-table-classification.sec-6` |
| `req-grift-envelope-validation` | In Development | Implemented | `parse_envelope_for_write` | — |
| `req-plugin-load-v0-ready-chain` | Implemented | Tested | — | `req-plugin-load-v0-ready-chain-1`, `req-plugin-load-v0-ready-chain-2` |
| `req-tap-auth-passkey-dev-bootstrap` | Implemented | Tested | — | `req-tap-auth-passkey-dev-bootstrap-1`, `req-tap-auth-passkey-dev-bootstrap-10`, `req-tap-auth-passkey-dev-bootstrap-11`, `req-tap-auth-passkey-dev-bootstrap-13`, `req-tap-auth-passkey-dev-bootstrap-14`, `req-tap-auth-passkey-dev-bootstrap-15`, `req-tap-auth-passkey-dev-bootstrap-3`, `req-tap-auth-passkey-dev-bootstrap-4`, `req-tap-auth-passkey-dev-bootstrap-6`, `req-tap-auth-passkey-dev-bootstrap-7`, `req-tap-auth-passkey-dev-bootstrap-8`, `req-tap-auth-passkey-dev-bootstrap-9` |
| `req-tap-auth-passkey-enrollment` | Proposed | Tested | — | `req-tap-auth-passkey-enrollment-1`, `req-tap-auth-passkey-enrollment-2`, `req-tap-auth-passkey-enrollment-3`, `req-tap-auth-passkey-enrollment-6`, `req-tap-auth-passkey-enrollment-8` |
| `req-tap-auth-passkey-genesis` | Proposed | Tested | — | `req-tap-auth-passkey-genesis-3`, `req-tap-auth-passkey-genesis-4` |
| `req-tap-auth-passkey-rollout` | Proposed | Tested | — | `req-tap-auth-passkey-rollout-2` |
| `req-tap-auth-passkey-webauthn` | Proposed | Tested | — | `req-tap-auth-passkey-webauthn-10`, `req-tap-auth-passkey-webauthn-11`, `req-tap-auth-passkey-webauthn-13`, `req-tap-auth-passkey-webauthn-3`, `req-tap-auth-passkey-webauthn-7`, `req-tap-auth-passkey-webauthn-8` |
| `req-tap-cares-secrets-files` | Implemented | Implemented | `<module>` | — |
| `req-tap-cares-secrets-root-resolution` | Implemented | Implemented | `resolve` | — |
| `req-tap-health-bootcheck` | Implemented | Tested | — | `req-tap-health-bootcheck-1`, `req-tap-health-bootcheck-2`, `req-tap-health-bootcheck-3`, `req-tap-health-bootcheck-4` |
| `req-tap-health-exposure` | Implemented | Tested | — | `req-tap-health-exposure-2`, `req-tap-health-exposure-3` |
| `req-tap-health-probe-registry` | Implemented | Tested | — | `req-tap-health-probe-registry-1`, `req-tap-health-probe-registry-5`, `req-tap-health-probe-registry-6`, `req-tap-health-probe-registry-8` |
| `req-tap-health-probes` | Implemented | Tested | — | `req-tap-health-probes-3`, `req-tap-health-probes-7`, `req-tap-health-probes-8`, `req-tap-health-probes-9` |
| `req-tap-health-selection` | Implemented | Tested | — | `req-tap-health-selection-1`, `req-tap-health-selection-2`, `req-tap-health-selection-3`, `req-tap-health-selection-4`, `req-tap-health-selection-5` |
| `req-tap-health-service` | Implemented | Tested | — | `req-tap-health-service-3`, `req-tap-health-service-5` |
| `req-web-page-dim` | Implemented | Implemented | `<module>` | — |

**Disputed** — the spec and the implementation disagree; each entry pairs with a row in the requirement-review ledger and a section in its owning spec (`req-tap-traceability-disputed`):

None.

**Declared unbuilt, but evidence exists** — reported, never failed; a requirement can be partly built, and a doctrine requirement is cited as guidance:

| Requirement | Declared | Derived |
| --- | --- | --- |
| `req-grid-edge-schema-required` | Proposed | Implemented |
| `req-tap-auth-passkey-enrollment` | Proposed | Tested |
| `req-tap-auth-passkey-genesis` | Proposed | Tested |
| `req-tap-auth-passkey-rollout` | Proposed | Tested |
| `req-tap-auth-passkey-webauthn` | Proposed | Tested |

**Declared `Verified` without two evidence classes** — this one fails (`req-tap-traceability-status`):

None.

<!-- END GENERATED EVIDENCE -->

## Relationship To Other Specs

- **`spec-docs.md`** (`req-docs-rid-integrity`) — the first half: every citation resolves. This spec
  promotes a chosen few of those citations from mention to claim, and reuses its parser
  (`tap.spec_trace`) and its reserved `req-example-*` placeholder namespace.
- **`spec-tap-known-dupes.md`** (`req-tap-known-dupes`) — the exact complement, and the escape hatch
  for `req-tap-traceability-uniqueness`. That convention declares a duplicate that must exist; this
  one declares an original that must not be duplicated.
- **`spec-dev-validation.md`** — the guards join the harness and the generated Validation Map; the
  derived-status report follows its generated-artifact-is-the-system-of-record pattern.
- **`spec-tap-testing.md`** (`req-tap-test-spec-linkage`) — the verification half. `@pytest.mark.spec`
  links a test to an acceptance criterion; a claim links a function to a requirement. Derived status
  needs both, and treats a requirement evidenced only by its own implementation as unverified.
- **`spec-sphinx-capability-docs.md`** (`req-sphinx-docs-capability-blocks`) — **superseded by this
  spec.** That requirement proposed a `:implements:` field inside Sphinx-Needs capability blocks; it
  was never built, and two docstring conventions for one relationship would be precisely the
  duplication this work exists to prevent.
- **`spec-tap-callsite-identity.md`** — the anchor/discriminator model the guards' baselines follow:
  keys are structural, never line numbers.

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
