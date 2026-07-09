# CI runner strategy — how to make the all-plugins lane faster (and when AWS)

Strategy note (not authoritative spec). Sibling to
[[doc-dev-validation-enterprise-ci-strategy]]: that note is the *why-CI-at-all*
trust-boundary argument; this note is the narrower *which-runner* decision for the
one server-side lane that exists today — `.github/workflows/all-plugins.yml`
(`req-dev-validation-all-plugins-lane`). The concrete change it recommends is
specced there. Versioning is git; do not store dates in the body.

## The question

Whether to stand up AWS-based self-hosted GitHub runners to speed up the all-plugins
lane — the hypothesis being that an AWS worker is *faster, cheaper, and easier* than
GitHub's org-based larger runners, with the bonus of native in-AWS testing of LLM /
`aws_core` integrations. Evaluated against the two cheaper levers it must beat.

## The load-bearing measurement

A real green run (2-core `ubuntu-latest`, `pytest -n 4`, ~21.5 min) breaks down as:

| Step | Time |
| --- | --- |
| checkout + setup + **cached** image build | ~40s |
| boot `test_all` stack | 61s |
| **full pytest lane** | **1292s (21.5 min)** |
| everything else | ~5s |

The test lane is **~95% of wall-clock**; the fixed build+boot tax is ~100s. Two
consequences fall straight out of that single number: (a) the suite is almost
perfectly shardable — the fixed tax you pay per shard is tiny — and (b) the suite is
Postgres-I/O-bound (workers block on DB round-trips; the workflow comments already say
this), so *more independent Postgres instances* helps more than *more cores on one
box*. The image-layer cache is real and load-bearing: the ~40s build is a cache hit
(`cache-from/to type=gha`, landed on main in `f051ba9e`); a cold build of the non-stock
Python 3.14 image is minutes. The ~100s tax already assumes the cache hits.

## Baseline cost (the "cheaper" hypothesis has no room)

Private repo on a **personal account** (not an org). At the 2026 Linux rate
(**$0.006/min**, after the Jan-2026 cuts) and ~5 runs/day of active dev (~150 runs/mo
≈ 3,150 min), CI today costs roughly **$0–20/month** — at or just over the monthly
included allotment. There is almost nothing to make cheaper. Any option that adds
dollars is *more* expensive than the status quo, not less.

## Three levers, grounded

| | **A: Matrix-shard (free runners)** | **B: Org → 8-core larger runner** | **C: AWS self-hosted** |
| --- | --- | --- | --- |
| Wall-clock | ~8–9 min (N=3), ~7 min (N=4) | ~8–11 min | ~6–9 min |
| Cost/mo | ~$5 (burns included minutes ~1.2×) | ~$33–66 (8-core = **$0.022/min, no included minutes**) | ~$3 compute + ~$10–35 fixed infra |
| Effort | an afternoon of YAML | one line `runs-on:` **+ org migration** | multi-day Terraform + **standing ops surface** |
| Structural blast radius | none (stays on personal account) | org billing/seats **+ forces the promote→PR-gate redesign** | new VPC/IAM/AMI/runner lifecycle to own |
| Unique upside | each shard = **own Postgres** → hits the documented I/O bottleneck directly | unlocks branch-protection + required checks (the highest-leverage GitHub setting) | **AWS-native**: Bedrock LLM tests, `aws_core` STS/AssumeRole dogfooding, role-native (no long-lived creds in GH secrets) |

Findings on the stated terms:

- **Cheaper — false.** Baseline is ~free; every option adds cost. AWS only beats
  *GitHub larger runners*, and we are not on those, so there is no bill to cut.
- **Easier — false.** AWS self-hosted is the hardest of the three and the only one
  carrying a permanent maintenance burden (AMI patching, module upgrades, cost/security
  monitoring). GitHub floated a **$0.002/min self-hosted charge** in 2026 — reversed
  after backlash but only *postponed indefinitely* — so "free self-hosted" carries a
  signaled tail risk.
- **Faster — true but not unique.** Sharding reaches the same wall-clock for ~$5/mo
  and zero new infra. Larger runners require the org move.

## Verdict

**On faster/cheaper/easier, AWS self-hosted loses to matrix-sharding.** Sharding is
the happy path for speed: the test lane is 95% shardable, each shard gets its own
Postgres (relieving the exact bottleneck), it stays on the personal account with no
org and no cloud, and it composes cleanly with the layer cache already in place (every
shard's `cache-from: type=gha` hits the same warm cache — no build-once-to-registry
dance needed). **Do not bite the bullet to AWS for speed.**

## Where AWS *does* have merit (a different axis)

Not speed — **capability**. A runner inside AWS carries an IAM role, which is the only
way to get: Bedrock LLM tests run natively as `tap_ai` (roadmap item 6) lands;
`aws_core` STS/AssumeRole/collector paths dogfooded against real AWS (ties to
[[aws-cross-account-assume-role]]) instead of mocks; and role-native auth with no
long-lived AWS creds in GitHub secrets. That is a real forward capability — but it is a
*different goal* from "make CI faster," it is not urgent, and building an autoscaling
runner fleet while CI is ~free and an afternoon of YAML gets 60% of the speed is
textbook premature scaling (the standing strategic-discipline filter). The
[[doc-dev-validation-enterprise-ci-strategy]] sibling already draws this line: "move to
self-hosted only when minutes-cost or environment-fidelity actually demands it. Do not
provision a runner fleet before the demand."

## Execution lanes — it is not just raw EC2 (cost/ops correction)

The "AWS self-hosted" tier above was scoped to the *most* ops-heavy vehicle — a raw
EC2 fleet built with `terraform-aws-github-runner` (AMI, VPC, NAT, autoscaler, standing
maintenance). That is a strawman for "run a Docker CI workload without buying EC2 time";
several lower-ops, cheaper lanes exist, and they cleanly split the two goals (speed vs
AWS-native capability):

| Lane | In our AWS acct? | Docker/compose works? | $/min Linux | Ops to stand up |
| --- | --- | --- | --- | --- |
| **Managed runner SaaS** (WarpBuild / Blacksmith / Namespace / Tenki) | no | yes (real Docker VM) | ~$0.003–0.005 (~50% under GitHub) | ~zero — one line `runs-on:` |
| **AWS CodeBuild GHA runners** | **yes** | **yes** (EC2 compute; Lambda compute can't DinD) | ~$0.005 small → ~$0.01 4-vCPU → ~$0.02 8-vCPU | low — one CloudFormation + webhook |
| AWS Fargate / ECS | yes | **no** — no privileged / docker-in-docker | cheap | medium (but blocks our compose lane) |
| raw EC2 + Terraform fleet | yes | yes | ~$0.003 spot | **high** — the original tier |

- **For pure speed:** a managed SaaS runner is the cheapest, lowest-ops option — flip
  `runs-on:` to a 4–8-vCPU WarpBuild/Blacksmith runner (~2× faster silicon), ~$6/mo,
  ~3–4 min sharded, zero infra. *Caveat for a security-focused shop: private code runs
  on a third party's infra.* No AWS-native identity, so it is a speed tool only.
- **For speed + AWS-native capability:** **AWS CodeBuild as a GitHub Actions runner** is
  the right vehicle — a *managed AWS service* (no AMI/NAT/autoscaler), EC2-mode compute
  supports docker-in-docker, and because it runs *in our account* it carries an IAM role
  (native Bedrock / `aws_core` STS testing, no long-lived creds). ~$18/mo sharded and an
  **afternoon** of setup, not the multi-day fleet. This — not the Terraform EC2 fleet —
  is the concrete form the deferred AWS-native runner should take.
- **The ~1.5–2 min floor is vendor-independent:** no provider pre-warms *our* boot
  (migrate + plugin install), so sub-2-min still needs the AMI/template-DB floor work
  regardless of who runs the container.

## Recommendation

1. **Now (speed): shard the all-plugins test lane across 3 free 2-core runners.**
   Specced as `req-dev-validation-all-plugins-lane-7`. ~60% wall-clock cut, ~$5/mo, no
   structural change.
2. **Defer the AWS-native runner to a capability trigger, not a speed trigger** — the
   first test that genuinely must execute inside AWS (a real Bedrock or live-`aws_core`
   integration test). Specced as an Out-Of-Scope entry with that trigger; do not
   provision before it fires. When it fires, prefer **AWS CodeBuild GHA runners** (managed,
   in-account IAM, DinD, ~an afternoon) over a hand-built EC2 fleet — see the lanes table
   above; reuse the External-ID discipline from [[aws-cross-account-assume-role]]. If pure
   *speed* is ever wanted before then, a managed SaaS runner (`runs-on:` swap) is the
   cheapest lever and needs no AWS at all.
3. **Org migration is a separate decision** — pursue it for branch-protection +
   required checks (the trust-boundary inflection in the sibling note), not for 8-core
   speed; it forces the promote→PR-gate redesign, so treat it as its own project.

## Identity isolation — the machine-account graduation step

Standing up CodeBuild requires authorizing the **AWS Connector for GitHub** App on the
CI repo. It is a single GitHub App with a **fixed permission manifest** — install is
all-or-nothing on the *permissions*; the only knob is *which repos*. Two of the perms
are load-bearing for the runner mechanism and cannot be declined:

- **Repository hooks** (write) — creates the `WORKFLOW_JOB_QUEUED` webhook.
- **Administration** (write) — registers/deregisters the ephemeral self-hosted runner
  (the runner registration-token API is admin-scoped).

Commit-statuses / pull-requests / contents come along unused (they serve the App's
CodeBuild-source-build and CodePipeline modes, which we do not use).

**As stood up today** the App is installed under the **personal `notgeorge` account**,
scoped to the **`tap` repo only**. The named, bounded risk: Administration-write sits on
a repo owned by the personal identity. This is the accepted cost of the *keyless,
managed* runner path — the narrow alternative (self-managed runner registration via a
fine-grained PAT) reintroduces a long-lived secret an AI-operated CI would hold, which is
exactly what keyless SSO was chosen to avoid. Administration-on-one-personal-repo is the
better side of that asymmetry.

**Graduation step (do at org-migration time, not before):** when TAP moves into a GitHub
**Organization** (a decision driven by branch-protection + required checks — see item 3
above and the sibling note — and likely wanted for company formation anyway), introduce a
`tap-ci-bot` **machine account**: a login-less GitHub user that *is* the identity CI acts
as. Make it a scoped **org member** (access via a team granting only the CI repos) and
re-authorize the CodeConnections connection **as the bot**. This does not shrink the App's
permission set — it relocates *whose identity* holds Administration-write off the personal
account onto a disposable, narrowly-scoped one. On a personal account the pattern is
cosmetic (you'd have to transfer `tap` to the bot or add it as an admin collaborator); it
only becomes clean isolation inside an org. So: **accept the App on `tap` under
`notgeorge` now; graduate to `tap-ci-bot` in the org when the org is created.** Do not
build the bot before the org — it is org-shaped work that does not pay off standalone.

## Prior art / sources

- GitHub Actions runner pricing (2026): 2-core $0.006, 4-core $0.012, 8-core $0.022 /min;
  larger runners are **org-only** (Team/Enterprise), no included minutes.
- The 2026 self-hosted per-minute-charge proposal ($0.002/min) → backlash → indefinite
  postponement.
- `github-aws-runners/terraform-aws-github-runner` (webhook → Lambda → ephemeral spot
  EC2, scale-to-zero); ARC (Kubernetes operator) as the heavier alternative.
