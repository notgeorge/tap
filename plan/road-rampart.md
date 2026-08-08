# Rampart Roadmap

`road-rampart` — the Rampart product roadmap. Governed by [spec-roadmap.md](../specs/spec-roadmap.md).

This is the demand/intent layer above specs: which work matters, in what order, by when, and why. It exists to keep development — human and AI threads — focused on the path most likely to turn TAP/Rampart from a promising internal platform into a real, usable, sellable product. TAP is the broad platform; Rampart is its first commercial crystallization. Do not confuse the two during near-term development.

---

## Doctrine

Standing, cross-cutting guidance. Stable; read this to know how to judge whether work is on-path. (This section currently lives here per `req-roadmap-doctrine`; it extracts to a `plan/plan.md` meta-doc only when a second roadmap appears.)

### Strategic posture (2026-06-24)

The near-term shift is toward a **presentable, deployable Rampart** we can put in front of partners and customers. The core samsite system already tells a convincing FedRAMP 20x story; the gap to "deployable product" is **auth and boot dialed in**, then plugin refactor (rapid per-customer iteration) and AI (the customer-facing, user-simulating guides). Build order to mid-July, in priority:

1. **Auth** — demo-able: user logins + enough internal controls to claim a real (if coarse-grained) authZ capability; web-layer warts acceptable.
2. **Boot** — repeatable instance bring-up; the critical path to standing instances up for demos and field deployments.
3. **Plugin refactor** — plugins as installable code: per-customer customization, product-suite composition, and focused work / testing / refactor.
4. **AI integration (first cut)** — the customer-facing, user-simulating guides: a real, integrated, useful "has-AI" capability and a genuine wow-factor in customer conversations. Deeper/agentic AI comes later.
5. **CI/CD / deployment** — the machinery to keep field deployments online through updates.

Items 1–4 are the **mid-July target** (`step-rampart-launch-ready`): with auth, boot, installable plugins, and a first AI integration in place, **TAP is functionally complete** — presentable for customer conversations and self-deployable. Sequencing: auth → boot, then plugin (3) and the first AI integration (4) **in parallel** — both depend on boot, not on each other, and that fork is what makes the push feasible. It will be a push to get there. CI/CD + deployment (5) is the post-July hardening that makes it stay-online deployable inside customer environments. The product + go-to-market shape this serves — the product lines (Rampart, Semaphore), solution-sets, plugin-sets, and the Self → Customer → Partnership deployment models — lives in [`product-map.md`](product-map.md), the standing companion to this roadmap.

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

What a product other people can use actually needs: defined scope with real-world usability; extensibility from inside the app; documentation; an installation process; security; bug fixes; in-place updates that don't break their stuff; beta users to make it real. Not all required now — tracked here so step scoping stays honest about the distance to a product. The product-line / solution-set / plugin-set and deployment-model taxonomy this feeds is in [`product-map.md`](product-map.md).

**Standing trigger — plugin/boot supply-chain integrity.** The single-command bootstrap-pointer system (`specs/spec-tap-boot-bootstrap.md`) makes the boot pointer a supply-chain root of trust. Its integrity ladder is deliberately demand-gated: the cheap **content-hash floor** (`req-boot-bootstrap-record-version`) is laid now; **Sigstore keyless signing** and eventually **TUF channel security** (`req-boot-bootstrap-signing`) are backlog whose **trigger is the first non-George user playing with the system.** The moment someone outside sets up an instance, we want to offer the most secure plugin/boot experience possible — sorting all the way through Sigstore up to TUF — to set the bar high from the start rather than retrofit it. Named here so the trigger is watched, not discovered late; the security-posture rationale (cheap edge now, expensive edges named) is in [`spec-security-posture.md`](../specs/spec-security-posture.md).

### AI Thread Instructions

When asked to implement, plan, review, or propose, first assess whether the work supports the active step — do not simply comply. Respond with a brief strategic check: (1) Path alignment to the active step's Done-Test; (2) Scope risk and whether a smaller demo-grade version exists; (3) Minimum useful version; (4) Defer list; (5) Recommendation — proceed, narrow, defer, or replace with a simpler step. Use direct language. Be skeptical of elegant overbuilding.

---

## Timeline Table

Quick-glance index. Per-step `Timeline Target` is authoritative; this table is its mirror, kept in sync in the same edit (`req-roadmap-timeline-table`).

| Step ID | Name | Timeline Target | Status | Note |
| --- | --- | --- | :---: | --- |
| [step-rampart-sam-demo](#step-rampart-sam-demo) | Demo to Sam Aydlette | 2026-06-01 | Completed | Demo landed 2026-05-31 (+ Eric later that week); samsite retained as demo/test target |
| [step-rampart-launch-ready](#step-rampart-launch-ready) | Launch-ready Rampart | 2026-07-18 | Active | TAP functionally complete + presentable for partner/customer talks; mid-July = auth → boot → (plugin ‖ first-AI); CI/CD post-July ([`product-map.md`](product-map.md)) |
| [step-rampart-first-paid-assessment](#step-rampart-first-paid-assessment) | First paid assessment | 2026-06 → 2026-07-07 | Active | Robco (the Self deployment model — first contracted Rampart deployment); their infra is weeks out / slow; value = prove the solo use case + field-harden the platform |
| [step-rampart-first-paying-customer](#step-rampart-first-paying-customer) | First paying customer | 2026-08-01 | Active | The Customer deployment model — Rampart deployed in a company, customer-managed; needs the stay-online machinery (boot, CI/CD, plugin refactor) |
| [step-rampart-self-sufficiency](#step-rampart-self-sufficiency) | Self-sufficiency | 2026-09-15 | Proposed | 3+ customers by mid-Sept → default alive |
| [step-rampart-big-bang](#step-rampart-big-bang) | Public big-bang demo | ~2026-10 | Proposed | Event horizon, not the current planning target |

**Calendar anchors (non-step):** pilot-partner scouting from 2026-05-17 (feeds the paid assessment); 2026-07-10 → 2026-07-17 Hawaii — rest, no work; 2026-07-17 → 2026-08 expanded use, repeatability, build toward productization.

---

## Steps

Steps are ordered but may overlap; concurrency is shown by the timeline table, not by ordering.

### step-rampart-sam-demo
Status: `Completed`
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

**Completion After Action**
Demo performed on May 31st and went great.  System worked as expected, was well received, and all features needed were there and demonstrable.  Sets the stage for collaboration in the future, provided validation of the approach and enthusiasm and confirmation that had been a bit lost while so deep into the work that I couldn't see the forest for the trees.

This was followed by a second demo to a colleague later in the week which was also very well received.  Together they demonstrate that I can communicate the capabilities of the system, and that the samsite demo has sufficient heft to actually present what's going on (much better than genericom).  Keeping samsite around as a demo target for the foreseeable future will be useful and to use it as a potential testing target for exercising plugins, etc. makes a lot of sense.  Thanks Sam and Eric!


### step-rampart-launch-ready
Status: `Active`
Timeline Target: `2026-07-18`
Objective: TAP/Rampart is functionally complete and presentable for real partner/customer conversations — auth (user logins + enforced coarse authZ), boot (clean instance bring-up), installable plugins, and a first AI integration all in place — so a fresh instance stands up, enforces auth, and demos the samsite FedRAMP 20x story with an AI guide walking it.
Done-Test: On demand you can bring up a fresh Rampart instance, log in as a named user, present the 20x samsite story with auth enforced and a working first AI integration (the user-simulating guide), and the plugin system is in its installable-code form (the per-customer customization path); a knowledgeable viewer accepts it as a functionally-complete, deployable product — not a dev rig — and it is ready for the post-July deployment-hardening.
Non-Goals: the CI/CD + field-deployment machinery (post-July: stay-online updates, backups); fine-grained per-page/per-row authZ (web-layer warts acceptable for this step); deeper / agentic AI beyond the first user-simulating guide; multi-tenant polish; productization solution-sets beyond the 20x/samsite story.

The **launch gate** beneath every paid deployment in [`product-map.md`](product-map.md). The samsite system already tells the 20x story; this step closes the gap to "functionally complete + something we deploy and demo on purpose." Build order: auth → boot → then **plugin refactor and the first AI integration in parallel** (both depend on boot, not on each other) — that fork is what makes the mid-July push feasible. CI/CD is the post-July follow-on. **This step's done-test is the first four** (TAP functionally complete):

- **Auth (demo-able + coarse authZ).** Real user logins (wiring toward a customer IdP, e.g. Google, while preserving example.com access) and enough internal capability controls to honestly claim an authZ capability. The multi-session program-actor + service-boundary work landing now is this foundation; the web-layer read-as-user pass is a known, acceptable wart for the gate.
- **Boot (repeatable instance bring-up).** The `tap_boot` path that stands an instance up from a fresh database to a populated, usable system without hand-holding — the critical path for demoing to and deploying for customers, and the **fork point**: once boot works, plugin and AI proceed in parallel.
- **Plugin refactor (installable plugins).** Plugins as installable (uv-based) code — versioned, testable, per-customer composable. What lets Rampart be *tailored* per engagement and lets plugin-sets compose into solution-sets (`product-map.md`); functionally-complete TAP means the plugin model is in its real form, not the built-in stopgap.
- **First AI integration (the demo wow).** The customer-facing, user-simulating guide — a `tap_ai` read-only surface over the graph: real, integrated, genuinely useful, the capability that lets a customer conversation include "and here's the AI walking you through it." Reads the existing graph, so it does *not* depend on the plugin refactor — hence the parallelism above.

CI/CD + deployment (item 5) is the post-July follow-on: stay-online updates and backups that make Rampart deployable in *customer* environments (the Customer/Partnership models). It is *not* gating for mid-July functional-completeness or the Self-deployment demo.

Concurrency: runs alongside the Robco engagement (`step-rampart-first-paid-assessment`) — Robco is the first place this capability gets deployed for real, and Robco's slow infra standup buys time. The Hawaii break (2026-07-10 → 2026-07-17) sits in this window; auth + boot are the pre-break push, with plugin + AI parallelizing after.


### step-rampart-first-paid-assessment
Status: `Active`
Timeline Target: `2026-06 → 2026-07-07`
Objective: Land and begin one paid white-glove security/compliance/vulnerability assessment of a small–medium enterprise, supported by Rampart, positioned as a leave-behind they can keep live.
Done-Test: A customer has paid for and started an assessment, Rampart is deployed against their environment producing findings a knowledgeable person agrees are useful — and the engagement has produced a real price point and a willingness-to-pay signal.
Non-Goals: productized SaaS; multi-tenant polish; full FedRAMP machinery; broad data-source coverage; anything aimed at the public big-bang.

The likely first sale is a white-glove assessment supported by Rampart, sold on existing reputation and domain expertise ("your infrastructure is changing fast, you know my judgment, I'm back doing assessments with AI-enhanced tooling"). The pitch includes a demo of the approach on demo data and a description of how it tailors to their needs (sophisticated beanbag). Preferred because it uses existing reputation, needs no productized SaaS, produces revenue quickly, creates real-world feedback, generates a reference path, and turns Rampart into a recurring-revenue leave-behind. This is a field-exercise-to-product transition: drive it into the field *before* it is production-quality to find the rough edges; it's a great outcome if early customers want to keep their own instance with white-glove operation transitioning to their staff.

This step's real job is to validate **willingness-to-pay and price**, not only to find rough edges. Pilot-partner scouting (the hustle to line customers up) runs concurrently from 2026-05-17 — folded into this step rather than its own, since it does not yet need its own fence. Key elements needed working: multiple collection paths (AWS, network scanners); vulnerability-management tooling.

**Status**

This task is Active as of 6/10/2026 with the agreement to consult / advise on Robco - a recently funded AI Safety startup.  The team is currently 1-3 people waiting for first funding to hit the bank at the end of the month.  I've got a verbal agreement with the founder and will send a contract formalizing the agreement.  This will be an ongoing assessment, I'll be advising them as they stand things up, billed monthly, with the understanding that I'll bring Rampart to the part when / where it's appropriate.  The great news is this provides real world signal, a first customer, and creates optionality across multiple dimensions including the ability to level up in "how do you secure AI models / model production", which feels like a growth industry.

Programmatically, this effort will be a source of opportunistic development / implementation based on demand signals.  The team's just getting started so there will be opportunities to integrate capabilities as they develop them, but only in the context of the greater strategy of building Rampart as a stand-alone product.  As we get things rolling, we'll spin up a Robco instance, eventually placing it online so that members of the team can access and view status.  That sets a target for online, self-hosted, persistent deployment capability, which will be a great exercise in keeping an instance alive during active development.

**Development Demands**
* user authentication - this will wire into the company's iDP, presumably Google, while still allowing me access via example.com
* plugin management - ideally have the plugins be based on uv so that we can easily manage versioning (and test versioned upgdates)
* backups - mechanism to backup the system so that we don't neeed to worry about blowing stuff up once there's production data
* updates - ability to update the core image as new capabilities come online.
* paths - as the system under observation comes together, tracking flows of build / deploy will be important

**New Plugins Possibly Needed**
* Google Workspace / IdP to map users, groups, possibly docs and policies
* AI-security ??? to map ai models, development, training, paths / flows etc


### step-rampart-first-paying-customer
Status: `Active`  
Timeline Target:  `2026-08-01`  
Objective: A customer has launched Rampart in their environment on a subscription.
Done-Test: The Rampart instance is up in their environment and has been operational for at least one week and is under active use / development.
Non-Goals: development that is not tied directly to the customer use case (which will be determined as we get the customer).

The Robco assessments gives me an opportunity to leverage Rampart inside a company.  This step is about getting Rampart deployed inside a company without my direct involvement on a monthly subscription that lays the foundation for achieving self-sufficient revenue in the next step.  This is a critical turning point where the system goes from "tool I can use" to "tool others are using".

The exact needs will dial in over time

**Critical Path**  
These are the must-do, and in the order in which they'll need to be done.  

* AuthN Approach - just bite the bullet and start specing it out with the robots.  That process will highlight the actual things you need to do.  Just do the thing.  This should also help define the shape for AuthZ, which will put dimensions on the board.  
* Plugin Refactor - also straightforward, have plenty of plugins to work from, should drive towards completing the refactor (and bumping the plugin building skill) to include the backend config and systems necessary to host the existing samsite plugin set.  Should be a fast refactor once the first one’s dialed in, the rest prove it out.  
* Boot Loader - expand to support plugins, bringing up samsite is sufficiently complex that you can exercise enough aspects of it.  Should get to the point where you have boot profiles that you can load and will be smart enough to start up with all plugins and you’ll need to figure out the auth system and what it means to self-configure (remember all those places where you hardcoded config in secrets files?)  
* Configuration - process likely integrated with plugins and boot loader, arrives at a point where important settings can be added and set interactively (initially stored as part of the boot profile - possibly driven by cli based on what plugins will be needed up front).
* Subscription Launch - determine the process for making the system available for launch inside another organization on a metered plan.  AWS Marketplace is likely the first target.

**Parallel Paths**  
These are to be done along the way in conjunction / parallel with the critical paths above.  They are needed functionlity that must be in the completed product for it to sellable.

* AI Onboard - this is what you meet when the system’s up and initial configuration is completed.  It’s the concierge and assistant.  There’s going to be a lot of complexity and customization added to this over time.  This can be started in parallel as the fun side project while plowing through the mainline nuts and bolts.  It’ll take about that long to get the pieces in place and should land at about the same time.  
* Paths - another “do the thing” implementation. This is an essential feature and knowing that it’s on the board will drive the total set of capabilities and add to the overall wow factor.  Samsite can be updated to come see the paths inherent to the system.  Gryphon extensions will follow, it’ll be a nice project for an afternoon to, you know, solve complex traversals multiple ways with a few hundred lines of code and some database objects.  
* Time Travel / Awareness - will likely be needed in some form to track changes to the environments over time to target customers keenly interested in keeping up with the velocity of changes inside their environment.  
* AuthZ - also something that will get more mature over time, driven by use cases and shaped by the initial AuthN implementation and AI integration.  This will be more than just dimensions by the time we get to AI, since it’ll quickly develop the ability to permute system state, build plugins, (there’s going to be a plugin development plugin i can feel it).  
* CI/CD - by this point it’ll be time to level up the backend environment to support enterprise (or better) grade development and validation for initial customers.  
* Docs - How all this stuff fits together for our approaching users

In addition, work will need to be done in licensing and legal agreements to arrive at a good old fashioned software company.

### step-rampart-self-sufficiency
Status: `Proposed`  
Timeline Target:  `2026-09-15`  

The first paying customer is just that - the first...of many.  Multiple customers will be pursued in parallel with the target of closing those deals shortly after the first customer is up and running.  The goal is 3+ customers by mid-September (self-sustaining september).  At that point the project is default alive.


### step-rampart-big-bang
Status: `Proposed`
Timeline Target: `~2026-10 (event horizon — not the current planning target)`
Objective: A splashy public demonstration (FedRAMP podcast or similar) showing Rampart take an infrastructure to FedRAMP-20x compliance in ~90 minutes flat, driving awareness and adoption.
Done-Test: The public demo runs live and converts attention into instance sign-ups / revenue.
Non-Goals: do not overbuild for this now. Build toward Sam and the first paid assessment; this step clarifies only after those work.

By this point the platform should be: **Scalable** (stable at small–medium enterprise scale; large enterprises federate multiple instances); **Usable** (installable/configurable by a moderately experienced technical person, with assessment/security-ops capabilities available as plugins); **Extensible** (an on-board AI support system — or a dev environment like the one building it now — that generates plugins, adapts code, tailors deployments: sophisticated beanbag); **Purchasable** (AWS Marketplace, possibly downloadable Docker behind a fee). Pricing model: per-instance, currently targeted at ~$60k/yr, marketplace billing by the minute, Docker images behind a subscription. Titled the big bang because it's hard to know what's on the other side — that's fine; better to go big into the unknown than follow a presumably-safe known path.

---

## Future

- **Structured strategy system.** A fuller strategy/tactic taxonomy is a captured good idea, not built. Demand trigger: a single step grows enough internal sub-actions to need its own file (`req-roadmap-primitive`).
- **Grid-native roadmap.** Roadmaps eventually live on the grid rather than in markdown. Not now (`spec-roadmap.md` philosophy).
