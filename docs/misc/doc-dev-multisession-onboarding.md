---
spec: ../../specs/spec-dev-multisession-onboarding-doc.md
audience: [developer, llm]
covers:
  - ../../specs/spec-dev-multisession.md
  - ../../specs/spec-dev-multisession-smoketest.md
  - ../../specs/spec-dev-multisession-teardown.md
  - req-dev-multisession-spawn-script
  - req-dev-multisession-admin-bootstrap
update-triggers:
  - scripts/spawn-session.sh invocation, prompts, or output
  - Restructuring of spec-dev-multisession-smoketest.md or -teardown.md
assumes:
  - macOS (the primary dev environment) or a Linux desktop (supported with the
    host prerequisites below; Kali is the first target)
  - bash available (the scripts are `#!/usr/bin/env bash`; your login shell may be zsh)
provides: |
  Reader knows the single command to run to spin up a new isolated TAP dev
  session, what a Linux host needs on board first, and where to look for what
  the script does (the requirements in spec-dev-multisession.md) and what to do
  next (smoke-test and teardown specs).
---

# Onboarding a New Multi-Session Dev Environment

Spec: [spec-dev-multisession-onboarding-doc.md](../../specs/spec-dev-multisession-onboarding-doc.md)

Run the interactive spawn script and follow the prompts:

```bash
cd ~/Documents/code/tap
scripts/spawn-session.sh
```

The script is the canonical procedure. It implements [req-dev-multisession-spawn-script](../../specs/spec-dev-multisession.md#spawn-script) and [req-dev-multisession-admin-bootstrap](../../specs/spec-dev-multisession.md#admin-user-bootstrap); each block in the script carries inline comments pointing at the requirement that defines its behavior. To understand *what* the script does or *why*, read those requirements — not a parallel description here, which would only drift.

After the script finishes, attach Claude Code to the new worktree (the script prints the exact command at the end), then run the smoke tests in [spec-dev-multisession-smoketest.md](../../specs/spec-dev-multisession-smoketest.md). When you're done with the session, see [spec-dev-multisession-teardown.md](../../specs/spec-dev-multisession-teardown.md).

Use `scripts/dc exec web ...` for app Python commands inside an active session. The container owns `/app/.venv` through a per-session Docker volume; host-side Python tools should use a separate env such as `.venv-host` if needed.

## Host prerequisites (Linux)

These are *environment* prerequisites — things the spawn script cannot do for you and
therefore does not document. macOS needs only Docker Desktop; a Linux desktop needs:

- **Docker Engine with the Compose v2 plugin** (`docker compose`, not the retired
  `docker-compose` v1 binary — `scripts/dc` invokes the plugin form). Your user must be
  able to run `docker` — the `docker` group, or root, which on Kali you may be anyway.
- **`lsof`** — the spawn script's port-band probe depends on it and refuses to run
  without it. Default on Kali and macOS; minimal installs: `apt install lsof`.
- **Free ports.** Sessions bind host ports in per-session bands (web 8000+, Postgres
  5432+ — the registry in spec-dev-multisession.md). A distro Postgres already listening
  on 5432 collides with the primary stack's default; stop it or let the spawn script's
  band allocation steer around it.
- **A stable admin password source, if you want one.** The macOS Keychain step is
  skipped off-Darwin; set `TAP_DEV_ADMIN_PASSWORD` in your environment for a stable
  cross-session password, or take the random per-session one from `.dev-credentials`.
- **The bind-mount ownership papercut.** The dev container runs as root and the repo is
  bind-mounted at `/app`, so on Linux anything the container writes into the tree
  (migrations, `black`/`ruff --fix` output, `uv.lock`, `__pycache__`) lands **root-owned
  in your checkout** — macOS Docker Desktop maps this away, Linux does not. When your
  editor hits a permission error: `sudo chown -R "$USER" .` in the worktree. Proper UID
  mapping is backlogged; until then this is a known cost of the road less traveled.
- **Sign-in without a platform authenticator.** Linux desktops generally have no
  Touch-ID equivalent, so at the login page use either a plugged-in FIDO2 security key
  (it needs a PIN set; if the browser cannot see the key, install your distro's fido2
  udev rules) or the password fallback link, which is enabled on dev profiles.
