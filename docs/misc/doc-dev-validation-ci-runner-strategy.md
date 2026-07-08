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

## Recommendation

1. **Now (speed): shard the all-plugins test lane across 3 free 2-core runners.**
   Specced as `req-dev-validation-all-plugins-lane-7`. ~60% wall-clock cut, ~$5/mo, no
   structural change.
2. **Defer the AWS-native runner to a capability trigger, not a speed trigger** — the
   first test that genuinely must execute inside AWS (a real Bedrock or live-`aws_core`
   integration test). Specced as an Out-Of-Scope entry with that trigger; do not
   provision before it fires. When it fires: `github-aws-runners/terraform-aws-github-runner`
   (maintained successor to `philips-labs/…`), **ephemeral spot** runners, pre-baked
   AMI (Docker + Postgres warm to erase the build/boot tax), least-privilege IAM role
   reusing the External-ID discipline from [[aws-cross-account-assume-role]].
3. **Org migration is a separate decision** — pursue it for branch-protection +
   required checks (the trust-boundary inflection in the sibling note), not for 8-core
   speed; it forces the promote→PR-gate redesign, so treat it as its own project.

## Prior art / sources

- GitHub Actions runner pricing (2026): 2-core $0.006, 4-core $0.012, 8-core $0.022 /min;
  larger runners are **org-only** (Team/Enterprise), no included minutes.
- The 2026 self-hosted per-minute-charge proposal ($0.002/min) → backlash → indefinite
  postponement.
- `github-aws-runners/terraform-aws-github-runner` (webhook → Lambda → ephemeral spot
  EC2, scale-to-zero); ARC (Kubernetes operator) as the heavier alternative.
