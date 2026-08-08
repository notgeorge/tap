#!/usr/bin/env bash
# scripts/stand-up.sh — first boot of a freshly cloned TAP repo as a local instance.
#
# The adopter path: someone cloned this repository onto their own machine (macOS or
# a Linux desktop) and wants a running, logged-in-able instance of TAP on the default
# ports. One command, no worktrees, no port bands, no registry:
#
#   scripts/stand-up.sh [<boot-profile>]
#
# This is deliberately NOT scripts/spawn-session.sh. Spawn provisions an Nth
# concurrent dev session for someone already running a primary stack: git worktree,
# port-band allocation, session registry, browser disambiguation. Stand-up
# provisions the FIRST and only stack in a fresh clone — the checked-in .env
# defaults (project `tap`, web 8000, postgres 5432) are already correct, so its job
# reduces to: check the host, mint an install identity, build+start, boot, hand
# over credentials. The two scripts share the standup-watch idiom (TAP-ABORT
# fast-fail + dead-container check + readiness poll, req-boot-abort-signal); the
# blocks are small and carry provenance comments back to spawn where they
# originated.
#
# The `stand-up` skill (tap_boot/skills/stand-up/) is this script's conversational
# driver for AI-assisted onboarding — it prepares the host and invokes this script;
# it re-implements nothing (the bootstrap_dev_passkey discipline: one place to be
# correct, one place an AI operator can drive).
#
# What this script deliberately does not do:
#   * FIPS choice — the image builds with TAP_FIPS=1 (the default; the published
#     posture). `TAP_FIPS=0 scripts/stand-up.sh` is the explicit escape hatch and
#     rides the existing compose ARG; nothing here needs to know.
#   * Passkey enrollment — first login is username/password (boot's auth phase
#     creates the admin; the login page links the password form). Enroll a passkey
#     afterwards from the authenticated session.
#   * Secrets — a fresh clone has no tap_secrets store and needs none to boot the
#     default profile. Credentialed collectors come later (see each plugin's README).

set -euo pipefail

bold()  { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
info()  { printf "    %s\n" "$1"; }
warn()  { printf "\033[33m    %s\033[0m\n" "$1"; }
fail()  { printf "\033[31m    ERROR: %s\033[0m\n" "$1" >&2; exit 1; }

# Resolve the repo root from this script's own location, not $PWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO"

# Wall-clock timeout without coreutils `timeout` (absent on stock macOS).
# Provenance: scripts/spawn-session.sh `with_timeout`.
with_timeout() {
  local secs="$1"; shift
  "$@" & local cmd_pid=$!
  ( sleep "$secs"; kill -9 "$cmd_pid" 2>/dev/null ) & local killer_pid=$!
  local rc=0; wait "$cmd_pid" 2>/dev/null || rc=$?
  kill "$killer_pid" 2>/dev/null; wait "$killer_pid" 2>/dev/null || true
  [[ $rc -eq 137 ]] && return 124
  return $rc
}

BOOT_PROFILE="core"
case "${1:-}" in
  -h|--help)
    sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") ;;
  -*) fail "Unknown flag: $1 (usage: scripts/stand-up.sh [<boot-profile>])" ;;
  *)  BOOT_PROFILE="$1" ;;
esac
[[ -f "boot/${BOOT_PROFILE}.boot.json" ]] || fail "No such boot profile: boot/${BOOT_PROFILE}.boot.json
    Available: $(cd boot && ls *.boot.json | sed 's/\.boot\.json//' | tr '\n' ' ')"

bold "Standing up TAP from this clone (profile: $BOOT_PROFILE)"

# ============================================================================
# Step 1: Refuse to run twice / refuse to run where an instance already lives
#
# .env.local is the marker that SOME provisioning already happened here — either
# a prior stand-up (it writes one below) or a spawn-session worktree (which
# writes one with a session label). Re-running against live state must not
# re-mint the install identity or re-boot over data.
# ============================================================================
# Effective config value: .env.local (operator overrides, e.g. custom ports)
# wins over the checked-in .env — the same layering scripts/dc applies.
env_get() {
  local v=""
  [[ -f .env.local ]] && v="$(grep "^$1=" .env.local 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  [[ -z "$v" ]] && v="$(grep "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  printf '%s' "$v"
}

if [[ -f .env.local ]]; then
  if grep -q "^TAP_SESSION_LABEL=..*" .env.local 2>/dev/null; then
    fail "This is a multi-session dev worktree ($(grep '^TAP_SESSION_LABEL=' .env.local)) — it was provisioned by scripts/spawn-session.sh, not stand-up. Use scripts/dc to manage it."
  fi
  if grep -q "^TAP_GRID_ID=..*" .env.local 2>/dev/null; then
    # A minted install identity is the marker that stand-up (or an operator)
    # completed provisioning — re-running must not re-mint it or re-boot over data.
    info ".env.local already carries a TAP_GRID_ID — this clone has been stood up before."
    info "To start it:      scripts/dc up -d"
    info "To reset FULLY (destroys the database): scripts/dc down -v && rm .env.local && scripts/stand-up.sh"
    exit 0
  fi
  # A .env.local with no grid id is operator pre-configuration (e.g. custom ports,
  # per this script's own port-collision guidance). Keep it; append below.
  info "Found operator-provided .env.local (no TAP_GRID_ID) — keeping it, appending the install identity."
fi

# ============================================================================
# Step 2: Host prerequisites
#
# Everything here is a precondition the script cannot create: Docker, the
# Compose v2 plugin, a responsive daemon, free default ports. Fail loudly and
# specifically — an adopter's first five minutes should never be spent
# interpreting a raw docker traceback. Linux specifics (docker group, lsof,
# bind-mount ownership) live in docs/misc/doc-dev-multisession-onboarding.md.
# ============================================================================
bold "Step 2: Checking host prerequisites"

command -v git >/dev/null 2>&1 || fail "git not found on PATH."
command -v docker >/dev/null 2>&1 || fail "docker not found on PATH.
    macOS: install Docker Desktop. Linux: install Docker Engine + the compose plugin."
docker compose version >/dev/null 2>&1 || fail "'docker compose' (the v2 plugin) is not available.
    The retired v1 'docker-compose' binary is not supported. Linux: apt install docker-compose-plugin."

DOCKER_PROBE_TIMEOUT=8
if ! with_timeout "$DOCKER_PROBE_TIMEOUT" docker info >/dev/null 2>&1; then
  fail "The Docker daemon is not responding (probe timed out after ${DOCKER_PROBE_TIMEOUT}s).
    Start Docker Desktop (or your Docker engine: systemctl start docker) and re-run.
    Linux: a permission error here usually means your user is not in the 'docker' group."
fi
info "Docker daemon responsive; compose v2 present."

# Existing project state = an earlier install (or a re-clone beside one). Booting
# into its named volumes would silently attach that database — the same drift
# spawn's stale-docker check exists for. Refuse; deletion is the operator's call.
COMPOSE_PROJECT="$(env_get COMPOSE_PROJECT_NAME)"
EXISTING="$(docker ps -a --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" --format '{{.Names}}' 2>/dev/null)"
EXISTING_VOLS="$(docker volume ls --format '{{.Name}}' 2>/dev/null | grep -E "^${COMPOSE_PROJECT}_" || true)"
if [[ -n "$EXISTING" || -n "$EXISTING_VOLS" ]]; then
  fail "Docker already has state for project '${COMPOSE_PROJECT}':
    containers: ${EXISTING:-none}
    volumes:    ${EXISTING_VOLS:-none}
    This machine already ran a TAP instance under that name (possibly from another
    clone). Stand-up will not silently attach its database. Either manage the
    existing instance from its own clone, or — to DESTROY it and start fresh —
    run: docker compose -p ${COMPOSE_PROJECT} down -v --remove-orphans"
fi

# Default-port availability, probed with bash's built-in /dev/tcp so this works
# with no lsof on the host (unlike spawn, there is no band search here — exactly
# two ports to check, and a busy port is a hard stop, not a steer-around).
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3>&- 3<&-; return 0; } || return 1; }
WEB_PORT="$(env_get WEB_PORT)"
POSTGRES_PORT="$(env_get POSTGRES_PORT)"
for p in "$WEB_PORT" "$POSTGRES_PORT"; do
  if port_busy "$p"; then
    fail "Port $p is already in use on this host.
    TAP's defaults are web=$WEB_PORT postgres=$POSTGRES_PORT (.env). A distro
    PostgreSQL on 5432 is the usual culprit on Linux — stop it, or change
    WEB_PORT/POSTGRES_PORT in a .env.local you create before re-running."
  fi
done
info "Ports $WEB_PORT (web) and $POSTGRES_PORT (postgres) are free."

# ============================================================================
# Step 3: Mint the install identity and write .env.local
#
# TAP_GRID_ID is the immutable per-install identity (see .env). The checked-in
# value is a placeholder that makes bare `docker compose up` work; a real
# install mints its own, exactly as spawn does per session. scripts/uuid7
# carries the pre-container pure-python fallback for hosts older than 3.14.
# ============================================================================
bold "Step 3: Writing .env.local (install identity + boot profile)"
TAP_GRID_ID="$(scripts/uuid7)"
[[ -n "$TAP_GRID_ID" ]] || fail "Could not mint a UUIDv7 install id (scripts/uuid7 returned nothing)."
# Append, never overwrite — Step 1 guaranteed any existing file is operator
# pre-configuration (custom ports etc.) with no TAP_GRID_ID of its own.
cat >> .env.local <<EOF
# Written by scripts/stand-up.sh $(date -u +%Y-%m-%dT%H:%M:%SZ) — per-install overrides
# layered over .env by scripts/dc (gitignored; safe to edit).
TAP_GRID_ID=$TAP_GRID_ID
TAP_BOOT_PROFILE=$BOOT_PROFILE
EOF
info "Install id: $TAP_GRID_ID"

# ============================================================================
# Step 4: Build the image and start the stack
# ============================================================================
bold "Step 4: Building the image and starting the stack (docker compose up -d --build)"
info "First build compiles the FIPS-validated OpenSSL provider from source and"
info "installs the Python closure — expect 10–20 minutes on a laptop. This is the"
info "one long step; every later start is seconds. (TAP_FIPS=0 skips the FIPS"
info "build — an explicit dev-only escape hatch, not the published posture.)"
scripts/dc up -d --build

# ============================================================================
# Step 5: Wait for the entrypoint (uv sync + FIPS self-check + migrate + serve)
#
# Provenance: scripts/spawn-session.sh Step 5 — the standup-watch idiom
# (req-boot-abort-signal): fast-fail on an emitted TAP-ABORT or a dead
# container instead of polling a corpse to the timeout.
# ============================================================================
bold "Step 5: Waiting for the entrypoint to finish (uv sync + migrate + runserver)"

abort_check() {
  local line
  line="$(scripts/dc logs web 2>&1 | grep -a 'TAP-ABORT:' | tail -n1 || true)"
  [[ -z "$line" ]] && return 0
  fail "Standup ABORTED (fast-fail).
    Reason: ${line#*TAP-ABORT: }
    Diagnose: the /diagnose-failed-session-spawn skill, or: scripts/dc logs web"
}
web_container_dead_check() {
  local state
  state="$(scripts/dc ps --all --format '{{.State}}' web 2>/dev/null | head -n1 || true)"
  case "$state" in
    exited|dead|restarting)
      abort_check
      fail "The web container is not running (state=${state}) — standup crashed before serving.
    Diagnose: the /diagnose-failed-session-spawn skill, or: scripts/dc logs web" ;;
  esac
}

WAIT_TIMEOUT=300
WAIT_START=$(date +%s)
while true; do
  abort_check
  web_container_dead_check
  if scripts/dc exec -T web python -c "
import urllib.request, sys
try:
    urllib.request.urlopen('http://localhost:8000/admin/', timeout=2)
    sys.exit(0)
except urllib.error.HTTPError:
    sys.exit(0)  # a real server answering 4xx/5xx is still 'listening'
except Exception:
    sys.exit(1)
" 2>/dev/null; then
    info "Web is responding."
    break
  fi
  elapsed=$(($(date +%s) - WAIT_START))
  [[ $elapsed -gt $WAIT_TIMEOUT ]] && fail "Web did not become ready in ${WAIT_TIMEOUT}s (no ABORT signal seen). Check: scripts/dc logs web"
  printf "    waiting... %ds\r" "$elapsed"
  sleep 3
done
echo

# ============================================================================
# Step 6: Boot the instance (manage.py boot owns the standup contract)
#
# Same bridge as spawn Step 6 (req-boot-spawn-bridge): resolve an admin
# password, expose it via .dev-credentials, and hand DJANGO_SUPERUSER_* to
# boot's auth phase (req-tap-auth-local-5). Resolution: TAP_DEV_ADMIN_PASSWORD
# env → random. (No Keychain tier here — that is spawn's multi-session
# convenience; set the env var if you want a stable password.)
# ============================================================================
bold "Step 6: Booting the instance (manage.py boot --profile $BOOT_PROFILE)"

if [[ -n "${TAP_DEV_ADMIN_PASSWORD:-}" ]]; then
  ADMIN_PASSWORD="$TAP_DEV_ADMIN_PASSWORD"
  info "Admin password source: \$TAP_DEV_ADMIN_PASSWORD"
else
  ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  info "Admin password source: random (fresh for this install)"
fi
ADMIN_EMAIL="admin@tap.localhost"

cat > .dev-credentials <<EOF
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=$ADMIN_PASSWORD
DJANGO_SUPERUSER_EMAIL=$ADMIN_EMAIL
GENERATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

if ! scripts/dc exec \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_PASSWORD="$ADMIN_PASSWORD" \
  -e DJANGO_SUPERUSER_EMAIL="$ADMIN_EMAIL" \
  web uv run python manage.py boot --profile "$BOOT_PROFILE"; then
  abort_check
  fail "manage.py boot failed (profile '$BOOT_PROFILE') — see the output above, or: scripts/dc logs web"
fi

# ============================================================================
# Step 7: Wire the in-tree skill farm for the attached AI assistant
# ============================================================================
bold "Step 7: Wiring skills (.claude/skills/)"
scripts/wire-skills.sh || warn "wire-skills failed — slash-command skills unavailable until you run scripts/wire-skills.sh manually."

# ============================================================================
# Done
# ============================================================================
bold "TAP is up"
info "URL:       http://localhost:${WEB_PORT}/"
info "Sign in:   username 'admin' — password in .dev-credentials (gitignored)."
info "           The login page offers a passkey button; use the password link"
info "           for first login, then enroll a passkey from your session."
info "Manage:    scripts/dc up -d | scripts/dc down | scripts/dc logs -f web"
info "Next:      /new-plugin to scaffold your first plugin; each plugin's README"
info "           documents its collectors and any credentials they need."
info "Problems:  /diagnose-failed-session-spawn, or open a GitHub issue."
