# Prompt for the next session

Copy everything below the line into the new session.

---

We're picking up work from `session/samsite-boot` (worktree `/Users/george/tap-sessions/samsite-boot`, web `:8020`, pg `:5452`). The base container is being swapped to **Wolfi + FIPS**, so assume nothing about the runtime until you've run the lanes.

**Read this first, in this order:**

1. `docs/handoff/2026-07-09-dev-passkey-onboarding-handoff.md` — the full writeup. Sections 3 (how the guards were bypassed), 5 (outstanding), and 6 (FIPS) are the load-bearing ones.
2. `tap_auth/specs/spec-tap-auth-passkey-v0.md` — the `Dev Bootstrap` and `Invitation & Enrollment Chokepoint` sections. RIDs `req-tap-auth-passkey-dev-bootstrap-9…-17`, `req-tap-auth-passkey-enrollment-8`, `req-tap-auth-passkey-slim-install-7`.
3. The keystone(s) on the grid and the active step in `plan/road-rampart.md` — note that George said the roadmap is being rewritten, so **ask before treating the current active step as authority**.

**State of the work:** built, all lanes green (`tap_auth` 266, `tap_web` 259, guards 86, mypy ratchet clean), **uncommitted and unpromoted** on `session/samsite-boot`. The worktree survives a container rebuild. Nothing is committed — start by reviewing `git diff` and the five new files before you change anything.

**The finding worth understanding before you touch the guards:** `import_dev_admin` binds an admin WebAuthn credential with zero proof-of-possession. Its only protection used to be a docstring telling callers to gate first — which four test call sites already ignored. Exactly one guard ever touched that code (`direct-write`), and it did so **by accident**, because it matches TAP-managed models *by class name* and `computing_core.User` happens to share a name with `tap_auth.User`. It flagged the harmless `User.objects.get_or_create` and never saw the dangerous `WebAuthnCredential.objects.update_or_create` two lines below. Commit `ae911d22` then silenced it with a `# TAP-WRITE-COV:` annotation whose stated reason was *true but orthogonal* to the actual danger. The gate now lives inside the function, and a new `tap_auth/guards/dev_passkey_import.py` enforces containment.

**What I want done, roughly in this order — but check with me before starting anything large:**

1. **Verify the stack on Wolfi/FIPS.** Full `scripts/test` run. Pay attention to `tap_auth`: the ceremony uses ES256 (P-256 + SHA-256) and the *vendored virtual authenticator* (`tap_auth/tests/virtual_authenticator.py`) generates keys and signs. If it reaches a non-approved primitive, the whole passkey assurance corpus goes red under FIPS while production code is fine. Diagnose before "fixing."
2. **Fix `direct_write` to match on the resolved model class, not the class name** (`tap/guards/direct_write.py::_tap_model_names`). This is the highest-leverage item outstanding. Expect the baseline to move — that's the point. Confirm `tap_auth.User` stops being flagged and that no genuine `BaseModel` write goes unflagged.
3. **Live Touch ID verification** of the guided flow — `manage.py bootstrap_dev_passkey --register --wait` from a terminal, then a fresh `spawn-session.sh`. `dev-bootstrap-12` (atomic placement) and `-13` (TTY/wait) are proven in tests, not in the field. I have to do the gesture; drive me through it.
4. **`req-tap-auth-passkey-dev-bootstrap-17`** — the `bootstrap-dev-passkey` skill. Doesn't exist yet; the spec names it and that's why the requirement is still `Proposed`. Repo skills live at `<app>/skills/`, wired by `scripts/wire-skills.sh`.
5. **Reconcile `spec-dev-multisession.md`** — four ACs under `req-dev-multisession-admin-bootstrap` still describe the password-era bridge and say passkey replay supersedes them "once it lands." It has partly landed.

**Also carry these forward — don't let them drop:**

- **Nothing guards credential binds.** `WebAuthnCredential` is off the Entity spine so `direct_write` correctly ignores it, yet it's functionally the most privileged write in the codebase. A surface with no guard has no Validation Map row, so the gap is *invisible* in the Map. Decide whether that's a `req-dev-validation-map-1` blind spot worth closing.
- **Annotation escape hatches inherit the reviewer's question.** Should `# TAP-WRITE-COV:` be required to name *what makes the call safe*, rather than why the guard's own rule doesn't apply?
- **Guards can't express interprocedural preconditions** ("X must precede Y" across modules). Is that a permanent boundary of the harness — meaning "make the property local" is always the answer — or is there a narrow class worth a dataflow guard?
- **`req-tap-auth-passkey-slim-install-7`** — the build-time layer (dev-only commands in a `dev` UV extra a prod build never installs). Rides slim-install. Do **not** build a bespoke exclusion mechanism ahead of it, and do **not** treat it as a reason to relax the runtime gates.
- **`~/tap-secrets` file permissions.** Dir is `0755`; four `*.secret.json` are `0644` (Google OIDC client secret, GitHub token, AWS collector creds) — world-readable to any local account. The dev-passkey record is correctly `0600`. Belongs in `spec-security-posture.md` as a named risk. Remember `~/tap-secrets` is **shared host state** symlinked into every session.
- **Repo-wide formatting drift.** Running the CLAUDE.md-documented `black .` / `ruff check --fix .` reformats **49 files** unrelated to any current work. I reverted them to keep the diff honest. Wants its own dedicated sweep commit — don't let it contaminate a feature diff.
- **Migration `0009_invitation_username.py`** will be absorbed by the planned pre-customer migration squash (one `0001_initial` per app, same fresh-DB wave as plugin eviction).

**Live-session leftovers you'll trip over:** a zero-byte `~/tap-secrets/dev-passkey/admin.dev-passkey.json` (inert — now classified `needs_registration`, overwritten by the first real export); two expired `add_credential` invitations in the samsite DB; and two admins in that DB — `admin` (password bridge) and `george@criticalsec.com` (holds my real Touch ID passkey, bound to `localhost:8020`). Replay targets `admin`, so the guided flow registers a second credential there. That's intended.

Start by reading the handoff doc and the `git diff`, then tell me what you'd do first and why. Don't start building until we've agreed on the order.
