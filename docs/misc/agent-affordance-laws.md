# Programmatic Actor Affordance Laws

Captured 2026-06-29, during the `spec-tap-health-v0` review. This is a
thinking document, not a spec and not scheduled implementation. It complements
[Agent-Legibility Doctrine](agent-legibility-doctrine.md) and
[Future Seam: TAP AI Integration](tap-ai-integration-notes.md).

The immediate trigger was health: a future Paladin-style agent should be able to
read instance health and decide what it can safely explain, recommend, or
propose. The correct response is not to stuff speculative AI fields into the
health system before `tap_ai` exists. The correct response is to capture the
affordance doctrine now, so future AI and programmatic surfaces have a shared
shape to aim at.

The standing question:

> Could a programmatic actor understand what this surface means, what it is
> allowed to do with it, and when it must stop, without reading Python or
> parsing a paragraph?

Where the answer is "no," the affordance is incomplete.

## Prior Art Inputs

These are vocabulary inputs, not code sources.

- **[Model Context Protocol tools](https://modelcontextprotocol.io/docs/concepts/tools)**
  separate tool descriptions, input schemas, output shapes, annotations, and
  execution controlled by the host. TAP should make capability meaning explicit
  in metadata rather than implicit in code.
- **[OpenAI Apps SDK tool descriptors](https://developers.openai.com/apps-sdk/reference)**
  carry model-visible descriptors, structured output, component metadata, and
  annotations such as read-only behavior. This points toward declared effect
  classes and machine-readable results rather than prose-only tool contracts.
- **[Kubernetes operators/controllers](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)**
  encode operational judgment as loops over declared state and observed status.
  They are the best non-AI analogy for Paladin: observe, compare, reconcile or
  escalate, and report status.
- **[OpenTelemetry status and attributes](https://opentelemetry.io/docs/specs/otel/trace/api/#set-status)**
  are a useful warning: machine systems branch on stable codes and fields; prose
  is explanatory context, not the control surface.

## The Zeroth Law

**TAP remains the control surface.**

The model is an engine inside TAP's boundaries. It is never the boundary itself.
TAP owns identity, authorization, projection, persistence, proposal/apply,
redaction, audit, lifecycle, and final authority. A model may recommend, draft,
summarize, classify, or propose through TAP-controlled affordances. It does not
receive raw credentials, bypass the service layer, or become the policy engine.

## The Laws

### First Law: Preserve Truth

A programmatic actor must not make the instance less true.

It must not hide broken state, over-green a degraded system, silently drop
uncertainty, collapse evidence into vibes, or turn "unknown" into "healthy" for
convenience. Unknown stays unknown. Degraded stays degraded. A failing check
keeps its evidence. A partial result stays partial. If the actor cannot verify a
claim, the output says so.

Implication: health, readiness, collector self-tests, auth checks, and validation
surfaces need explicit status vocabularies, stable failure codes, observed
timestamps, and evidence references.

### Second Law: Stay Within Authority

A programmatic actor must not act beyond its declared authority.

Every capability exposed to an actor needs an identity, authorization boundary,
scope, and effect class. The actor should know whether a tool is read-only,
idempotent, mutating, destructive, external-world-touching, or privileged before
it calls it. TAP must enforce that boundary server-side; the declaration helps
the actor behave, but enforcement belongs to TAP.

Implication: future tool and capability manifests should include effect class,
required capabilities, projection tier, input schema, output schema, and
confidentiality expectations.

### Third Law: Prefer Proposals To Actions

A programmatic actor must prefer a reviewable proposal over a direct action.

For v0, graph mutation is out of scope. Longer term, changes to TAP-managed
state, files, external systems, or user-visible behavior should flow through
proposal, preview, approval, apply, history, and provenance unless a later spec
explicitly grants a narrower autonomous action. The default safe path is
proposal-first because it is inspectable, reversible where the substrate allows,
and attributable.

Implication: GRIFT-batch-as-proposal remains the natural write path for
grid-shaped changes, and Paladin-style remediation should start as detection,
explanation, recommendation, and issue/proposal creation.

### Fourth Law: Structure Before Prose

A programmatic actor must receive structured meaning before human prose.

Prose is for explanation, summarization, and human review. It is not the thing a
programmatic actor should parse to decide what happened. Machine surfaces should
prefer stable field names, schemas, enumerated codes, timestamps, entity refs,
run IDs, source IDs, evidence refs, remediation refs, and docs refs. Human
strings should sit beside those fields, not replace them.

Implication: machine views are first-class siblings of human views. An HTML page,
panel, health report, collector readiness block, or task run should have a data
twin when programmatic actors are expected to consume it.

### Fifth Law: Respect Projection Boundaries

A programmatic actor must not receive more sensitive context than its task and
authority require.

The same underlying report may have multiple projections: public/coarse,
operator-rich, agent-safe, plugin-scoped, or internal-only. A projection boundary
is a security boundary. It strips or reshapes detail, reasoning, evidence,
source paths, account identifiers, user data, and secret-adjacent context
according to caller trust. Redaction is a contract, not a courtesy.

Implication: "rich inside, projected outside" is the right shape, but rich
diagnostic collection must be paired with explicit projection tests.

### Sixth Law: Leave A Trail

A programmatic actor must make its work observable.

Runs should have identity, purpose, inputs, tool calls, outputs, status,
duration, model/provider where relevant, cost where relevant, and human approval
state where relevant. The trail should let a human, another actor, or a future
Paladin answer: what happened, who or what initiated it, what authority was used,
what changed, what was merely suggested, and what remains unresolved?

Implication: activity records and provenance are not AI decoration. They are the
surface that makes programmatic work reviewable and trustworthy.

### Seventh Law: Know When To Stop

A programmatic actor must have lifecycle limits and escalation paths.

Every agent run or programmatic loop needs a bounded job, budget, timeout,
context-window strategy, retry posture, confidence threshold, and stop/escalate
condition. Long-running agents need health checks of their own. An actor that
cannot make safe progress should report a blocked state rather than continue
guessing.

Implication: agent lifecycles need explicit classes: one-off, as-needed,
long-running, manager, and collaborative. The lifecycle class determines budget,
memory, health, stop rules, and escalation.

## Applying This To Health

Health is the first concrete pressure test for these laws.

The near-term health system should stay modest: internal service, first-party
probe registry, CLI projection, spawn gate, and no default unauthenticated rich
endpoint. But when a future agent consumes health, it should not need bespoke
parsing of `detail` strings. It should see stable status fields and codes, know
which checks are critical, know which subsystem owns each check, receive only the
projection it is authorized to see, and be pointed toward safe next steps.

That does not mean `spec-tap-health-v0` needs full AI fields today. It means the
health report should avoid shapes that would make those future affordances hard:
opaque prose-only results, status values without codes, hidden criticality,
unbounded plugin probes, caller identity mixed with probe execution identity, or
rich context with no projection discipline.

## Design Smells

- A programmatic consumer must parse a sentence to know the error class.
- A tool can mutate or touch the external world but its descriptor does not say
  so.
- A report says "healthy" while known degraded or unknown subcomponents are
  hidden elsewhere.
- A surface has a human HTML view but no structured machine view.
- Diagnostic context is collected before anyone has defined the projections that
  can safely expose it.
- A model is trusted to self-limit instead of TAP enforcing limits.
- A future remediation path starts with "the agent just fixes it" instead of a
  proposal spine.

## Future Spec Hooks

When `tap_ai` and Paladin move from seam to build, this note should turn into
requirements for:

- capability/tool descriptors and effect classes.
- machine-view/data-twin conventions for human surfaces.
- programmatic status report shape: stable codes, status vocabulary, evidence,
  remediation refs, projection tiers.
- agent lifecycle classes and stop/escalation rules.
- proposal/preview/approve/apply flows for write-capable agents.
- Paladin detection and safe-remediation contracts.
- projection tests for rich diagnostic surfaces.
