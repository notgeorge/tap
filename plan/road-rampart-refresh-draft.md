# Rampart Roadmap Refresh — DRAFT (2026-07-09)

Status: `Draft — for discussion 2026-07-10`
Purpose: Consolidate the strategy shift discussed this session into one place, and stage the
changes that will **supplant / update `road-rampart.md`** once we've talked it through. This is a
notes-and-scaffolding document, not yet canon. Nothing here changes the active roadmap step until
we agree to fold it in.

Companion docs this refresh touches: [`road-rampart.md`](road-rampart.md) (the roadmap it
updates), [`product-map.md`](product-map.md) (deployment models + product lines), and the eviction
/ dev-workspace / cicd-hardening specs referenced inline.

---

## 0. One thing to confirm first — "the Star Trek deployment"

I read **"the Star Trek deployment" = the *Enterprise* deployment** — the sealed, hardened,
FIPS-mode customer/appliance delivery (Star Trek's ship is the *Enterprise*), as opposed to the
open source-clone developer kit. Everything below is written on that reading, because it lines up
exactly with the Wolfi + FIPS hardening work: that substrate only matters for a hardened
appliance/customer deployment, not for the developer path. **If "Star Trek" meant something else,
flag it and I'll re-cut §3–§4** — the rest of the frame stands regardless.

---

## 1. What changed since the roadmap was written (2026-06-24 → 2026-07-09)

The current roadmap's Doctrine was set on 2026-06-24 with one target: a **mid-July "launch-ready"
Rampart** — auth → boot → (plugin ‖ first-AI), "functionally complete and presentable for
customer conversations." That target has largely been **hit or is in-flight**:

- **Auth** — passwordless/passkey MVP + Google OIDC login promoted to main.
- **Boot** — from-git bootstrap, ordered profiles, health-gated bring-up promoted.
- **Plugins** — installable-code form done; now going the last mile (full eviction, below).
- **First AI** — still the open item from the mid-July list.

So the roadmap did its job. The refresh is not a reversal — it's that **the horizon past
"launch-ready" has come into focus with two concrete, dated go-to-market wedges** that the
2026-06-24 Doctrine only gestured at ("CI/CD post-July", "first-paying-customer 8/1"). Those
wedges now deserve to be the roadmap's center of gravity.

Three things crystallized this session:

1. **Full plugin eviction** — the TAP repo goes **core-only**; **every** plugin lives in its own
   git repo, git-installed at a pinned tag. Uniform model, one way to develop any plugin.
   (Supersedes the earlier "keep monorepo copies as the fallback" lean.) Rationale: **dogfooding
   the external-developer path** — we build our own plugins the exact way outside developers will.
2. **A hardened deployment substrate** — the passkey session standardized on **Wolfi Linux + FIPS
   mode default-ON** (`spec-cicd-hardening.md`, landed on main 2026-07-09 as decision + proofs;
   the runtime Dockerfile switch is imminent). This is the substrate for the *Enterprise* delivery.
3. **A two-audience split becoming explicit** — *developers* (source-clone kit) and *the
   Enterprise/appliance customer* (sealed hardened image) are genuinely different products with
   different delivery vehicles, timelines, and hardening bars. Naming them separately is the core
   move of this refresh.

---

## 2. The core new frame: two audiences, two delivery surfaces

The single biggest clarification: **TAP/Rampart now serves two distinct consumers, and the
same core serves both through different packaging.** This is the lens the refreshed roadmap
should be organized around.

| | **Developer surface** | **Enterprise ("Star Trek") surface** |
| --- | --- | --- |
| Who | Friendly external plugin developers (+ us, dogfooding) | Paying customers running Rampart in/against their environment |
| What they get | **Clone of the core repo** + `spawn` + a plugin workspace; full trust (specs, tests, agents) | A **sealed, hardened, FIPS-mode appliance/container**; no source, no dev rig |
| Delivery vehicle | Git (core repo read access + issued PAT), per-repo CI on free runners | Hardened OCI image (Wolfi + FIPS), boot profile pins the product plugin-set |
| Hardening bar | Dev-grade; the CONTRACT (compat floor + conformance + reusable CI) | Production/compliance-grade (FIPS, minimal CVE surface, signed artifacts) |
| First milestone | **~Aug 1, 2026** — open to a small set of external devs | **~end Oct 2026** — first sellable FedRAMP-20x deployment (Rampart-20x) |
| Maps to product-map | *New* — an ecosystem-seeding path (not one of the 3 deployment models) | The **Customer** deployment model, made concrete + hardened |

Why they reinforce each other, not compete:
- The developer surface is **how the plugin-sets that make up a solution-set get built** — by us
  and (later) partners/customers. It feeds the Enterprise surface.
- Building the developer surface **dogfoods** the exact packaging discipline (evicted plugins,
  pinned boots, conformance) the Enterprise surface needs to compose products reliably.
- The two critical paths are **sequential, not parallel-competing**: dev-kit (Aug-1) first,
  FedRAMP-20x Enterprise deployment (end-Oct) after — the Aug→Oct window is where the assessment
  build-out (Teleport collector, KSI, persistent instance, grid export/import) lives.

---

## 3. Wedge A — Developer enablement (~Aug 1, 2026)

Open the platform to a small set of friendly external developers who can: git-boot their own
Rampart, use their own coding agents to build plugins, push to their **own** repos, build boot
profiles, and PR back to mainline TAP + TAP-owned plugins. One-shot first impression → the dev
experience must be **dialed in and lived-with first**.

**What this needs (status):**
- **Full plugin eviction** — core-only repo; all plugins in own repos. *In progress; the
  coordinated wave is staged* (see §5, and the eviction plan doc).
- **The external-dev CONTRACT** — BUILT + on main (2026-07-09):
  - `requires_tap` compatibility floor (reject-at-boot),
  - conformance linter (`validate_plugin --strict`),
  - reusable per-repo CI (`workflow_call`, free runners).
  - *Deferred to the GitHub-org refactor:* protocol-version (#2) + artifact signing (#5).
- **The plugin workspace** (the inner dev loop) — `spawn --dev-plugins` (BUILT) + `release-plugin`
  (BUILT this session; held from promote pending Wolfi). This is *our* dev loop and *theirs* —
  same entrypoints local and in CI.
- **MVP dev-kit plugin set** — Rampart + aws_core + github_core (+ transitive substrate). Tune later.
- **Platform-repo hardening** — read access + protected main + PR-back review.

**The concrete "in front of real people" step (center-of-gravity check):** identify the 1–3
friendly developers, get them cloning + booting + shipping one trivial plugin, and *watch where
they stub their toes*. That friction log is the real Aug-1 deliverable — not a polished kit.

---

## 4. Wedge B — First sellable deployment: Rampart-20x on the Enterprise surface (~end Oct 2026)

The first sellable Rampart product line is **Rampart-20x** — a FedRAMP 20x assessment engagement
(Teleport-based remote access + KSI checks), delivered as a **hardened Enterprise appliance**. This
is the "Star Trek" deployment: sealed, FIPS-mode, minimal-surface, customer-run.

**What this needs (status):**
- **Hardened substrate** — Wolfi + FIPS default-ON. *Decision + proofs on main; runtime switch
  imminent* (`spec-cicd-hardening.md`, `doc-fips-assessment-record.md`). FIPS is a hard
  requirement (~Sept) and a compliance selling point, not just hygiene. Self-built OpenSSL 3.0
  #4282 FIPS provider PROVEN on Wolfi.
- **Assessment build-out** (slides into the Aug→Oct window): Teleport collector, KSI catalog
  build-out, a **stable persistent instance**, and **grid export/import** (the durable,
  schema-independent data-portability answer — leave-behind backup + multi-sale portability).
- **The sealed-image delivery vehicle** — the OCI packaging path (distinct from the dev
  source-clone), pinning the Rampart-20x plugin-set at released tags.
- **Signed release artifacts** — deferred to the GitHub-org refactor, but the Enterprise surface
  is where signing eventually earns its keep (supply-chain provenance for a compliance product).

**Why Wolfi/FIPS is the cheap foundational edge here:** we're rewriting the base image *anyway*;
laying the FIPS/minimal-CVE floor now (while the surface is open) is asymmetric — cheap now,
expensive/impossible to retrofit into a shipped compliance appliance later. (Security-posture
standing filter.)

---

## 5. The hardening / plumbing that serves both (mostly de-risked)

- **Coordinated eviction wave** (one fresh-DB event): squash all migrations → release each plugin
  once with clean migrations + test-carrying wheels → git-source `test_all` + flip CI to git →
  verify green → delete monorepo copies (core-only) → retire `lotr`. *Staged; executes after the
  Wolfi switch lands and the spawn/release promotes clear.* Full autonomy authorized through the
  irreversible copy-deletion, gated on green git-sourced CI.
- **grid export/import** de-urgentizes the migration squash (assessment data is mostly
  reproducible; the irreproducible bit is grid entities → export/import + pg_dump). Squash is now
  convenience-on-a-clean-base, folded into the eviction wave, not now-or-never.
- **Naming** (lock it): platform = **TAP** (substrate, not sold); commercial crystallization =
  **Rampart** (no dash); subproducts take the dash — **Rampart-20x**, Rampart-Defend, etc.
  Second product line = **Semaphore** (critical-infra vertical, gated behind Rampart traction).

---

## 6. How this maps onto — and supplants — `road-rampart.md`

Proposed roadmap changes to discuss tomorrow. **Nothing here is applied yet.**

**Doctrine (§ Strategic posture):**
- *Keep* the product-discipline core (Platform Ambition vs Product Discipline, the Strategic Rule,
  Red/Green flags) — it's still exactly right.
- *Update* the 2026-06-24 "strategic posture" paragraph: mid-July launch-ready is **substantially
  achieved**; the new posture is the **two-audience frame** (§2) with the two dated wedges (§3–§4)
  as the center of gravity. First-AI remains the open launch-ready item and folds into the
  developer/demo surface.

**Timeline table — proposed edits:**
- `step-rampart-launch-ready` (7/18) → mark the auth/boot/plugin legs **done**; narrow the
  remaining scope to **first-AI integration**; note that "launch-ready" is now a *waypoint*, not
  the horizon.
- **NEW step — `step-rampart-dev-kit`** (~Aug 1): open the developer surface to 1–3 external devs.
  Objective/Done-Test = a real external developer clones core, boots, ships one plugin, PRs it
  back — and tells us where it hurt. (Wedge A.)
- `step-rampart-first-paying-customer` (8/1) → clarify as the **Customer / Enterprise** deployment
  model, now with the hardened-appliance substrate as its dependency.
- **NEW step — `step-rampart-20x-deployment`** (~end Oct): first sellable Rampart-20x on the
  hardened Enterprise surface. Objective/Done-Test = a paid FedRAMP-20x engagement running on a
  FIPS-mode appliance producing accepted findings. (Wedge B.)
- `step-rampart-first-paid-assessment` (Robco / Self) → unchanged; still the near-term revenue +
  field-hardening loop. It's the *Self* model that de-risks the *Customer/Enterprise* model.
- `step-rampart-big-bang` → unchanged (Proposed, downstream).

**product-map.md — proposed edit:**
- Add the **Developer surface** as a distinct path alongside the three deployment models (Self /
  Customer / Partnership). It's not a deployment model (nobody deploys *to* a developer) — it's an
  **ecosystem-seeding + dogfooding path** that feeds all three. Worth its own short section.
- Make explicit that the **Customer** model's delivery vehicle is the hardened Enterprise appliance
  (Wolfi/FIPS), and the **Self** model runs the same core un-sealed.

---

## 7. Open questions for tomorrow

1. **"Star Trek" confirm** (§0) — Enterprise/appliance deployment, or something else?
2. **Is the developer surface a roadmap *step* or a standing *track*?** It recurs (every partner
   who builds plugins re-enters it). Step with a date, or a doctrine-level track with milestones?
3. **Sequencing under load** — Aug-1 dev-kit and the Aug→Oct assessment build-out overlap in
   calendar. Which yields when they contend? (Draft assumption: dev-kit first-impression is the
   hard Aug-1 gate; assessment build-out is the longer pour behind it.)
4. **Does "launch-ready" survive as a step, or dissolve into "done legs + first-AI"?** Leaning
   dissolve — it was a mid-July rallying point that has served its purpose.
5. **First-AI scope** — is the user-simulating guide still the right first cut, and does it belong
   to the developer/demo surface or the customer surface? (Affects which wedge it blocks.)
6. **Semaphore / Partnership** — still correctly downstream? Anything about the two-audience frame
   that pulls either earlier?

---

## 8. Where we actually are right now (concrete, so tomorrow starts from truth)

- **Developer surface:** external-dev CONTRACT built + on main; `spawn --dev-plugins` +
  `release-plugin` built (release held from promote pending Wolfi); eviction wave staged.
- **Enterprise surface:** Wolfi + FIPS **decision + proofs** on main (2026-07-09); **runtime
  Dockerfile switch NOT yet landed** (still `python:3.14-slim`) — a watcher is armed to catch it.
- **Revenue/field loop:** Robco (Self) active; near-term $ + hardening signal.
- **Immediate blockers to nothing-here:** the whole downstream sequence (promote the workspace
  tools → eviction wave → Rampart-20x packaging) gates on the Wolfi switch landing. Until then the
  build-ahead is done and green; strategy discussion (this doc) is the productive use of the wait.
