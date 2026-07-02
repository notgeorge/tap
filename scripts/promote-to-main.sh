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
  info "[dry-run] would: scripts/test (full lane) then scripts/gate (cold-boot gate)"
else
  bold "Development-validation gate on the merged tree"
  if ! scripts/dc ps --status running --services 2>/dev/null | grep -qx web; then
    fail "Validation gate requires this session's stack to be up (scripts/dc up -d). \
Refusing to promote an unvalidated tree to origin/main (req-dev-validation-promote-hook)."
  fi
  # Two composed surfaces (req-dev-validation-suite-tiers-1, req-dev-validation-promote-hook):
  #   1. Full pytest lane — catches unit/functional regressions (e.g. a stale
  #      collector key red'ing a unit test — the exact class that shipped to main
  #      before this hook existed).
  #   2. Cold-boot gate — catches what the suite structurally cannot: a cold boot
  #      from zero, per-profile resolution, the real backend, real health.
  info "Full test lane (scripts/test) ..."
  if ! scripts/test; then
    fail "Full test lane RED — aborting promote. origin/main is NOT advanced \
(req-dev-validation-promote-hook-2). Fix the failing test(s) and re-run."
  fi
  info "Full test lane GREEN. Cold-boot gate (scripts/gate) ..."
  if ! scripts/gate; then
    fail "Cold-boot gate RED — aborting promote. origin/main is NOT advanced \
(req-dev-validation-promote-hook-2). Fix the failing step and re-run."
  fi
  info "Validation GREEN (full lane + cold-boot gate) — proceeding to push."
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
