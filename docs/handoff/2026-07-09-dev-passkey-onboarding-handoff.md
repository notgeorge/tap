# Handoff — Dev Passkey Onboarding + the Guard-Bypass Finding

**Date:** 2026-07-09
**Session:** `session/samsite-boot` (worktree `/Users/george/tap-sessions/samsite-boot`, web `:8020`, pg `:5452`)
**Status:** built, all lanes green, **uncommitted and unpromoted**
**Context for the next session:** the repo is mid-swap to a **Wolfi base container with FIPS enabled**. See the FIPS section — it interacts with this work.

---

## 1. How this started

The session's purpose was to confirm the samsite boot profile loads everything, including passkey login. George asked "can I log in with passkey at :8020?" The answer was no — nothing was enrolled. Minting a genesis invitation worked, he registered with Touch ID, and logged in. That succeeded.

Then `export_dev_passkey` failed with `user 'admin' has no WebAuthn user handle`. Chasing that one error surfaced a design seam, then a security finding, then a hole in the guards system.

---

## 2. What was actually wrong

### 2.1 The "register once, replay forever" flow was unreachable

The documented dev-bootstrap loop is: register a `localhost` passkey once → export the public record → every future spawn binds it with no re-registration. Replay (`import_dev_admin`) hardcodes the target account to `DEV_ADMIN_USERNAME = "admin"`.

But there was **no way to register a passkey onto `admin`**:

- `enroll_admin --email …` derives the username from the email (`_unique_username`), producing `operator@example.com`, not `admin`.
- Pinning the username wasn't possible — there was no `--username`.
- Even with one, `enroll_first` is create-only and `admin` already exists (spawn's Step 6 password bridge creates it).
- The correct path, `add_credential`, **crashed**: `views_enroll.enroll_options` called `WebAuthnUserHandle.objects.get(user=target)`, which raises `DoesNotExist` for an account that never registered a passkey — i.e. every password-era account, including `admin`.

So the export→import round trip landed the credential on a *different account* than it was registered on. Login still resolved (discoverable credentials look up by the replayed `user_handle`, not the username), so nothing broke loudly — the labels just diverged, invisibly, for whoever is least able to tell cosmetic from broken: a developer in their first hour.

**The `WebAuthnUserHandle` fix is not dev-only.** Every password-era account that password retirement (`req-tap-auth-passkey-recovery`) migrates will need to bind its first passkey through exactly this path.

### 2.2 `spawn-session.sh` gated on a stat, and printed wrong instructions

Step 6.4 tested `[[ -f "$RECORD" ]]`. A **zero-byte file passes that test** — and a zero-byte file is precisely what a failed `> record` redirect leaves behind, since the shell truncates the target before the command runs. Spawn would take the record-present branch, fail the import, and tell the developer the profile "may not be `dev_local`" when the record was simply empty.

Line 787 printed `export_dev_passkey > "$RECORD"` with no `--username`. Following spawn's own printed instructions reproduced the original error exactly.

(There is still a **zero-byte `~/tap-secrets/dev-passkey/admin.dev-passkey.json`** on the host from that failed redirect. It is now correctly classified `needs_registration` rather than `ready`, so it is inert — but see §6.)

### 2.3 The security finding: the gate was a docstring

`import_dev_admin` creates an admin and binds a WebAuthn credential with **zero proof-of-possession** — no attestation, no challenge-response. Whoever controls the record's bytes controls which public key becomes admin, and a dev-session admin holds real `~/tap-secrets` cloud credentials.

Its only protection was `assert_dev_import_allowed`, called **at one call site** (`enroll_admin.py:170`), with the function's docstring instructing callers to do so:

> *"Callers MUST have already run `assert_dev_import_allowed`."*

That instruction was already being ignored: `test_dev_bootstrap.py` called `import_dev_admin(record)` ungated at **four** call sites. The bypass was one import away, and the new `bootstrap_dev_passkey` command would have been the fifth.

---

## 3. How this bypassed the GUARDS system

This is the part worth carrying forward. It is not "the guards missed it."

**One guard fired. We silenced it — and it was firing for the wrong reason.**

The `direct-write` ratchet flagged `dev_record.py::import_dev_admin::User.get_or_create`. Commit **`ae911d22`** ("annotate dev-import genesis write for direct-write coverage ratchet", 2026-07-08) added three lines of comment to make it green:

```
# TAP-WRITE-COV: below-the-capability-gate root-of-trust bootstrap (genesis-class,
# like sync.ensure_initial_admin) — auth bootstrap is the sanctioned direct-ORM
# exception; no capability-holding caller exists when the dev admin is first minted.
```

Every word is **true**. Genesis really does sit below the capability gate. It is also **completely orthogonal to the actual danger.** The annotation answers *"why is there no `authorize()` here?"* Nobody asked *"and is the other gate — the `dev_local` allowlist that is the entire reason this function is safe — actually enforced?"*

Three compounding failures:

1. **The guard was watching by class name, not class.** `_tap_model_names()` collects the *names* of `BaseModel` subclasses. `tap_auth.User` is **not** a `BaseModel` — but `computing_core.User` **is**, so the string `"User"` enters the scope set and every `User.objects.*` call repo-wide gets flagged as if it were the plugin's graph model. *The only guard that touched this code touched it by coincidence.* Rename `computing_core.User` and the guard goes silent on `dev_record.py` forever.

2. **It flagged the harmless line and missed the dangerous one.** `User.objects.get_or_create` just makes an account row. The dangerous statement is two lines later — `WebAuthnCredential.objects.update_or_create`, the zero-PoP credential bind. `WebAuthnCredential` is a plain auth-infra model, off the Entity spine, so it is *correctly* out of the direct-write guard's scope. **The one line that mattered was never flagged by anything.**

3. **No other guard had jurisdiction, and each was right not to.**
   - `authz-coverage` scans for calls to privileged *graph write sinks* (`write_batch`, `grift_import`, `_*_internal`). `import_dev_admin` calls none.
   - `service-boundary-imports` polices `_`-prefixed submodules inside `services/` boundary packages. `dev_record.py` is neither.
   - Nothing models the `dev_local` allowlist, because it isn't the authz system — it's a bespoke, hand-rolled profile check.

**The structural reason.** Every guard in the harness checks a *local, structural* property: does this call sit lexically inside a gated function; does this module import that module; does this log line carry a hex token. All answerable by reading one file. But *"callers must invoke `assert_dev_import_allowed` before calling `import_dev_admin`"* is an **interprocedural dataflow** property spanning module boundaries. Nothing in `tap/guards` does interprocedural analysis, and a guard that tried would be expensive and fragile.

The rule lived in a docstring because a docstring was the only place it *could* live, given the shape of the harness. **A comment asserting a guarantee is a latent lie until it fails** — and it already had, silently, four times.

**Hence the fix changes the property rather than adding a checker.** Moving the gate *inside* `import_dev_admin` makes "is it gated?" answerable by reading one function — local again, true by construction rather than by convention. The new guard then enforces something structural checkers are genuinely good at: **containment** — not "was it gated" but "can this dangerous name even be imported outside the shell surface."

---

## 4. What was built (all green, uncommitted)

### Three-layer defence for the zero-PoP bind

| Layer | Where | Status |
|---|---|---|
| **Runtime** — gate inside the function | `import_dev_admin` calls `assert_dev_import_allowed(resolve_profile_kind(...))` first, unconditionally | ✅ built (`dev-bootstrap-15`) |
| **Review-time** — guard | `tap_auth/guards/dev_passkey_import.py` — name-level: flags `import_dev_admin` + the module handle, ignores harmless public-record builders | ✅ built (`dev-bootstrap-16`) |
| **Build-time** — not shipped in prod | dev-only commands in a `dev` UV extra | ❌ **Proposed** (`slim-install-7`) |

The spec **explicitly forbids** treating the build-time layer as a reason to drop the runtime checks: a dev build can be pointed at a customer profile (`--profile` exists for that), and a dev image on a staging host holds real cloud credentials.

The guard was **proven to fail** on both bypass shapes (direct name import; module-handle import) and proven **not** to fire on the harmless `build_record_for_user` import. A guard that can't fail is a false green.

### `manage.py bootstrap_dev_passkey` — the single implementation

Resolves exactly one of `not_dev` / `ready` / `needs_registration`, then acts.

- **Validate, don't stat** — readiness decided by `load_dev_record` (schema + integrity digest). Zero-byte, truncated, corrupt, tampered → `needs_registration`, with a diagnostic naming which failed.
- **Stream discipline** — narration + the secret-bearing enrollment URL to **stderr**; record JSON to **stdout** only under `--emit-record`; machine state to stdout only under `--json`. Redirecting stdout is always safe and never captures the one-time secret.
- **Caller-owned placement** — `/run/tap-secrets` is `:ro` by design (that mount is an integrity control). The command emits; the host writes `mktemp` → `chmod 600` → `mv -f`.
- **Never blocks headless** — `--wait` is opt-in and timeout-bounded. `docker compose exec -T` strips the TTY, so the caller (`spawn`, via `[[ -t 0 ]]`) owns the "is a human present" decision, not an `isatty()` inside the container.
- **Right shape for the world it finds** — `enroll_first` with a **pinned** username on a truly fresh instance; `add_credential` onto the existing account otherwise.

### Supporting changes

- **`--username` pinned at mint** (`enrollment-8`). Create-only. Fails loud at mint **and again at redeem** — the mint→redeem window is a real TOCTOU gap. The redeem-side refusal rolls the consume back so a squatter cannot burn the invitation. Confers no authority: username stays a mutable display label, never an identity anchor (same reasoning as *email is not identity*).
- **`WebAuthnUserHandle` get_or_create** in `enroll_options` — a password-era account can now bind its first passkey.
- **`mint_below_gate_as_bootloader`** — shared genesis-class mint so `enroll_admin` and `bootstrap_dev_passkey` cannot drift on below-the-gate attribution.
- **`build_record_for_user`** — shared record builder so `export_dev_passkey` and `bootstrap_dev_passkey` cannot drift on credential selection.
- **`spawn-session.sh` Step 6.4** rewritten as a *caller*: `--json` → branch → import, or guided register + atomic placement.
- **Validation Map row** generated (`manage.py guards --sync-map`): *"Dev passkey import stays shell-only"*.

### Verification actually performed

- `tap_auth` lane: **266 passed** (was 226).
- `tap_web` lane: **259 passed**.
- All guards: **86 passed** (incl. the new one + Map-sync).
- mypy: clean across every touched file; the mypy ratchet passes.
- Guard failure proven by planting violations; harmless import proven not to fire.
- Live container: state machine, refusals, stream discipline, and spawn's JSON parse all exercised against `:8020`.

**Not verified:** the real Touch ID gesture. Tests drive a vendored ES256 virtual authenticator against real `py_webauthn` verification — that is not a Secure Enclave. `dev-bootstrap-12` (atomic placement) and `-13` (TTY/wait) are proven in tests, **not in the field**.

---

## 5. Outstanding — everything, not just the immediate

### 5.1 This work, to finish

1. **Commit and promote.** Everything is uncommitted on `session/samsite-boot`. The worktree is on disk and survives a container rebuild.
2. **Live Touch ID run.** `scripts/dc exec web uv run python manage.py bootstrap_dev_passkey --register --wait` from a terminal, then a fresh `spawn-session.sh` to watch the guided path (register → emit → `chmod 600` → atomic `mv`) end-to-end.
3. **`req-tap-auth-passkey-dev-bootstrap-17` — the AI-operable skill.** `tap_auth/skills/bootstrap-dev-passkey/` does **not** exist. The spec names it (spec-ai-integration: "author operational procedures as AI-operable skills"). Repo skills live at `<app>/skills/`, symlinked via `scripts/wire-skills.sh`. This is why `req-tap-auth-passkey-dev-bootstrap` is still requirement-level `Proposed`.
4. **`req-tap-auth-passkey-slim-install-7`** — the build-time layer. Dev-only commands (`bootstrap_dev_passkey`, `export_dev_passkey`, `--import-dev-passkey`) ship in a `dev` UV extra a production build never installs. Rides slim-install; do not build a bespoke exclusion mechanism ahead of it.
5. **`spec-dev-multisession.md` companion edit.** Four ACs under `req-dev-multisession-admin-bootstrap` still describe the password-era bridge and say "superseded by `req-tap-auth-passkey-dev-bootstrap` *once it lands*." It has now partly landed; Step 6.4 is a command caller. Reconcile.
6. **Minor:** the refusal message for `--register` under a non-dev profile reads "`--import-dev-passkey` is permitted only under…" — accurate about the gate, mildly confusing about which flag the user typed.

### 5.2 Guard-system findings (the durable ones)

7. **`direct_write` matches by class NAME, not resolved class.** False positives (`tap_auth.User` flagged because `computing_core.User` exists) and a false sense of coverage. Should key on the resolved model class. Contained fix. **Do this next** — it is the highest-leverage item in this list.
8. **Annotation escape hatches inherit the quality of the reviewer's question.** `# TAP-WRITE-COV: <reason>` demands a reason for the *write*. When a write is safe for reason A but dangerous for unrelated reason B, a *true* reason A silences the alarm permanently. Consider requiring the annotation to name **what makes the call safe**, not merely why the guard's rule doesn't apply.
9. **Nothing guards credential binds.** `WebAuthnCredential` is off the Entity spine, so `direct_write` correctly ignores it — yet it is functionally the most privileged write in the codebase. A surface with no guard has no Validation Map row, so this gap is currently *invisible* in the Map. That is a `req-dev-validation-map-1` blind spot worth naming.
10. **Guards cannot express interprocedural preconditions.** Worth deciding explicitly: is that a permanent boundary of the harness (and therefore "make the property local" is always the answer), or is there a narrow class of "X must precede Y" rules worth a dataflow guard?

### 5.3 Security posture, outside this spec

11. **`~/tap-secrets` permissions.** Directory is `0755`; four `*.secret.json` files are `0644` — Google OIDC client secret, GitHub token, AWS collector creds — world-readable to any local account. The dev-passkey record itself *is* `0600`. The `dev_record` docstring names "0600 in an operator-owned dir" as the load-bearing anti-tamper mitigation; the filesystem and the code's stated mitigation disagree for the neighbours. Single-user Mac, so practical risk is low. Belongs in `spec-security-posture.md` as a named risk. **Reminder: `~/tap-secrets` is shared host state — symlinked into every session.**
12. **Is `~/tap-secrets` the right home for a non-secret?** Concluded **yes**, but for reasons unrelated to the directory's name: the record's *integrity* is load-bearing (confidentiality is not), and that directory is the only one with the two properties it needs — operator-owned `0600`, and read-only inside every container. The trust boundary doesn't widen: anyone who can write there can already write the real secrets. Residual cost is **semantic** (an auditor enumerating "what secrets does TAP hold" finds a public key). Clean future fix: a sibling `~/tap-public/` with the same ownership + `:ro` semantics. Not a blocker.

### 5.4 Repo hygiene

13. **Repo-wide formatting drift.** Running the CLAUDE.md-documented `black .` / `ruff check --fix .` reformatted **49 files** unrelated to this work (pure line reflow at the 120-char config, plus a stray blank line). I reverted all of them to keep this diff honest. **The drift is real and sitting in `main`** — anyone running the documented command re-triggers it. Wants a separate, dedicated formatting sweep commit. Files span `tap/`, `tap_grid/`, `tap_cares/`, `tap_web/`, `tap_plugins/`, `scripts/`, and most of `plugins/`. Also `tap_auth/migrations/0004_*.py` is unformatted.
14. **Migration `0009_invitation_username.py`** will be swept up by the planned pre-customer migration squash (one `0001_initial` per app, landing in the same fresh-DB wave as plugin eviction).

### 5.5 Live-session leftovers (harmless, but know they exist)

15. Zero-byte `~/tap-secrets/dev-passkey/admin.dev-passkey.json` — inert now (classified `needs_registration`), overwritten by the first real export. **Shared across all sessions.**
16. Two pending `add_credential` invitations in the samsite DB from `--register` smoke tests (1h TTL, expired by now).
17. George's Touch ID holds a real passkey registered against `localhost:8020` bound to user **`operator@example.com`**, not `admin`. It works for login. macOS Passwords will show it under that name. The guided flow will register a *second* credential onto `admin`; that is the intended target for replay.
18. This session's DB has **two** admins: `admin` (password bridge, superuser, `tap_admin`) and `operator@example.com` (passkey, `tap_admin`).

---

## 6. FIPS / Wolfi — what to check when the base image lands

The passkey stack is the most crypto-dependent surface in the repo. Under a FIPS-enabled build, non-approved algorithms **fail closed at the library level**, so verify rather than assume:

- **`py_webauthn` / `cryptography`** — the ceremony uses ES256 (ECDSA P-256 + SHA-256) and SHA-256 digests. Both are FIPS-approved, but confirm the `cryptography` build's backend accepts them and that no code path reaches a non-approved primitive (e.g. Ed25519 `EdDSA` if any authenticator negotiates it — check `ceremony.registration_options`' supported algorithm list).
- **The vendored virtual authenticator** (`tap_auth/tests/virtual_authenticator.py`) generates keys and signs. If it uses a non-approved path, the **entire passkey assurance corpus goes red under FIPS** while production code is fine. That would be a confusing first failure.
- **Invitation token hygiene** — `hashlib.sha256` + `secrets.token_urlsafe` + `hmac.compare_digest`. All FIPS-fine.
- **Record integrity** — `canonical_digest_bytes` (sha256). Fine.
- **`md5`/`sha1` anywhere** in Django internals under `FIPS mode` can raise; Django usually flags `usedforsecurity=False`, but a FIPS-strict OpenSSL may still object. Worth a full-lane run early.

Do a **full `scripts/test` run** on the new base image before trusting any of the above.

---

## 7. Files touched

**Modified:** `scripts/spawn-session.sh`, `specs/spec-dev-validation.md` (generated Map row), `tap_auth/invitations.py`, `tap_auth/models.py`, `tap_auth/views_enroll.py`, `tap_auth/passkey/dev_record.py`, `tap_auth/management/commands/enroll_admin.py`, `tap_auth/management/commands/export_dev_passkey.py`, `tap_auth/specs/spec-tap-auth-passkey-v0.md`, `tap_auth/tests/test_dev_bootstrap.py`, `tap_auth/tests/test_passkey_assurance.py`

**New:** `tap_auth/management/commands/bootstrap_dev_passkey.py`, `tap_auth/guards/__init__.py`, `tap_auth/guards/dev_passkey_import.py`, `tap_auth/migrations/0009_invitation_username.py`, `tap_auth/tests/test_dev_onboarding.py`

**Spec RIDs added:** `req-tap-auth-passkey-enrollment-8`, `req-tap-auth-passkey-dev-bootstrap-9…-17`, `req-tap-auth-passkey-slim-install-7`
