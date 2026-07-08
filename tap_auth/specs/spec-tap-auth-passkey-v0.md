# TAP Auth Passkey v0 Specification

## Philosophy

`spec-tap-auth-v0.md` starts human authentication at an external identity provider: Google/OIDC vouches that a login belongs to a real, domain-scoped human, and the whole login-security chokepoint lives in the social adapter's `pre_social_login`. That model is correct when a customer already runs an IdP — but it makes the IdP a hard dependency for *any* human to log in, and it does not, on its own, get TAP off passwords: the IdP's own password is still the front door.

This spec defines the complementary path: **passwordless-primary authentication where TAP is its own identity authority.** A human logs in with a passkey (WebAuthn/FIDO2 discoverable credential + local user verification) directly against TAP, with no IdP in the loop. Passkeys are phishing-resistant by construction (origin-bound key pairs the browser/OS refuses to present on the wrong domain), leak nothing useful on a server breach (the server holds only public keys), and fold "something you have" + "something you are" into one gesture.

**Target deployment (drives every trade-off below):** a **secure solo developer / single-user self-hosted** instance, stood up by the operator themselves — potentially exposed on the public internet — that wants strong, phishing-resistant authentication **without the burden of wiring an external IdP**. Low-friction stand-up is a first-class goal. And the posture is itself a signal: our earliest users are security-minded, so **"no static passwords anywhere, phishing-resistant by default, no IdP required"** is an early, legible statement of how seriously this product takes security. The **default posture is the signal** — a passkey-only build in which the social-login framework is *not even installed* (`req-tap-auth-passkey-slim-install`) is the strongest form of that statement: minimal dependencies, minimal attack surface, only what you need.

The core doctrine is:

> Without an IdP, TAP is the identity authority. Login-by-passkey is easy; the security weight is entirely on **bootstrap** — how the first passkey is bound to a user, and what stops anyone from binding one. The chokepoint moves from `pre_social_login` to a TAP-owned **enrollment chokepoint**. The single root of trust is out-of-band shell / `manage.py` access; everything above it is passkeys.

This is a deliberate deviation from IdP-as-bootstrap, chosen 2026-07-07: the goal is a login process more secure than a password that does **not** require an IdP. Federated (IdP) and passkey methods coexist as peer families under one registry, and — because the passkey stack shares no code with the federated stack — a passkey-only deployment can drop the federated dependency entirely.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Passwordless-Primary | A human logs in with a passkey, no IdP and no password, as the ordinary path. |
| 2. | TAP-As-Authority | Account existence is decided by a TAP-owned, gated enrollment ceremony — not delegated to an IdP. |
| 3. | One Root Of Trust | Genesis and recovery are uniformly out-of-band `manage.py`; there is exactly one break-glass floor. |
| 4. | Method-Pluralism + Slim Install | Federated and passkey login are peer families under one boot-declared registry; a passkey-only deployment never installs the federated (allauth) stack. |
| 5. | Machine-Legible | Passkey enrollment state is a queryable projection so a human or AI operator can reason about coverage and recovery risk. |
| 6. | Posture-As-Signal | The default build is passwordless-primary, no-IdP, minimal-dependency — a legible security statement to a security-minded audience. |

## Roadmap Alignment

`plan/road-rampart.md` active step is `step-rampart-launch-ready`. Passwordless-primary passkey login is **not** on that step's Done-Test critical path (a single-tenant, shell-operated deployment does not require it), and the step explicitly accepts web-layer auth warts. This spec is justified instead by two things:

- **Immediate user fit.** Our nearest users are individual developers and solo operators who will stand TAP up to try it *without* wanting to configure a Google Workspace / Okta tenant first. Passkey-primary + no-IdP + low-friction stand-up is what that audience actually needs, and the passkey-only build is therefore a **primary** path, not a speculative one.
- **`specs/spec-security-posture.md` cheap-edge doctrine.** The auth surface is freshly built, small, and open right now — the cheap moment to lay the method-registry, slim-install, and enrollment seams; retrofitting auth later is the expensive kind. The build is phased (`req-tap-auth-passkey-rollout`) so the cheap foundation lands now and the disruptive front-door + password-retirement land as the deployment story firms up.

## Prior Art

A four-lane prior-art survey (2026-07-07) grounds this design; the through-line is that our choices land at the **strict/correct** end of every standard, and the one place we deviate from consensus (single-passkey default) is a named accepted-risk (`req-tap-auth-passkey-recovery`).

**Standards & ceremony policy.**
- **W3C WebAuthn Level 3** (https://www.w3.org/TR/webauthn-3/), **SimpleWebAuthn** (https://simplewebauthn.dev/docs/advanced/passkeys/), **Google web.dev** (https://web.dev/articles/passkey-registration), **Yubico** (https://developers.yubico.com/WebAuthn/) establish the recommended defaults for a passkey as a *sole, MFA-grade* factor: **discoverable/resident credentials required** (usernameless login), **user verification required** (the docs default to `preferred`; `required` is the correct call for a lone factor), an **opaque, ≤64-byte, non-PII user handle** (never email/username), RP-ID/origin binding for phishing resistance, `attestation: none` by default, and recording the **Backup-Eligibility (BE) / Backup-State (BS)** flags at registration to detect device-bound (single-point-of-failure) credentials.
- **`py_webauthn`** (Duo Labs; PyPI `webauthn`, v3.x, Production/Stable — https://pypi.org/project/webauthn/) is the chosen crypto core: it implements the four ceremony functions and owns no user model, which fits "TAP is its own identity authority" and yields a one-dependency footprint. **`django-otp-webauthn`** (Stormbase — https://github.com/Stormbase/django-otp-webauthn) is used as a **model-design reference** (its opaque `WebAuthnUserHandle` via `secrets.token_bytes(64)` and full credential fields), not a dependency.

**Recovery.**
- **FIDO Alliance, *Recommended Account Recovery Practices for FIDO Relying Parties*** (2019, https://media.fidoalliance.org/wp-content/uploads/2019/02/FIDO_Account_Recovery_Best_Practices-1.pdf): the primary recovery mechanism is **registering multiple authenticators** (a reserve key "in a desk drawer"); recovery otherwise **re-runs onboarding at equal-or-higher assurance**; "recovery is the weak link"; weak recovery is explicitly not recommended.
- **NIST SP 800-63B-4** (https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63B-4.pdf): verifiers **SHALL** offer a phishing-resistant option at AAL2 (discoverable + UV passkey qualifies); CSPs **SHOULD** encourage **≥2** authenticators; recovery **SHALL** conform to additional-authenticator binding (rebind, not resurrect); **syncable authenticators are AAL2-only** (exportable key disqualifies AAL3); record authenticator characteristics at bind.
- **OWASP Forgot Password / Session Management Cheat Sheets**: enrollment tokens are CSPRNG-random (≥128-bit floor), single-use, short-TTL, **hashed at rest**, HTTPS + `Referrer-Policy: no-referrer`, never built from a request `Host` header, and never auto-login-after-use.

**Self-hosted peers & bootstrap patterns.**
- Self-hosted RPs do passkey-primary with no upstream IdP today — **Authentik** (`ak create_recovery_key` prints a one-shot recovery link ≈ our shell recovery floor; env-var bootstrap admin), **Keycloak 26.4** (`kc.sh bootstrap-admin`, an explicitly *temporary* admin), **Zitadel** (`AddPasswordlessRegistration` returns a link+code you can *display*, not just email), **Ory Kratos** (admin-generated recovery code, headless/API genesis). The email-free admin enrollment path exists in all of them as the *secondary* path — we are restricting to a supported path, not inventing one. **None ships solo + CLI-genesis + passkey-primary + no-email as a first-class feature** → our whitespace.
- **Microsoft Entra Temporary Access Pass** (https://learn.microsoft.com/entra/identity/authentication/howto-authentication-temporary-access-pass) is the closest architectural analog to our invitation: an admin-issued, time-limited, single-use passcode to bootstrap the first passkey *and* to recover. Microsoft's doctrine — "recovery is the hard part; eliminate phishable fallbacks" — plus its numbers (14× faster than password+MFA; 95% vs 30% sign-in success) validate both the model and the positioning.
- Fresh-instance bootstrap patterns to borrow: **kubeadm** bootstrap tokens (`public-id.secret` split → individually revocable, log-safe), **GitLab** (`initial_root_password` printed then auto-deleted after 24h), **Jupyter** (token to stdout, never emailed), **HashiCorp Vault** ("bootstrap then revoke" the init token), **Portainer** (time-boxed first-run claim window). Anti-pattern: **Grafana** `admin/admin` default — a per-install random CLI-minted token is strictly better.
- **SSH-key / mutual-TLS** is the conceptual lineage: an operator with pre-existing host access bootstraps the first credential — exactly what shell genesis is, and the right shape for any future machine/CLI/service actor.

**Alternatives considered and rejected as *primary*** (mined for bootstrap/recovery companions only): SMS OTP (NIST-*restricted*; SIM-swap), email OTP / **magic links** (phishable bearer tokens capped at mailbox strength), **TOTP-only** (phishable *and* stores a replayable server-side seed), **OPAQUE/SRP** (a "better password," still not phishing-resistant; RFC 9807 has no notable production primary deployment), **SQRL** (lacked the ecosystem/distribution passkeys have — cautionary "don't roll your own scheme"). **Recovery/backup codes** are the one worthwhile *recovery companion* (offline, no delivery channel; see Backlog). Big-platform direction of travel — GitHub, Google, Apple (WWDC25 Account Creation API → accounts that "never have passwords"), Entra — confirms passkey-primary is mainstream; **Cloudflare** still 2FA-only in 2026 is a useful contrast for the positioning.

## Supersedes / Reconciles

This spec revises three decisions elsewhere for deployments that adopt passwordless-primary mode:

- **`req-tap-auth-policy-6` (Admin Recovery Floor)** in `spec-tap-auth-v0.md` — the "Django-admin-superuser-with-a-password is the break-glass floor" is **replaced** by a shell-only floor (`req-tap-auth-passkey-recovery`). Admin password login retires; `manage.py` / out-of-band shell becomes the sole reachable break-glass path. The invariant ("no boot/config may converge to no reachable admin path") is preserved and re-founded on shell.
- **`req-tap-auth-local` (Local Password Auth)** in `spec-tap-auth-v0.md` — local password login moves from "dev/default recovery path" to "retired from the routine surface by default, including Django admin; dev-only if explicitly enabled." `TAP_LOCAL_PASSWORD_ENABLED` is retained as the mechanism; a passwordless deployment defaults it off.
- **`req-dev-multisession-admin-bootstrap`** in `spec-dev-multisession.md` — the dev spawn admin bridge changes from "resolve a Django superuser *password* (Keychain → env → random) and `createsuperuser`" to "seed the admin and **replay the operator's exported public passkey record**" (`req-tap-auth-passkey-dev-bootstrap`). This retires the dev password and makes the dev loop exercise the real passkey path.

`spec-tap-auth-v0.md`'s `req-tap-auth-providers` (the federated provider framework) is **generalized, not discarded**, into the login-methods registry (`req-tap-auth-passkey-methods`): federated providers remain exactly as specified and become the `federated` method family. Reconciliation notes are added to `spec-tap-auth-v0.md` and `spec-dev-multisession.md` pointing here.

## Relationship To Existing Specs

- `tap_auth/specs/spec-tap-auth-v0.md` — the auth system this extends (actors, capabilities, providers, policy, sessions, boot).
- `tap_auth/specs/spec-tap-auth-assurance-v0.md` — **retired/deprecated** (its surface-centric model was rejected; see its banner). Passkey assurance does **not** depend on it: `req-tap-auth-passkey-assurance` defines its cases directly and capability-centrically. The authoritative auth model is `spec-tap-auth-v0.md` + `docs/misc/doc-auth-per-app-standards.md`.
- `tap_plugins/specs/spec-plugin-architecture.md` — `req-plugin-arch-slim-install` / `req-plugin-arch-python-deps`; the optional-install machinery the slim-install requirement reuses.
- `specs/spec-dev-multisession.md` — the spawn machinery the dev bootstrap reuses (`req-dev-multisession-admin-bootstrap`).
- `specs/spec-security-posture.md` — the cheap-edge / name-the-open-risk doctrine this spec applies.
- `specs/spec-tap-boot-v0.md` — the boot profile the auth method config, deps-gate, and genesis validation ride on.
- `specs/spec-ai-integration.md` — the Player-3 legibility filter behind the credential projection.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-auth-passkey-methods | [Login Methods Registry](#login-methods-registry) | Proposed | Generalize `providers` → login methods with a `kind` discriminator; sole-passkey deployment is first-class |
| req-tap-auth-passkey-slim-install | [Slim Install](#slim-install) | Proposed | Auth stack as UV extras; passkey-only never installs allauth; conditional INSTALLED_APPS + boot deps-gate; realizes `req-plugin-arch-slim-install` |
| req-tap-auth-passkey-webauthn | [WebAuthn Passkey Method](#webauthn-passkey-method) | Proposed | Native on `py_webauthn` (Duo); discoverable + UV required; opaque handle; RP-ID as boot config; TAP-owned ceremony + login views |
| req-tap-auth-passkey-enrollment | [Invitation & Enrollment Chokepoint](#invitation--enrollment-chokepoint) | Proposed | Moved chokepoint; OWASP-hardened one-time tokens with public-id/secret split; admin-UI/CLI display, no email; atomic consume |
| req-tap-auth-passkey-genesis | [Genesis Bootstrap](#genesis-bootstrap) | Proposed | Production first-login; `manage.py enroll-admin --print-token`; disposable genesis admin; zero-provider boot validation |
| req-tap-auth-passkey-dev-bootstrap | [Dev Bootstrap (Spawn Passkey Replay)](#dev-bootstrap-spawn-passkey-replay) | Proposed | Register-once / replay-forever; `--import-dev-passkey`; supersedes the password-based spawn bridge; dev/test-only, fails closed in prod |
| req-tap-auth-passkey-identity | [Native Identity & Credential Projection](#native-identity--credential-projection) | Proposed | Native users have no `ExternalIdentity`; queryable `WebAuthnCredential` projection incl. BE/BS/AAGUID; record characteristics at bind |
| req-tap-auth-passkey-recovery | [Recovery Floor & Password Retirement](#recovery-floor--password-retirement) | Proposed | Shell-only floor; retire passwords incl. admin; rebind-not-resurrect; single passkey allowed (named risk) + permit-N + BE-aware nudge |
| req-tap-auth-passkey-assurance | [Passkey AuthN Assurance](#passkey-authn-assurance) | Proposed | `authn_providers.passkey.json` rows: gating, replay/expiry, UV, RP-ID mismatch, dev-import-refused-in-prod |
| req-tap-auth-passkey-rollout | [Rollout](#rollout) | Proposed | Feature phases (foundation → bootstrap → front door) × slim-install phases (A both-installable → B allauth-optional) |

---

### Login Methods Registry
----
RID: `req-tap-auth-passkey-methods`  
Status: `Proposed`

TAP MUST generalize the boot-declared provider registry into a **login-methods** registry with a `kind` discriminator, so a passkey is a first-class login method rather than an IdP wearing a provider costume.

A federated provider (`req-tap-auth-providers`) is shaped entirely around external-IdP semantics — `resolve_secrets` (client credentials), `evaluate_access(claims)`, OIDC discovery self-tests, `build_allauth_settings` (a social APPS entry). A passkey method has none of these: no upstream IdP, no client secret, no `hd`/`sub` claim, no discovery document. Forcing it into the `Provider` protocol would be a Procrustean fit; the registry instead admits families that share the declarative/self-testable/policy-gated contract but differ in protocol.

#### Implementation

- Method families (v0 `kind` values, closed set):
  - `federated` — external IdP (`google_oidc` today; future SAML/Okta). Unchanged from `req-tap-auth-providers`; existing provider configs load as `federated`.
  - `passkey` — WebAuthn/TAP-native (`req-tap-auth-passkey-webauthn`).
  - `local_password` — legacy Django password; the degenerate local-credential member, off by default (`req-tap-auth-passkey-recovery`).
- The boot `auth` section declares methods (federated providers continue to appear as today; the loader tags them `kind: federated`). A `passkey` method entry carries RP-ID/origin and ceremony policy, not secrets.
- Common method contract: `validate_config` (offline shape), `self_test` (offline + optional live), and a machine-legible description — mirroring `req-tap-auth-providers-4/5`. A passkey method's `self_test` verifies RP-ID/origin coherence and that a reachable enrollment/genesis path exists; it has no `resolve_secrets`/`evaluate_access`/`build_allauth_settings`.
- A deployment MAY declare a `passkey` method and **zero** `federated` providers — the sole-passkey deployment. Boot validation MUST accept this (`req-tap-auth-passkey-genesis`), not assume at least one provider. The dependency dimension of this (dropping allauth) is `req-tap-auth-passkey-slim-install`.
- Federated and passkey methods coexist at runtime: a federated-provisioned user MAY also enrol passkeys, subject to the enrollment chokepoint.
- The `providers.<type>` health probe (`req-tap-auth-providers-8`) generalizes to `methods.<id>`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-methods-1 | Kind Discriminator | Proposed | The registry admits `federated`/`passkey`/`local_password` methods behind a closed `kind` set. | |
| req-tap-auth-passkey-methods-2 | Providers Preserved | Proposed | Existing federated provider configs load unchanged as `kind: federated`. | |
| req-tap-auth-passkey-methods-3 | Sole-Passkey Deployment | Proposed | A boot profile with a passkey method and zero federated providers is valid and boots. | |
| req-tap-auth-passkey-methods-4 | No IdP Shape On Passkey | Proposed | A passkey method has no secret/claims/discovery surface; unknown method kinds fail closed and loud. | |
| req-tap-auth-passkey-methods-5 | Coexistence | Proposed | Federated and passkey methods can be enabled together on one deployment. | |

---

### Slim Install
----
RID: `req-tap-auth-passkey-slim-install`  
Status: `Proposed`

The auth stack MUST be installable per-method so that a **passkey-only deployment never downloads or imports the federated (allauth) stack**. This realizes `req-plugin-arch-slim-install` for auth (already anticipated in `pyproject.toml`: "a future slim/headless install may move the auth stack to an optional extra so headless instances drop it entirely") and is the concrete form of Goal 6 — minimal dependencies as the security signal.

The enabling fact: because the passkey stack is native on `py_webauthn` and shares no code with allauth (`req-tap-auth-passkey-webauthn`), passkey login has zero allauth dependency. (This is why passkeys cannot live in `allauth.mfa` — a submodule of allauth — which would make passkey-only-without-allauth impossible.)

#### Implementation

- **UV extras** in the root `pyproject.toml` `[project.optional-dependencies]`:
  - `passkey = ["webauthn>=3", ...]` (the `py_webauthn` distribution) — no allauth.
  - `federated = ["django-allauth[socialaccount]>=65"]`.
  - `full` = the explicit union of the `passkey` and `federated` package lists (e.g. `["webauthn>=3", "django-allauth[socialaccount]>=65"]`), *not* a self-referential `tap[passkey,federated]` — kept literal for portability unless self-referential-extra resolution is confirmed for the toolchain.
  - `django-allauth` and its transitive OIDC deps move **out of core `dependencies`** into the `federated` extra. Core keeps only what every profile needs.
- **Profile-driven install** — the pre-boot stage installs the extra(s) the boot profile's declared methods require, reusing the plugin `install`-section machinery in `tap/preboot.py` (the same lever that editable-installs only the plugins a profile declares).
- **Conditional `INSTALLED_APPS`** — `ALLAUTH_APPS` is spliced in only when allauth is present, discovered from **installed distribution metadata** (the same mechanism already used for `*TAP_PLUGINS_APPS`), so the app list is self-consistent with the venv and never stale.
- **Import isolation — full inventory.** allauth is currently the login/logout engine, URL-name provider, an auth backend, middleware, and part of the template shell, so Phase B MUST inventory and retire/alias *all* of these, not just the adapter/providers. Known touchpoints (verified 2026-07-07): `tap_auth/adapter.py` and `tap_auth/providers/*` (allauth imports); `tap_auth/auth_backends.py` (`TapAllauthBackend` imports allauth at module load); `tap_auth/urls.py` (`include("allauth.urls")`); `tap/settings.py` (allauth `AccountMiddleware`, `SOCIALACCOUNT_*`/`ACCOUNT_*`, and `ALLAUTH_APPS`); `LOGIN_URL = "account_login"`; and templates reversing allauth URL names (e.g. `account_logout` in `tap_web/templates/tap_web/base.html`). Each MUST be reachable only when the federated method is installed. The invariant "no tap app imports allauth at AppConfig-load time" is extended to "a passkey-only build never imports allauth at all." Conversely, whenever allauth **is** installed (a federated build), `AccountMiddleware` MUST be **retained**: allauth hard-requires it and it clears dangling partial-login state, so its removal is a security regression in that build. The conditional wiring is retain-under-federated / absent-under-passkey-only — never remove-always. (A passkey-only build has no allauth partial-login artifact; its single-use, atomically-consumed challenge is the analogous control.)
- **Stable TAP-owned URL names** — `tap_auth` MUST provide stable `login`/`logout` URL names (and set `LOGIN_URL` to a TAP name) that *both* builds satisfy — aliased to allauth views in a federated build, served by TAP views in a passkey-only build. Templates reverse the TAP names, never allauth-specific names, so a no-allauth install neither crashes at import nor fails template URL reversing.
- **Boot deps-gate** — a profile declaring a `kind: federated` method whose package is absent (or `kind: passkey` whose package is absent) MUST fail boot loudly, reusing the plugin declared-vs-installed reconciliation guard (`build_report` family). Fail closed, never silently skip a configured method.
- **Lean-boot gate** — a `scripts/gate-lean` variant spawns a passkey-only stack in its own venv and asserts allauth is neither installed nor imported (catches import-leak regressions the full-venv gate cannot).
- **Default solo-dev profile** installs `tap[passkey]` only — allauth is not on disk. That absence is the point.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-slim-install-1 | Auth Extras | Proposed | `passkey`/`federated`/`full` extras exist; allauth is in `federated`, not core deps. | |
| req-tap-auth-passkey-slim-install-2 | Passkey-Only No allauth | Proposed | A passkey-only install has allauth neither installed nor imported; a lean-boot gate proves it. | |
| req-tap-auth-passkey-slim-install-3 | Conditional Apps | Proposed | `INSTALLED_APPS` includes allauth apps only when allauth is installed, via installed-metadata discovery. | |
| req-tap-auth-passkey-slim-install-4 | Deps-Gate | Proposed | A declared method whose package is absent fails boot loudly (reconciliation guard), never silently skipped. | |
| req-tap-auth-passkey-slim-install-5 | Import Isolation | Proposed | Every allauth touchpoint (adapter, providers, auth_backends, urls, middleware/settings, `LOGIN_URL`, template URL names) is reachable only when the federated method is installed. | |
| req-tap-auth-passkey-slim-install-6 | No-allauth Renders | Proposed | A passkey-only install neither crashes at import nor fails template URL reversing; login/logout resolve via stable TAP URL names. | |

---

### WebAuthn Passkey Method
----
RID: `req-tap-auth-passkey-webauthn`  
Status: `Proposed`

TAP MUST implement the passkey method natively on **`py_webauthn`** (Duo Labs; Production/Stable), owning the ceremony endpoints, credential storage, and — in a passkey-only build — the login/logout view scaffolding. `py_webauthn` provides the crypto (the four ceremony functions) and no user model, which fits "TAP is its own identity authority" and yields a one-dependency footprint. `django-otp-webauthn`'s data model is a design reference (opaque handle + credential fields), not a dependency.

#### Implementation

- **Ceremony** via `py_webauthn`: `generate_registration_options` / `verify_registration_response` and `generate_authentication_options` / `verify_authentication_response`. TAP owns the views, challenge storage (server-side, single-use), and the `WebAuthnCredential` persistence (`req-tap-auth-passkey-identity`).
- **Ceremony policy (the load-bearing *request* settings):**
  - **Discoverable (resident) credentials REQUIRED** (`residentKey=required`) — usernameless login.
  - **User verification REQUIRED** (`userVerification=required`) — biometric/PIN mandatory; every passkey is MFA-grade in one gesture. (Stricter than the common `preferred` default; correct for a sole factor.)
  - **Opaque user handle** — a stable, non-PII opaque value (`secrets.token_bytes(64)` per user, stored hex), never email/username.
  - `pubKeyCredParams` = ES256 (-7) + EdDSA (-8) + RS256 (-257) — EdDSA offered for modern Ed25519-capable authenticators, RS256 retained for older ones; the RP verifies each assertion against the *stored* credential's algorithm, so offering more algorithms carries no downgrade risk. `excludeCredentials` set to prevent double-registration; `attestation=none` (authenticator allowlisting is Backlog). Under `none` the AAGUID is **best-effort, not guaranteed**: clients zero it to all-zeros for many roaming authenticators (security keys), while synced platform passkeys usually keep their *well-known provider* AAGUID — so it is captured when present but MUST NOT be assumed populated, and all-zeros means *unknown*. Reliable make/model capture needs `attestation: direct` (Backlog). The BE/BS flags, by contrast, live in the authenticator-data flags byte and **are** reliable under `none`.
- **Assertion/registration verification (the load-bearing *enforcement* settings).** `py_webauthn`'s verify functions are insecure-by-omission — requesting a policy in the options does nothing unless the server *verifies* it in the response — so these are stated normatively rather than left to implementer discretion:
  - **Verify user verification, not just request it** — both `verify_registration_response` and `verify_authentication_response` MUST be called with `require_user_verification=True`. The library defaults this to `False`; requesting `userVerification=required` in the options while leaving the verify call at its default silently accepts a presence-only (UP-without-UV) authenticator. UV is enforced at the *verify* call, not the options request.
  - **Verify RP-ID and origin on every ceremony** — every registration and assertion MUST pass and enforce `expected_rp_id` (the pinned RP-ID) and `expected_origin`; this is the phishing-resistance check and is not deferred to the method `self_test`. The expected origin is **exact — scheme, host, and port** — never an any-origin or any-`localhost` wildcard (a wildcard lets a co-resident `localhost:<other>` service relay an assertion; see `req-tap-auth-passkey-dev-bootstrap`), and the origin allowlist MUST contain only RP-controlled origins.
  - **Sign-counter regression handling** — on every assertion TAP MUST pass the stored count as `credential_current_sign_count` and persist `max(stored, VerifiedAuthentication.new_sign_count)` back to the credential row. A returned count that regresses (`presented <= stored`, either nonzero) is WebAuthn's cloned-authenticator signal and MUST be audited/flagged. The `stored == 0 && presented == 0` case is the legitimate no-counter authenticator (synced/platform passkeys report 0 permanently) and MUST NOT be treated as a regression. Feeding a hardcoded `0` or discarding `new_sign_count` turns clone detection into a silent no-op.
  - **Challenge lifecycle (bound per ceremony — the user is not always known yet).** The server-side challenge is minted with ≥16 bytes of CSPRNG entropy (the library default is 64), given a short TTL, and consumed atomically (single-use) so a challenge minted for one ceremony cannot be redeemed in a parallel one. Binding differs by ceremony:
    - **Registration / enrollment** — the user *is* known (from the invitation, or from the authenticated session on a self-add), so the challenge is bound to that **invitation/user + session**.
    - **Authentication (usernameless)** — the user is intentionally **unknown** until the assertion is verified, so the challenge is bound to the **session + ceremony metadata only**; the user is resolved *after* verification by credential-id → owning user, confirming the asserted `userHandle` matches (`req-tap-auth-passkey-webauthn-10`). Binding an authentication challenge to a specific user up front is impossible in the discoverable flow and MUST NOT be required.
    `py_webauthn` verifies the challenge value passed to it but does not store, bind, or expire it — that is entirely TAP's responsibility.
  - **Credential-id uniqueness + owner binding** — `credential_id` carries a global unique constraint so a discoverable assertion resolves to exactly one credential/owner. On assertion TAP looks up the credential by `credential_id`, then confirms the asserted `userHandle` equals the owning user's stored opaque handle before authenticating (W3C WebAuthn L3 §7.2).
- **RP-ID / origin as boot config** — the Relying Party ID (registrable domain) and expected origin(s) are a boot-profile field alongside `TAP_BASE_URL`. **Pin RP-ID deliberately at genesis: changing it later invalidates every registered passkey** (loud boot warning). `localhost` is a WebAuthn secure context, so dev works over plain http; the insecure-origin allowance is dev-only and never on for a customer/deploy profile.
- **TAP-owned login scaffolding** — in a passkey-only build there is no allauth, so `tap_auth` owns the login/logout views and the `login`/`logout` URL names (`LOGIN_URL`), built on Django `contrib.auth` + the passkey authentication backend. `tap_web` already owns the auth templates, so this is view + URL wiring, not new templates. (Landed in slim-install Phase B — see `req-tap-auth-passkey-rollout`.) Because this hand-rolled surface replaces machinery Django/allauth supplied by default, it MUST re-assert the controls that machinery gave for free — a custom login flow most easily drops exactly these:
  - **Session-fixation defense** — a successful assertion MUST be finalized through `django.contrib.auth.login(request, user)`, which cycles the session key (`SessionBase.cycle_key()`) on the privilege change. The passkey backend MUST NOT write the auth session keys (`SESSION_KEY`/`_auth_user_id`) directly, which would skip the rotation and leave a pre-auth (attacker-fixated) session valid post-login.
  - **CSRF on ceremony/redeem endpoints** — the registration/authentication/redeem POST endpoints run under `CsrfViewMiddleware` (the `fetch` ceremony call sends `X-CSRFToken`) and are never `@csrf_exempt`. The WebAuthn challenge binds the *assertion object* (origin-bound proof of possession); it is **not** a substitute for CSRF protection of the TAP endpoint that consumes it, which rides the ambient session cookie. This is the passkey analogue of the federated path's `SOCIALACCOUNT_LOGIN_ON_GET = False` login-CSRF guard.
  - **Safe post-login redirect** — the `?next=` target MUST be validated with `django.utils.http.url_has_allowed_host_and_scheme(allowed_hosts=request.get_host())`, falling back to `LOGIN_REDIRECT_URL`; a raw `redirect(request.GET["next"])` is an open redirect (phishing / token-relay hop).
  - **Server-side logout** — the TAP logout view MUST complete through `django.contrib.auth.logout()` (which deletes the server-side session record and flushes), not merely clear the client cookie; for DB-backed sessions a cookie-only logout leaves a live, replayable session. Per-user/global session invalidation (`req-tap-auth-sessions`) continues to work for passkey-native users — Django `User` rows carry `_auth_user_id` with no `ExternalIdentity` needed.
  - **Deploy security gate still runs** — a passkey-only / slim boot MUST still run the deploy security check (`req-tap-auth-boot-7`: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/`SESSION_COOKIE_HTTPONLY`/`SESSION_COOKIE_SAMESITE`, HTTPS/HSTS); re-owning the boot wiring for the no-allauth build MUST NOT drop that gate. For a customer/deploy profile the passkey method `self_test` additionally fails closed if the expected-origin scheme is not `https://` (the `http://localhost` carve-out is dev-only).
  - **Abuse / rate limiting** — challenge-generation, assertion-verification, invitation-redeem, and the fronted `POST /admin/login/` carry throttling (allauth's on-by-default `ACCOUNT_RATE_LIMITS` is gone in the slim build and MUST be replaced), bounding unbounded-challenge memory growth, crypto-verify CPU burn, and enrollment-endpoint enumeration/DoS.
- **Conditional UI (autofill) — necessary but not sufficient.** Offer conditional-UI autofill for usernameless login where supported (heed the Shopify caution: do **not** dangle autofill at invitation-gated first visitors who cannot yet have a credential; present it only where a credential is likely to exist). But autofill alone is insufficient — it may not surface all credentials, especially hardware security keys and cross-device/hybrid authenticators — so the login page MUST **also** present an explicit **"Sign in with a passkey"** action that starts a modal (non-conditional) `navigator.credentials.get()`. Both are required.
- **Authenticated self-add (the v0 affordance behind permit-N).** A logged-in user MUST be able to register an **additional** passkey to their *own* account directly from an authenticated session — the registration ceremony bound to their existing user (no invitation; `excludeCredentials` set to their current credentials to prevent duplicates), the new credential kept-and-added. This is the concrete Phase-1 self-service path that backs the backup nudge (`req-tap-auth-passkey-recovery`) so the nudge points at a real action, not air. (Adding a passkey on a *new device* with no session there uses cross-device/hybrid login above, or the admin-issued additive link in Backlog; a self-service list/name/revoke management page is Backlog.)
- **Cross-device (hybrid) authentication is supported and MUST NOT be precluded.** A user can authenticate on a *new* device by approving on an *existing* one — the platform "scan the QR with your phone" / hybrid transport. To the RP this is an ordinary assertion (`py_webauthn` verifies it like any other), so it needs no special TAP code; but the login / conditional-UI flow MUST NOT assume a local credential exists. This is both a login convenience (a synced or roaming credential logs you in anywhere) and the free bootstrap for **adding a device**: hybrid-login on the new device, then enrol a device-local passkey there (add-a-device affordances in Backlog).
- **Record at registration** the credential public key, credential id, sign count, AAGUID (when present — see the `attestation=none` caveat above; all-zeros is stored as *unknown*), transports, and the **BE/BS flags** (`req-tap-auth-passkey-identity`), which are always present under `none` and feed the BE-aware backup nudge (`req-tap-auth-passkey-recovery`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-webauthn-1 | Native Core | Proposed | The passkey method is implemented on `py_webauthn`; no allauth dependency. | |
| req-tap-auth-passkey-webauthn-2 | Discoverable Required | Proposed | Registration requires discoverable credentials so usernameless login works. | |
| req-tap-auth-passkey-webauthn-3 | User Verification Required | Proposed | Registration and assertion require user verification, **enforced at the verify call** (`require_user_verification=True`), not merely requested in the options. | |
| req-tap-auth-passkey-webauthn-4 | Opaque Handle | Proposed | The user handle is opaque/non-PII (`token_bytes(64)`); email is never used as the handle. | |
| req-tap-auth-passkey-webauthn-5 | RP-ID Configured & Pinned | Proposed | RP-ID/origin are explicit boot config; a mismatch fails the method self-test; changing RP-ID is a loud, documented mass-invalidation. | |
| req-tap-auth-passkey-webauthn-6 | Owns Login Views | Proposed | A passkey-only build serves login/logout from `tap_auth`, not allauth. | |
| req-tap-auth-passkey-webauthn-7 | Origin/RP-ID Enforced Every Ceremony | Proposed | Every registration and assertion enforces the pinned `expected_rp_id` and an **exact** `expected_origin` (scheme+host+port); no any-origin / any-`localhost` wildcard; the allowlist holds only RP-controlled origins. | |
| req-tap-auth-passkey-webauthn-8 | Sign-Counter Regression | Proposed | Each assertion passes the stored sign count and persists `max(stored, new)`; a regression (either nonzero) is flagged as a clone signal; `0/0` is exempt (no-counter authenticator). | |
| req-tap-auth-passkey-webauthn-9 | Challenge Bound & Single-Use | Proposed | The server-side challenge is CSPRNG (≥16B), TTL'd, atomically single-use, and bound **per ceremony**: registration/enrollment to invitation/user + session; authentication (usernameless) to session + ceremony metadata only, with the user resolved post-verify (binding an auth challenge to a user up front is not required). | |
| req-tap-auth-passkey-webauthn-10 | Credential-Id Unique + Owner-Bound | Proposed | `credential_id` is globally unique; a discoverable assertion is resolved by `credential_id` and the asserted `userHandle` is confirmed to equal the owning user's stored handle before authenticating. | |
| req-tap-auth-passkey-webauthn-11 | Session-Fixation Defense | Proposed | A successful assertion is finalized via `django.contrib.auth.login()` (cycles the session key); the backend never writes the auth session keys directly. | |
| req-tap-auth-passkey-webauthn-12 | Ceremony CSRF | Proposed | Registration/authentication/redeem POSTs run under CSRF protection (never `@csrf_exempt`); the WebAuthn challenge is not treated as a CSRF substitute. | |
| req-tap-auth-passkey-webauthn-13 | Login Surface Hygiene | Proposed | `?next=` is validated with `url_has_allowed_host_and_scheme`; logout completes via `auth.logout()` (server-side flush); ceremony/redeem/admin-login endpoints are throttled; the slim boot still runs the `req-tap-auth-boot-7` deploy gate and the `https`-origin self-test for customer profiles. | |
| req-tap-auth-passkey-webauthn-14 | Explicit Passkey Login Action | Proposed | The login page offers both conditional-UI autofill (where supported) and an explicit "Sign in with a passkey" button that starts a modal, non-conditional assertion, so hardware/hybrid credentials are reachable. | |
| req-tap-auth-passkey-webauthn-15 | Authenticated Self-Add | Proposed | A logged-in user can register an additional passkey to their own account from an authenticated session (no invitation; keep-and-add; `excludeCredentials` prevents duplicates) — the v0 affordance backing the permit-N backup nudge. | |

---

### Invitation & Enrollment Chokepoint
----
RID: `req-tap-auth-passkey-enrollment`  
Status: `Proposed`

Account creation MUST pass through a TAP-owned enrollment chokepoint — the native replacement for `pre_social_login`. Without an IdP to vouch for a human, an **invitation** is the cryptographic carrier of an existing admin's vouch, and redeeming it binds the first passkey. This surface now stands where every other system put "verified email + prior first factor," so it is the single most security-critical path and gets the full token discipline below.

#### Implementation

- **`Invitation` model** (plain Django auth-infra model, off the Entity/graph spine like `ExternalIdentity`):
  - a **public-id + secret split** token (kubeadm pattern): a non-secret public id (for lookup/revocation/log lines) plus a high-entropy secret half (≥128-bit CSPRNG) that is **stored hashed** — the raw secret is shown once at mint and never persisted. Redemption looks the row up **by public-id**, then verifies the presented secret with a **constant-time compare** (`hmac.compare_digest`) against a **plain `SHA-256`/`SHA-512`** of the secret. It is deliberately **not** a password KDF (bcrypt/argon2 buy nothing on a full-entropy secret and invite `==`/truncation shortcuts) and a per-secret salt is unnecessary at ≥128-bit entropy; the DB lookup is **never** keyed on the secret-hash (an equality-by-secret query is a timing leak);
  - intended identity (email + display name), the **role grants** to apply, `issued_by` actor, `issued_at`, `expires_at` (short TTL — **default ≈1h for genesis, ≤24h for a general invite, with an enforced maximum the config cannot exceed**; a TTL past the ceiling fails validation, it does not warn-and-proceed), and a lifecycle status (`pending` → `consumed` / `expired` / `revoked`);
  - single-purpose (enroll-first-passkey only — never a general session bearer), and **consumed atomically at credential registration** via a conditional `UPDATE … SET status='consumed' WHERE id=? AND status='pending'` gated on `rowcount == 1` (or `SELECT … FOR UPDATE`) in the **same transaction** as user-create + passkey-bind, so the token dies the instant the first passkey binds and cannot be redeemed twice or raced. A failed or abandoned ceremony leaves the invitation `pending` (still TTL-bounded, still redeemable) — it is burned only on a *successful* bind, so a mid-ceremony hiccup never DoSes the operator by consuming the token at page-load.
- **Token hygiene (OWASP):** CSPRNG-random, single-use, short TTL, hashed at rest, HTTPS-only, and **no auto-login on token use** independent of the passkey ceremony. The enrollment page carries `Referrer-Policy: no-referrer`, `Cache-Control: no-store, no-cache`, and `X-Robots-Tag: noindex`, and its URLs are never built from a request `Host` header. The raw secret rides the URL **fragment** (`/enroll/<public-id>#<secret>`), never the path or query string — the fragment is **never transmitted to the server** by the browser, so the secret is structurally incapable of appearing in any server-side log (reverse proxy, load balancer, app access log, container stdout). Client-side JS reads `location.hash` and submits it in the redeem **POST body**, and the redeem endpoint MUST NOT log its request body. (Path *and* query strings are routinely logged, so neither is acceptable for a live bearer secret; per-hop log redaction is fragile and is at most defense-in-depth, not the control.) This costs nothing — WebAuthn already mandates JS — and as a bonus defeats link-preview crawlers, which fetch the URL without the fragment and never run the JS, so a preview bot can neither read nor consume the token. Named residual: the fragment lands in the redeemer's own browser history — low-stakes (their device; mitigated by `no-store` + short TTL + single-use), far below a server-readable log. Redemption failures — unknown public-id, wrong secret, expired, already-consumed — collapse to **one generic "invalid or expired invitation" response in constant time** (the constant-time secret compare runs regardless of whether the public-id resolved), so the semi-public public-id cannot enumerate invitation existence or lifecycle. Online brute force of the secret is **intentionally not treated as a rate-limited control** — the ≥128-bit entropy floor carries that — though the mint/redeem endpoints inherit the general throttling in `req-tap-auth-passkey-webauthn` as DoS defense-in-depth. Two deliberate positive properties: the enrollment flow makes **no outbound fetch** (no email, no IdP discovery), so its SSRF surface is nil; and the raw secret only ever transits stdout (via `--print-token`) or an authenticated admin view, **never a command argument** where `ps`/argv would expose it.
- **Redemption** opens a scoped, one-shot signup for exactly the invited identity, runs the WebAuthn **registration** ceremony, and atomically: creates the `User` (`user_kind=human`), binds the passkey, applies the grants through the same `is_login_grantable` guard the social adapter uses, and marks the invitation consumed. Identity, grants, and the opaque user handle are taken **from the server-stored `Invitation` row**, never from client input — WebAuthn lets the client supply `user.name`/`user.displayName`, but those are cosmetic-only here, so a redeemer cannot alter the bound email, display name, grants, or handle by POSTing different values.
- **Delivery is display-only** (locked decision): the raw token / enrollment link is shown inside an authenticated admin session or printed by `manage.py enroll-admin --print-token` and hand-carried out-of-band. TAP sends **no email**; there is no SMTP dependency and no email phishing surface. Email delivery is Backlog. **Named residual exposure:** kubeadm's public-id/secret split makes the *public-id* log-safe, but the printed enrollment URL still carries the raw secret, and `--print-token` puts it on stdout — shell history, terminal scrollback, tmux/`script(1)` capture, container stdout, CI logs. Mitigated (not eliminated) by the short genesis TTL and by handling the printed value as a secret; the residual is named rather than implied clean.
- Invitation mint and revoke are capability-gated (`auth.manage_users` family) and audited (issued_by, target, grants, expiry). Enrollment is a registered auth surface (`tap_auth.invite.mint`, `tap_auth.invite.redeem`).
- **Shell mint command (`manage.py enroll-user`).** The imperative twin of the declarative `initial_grants` path — the runtime way to invite a non-admin (e.g. Sam as `tap_viewer`) from the shell without the admin UI or a re-boot: `manage.py enroll-user --email … --role … --print-token` mints an invitation for an arbitrary **human-assignable** role and prints the one-time enrollment URL to stdout. It rides the same `invite.mint` operation, `auth.manage_users` capability, and human-assignable-role guard (`req-tap-auth-roles`) as every other mint; a non-human-assignable role (e.g. `tap_bootloader`/`tap_cares.*`) is refused. **`enroll-admin` is retained as documented sugar for `enroll-user --role tap_admin`**, exactly mirroring the base spec's `initial_admins` = `initial_grants[…tap_admin]` fold (`req-tap-auth-boot`), so genesis (`req-tap-auth-passkey-genesis`) and dev replay (`req-tap-auth-passkey-dev-bootstrap`) keep their `enroll-admin` spelling. The role is an argument; the secret is never an argument (it only transits stdout via `--print-token`, per token hygiene above) — so `ps`/argv never expose it. This keeps a single shell enrollment chokepoint, is scriptable/AI-operable (Player-3 legibility), and fits the shell-is-root-of-trust posture where the operator's primary admin surface is the shell.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-enrollment-1 | Gated Creation | Proposed | A user/passkey can be created only by redeeming a valid, unexpired, unconsumed invitation (or genesis). | |
| req-tap-auth-passkey-enrollment-2 | Token Hygiene | Proposed | Tokens use a public-id/secret split, CSPRNG ≥128-bit, single-use, hashed-at-rest with a **plain SHA-256/512 + constant-time compare** looked up by public-id, TTL'd with an **enforced maximum**, and consumed atomically (`rowcount==1`-guarded transition); a failed ceremony leaves the token `pending`. | |
| req-tap-auth-passkey-enrollment-3 | Identity & Grant Bound | Proposed | Redemption applies only the invited identity, grants, and handle **from the server-stored invitation** (client-supplied identity fields ignored); non-human-grantable roles are refused. | |
| req-tap-auth-passkey-enrollment-4 | No Email | Proposed | Tokens are displayed in admin UI / `manage.py` only; TAP sends no invitation email; the `--print-token` stdout exposure is named. | |
| req-tap-auth-passkey-enrollment-5 | Audited | Proposed | Mint/redeem/revoke are capability-gated and produce structured audit records. | |
| req-tap-auth-passkey-enrollment-6 | Non-Enumerating Redemption & Secret-In-Fragment | Proposed | All redemption failures collapse to one generic constant-time response; the enrollment page carries `no-store`/`noindex`/`no-referrer`; the secret rides the URL **fragment** (never path/query) so it never reaches a server log, and the redeem POST body is never logged. | |
| req-tap-auth-passkey-enrollment-7 | Shell Mint Command | Proposed | `manage.py enroll-user --email … --role … --print-token` mints an invitation for any human-assignable role from the shell (non-human roles refused); `enroll-admin` is retained as sugar for `--role tap_admin`; the role is an argument, the secret never is. | |

---

### Genesis Bootstrap
----
RID: `req-tap-auth-passkey-genesis`  
Status: `Proposed`

A fresh instance has no users and no prior trust anchor, so the **first** passkey MUST be enrollable out-of-band via `manage.py` — the same shell floor that anchors recovery. This is genesis: shell is the root of trust. It is the production first-login path.

#### Production first-login (normative walkthrough)

1. Operator stands up the instance; zero users exist.
2. Operator runs `manage.py enroll-admin --email me@example.com --print-token` (or the command reads the profile's `initial_admins`). It mints a genesis invitation (`req-tap-auth-passkey-enrollment`) and **prints the one-time enrollment URL to stdout** — never email.
3. Operator opens the URL in a browser within the TTL; the WebAuthn **registration** ceremony runs (discoverable + UV required); the token is consumed atomically at bind; the admin user + first passkey are created and grants applied.
4. Operator is logged in — passwordless, no IdP, no email, no password. The BE-aware backup nudge (`req-tap-auth-passkey-recovery`) follows.

#### Implementation

- **Disposable genesis admin** (Keycloak `bootstrap-admin` / Vault "bootstrap then retire" pattern): the genesis admin is a normal `tap_admin`, but the design treats it as replaceable — nothing depends on *that specific* admin persisting, so it can be rotated/retired once another admin exists, without special-casing.
- **`initial_grants` as invitation source** — on first boot the declarative `email → roles` map (`req-tap-auth-boot`) MAY mint pending invitations. The declarative grant machinery carries over unchanged, producing enrollment tokens instead of gating an IdP login.
- **Zero-provider boot validation** — the last-admin invariant (never converge to zero active human `tap_admin`) is satisfied by a reachable admin path: an active human admin, **or** a pending admin invitation, **or** the always-available `manage.py` genesis path. A passwordless deployment with no active admin and no pending admin invitation MUST boot with a loud warning directing the operator to run genesis — never silently unreachable, and never requiring a federated provider to satisfy the invariant.
- Genesis is a registered boot/system surface (`tap_boot.enroll_admin` / `tap_auth.genesis`), run as a named actor.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-genesis-1 | Shell Genesis | Proposed | `manage.py enroll-admin --print-token` mints a first-admin enrollment on an instance with zero users, printing the URL to stdout. | |
| req-tap-auth-passkey-genesis-2 | Grants As Invitations | Proposed | First boot can mint pending invitations from `initial_admins`/`initial_grants`. | |
| req-tap-auth-passkey-genesis-3 | Zero-Provider Invariant | Proposed | The last-admin invariant is satisfiable with no federated provider; a no-admin/no-invitation boot warns loudly, never silently unreachable. | |
| req-tap-auth-passkey-genesis-4 | Named Surface | Proposed | Genesis runs as a named system actor through a registered surface. | |

---

### Dev Bootstrap (Spawn Passkey Replay)
----
RID: `req-tap-auth-passkey-dev-bootstrap`  
Status: `Proposed`

The multi-session spawn machinery MUST let a developer reuse one existing passkey across every freshly-spawned instance without re-running the registration ceremony each time. This supersedes the password-based spawn admin bridge (`req-dev-multisession-admin-bootstrap`) and makes the dev loop exercise the real passkey path.

The correction that makes this safe: **TAP exports only the public credential record; private key material is never exported by TAP and remains under the authenticator / platform or its sync fabric.** (Passkeys are not uniformly non-exportable device-bound keys — a backup-eligible credential may sync across the operator's devices via iCloud Keychain / Google Password Manager; the point is that TAP never touches the private half either way.) What spawn reuses is the public record (not a secret); the operator's device supplies the private half at login with one local gesture. Only public material moves — strictly safer than the admin *password* it replaces.

#### Implementation

- **Dev RP-ID / origin is `localhost`, not the labeled host.** Multi-session's normal URL is `http://<name>.tap.localhost:<port>/`, but WebAuthn's http secure-context carveout is specifically host `localhost` (browser support for `*.localhost` as a trustworthy origin varies), and RP-ID = `localhost` is only unambiguously a valid registrable suffix of a `localhost` origin. So in v0 the passkey ceremony (register **and** login) MUST run on the direct `http://localhost:<WEB_PORT>/` origin (each session has a distinct `WEB_PORT`; `localhost` MUST be in `ALLOWED_HOSTS`), with **RP-ID = `localhost`**. Because RP-ID scoping ignores port, one `localhost` credential is then valid against every session's stack — and because RP-ID `localhost` collapses *every* local service into one RP scope, each session MUST enforce its **own exact expected origin** (`http://localhost:<its own WEB_PORT>`, taken from that session's `.env.local`), never an any-`localhost` allowlist and never an origin baked into the shared record. That server-side exact-origin check is the only thing preventing a co-resident malicious `localhost:<other>` service from real-time-relaying a TAP-challenge assertion back to TAP; broadening `expected_origin` to make one shared record "just work" across ports would open that relay. The `localhost` RP-ID is itself a footgun (any local service can request an assertion for this credential), so the dev replay credential SHOULD be a dedicated/throwaway authenticator and MUST NOT be reused as a production credential. Passkey login over the labeled `*.tap.localhost` host is out of scope for v0 and would require HTTPS + a deliberate RP-ID strategy (Backlog: multi-host RP-ID).
- **Register once, export the public record.** The operator runs the production registration once on `http://localhost:<WEB_PORT>/` (RP-ID `localhost`); TAP exports the **public** credential record — credential id, COSE public key, sign count (`0`; platform passkeys report 0), AAGUID, transports, RP-ID, expected-origin policy, and a **fixed dev user handle** — to a schema-validated file under `~/tap-secrets/auth/` (already symlinked into every session). **Confidentiality of this file is low-stakes** (the private key is never in it, so *reading* it grants nothing — `req-tap-auth-passkey-dev-bootstrap-1`), **but its *integrity* is load-bearing.** Import substitutes file integrity for the registration ceremony's proof-of-possession — there is no attestation and no challenge-response at import proving anyone holds the private key — so whoever controls the file's *bytes* controls which public key becomes admin. A process that can write `~/tap-secrets/auth/` (a sibling session, or any local process) could swap in an attacker-controlled `{credential_id, public key, handle}`; the next import would bind it, and the attacker's *own* remote authenticator would then complete a valid assertion as admin — a durable remote admin login reached later with no box access. Schema validation checks *shape, not authenticity*, and does not defend this. The record MUST therefore be integrity-protected: an operator-owned directory + `0600` file perms with the sole-owner assumption **named** as the load-bearing mitigation, and/or a `sha256`-in-trusted-referrer binding mirroring the boot-record integrity pattern (`tap/boot_records.py`). Blast radius is dev-only (the allowlist prod gate below refuses import outside a dev/local profile), but a dev-session admin holds real `~/tap-secrets` cloud secrets, so the edge is named, not waved off.
- **Exported-record schema.** The dev passkey record is a new on-disk structured format, so it MUST have a JSON Schema under `tap_auth/schemas/` with a loader that validates on import (TAP's structured-data convention). The schema pins: `version`, RP-ID (`localhost`), the **expected-origin policy — which records that the login origin is resolved *per importing session* as `http://localhost:<WEB_PORT>` (exact, incl. port) and is NOT a wildcard baked into the shared record**, fixed-user-handle encoding, credential-id / public-key encodings, sign-count semantics, BE/BS/AAGUID/transports, and the dev-only import guard — each field described. The loader validates *shape*; record *integrity* is guarded separately (see the export bullet above) because schema validity does not imply authenticity.
- **Replay every spawn.** The spawn bootstrap step runs `manage.py enroll-admin --import-dev-passkey`, which validates + loads the record, seeds the admin with the fixed dev user handle, and imports the public record — binding the operator's existing `localhost` passkey to the fresh instance with **no registration ceremony**. The fixed dev user handle MUST match the discoverable credential on the authenticator for autofill to resolve consistently.
- **Login** is the real ceremony: conditional-UI autofill offers the passkey → one local gesture → in.
- **Same command, two modes** — `enroll-admin` supports `--print-token` (production interactive registration) and `--import-dev-passkey` (dev replay). The genesis surface is identical, so nothing dev-only diverges from the real security model.
- **Not a production bypass — allowlist gate, fail closed on ambiguity.** `--import-dev-passkey` is dev/test-only and MUST be **permitted only when the boot profile is *explicitly* classified `dev/local`** — an allowlist, not a denylist. "Refused under a customer/deploy profile" is insufficient on its own: an unclassified, unknown, future, or typo'd profile kind is *not* customer/deploy, so a denylist-shaped guard would wrongly permit it. The guard MUST refuse on any missing/unknown/ambiguous classification (fail closed). It is **never keyed off `DEBUG`**, which per `spec-tap-auth-v0.md` may legitimately be `True` in a non-test instance and must not imply test-only behavior. `TAP_TEST_MODE`, where used, is an **additional AND-narrowing** condition — never an independent enabler: a stray or attacker-set `TAP_TEST_MODE=1` env var MUST NOT enable dev import on a profile that is not itself dev/local-classified. The gate lives on the `--import-dev-passkey` flag handler and is re-evaluated on every invocation, so sharing the `enroll-admin` command across its two modes carries no extra risk (reaching the flag already requires shell, the root of trust). Refusal surfaces as an `exemption_not_allowed`-class assurance case. The fully-headless escape hatch for CI / `drive-browser` (mint a Django session cookie directly) remains, scoped to automated/headless only; interactive dev keeps the one-gesture passkey login so dev never drifts from prod. **This import path creates an admin and binds a credential with zero proof-of-possession and no human interaction, so its entire trust basis is exactly two guards — record integrity (`req-tap-auth-passkey-dev-bootstrap-8`) and this allowlist gate — both load-bearing, neither incidental.**

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-dev-bootstrap-1 | Public-Only Replay | Proposed | Only the public credential record is exported/replayed; no private key material moves. | |
| req-tap-auth-passkey-dev-bootstrap-2 | Replaces Password Bridge | Proposed | Spawn seeds the admin via passkey replay, not a Keychain/env password + `createsuperuser`. | |
| req-tap-auth-passkey-dev-bootstrap-3 | One Passkey, Many Sessions | Proposed | A single `localhost` passkey logs into every spawned session without re-registration, via the `http://localhost:<WEB_PORT>/` origin. | |
| req-tap-auth-passkey-dev-bootstrap-4 | Prod Fail-Closed (Allowlist) | Proposed | `--import-dev-passkey` is permitted **only** under an explicitly `dev/local`-classified profile and refused on any missing/unknown/ambiguous classification; `TAP_TEST_MODE` is AND-narrowing, never an independent enabler; never keyed off `DEBUG`. | |
| req-tap-auth-passkey-dev-bootstrap-5 | Real Path In Dev | Proposed | Interactive dev login uses the real passkey assertion (session-cookie mint is automated/headless only). | |
| req-tap-auth-passkey-dev-bootstrap-6 | Exact Per-Session Origin | Proposed | Dev register/login run on `http://localhost:<WEB_PORT>/` with RP-ID `localhost`, and each session enforces its **own exact** origin (incl. port) — never an any-`localhost` wildcard; the labeled `*.tap.localhost` host is not used for passkey login in v0. | |
| req-tap-auth-passkey-dev-bootstrap-7 | Record Schema | Proposed | The exported dev passkey record validates against a JSON Schema under `tap_auth/schemas/` on import. | |
| req-tap-auth-passkey-dev-bootstrap-8 | Record Integrity | Proposed | The exported record is integrity-protected (operator-owned dir + `0600`, and/or `sha256`-in-trusted-referrer); a tampered record cannot inject an attacker credential as admin. Confidentiality is low-stakes; integrity is load-bearing. | |

---

### Native Identity & Credential Projection
----
RID: `req-tap-auth-passkey-identity`  
Status: `Proposed`

A passkey-native human has **no `ExternalIdentity` row** — the `User` is the identity anchor and the passkey is the proof. Enrollment state MUST be queryable so a human or AI operator can reason about coverage and recovery risk, and authenticator characteristics MUST be recorded at bind (NIST 800-63B-4).

#### Implementation

- Native users carry no `(provider_id, subject)` external link; the `req-tap-auth-external-identity` linking-disabled rules apply only to federated logins. A user MAY hold both a federated identity and passkeys.
- **`WebAuthnCredential` projection** — a TAP-side, queryable model of each stored passkey (design-referenced from `django-otp-webauthn`; the same pattern by which `Capability` projects the code registry). Described fields: owning user, opaque user handle, credential id (redacted for display/logging), public key, sign count, AAGUID (best-effort under `attestation=none` — frequently all-zeros for roaming authenticators; all-zeros is queried as *unknown*, not a distinct model), transports, device label, created / last-used, and the **BE/BS flags (synced vs device-bound)** — each with a description so the projection is legible to an AI operator (`spec-ai-integration.md`). The device-bound-vs-synced determination rides the reliable BE/BS flags, **not** the AAGUID, so the recovery-risk queries below hold even when the AAGUID is zeroed.
- **Record characteristics at bind** (NIST): store whether the authenticator is phishing-resistant (always true for WebAuthn+UV), single- vs multi-factor, and syncable (BE) vs device-bound — so a verifier/operator can reason about AAL and recovery risk. Note: **syncable passkeys are AAL2-only**; the credential model MUST be shaped so a future **AAL3 tier** (device-bound hardware + enforced authentication intent) is addable without a schema rewrite.
- The projection answers operator/AI questions directly: who is passkey-only, who is still password/IdP-only, who has exactly one credential (recovery risk), who holds only a device-bound (BE=0) credential. v0 exposure is read-only and internal (no core-graph write).
- Credential enrollment/removal is capability-gated and audited; removing a user's last credential is a recovery-relevant event and is logged as such.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-identity-1 | No External Row | Proposed | A passkey-native user has no `ExternalIdentity`; the User is the anchor. | |
| req-tap-auth-passkey-identity-2 | Queryable Projection | Proposed | Each passkey has a described `WebAuthnCredential` projection row incl. BE/BS/AAGUID, queryable from the DB/service layer. | |
| req-tap-auth-passkey-identity-3 | Characteristics At Bind | Proposed | Phishing-resistance / factor / syncable characteristics are recorded at registration; the model leaves room for a future AAL3 tier. | |
| req-tap-auth-passkey-identity-4 | Recovery-Risk Legible | Proposed | The projection distinguishes synced vs device-bound and surfaces single-credential users. | |
| req-tap-auth-passkey-identity-5 | Safe Display | Proposed | Credential identifiers are redacted in logs/UI; raw material is not duplicated. | |

---

### Recovery Floor & Password Retirement
----
RID: `req-tap-auth-passkey-recovery`  
Status: `Proposed`

In passwordless-primary mode there is exactly **one** break-glass floor: out-of-band `manage.py` / shell. Passwords retire from the routine surface, including Django admin. This supersedes `req-tap-auth-policy-6` and revises `req-tap-auth-local`.

#### Implementation

- **Password retirement** — for a passwordless deployment, `TAP_LOCAL_PASSWORD_ENABLED` defaults off; local password login is blocked everywhere including Django admin (the existing toggle + backends are the mechanism). Dev MAY re-enable it explicitly and loudly. A **customer/deploy profile MUST refuse `TAP_LOCAL_PASSWORD_ENABLED=true`** (fail closed) — the same profile-class guard the dev passkey-import path gets (`req-tap-auth-passkey-dev-bootstrap-4`) — so a weak password backend is reachable only under an explicitly dev/local-classified profile, never one flag away on a deployment. Retiring passwords does not deactivate users.
- **Retire the password *surface*, not just the login form.** Disabling password *login* is necessary but not sufficient — the residual Django/allauth password-*mutation* endpoints can re-introduce a usable credential out of band and MUST be closed in passwordless mode:
  - `django.contrib.auth`'s `PasswordResetView`/`PasswordChangeView` and allauth's `account_reset_password`/`account_change_password`/`account_set_password` are unmounted. In the coexist build (slim Phase A, allauth present) these routes are live even with `TAP_LOCAL_PASSWORD_ENABLED` off unless the toggle also gates URL mounting.
  - passkey-native users are created with `set_unusable_password()` — a `User` with an empty/reset-capable password is a latent re-enablement target.
  - `ModelBackend` is **removed** from `AUTHENTICATION_BACKENDS` (not merely the form hidden), so `POST /admin/login/` is *refused*, not just visually redirected. `createsuperuser` still mints password-capable staff accounts and is understood as a shell-floor tool, not a routine surface.
- **Credential revocation terminates its live sessions.** In passwordless mode Django's `get_session_auth_hash()` is HMAC'd over the (now static/unusable) password field, so it never rotates when a passkey is added or revoked — meaning revoking a credential does **not**, by itself, invalidate sessions already established with it. TAP MUST therefore explicitly terminate the sessions bound to a revoked credential — on rebind **and** on any credential removal — so a lost/compromised passkey (or a transient attacker enrollment) cannot retain a live session after its credential is gone. Implemented via credential↔session linkage or a per-user auth-hash salt whose rotation invalidates, composed with the existing per-user session invalidation (`req-tap-auth-sessions`).
- **Django admin under retirement** — an unauthenticated `/admin/` MUST be fronted by the passkey login flow (redirect to passkey login; `is_staff`/`is_superuser` still gate admin), not a dead password form. Superuser-is-god at the Django level is unchanged in *capability*; the *credential* to reach that session is now a passkey or shell. `policy.can` continues to ignore `is_superuser` for TAP service authZ.
- **Recovery is uniformly shell, and is a *rebind* not a resurrect** (NIST): lost/all-passkeys-gone → another admin re-invites, or `manage.py` mints a fresh enrollment → the operator **registers a new passkey and the old credential is revoked**; the lost credential is never resurrected. No password fallback, no email reset. `manage.py` is always reachable in v0/v1 single-tenant operation and is the dependable floor. NIST frames binding a *replacement* authenticator as an event that must itself meet the account's assurance; shell/`manage.py` genesis is equal-or-higher assurance (the out-of-band root of trust), so the rebind satisfies that requirement rather than weakening it.
- **Shell-assumption trigger.** The shell-only floor is valid *only while out-of-band shell / `manage.py` access is genuinely assumed* (v0/v1 single-tenant, operator-owned). In that world recovery *is* the operator running `manage.py` themselves, or — in a small multi-admin instance — calling another admin who mints a fresh enrollment by hand; that is sufficient by design, not a stopgap. A genuinely **no-shell-access, multi-user field deployment** MUST NOT ship on shell-only recovery: it is the promotion trigger for `emergency_only` local auth (the `spec-tap-auth-v0.md` Backlog path) and/or recovery/backup codes (Backlog below). This is named so the floor is not silently relied on where it does not hold.
- **Named terminal risk (honest-risk doctrine).** The shell/`manage.py` floor is a *deployment property TAP cannot itself enforce or detect*, so exactly one convergence-to-zero sequence exists and is **accepted in v0 rather than hidden**: a *sole* admin who loses their only passkey **and** simultaneously lacks shell/`manage.py` access (e.g. a PaaS / managed-container deploy where exec is disabled or ephemeral) reaches a permanently-unreachable instance — data intact, no admin path, no self-service recovery. v0 accepts this as the cost of one-root-of-trust simplicity for the operator-owned target, mitigated by permitting N passkeys and the BE-aware backup nudge. It is deliberately **not** bought back with backup codes in v0/v1: codes are the wrong tool while the operator holds their own shell (and an on-call admin covers the small multi-admin case), and they earn their place only when the no-reliable-shell, multi-user field deployment above becomes real — the same trigger that promotes `emergency_only` local auth.
- **Single passkey allowed; permit N; nudge BE-aware** — a user MAY operate with one passkey (locked decision), and TAP MUST NOT block on a second. But TAP MUST **permit multiple** passkeys per user (the industry recovery mechanism, free and email-free), and after first enrollment SHOULD nudge a backup — **escalated** (firmer than a soft nudge) when the credential is device-bound (BE=0, no sync safety net) and kept soft when synced (BE=1). The nudge MUST point at a real v0 action — **authenticated self-add** (`req-tap-auth-passkey-webauthn-15`) — not a Backlog UI, so it is actionable the moment it fires.
- **Named accepted-risk** (`spec-security-posture.md` honesty): defaulting to a single passkey runs against a FIDO/NIST *SHOULD* ("maintain ≥2 authenticators") and against every system surveyed, which treat a second credential as *the* recovery path. It is accepted in v0 as the cost of one-root-of-trust simplicity, mitigated by (a) permitting N passkeys, (b) the BE-aware nudge, and (c) an equal-or-higher-assurance shell recovery floor (which FIDO sanctions as legitimate re-onboarding). The residual risk — a sole admin with a single device-bound passkey on a lost device — drops to shell; this is named, not hidden.
- Every recovery / genesis / weaker-factor event is audited (actor, scope, target, reason).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-recovery-1 | Passwords Retired | Proposed | Passwordless deployments disable local password login everywhere including admin by default. | |
| req-tap-auth-passkey-recovery-2 | Admin Fronted | Proposed | Unauthenticated `/admin/` routes to passkey login; staff/superuser still gate admin. | |
| req-tap-auth-passkey-recovery-3 | Shell-Only Rebind | Proposed | Recovery is `manage.py`/admin re-invite only, and registers a new passkey + revokes the old; no password or email reset exists. | |
| req-tap-auth-passkey-recovery-4 | Single OK, Permit N, BE-Nudge | Proposed | Enrollment completes with one passkey; multiple are permitted; the backup nudge escalates for device-bound (BE=0) credentials. | |
| req-tap-auth-passkey-recovery-5 | Invariant Held & Risk Named | Proposed | No boot/config converges to no reachable admin path *given the shell assumption*; the single-passkey default and the sole-admin-no-shell terminal-brick sequence are recorded as named accepted-risks (backup codes stay backlogged to the multi-user-field trigger). | |
| req-tap-auth-passkey-recovery-6 | Revocation Kills Sessions | Proposed | Revoking a credential (rebind or removal) explicitly terminates the sessions bound to it; the passwordless `get_session_auth_hash` gap is closed via credential↔session linkage or auth-hash-salt rotation. | |
| req-tap-auth-passkey-recovery-7 | Password Surface Closed | Proposed | Password mutation/reset endpoints are unmounted, passkey-native users get `set_unusable_password()`, and `ModelBackend` is removed so `POST /admin/login/` is refused (not merely redirected). | |

---

### Passkey AuthN Assurance
----
RID: `req-tap-auth-passkey-assurance`  
Status: `Proposed`

The passkey method MUST ship its own AuthN assurance **test cases** so a change to passkey auth is reviewable and regression-guarded. This is defined **directly and capability-centrically here** — it does **not** depend on `spec-tap-auth-assurance-v0.md` (retired) or its never-built, surface-centric `authn_providers.<type>.json` artifact. The *runtime* self-check is already the method-registry `self_test` (`req-tap-auth-passkey-methods`), mirroring federated providers' `self_test` (`req-tap-auth-providers`); this requirement adds the *build-time* complement — a described, fail-closed passkey ceremony test corpus. It is the first instance of the capability-centric assurance test-corpus backlogged in `spec-tap-auth-v0.md`.

#### Implementation

- A described, **schema-validated passkey assurance case file** under `tap_auth/` (e.g. `tap_auth/passkey/assurance_cases.json`, validated by a loader at test-collection time) declares allow/deny cases covering at minimum:
  - enrollment **gating** — creation without a valid invitation/genesis is refused;
  - invitation **replay** and **expiry** — a consumed or expired token is refused;
  - **user-verification-required** — an assertion lacking UV is refused, **asserted against the verify call** (`require_user_verification=True`), not merely the options request (`req-tap-auth-passkey-webauthn-3`);
  - **sign-counter regression** — an assertion presenting a regressed counter is flagged as a clone signal; the `0/0` no-counter case is accepted (`req-tap-auth-passkey-webauthn-8`);
  - **discoverable-credential** usernameless login succeeds for an enrolled user; a mismatched `userHandle`↔credential owner is refused (`req-tap-auth-passkey-webauthn-10`);
  - **RP-ID/origin mismatch** — an assertion for the wrong or non-exact origin is refused (the phishing-resistance assertion), including an any-`localhost` wildcard (`req-tap-auth-passkey-webauthn-7`);
  - **session-fixation** — the session key is cycled on a successful assertion (login finalized via `auth.login()`, `req-tap-auth-passkey-webauthn-11`);
  - **ceremony CSRF** — a ceremony/redeem POST without a valid CSRF token is refused (`req-tap-auth-passkey-webauthn-12`);
  - **lost-device / recovery** — rebind (new passkey + old revoked), single-credential removal behavior, and that revocation **terminates the credential's live sessions** (`req-tap-auth-passkey-recovery-6`);
  - **dev-import refused outside dev/local** — `--import-dev-passkey` is permitted only under an explicitly `dev/local`-classified profile and fails closed on any missing/unknown/ambiguous classification (`req-tap-auth-passkey-dev-bootstrap-4`); a tampered/integrity-failed record is refused (`req-tap-auth-passkey-dev-bootstrap-8`).
- A fail-closed test loads and exercises these cases; enabling the passkey method without its assurance cases fails the relevant tests (the harness refuses to green on missing coverage). The runtime method-registry `self_test` (`req-tap-auth-passkey-methods`) is the complementary live check.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-assurance-1 | Method Assurance File | Proposed | A described, schema-validated passkey assurance case file exists under `tap_auth/` and is exercised by a fail-closed test (capability-centric; not dependent on the retired surface-centric assurance spec). | |
| req-tap-auth-passkey-assurance-2 | Gating & Replay Covered | Proposed | Enrollment gating, token replay, and expiry have deny cases. | |
| req-tap-auth-passkey-assurance-3 | Ceremony & Phishing Covered | Proposed | Verify-time UV, sign-counter regression, exact RP-ID/origin mismatch (incl. any-`localhost` wildcard), and `userHandle`↔owner-mismatch denials are asserted. | |
| req-tap-auth-passkey-assurance-4 | Dev Bypass Fail-Closed | Proposed | The dev passkey-import path is asserted to fail closed outside an explicit `dev/local` profile (allowlist, ambiguity-refused) and to refuse a tampered/integrity-failed record. | |
| req-tap-auth-passkey-assurance-5 | Fail-Closed On Missing | Proposed | Enabling the passkey method without assurance rows fails tests. | |
| req-tap-auth-passkey-assurance-6 | Session Controls Covered | Proposed | Session-fixation (key cycled on login), ceremony CSRF, and revocation-terminates-sessions each have an asserted case. | |

---

### Rollout
----
RID: `req-tap-auth-passkey-rollout`  
Status: `Proposed`

Two intertwined axes: **feature phases** (what works) and **slim-install phases** (how lean). The feature work lands first with both stacks installable (Phase A); the dependency slimming (Phase B) follows, because it carries the harder refactor (import isolation + TAP-owned login scaffolding) and must not block a working passwordless demo.

#### Implementation

**Feature phases:**
1. **Foundation** — login-methods registry (`req-tap-auth-passkey-methods`); native `py_webauthn` passkey method + ceremony (`req-tap-auth-passkey-webauthn`); `WebAuthnCredential` projection (`req-tap-auth-passkey-identity`); passkey enrollment **from an already-authenticated session**. No change to existing federated login.
2. **Bootstrap** — `Invitation` chokepoint (`req-tap-auth-passkey-enrollment`); `manage.py enroll-admin` genesis + zero-provider boot validation (`req-tap-auth-passkey-genesis`); dev spawn passkey-replay (`req-tap-auth-passkey-dev-bootstrap`); assurance rows (`req-tap-auth-passkey-assurance`). A sole-passkey instance can now stand up and admit users with no IdP.
3. **Passwordless front door + retirement** — passkey as a primary login method on the login page; retire passwords including admin and front `/admin/` (`req-tap-auth-passkey-recovery`); apply the `req-tap-auth-policy-6` supersession in `spec-tap-auth-v0.md`.

**Slim-install phases (`req-tap-auth-passkey-slim-install`):**
- **Phase A — both installable, config-selects.** allauth + the passkey stack can coexist; the boot profile selects the active method(s). Passwordless works end-to-end. Cheapest path to a working demo.
- **Phase B — allauth optional, passkey-only lean.** Move allauth to the `federated` extra; conditional `INSTALLED_APPS`; import isolation; TAP-owned login/logout scaffolding for the no-allauth build; lean-boot gate. A passkey-only install no longer has allauth on disk — the security signal is realized.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-auth-passkey-rollout-1 | Foundation First | Proposed | Feature Phase 1 lands with no change to existing federated login behavior. | |
| req-tap-auth-passkey-rollout-2 | Bootstrap Stands Alone | Proposed | After feature Phase 2 (slim Phase A), a zero-provider sole-passkey instance bootstraps and admits users. | |
| req-tap-auth-passkey-rollout-3 | Retirement Reconciled | Proposed | Feature Phase 3 applies the `req-tap-auth-policy-6` supersession in the auth spec in the same change. | |
| req-tap-auth-passkey-rollout-4 | Lean Payoff | Proposed | After slim Phase B, a passkey-only install has allauth neither installed nor imported. | |

## Approved Dependencies

This spec approves adding **`py_webauthn`** (PyPI distribution `webauthn`, Duo Labs; `>=3`) for the passkey implementation path, subject to implementation-time version selection and ordinary dependency review. It is the passkey path's **only** new runtime dependency (the crypto ceremony core; TAP owns everything above it). `django-allauth` is not newly introduced here — it is the existing federated-path dependency (approved in `spec-tap-auth-v0.md`), and this spec only re-scopes it from a core dependency to the `federated` extra (`req-tap-auth-passkey-slim-install`). `django-otp-webauthn` is a **design reference only** and MUST NOT be added as a dependency.

## Backlog

Security-relevant, intentionally out of v0 scope, kept visible:

- **Recovery/backup codes (v1+, multi-user-field-triggered — deliberately NOT v0).** The standard offline, phishing-channel-free *self-service* recovery companion to shell recovery (store hashed, show once, regenerate). Explicitly deferred: in v0/v1 single-tenant, operator-owned deployment the recovery path *is* out-of-band `manage.py` — the operator resets their own enrollment, or a second admin mints a fresh one by hand (you call your administrator; that is what administrators are for) — and that is sufficient by design. Backup codes earn their place only once TAP supports **multi-user environments in the field**, where neither the operator's own shell nor an on-call admin is a safe assumption; that is the trigger to promote this, alongside the `emergency_only` local-auth path in `spec-tap-auth-v0.md`. See the `req-tap-auth-passkey-recovery` named terminal risk.
- **Email/self-service invitation delivery** — only if a deployment needs onboarding without an operator hand-carrying tokens; reintroduces email as a bootstrap/phishing surface, deliberately deferred.
- **Attestation-based authenticator policy** — require hardware/FIPS/enterprise authenticators via attestation + AAGUID allowlisting; v0 accepts `none` (which is exactly why v0 AAGUID capture is best-effort and often all-zeros — reliable make/model identification and allowlisting need `direct`/enterprise attestation).
- **AAL3 device-bound tier** — device-bound (non-syncable) passkeys + enforced authentication intent for a higher-assurance tier; the credential model reserves room (`req-tap-auth-passkey-identity`).
- **Federated-claim → passkey enrollment fast-path** — in a mixed deployment, let an IdP login auto-open a passkey enrollment.
- **Add-a-device via additive credential enrollment (admin `manage.py` first; self-service UI later).** Adding a *second device* to an existing account is the enrollment invitation generalized to an **additive target**: an admin-issued link — via `manage.py enroll-user` when the email resolves to an *existing* user — that **adds** a passkey to that user (keep-and-add), distinct from create-a-user redemption *and* from recovery-rebind (which replaces + revokes). It reuses the full token discipline (`req-tap-auth-passkey-enrollment`) and applies **no new grants** (the user keeps their existing role). Security note: an additive link is a *credential-addition* capability — misdelivery is account takeover — so it carries the same short-TTL, single-use, hand-carried-out-of-band discipline as the create link, and each addition is audited as a security-relevant event. **First implementation is the `manage.py` admin affordance only** (demand-gated, no web UI): an operator runs it at a user's request, or self-exercises it to hold multiple passkeys on a persistent instance (the `req-tap-auth-passkey-recovery` permit-N path). The complementary no-new-credential path is cross-device/hybrid login (`req-tap-auth-passkey-webauthn`). The self-service page to do this *without* an admin is the Passkey management UI below.
- **Passkey management UI** — self-service page to name/list/revoke one's passkeys, consuming the projection.
- **Step-up / re-auth on sensitive actions** — require a fresh passkey assertion before `grid.purge` / `auth.manage_users`.
- **RP-ID strategy for multi-host / future multi-tenant** — origin-binding beyond single-domain single-tenant.
- **Time-boxed web genesis** — if a web first-run wizard is ever added, time-box the claim window (Portainer pattern) to close the first-visitor race that shell genesis avoids by construction.
