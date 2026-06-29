# Future Seam: TAP AI Integration

Captured 2026-06-14 from a stream-of-consciousness design note. This is a
thinking document, not a spec, not scheduled implementation, and not an
architecture decision record. It complements
[Agent-Legibility Doctrine](agent-legibility-doctrine.md): that earlier note is
about making TAP understandable and usable by a future grid-native agent; this
note is about where AI integration itself belongs in TAP and what shapes it may
need. It is also complemented by
[Programmatic Actor Affordance Laws](agent-affordance-laws.md), which captures
the standing rules for AI/programmatic-facing surfaces: TAP remains the control
surface; actors need structured meaning, authority declarations, projection
boundaries, audit trails, proposal-first writes, and explicit stop conditions.

Roadmap posture: AI integration is strategically central but must not become a
VC-style "AI everywhere" distraction. For the August product horizon, TAP should
prepare a first-class but optional AI capability that can help sell, explain,
guide, and extend the platform without making AI a hard dependency of every
deployment.

## Core Thesis

TAP is an entry into the post-ChatGPT, post-March-26-capability-inflection
discussion about how AI systems become real-world infrastructure rather than
clever, single-user tools.

Claude Code and app-style agents are a strong early signal, but their operating
mode is still loose: agents do stuff, usually for one human, inside one session,
with unclear repeatability, coordination, sharing, extension, lifecycle, or
cross-instance behavior.

TAP's contribution is not simply "put a chatbot on a graph." The grid is the
underlying data model and coordination substrate. TAP can give AI systems shape:
durable context, discoverable capabilities, typed graph state, auth boundaries,
service-layer mutation rules, provenance, paths, skills, agent collaboration,
and cross-instance structure.

The models are the steam engine. TAP should be the locomotive: a platform built
for the engine instead of a horse-drawn buggy with a powerhouse strapped to it.

## Why AI Is First-Class But Optional

`tap_ai` should be a native, first-class core application, but optional at
deployment time.

That sounds contradictory only if "first-class" means "mandatory." It should
not. TAP has good reasons to support static deployments that do not want or need
runtime AI integration. Those instances may still be built, configured,
debugged, and maintained with AI-assisted development outside the instance, but
they should not have to carry model integrations, API keys, agent runtime code,
or provider-specific behavior just to operate.

The likely implementation posture:

- Build `tap_ai` as a native app, similar in altitude to `tap_web` and
  `tap_api`: above the grid, using the grid, not required for the grid to exist.
- Treat it as a primary/dominant capability path for most rich deployments.
- Prepare for a deployment profile where it is disabled or not shipped.
- Keep the core grid usable in the simplest possible way.

This preserves TAP's simplicity discipline while acknowledging that AI will
almost certainly become one of the most important ways people interact with the
system.

## Model Constraints TAP Must Design Around

Current LLM-based systems are immensely powerful, but they have known limits.
TAP should treat those limits as design inputs, not temporary embarrassments to
paper over.

### Limited Attention

Context windows are finite, even as they grow. They also degrade near the tail:
large, complex, long-running tasks can get fuzzy or flaky as the model's
attention fills up.

Large real systems will exceed any single model context. TAP therefore needs
structured ways to wire context in and out while the model works: scoped reads,
summaries, paths, machine views, capability manifests, queryable history, and
durable state. The model's spotlight of attention is powerful but bounded; the
grid should be the larger memory and coordination field.

### Fast-Changing Engines

Models change all the time. Capabilities, providers, APIs, costs, and behavior
are under active development, with heavy competition.

TAP should avoid static integrations that overfit one provider or one moment.
Provider-specific support is necessary, but the platform concept should be
stable above model churn: standard agent APIs, standard runtime configuration,
standard logging, standard auth, standard proposal/application flows, and
plugin-extensible provider integrations.

### No Native Persistence

Models wake up fresh. They are very smart, but they need initial context.

That context has to come from somewhere. The better the "egg," the better the
"chicken." TAP can supply that egg: keystones, specs, capability discovery,
paths, history, prior conversations, task state, skill graphs, plugin docs,
machine-readable pages, and domain data.

The next turn of the wheel is even more interesting: an agent that can improve
the context substrate for future agents. A chicken that can permute the egg
makes the next chicken better.

### More Than Chat

AI integration should not collapse into a chat box.

A chat UI is the obvious v0 surface, but the real opportunity is structured
agent operation: skills as data, agent classes, agent lifecycles, collaboration,
delegation, cross-instance coordination, proposals, reviews, user-guided
navigation, long-running monitors, and specialized agents that understand a
bounded job.

Current agent files and skills are powerful but uncoordinated. TAP can organize
them on the grid, relate them to plugins, build skill trees, give them auth
boundaries, and make them observable.

## `tap_ai` as a Native App

`tap_ai` likely defines the standard ways agents interact with TAP:

- API calls and service-layer entry points.
- Agent, skill, task, run, memory, and conversation node/edge types.
- Standard provider/model configuration references.
- Authenticated and authorized execution contexts.
- Logging, audit, and observability conventions.
- Proposal/preview/approve/apply flows for future writes.
- Discovery surfaces for available agents, tools, skills, and model backends.

Boot/config implications:

- The bootloader should eventually support AI-specific configuration.
- Provider API keys live in secrets, not on the grid.
- Local model execution services are referenced by configured paths or runtime
  service keys, not arbitrary executable blobs in graph data.
- AI capability classes can be enabled/disabled per deployment profile.
- Provider integrations may eventually behave like authN providers: shipped as
  core support where appropriate, extended through plugins where necessary.

This should align with the broader TAP rule: interfaces define authentication
and request identity; the service layer implements authorization and graph
mutation policy.

## Agents as Plugins

TAP will likely need an agent plugin contract. Agent capabilities may ship as
standalone plugins or as part of domain plugins.

The shape will become clearer during implementation, but likely contract areas
include:

- Initiation: what event, user action, schedule, flaw, path break, or grid
  signal starts the agent?
- Agent configuration: which model/provider/backend, settings, tools, limits,
  and provider-specific knobs does it use?
- Pre-context: what gets gathered before the model starts so it understands its
  job and local situation?
- AuthN/AuthZ: which user, service identity, role, dimensions, and permissions
  bound the agent?
- Health and duration: how long can it live, how is context-window pressure
  managed, when is it stopped, and how does TAP avoid stale or runaway agents?
- Discovery and interaction: how does an agent learn which agents/tools/skills
  are available, and how can agents communicate securely?
- User-facing actions: what does the human see in `tap_web`, beyond chat?
  Navigation, explanation, guided walkthroughs, proposals, and live status all
  belong here.
- Agent hub: a central surface for available agents, active runs, health,
  current tasks, permissions, and recent outcomes.

Skills probably deserve grid identity. Skill nodes, skill trees, and edges
between skills could make agent capability legible, composable, searchable, and
shareable. This is also where paths may become important: skills, workflows,
plans, loops, and branches are naturally path-shaped.

## Agent Lifecycles

Not all agents are the same thing. TAP should name lifecycle classes rather than
pretending every agent is a chatbot session.

### One-Off Agents

Quickly fired up to explain, inspect, summarize, or help decide something. They
exist for the moment and do not need durable identity beyond run records,
provenance, and any saved conversation/task output.

### As-Needed Agents

Triggered by events or user actions to perform a bounded job. They may retain
state about a user, system, or recurring task so they can be started and stopped
without losing their role-specific context.

### Long-Running Agents

Persistent, dependable agents scoped to a specific use case. They need context
management beyond a single model window, health checks, memory discipline,
authorization boundaries, and clear shutdown/escalation behavior.

The lifecycle distinction matters because auth, memory, observability,
provider/model selection, cost control, and failure handling are different for
each class.

## Candidate Agent Families

These are examples, not committed scope.

### SecSystem and SecUnits

A persistent security capability for an instance. The SecSystem watches security
signals, flaws, logs, collector outputs, and graph changes. It can fire up
shorter-lived SecUnit agents to investigate bounded situations, gather context,
draft findings, propose remediation, or escalate to humans.

### User Guide

A guide agent for users exploring an instance. It understands the instance's
knowledge, pages, paths, and story surfaces, and can guide a user through them.

Interactions can persist so the guide understands who the user is, what they
have seen, what they care about, and where they might want to go next. This is
personalization as a grid-native guide, not a generic chatbot bolted onto a
site.

### Paladin

A self-healing and monitoring agent for the TAP instance itself. It detects
errors, flaws, unhealthy state, broken paths, collector failures, and other
concerns.

Near-term Paladin behavior should be cautious: detect, explain, recommend, and
raise issues. Any autonomous remediation or code-change behavior requires
explicit specs and approval. Longer-term, Paladin may propose local fixes, open
reviewable changes, or send upstream patches through the same
propose-preview-approve discipline as other write-capable agents.

### Plugin Builder

An agent that knows how to build TAP plugins, collectors, pages, panels, paths,
GRIFT, schemas, and tests. It helps extend an instance from inside TAP.

This is a major expression of the agent-legibility doctrine: TAP eventually gets
built from inside TAP. Plugin Builder crosses the current "code wall" by
providing a guided, reviewable route from grid-native intent to plugin changes.

### Managers

Overseer agents for multiple agents across one or more instances. Examples:

- A fleet-wide SecSystem coordinating per-instance SecSystems.
- Paladin coordination across customer instances.
- Shared capability management across many deployments.

This points at cross-instance coordination, but should stay future-facing until
the single-instance model is solid.

### Collaborative Agents

Multiple agents or models working from the same base context to evaluate,
critique, reconcile, or disagree.

Instead of manually copy-pasting between chat windows, TAP can coordinate the
collaboration on-grid: same context packet, separate agent runs, recorded
outputs, disagreement surfaces, and an explicit human decision point.

## Relationship to Paths

AI integration and paths are entangled.

Agents need paths to understand systems as more than piles of facts:

- Build and deploy flows.
- Evidence chains.
- User journeys.
- Ownership and dependency chains.
- Incident timelines.
- Model/data/tool lineages.
- Skill trees and agent workflows.

Conversely, agents may be one of the primary ways paths are authored, explained,
materialized, repaired, and traversed. A guide agent follows paths. A SecUnit
agent investigates along paths. A Plugin Builder uses skill paths. Paladin
notices broken paths. Managers coordinate paths across instances.

This is likely where branch, loop, and "paths on paths" semantics become
practical rather than abstract.

## Guardrails and Non-Negotiables

The existing TAP rules still apply:

- No autonomous graph mutation in v0.
- Future writes go through proposal, preview, human approval, service-layer
  apply, history, and provenance.
- Secrets stay in trusted runtime configuration, not graph data.
- Provider credentials are never handed to the model.
- Agent reads must be authenticated, scoped, and audited.
- Agent actions must be observable.
- Plugins declare their capabilities; no hidden reach-in dependencies.
- AI behavior should be model/provider-portable where practical.

The model should be treated as a powerful bounded engine inside TAP's control
surfaces, not as the control surface itself.

## Why This Belongs Last

AI integration is the last major TAP puzzle piece, and that timing makes sense.

The scaffolding, data models, service layer, plugins, graph read/write surfaces,
GRIFT, Gryphon, history, dimensions, pages, and visualization were originally
imagined as human-operated machinery. AI does not invalidate that work. It
reveals why the foundation mattered.

TAP was never really centered on humans as the only actors. It was centered on
mapping systems, relationships, operations, and "the way." Who reads, creates,
changes, or navigates the map is a second-order question.

The fact that TAP's underlying concepts survived the AI black-swan moment is a
good sign. The same structural challenge TAP was built to address -- durable,
legible, actionable system maps -- is now one of the central challenges facing
AI systems. That is the opportunity: get in early and make noise with a platform
that gives agents a real substrate instead of another shapeless chat box.

## Future Spec Hooks

Likely specs or spec sections when this becomes implementation work:

- `tap_ai` app boundary: optional core app behavior, deployment profile, and
  disabled/not-installed semantics.
- AI boot configuration: provider keys, local model service references,
  capability enablement, and secret handling.
- Agent model: agent types, runs, tasks, conversations, memory, skill nodes,
  tool/capability discovery, and lifecycle state.
- Agent plugin contract: manifests, declared capabilities, triggers,
  pre-context, model/provider requirements, auth requirements, and UI surfaces.
- Agent auth: request identity, delegated user/service identity, dimensions,
  scoped reads, audit logging, and future write approval.
- Programmatic actor affordances: tool/capability effect classes, machine-view
  conventions, stable status/error codes, projection tiers, audit trails, and
  lifecycle stop/escalation rules.
- Agent hub: system UI for available agents, active agents, health, runs,
  permissions, costs, and recent outcomes.
- Provider integrations: model registry, provider-specific adapters, local
  model execution services, and portability rules.
- Path integration: skills, plans, workflows, agent collaboration, and
  traversable task/path structures.
- Paladin: detection signals, safe remediation boundaries, issue/proposal
  creation, and no-autonomous-action gates.
- Cross-instance future: agent managers, federation, shared capabilities, and
  secure inter-instance communication.

## Future Prior Art Pass

No prior art search was performed for this capture note. The later design/spec
session should research at least:

- Claude Code, Codex, and similar coding-agent operating models.
- OpenAI Apps SDK / tool and component patterns.
- LangGraph / LangChain-style agent graphs as vocabulary and contrast.
- Temporal / workflow-engine lifecycle and retry concepts.
- Kubernetes controllers/operators for reconciliation loops and manager/worker
  patterns.
- Security guidance for agent tool use, prompt injection, credential handling,
  and delegated authorization.
- Multi-agent coordination patterns, including debate/critic/reviewer flows.
- Existing plugin/extension models for agent capabilities.

The goal of that pass is inspiration and vocabulary, not code copying.
