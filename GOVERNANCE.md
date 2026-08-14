# Governance

TAP is young and small. This document describes how decisions are actually
made today — not an aspirational structure — including the parts that are
uncomfortable to write down, like what happens when the person currently
making most of the decisions stops.

## Roles

### Project Steward

The Project Steward is **Unified Systems LLC**, acting through a written
resolution of its sole member or through a successor governance process
expressly authorized by such a resolution.

The Steward holds legal authority: licensing and any future license migration
(bounded by the terms in `CONTRIBUTING.md`), custody of the project's assets —
the `unified-systems-com` organization, package and registry namespaces,
domains, and signing material — and appointment to the role below.

The Steward does not direct day-to-day technical work. The Steward is a
different person from the Philosopher King for Now, which is deliberate: it
means the constraints on relicensing in `CONTRIBUTING.md` are enforced by
someone other than the person who would ever be in a position to want them
relaxed.

### Philosopher King for Now

Technical direction, specification canon, and code of conduct enforcement rest
with one person, the **Philosopher King for Now**. Other projects call this
role the BDFL — benevolent dictator for life. The difference is deliberate,
and is the substance of what follows.

**The claim is epistemic.** Authority rests on knowing the system, not on
ownership, seniority, or good intentions. That claim is falsifiable, and it is
transferable: anyone who comes to know the system can come to hold it.

**The claim is constrained by publication.** Judgment takes effect only once
it has been written down where it can be inspected — as a specification
requirement, a guard, or a test. See "How a decision becomes binding" below.
A ruler obliged to publish his reasoning before it binds anyone is limited in
a way that a benevolent dictator is not.

**The tenure is explicitly temporary.** "For Now" is not modesty; it is a
removability clause, and the conditions under which it fires are stated in
"Continuity" below. The role anticipates its own end rather than requiring an
escape to be improvised during a crisis.

The Philosopher King for Now is appointed by, and serves at the pleasure of,
the Steward.

### Contributors and delegated sessions

Contributors decide within the scope of the work they take on. They do not
need permission to exercise judgment there; see "Subsidiarity" below.

TAP is developed with substantial help from AI coding agents working
autonomously in isolated session worktrees. They are real subordinate bodies
under the subsidiarity rule, and the line governing them is that **competence
devolves and accountability does not.** An agent may decide within its scope.
It may not set canon, advance `main` outside the gate, certify the Developer
Certificate of Origin, or widen its own mandate. Work produced under a
person's delegation is that person's work and that person's responsibility.

### Plugin maintainers

Plugins live in their own repositories with their own tests, releases, and
manifests. As plugins acquire maintainers other than the core project, those
maintainers hold decision authority over their plugin, bounded by the
interfaces and posture requirements core enforces globally.

## How a decision becomes binding

Specifications are the canonical source of truth. A decision that has not been
written where it can be inspected is not yet a decision — it is an intention,
and it binds nobody.

This is the project's oldest working rule and the real check on concentrated
authority. It also makes governance auditable: because decisions are recorded
as requirements with stable identifiers, it is possible to see *which level* a
decision was taken at, and to argue that it was taken at the wrong one.

## Subsidiarity

Decisions belong at the **narrowest level competent to make them**. A higher
level absorbing a decision that a lower level could have made is treated as a
defect in this project, not as tidiness.

Three rules follow:

- **Escalation carries a burden.** Raising a decision to a higher level means
  stating why the lower level could not make it. Where the decision lands in
  canon, that reason is recorded with it.
- **Anyone may challenge the level.** Arguing that a decision was taken too
  high is legitimate, in-scope feedback — open an issue.
- **The higher level owes help.** *Subsidiarity* comes from *subsidium*,
  reserve troops. The obligation is two-sided: core may not absorb what
  belongs lower, and core owes lower levels the scaffolding that lets them
  succeed there. Published specifications, machine-legible metadata, guards,
  plugin release tooling, and shared CI configuration are that obligation
  being discharged, not conveniences.

The house pattern for expressing this in code is **declare / enforce /
waive**: the lower level *declares* its posture, the system *enforces*
globally, and only the operator *waives* — explicitly, narrowly, with a
recorded reason. A component can never exempt itself. The FIPS posture
declaration in plugin manifests is the reference implementation.

## Disputes

Ordinary technical disagreement is resolved by the Philosopher King for Now.
That is what the role is for, and being overruled is a normal outcome rather
than a grievance.

Everything else — disputes about the decisions or conduct of the maintainer
role itself, and conduct reports generally — goes to the **oversight body**:
the leadership of Unified Systems LLC together with the Philosopher King for
Now. The LLC's internal composition may change without changing this document;
whoever leads it at the time holds that seat.

**Recusal.** Anyone on the oversight body with a stake in a matter recuses
from it. Recusal is expected and implies no wrongdoing — a maintainer whose
own decision is under review recuses as a matter of course.

**Replacement.** The remaining members do not simply decide alone. They select
an **independent reviewer** — someone who is neither part of the LLC's
leadership nor a maintainer of this project, and who holds no material stake
in the outcome — and name that person publicly in this document. The same
mechanism resolves a deadlock: where the body cannot reach agreement, it
appoints an independent reviewer whose determination settles the matter.

Where every member is recused, the Steward still makes the appointment,
because someone must hold the power to appoint — but takes no part in the
decision itself.

The appointment is public; the matter need not be. Where the dispute is a
conduct report, the confidentiality owed to the reporter under
`CODE_OF_CONDUCT.md` governs what is said about the substance.

**Independent reviewers appointed to date:** none.

Independently of all of the above, GitHub's own abuse reporting and Terms of
Service apply to this repository and are not within this project's control.
Anyone uncomfortable raising a matter internally may use that channel.

## Continuity

Authority under this document rests on three conditions together: **knowledge**
of the system, the **capacity** to be accountable for it, and the
**willingness** to be. Knowledge alone is not sufficient — which is why
autonomous agents hold delegated competence but never standing.

Two conditions can lapse, and each has its own relief valve, because one is
known from the inside and the other is visible from the outside.

**Willingness — declared.** The Philosopher King for Now may hand back any
part of the role at any time, in writing, to the Steward. This is expected to
happen eventually and is not treated as abandonment; a maintainer who has
stopped wanting the work but stays nominally in place is the worst outcome for
everyone. Withdrawal may be partial: handing off code maintenance while
retaining direction, or the reverse, is a normal application of subsidiarity
rather than a failure of the role.

**Capacity — observed.** The Steward may declare the role vacant and appoint a
successor. If the Steward is also unavailable, a dormancy backstop applies:
where there has been no response from either party to a governance-level
request for **90 days** and no merge to `main` for **180 days**, the project is
dormant, and the continuity provisions below take effect without further
declaration. The thresholds are deliberately long and deliberately objective,
so that invoking them is an observation rather than a coup.

**What continuity actually moves.** The Apache License already guarantees that
anyone may fork this project at any time, for any reason. What a fork cannot
take is the name, the organization, the package and registry namespaces, the
domains, and the signing material. Those are the Steward's, and moving them —
to a successor maintainer, to a foundation, or by blessing a fork as the
continuation — is what these provisions are for.

That places a standing obligation on the project: access to those assets must
be held by more than one person and must be documented well enough to be
exercised. A continuity clause that no one can act on is decoration.

## Amending this document

Changes to this document are made by the Philosopher King for Now with the
Steward's agreement, and ride the same pull request and review process as any
other change.
