#!/usr/bin/env bash
# scripts/despawn-session.sh — fully tear down a multi-session dev environment.
#
# Removes everything: docker containers + volumes + networks, the worktree
# (with all uncommitted files), the session/<name> branch, and the registry
# row. Best-effort: individual step failures log a warning and we continue —
# the goal is "leave nothing behind."
#
# Spec: req-dev-multisession-teardown-script in spec-dev-multisession-teardown.md
#
# Usage:
#   scripts/despawn-session.sh                  # interactive — pick from registry
#   scripts/despawn-session.sh <name>           # despawn the named session (with confirm)
#   scripts/despawn-session.sh <name> --yes     # skip confirm prompt
#   scripts/despawn-session.sh <name> --purge-image
#                                               # also force-remove the per-project
#                                               # web image so the next spawn rebuilds
#                                               # without cache (use when uv cache
#                                               # or wheel state is poisoned).

# NOT set -e — we want best-effort cleanup, not abort-on-first-failure.
set -uo pipefail

# Resolve repo root from this script's own location, not $PWD, so the script
# can be invoked from anywhere (e.g. via a PATH symlink or alias).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
REGISTRY="$HOME/tap-sessions/.registry"

bold()   { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
info()   { printf "    %s\n" "$1"; }
warn()   { printf "\033[33m    %s\033[0m\n" "$1"; }
err()    { printf "\033[31m    %s\033[0m\n" "$1" >&2; }
prompt() { printf "    \033[36m%s\033[0m " "$1"; }

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
SESSION_NAME=""
ASSUME_YES=0
PURGE_IMAGE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes)         ASSUME_YES=1; shift ;;
    --purge-image)    PURGE_IMAGE=1; shift ;;
    -h|--help)
      sed -n '/^# Usage:/,/^# *$/p' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    -*)               err "Unknown flag: $1"; exit 1 ;;
    *)                SESSION_NAME="$1"; shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Pick session name interactively if not provided
# ---------------------------------------------------------------------------
if [[ -z "$SESSION_NAME" ]]; then
  if [[ -f "$REGISTRY" ]] && grep -qvE '^(#|$)' "$REGISTRY"; then
    bold "Current sessions"
    printf '      %-20s %-5s %-5s %s\n' "name" "web" "db" "spawned"
    grep -vE '^(#|$)' "$REGISTRY" | while read -r r_name r_web r_db r_branch r_spawned; do
      printf '      %-20s %-5s %-5s %s\n' "$r_name" "$r_web" "$r_db" "$r_spawned"
    done
    echo
  else
    info "No sessions in registry. Proceed by name to clean up half-spawned state."
  fi
  prompt "Session name to despawn:"
  read -r SESSION_NAME
fi

[[ -n "$SESSION_NAME" ]] || { err "Session name required"; exit 1; }

WORKTREE="$HOME/tap-sessions/$SESSION_NAME"
PROJECT="tap_${SESSION_NAME}"

# ---------------------------------------------------------------------------
# Show the plan, get confirmation
# ---------------------------------------------------------------------------
bold "Despawn plan for '$SESSION_NAME'"
info "  Docker project:        $PROJECT"
info "  Worktree:              $WORKTREE  (entire directory + all uncommitted files)"
info "  Branch:                session/$SESSION_NAME"
info "  Registry row:          $REGISTRY"
[[ "$PURGE_IMAGE" -eq 1 ]] && info "  Per-project image:     ${PROJECT}-web (force rebuild on next spawn)"
echo

if [[ "$ASSUME_YES" -eq 0 ]]; then
  prompt "Permanently delete all of the above? [y/N]"
  read -r ans
  [[ "$ans" =~ ^[Yy] ]] || { info "Aborted."; exit 0; }
fi

# ---------------------------------------------------------------------------
# 1. Stop docker stack (preferring scripts/dc inside the worktree so .env.local
#    is honored; fall back to the project name if dc is unavailable).
# ---------------------------------------------------------------------------
bold "Stopping docker stack"
if [[ -d "$WORKTREE" && -x "$WORKTREE/scripts/dc" ]]; then
  ( cd "$WORKTREE" && scripts/dc down -v --remove-orphans 2>&1 ) || warn "scripts/dc down returned non-zero (may already be down)"
else
  docker compose -p "$PROJECT" down -v --remove-orphans 2>&1 || warn "docker compose down returned non-zero (may already be down)"
fi

# ---------------------------------------------------------------------------
# 2. Belt-and-suspenders volume + network cleanup. If step 1 didn't have a
#    valid .env.local to identify the project, named volumes/networks may
#    still exist.
# ---------------------------------------------------------------------------
bold "Removing residual docker volumes and networks"
volumes_to_rm="$(docker volume ls --filter "name=${PROJECT}_" --format '{{.Name}}')"
if [[ -n "$volumes_to_rm" ]]; then
  echo "$volumes_to_rm" | while read -r v; do
    info "  volume: $v"
    docker volume rm "$v" >/dev/null 2>&1 || warn "    (failed)"
  done
else
  info "  no volumes"
fi
networks_to_rm="$(docker network ls --filter "name=${PROJECT}_" --format '{{.Name}}')"
if [[ -n "$networks_to_rm" ]]; then
  echo "$networks_to_rm" | while read -r n; do
    info "  network: $n"
    docker network rm "$n" >/dev/null 2>&1 || warn "    (failed)"
  done
else
  info "  no networks"
fi

# ---------------------------------------------------------------------------
# 3. Worktree + branch. --force ignores uncommitted files (the
#    user explicitly asked for nuke). If the directory survives somehow
#    (e.g. removed outside git's awareness), rm -rf it.
# ---------------------------------------------------------------------------
bold "Removing worktree and branch"
git -C "$REPO" worktree remove --force "$WORKTREE" 2>/dev/null && info "  worktree removed via git" || info "  worktree not in git's list"
git -C "$REPO" worktree prune 2>/dev/null
if [[ -e "$WORKTREE" ]]; then
  warn "  worktree directory still on disk; removing forcibly"
  rm -rf "$WORKTREE" && info "  $WORKTREE removed"
fi
git -C "$REPO" branch -D "session/$SESSION_NAME" 2>/dev/null && info "  branch deleted" || info "  branch not present"

# ---------------------------------------------------------------------------
# 5. Registry row.
# ---------------------------------------------------------------------------
bold "Removing registry row"
if [[ -f "$REGISTRY" ]]; then
  if grep -qE "^${SESSION_NAME} " "$REGISTRY"; then
    sed -i.bak "/^${SESSION_NAME} /d" "$REGISTRY" && rm -f "$REGISTRY.bak"
    info "  row for '$SESSION_NAME' removed"
  else
    info "  no row for '$SESSION_NAME' (was probably never recorded)"
  fi
else
  info "  no registry file"
fi

# ---------------------------------------------------------------------------
# 6. Optional: purge the per-project web image so the next spawn rebuilds
#    without cache. Use this when uv's cache or wheel state is poisoned —
#    despawn alone won't fix that because the cache is baked into the image.
# ---------------------------------------------------------------------------
if [[ "$PURGE_IMAGE" -eq 1 ]]; then
  bold "Purging per-project image"
  images_to_rm="$(docker images --filter "reference=${PROJECT}-web" --format '{{.Repository}}:{{.Tag}}')"
  if [[ -n "$images_to_rm" ]]; then
    echo "$images_to_rm" | while read -r img; do
      info "  image: $img"
      docker rmi "$img" >/dev/null 2>&1 || warn "    (failed — image may still be in use)"
    done
  else
    info "  no per-project image found"
  fi
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
bold "Despawn complete for '$SESSION_NAME'"
echo
info "Verification (everything below should be empty / 'no output'):"
info "  docker compose -p $PROJECT ps -a"
info "  docker volume ls | grep ${PROJECT}_"
info "  ls $WORKTREE 2>&1 | head"
info "  git -C $REPO worktree list | grep tap-sessions/$SESSION_NAME"
info "  grep '^$SESSION_NAME ' $REGISTRY"
echo
