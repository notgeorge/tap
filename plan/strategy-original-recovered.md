# Strategy Guardrail: Rampart / TAP Development Focus

## Purpose

This document exists to keep development for both humans and ai's focused on the path most likely to turn TAP/Rampart from a promising internal platform into a real, usable, sellable product.

The system is broad by nature. It can become a context graph, visualization engine, AI-native workbench, plugin platform, compliance system, observability layer, and federation substrate. That breadth is powerful, but it also creates a major risk: spending too much time improving the substrate instead of moving toward real-world use, feedback, and revenue.

When evaluating any new feature, refactor, architecture change, or implementation plan, use this document to assess and if needed challenge whether the work is on-path.

## Timeline

May 17+ - Scope out potential pilot partners
June 1 - Sam Aydlette Demo
June - July 10 - first pilot use inside an environment as a vulnerability assessment, continuing to identify pilot customers
July 10 - 17 - Hawaii trip, rest, relax
July 17 - August - expanded use, build up to major / large companies, repeatability, build toward productization
September - product launch big-bang demos

---

# Product Needs

Let's get real on what a product that other people can use actually needs.

- defined scope with real-world usability
- extensibility from inside the app (what makes it take off)
- documentation
- installation process
- security
- bug fixes
- updates in place that don't blow their stuff up
- beta users to make it all real...

---

# Steps on the path

## North Star - Big Bang

Rampart's current big-bang target is to demonstrate the ability to take an infrastructure to FedRAMP20x compliance in 90 minutes flat.  This will notionally be done live on a podcast or other recorded presentation.

The goal is to demonstrate the system's speed, accuracy, flexibility applied to a strenuous security challenge to drive awareness and adoption.

By that point, the platform should be:

- Scalable: Stable to operate at the scale of a small-medium sized enterprise (large enterprises can run multiple instances and federate)
- Usable: Capable of a being installed and configured by a moderately experiencd technical person, with all the capabilities necessary to perform assessment / security operations of their environment available as plugins
- Extensible:  Extensible using an (ideally) on-board ai support system (if not on-board then as a development environment similar to the one being I'm using to build now) that can generate plugins, adapt existing code, and tailor the deployment to meet their needs == sophisticated beanbag
- Purchase-able:  Available to launch through AWS marketplace and possibly as downloadable docker (after paying a fee)

Pricing model will be per-instance, currently taregeted at $60k / yr, with marketplace instance billing by the minute and docker images available with some sort of subscription service.

The splashing announcement / podcast will be intended to drive virality and uptake of the platform.  By that point it should be ready for new users to click a few buttons, bring up an instance, and start deriving value at the same time as generating revenue.

This phase is titled the big bang because it's difficult to know what's on the other side of it.  That's fine, we'd rather go big and venture into the unknown than go timidly following a presumably safe, presumably known path.

---

## Current Strategic Path

The current path is a constellation of milestones, leading to product launch.

### Phase 1. Demo to Sam Aydlette - by June 1 2026

The next major target is a credible demo to Sam Aydlette.

Sam is a trusted first audience, but also a serious and strategically valuable one. He understands large FedRAMP programs, has credibility inside Cisco, and can give meaningful feedback on whether the product story lands.

The demo should show Rampart doing something real and concrete:

- Assess Sam’s simple website (static content on aws using cloudfront and s3 buckets).
- Show the system map visually including aws infrastructure and github actions for ci/cd and compliance systems (lambda, rego, sigstore)
- Surface relevant security or compliance issues.
- Be prepared to import his environment live on a call using aws credentials to show the system acting in real-time
- Drive the point that this is real, it works, it's extensible, it's heading towards the big time and he wants to be a part of this

This demo does not need to prove the entire TAP/Grid vision. It needs to prove that Rampart is real, useful, and pointed at an actual buyer problem.

Demo Flow

- bit of opening patter, what i've been doing, why
- load the first page, holy shit moment when he realizes that's his site
- click into one of the objects like the lambda function
- now make it real by asking for creds, show loading them up into the app (or have it done at the cli), then run the live pull to gather his running config & run compliance checks
- pull back to KSI status / scoreboard (funny moment when it points out all the KSI's he doesn't really touch on and / or accept his exceptions by pulling them in)

Critical Path Features:

- SamSite Clone:  Need to clone and deploy my own copy of sam's site under my own domain
- AWS Collector:  Build an operational view of the site using aws credentials to identify the actual aws plumbing in realtime on a call, re-use the projection to see what it looks like in the ops view
- Sam Projection:  Use a custom projection to lay out what we see in the development view, bonus points for a zoom-into something experience and / or click-into to see the internals (like the lambda function - minimal parser for package.json maybe)
- Compliance System:  Run a sampling of compliance tests, whatever's super simple to build, to drive evidence collection off the grid (bonus to pull in his exclusions as exceptions to findings, build a compliance check as we chat ala "hey could it...")
- KSI Scoreboard:  Scoreboard rendered with findings / status, could likely re-use the system that we have now (leaves something for sam and i to brainstorm on together and sets up a hey could you build it this way moment)
- History UI:  Have pretty history and FLIP fields that we can show off, just bake what we've got into the existing pages to surface / make them pretty.  
- Batch UI:  Need to actually build this out.

Bonus Features that would be nice but we don't have time for:




Things that will blow Sam's mind:

1. Graphical view of the site (holy shit that's my site)
2. Web-system, fully fleshed out with all internal bells and whistles (holy shit this is an app)
3. Live import via aws collector(s) and holy shit that just loaded in real-time.
4. Compliance check system, KSI applicability and scorecard (holy shit that's compliance)
5. Sophisticated Beanbag:  Modify the system via ai calls as we chat and reload (holy shit beanbag)
6. History system, FLIP (holy shit that's honest-to-god audit evidence)


We want to take him from "hey this works on my toy website" to "hey this could work at scale inside Cisco" with a side of "holy crap george is IN. THE. GAME. and he's playing to win".

Things we don't need at this time:

- multi-user
- security pass
- encrypted secrets
- installation / configuration flow
- audit / logging super detailed internals and affordances in the web ui
- ai integration in the app


### Phase 2. First Paid Security / Vulenrability Assessment - June - July 7 2026

After the Sam demo, the next goal is to find and begin one paid assessment and position for selling them a Rampart instance they can keep live on their environment.  The hustle to find customers will start in mid-may to line them up by early June.

The likely first sale is a white-glove security/compliance/vulnerability assessment, supported by Rampart, targeting a small-medium-sized enterprise.

The sell will be "hey your infrastructure is changing fast, you know and trust my judgement from the past (or via referral), I'm back in the business of doing assessments with ai-enhanced tooling.

The pitch to customers will inculde a demo of the approach I use, showing off Rampart in action using demo data, describe how it can be tailored to their needs (sophisticated beanbag).

This path is preferred because it:

- Uses existing reputation and domain expertise.
- Does not require a fully productized SaaS platform.
- Produces revenue quickly.
- Creates real-world feedback.
- Generates a case study or reference path.
- Turns Rampart into a leave-behind asset that can lead to recurring revenue.

This is an field-exercise-to-product transition.  The first fielding doesn't need to be product-ready, in fact we want to drive it into the field before it's production-quality to find the rough edges.

It's okay if the first few customers want to keep one of their own, great outcome.  I can provide white-glove operation while making the transition to their personnel for operation.

Key elements we'll need to have working:
- Multiple collection paths for aws, network scanners, 
- Vulnerability management tooling

Things that will be near 

### 3. Public / Big Bang Demo

The larger public-facing goal is a splashy demonstration, possibly in a FedRAMP podcast or similar venue, where Rampart assesses and explains a real system in a short time window.

This is an event horizon, not the immediate planning target.

Do not overbuild for the public demo yet. Build toward the Sam demo and the first paid assessment. If those work, the public demo will become much clearer.

---

## Strategic Rule

When evaluating any work, ask:

> Does this directly help us demo Rampart to Sam, land a paid assessment, or make the first assessment repeatable?

If the answer is no, the work is probably not current-path unless it is fixing a blocker.

---

## Priority Order

Use this order when deciding what to build next.

### Highest Priority

Work that directly supports the Sam demo or first paid assessment.

Examples:

- Collecting real data from a website, AWS account, or other target.
- Representing that data in the graph.
- Visualizing the system clearly enough for a human to understand.
- Surfacing findings, alerts, or compliance gaps.
- Explaining why a finding matters.
- Producing a simple system report card.
- Supporting a small number of FedRAMP 20x checks that are easy to understand.
- Making demo setup and reset reliable.

### Medium Priority

Work that makes near-term delivery safer, cleaner, or repeatable.

Examples:

- Service layer consistency when needed to avoid fragile feature work.
- Minimal security needed for a demo or assessment.
- Basic plugin structure needed for collectors or checks.
- Basic scheduling for repeatable collection.
- Minimal installation or environment setup needed to run the system reliably.
- Refactors that remove immediate friction from the demo or assessment path.

### Lower Priority

Work that is strategically important but not needed immediately.

Examples:

- Full policy modeling.
- General-purpose AI agent frameworks.
- Comprehensive plugin dependency management.
- Full federation.
- Full time travel.
- General-purpose path systems.
- Advanced visual polish.
- Broad support for many data sources.
- Multi-tenant SaaS polish.
- Marketplace-style plugin ecosystems.

These may be important later. Do not build them now unless they directly unblock the Sam demo or first assessment.

---

## Platform Ambition vs Product Discipline

TAP is the broader platform.

Rampart is the first commercial crystallization.

Do not confuse the two during near-term development.

The platform can eventually support many use cases, but the current mission is to make one use case undeniably real.

A feature is suspect if its main justification is:

- “This will be useful eventually.”
- “The platform should probably have this.”
- “This makes the architecture more complete.”
- “This would be elegant.”
- “This is necessary for the full vision.”

A feature is stronger if its justification is:

- “This makes the Sam demo clearer.”
- “This helps us assess a real system.”
- “This makes findings visible.”
- “This helps explain compliance status.”
- “This makes a paid assessment easier to deliver.”
- “This reduces manual work in the first assessment.”
- “This makes the leave-behind more valuable.”

---

## Development Heuristic

Prefer:

> Make it work for the first real use case.

Over:

> Make it generally correct for all future use cases.

Prefer:

> One clear demo path.

Over:

> A flexible framework with no visible payoff.

Prefer:

> A rough but working Rampart assessment.

Over:

> A beautifully generalized TAP substrate.

Prefer:

> A feature that helps a human understand a real system.

Over:

> A feature that only satisfies architectural completeness.

---

## AI Coding Agent Instructions

When asked to implement, plan, review, or propose a feature, actively challenge whether the work is on strategy.

Do not simply comply with the requested feature. First assess whether it supports the current path.

For every proposed feature or implementation plan, respond with a brief strategic check:

1. **Path Alignment**
   - Does this help the Sam demo, first paid assessment, or assessment repeatability?
   - If yes, explain how.
   - If no, say so clearly.

2. **Scope Risk**
   - Is this likely to expand into a larger platform subsystem?
   - Is there a smaller demo-grade version?

3. **Minimum Useful Version**
   - What is the smallest version that would support the current milestone?

4. **Defer List**
   - What parts should explicitly not be built yet?

5. **Recommendation**
   - Proceed, narrow, defer, or replace with a simpler step.

Use direct language. Be skeptical of elegant overbuilding.

---

## Red Flags

Call out these patterns when they appear:

- Building a general framework before a specific use case needs it.
- Adding capabilities because they are “obviously part of the platform.”
- Expanding visualization before the demo needs the additional view.
- Expanding AI integration before the workflow is clear.
- Building full FedRAMP policy machinery before demonstrating a few checks.
- Making install, federation, or plugin systems robust before first field use.
- Refactoring for elegance without immediate delivery benefit.
- Chasing features that would be impressive but not necessary for Sam or the first assessment.
- Treating the public “big bang” demo as the current target instead of the Sam demo.

---

## Green Flags

Prefer work that:

- Makes a real system visible.
- Turns raw collected data into understandable entities and relationships.
- Surfaces security or compliance issues.
- Explains why those issues matter.
- Produces a simple, compelling visual.
- Helps a knowledgeable security/compliance person say, “Yes, this is useful.”
- Creates reusable patterns for the first paid assessment.
- Keeps the codebase understandable and tractable.
- Supports rapid iteration after feedback.

---

## Current Working Milestone

The immediate milestone is:

> Demo to Sam: assess a real target, show the system map, surface security/compliance issues, and make Rampart visibly answer what is going on.

Everything should be judged against that milestone unless explicitly stated otherwise.

---

## Operating Principle

The big vision is valid, but the next win must be concrete.

Build the smallest version that makes Rampart real in front of another person.

Then let reality update the roadmap.
