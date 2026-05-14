#!/usr/bin/env bash
# scripts/spawn-session.sh — interactive multi-session dev environment provisioning.
#
# This script is the canonical implementation of the onboarding procedure.
# Each numbered step block below carries a spec anchor pointing at the
# requirement that defines its behavior. To understand WHY a step does what
# it does, read the linked requirement — not a parallel description elsewhere
# (those would just drift).
#
# Top-level requirements implemented here:
#   req-dev-multisession-spawn-script      — overall flow, registry validation, failure trap
#   req-dev-multisession-admin-bootstrap   — Django admin user creation + .dev-credentials
#
# Top-level requirements depended on:
#   req-dev-multisession-compose-parameterized  — docker-compose.yml env-var contract
#   req-dev-multisession-env-cascade            — scripts/dc cascades .env + .env.local
#   req-dev-multisession-port-registry          — registry table in the spec is authoritative
#   req-dev-multisession-browser-disambiguation — TAP_SESSION_LABEL + *.localhost URL
#
# All four are documented in: specs/spec-dev-multisession.md
# Public-facing entry point: docs/doc-dev-multisession-onboarding.md

set -euo pipefail

# Resolve the repo root from this script's own location, not $PWD, so the
# script can be invoked from anywhere (e.g. via a PATH symlink or alias).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

bold()  { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
info()  { printf "    %s\n" "$1"; }
warn()  { printf "\033[33m    %s\033[0m\n" "$1"; }
fail()  { printf "\033[31m    ERROR: %s\033[0m\n" "$1" >&2; exit 1; }
prompt(){ printf "    \033[36m%s\033[0m " "$1"; }

# Trap to give the user a one-line recovery command if anything goes sideways.
SESSION_NAME=""
on_failure() {
  local rc=$?
  if [[ $rc -ne 0 ]] && [[ -n "$SESSION_NAME" ]]; then
    echo
    warn "spawn failed (exit $rc). To nuke the partial state and start clean:"
    warn "  scripts/despawn-session.sh $SESSION_NAME --yes"
    warn ""
    warn "Add --purge-image if you suspect a poisoned image cache (uv install"
    warn "errors, stale dependency state, etc.) — that forces a no-cache rebuild"
    warn "on the next spawn."
  fi
}
trap on_failure EXIT

# ---------------------------------------------------------------------------
# Parse args
#
# Positional <name> skips the interactive name prompt in step 1.
# Optional <launch> is `cli`, `codex`, or `vscode` — when set, after a
# successful spawn the script auto-launches the matching editor against the
# new worktree.
# ---------------------------------------------------------------------------
LAUNCH_TARGET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      cat <<EOF
Usage: $0 [<name>] [cli|codex|vscode]

Spawn a new isolated TAP dev session. <name> is the session label
(lowercase, e.g. cli, vscode, fix-arrangements). If omitted, the script
prompts for it interactively.

Optional second arg auto-attaches an editor after spawn completes:
  cli     — cd into the worktree and exec \`claude\` (this script's process
            becomes the claude REPL)
  codex   — open the worktree in the Codex desktop app via
            \`codex app <worktree>\` (non-blocking — Codex launches separately)
  vscode  — open the worktree in VS Code via \`open -a "Visual Studio Code"\`
            (non-blocking — VS Code launches as a separate app)

Examples:
  $0                         # interactive, no auto-launch
  $0 fix-arrangements        # named, no auto-launch
  $0 fix-arrangements cli    # named + attach Claude in the worktree
  $0 fix-arrangements codex  # named + attach Codex in the worktree
  $0 fix-arrangements vscode

Spec: req-dev-multisession-spawn-script in specs/spec-dev-multisession.md
EOF
      exit 0
      ;;
    -*) fail "Unknown flag: $1" ;;
    cli|codex|vscode)
      [[ -z "$LAUNCH_TARGET" ]] || fail "Multiple launch targets given: '$LAUNCH_TARGET' and '$1'."
      LAUNCH_TARGET="$1"
      shift
      ;;
    *)
      [[ -z "$SESSION_NAME" ]] || fail "Multiple session names given: '$SESSION_NAME' and '$1'."
      SESSION_NAME="$1"
      shift
      ;;
  esac
done

cd "$REPO"

# ============================================================================
# Step 0: macOS Keychain admin password (one-time per Mac)
#
# Spec: req-dev-multisession-admin-bootstrap (Password resolution order, source #3).
#       Keychain is the recommended home for the shared default admin password
#       across sessions. Random-per-session is the fallback when this is unset.
#       Service name `tap-dev-default` and account `admin` are the contract.
# ============================================================================
bold "Step 0: macOS Keychain admin password"

if [[ "$(uname)" != "Darwin" ]]; then
  info "Not macOS — Keychain step skipped. Falling back to env var or random per session."
elif security find-generic-password -s tap-dev-default -a admin >/dev/null 2>&1; then
  info "Already set in Keychain (tap-dev-default / admin). Skipping."
else
  info "No 'tap-dev-default' Keychain entry found."
  info "Stash a stable admin password? Skipping is fine — a random one will be generated"
  info "for this session and saved to the worktree's .dev-credentials file."
  prompt "Set Keychain password now? [Y/n]"
  read -r ans
  ans="${ans:-Y}"
  if [[ "$ans" =~ ^[Yy] ]]; then
    info "macOS will prompt for the password (not echoed, not in shell history)."
    security add-generic-password -s tap-dev-default -a admin -w
    info "Saved."
  else
    info "Skipping — random password will be generated per session."
  fi
fi

# ============================================================================
# Step 1: Pick a session name and allocate a port band
#
# Spec: req-dev-multisession-port-registry — sessions are allocated on demand.
#       The per-machine registry at ~/tap-sessions/.registry is canonical for
#       active sessions. Despawn removes the row; spawn appends one. Bands are
#       ephemeral by default (despawn frees them).
#       req-dev-multisession-spawn-script — name validation, primary-name
#       reservation, stale-docker pre-check.
# ============================================================================
bold "Step 1: Pick a session name and allocate a port band"

REGISTRY="$HOME/tap-sessions/.registry"
mkdir -p "$HOME/tap-sessions"

if [[ ! -f "$REGISTRY" ]]; then
  cat > "$REGISTRY" <<'EOF'
# TAP multi-session dev environment registry (per-machine, line-delimited).
# Each non-comment row records a live session: name web db branch spawned
# Spawn appends; despawn removes. See specs/spec-dev-multisession.md.
EOF
fi

# Display current allocations only when we'll actually prompt — if the name
# came in via CLI arg, the listing is noise.
if [[ -z "$SESSION_NAME" ]]; then
  ACTIVE_COUNT="$(grep -cvE '^(#|$)' "$REGISTRY" || true)"
  if [[ "$ACTIVE_COUNT" -gt 0 ]]; then
    info "Current sessions ($ACTIVE_COUNT):"
    printf '      %-20s %-5s %-5s %s\n' "name" "web" "db" "spawned"
    grep -vE '^(#|$)' "$REGISTRY" | while read -r r_name r_web r_db r_branch r_spawned; do
      printf '      %-20s %-5s %-5s %s\n' "$r_name" "$r_web" "$r_db" "$r_spawned"
    done
  else
    info "No sessions currently spawned."
  fi
  echo

  prompt "Session name:"
  read -r SESSION_NAME
else
  info "Session name (from CLI): $SESSION_NAME"
fi
[[ -n "$SESSION_NAME" ]] || fail "Session name is required."
[[ "$SESSION_NAME" =~ ^[a-z][a-z0-9_-]*$ ]] || fail "Session name must be lowercase, start with a letter, and contain only letters/digits/_/-."
[[ "$SESSION_NAME" != "default" ]] || fail "'default' is reserved for the primary stack. Pick another name."

# Reject collision with an existing registry entry.
if grep -qE "^${SESSION_NAME} " "$REGISTRY"; then
  fail "Session '$SESSION_NAME' already exists in $REGISTRY. Despawn it first, or pick a different name."
fi

# Allocate the smallest free band starting at 1 (web=8010, db=5442).
# Band 0 (8000/5432) is reserved for the primary stack.
# Cap at 50 so we fail loudly instead of allocating into someone else's well-
# known port range.
#
# A band is "free" when neither the registry NOR actual listening sockets
# claim it. The actual-port check catches the drift case where a session was
# spawned by an earlier script version that never appended its registry row,
# or where the host has something else listening on the band's ports.
port_in_use() {
  lsof -iTCP:"$1" -sTCP:LISTEN -P -n 2>/dev/null | grep -q LISTEN
}
WEB_PORT=""
POSTGRES_PORT=""
for ((band=1; band<=50; band++)); do
  candidate_web=$((8000 + 10 * band))
  candidate_db=$((5432 + 10 * band))
  if grep -qE "^[^ #]+ ${candidate_web} ${candidate_db} " "$REGISTRY"; then
    continue   # band claimed in registry
  fi
  if port_in_use "$candidate_web" || port_in_use "$candidate_db"; then
    continue   # band claimed by something actually listening
  fi
  WEB_PORT=$candidate_web
  POSTGRES_PORT=$candidate_db
  break
done
[[ -n "$WEB_PORT" ]] || fail "All session bands (1..50) are in use. Despawn unused sessions or raise the cap."

info "Allocated: tap_$SESSION_NAME / web=$WEB_PORT / db=$POSTGRES_PORT"

WORKTREE="$HOME/tap-sessions/$SESSION_NAME"
[[ ! -e "$WORKTREE" ]] || fail "Worktree already exists at $WORKTREE. Despawn first."

# Catch stale Docker state from a previous failed spawn whose `dc down -v`
# didn't actually target the right project (typically because .env.local was
# missing at cleanup time). A leftover volume survives `git worktree remove`
# and would silently inherit migration state into the new session.
STALE_VOLUME="tap_${SESSION_NAME}_postgres_data"
if docker volume inspect "$STALE_VOLUME" >/dev/null 2>&1; then
  fail "Stale Docker volume '$STALE_VOLUME' exists from a previous session. Remove it first:
    docker volume rm $STALE_VOLUME"
fi
STALE_CONTAINERS="$(docker ps -a --filter "label=com.docker.compose.project=tap_${SESSION_NAME}" --format '{{.Names}}' 2>/dev/null || true)"
if [[ -n "$STALE_CONTAINERS" ]]; then
  fail "Stale Docker containers exist for project 'tap_${SESSION_NAME}': $STALE_CONTAINERS
    Remove them first: docker compose -p tap_${SESSION_NAME} down -v --remove-orphans"
fi

# ============================================================================
# Step 1.5: Refresh local main from origin
#
# Spec: req-dev-multisession-push-workflow (step 4 + spawn-side guard).
#       `git worktree add -b session/<name>` below branches from local `main`'s
#       HEAD. If sibling sessions have pushed work to origin/main since this
#       worktree's main ref last advanced, branching now would silently start
#       the new session from stale code. Refresh first so the new session is
#       always current.
#
#       The pull must run INSIDE the main worktree (not via `$REPO`, which is
#       wherever the script was invoked from — possibly a session worktree).
#       `git -C <main-worktree> pull` runs as if invoked there, so it advances
#       `main` rather than whatever branch the invoking worktree has checked out.
#
#       --ff-only refuses non-fast-forward updates — if it fails, local main
#       has either uncommitted changes (a discipline violation; never edit on
#       main) or has diverged from origin (also a discipline violation). Surface
#       the error rather than papering over it.
# ============================================================================
MAIN_WORKTREE="$HOME/tap-sessions/main"
bold "Step 1.5: Refreshing local main from origin"
if [[ ! -d "$MAIN_WORKTREE/.git" && ! -f "$MAIN_WORKTREE/.git" ]]; then
  warn "Main worktree not found at $MAIN_WORKTREE — skipping refresh."
  warn "If this is a non-standard checkout layout, advance local main manually before spawning."
else
  if ! git -C "$MAIN_WORKTREE" pull --ff-only origin main; then
    fail "Local main is not fast-forwardable from origin/main.
    Resolve manually in $MAIN_WORKTREE before spawning a new session.
    Common causes: uncommitted changes in main (never edit there), or a divergent local main."
  fi
  info "Local main is current with origin/main."
fi

# ============================================================================
# Step 2: Create the worktree
#
# Spec: req-dev-multisession-spawn-script — worktrees live OUTSIDE the repo at
#       ~/tap-sessions/<name> on a new branch session/<name>. Working tree
#       isolation is goal #2 of spec-dev-multisession.md.
#
#       The explicit `main` start-point is load-bearing: without it,
#       `git worktree add -b <new>` uses the INVOKING worktree's HEAD, not
#       `main`. If spawn-session.sh is invoked from a session worktree (e.g.
#       an agent inside vscode-prime spawning a sub-session), the new session
#       would silently inherit that session's branch-local commits. Naming
#       `main` makes the start point unambiguous and ties the new session to
#       the local `main` ref that Step 1.5 just refreshed from origin.
# ============================================================================
bold "Step 2: Creating worktree at $WORKTREE"
git worktree add "$WORKTREE" -b "session/$SESSION_NAME" main
cd "$WORKTREE"
info "Created. Now on branch session/$SESSION_NAME (branched from main)."

# ============================================================================
# Step 3: Write .env.local
#
# Spec: req-dev-multisession-compose-parameterized — docker-compose.yml reads
#       COMPOSE_PROJECT_NAME, WEB_PORT, POSTGRES_PORT, TAP_GRID_ID from env.
#       req-dev-multisession-env-cascade — scripts/dc layers .env.local on top
#       of the checked-in .env so this per-worktree override file is the
#       standard way to differentiate sessions.
#       req-dev-multisession-browser-disambiguation — TAP_SESSION_LABEL drives
#       the page-title prefix and nav badge so browser tabs are distinguishable.
#       TAP_GRID_ID is freshly generated per session because each isolated
#       stack is logically a separate TAP installation.
# ============================================================================
bold "Step 3: Writing .env.local"
# uuid.uuid7 entered the stdlib in Python 3.14. The host's `python3` may be older
# (the Docker container is fine — that's 3.14+ — but we need the GRID_ID set
# before the container starts). Fall back to an inline RFC 9562 implementation
# so the script works on any Python 3.x host.
TAP_GRID_ID="$(python3 - <<'PY'
import os, time, uuid
try:
    print(uuid.uuid7())
except AttributeError:
    ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0xFFF
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    val = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    print(uuid.UUID(int=val))
PY
)"
cat > .env.local <<EOF
COMPOSE_PROJECT_NAME=tap_$SESSION_NAME
WEB_PORT=$WEB_PORT
POSTGRES_PORT=$POSTGRES_PORT
TAP_GRID_ID=$TAP_GRID_ID
TAP_SESSION_LABEL=$SESSION_NAME
EOF
info "Wrote $WORKTREE/.env.local (gitignored)."

# ============================================================================
# Step 4: Build & start the Docker stack
#
# Spec: req-dev-multisession-env-cascade — must invoke compose via scripts/dc
#       (not bare docker compose) so .env.local is layered correctly and the
#       per-session port band actually takes effect.
# ============================================================================
bold "Step 4: Building and starting Docker stack"
info "First build pulls postgres:16-alpine and compiles the web image — typically 2-5 minutes."
scripts/dc up -d --build

# ============================================================================
# Step 5: Wait for the entrypoint to finish initial setup
#
# `dc up -d` returns the moment PID 1 (entrypoint.sh) starts, but the entrypoint
# is still running `uv sync` (slow on first run — populates the named-volume
# uv cache and the bind-mounted .venv) and then `migrate`. Running another
# `dc exec uv run ...` here would race those processes and one of them gets
# SIGKILL'd by the lock contention (this caused exit 137 errors all day).
#
# Instead, poll for runserver readiness — once Django responds on port 8000
# inside the container, we know uv sync + migrate are both done. Migrate is
# already applied by the entrypoint, so we don't re-run it here.
# ============================================================================
bold "Step 5: Waiting for entrypoint (uv sync + migrate + runserver)"
info "First-time uv sync downloads ~50MB of wheels — typically 1-3 minutes."
WAIT_TIMEOUT=300   # 5 minutes
WAIT_START=$(date +%s)
while true; do
  # Use Python's urllib (always present — the base image is python:3.14-slim,
  # which doesn't ship curl). The check passes if anything HTTP responds at
  # all — the goal is "is runserver listening?", not "does the page load
  # cleanly?". 500s are fine here; we just need to know uv sync + migrate
  # finished and the dev server bound the port.
  if scripts/dc exec -T web python -c "
import urllib.request, sys
try:
    urllib.request.urlopen('http://localhost:8000/admin/', timeout=2)
    sys.exit(0)
except urllib.error.HTTPError:
    sys.exit(0)  # 4xx/5xx from a real server is still 'listening'
except Exception:
    sys.exit(1)  # connection refused / not listening yet
" 2>/dev/null; then
    info "Web is responding."
    break
  fi
  elapsed=$(($(date +%s) - WAIT_START))
  if [[ $elapsed -gt $WAIT_TIMEOUT ]]; then
    fail "Web did not become ready in ${WAIT_TIMEOUT}s. Check 'scripts/dc logs web' in $WORKTREE."
  fi
  printf "    waiting... %ds\r" "$elapsed"
  sleep 3
done
echo

# ============================================================================
# Step 6: Seed plugin data
#
# Each isolated stack is a separate TAP installation; spawn seeds it so the
# attached Claude session has data to work with from the first request.
# Plugin order is INSTALLED_APPS order via apps.get_app_configs() — see
# req-plugin-load-v0-ready-readonly.
# ============================================================================
bold "Step 6: Seeding plugin data"
scripts/dc exec web uv run python manage.py import_plugin_grift --all

# ============================================================================
# Step 7: Create the Django admin superuser
#
# Spec: req-dev-multisession-admin-bootstrap — full design lives there.
#       Username/email are fixed (admin / admin@<session>.tap.localhost).
#       Password resolution order: TAP_DEV_ADMIN_PASSWORD → macOS Keychain
#       (tap-dev-default / admin) → random secrets.token_urlsafe(18).
#       Whatever password is resolved is written to .dev-credentials in the
#       worktree (gitignored) — that file is the runtime interface for the
#       attached Claude or developer to read on demand.
#       The createsuperuser invocation uses --noinput driven by env vars,
#       Django's built-in unattended path.
# ============================================================================
bold "Step 7: Creating Django admin superuser"

# Resolution order matches req-dev-multisession-admin-bootstrap.
# (--admin-password CLI flag isn't supported in v1; add later if needed.)
ADMIN_PASSWORD=""
if [[ -n "${TAP_DEV_ADMIN_PASSWORD:-}" ]]; then
  ADMIN_PASSWORD="$TAP_DEV_ADMIN_PASSWORD"
  info "Password source: \$TAP_DEV_ADMIN_PASSWORD"
elif [[ "$(uname)" == "Darwin" ]] && ADMIN_PASSWORD="$(security find-generic-password -s tap-dev-default -a admin -w 2>/dev/null)" && [[ -n "$ADMIN_PASSWORD" ]]; then
  info "Password source: macOS Keychain (tap-dev-default)"
else
  ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  info "Password source: random (fresh per session)"
fi

ADMIN_EMAIL="admin@$SESSION_NAME.tap.localhost"

cat > .dev-credentials <<EOF
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=$ADMIN_PASSWORD
DJANGO_SUPERUSER_EMAIL=$ADMIN_EMAIL
SESSION_NAME=$SESSION_NAME
GENERATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

scripts/dc exec \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_PASSWORD="$ADMIN_PASSWORD" \
  -e DJANGO_SUPERUSER_EMAIL="$ADMIN_EMAIL" \
  web uv run python manage.py createsuperuser --noinput

info "Superuser created. Credentials saved to $WORKTREE/.dev-credentials (gitignored)."

# ============================================================================
# Final: record the session in the registry
#
# Spec: req-dev-multisession-port-registry — registry is the canonical record
#       of live sessions. Append-on-success means partial spawns leave no
#       row; the band stays "free" for the next attempt to retry the same
#       name. (Trade-off: two simultaneous spawns could race on band
#       allocation. Genuinely rare; not worth a lock for v1.)
# ============================================================================
SPAWNED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "$SESSION_NAME $WEB_PORT $POSTGRES_PORT session/$SESSION_NAME $SPAWNED_AT" >> "$REGISTRY"

# ============================================================================
# Done — print URLs, credentials, and attach instructions
#
# Spec: req-dev-multisession-browser-disambiguation — the labeled URL uses the
#       *.localhost subdomain pattern (RFC 6761 native browser resolution to
#       127.0.0.1) so the address bar tells the developer which session they're
#       in. The direct localhost:<port> URL is the unambiguous fallback.
# ============================================================================
trap - EXIT  # Disarm failure trap on success.

echo
bold "Done — session '$SESSION_NAME' is ready."
echo
info "URLs"
info "  Labeled:   http://$SESSION_NAME.tap.localhost:$WEB_PORT/"
info "  Direct:    http://localhost:$WEB_PORT/"
info "  Admin URL: http://$SESSION_NAME.tap.localhost:$WEB_PORT/admin/"
echo
info "Admin credentials"
info "  Username:  admin"
info "  Password:  (saved to .dev-credentials — never printed to stdout)"
info "  File:      $WORKTREE/.dev-credentials"
info "  Read with: cat '$WORKTREE/.dev-credentials'"
echo
info "Attach Claude Code"
info "  CLI:       cd $WORKTREE && claude"
info "  Codex:     codex app '$WORKTREE'"
info "  VSCode:    open '$WORKTREE' in a new VSCode window"
echo
info "Next: from inside the attached Claude session, run the smoke tests in"
info "      specs/spec-dev-multisession-smoketest.md"
echo

# ============================================================================
# Auto-launch editor (optional second positional arg)
#
# `cli` — exec claude in the worktree. This script's process becomes the
#         claude REPL; when claude exits the user is back in their original
#         shell.
# `codex` — open the worktree in the Codex desktop app. Non-blocking, same
#           shape as `vscode`, but routed through Codex's workspace-aware CLI.
# `vscode` — open the worktree as a folder in VS Code. Non-blocking; the
#            script exits normally after the open call returns.
# ============================================================================
case "$LAUNCH_TARGET" in
  cli)
    bold "Launching Claude Code in $WORKTREE..."
    cd "$WORKTREE"
    exec claude
    ;;
  codex)
    bold "Opening $WORKTREE in Codex..."
    codex app "$WORKTREE"
    ;;
  vscode)
    bold "Opening $WORKTREE in VS Code..."
    open -a "Visual Studio Code" "$WORKTREE"
    ;;
esac
