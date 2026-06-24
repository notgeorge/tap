# Rampart Product Map

`product-map` — the standing **product + go-to-market** taxonomy for the commercial work on TAP. This is the demand/intent layer's companion to [`road-rampart.md`](road-rampart.md): the roadmap is the time-ordered *progression* (which outcome, by when); this map is the stable *shape* (what we sell, to whom, how it's packaged). The roadmap references this map; this map does not define timelines (the roadmap's Timeline Table is the single source of truth for dates, `req-roadmap-timeline-table`).

Last meaningful revision: 2026-06-24 (George strategy lock-in).

---

## The substrate: TAP — The Analogy Platform

TAP (The Analogy Platform) is the general substrate — entity/edge graph, service layer, plugins, collectors, auth, viz, AI surfaces. It is **not** sold directly. Commercial offerings are **product lines**: focused, named crystallizations of TAP aimed at a market. Two are in view today.

The leverage of this structure: almost all platform and plugin work pays off across *multiple* solution-sets and product lines. A capability built once (e.g. the AWS collector) is reused everywhere it's relevant. That multi-pay-off is the core economic argument for investing in TAP/Rampart depth.

---

## Product line: Rampart (cyber-security)

Rampart is the cyber-security product line. It ships as **solution-sets** — packaged configurations of plugin-sets aimed at a specific buyer and job. Significant overlap is expected and *wanted*: the same plugin-sets recur across solution-sets.

| Solution-set | Buyer / job | Notes |
| --- | --- | --- |
| **Outpost** | Compliance/FedRAMP platforms | **Partner play** — integrate into FedRAMP platforms and compliance-automation systems (e.g. Drata, Vanta, and similar infusion points), feeding and consuming evidence and findings at those integration points. |
| **20x** | CSPs | Run **inside the CSP boundary** to generate their FedRAMP 20x scorecards and implement the security tests behind them. This is the story the samsite system already tells most of the way. |
| **Auditable** | Auditors / audit agencies | Evaluate systems, track evidence, and assess against compliance regimes. **Partner play** for audit agencies; can also start as a **solo deploy** supporting a single audit team. |
| **AO** | FedRAMP Agency Owners (and in-house GRC) | Oversee compliance across a portfolio of CSPs. Also usable by in-house GRC teams to track internal deployments. |
| **Defend** | Security teams | Grab-bag of functionality to defend infrastructure, systems, services, and software. The broad "security team" surface, less compliance-shaped than the others. |

**Plugin-sets** are the shared capability layer beneath the solution-sets. Example: the **AWS scanner** is used by Outpost, 20x, Auditable, and Defend. Solution-sets are largely *compositions + configurations* of plugin-sets aimed at a buyer; building a plugin-set well pays off across every solution-set that includes it.

---

## Product line: Semaphore (critical-infrastructure vertical)

Semaphore is a planned **second product line** focused on a specific critical-infrastructure vertical (vertical TBD). It is deliberately **gated**: the pitch to critical-infrastructure customers is de-risked by first having Rampart demonstrably working in legitimate companies. Semaphore is therefore downstream of Rampart traction, not a parallel near-term build.

---

## Go-to-market: deployment models (shortest time-to-money first)

The deployment *model* is orthogonal to the solution-set: any Rampart solution-set can, in principle, be delivered in any of these. They are ordered by time-to-money, which corresponds to development cycles required.

1. **Self.** Engagements where George runs Rampart locally / in-house — not managed by the customer. Shortest time-to-money; least platform machinery required. **Robco starts here** (the first contracted deployment); actively seeking more solo engagements. Field-validates the platform against real systems and surfaces the issues that harden it for the heavier models below.
2. **Customer.** Deployment *inside customer environments*, largely managed by their teams. Requires the reproducibility / stay-online machinery (boot, CI/CD, in-place updates) that a self-deploy doesn't. George is canvassing potential customers to learn which immediate needs to target — those become concrete build targets. Bonus: while building these, ideally run a live self-deployment to test the same features against real systems personally.
3. **Partnership.** White-labeled / integrated / support-implementation deals that dovetail into a partner's ecosystem, products, or workflows. Longest to develop (discussions, planning, testing, roll-out), but middle-term significant profitability through wash-rinse-repeat, and a funnel: partners exposed to the concept become customer-deployment prospects for their own instances.

---

## How this maps to the roadmap

- The **launch-ready** step (`step-rampart-launch-ready`) is the mid-July gate beneath *any* paid deployment: **TAP functionally complete** — auth + boot + installable plugins + a first AI integration (the user-simulating guide) — enough to stand an instance up, log in, and present the 20x story with an AI guide. Sequencing is auth → boot, then plugin and AI in parallel. CI/CD + deployment is the post-July hardening for stay-online customer environments.
- The **Self** model is the near-term revenue path (Robco + further solo engagements) and the field-hardening loop.
- **Customer** deployments are gated on the stay-online machinery (boot maturity, CI/CD, plugin refactor for per-customer customization).
- **Partnerships** and **Semaphore** are downstream of demonstrated Rampart traction.

Solution-sets (Outpost/20x/Auditable/AO/Defend) are productization targets that sharpen as customer/partner conversations identify which immediate needs to build toward; they are intentionally *not* near-term build steps. The near-term build is the platform capability that makes any of them deliverable — see the roadmap.
