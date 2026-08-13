# AI-Reviewer Ensemble For Pull Requests

## Philosophy

**DRAFT (2026-08-11)** — authored from the sam-dev research session on AI PR review; requirements are
`Proposed` and unbuilt. This spec is the center of gravity for **automated AI review of changes to
TAP's repositories**: which AI reviewers run, what they are trusted to do, how their verdicts gate
(or don't gate) a merge, and how the fast-moving prior art is tracked over time.

The demand is real and stated plainly: a solo maintainer cannot keep up with the influx of changes,
and the classic answer — multi-human review — is not available. The emerging industry answer is an
**ensemble of independent AI reviewers** standing in for the second (and third) pair of eyes.
Production evidence now exists at scale (Cloudflare: 130k+ reviews/month, ~$1/review median, with
actual merge-blocking authority; Datadog: LLM malicious-PR detection fleet-wide), and the major
vendors ship first-party review products. TAP adopts the pattern early and deliberately.

The **priority order is explicit**: the #1 job is defending the codebase against **subtle malicious
changes smuggled in through a compromised maintainer machine or compromised major contributor** —
the xz-utils class of attack. Hygiene (code smells, correctness nits, style) is the #2 job and
comes largely for free from the same reviewers, but every architectural decision here is judged
against the security job first.

Three doctrine points shape everything below:

> **1. The reviewer is also an attack surface.** Every documented compromise of an AI review system
> (CodeRabbit RCE via a linter config in a PR; Claude Action key leak via bash in a PR title;
> CamoLeak; GhostCommit) required the reviewer to hold write privileges, secrets, tool access, or
> network egress. A read-only, no-tool, egress-blocked reviewer degrades under prompt injection to
> "wrong verdict" — which the ensemble absorbs — instead of "compromised pipeline." Least privilege
> applies to the watcher exactly as to the watched (`req-cicd-runner-least-privilege`, the
> trust-delta doctrine).

> **2. An AI verdict gates through a TAP-owned, fail-closed check — never through a bot "approval."**
> GitHub's own flagship (Copilot code review) cannot satisfy required-review rules, and no standards
> body accepts AI review as a two-person rule (SLSA L4 requires trusted *persons*). The blocking
> mechanism is the one TAP already trusts: a required status check whose pass/fail logic we own —
> the `gate` aggregator pattern — parsing machine-readable verdicts, red on absence.

> **3. Honesty about what this is.** Multiple AI reviewers are an **additional detection control and
> a forced second look**, not a substitute second human. The known gaps (multi-PR distributed
> attacks, build-script/binary channels, correlated model errors, admin-account compromise) are
> named in this spec per `req-sec-honest-risk`, not implied closed.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Independent Eyes On Every PR | ≥2 AI reviewers from different vendors review every code-bearing PR to main. |
| 2. | Security First | The ensemble is tuned, prompted, and gated for malicious-change detection above hygiene. |
| 3. | Reviewer Least Privilege | Reviewers read and comment; they hold no write path, no secrets, no egress, no tools they don't need. |
| 4. | TAP Owns The Gate | Blocking is a fail-closed TAP-owned required check over machine-readable verdicts, never a delegated bot approval. |
| 5. | Advisory Then Blocking | Reviewers start advisory; only measured, calibrated, security-severity findings graduate to blocking. |
| 6. | Track The Wave | The prior-art ledger below is maintained as the field moves; TAP stays at the leading edge on purpose. |

## Prior Art (the standing ledger — `req-cicd-ai-review-prior-art`)

Last swept: **2026-08-12** (verification sweep confirming vendor model-stacks, pricing tiers and
reviewer CVEs ahead of the roster decision; built on the 2026-08-11 three-agent sweep). Update triggers: any
reviewer vendor incident; a new first-party review product; a major eval/benchmark result on
malicious-change detection; SLSA/OpenSSF movement on AI review as a control.

**Production ensembles.** Cloudflare's orchestrator is the reference architecture: up to seven
specialized reviewers across model families (Claude, GPT, Kimi), a coordinator model that dedups,
re-verifies uncertain findings against source, and applies a strict approval rubric; 131k
reviews/30 days, median $0.98/review, 0.6% human break-glass rate
(blog.cloudflare.com/ai-code-review). Datadog's BewAIre reviews every PR for benign/malicious with
>99.3% accuracy and 0.03% FP after months of shadow-mode curation — "curated datasets beat newer
models" (datadoghq.com/blog/engineering/malicious-pull-requests). Google (Critique ML) and Meta
(MetaMateCR) frame AI review as productivity, not a security gate.

**Reviewer independence.** CodeRabbit's "code review needs independence": models fail to catch
their own errors ~64.5% of the time (self-correction blind spot); same-family testing inflates pass
rates 9–17 points (homogenization trap). The load-bearing caveat: "Nine Judges, Two Effective
Votes" (arxiv 2605.29800) — correlated training data means N nominal reviewers ≈ far fewer
effective votes. Author-model ≠ reviewer-model is the single most consistently argued rule; since
Claude authors nearly all TAP code, a non-Anthropic reviewer is mandatory, and 2–3 vendors should
be counted as ~1.5 independent opinions, not 3. **The rule is now productized** (2026-08-12
verification): Greptile's experimental *Model Inversion* detects the authoring agent from commit
trails/branch prefixes and routes review to the opposing family (Claude Opus 4.7 ↔ GPT 5.5), on
measured grounds — Claude Opus caught 62% of high-severity bugs in GPT-authored code vs 53.7% in its
own; GPT caught 60% in Claude-authored code vs 50.5% in its own, because "the types of bugs a model
introduces most often are the same types it's more likely to miss during review"
(greptile.com/blog/model-inversion). Independent convergence on this spec's central rule.
**Corollary that decides seats, not just vendors:** a product's *brand* is not its model family —
CodeRabbit's planning layer is built on Claude (plus a post-trained NVIDIA Nemotron router), so
seating CodeRabbit does NOT discharge the non-Anthropic requirement. Independence must be verified
at the model stack, not the logo.

**Adversarial evals.** PRWeaver (arxiv 2608.02693, Aug 2026): 208 execution-validated attacks vs
production reviewers — monolithic malicious PRs caught 42–79%; fused into a plausible carrier PR
with a cover-story description, detection floor ~29%; batched review of many PRs collapses
detection to 16–22% (⇒ review per-PR, never batched); auditors often localize the risky line but
fail to name the planted capability. SecVulEval: best model 23.8% F1 on statement-level CVE ground
truth. xz retrospectives: the payload lived in build scripts + binary test fixtures — surfaces
diff-review barely sees; no credible claim standard AI review would have caught it.

**Attacks on reviewers.** CodeRabbit RCE (disclosed 2025-01, published 2025-08, Kudelski): a PR's
`.rubocop.yml` executed attacker Ruby on CodeRabbit prod, leaking the GitHub App private key ⇒
mintable write tokens for ~1M repos; fixed in days (tools now sandboxed, "tools in jail"), but the
broad App grant (contents R/W, administration) remains the structural risk. Claude Code Action —
**CVE-2025-59536** (arbitrary code execution via prompt injection embedded in PR content; bash in a
PR *title* executed by the agent) and **CVE-2026-21852** (Anthropic API-key exfiltration by the same
vector); reported by RyotaK of GMO Flatt Security, fixed in four days, hardened through spring 2026,
fixes in `claude-code-action` v1.0.94; `claude-code-security-review` self-declares "not hardened
against prompt injection." That pair is the direct evidence behind
`req-cicd-ai-review-ensemble-4` — a reviewer that both parses attacker-controlled text and holds a
key inside our pipeline is the highest-consequence configuration in the field. CamoLeak (CVSS 9.6):
hidden markdown comments prompt-injected Copilot Chat into secret exfiltration via GitHub's Camo
proxy. GhostCommit (2026): malicious instructions rendered as text *inside a PNG* referenced from
AGENTS.md — text reviewers pass it, a later vision-capable agent executes it; CodeRabbit's default
config excludes images ⇒ the blind spot is the vector. CSA's framing: an AI agent in CI "combines
the attack surface of an untrusted text interpreter with the privilege level of a trusted pipeline
actor."

**Vendor offerings (as researched 2026-08).**
- *Greptile*: whole-codebase context (vector-indexed) rather than diff-local; experimental **Model
  Inversion** (above); ~82% seeded-bug catch and ~50% more bugs than CodeRabbit on a 50-PR
  head-to-head, at the cost of measurably higher noise (11 FPs vs CodeRabbit's 2 on that benchmark);
  $30/seat (50 reviews/mo, then $1/review), free general tier since 2026-06 (50 reviews/mo) and a
  free Developer plan for qualified MIT/Apache/GPL open source — **TAP is Apache-2.0 and public, so
  it qualifies**; GitHub + GitLab only; SOC 2 Type II all tiers; no training on customer code. The
  50-review/month ceiling is the open question against TAP's measured ~44 merged PRs/30d.
- *CodeRabbit*: full Pro features free on public repos (permanent, no application or qualification
  process — the free tier is the complete Pro plan, not a reduced one); **planning layer built on
  Claude** plus a post-trained NVIDIA Nemotron routing model ⇒ NOT vendor-independent from TAP's
  authoring model; paid reference $24–30/seat/mo; GitHub App (org/user install,
  scopable to selected repos); summary + inline comments; can formally Approve only behind
  `reviews.request_changes_workflow` (off by default; not endorsed as a required-review substitute);
  `.coderabbit.yaml` — `profile` quiet/chill/assertive, `path_filters`, `path_instructions` (≤20k
  chars, the security-instruction hook), `auto_review`, 60+ bundled tools incl. semgrep + gitleaks;
  SOC 2 Type II; code shared with OpenAI/Anthropic for review, no training on customer code.
- *OpenAI Codex*: `@codex review` / auto-review toggle via the Codex cloud GitHub integration
  (ChatGPT-plan billed; Free tier excluded — **Plus at $20/mo is the entry point that includes
  GitHub code review**; Pro 5x $100/mo since 2026-04). **Gotcha that constrains the wiring: the API
  tier carries no cloud features at all** — GitHub code review and Slack come with the
  *subscription*, not the key, so the seat is provisioned as an account, not a secret; posts a real
  GitHub review, P0/P1-focused;
  `@codex security review` variant; `AGENTS.md` "Code Review Rules" section tunes it; cloud sandbox
  runs the agent phase network-off with secrets stripped. `openai/codex-action@v1` runs in *your*
  CI (API-key billed), sandbox modes read-only/workspace-write, structured `output-schema` verdicts
  ⇒ first-party supported required-check gating.
- *Anthropic*: `anthropics/claude-code-action` (interactive @claude / automation mode; API key,
  subscription OAuth token, OIDC federation, or Bedrock/Vertex; the most detailed vendor
  prompt-injection hardening — content sanitization, untrusted-ref discipline, base-branch config
  restoration). `anthropics/claude-code-security-review` — security-only semantic diff review,
  confidence-filtered, advisory by default, self-declares "not hardened against prompt injection."
  Managed *Claude Code Review* (Team/Enterprise research preview): specialist-agent fleet on
  Anthropic infra, verification pass filters FPs, ~$15–25/review, deliberately-neutral check run
  plus a documented recipe for building your own blocking check from its severity JSON.
- *GitHub Copilot code review*: comments only; cannot approve/request-changes/satisfy required
  reviews — the negative result that cements the required-check gating pattern.

**Standards.** SLSA Source Track L4 = two or more trusted *persons*; AI does not count (a "Trusted
Robot" policy-exception seam exists; L1–3 are the honest solo-maintainer target). OpenSSF
"Securing Open Source in the Age of AI" (2026-05): AI review has "reached acceptable quality to
accelerate security outcomes for constrained maintainers"; robots over-inflate severity; publish an
AI policy; threat-model first. OWASP LLM Top 10 / Agentic Top 10 supply the reviewer-threat
vocabulary. Linux kernel: AI must not `Signed-off-by` (DCO is human-only — mirrors TAP's DCO
stance). Ghostty/curl wave: AI-assisted-and-human-filtered welcome, unfiltered AI slop banned; no
serious OSS project yet *mandates* an AI review pass — TAP doing so is ahead of published practice.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-cicd-ai-review-ensemble | [Independent Reviewer Ensemble](#independent-reviewer-ensemble) | Proposed | ≥2 vendors; author-model ≠ reviewer-model — a non-Anthropic reviewer is mandatory while Claude authors |
| req-cicd-ai-review-least-privilege | [Reviewer Least Privilege](#reviewer-least-privilege) | Proposed | Read + comment only; no write path, no secrets, no egress, minimal tools; per-reviewer trust-delta named |
| req-cicd-ai-review-untrusted-content | [PR Content Is Untrusted Input](#pr-content-is-untrusted-input) | Proposed | Injection-aware config; unreviewable binaries/images are findings; per-PR review unit, never batched |
| req-cicd-ai-review-gate | [TAP-Owned Fail-Closed Gate](#tap-owned-fail-closed-gate) | Proposed | Blocking = required check over machine-readable verdicts (the `gate` pattern); never a bot approval |
| req-cicd-ai-review-graduation | [Advisory Then Blocking](#advisory-then-blocking) | Proposed | Phase 1 advisory; graduate only measured, security-severity findings to blocking |
| req-cicd-ai-review-verdict-ledger | [Verdict Ledger](#verdict-ledger) | Proposed | Machine-legible review verdicts retained as an audit trail; named AI consumer per `req-ai-name-the-consumer` |
| req-cicd-ai-review-prior-art | [Maintain The Prior-Art Ledger](#maintain-the-prior-art-ledger) | Proposed | The ledger above is standing canon with named update triggers |
| req-cicd-ai-review-honest-limits | [Name What This Does Not Do](#name-what-this-does-not-do) | Proposed | Not SLSA two-person; correlated votes; multi-PR/build-script/binary gaps; admin-compromise residual |

---

### Independent Reviewer Ensemble
----
RID: `req-cicd-ai-review-ensemble`
Status: `Proposed`

Every code-bearing PR targeting `main` receives review from **at least two AI reviewers from
different vendors**, chosen so that the reviewer set is independent of the authoring model.

#### Implementation

- **Author-model ≠ reviewer-model is the non-negotiable rule.** TAP is authored overwhelmingly by
  Claude (the beanbag); therefore at least one reviewer MUST be non-Anthropic (Codex/GPT family).
  This is the strongest-evidenced ensemble rule (self-correction blind spot; homogenization trap).
- **v0 roster (DECIDED 2026-08-12 — two seats, both running off TAP infrastructure):**
  1. **CodeRabbit** (free full-Pro on public repos — no application, permanent; GitHub App scoped
     to selected repos) — the daily-life seat: PR summaries and walkthroughs, hygiene, 40+ bundled
     static tools (semgrep/gitleaks), malicious-change `path_instructions`. Advisory always.
     **Explicitly NOT the independence leg** — CodeRabbit's planning layer is built on Claude, the
     authoring family, so it cannot satisfy `req-cicd-ai-review-ensemble-2`.
  2. **OpenAI Codex cloud review** — the independence leg, and the only seat that satisfies
     `req-cicd-ai-review-ensemble-2`. Runs on OpenAI infra (ChatGPT-plan billed; the API tier does
     not include cloud review), no secrets in our CI; tuned via the `AGENTS.md` review-rules
     section TAP already maintains.
- **The malicious-change lens is CONFIGURATION ON BOTH SEATS, not a third agent.** A dedicated
  CI-resident security reviewer (`anthropics/claude-code-security-review`) was evaluated and
  **deferred, not eliminated**: it executes inside TAP's CI holding an API key while parsing
  attacker-controlled PR content — precisely the capability combination behind CVE-2025-59536
  (code execution via PR-borne prompt injection) and CVE-2026-21852 (API-key exfiltration), fixed
  in `claude-code-action` v1.0.94. Adding that surface in order to defend against smuggled
  compromise is a net-negative trade at v0 scale. Revisit only if the Phase-2 observation window
  shows the dedicated lens catching a class the two seats miss — and then hardened per
  `req-cicd-ai-review-least-privilege`.
- Count votes honestly: correlated errors mean this roster ≈ 1.5 effective independent opinions.
  Diversity of *prompt/lens* (hygiene + summaries vs independent correctness) is deliberate, and
  both seats carry the malicious-change instructions rather than one specialist holding them.
- **Alternative on the shelf:** *Greptile* (whole-codebase context; its experimental **Model
  Inversion** auto-detects the authoring agent from commit trails/branch prefixes and routes review
  to the opposing family — this spec's independence rule, productized; free for Apache-2.0 OSS).
  Passed over at v0 because it is measurably the noisiest reviewer (11 false positives vs
  CodeRabbit's 2 across a 50-PR benchmark) and noise is the failure mode that would sink the
  daily-life goal for a solo maintainer. Swap it in if depth beats quiet in practice.
- Both reviewers' instructions MUST explicitly target the malicious-change class:
  instruction-like content in diffs/comments, capability-adding changes with cover-story
  descriptions, CI/build-script modifications, dependency/lockfile edits, encoded/obfuscated blobs.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-ai-review-ensemble-1 | Two Vendors Minimum | Proposed | Every code-bearing PR to main is reviewed by ≥2 AI reviewers from different vendors. | Docs-tier PRs MAY be exempt (change-tier). |
| req-cicd-ai-review-ensemble-2 | Non-Author Vendor | Proposed | While Claude is the primary authoring model, ≥1 reviewer is non-Anthropic. | The independence leg. |
| req-cicd-ai-review-ensemble-3 | Malicious-Change Lens | Proposed | EVERY seated reviewer runs explicit malicious-change/smuggling instructions, not generic review prompts. | The #1-with-a-bullet job; carried by config on both seats, not by a specialist agent. |
| req-cicd-ai-review-ensemble-4 | No CI-Resident Reviewer At v0 | Proposed | No reviewer executes inside TAP's CI holding a TAP secret; the v0 roster runs entirely on vendor infrastructure. | Escalating past this requires the re-decision named in `req-cicd-ai-review-least-privilege`. |

---

### Reviewer Least Privilege
----
RID: `req-cicd-ai-review-least-privilege`
Status: `Proposed`

A reviewer **reads the PR and posts comments/verdicts — nothing else.** Every documented reviewer
compromise exploited privileges beyond that. This is `req-cicd-runner-least-privilege` applied to
the reviewer class, plus the trust-delta doctrine applied to third-party reviewer *apps*.

#### Implementation

- **Strongest form first: prefer reviewers that do not execute in TAP's CI at all.** The v0 roster
  (`req-cicd-ai-review-ensemble`) is deliberately all-vendor-infrastructure: no reviewer holds a TAP
  secret, no reviewer process parses attacker-controlled PR content inside our pipeline, and a
  reviewer compromise therefore cannot become pipeline execution. A CI-resident reviewer is an
  *escalation*, adopted only when a capability genuinely demands it and hardened per the bullet
  below. This is why the dedicated Claude security action is deferred rather than seated.
  **Named tension:** the Phase-3 blocking path in `req-cicd-ai-review-graduation` currently assumes
  `openai/codex-action` with `output-schema` running in our CI — which re-introduces exactly the
  CI-resident reviewer this bullet avoids. That trade MUST be re-decided at the flip, with parsing
  the cloud review's already-posted verdict evaluated first as the no-new-surface alternative.
- **Action-based reviewers (in our CI):** `pull_request` trigger only — never `pull_request_target`
  with a fork checkout; `permissions:` read-only plus `pull-requests: write` solely for the comment
  step; SHA-pinned per `req-cicd-runner-least-privilege-4`; sandbox read-only / network-off where
  the runner supports it (codex-action `read-only`; claude actions' bubblewrap + env scrubbing);
  API keys as repo secrets, absent from fork-PR runs by GitHub's own model.
- **App-based reviewers (vendor infra):** installation scoped to **selected repositories**, never
  all-repos; CodeRabbit's approve/request-changes workflow stays **off** (its formal approval must
  never be load-bearing); each app's permission grant is recorded and reviewed like
  `tap-renovate`'s. The named residual: a vendor-side compromise of an installed App's key is write
  access to the scoped repos — mitigated by the `main` ruleset (required checks apply to apps too)
  and bounded by the selected-repo scope; this is the Kudelski lesson and it is accepted, named,
  and re-reviewed on any vendor incident (a prior-art-ledger update trigger).
- Reviewers never hold or mint credentials beyond their own vendor key; reviewer workflows carry no
  other repo secrets.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-ai-review-least-privilege-1 | Read And Comment Only | Proposed | No reviewer holds a write path to code, a shared secret store, or unnecessary tool/network access. | |
| req-cicd-ai-review-least-privilege-2 | Scoped App Installs | Proposed | Third-party reviewer apps are installed on selected repos only, grants recorded, trust-delta named. | Kudelski lesson. |
| req-cicd-ai-review-least-privilege-3 | No pull_request_target | Proposed | Reviewer workflows never combine `pull_request_target`/`workflow_run` with untrusted checkout. | GitHub pwn-request class. |

---

### PR Content Is Untrusted Input
----
RID: `req-cicd-ai-review-untrusted-content`
Status: `Proposed`

Everything a PR controls — title, body, comments, commit messages, code comments, file contents,
images, tool configs — is **untrusted input to the reviewer**. Injection is assumed possible; the
design absorbs a steered verdict rather than pretending to prevent steering.

#### Implementation

- Prefer reviewer configurations that sanitize PR-derived content (claude-code-action's stripping
  of HTML comments/invisible characters/alt-text is the current best-in-class; Cloudflare's
  boundary-tag stripping is the pattern).
- **An unreviewable file is a finding, not a skip** (the GhostCommit lesson): a PR adding or
  modifying binary blobs, images in code paths, or opaque encoded content gets flagged by policy —
  reviewer prompts say so explicitly. TAP has little legitimate binary churn; the FP cost is low.
- **Per-PR review unit, never batched** (PRWeaver: batching collapses detection 3×). TAP's
  one-PR-per-promote flow already satisfies this; keep it true.
- Injection degrades to "wrong verdict": the gate (`req-cicd-ai-review-gate`) fails closed on a
  *missing* verdict, and a forged *approving* verdict from one reviewer still faces the other
  reviewers and the human — which is why approve-the-backdoor is named, not solved, in
  `req-cicd-ai-review-honest-limits`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-ai-review-untrusted-content-1 | Sanitizing Configs | Proposed | Reviewer configs enable available content-sanitization and injection mitigations. | |
| req-cicd-ai-review-untrusted-content-2 | Unreviewable = Finding | Proposed | Binary/image/opaque additions in code paths are flagged findings, not silent skips. | GhostCommit. |
| req-cicd-ai-review-untrusted-content-3 | Per-PR Unit | Proposed | Review scope is one PR; no batched multi-PR review mode is adopted. | PRWeaver. |

---

### TAP-Owned Fail-Closed Gate
----
RID: `req-cicd-ai-review-gate`
Status: `Proposed`

When AI review becomes blocking, the mechanism is a **TAP-owned required status check** — an
aggregator job in the `gate` pattern that parses machine-readable reviewer verdicts and fails
closed — **never** a bot Approve satisfying a required-review rule.

#### Implementation

- An `ai-review` aggregator (product-lines.yml sibling of `gate`, or its own workflow with a
  hand-named stable job) consumes structured verdicts: codex-action `output-schema` JSON; the
  Claude action's structured output (or managed Code Review's `bughunter-severity:` JSON if that
  product is adopted); CodeRabbit remains advisory (no reliable machine verdict contract).
- **Fail-closed semantics mirror `gate`:** missing verdict = red; skipped = red unless the change
  tier justifies it (docs-tier exempt via `scripts/change-tier`, same as the boot gates); severity
  ≥ the blocking threshold = red. `if: always()` aggregator so a skip cannot become a false green.
- Blocking threshold: **security-class findings at high/critical**; hygiene findings never block.
- Wired into the `main-required-checks` ruleset beside `gate`; composes with the promote flow's
  auto-merge (auto-merge waits on required checks) and with the planned emptying of the admin
  bypass — **until the bypass list is emptied, this gate is advisory-in-fact for an admin laptop**,
  which is exactly the compromised-machine path; the two changes belong to the same wave.
- Break-glass: the skip-hatch is the existing loud, documented one (direct push / bypass telemetry
  in `promote-to-main.sh`), never a quiet reviewer-disable. Reviewer-service outage → re-run
  affordance + documented human-review fallback, recorded in the PR.
- This is a validation surface: the implementing change adds its **Validation Map row**
  (`req-dev-validation-map`) — the honest guard-status discipline applies to AI checks too.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-ai-review-gate-1 | Required Check, Not Approval | Proposed | Blocking rides a TAP-owned required status check; no bot approval is load-bearing for merge. | |
| req-cicd-ai-review-gate-2 | Fail Closed | Proposed | Missing/unparseable verdicts and unjustified skips are red, tier-gated like the boot gates. | |
| req-cicd-ai-review-gate-3 | Security Blocks, Hygiene Advises | Proposed | Only security-class findings above the calibrated threshold block; hygiene never does. | |
| req-cicd-ai-review-gate-4 | Loud Break-Glass | Proposed | Bypass/outage paths are the existing loud documented ones; verdictless merges are visible anomalies. | |

---

### Advisory Then Blocking
----
RID: `req-cicd-ai-review-graduation`
Status: `Proposed`

Reviewers land **advisory-first**; blocking authority is granted only after a measured observation
window, and only to the security-severity slice.

#### Implementation

- Phase 1: all reviewers comment-only on every PR to main. No merge behavior changes.
- Observation window (~2 weeks / ~20 PRs): track finding volume, FP rate, latency, and at least
  informal seeded-bug spot checks. OpenSSF's warning is the calibration target: robots over-inflate
  severity — tune thresholds against *our* risk, not the reviewer's.
- Phase 2 flip: the `ai-review` gate (`req-cicd-ai-review-gate`) goes required in the same wave as
  the ruleset bypass-emptying. The flip is a deliberate, recorded decision referencing the
  observation data.
- Noise is managed in config (CodeRabbit `profile`/`path_filters`; Codex P0/P1-only posture;
  Claude confidence filtering + "what NOT to flag" instructions), not by ignoring reviewers — an
  ignored advisory layer is worse than none (the it-was-on-but-unread failure).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-ai-review-graduation-1 | Advisory First | Proposed | Reviewers run comment-only through a defined observation window before any blocking. | |
| req-cicd-ai-review-graduation-2 | Measured Flip | Proposed | The blocking flip cites observed volume/FP/latency data and flips only the security slice. | |

---

### Verdict Ledger
----
RID: `req-cicd-ai-review-verdict-ledger`
Status: `Proposed`

Every AI review produces a **machine-legible verdict record** that is retained and queryable — the
audit trail that makes "this merge was reviewed, by whom, concluding what" a fact, and a
merge-without-verdict a visible anomaly.

#### Implementation

- v0 is cheap: the verdicts already live on the PR (comments, check runs, action artifacts);
  the requirement is that structured verdict JSON (reviewer, model, severity, findings, PR SHA) is
  emitted and retained (action artifacts / check-run output), not just prose comments.
- **Named AI consumer** (`req-ai-name-the-consumer`): the internal security AI — the same consumer
  as the `CONCERN` stream — monitors verdict records for trends: rising severity, verdictless
  merges, reviewer-disable events. George is the human consumer of the same record at review time.
- Future (demand-gated, named not built): verdicts land on the grid as TAP-managed nodes — the
  system observing its own supply chain with the same machinery it points at customer
  infrastructure. Do not build ahead of the read-only `tap_ai` surface.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-ai-review-verdict-ledger-1 | Structured Verdicts Retained | Proposed | Each review emits structured verdict data tied to the PR SHA, retained beyond the PR conversation. | |
| req-cicd-ai-review-verdict-ledger-2 | Named Consumer | Proposed | The verdict stream names its AI consumer (internal security AI) and supports its queries. | |

---

### Maintain The Prior-Art Ledger
----
RID: `req-cicd-ai-review-prior-art`
Status: `Proposed`

The **Prior Art section of this spec is standing canon**, maintained over time — the record of
where the leading edge is and where TAP sits relative to it.

#### Implementation

- Update triggers (any of): a reviewer-vendor security incident; a new or materially changed
  first-party review product (OpenAI/Anthropic/GitHub/CodeRabbit); a significant benchmark or
  adversarial-eval result on malicious-change detection; SLSA/OpenSSF/OWASP movement on AI review
  as a recognized control; TAP's own observation-window data contradicting a ledger claim.
- Each sweep stamps its date at the ledger head. Entries carry enough source identity to re-find
  (org + title/venue); dead links are pruned, claims re-verified on major decisions.
- The re-evaluation posture mirrors the hardened-base-image landscape doc: alternatives (e.g. the
  managed Claude Code Review product, Copilot review, a Cloudflare-style self-built coordinator)
  are **parked, not eliminated**, with named reopen conditions.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-ai-review-prior-art-1 | Triggered Updates | Proposed | The ledger is updated on the named triggers, date-stamped per sweep. | |

---

### Name What This Does Not Do
----
RID: `req-cicd-ai-review-honest-limits`
Status: `Proposed`

Per `req-sec-honest-risk`, the gaps this control does **not** close are stated where the control is
defined:

- **Not a SLSA two-person review.** AI reviewers are not "trusted persons"; TAP's claim is
  "additional detection control + forced second look for a solo maintainer," documented as a
  self-defined control. SLSA L1–3 remain the honest target; L4 is out of reach solo.
- **Correlated votes.** 2–3 vendors ≈ ~1.5 effective independent opinions; a class of error shared
  across frontier models passes all reviewers.
- **Multi-PR distributed attacks.** Detection floor ~29% for plausible-carrier attacks even with
  strong models; cross-PR evidence linking is an open research gap nobody ships. Partial mitigation:
  per-PR review + small diffs + the human's own memory.
- **Build-script / binary channels** (the actual xz vector). Partially mitigated by the
  unreviewable-file rule and CI-config-aware prompts; not closed.
- **Prompt-injected false approval.** Mitigated (sanitization, ensemble, fail-closed parsing),
  not eliminated.
- **Admin-account compromise trumps the gate.** A compromised machine holding admin credentials can
  alter rulesets or ride the bypass until the bypass list is emptied — and even then GitHub admins
  can bypass. The gate makes malicious merges *loud and evidence-bearing*, not impossible; the root
  controls are account-level (passkeys/2FA on GitHub, the bypass-emptying wave) — same calibration
  as guard meta-integrity (`req-dev-validation-meta-integrity`).
- **Reviewer availability.** A required external reviewer adds an outage mode to shipping; accepted
  with the loud break-glass (`req-cicd-ai-review-gate-4`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-cicd-ai-review-honest-limits-1 | Gaps Stated | Proposed | The above limits remain stated in this spec and are re-checked when the ledger updates. | |

---

## Relationship To Other Specs

- **[spec-cicd-hardening.md](spec-cicd-hardening.md)** — the parent pipeline doctrine; this spec is
  a new enforcement layer beside `req-cicd-branch-protection` (the gate rides the same ruleset and
  the same bypass-emptying wave) and inherits `req-cicd-runner-least-privilege`.
- **[spec-cicd-root-of-trust.md](spec-cicd-root-of-trust.md)** — who watches these watchers: the
  reviewer/gate configuration is guard surface protected by that spec's two-account structure,
  tamper telemetry, and ceremonies; its blocking-flip wave and this spec's are one wave.
- **[spec-security-posture.md](spec-security-posture.md)** — cheap-edge + honest-risk doctrine;
  `req-cicd-ai-review-honest-limits` is `req-sec-honest-risk` applied here; the trust-delta
  doctrine governs the third-party reviewer apps.
- **[spec-ai-integration.md](spec-ai-integration.md)** — AI reviewers are Player-3 actors on the
  development pipeline; the verdict ledger names its AI consumer per `req-ai-name-the-consumer`.
- **[spec-dev-validation.md](spec-dev-validation.md)** — the blocking gate is a validation surface
  requiring its Validation Map row in the implementing change.
- **[spec-dev-multisession.md](spec-dev-multisession.md)** — the promote/PR flow the reviewers
  attach to; per-PR review assumes that flow's one-PR-per-promote shape.

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
