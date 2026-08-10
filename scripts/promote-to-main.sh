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
# Step 2.5 + 2.6: parallelized validation gate (req-dev-multisession-promote-gate,
# req-dev-multisession-ci-gate, req-dev-validation-product-line-lanes-6).
#
# Two validation surfaces gate the push, and they OVERLAP in wall-clock:
#
#   * CLOUD (Step 2.6) — the product-lines `test_all` union lane on AWS CodeBuild:
#     the all-plugins authority (full plugin set, real image, Tier-0-tuned). Same
#     suite the local lane would run, but definitive. Dispatched FIRST so it runs
#     while the local gates run underneath it.
#
#   * LOCAL (Step 2.5) — cold-boot gate + lean-boot gate (structural checks the
#     cloud lane does NOT do) plus a pytest lane. When the cloud gate is ACTIVE it
#     owns the full corpus, so the local pytest is only the FAST fail-fast subset
#     (`scripts/test --fast`, no gryphon corpus — deferred to the cloud). When the
#     cloud gate is INACTIVE (bootstrap / skip-hatch), the local lane is the SOLE
#     authority and runs the FULL corpus (`scripts/test --gryphon`).
#
# Wall-clock is max(local, cloud), not sum: the cloud run is kicked off, the local
# gates run in its shadow, then we JOIN on the cloud run's conclusion. A local red
# CANCELS the in-flight cloud run (saves compute). Both green ⇒ push. Either red, a
# lost-contact timeout, or an un-runnable cloud gate ⇒ abort with origin/main NOT
# advanced (fail-closed).
#
# The cloud lane runs against a THROWAWAY ref (_ci-gate/<session>), so neither
# origin/main nor origin/session/<name> moves before validation — only Step 3's
# atomic push advances them.
#
# Bootstrap: workflow_dispatch only works once the gate workflow is on origin/main;
# until then the cloud gate is SKIPPED (detected via git) and the local FULL lane is
# the sole authority for that one promote. Escape hatches: TAP_PROMOTE_CI_WORKFLOW=
# all-plugins.yml (free-runner fallback) and TAP_PROMOTE_SKIP_CI_GATE=1 (skip cloud;
# local FULL lane is authority). When the cloud gate SHOULD run, gh with the
# 'workflow' scope is REQUIRED — a missing gh fails closed rather than silently
# downgrading to a possibly-focused local stack.
# ---------------------------------------------------------------------------
CI_WORKFLOW="${TAP_PROMOTE_CI_WORKFLOW:-product-lines.yml}"
# product-lines.yml is a per-line matrix; the promote gate runs only the all-plugins
# `test_all` union lane. all-plugins.yml takes no inputs.
CI_DISPATCH_ARGS=()
[[ "$CI_WORKFLOW" == "product-lines.yml" ]] && CI_DISPATCH_ARGS=(-f line=test_all)

# Run the local validation surfaces in order. $1 = "fast" | "full". Called in a
# condition (`if ! run_local_gates ...`), so `set -e` is relaxed inside the body —
# every step handles its own failure with an explicit `|| return 1`.
run_local_gates() {
  local mode="$1"
  # DCO sign-off trailers (req-cicd-dco-signoff) — host-side and cheap, so it runs
  # first, before the stack even matters. REPORT-ONLY until CONTRIBUTING.md lands
  # as repo policy; the flip is TAP_DCO_ENFORCE=1 here and in the product-lines
  # `dco` job. Merge + bot commits exempt (the promote's pre-push merge stays clean).
  info "DCO sign-off trailer check (scripts/check-dco; report-only until CONTRIBUTING lands) ..."
  scripts/check-dco || return 1
  if ! scripts/dc ps --status running --services 2>/dev/null | grep -qx web; then
    warn "Validation gate requires this session's stack to be up (scripts/dc up -d)."
    return 1
  fi
  # Clear mypy's incremental cache — it goes stale across the pre-push merge when a
  # merge moves/deletes a module (content-hash invalidation misses the tree-structure
  # change → false import-untyped in the mypy guard). The .githooks/post-merge hook
  # also clears it; this is the hook-independent fail-safe on the branch that advances
  # origin/main. (Standardizes the fix for the github_core false red on tip a94bc98c.)
  info "Clearing mypy incremental cache (post-merge staleness guard) ..."
  scripts/dc exec -T web sh -c 'rm -rf /app/.mypy_cache' 2>/dev/null || true
  if [[ "$mode" == "full" ]]; then
    # Sole authority: run the FULL corpus. --gryphon forces the gryphon corpus ON
    # regardless of the diff (req-dev-validation-suite-tiers-4).
    info "Local pytest — FULL lane (scripts/test --gryphon; cloud gate inactive → sole authority) ..."
    scripts/test --gryphon || return 1
  else
    # Cloud owns the full corpus incl. gryphon; local runs the fast fail-fast subset.
    info "Local pytest — FAST lane (scripts/test --fast; cloud gate owns the full corpus incl. gryphon) ..."
    scripts/test --fast || return 1
  fi
  # Cold-boot gate — a cold boot from zero, per-profile resolution, real backend/health.
  # Boots the full `test_all` union, so it is inherently a FULL-install check; on a
  # focused session it SKIPS via --skip-if-not-installable and the cloud lane owns full
  # cold-boot truth (req-dev-validation-all-plugins-lane). On a full stack it runs.
  info "Local pytest GREEN. Cold-boot gate (scripts/gate; skips on a focused stack) ..."
  scripts/gate --skip-if-not-installable || return 1
  # Lean-boot independence — catches a core module importing a plugin-only dependency
  # (requests/jwt class) in an isolated core-only venv where the leak fails loud; the
  # cold-boot gate's full venv hides it (req-dev-validation-lean-boot).
  info "Cold-boot gate GREEN. Lean-boot independence gate (scripts/gate-lean) ..."
  scripts/gate-lean || return 1
  info "Local gates GREEN (pytest + cold-boot + lean-boot)."
  return 0
}

if [[ "$DRY_RUN" -eq 1 ]]; then
  info "[dry-run] would: dispatch $CI_WORKFLOW (line=test_all) on the merged tree, run the local gates (scripts/test --fast + cold-boot + lean-boot) CONCURRENTLY in its shadow, JOIN on the cloud run, and push only if both are green. When the cloud gate is bootstrap/skipped, would run the FULL local lane (--gryphon) as the sole authority instead."
else
  # --- Decide the cloud gate's disposition. ---
  CLOUD_ACTIVE=0
  if ! git cat-file -e "origin/main:.github/workflows/$CI_WORKFLOW" 2>/dev/null; then
    warn "Cloud gate workflow ($CI_WORKFLOW) not yet on origin/main — bootstrap promote, cloud gate SKIPPED."
    warn "The local FULL lane is the sole authority for this one promote. Every promote after is cloud-gated."
  elif [[ "${TAP_PROMOTE_SKIP_CI_GATE:-0}" == "1" ]]; then
    warn "TAP_PROMOTE_SKIP_CI_GATE=1 — SKIPPING the cloud gate. The local FULL lane is the authority."
    warn "Only this stack's installed plugin subset is validated locally; do this only when the full set is known green another way."
  else
    # Cloud gate SHOULD run — require gh (fail-closed: never silently downgrade to a
    # possibly-focused local stack when cloud validation was expected).
    command -v gh >/dev/null 2>&1 || fail "Cloud gate is live (workflow on origin/main) but 'gh' is not installed/on PATH. Install+auth gh, or set TAP_PROMOTE_SKIP_CI_GATE=1 if the full set is validated another way."
    gh repo view --json nameWithOwner -q .nameWithOwner >/dev/null 2>&1 || fail "gh could not resolve the repo (auth?). Run 'gh auth login' (needs the 'workflow' scope)."
    CLOUD_ACTIVE=1
  fi

  if [[ "$CLOUD_ACTIVE" -eq 0 ]]; then
    # --- Serial: local FULL lane is the sole authority (bootstrap / skip-hatch). ---
    bold "Development-validation gate on the merged tree (local FULL lane — cloud gate inactive)"
    run_local_gates full || fail "Local validation RED — aborting promote. origin/main is NOT advanced (req-dev-validation-promote-hook-2). Fix and re-run."
    info "Validation GREEN — proceeding to push."
  else
    # --- Parallel: kick off the cloud gate, run local gates in its shadow, join. ---
    bold "Parallel validation gate (cloud CodeBuild lane + local gates overlap)"
    TIP="$(git rev-parse HEAD)"
    CI_REF="_ci-gate/$SESSION"
    info "Publishing merged tree to origin/$CI_REF (throwaway ref) for the cloud gate ..."
    git push -f origin "HEAD:refs/heads/$CI_REF" >/dev/null 2>&1 || fail "Could not publish the CI ref origin/$CI_REF."
    # Clean the throwaway ref up on ANY exit path from here on.
    _ci_cleanup() { git push origin --delete "$CI_REF" >/dev/null 2>&1 || true; }
    trap _ci_cleanup EXIT
    info "Dispatching $CI_WORKFLOW on $CI_REF ($TIP) ..."
    # Snapshot the time just before dispatch. A re-promote of the SAME commit (e.g. after a
    # transient gate red) leaves STALE runs with the identical headSha; since workflow_dispatch
    # returns no run id, a naive "newest run for this SHA" polled right after dispatch can grab
    # one of those stale runs (the fresh one hasn't registered yet) and then abort on its old
    # conclusion. Match only a run CREATED after this dispatch. 30s back-buffer absorbs
    # GitHub/local clock skew (macOS `date -v`; GNU `date -d` fallback).
    _ci_since="$(date -u -v-30S +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '30 seconds ago' +%Y-%m-%dT%H:%M:%SZ)"
    # Empty-array expansion under `set -u` on bash 3.2 (macOS) needs the +alt-value guard.
    gh workflow run "$CI_WORKFLOW" --ref "$CI_REF" "${CI_DISPATCH_ARGS[@]+"${CI_DISPATCH_ARGS[@]}"}" >/dev/null 2>&1 || fail "Failed to dispatch $CI_WORKFLOW on $CI_REF (does the token carry the 'workflow' scope?)."
    # workflow_dispatch does not return a run id — poll for OUR run (exact SHA, created after
    # the dispatch snapshot), newest-wins if somehow more than one.
    RUN_ID=""
    for _ in $(seq 1 40); do
      RUN_ID="$(gh run list --workflow "$CI_WORKFLOW" --branch "$CI_REF" --json databaseId,headSha,createdAt \
                  -q "[.[] | select(.headSha==\"$TIP\" and .createdAt >= \"$_ci_since\")] | sort_by(.createdAt) | last | .databaseId" 2>/dev/null || true)"
      [[ -n "$RUN_ID" && "$RUN_ID" != "null" ]] && break
      sleep 5
    done
    [[ -n "$RUN_ID" && "$RUN_ID" != "null" ]] || fail "Could not locate the dispatched CI run for $TIP on $CI_REF."
    info "Cloud gate running: $CI_WORKFLOW run $RUN_ID (~6-8 min). Running local gates underneath it ..."

    # Local gates run NOW, concurrently with the cloud run. Fail-fast: a local red
    # cancels the in-flight cloud run to save compute, then aborts.
    if ! run_local_gates fast; then
      warn "Local gates RED — cancelling in-flight cloud run $RUN_ID to save compute ..."
      gh run cancel "$RUN_ID" >/dev/null 2>&1 || true
      fail "Local gates RED — aborting promote. origin/main is NOT advanced (req-dev-validation-promote-hook-2). Fix and re-run."
    fi

    # JOIN: local is green; now wait on the cloud run's REAL conclusion.
    # NB: `gh run watch --exit-status` conflates "CI failed" with "gh itself errored" — a
    # transient API blip (e.g. HTTP 401 mid-watch) exits non-zero and would false-abort a
    # green run. Drive the poll ourselves: treat gh/API errors as transient (retry), and
    # let only a completed non-success abort. Fail-closed — a timeout or sustained
    # lost-contact still refuses to push.
    info "Local gates GREEN — joining on cloud run $RUN_ID ..."
    CI_CONCLUSION=""
    _ci_errs=0
    for _ in $(seq 1 240); do          # 240 * 15s = 60 min ceiling
      _ci_line="$(gh run view "$RUN_ID" --json status,conclusion \
                    -q '.status + "|" + (.conclusion // "")' 2>/dev/null || true)"
      if [[ -z "$_ci_line" ]]; then
        _ci_errs=$((_ci_errs + 1))
        [[ "$_ci_errs" -ge 20 ]] && fail "Lost contact with GitHub polling cloud run $RUN_ID (20 consecutive errors) \
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
    [[ "$CI_CONCLUSION" == "success" ]] || fail "Cloud gate not green (run $RUN_ID, \
conclusion='${CI_CONCLUSION:-<timeout/unknown>}') — aborting promote. origin/main is NOT advanced \
(req-dev-multisession-ci-gate-2). Inspect: gh run view $RUN_ID --log-failed"
    info "Cloud gate GREEN (run $RUN_ID) + local gates GREEN — proceeding to push."
    _ci_cleanup
    trap - EXIT
  fi
fi

# ---------------------------------------------------------------------------
# Step 2.9: red-gate abort (req-cicd-branch-protection-4). Checks earned by the
# cloud run on the throwaway _ci-gate ref do NOT satisfy ruleset evaluation for
# a direct push to main (proven 2026-08-10: a lone green check still evaluated
# as a violation) — so this preflight cannot make the push "pass on merit"; the
# admin bypass is structural until the PR-flow rework. What it DOES do: abort,
# with origin/main untouched, if the latest "gate" check on the pushed SHA is
# red, pending, or missing — the class of mistake the bypass would otherwise
# silently wave through. When the cloud gate was skipped (bootstrap/skip-hatch)
# no check exists and bypass is the documented mechanism - assertion scoped out.
# ---------------------------------------------------------------------------
if [[ "${CLOUD_ACTIVE:-0}" == "1" && "$DRY_RUN" -ne 1 ]]; then
  PUSH_SHA="$(git rev-parse "$BRANCH")"
  LATEST_GATE="$(gh api "repos/{owner}/{repo}/commits/$PUSH_SHA/check-runs?check_name=gate&per_page=50" \
    --jq '[.check_runs[]] | sort_by(.started_at) | last | (.conclusion // "pending")' 2>/dev/null || echo "unqueryable")"
  case "$LATEST_GATE" in
    success)
      info "Ruleset preflight: latest 'gate' check on $PUSH_SHA is green. (The push itself still rides the admin bypass — throwaway-ref checks never satisfy the ruleset; see req-cicd-branch-protection.)" ;;
    unqueryable)
      warn "Ruleset preflight: check-runs unqueryable (gh/API hiccup) — proceeding; watch for a 'Bypassed rule violations' line below." ;;
    *)
      fail "Ruleset preflight: latest 'gate' check on $PUSH_SHA is '$LATEST_GATE', not success — refusing to push over a red/missing gate. Re-run, or inspect: gh api repos/{owner}/{repo}/commits/$PUSH_SHA/check-runs" ;;
  esac
fi

# ---------------------------------------------------------------------------
# Step 3: atomic dual-refspec push (req-dev-multisession-push-workflow-3).
# Without --atomic the server may apply each refspec independently — a non-FF
# on one ref could still leave the other update applied. With --atomic, both
# refs advance or neither does.
# ---------------------------------------------------------------------------
bold "Atomic push: origin/main and origin/$BRANCH"
if [[ "$DRY_RUN" -eq 1 ]]; then
  dry git push --atomic origin "$BRANCH:main" "$BRANCH:$BRANCH"
else
  # Capture the remote's messages: a "Bypassed rule violations" line means the
  # server-side gate did NOT pass on merit and the admin-role bypass carried the
  # push. Loud, review-visible telemetry until the bypass list is shrunk to a
  # dedicated promote identity (req-cicd-branch-protection ladder rung 3).
  PUSH_OUT="$(git push --atomic origin "$BRANCH:main" "$BRANCH:$BRANCH" 2>&1)" \
    || { printf '%s\n' "$PUSH_OUT"; fail "Atomic push failed."; }
  printf '%s\n' "$PUSH_OUT"
  if grep -q "Bypassed rule violations" <<<"$PUSH_OUT"; then
    warn "ADMIN BYPASS: the push landed by bypassing the main ruleset (see remote messages above),"
    warn "not by satisfying the required 'gate' check. Expected ONLY for bootstrap/skip-gate promotes;"
    warn "otherwise investigate the gate check on the pushed SHA (req-cicd-branch-protection)."
  fi
fi

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
