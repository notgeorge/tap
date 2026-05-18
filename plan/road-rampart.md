# Rampart Roadmap

`road-rampart` — the Rampart product roadmap. Governed by [spec-roadmap.md](../specs/spec-roadmap.md).

This is the demand/intent layer above specs: which work matters, in what order, by when, and why. It exists to keep development — human and AI threads — focused on the path most likely to turn TAP/Rampart from a promising internal platform into a real, usable, sellable product. TAP is the broad platform; Rampart is its first commercial crystallization. Do not confuse the two during near-term development.

---

## Doctrine

Standing, cross-cutting guidance. Stable; read this to know how to judge whether work is on-path. (This section currently lives here per `req-roadmap-doctrine`; it extracts to a `plan/plan.md` meta-doc only when a second roadmap appears.)

### Strategic Rule

When evaluating any work, ask:

> Does this directly help the active step's Done-Test?

If no, the work is probably not current-path unless it is fixing a blocker.

### Priority Order

**Highest** — directly supports the active step. Collecting real data from a real target; representing it in the graph; visualizing it so a human understands it; surfacing findings/compliance gaps; explaining why a finding matters; a simple system report card; a small number of easy-to-understand FedRAMP 20x checks; reliable demo setup and reset.

**Medium** — makes near-term delivery safer/cleaner/repeatable. Service-layer consistency where it prevents fragile feature work; minimal security for a demo/assessment; basic plugin structure for collectors/checks; basic scheduling for repeatable collection; minimal environment setup; refactors that remove immediate friction from the active step.

**Lower** — strategically important, not needed now. Full policy modeling; general-purpose AI agent frameworks; comprehensive plugin dependency management; full federation; full time travel; general-purpose path systems; advanced visual polish; broad data-source support; multi-tenant SaaS polish; marketplace plugin ecosystems. Do not build these now unless they directly unblock the active step.

### Platform Ambition vs Product Discipline

The platform can eventually support many use cases; the current mission is to make one use case undeniably real.

A feature is **suspect** if its main justification is: "useful eventually" / "the platform should have this" / "makes the architecture more complete" / "would be elegant" / "necessary for the full vision."

A feature is **stronger** if its justification is: "makes the Sam demo clearer" / "helps assess a real system" / "makes findings visible" / "explains compliance status" / "makes a paid assessment easier to deliver" / "reduces manual work in the first assessment" / "makes the leave-behind more valuable."

### Development Heuristic

Prefer: make it work for the first real use case → over: make it generally correct for all future use cases.
Prefer: one clear demo path → over: a flexible framework with no visible payoff.
Prefer: a rough but working Rampart assessment → over: a beautifully generalized TAP substrate.
Prefer: a feature that helps a human understand a real system → over: a feature that only satisfies architectural completeness.

### Red Flags

- Building a general framework before a specific use case needs it.
- Adding capabilities because they are "obviously part of the platform."
- Expanding visualization before the demo needs the additional view.
- Expanding AI integration before the workflow is clear.
- Building full FedRAMP policy machinery before demonstrating a few checks.
- Making install, federation, or plugin systems robust before first field use.
- Refactoring for elegance without immediate delivery benefit.
- Chasing features that would be impressive but not necessary for the active step.
- Treating the public "big bang" as the current target instead of the active step.

### Green Flags

- Makes a real system visible.
- Turns raw collected data into understandable entities and relationships.
- Surfaces security/compliance issues and explains why they matter.
- Produces a simple, compelling visual.
- Helps a knowledgeable security/compliance person say "yes, this is useful."
- Creates reusable patterns for the first paid assessment.
- Keeps the codebase understandable and tractable.
- Supports rapid iteration after feedback.

### Product Needs (standing productization context)

What a product other people can use actually needs: defined scope with real-world usability; extensibility from inside the app; documentation; an installation process; security; bug fixes; in-place updates that don't break their stuff; beta users to make it real. Not all required now — tracked here so step scoping stays honest about the distance to a product.

### AI Thread Instructions

When asked to implement, plan, review, or propose, first assess whether the work supports the active step — do not simply comply. Respond with a brief strategic check: (1) Path alignment to the active step's Done-Test; (2) Scope risk and whether a smaller demo-grade version exists; (3) Minimum useful version; (4) Defer list; (5) Recommendation — proceed, narrow, defer, or replace with a simpler step. Use direct language. Be skeptical of elegant overbuilding.

---

## Timeline Table

Quick-glance index. Per-step `Timeline Target` is authoritative; this table is its mirror, kept in sync in the same edit (`req-roadmap-timeline-table`).

| Step ID | Name | Timeline Target | Status | Note |
| --- | --- | --- | :---: | --- |
| [step-rampart-sam-demo](#step-rampart-sam-demo) | Demo to Sam Aydlette | 2026-06-01 | Active | Fork-and-reproduce his own infra; boto3 collector; static/edge topology |
| [step-rampart-first-paid-assessment](#step-rampart-first-paid-assessment) | First paid assessment | 2026-06 → 2026-07-07 | Proposed | Pilot scouting runs from 2026-05-17; validates willingness-to-pay |
| [step-rampart-big-bang](#step-rampart-big-bang) | Public big-bang demo | ~2026-09 | Proposed | Event horizon, not the current planning target |

**Calendar anchors (non-step):** pilot-partner scouting from 2026-05-17 (feeds the paid assessment); 2026-07-10 → 2026-07-17 Hawaii — rest, no work; 2026-07-17 → 2026-08 expanded use, repeatability, build toward productization.

---

## Steps

Steps are ordered but may overlap; concurrency is shown by the timeline table, not by ordering.

### step-rampart-sam-demo
Status: `Active`
Timeline Target: `2026-06-01`
Objective: Sam sees Rampart assess a faithful, live reproduction of his own samaydlette.com infrastructure and his own FedRAMP-20x compliance machinery, and concludes it is real, useful, and could evolve to work at Cisco scale.
Done-Test: On a live call, Rampart opens on a legible projection of the reproduced architecture, drills into a real finding, and shows a KSI scoreboard fed from Sam's own `ksi-catalog.json` — and Sam states, unprompted, that he'd want this running inside Cisco. (An outcome — never "demo delivered.")
Non-Goals: live credentials / live pull from Sam's real account; VPC/subnet topology; Terraform collector; config-vs-ops dimensions; DCOM drift comparison; multi-user; encrypted secrets; install/config flow; in-app AI; a security pass.
Depends-on: `spec-aws-core-v0`; the from-scratch boto3 `aws_core` collector — clean slate, Steampipe excised on main 2026-05-17 (parked at git tag `park/steampipe-tooling`), new collector spec to be written; `spec-aws-projection-top-level-minimal` (needs an edge/serverless variant — see below); `plugins/fedramp_20x_ksi`; `spec-rampart-demo-anwar` (proven precedent for the curated fallback).

**The unlock — fork and reproduce.** Sam is a close friend, technically generous, and wants this to succeed. His site is public: `github.com/sam-aydlette/samaydlette.com`. We clone it into *our own* AWS account rather than ever touching his credentials. His Terraform is a compliance **overlay** (it `data`-references a pre-existing S3 bucket, CloudFront distribution, ACM cert in us-east-1, and Route53 zone). So the bounded work is: ~80 lines of bootstrap Terraform for those four base resources, a cheap throwaway demo domain, push the `website/` content, and fork the GitHub repo so the OPA-gated deploy + sigstore (`scn-tag`) CI runs under our creds. Result: a real, running, rehearsable system we control end to end — zero dependency on Sam's account, and the chicken-and-egg ("will my collector work on his unknown prod?") becomes "does my collector handle this specific known system I've rehearsed 20 times?"

**boto3 collector (clean slate).** Main already excised the Steampipe collector on 2026-05-17 (parked at git tag `park/steampipe-tooling`) for a from-scratch boto3 build starting 2026-05-18 — the pivot this strategy reasoned to is now canonical, not a proposal. The demand-driven first feature set is *exactly Sam's resource types* — S3, CloudFront, ACM, Route53, Lambda, IAM role, CloudWatch log group, EventBridge rule. Sam's stack has no VPC/EC2/RDS, so the reproduction supplies a clean, demand-driven target with no legacy collector slice to carry forward; the prior VPC/subnet limitation is moot.

**Projection.** Sam's real topology is static/edge: CloudFront → S3, a scheduled compliance Lambda, Route53/ACM/IAM. The existing `spec-aws-projection-top-level-minimal` (account → VPC → subnet → EC2/RDS containment) is the wrong shape for Sam and needs an edge/serverless variant. Good news inside that: no VPC networking to model.

**Compliance / KSI — the strongest moment.** Sam's repo is a full FedRAMP-20x reference implementation: a ~70-KSI catalog across 11 families (`infrastructure/schemas/ksi-catalog.json`), a KSI-signal schema, OPA/rego policy gates, OSCAL SSP/POA&M builders, sigstore signing. Ingest *his own* KSI catalog and OPA policies, project them on the grid, independently assess the running reproduction, and show agreement/gaps. "Who watches the watcher" becomes literal — Rampart assesses his compliance Lambda itself. Sam recognizing his own KSI catalog reflected back beats any generic scoreboard.

**Beanbag, clarified.** The "modify the system via AI as we chat and reload" mind-blower is *George live in the Claude Code dev environment*, not in-app AI. In-app AI is a Non-Goal for this step. The dev environment is the beanbag, and it is already real.

**Demo flow.** 
- bit of opening patter, what i've been doing, why
- load the first page, holy shit moment when he realizes that's his site
- click into one of the objects like the lambda function
- now make it real by asking for creds, show loading them up into the app (or have it done at the cli), then run the live pull to gather his running config & run compliance checks
- pull back to KSI status / scoreboard (funny moment when it points out all the KSI's he doesn't really touch on and / or accept his exceptions by pulling them in)


**Mind-blowers.**
1. Graphical view of the site (holy shit that's my site)
2. Web-system, fully fleshed out with all internal bells and whistles (holy shit this is an app)
3. Live import via aws collector(s) and holy shit that just loaded in real-time.
4. Compliance check system, KSI applicability and scorecard (holy shit that's compliance)
5. Sophisticated Beanbag:  Modify the system via ai calls as we chat and reload (holy shit beanbag)
6. History system, FLIP (holy shit that's honest-to-god audit evidence)


**Critical path (rescoped, finite).**
1. SamSite Clone:  Need to clone and deploy my own copy of sam's site under my own domain
2. AWS Collector:  Build an operational view of the site using aws credentials to identify the actual aws plumbing in realtime on a call, re-use the projection to see what it looks like in the ops view
3. Sam Projection:  Use a custom projection to lay out what we see in the development view, bonus points for a zoom-into something experience and / or click-into to see the internals (like the lambda function - minimal parser for package.json maybe)
4. Compliance System:  Run a sampling of compliance tests, whatever's super simple to build, to drive evidence collection off the grid (bonus to pull in his exclusions as exceptions to findings, build a compliance check as we chat ala "hey could it...")
5. KSI Scoreboard:  Scoreboard rendered with findings / status, could likely re-use the system that we have now (leaves something for sam and i to brainstorm on together and sets up a hey could you build it this way moment)
6. History UI:  Have pretty history and FLIP fields that we can show off, just bake what we've got into the existing pages to surface / make them pretty.  
7. Batch UI:  Need to actually build this out.

**Bonus Features that would be nice but we don't have time for:**
- DCOM: perform a comparisson between his configured grid and the operational grid to assess drift (first pass at DCOM, but we can always just speak to it)
- Terraform Collector:  Parse his github repository to use the terraform to gather a view of his site - https://github.com/sam-aydlette/samaydlette.com on a configuration dimension including his compliance checking machinery (who watches the watcher). 
- Dimensionality:  Use the config and ops graphs to formalize how this is collected and presented in the system.  First real-world test of dimensions, demand-driven as it should be

**Unneeded at this time**
- multi-user
- security pass
- encrypted secrets
- installation / configuration flow
- audit / logging super detailed internals and affordances in the web ui
- ai integration in the app

### step-rampart-first-paid-assessment
Status: `Proposed`
Timeline Target: `2026-06 → 2026-07-07`
Objective: Land and begin one paid white-glove security/compliance/vulnerability assessment of a small–medium enterprise, supported by Rampart, positioned as a leave-behind they can keep live.
Done-Test: A customer has paid for and started an assessment, Rampart is deployed against their environment producing findings a knowledgeable person agrees are useful — and the engagement has produced a real price point and a willingness-to-pay signal.
Non-Goals: productized SaaS; multi-tenant polish; full FedRAMP machinery; broad data-source coverage; anything aimed at the public big-bang.

The likely first sale is a white-glove assessment supported by Rampart, sold on existing reputation and domain expertise ("your infrastructure is changing fast, you know my judgment, I'm back doing assessments with AI-enhanced tooling"). The pitch includes a demo of the approach on demo data and a description of how it tailors to their needs (sophisticated beanbag). Preferred because it uses existing reputation, needs no productized SaaS, produces revenue quickly, creates real-world feedback, generates a reference path, and turns Rampart into a recurring-revenue leave-behind. This is a field-exercise-to-product transition: drive it into the field *before* it is production-quality to find the rough edges; it's a great outcome if early customers want to keep their own instance with white-glove operation transitioning to their staff.

This step's real job is to validate **willingness-to-pay and price**, not only to find rough edges. Pilot-partner scouting (the hustle to line customers up) runs concurrently from 2026-05-17 — folded into this step rather than its own, since it does not yet need its own fence. Key elements needed working: multiple collection paths (AWS, network scanners); vulnerability-management tooling.

### step-rampart-big-bang
Status: `Proposed`
Timeline Target: `~2026-09 (event horizon — not the current planning target)`
Objective: A splashy public demonstration (FedRAMP podcast or similar) showing Rampart take an infrastructure to FedRAMP-20x compliance in ~90 minutes flat, driving awareness and adoption.
Done-Test: The public demo runs live and converts attention into instance sign-ups / revenue.
Non-Goals: do not overbuild for this now. Build toward Sam and the first paid assessment; this step clarifies only after those work.

By this point the platform should be: **Scalable** (stable at small–medium enterprise scale; large enterprises federate multiple instances); **Usable** (installable/configurable by a moderately experienced technical person, with assessment/security-ops capabilities available as plugins); **Extensible** (an on-board AI support system — or a dev environment like the one building it now — that generates plugins, adapts code, tailors deployments: sophisticated beanbag); **Purchasable** (AWS Marketplace, possibly downloadable Docker behind a fee). Pricing model: per-instance, currently targeted at ~$60k/yr, marketplace billing by the minute, Docker images behind a subscription. Titled the big bang because it's hard to know what's on the other side — that's fine; better to go big into the unknown than follow a presumably-safe known path.

---

## Future

- **Structured strategy system.** A fuller strategy/tactic taxonomy is a captured good idea, not built. Demand trigger: a single step grows enough internal sub-actions to need its own file (`req-roadmap-primitive`).
- **Grid-native roadmap.** Roadmaps eventually live on the grid rather than in markdown. Not now (`spec-roadmap.md` philosophy).
