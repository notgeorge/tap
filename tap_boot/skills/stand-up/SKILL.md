---
name: stand-up
description: Stand up a freshly cloned TAP repo as a running, logged-in-able local instance by preparing the host and driving scripts/stand-up.sh — the adopter first-boot path (macOS or Linux desktop). Use when someone with a new clone says "get TAP running", "stand up TAP/Rampart", "launch this", or asks how to log in for the first time. NOT for multi-session dev worktrees (that is scripts/spawn-session.sh) or an already-stood-up clone (scripts/dc up -d).
allowed-tools: Read Grep Glob Bash(scripts/*) Bash(docker *) Bash(docker compose *) Bash(git *) Bash(uname *) Bash(grep *) Bash(cat *) Bash(ls *) Bash(tail *)
argument-hint: [boot-profile]  (default: core — the zero-plugin baseline)
---

# Stand Up TAP From a Fresh Clone

> **Skill source-of-truth.** Canonical location: `tap_boot/skills/stand-up/SKILL.md`. `.claude/skills/…` is a wiring symlink (`scripts/wire-skills.sh`). Edit the canonical.

`scripts/stand-up.sh` is the **single canonical implementation** of first boot: host
checks, install-identity mint, image pull (GHCR, anonymous — local build only as the
offline/modified-Dockerfile fallback), entrypoint wait, `manage.py boot`, admin
credentials, skill wiring. This skill is its conversational driver — you prepare the
host, make the three choices with the human, invoke the script, and walk them in the
door. **Re-implement nothing.** If the script's behavior looks wrong, fix the script;
a parallel procedure here would only drift (the `bootstrap_dev_passkey` discipline).

The goal is minutes-to-logged-in, with the human feeling cared for at every step —
first-adopter onboarding, not expert workflow.

## Step 0 — Recognize which situation you are in

Route before running anything:

- **`.env.local` has `TAP_SESSION_LABEL`** → this is a multi-session dev worktree.
  Stop; manage it with `scripts/dc`, and see `docs/misc/doc-dev-multisession-onboarding.md`.
- **`.env.local` has `TAP_GRID_ID`** → already stood up. `scripts/dc up -d` starts it;
  don't re-run stand-up (it will correctly refuse).
- **Neither / no `.env.local`** → fresh clone. Proceed.

The script guards all three itself — this step exists so you route the conversation
correctly instead of learning the situation from a refusal message.

## Step 1 — Prepare the host (platform-specific)

Detect the platform (`uname`). Then:

- **macOS**: Docker Desktop installed and running is the whole list.
- **Linux** (Kali is the first-class target): work through **"Host prerequisites
  (Linux)"** in `docs/misc/doc-dev-multisession-onboarding.md` — Docker Engine with
  the Compose v2 plugin, docker-group membership, free ports. Warn about the
  root-owned bind-mount papercut *before* it bites (the relief valve is
  `sudo chown -R "$USER" .`). That section is the canonical list; don't restate it
  from memory.
- **Both**: expect ~10 GB free disk for the images, and network access to
  `ghcr.io` (anonymous) for the published `tap-web`/`tap-db` pulls. Only the
  local-build fallback additionally needs the base image + OpenSSL source.

## Step 2 — Three choices, made WITH the human

1. **Boot profile** (the script's one argument; default `core`).
   `core` is the zero-plugin baseline: boots with no credentials, guaranteed, and is
   the right first boot for "I want to see it run, then build my own plugins."
   Richer profiles (`core_dev`, `samsite`) install plugins from their git sources —
   offer them only if those repos are reachable from this machine (during the
   org migration window some may not be). `samsite` additionally needs AWS
   credentials and per-deployment configuration — that is a second session's work,
   documented in the samsite plugin README, not a first boot.
2. **FIPS** (default ON — leave it on unless asked). The published image ships the
   FIPS-validated OpenSSL provider pre-built and pre-activated — FIPS costs the
   adopter nothing at stand-up time. Only the local-build fallback compiles it from
   source (10–20 minutes, once). `TAP_FIPS=0 scripts/stand-up.sh` is the explicit
   dev-only escape hatch (and forces a local build — the published artifact is
   FIPS-on only).
3. **Admin password**: default is random-per-install, written to `.dev-credentials`.
   If they want a stable one, have them export `TAP_DEV_ADMIN_PASSWORD` first —
   never type a password into the chat.

## Step 3 — Run it

```bash
scripts/stand-up.sh            # or: scripts/stand-up.sh <profile>
```

Narrate the phases as they pass (the script's `==>` banners): prereq checks are
seconds; the image pull is the longest step on a cold machine (a few minutes of
download; the local-build fallback is the 10–20 minute path); the entrypoint wait
(cache-seeded uv sync + migrate) is under a minute; boot is seconds on `core`. The
script fast-fails on a `TAP-ABORT` signal rather than hanging — silence with a
progress counter is normal, a stall past ~5 minutes after the pull is not.

## Step 4 — If it fails

The script fails specifically, not generically — **read the error first**; it names
the fix for every precondition (daemon down, port busy, stale project state, missing
compose plugin). For failures *after* the stack starts (entrypoint or boot phase),
drive `/diagnose-failed-session-spawn` — it reads the same `TAP-ABORT` /
container-state evidence this script emits, and its Step 0 works from a compose
project name (here: the `COMPOSE_PROJECT_NAME` in `.env`, default `tap`).

If it is genuinely stuck or looks like a TAP bug, say so plainly and help them file
a GitHub issue with: the script output from the failing step, `scripts/dc logs web`
tail, platform (`uname -a`), and Docker version. Rough edges reported by first
adopters are wanted — make filing feel like contributing, not complaining.

## Step 5 — Walk them in the door

From the script's final summary:

1. Open the printed URL. The login page offers a passkey button and (on dev
   profiles) a password link — first login is **username `admin` + the password
   from `.dev-credentials`** (passkeys need enrollment first, and on a Linux
   desktop a platform authenticator may not exist at all; a FIDO2 security key
   with a PIN also works once enrolled).
2. Once they're in, suggest enrolling a passkey from the authenticated session.
3. Point forward: `/new-plugin` scaffolds their first plugin; each plugin's README
   documents its collectors and credentials; `scripts/dc up -d` / `down` /
   `logs -f web` is the daily loop.
