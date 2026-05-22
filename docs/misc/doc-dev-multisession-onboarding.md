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
  - macOS / zsh shell (the only environment the spawn script supports today)
provides: |
  Reader knows the single command to run to spin up a new isolated TAP dev
  session, and where to look for what the script does (the requirements in
  spec-dev-multisession.md) and what to do next (smoke-test and teardown specs).
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
