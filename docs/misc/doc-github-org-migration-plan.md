---
title: GitHub Organization Migration Plan
spec: tap_plugins/specs/spec-plugin-external-development.md
audience:
  - llm
  - developer
status: plan
---

# GitHub Organization Migration Plan

Move the TAP repositories from the personal account `notgeorge` to a GitHub **Organization**.

Decided 2026-07-21 as the next GitHub-cleanup work. Nothing is broken today — this is
optionality plus Aug-1 external-developer readiness, and it unblocks two already-deferred
requirements. Written up so it does not live only in a chat log.

## Why — the forcing functions, in the order they actually bit

1. **Token sprawl.** A personal account has **no organization-level Actions secrets**, so
   the `TAP_CORE_RO_PAT` that the per-repo CI needs must be set on **every plugin repo**
   and re-set on every one at each rotation. That friction is why a broad read-only PAT
   was chosen over per-repo scoping (2026-07-21) — the secure option was the inconvenient
   one. An org inverts that: one org secret with a repo allowlist, or better, a **GitHub
   App** whose installation tokens are short-lived, per-repo scoped, auto-rotating, and
   not tied to a human account.
2. **Governance applied once instead of seventeen times.** Org rulesets push branch
   protection / required checks / required reviews across every plugin repo from one
   place. Today "protect `main` everywhere" is a per-repo config that will drift. The
   external-dev kit already calls for protected main + PR-back review.
3. **`CODEOWNERS` can only name individual users** on a personal account. The
   guard-integrity work uses CODEOWNERS; team ownership (`@org/team`) needs an org, and
   it is how the single-named-owner bottleneck goes away.
4. **Signing is blocked on this.** `req-plugin-extdev-signing` (#5) and
   `req-cicd-supply-chain-provenance` are already pinned to the org refactor because
   Sigstore/OIDC provenance claims are org-rooted (`repo:org/name`).
5. **External developers arrive ~Aug 1.** On a personal account every external dev is a
   collaborator on personal repos. An org gives scoped teams and a boundary between "our
   plugins" and "theirs" — and avoids onboarding devs under a credential model we then
   migrate underneath them.
6. **A home for the package index.** The deferred `index` / `wheelhouse` source paths
   (`req-plugin-arch-sources-3` / `-6`) need somewhere to live; org-scoped GitHub Packages
   is the natural answer.

## Measured inventory (2026-07-21 — verified, not estimated)

### Repositories: 17 under `notgeorge`

| Class | Repos | Migrate? |
| --- | --- | --- |
| Core | `tap` | yes |
| Live plugins (in boot profiles) | `tap-plugin-` + `administrivia`, `computing-core`, `roscale`, `identity-core`, `aws-core`, `sigstore-core`, `github-core`, `compliance-core`, `fedramp-20x-ksi`, `samsite`, `grid-fixtures`, `gryphon-playground` (12) | yes |
| Deferred but real | `tap-plugin-aws-secrets-source` (build-bake eviction still open) | yes |
| Dead weight | `tap-plugin-aws`, `tap-plugin-genericom` (plugin deleted), `tap-plugin-lotr` (already archived) | **decide** — leaving them behind is a feature |

The migration is the natural moment to decide what does *not* come. Archived/dead repos
can stay on the personal account as an archaeology shelf.

### In-repo changes: ~30 functional lines, ZERO code

| What | Count | Note |
| --- | --- | --- |
| Boot-profile `url:` entries | 26 across 4 committed profiles (`core_dev` 1, `soak` 2, `samsite` 11, `test_all` 12) | pure data |
| `.github/workflows/plugin-ci.yml` → `harness_repo` default | 1 | |
| `ci/terraform/codebuild-runners/variables.tf` → `github_owner` default | 1 | |
| `scripts/spawn-session.sh` help examples | 2 | cosmetic |
| Test fixture URLs (`test_plugin_source_auth`, `test_dev_workspace`, `test_plugin_release`) | 3 | synthetic strings |
| Docs / specs prose | ~20 | follow-up, non-blocking |

**No code changes at all.** Nothing derives a repository URL from the owner — the
boot-record `url`/`credential` is the authority and the slug is deliberately never used to
derive a URL (`spec-dev-plugin-workspace.md`). That decision is what makes this a config
migration rather than a refactor. **Do not regress it** by introducing owner-derived URLs.

## The one real risk: the PAT cliff

Fine-grained PATs are scoped to a **resource owner**. The moment the repos become
org-owned, a user-owned PAT scoped to *user* repos loses access — and an org can
additionally **require approval** for fine-grained PATs (the likely surprise). At transfer
time, plugin git-install breaks **everywhere simultaneously**: local boot, both CodeBuild
lanes, and per-repo CI.

Two amplifiers:

- **`~/tap-secrets` is shared host state** — symlinked into every session worktree, so
  re-issuing the token mutates *every live session at once*.
- The same credential is duplicated in **AWS Secrets Manager** (`tap-ci/github-plugins-ro`)
  for the CodeBuild lanes. Both copies must move together or the lanes go red.

Everything else is low-drama and reversible. **GitHub redirects old URLs for git
operations**, so boot profiles keep working after the transfer — which usefully decouples
the URL rewrite (step 5) from the transfer itself (step 3).

### Two credentials, do not conflate them

| Credential | Reads | Lives in | Consumers |
| --- | --- | --- | --- |
| `github-plugins-ro` | plugin repos (**404 on core** — verified) | `~/tap-secrets/tap_plugins/…`, AWS Secrets Manager | local pre-boot install, CodeBuild lanes |
| `TAP_CORE_RO_PAT` (`harness_pat`) | core `tap` only | GitHub Actions repo secret on the plugin repo | per-repo CI conformance job |

They point in **opposite directions** and must stay separate even while both are broad.

## Sequence

Each step independently verifiable; risk-ordered so the scary part is proven on one repo.

0. **Decide.** Org name. Which dead repos stay behind. Free vs paid tier.
1. **Create the org**; install the AWS Connector GitHub App on it. **Transfer nothing yet.**
2. **PILOT: transfer ONE repo — `grid-fixtures`.** Re-issue a PAT scoped to the org.
   Verify: redirect works, local boot green, the pilot CI still green.
   **Then stop and assess.** This exercises the entire credential story for the price of
   one repo. (Same pilot-first discipline that found three real bugs on 2026-07-21.)
3. **Transfer the rest.**
4. **Credential swap.** Re-issue → update `~/tap-secrets` **and** AWS Secrets Manager
   together. Verify with a scratch `spawn-session.sh`.
5. **Rewrite boot URLs + the two defaults**; promote through the normal gate.
6. **Terraform.** `github_owner` + a new CodeConnections (one-time manual authorize in the
   AWS console); `terraform apply`; verify a CodeBuild lane green. Safe now that tfstate is
   in S3 (`s3://tap-ci-tfstate`) — this would have been genuinely risky before 2026-07-21.
7. **Org hardening.** Org secret replaces the per-repo `TAP_CORE_RO_PAT`; delete the
   per-repo copy; Actions `access_level` → `organization` (currently `user`); org rulesets.
8. **Docs/specs prose sweep.**

Steps 1–4 are the disruptive window (a few hours, much of it GitHub UI work only George can
do). 5–8 are ordinary work.

### Verification gates

| After | Check |
| --- | --- |
| 2 | `spawn-session.sh` boots with the transferred repo git-sourced; `gh run list` on that repo is green |
| 4 | a scratch spawn installs **all** plugins; both CodeBuild lanes dispatch green |
| 5 | `scripts/gate` green; promote gate green |
| 6 | `terraform plan` clean; a real `product-lines` run succeeds |
| 7 | a plugin repo's CI passes using the **org** secret, per-repo secret deleted |

## Do this during the migration, not after

**Move plugin-pull from a PAT to a GitHub App installation token.** It is the end state
regardless; doing it *during* the transfer avoids a second credential swap, and it removes
the "read-everything token sitting in a repo secret" pattern **before** external developers
inherit it. An external dev holding a token that reads the whole account is a materially
different risk from us holding one — and anyone who can push a workflow to their own plugin
repo can exfiltrate whatever secret that repo holds.

## Open questions — verify before relying on them

- **Free vs Team tier**: org rulesets / required workflows may need a paid tier. Confirm
  before building the governance plan on them.
- **CodeConnections**: can the existing connection be re-pointed at an org, or must it be
  recreated? Likely recreated, which means a brief CI outage inside step 6.
- **Org PAT-approval policy**: whether fine-grained PATs need explicit org approval — the
  most probable cause of a surprise in step 2, which is exactly why step 2 is one repo.

## Status of the work this plan came out of (all landed, `origin/main` `f9fec738`)

- Migration squash + re-release wave complete; plugin fleet on post-squash tags.
- CodeBuild tfstate recovered into S3 (prerequisite for step 6).
- `plugin-ci.yml` — the reusable per-plugin CI — **fixed and proven green** on
  `tap-plugin-grid-fixtures` (2026-07-21). It had never compiled; three defects were found
  by finally running it. This is CI lane 2 of the three-lane model.
- Core Actions `access_level` set `none` → `user` so plugin repos can call it.

### Not yet done, and NOT blocked on the org

- **11 remaining plugin repos have no CI.** Deliberately held: each one wired now is one
  re-configured after the migration. Wire them in step 7, using the org secret.
- `roscale`'s in-package manifest test resolves its plugin root to `/app` when run from an
  installed wheel (validates core as a plugin, fails). Latent today; will surface when lane
  2 runs against installed plugins.
- `plugin-ci.yml` pins `astral-sh/setup-uv@v5`, which triggers a Node 20 deprecation
  warning on GitHub runners.
