---
name: provision-secrets
description: Guide an operator from "this boot profile declares secrets" to "every required secret present, kind-matched, and alive" — enumerate needs offline from the profile's required_secrets declaration, check current state via the boot record and envelope metadata, route each gap to its kind's canonical minting docs, place the envelope safely, and verify through the boot preflight. Use when a boot/preflight reports a missing or dead secret, before first boot of a credentialed profile (e.g. samsite), or when someone asks "what credentials does this need?" NOT for wiring a NEW secret kind into the system — that is /manage-secret.
allowed-tools: Read Grep Glob Bash(scripts/dc *) Bash(scripts/*) Bash(docker *) Bash(git *) Bash(ls *) Bash(cat boot/*) Bash(python3 *) Bash(grep *) Bash(mkdir *) Bash(chmod *) Bash(tail *)
argument-hint: [boot-profile]  (default: the session's TAP_BOOT_PROFILE from .env.local)
---

# Provision the Secrets a Boot Profile Requires

> **Skill source-of-truth.** Canonical location: `tap_boot/skills/provision-secrets/SKILL.md`. `.claude/skills/…` is a wiring symlink (`scripts/wire-skills.sh`). Edit the canonical.

The profile's `required_secrets` declaration (`req-boot-required-secrets`, `spec-tap-boot-v0.md`) is the single machine-readable source of what must be provisioned — this skill is its named consumer. The boot preflight enforces it in two lanes (`req-boot-obs-preflight-6`): **offline** (envelope present, kind matches — a *provisioning* gap: mint it) and **live** (the collector's self-test — a *liveness* gap: rotate it). Your job is to walk the operator across whichever gap the evidence shows, without ever seeing a secret value.

**Division of labor with `/manage-secret`:** that skill *authors* — a new secret kind, a new consumer, scanner/redaction wiring (developer-facing). This skill *provisions* — supplies values for already-declared requirements (operator-facing). If the work turns into "TAP doesn't have a kind/consumer for this yet," switch skills.

## Redaction discipline (read first, non-negotiable)

- **Never print, echo, or paste a secret value into the conversation** — not the `data` block of an envelope, not a token "just to check it." When inspecting envelopes, read **identity fields only** (`scope`, `key`, `kind`, `description`, `metadata`); a one-liner that cannot leak: `python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print({k: d[k] for k in ('scope','key','kind','description') if k in d})" <path>`.
- The operator types values into their own editor, never into chat. You write envelope **skeletons** with `"<PASTE-VALUE-HERE>"` placeholders; they fill them in.
- `~/tap-secrets` is **shared host state** symlinked into every session — editing an envelope mutates all live sessions at once. Say so before any edit; for red-testing or experiments, point `TAP_SECRETS_ROOT` at a private scratch dir instead.

## Step 0 — Enumerate the requirements (offline, from the declaration)

Read the profile — `boot/<profile>.boot.json` (repo-local) or the staged record — and present the requirement table: for each `required_secrets` entry, its `scope:key`, `kind`, the least-privilege `note`, and which enabled steps consume it (`secrets` refs). No container, no network needed (`req-boot-required-secrets-6`).

A profile with no `required_secrets` and no fire-collector steps needs nothing — say so and stop. Auth-section secrets (e.g. an OIDC client secret) are outside this declaration by design; auth's own boot validation covers them.

## Step 1 — Establish current state (evidence, not guesswork)

Best evidence first:

1. **The boot record** — `<worktree>/logs/boot/latest.boot-record.json`. Its preflight entries answer both lanes per ref/collector: `{"type": "preflight", "key": "<scope>:<key>", "status": ...}` for the offline checks, collector-keyed entries (with `failing_checks`) for the live lane. The abort block's `missing_secrets` (ref/kind/note/problem) is the exact worklist.
2. **No record yet** (never booted): check envelopes directly under `$TAP_SECRETS_ROOT` (`<scope>/<key>.secret.json`) — presence, and `kind` via the identity-fields one-liner above. This predicts the offline lane; only a boot proves the live lane.

Classify each requirement: **present + alive** (done), **missing/kind-mismatched** (provisioning gap → Step 2), **present but dead** (liveness gap — a 401/403 in the live lane's `failing_checks` → Step 2, framed as *rotate/re-mint*, and the old value is revoked provider-side, not merely misplaced).

## Step 2 — Route each gap to its kind's canonical guidance

**Do not restate minting steps here — they live with the kind's consumer and would only drift.** Route:

- `github_pat` → the samsite plugin README ("Place the GitHub credential") and `github_core`'s collector secret schema (`tap_plugin/github_core/.../secret.py` documents the exact `data` fields). Least-privilege posture rides the declaration's `note` (read-only Metadata + Contents + Actions, scoped repos).
- `aws_static_access_key` / `aws_assumed_role` → the samsite plugin README (Steps 1–2) and `aws_core`'s handoff kit (`tap_plugin/aws_core/collectors/boto3_collector/handoff/`) for the cross-account variant. Region scope lives on the envelope and is mandatory.
- Any other kind → its consuming plugin's README + secret schema module (the kind is consumer-owned, `req-tap-cares-secrets-consumer-kinds`). If no consumer documents it, that's an authoring gap → `/manage-secret`.

Walk the operator through minting **conversationally** (which console, which scopes to tick, what expiry), reading from those sources — the human does the clicking; remind them about expiry ("set one you'll outlive, or calendar the rotation — an expired token aborts the next boot at preflight").

## Step 3 — Place the envelope

Write the skeleton at `$TAP_SECRETS_ROOT/<scope>/<key>.secret.json` (create the scope dir if needed) with `scope`/`key`/`kind` exactly as declared, a human `description`, and placeholder `data` matching the kind's schema. Then:

- Operator fills the value(s) in their editor. `chmod 600` the file.
- Never commit it (the leak-guard would catch it; don't make it try). Never place fixtures with a real-looking name — `.secret.example.json` for templates.
- Repeat the shared-state warning if the target is the `~/tap-secrets` symlink.

## Step 4 — Verify through the machinery, not by hand

The secrets loader is **load-once (restart-to-rotate)**: a new or changed envelope is invisible until the web container restarts. So:

```bash
scripts/dc restart web
# wait for readiness, then:
scripts/dc exec web uv run python manage.py boot --profile <profile>
```

The preflight is the verifier: the offline lane confirms presence + kind, the live lane proves the credential works — one output, both answers, and the boot record persists the verdict. Green means fully provisioned *and* alive; don't hand-craft curl checks when the self-test already encodes the right probe.

## Step 5 — If it still fails

- Live-lane failure after a fresh mint → `/diagnose-failed-session-spawn`'s credential signature splits credential-dead vs target-moved (e.g. the envelope's `repos`/target list is stale even though the token is good).
- Offline-lane failure after placing the file → kind typo (envelope `kind` vs declared), wrong path (`scope`/`key` must match the filename convention), or the restart was skipped.
- The need itself looks wrong (profile demands a secret this deployment shouldn't have) → the profile is config-as-code: disabling the consuming step drops the requirement (the coherence rules then demand removing the entry) — an edit for the operator to make deliberately, not a waiver to talk them around.
