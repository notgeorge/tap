#!/usr/bin/env bash
# scripts/promote-to-main.sh — promote the current session worktree's commits
# to origin/main.
#
# Implements req-dev-multisession-promote-script (specs/spec-dev-multisession.md)
# which codifies steps 1–4 of req-dev-multisession-push-workflow as one
# invocation:
#   1. Fetch origin/main.
#   2. Pre-push merge of origin/main into the session branch (surfaces real
#      conflicts in the session worktree, the right place to resolve them).
#   3. Atomic dual-refspec push: advance origin/main AND origin/session/<name>
#      in one operation so neither lands without the other.
#   4. Sync the primary worktree (git -C ~/tap-sessions/main pull --ff-only)
#      so the local main ref the next spawn branches from is current.
#
# Companion: scripts/promote-all-sessions.sh iterates the registry and calls
# this script in each worktree in turn.
#
# Usage:
#   scripts/promote-to-main.sh           # promote this session
#   scripts/promote-to-main.sh --dry-run # report what would happen; no writes
#

set -euo pipefail

bold() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
info() { printf "    %s\n" "$1"; }
warn() { printf "\033[33m    %s\033[0m\n" "$1"; }
fail() { printf "\033[31m    ERROR: %s\033[0m\n" "$1" >&2; exit 1; }

DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '/^# Usage:/,/^# *$/p' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    -*) fail "Unknown flag: $1" ;;
    *)  fail "Unexpected arg: $1" ;;
  esac
done

# Mirror real git ops vs a "would: ..." log line, depending on --dry-run.
dry() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "[dry-run] would: $*"
  else
    "$@"
  fi
}

# Operate on the worktree we were invoked from, not the script's location —
# the orchestrator cd's into each session before calling us.
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || fail "Not inside a git worktree."
cd "$REPO"

# Sanity: must be on a session/<name> branch
# (req-dev-multisession-push-workflow-1 — never edit on main).
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
case "$BRANCH" in
  session/*) SESSION="${BRANCH#session/}" ;;
  main)      fail "On 'main' — promote from a session worktree, not the main worktree." ;;
  HEAD)      fail "Detached HEAD. Checkout the session branch first." ;;
  *)         fail "Unexpected branch '$BRANCH'. Expected 'session/<name>'." ;;
esac

# Sanity: clean working tree. Merge would refuse anyway, but a clear message
# is friendlier than git's default. Untracked files are fine (e.g. .env.local,
# .dev-credentials) — only staged/unstaged changes block us.
if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "Working tree is not clean. Commit or stash before promoting."
fi

bold "Promoting $BRANCH → origin/main"

# ---------------------------------------------------------------------------
# Step 1: fetch.
# ---------------------------------------------------------------------------
info "Fetching origin/main..."
dry git fetch origin main

# Snapshot how this branch sits against origin/main.
AHEAD="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "0")"
BEHIND="$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "0")"
info "  ahead of origin/main:  $AHEAD"
info "  behind origin/main:    $BEHIND"

if [[ "$AHEAD" -eq 0 ]]; then
  info "Nothing to push. Done."
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 2: pre-push merge (req-dev-multisession-push-workflow-2).
# Skip when not behind to avoid a redundant empty merge commit.
# ---------------------------------------------------------------------------
if [[ "$BEHIND" -gt 0 ]]; then
  info "Pre-push merge: merging origin/main into $BRANCH ($BEHIND commits behind)..."
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "[dry-run] would: git merge --no-edit origin/main"
  else
    if ! git merge --no-edit origin/main; then
      git merge --abort 2>/dev/null || true
      fail "Merge conflicted. Aborted. Resolve manually on $BRANCH, commit, then re-run."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Step 2.5: development-validation gate (req-dev-multisession-promote-gate ↔
# req-dev-validation-promote-hook). Runs AFTER the pre-push merge so it validates
# the exact tree that will become origin/main, and BEFORE the atomic push so red
# blocks the advance — a session never publishes a tree it has not validated,
# which is what protects every session spawned from local main.
#
# The gate stands up a fresh scratch DB inside the running compose image and runs
# the ordered cold-boot cycle; it is not reimplemented here. On --dry-run we skip
# it (there is no push to gate). It requires the session's stack to be up.
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
  info "[dry-run] would: scripts/test (full lane) then scripts/gate (cold-boot gate) then scripts/gate-lean (lean-boot independence)"
else
  bold "Development-validation gate on the merged tree"
  if ! scripts/dc ps --status running --services 2>/dev/null | grep -qx web; then
    fail "Validation gate requires this session's stack to be up (scripts/dc up -d). \
Refusing to promote an unvalidated tree to origin/main (req-dev-validation-promote-hook)."
  fi
  # Three composed surfaces (req-dev-validation-suite-tiers-1, req-dev-validation-promote-hook):
  #   1. Full pytest lane — catches unit/functional regressions (e.g. a stale
  #      collector key red'ing a unit test — the exact class that shipped to main
  #      before this hook existed).
  #   2. Cold-boot gate — catches what the suite structurally cannot: a cold boot
  #      from zero, per-profile resolution, the real backend, real health. It boots
  #      the full `test_all` union, so it is inherently a FULL-install check; on a
  #      focused session (a plugin subset installed) it SKIPS via
  #      --skip-if-not-installable and the all-plugins CI lane (Step 2.6) owns full
  #      cold-boot truth (req-dev-validation-all-plugins-lane). On a full stack it runs.
  #   3. Lean-boot independence gate — catches what BOTH above structurally cannot:
  #      a core module importing a plugin-only dependency (requests/jwt class). The
  #      cold-boot gate reuses this stack's FULL venv where the leak is invisible;
  #      gate-lean stands up a separate stack with a core-only venv (~1 min) where
  #      the leak fails loud. It branches the throwaway off HEAD (the just-merged
  #      session tree — the exact tree about to become origin/main; local `main`
  #      isn't advanced until after the push) and nukes itself on exit.
  #      (req-dev-validation-lean-boot)
  info "Full test lane (scripts/test) ..."
  if ! scripts/test; then
    fail "Full test lane RED — aborting promote. origin/main is NOT advanced \
(req-dev-validation-promote-hook-2). Fix the failing test(s) and re-run."
  fi
  info "Full test lane GREEN. Cold-boot gate (scripts/gate; skips on a focused stack) ..."
  if ! scripts/gate --skip-if-not-installable; then
    fail "Cold-boot gate RED — aborting promote. origin/main is NOT advanced \
(req-dev-validation-promote-hook-2). Fix the failing step and re-run."
  fi
  info "Cold-boot gate GREEN. Lean-boot independence gate (scripts/gate-lean) ..."
  if ! scripts/gate-lean; then
    fail "Lean-boot gate RED — aborting promote. origin/main is NOT advanced \
(req-dev-validation-promote-hook-2). Read the VERDICT line in the *-diag.log for the \
classified cause — image-build/infra (a network flake, not your code) vs. import-leak \
(a core module importing a plugin-only dependency) vs. boot/health — then the \
/diagnose-failed-session-spawn skill."
  fi
  info "Validation GREEN (full lane + cold-boot gate + lean-boot gate) — proceeding to push."
fi

# ---------------------------------------------------------------------------
# Step 2.6: all-plugins CI gate (req-dev-multisession-ci-gate, option B).
# The local Step 2.5 gate only validates the plugins installed in THIS stack.
# Once plugins leave the monorepo, all-plugins truth is server-side
# (req-dev-validation-all-plugins-lane); this step triggers that lane on the
# exact merged tree and blocks the atomic push on red — the reciprocal that
# protects main's full plugin set. Option B (trigger + poll) is used, not a
# PR-gated merge, specifically so Step 3's atomic dual-refspec push survives.
#
# It runs the lane against a THROWAWAY ref (not the session branch), so neither
# origin/main nor origin/session/<name> moves before validation — the atomic
# push in Step 3 stays the only thing that advances them.
#
# Bootstrap: workflow_dispatch only works once .github/workflows/all-plugins.yml
# is on origin/main. Until the first promote lands it there, this gate cannot
# run and is SKIPPED — that first promote is ungated by construction. Detection
# uses git (the file's presence on origin/main), so bootstrap needs no gh.
#
# Escape hatch: TAP_PROMOTE_SKIP_CI_GATE=1 skips loudly — use only when the full
# plugin set is validated another way (e.g. a full-monorepo local lane where the
# stack already has every plugin installed, as in the session that landed this).
# ---------------------------------------------------------------------------
CI_WORKFLOW="all-plugins.yml"
if [[ "$DRY_RUN" -eq 1 ]]; then
  info "[dry-run] would: trigger the all-plugins CI lane on the merged tree and poll to green before pushing (unless bootstrap or TAP_PROMOTE_SKIP_CI_GATE)"
elif ! git cat-file -e "origin/main:.github/workflows/$CI_WORKFLOW" 2>/dev/null; then
  warn "all-plugins CI workflow not yet on origin/main — bootstrap promote, all-plugins CI gate SKIPPED."
  warn "Expected exactly once: the promote that first lands .github/workflows/$CI_WORKFLOW on main. Every promote after is gated."
elif [[ "${TAP_PROMOTE_SKIP_CI_GATE:-0}" == "1" ]]; then
  warn "TAP_PROMOTE_SKIP_CI_GATE=1 — SKIPPING the all-plugins CI gate (req-dev-multisession-ci-gate)."
  warn "Only this stack's installed plugin subset is server-validated. Do this only when the full set is known green another way."
else
  bold "All-plugins CI gate on the merged tree (req-dev-multisession-ci-gate)"
  command -v gh >/dev/null 2>&1 || fail "The all-plugins CI gate is live (workflow on origin/main) but 'gh' is not installed/on PATH — cannot validate the full plugin set. Install+auth gh, or set TAP_PROMOTE_SKIP_CI_GATE=1 if the full set is validated another way."
  gh repo view --json nameWithOwner -q .nameWithOwner >/dev/null 2>&1 || fail "gh could not resolve the repo (auth?). Run 'gh auth login' (needs the 'workflow' scope)."
  TIP="$(git rev-parse HEAD)"
  CI_REF="_ci-gate/$SESSION"
  info "Publishing merged tree to origin/$CI_REF (throwaway ref) for CI ..."
  git push -f origin "HEAD:refs/heads/$CI_REF" >/dev/null 2>&1 || fail "Could not publish the CI ref origin/$CI_REF."
  # Clean the throwaway ref up on ANY exit path from here on.
  _ci_cleanup() { git push origin --delete "$CI_REF" >/dev/null 2>&1 || true; }
  trap _ci_cleanup EXIT
  info "Dispatching $CI_WORKFLOW on $CI_REF ($TIP) ..."
  gh workflow run "$CI_WORKFLOW" --ref "$CI_REF" >/dev/null 2>&1 || fail "Failed to dispatch $CI_WORKFLOW on $CI_REF (does the token carry the 'workflow' scope?)."
  # workflow_dispatch does not return a run id — poll for the run on our exact SHA.
  RUN_ID=""
  for _ in $(seq 1 40); do
    RUN_ID="$(gh run list --workflow "$CI_WORKFLOW" --branch "$CI_REF" --json databaseId,headSha \
                -q "[.[] | select(.headSha==\"$TIP\")][0].databaseId" 2>/dev/null || true)"
    [[ -n "$RUN_ID" && "$RUN_ID" != "null" ]] && break
    sleep 5
  done
  [[ -n "$RUN_ID" && "$RUN_ID" != "null" ]] || fail "Could not locate the dispatched CI run for $TIP on $CI_REF."
  info "Watching all-plugins CI run $RUN_ID (the full lane — ~20-30 min) ..."
  # NB: `gh run watch --exit-status` conflates "CI failed" with "gh itself errored" — a
  # transient API blip (e.g. HTTP 401 mid-watch over a 20-30 min run) exits non-zero and would
  # false-abort a perfectly green run. Drive the poll ourselves and decide on the run's REAL
  # conclusion: treat gh/API errors as transient (retry), and let only a completed non-success
  # abort. Fail-closed is preserved — a timeout or sustained lost-contact still refuses to push.
  CI_CONCLUSION=""
  _ci_errs=0
  for _ in $(seq 1 240); do          # 240 * 15s = 60 min ceiling
    _ci_line="$(gh run view "$RUN_ID" --json status,conclusion \
                  -q '.status + "|" + (.conclusion // "")' 2>/dev/null || true)"
    if [[ -z "$_ci_line" ]]; then
      _ci_errs=$((_ci_errs + 1))
      [[ "$_ci_errs" -ge 20 ]] && fail "Lost contact with GitHub polling CI run $RUN_ID (20 consecutive errors) \
— cannot confirm green, so refusing to push. origin/main is NOT advanced. Check gh auth; inspect: gh run view $RUN_ID"
      sleep 15
      continue
    fi
    _ci_errs=0
    if [[ "${_ci_line%%|*}" == "completed" ]]; then
      CI_CONCLUSION="${_ci_line##*|}"
      break
    fi
    sleep 15
  done
  [[ "$CI_CONCLUSION" == "success" ]] || fail "All-plugins CI lane not green (run $RUN_ID, \
conclusion='${CI_CONCLUSION:-<timeout/unknown>}') — aborting promote. origin/main is NOT advanced \
(req-dev-multisession-ci-gate-2). Inspect: gh run view $RUN_ID --log-failed"
  info "All-plugins CI lane GREEN (run $RUN_ID) — proceeding to push."
  _ci_cleanup
  trap - EXIT
fi

# ---------------------------------------------------------------------------
# Step 3: atomic dual-refspec push (req-dev-multisession-push-workflow-3).
# Without --atomic the server may apply each refspec independently — a non-FF
# on one ref could still leave the other update applied. With --atomic, both
# refs advance or neither does.
# ---------------------------------------------------------------------------
bold "Atomic push: origin/main and origin/$BRANCH"
dry git push --atomic origin "$BRANCH:main" "$BRANCH:$BRANCH"

# ---------------------------------------------------------------------------
# Step 4: sync the primary worktree (req-dev-multisession-push-workflow-4).
# Load-bearing for spawn-session.sh: the next spawn branches from local main.
# ---------------------------------------------------------------------------
bold "Syncing primary worktree"
MAIN_WORKTREE="$HOME/tap-sessions/main"
if [[ -d "$MAIN_WORKTREE/.git" || -f "$MAIN_WORKTREE/.git" ]]; then
  dry git -C "$MAIN_WORKTREE" pull --ff-only origin main
else
  warn "Main worktree at $MAIN_WORKTREE not found; skipped."
  warn "If this is a non-standard checkout, advance local main manually before the next spawn."
fi

info "Promoted '$SESSION' to origin/main."
