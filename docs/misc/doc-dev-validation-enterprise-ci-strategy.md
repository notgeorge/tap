# Enterprise CI strategy — validation "outside the laptop"

Strategy note (not authoritative spec). `specs/spec-dev-validation.md` remains the
center of gravity for validation; that spec owns the **local** pre-push gate for the
solo dog-food window. This note is the **longer-horizon sibling**: how validation
should look when it runs where the developer is not watching it — the server-side-CI
inflection the spec defers under "Out Of Scope (v0) → Server-side CI". It is
deliberately trigger-gated (CI/CD is roadmap item 5, post-July per
[[rampart-launch-ready-strategy]]); this records the shape so it can be built
deliberately, not reactively. Versioning is git; do not store dates in the body.

## The one load-bearing principle: one gate, many invokers

The single decision that separates professional setups from bolt-on CI: **the gate
is one artifact that local, promote, and CI all invoke identically** — not "CI has
its own YAML that approximates what I run locally." Same command, same compose
image, same verdict everywhere. Nautobot is the exemplar (every CI job is a thin
`poetry run invoke <task>`; CI ≡ local). TAP already leans this way via `scripts/dc`
and `scripts/test`; the dev-validation gate should be built as a single entrypoint
(`manage.py dev_validation` or `scripts/gate`) that the promote path and any future
CI both call. The failure mode this prevents: green in CI, red on the machine (or
vice versa) because the two environments diverged.

The **compose-image mandate** is part of this: the gate MUST stand up the existing
image, never a reimplemented environment (`req-dev-validation-smoke-gate-5`) — the
container's Python build is non-stock. When CI lands it runs the same image on a
runner; it does not re-describe the environment in YAML.

## Topology: three rings, the same gate moving outward

```
Ring 1  pre-commit (local, seconds)      format · lint · -m smoke        every save
Ring 2  pre-push / promote (local today) the full cold-boot gate         before main advances
Ring 3  server CI (the next inflection)  THE SAME gate, neutral hardware  every push / PR
```

Solo→team is not a rewrite — it is **the Ring-2 gate moving to Ring-3 hardware and
becoming the arbiter**. What the gate *checks* does not change; where it runs, and
who trusts the result, does.

## The real trigger is the trust boundary, not headcount

CI leaves the laptop not because a second person is dishonest, but because **"I ran
it" stops being mechanically verifiable by anyone who isn't the author** — two
environments diverge; a claim is not a proof. Server CI exists to make "green"
verifiable *by a party that is not the author*. Everything else (matrix, caching,
artifacts) is optimization on top of that one function.

At that moment `main` gets **branch protection + required status checks** — the
single highest-leverage GitHub setting. It converts the "no broken tree to main"
discipline that `scripts/promote-to-main.sh` enforces *by convention* into physics.

## The AI angle (where TAP is unusual)

1. **TAP's multi-session model already IS multi-developer — the developers are
   agents.** Worktree-per-session, isolated compose stacks, integrating through the
   promote path: a multi-contributor system where contributors are Claude/Codex
   sessions. So the second-contributor trigger may be half-fired already, and the
   promote path is already the integration bottleneck.
2. **CI is the trust arbiter for AI-generated code specifically.** An agent produces
   code fast and asserts "tests pass" confidently; you cannot audit every claim. The
   gate on neutral hardware is ground truth. This makes CI *more* important in an
   AI-heavy workflow, not less — it replaces "George happened to notice while
   dog-fooding" (the thinning safety net the dev-validation philosophy is built
   around).
3. **Ratchets are the AI-specific guardrail — the underrated part.** The
   characteristic AI failure mode is not a broken build; it is *silent quality
   erosion* (weakening an assertion to pass, dropping coverage, routing around the
   service layer). TAP's honest-coverage ratchets (authz-coverage, direct-write,
   branch-coverage floor, `xfail_strict`) are the mechanical defense — a floor an
   agent can't lower without the change being visible in a baseline diff is worth ten
   prose guidelines. Built for honesty; ideal governance for machine-authored code.
   Frame new honesty mechanisms through this lens.
4. **Machine-readable CI outputs** (JUnit XML, SARIF, coverage XML) so a triage agent
   can consume a red run and propose the fix, and `/code-review` / ultrareview /
   codex-security become pipeline stages rather than manual invocations.

## Two TAP-specific hard bits to design around

**(a) The compose-image mandate makes runners heavier than stock CI.** The gate is
not `pip install && pytest` — it is "stand up Postgres + the built image + run a real
cold-boot cycle," minutes not seconds (that fidelity is the point — it is why the
gate catches the async/queue and preboot classes NetBox/Nautobot's low-fidelity
setups miss). Start with **GitHub-hosted runners running `docker compose`**; move to a
**self-hosted runner** only when minutes-cost or environment-fidelity (secrets, data
volume, GPU for tap_ai) actually demands it. Do not provision a runner fleet before
the demand.

**(b) The promote model must evolve from atomic-push to PR-gated.** Today: session
branch → atomic dual-refspec push to `main`, gated by a trusted local run. Elegant
for solo. With multiple contributors pushing you get races/conflicts on `main` and
the "trusted laptop" assumption breaks. The evolution is **PR-based**: session branch
→ PR → CI runs the gate as a required check → merge. That is a real change to
`req-dev-multisession-push-workflow`; atomic-push and PR-gate do not compose — pick
one per branch-protection regime. Flag as needing deliberate redesign, not
incremental patching.

## Prior art (NetBox + Nautobot, from their real CI/config)

- Both: real Postgres/Redis service containers (not mocks) + a `makemigrations
  --check` missing-migration gate + a consolidated **Ruff** gate + full suite as a
  required check. Neither runs **mypy**; neither enforces a **coverage floor**
  (Nautobot has none) — so TAP's ratchets + mypy-strict are *above* both exemplars.
- Both take the **low-fidelity async path** (NetBox `django-rq` inline / Nautobot
  Celery `task_always_eager`) that the upstream docs explicitly warn against — TAP's
  real-backend cold-boot spike is genuinely ahead here; keep it.
- **Nautobot's `invoke`-tasks = CI ≡ local** is the pattern to emulate (TAP's
  `scripts/dc` + `scripts/test` already lean this way). Worth stealing later
  (trigger-gated): Nautobot's **frozen-dataset migration-upgrade test** — directly
  relevant to a versioned grid spine.
- Reviewer checklists a serious auditor cites: OpenSSF Scorecard / Best Practices
  Badge (branch-protection, SAST, dependency-update, pinned deps, token-permissions).

## Build-now vs defer (center of gravity)

- **Now — prerequisites for CI regardless, all cheap (do these even before CI):**
  finish the gate-as-single-invokable-artifact; fold `makemigrations --check` into
  the cold-boot cycle (the #1 Django gap both exemplars close, TAP does not); make
  the gate emit structured output (JUnit/SARIF).
- **At the trust-boundary trigger (post-July):** GitHub Actions running the *same*
  gate in the compose image on every push; branch protection + required checks; the
  PR-gated promote redesign; dependency + secret scanning as CI jobs (TAP already has
  the secret-leak scanner — it moves into the pipeline); pre-commit ≡ CI mirror.
- **Defer (trigger-gated, do NOT pre-build):** matrix testing (multi-Python /
  multi-DB), multi-arch builds, self-hosted runner fleets, stage/prod-validation
  siblings, release automation. Wait for the persistent-customer inflection.

Bottom line: TAP does not have a CI problem; it has a *"make the gate a clean
artifact + decide the promote regime"* problem. Solve those two and CI is a thin
wrapper standable in an afternoon whenever the trust boundary warrants it — which,
given the AI-session model, may arrive sooner than the post-July marker assumes.
</content>
