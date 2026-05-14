#!/usr/bin/env bash
# scripts/promote-all-sessions.sh — promote every session in the registry to
# origin/main, in order.
#
# Implements req-dev-multisession-promote-all-script
# (specs/spec-dev-multisession.md). Reads the per-machine session registry
# at ~/tap-sessions/.registry and runs scripts/promote-to-main.sh in each
# session worktree sequentially. The per-session script handles the full
# fetch / pre-push merge / atomic push / main-sync sequence.
#
# Sequential is intentional: each promote pushes the session tip to
# origin/main, then the next session's pre-push merge picks up that change
# and folds it into its branch before its own push.
#
# Usage:
#   scripts/promote-all-sessions.sh             # promote every session, stop on first failure
#   scripts/promote-all-sessions.sh --dry-run   # report what would happen; no writes
#   scripts/promote-all-sessions.sh --keep-going
#       # continue past per-session failures instead of stopping on first
#

set -uo pipefail

REGISTRY="$HOME/tap-sessions/.registry"

bold() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
info() { printf "    %s\n" "$1"; }
warn() { printf "\033[33m    %s\033[0m\n" "$1"; }
fail() { printf "\033[31m    ERROR: %s\033[0m\n" "$1" >&2; exit 1; }

DRY_RUN=0
KEEP_GOING=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--dry-run)    DRY_RUN=1; shift ;;
    -k|--keep-going) KEEP_GOING=1; shift ;;
    -h|--help)
      sed -n '/^# Usage:/,/^# *$/p' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    -*) fail "Unknown flag: $1" ;;
    *)  fail "Unexpected arg: $1" ;;
  esac
done

[[ -f "$REGISTRY" ]] || fail "No registry at $REGISTRY — no sessions to promote."

# bash 3.2 compatible (macOS default): no mapfile/readarray.
SESSIONS=()
while IFS= read -r name; do
  [[ -n "$name" ]] && SESSIONS+=("$name")
done < <(grep -vE '^(#|$)' "$REGISTRY" | awk '{print $1}')

if [[ ${#SESSIONS[@]} -eq 0 ]]; then
  info "No sessions registered. Nothing to do."
  exit 0
fi

bold "Promoting ${#SESSIONS[@]} session(s) to origin/main"
for s in "${SESSIONS[@]}"; do
  info "  - $s"
done

OK=()
FAILED=()
SKIPPED=()

for s in "${SESSIONS[@]}"; do
  WORKTREE="$HOME/tap-sessions/$s"
  bold "[$s] $WORKTREE"

  if [[ ! -d "$WORKTREE" ]]; then
    warn "Worktree missing; skipping. Registry row may be stale — despawn to clean up."
    SKIPPED+=("$s")
    continue
  fi
  if [[ ! -x "$WORKTREE/scripts/promote-to-main.sh" ]]; then
    warn "promote-to-main.sh missing in this worktree; skipping."
    warn "This session pre-dates the promote scripts — consolidate it manually per spec."
    SKIPPED+=("$s")
    continue
  fi

  # Forward --dry-run through. The per-session script's own --dry-run is the
  # ground truth: orchestrator dry-run is just "what would each session do."
  ARGS=()
  [[ "$DRY_RUN" -eq 1 ]] && ARGS+=("--dry-run")

  # Subshell isolates the cd; we return to the original CWD between sessions.
  if ( cd "$WORKTREE" && scripts/promote-to-main.sh "${ARGS[@]}" ); then
    OK+=("$s")
  else
    FAILED+=("$s")
    if [[ "$KEEP_GOING" -eq 0 ]]; then
      echo
      fail "Promote failed for '$s'. Use --keep-going to continue past failures."
    fi
  fi
done

echo
bold "Summary"
info "  ok:      ${#OK[@]}  ${OK[*]:-}"
info "  failed:  ${#FAILED[@]}  ${FAILED[*]:-}"
info "  skipped: ${#SKIPPED[@]}  ${SKIPPED[*]:-}"

[[ ${#FAILED[@]} -eq 0 ]] || exit 1
