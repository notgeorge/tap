---
title: Google OIDC Login — Go-Live Checklist
date: 2026-06-25
status: how-to
audience:
  - developer
  - operator
related_specs:
  - tap_auth/specs/spec-tap-auth-v0.md
related_docs:
  - docs/misc/doc-auth-per-app-standards.md
---

# Google OIDC Login — Go-Live Checklist

How to take a TAP instance from "authN code is built" to "a real person logs in
with Google." The code path (allauth + `google_oidc` provider + the TAP security
adapter + boot wiring) is built, tested, and live-verified up to the redirect to
Google; the only step a browser/human must complete is the consent round-trip.

## What's already done

- allauth + `/auth/` routes, the default-deny login wall, the no-access page.
- The `google_oidc` provider, the security adapter (verified-email / `hd`-domain /
  `allowed_emails` / linking-disabled), `ExternalIdentity`, gated provisioning,
  initial-admin-on-first-login.
- The `operator_sso` boot profile (`boot/operator_sso.boot.json`) wiring the
  `example-google` provider pinned to `operator@example.com`.
- The secret `~/tap-secrets/auth/example-google.secret.json` (your real
  Google client id/secret), schema-validated.
- Live-verified: `manage.py auth_selftest --live` PASSes (incl. real Google
  discovery), and login-initiation redirects to `accounts.google.com` with the
  right client id / redirect uri / scope.

## In the Google Cloud Console (one-time, if not already done)

The OAuth client you created must have this **authorized redirect URI** for the
local stack (port 8010 for the `boot` session):

```
http://localhost:8010/auth/oidc/example-google/login/callback/
```

- Consent screen: **Internal** (restricts to example.com + guarantees the
  returned `hd` claim).
- Scopes: `openid`, `email`, `profile` (non-sensitive — no Google review needed).
- For a deployed instance, add `https://<host>/auth/oidc/example-google/login/callback/`.

## Wire the running server to the profile

The running web server reads providers from its `TAP_BOOT_PROFILE`. For the local
browser smoke, point this session's stack at the `operator_sso` profile and set the
base URL (used for self-test/callback display):

```bash
# in .env.local (this session) — or export before `scripts/dc up`
TAP_BOOT_PROFILE=operator_sso
TAP_BASE_URL=http://localhost:8010
```

Then restart web: `scripts/dc restart web`. Confirm the provider is wired:

```bash
scripts/dc exec web uv run python manage.py auth_selftest --live   # all PASS
```

> Dev note: with `DEBUG=True` the boot deploy-posture gate is relaxed (logged, not
> enforced) and provider self-tests run offline at boot. A real deploy
> (`DEBUG=False`) enforces both, and `local_password_enabled` can flip to `false`
> in the profile once Google login is confirmed.

## The browser smoke

1. Open `http://localhost:8010/` → you're redirected to `/auth/login/`.
2. The login page shows the **example.com (Google)** button (POST-only —
   `SOCIALACCOUNT_LOGIN_ON_GET=False`).
3. Click it → Google consent → back to the callback.
4. The TAP adapter runs: verified email + `hd=example.com` + `george@` on the
   allowlist → allowed → a user is provisioned, an `ExternalIdentity` is written,
   and because `operator@example.com` is in `auth.initial_admins`, the user is
   added to `tap_admin`. (`initial_admins` is sugar for the general
   `auth.initial_grants` email→role map; e.g. `{"sam@example.com": ["tap_viewer"]}`
   admits a read-only guest. Only human-assignable roles — `tap_admin`,
   `tap_viewer` — may be granted this way; see `req-tap-auth-roles`.)
5. You land on `/` as a named, authenticated admin.

### Expected denials (try them to see the security adapter work)

- A `example.com` account NOT on `allowed_emails` → `account_not_allowlisted`.
- A non-`example.com` Google account → `domain_not_allowed`.
- Each shows a specific page (not an opaque error) and logs a structured security
  event with a redacted subject.

## Operating levers

- **Disable local password login** (once Google is the path): set
  `auth.local_password_enabled: false` in the profile. Blocks password login
  everywhere incl. Django admin; does NOT deactivate users or kill sessions.
  Recovery floor is out-of-band shell/management-command access.
- **Invalidate sessions** (incident response):
  `manage.py auth_sessions --as-user <admin> --user <target>` (or `--all` /
  `--session-key <key>`). Capability-gated (`auth.manage_sessions`), audited.

## Troubleshooting

- `redirect_uri_mismatch` from Google → the registered URI must match the running
  host:port exactly, including the trailing slash.
- Login button missing → provider not wired; check `TAP_BOOT_PROFILE` is set for
  the web process and `auth_selftest` shows the provider.
- `domain_not_allowed` for a Workspace account → confirm the consent screen is
  Internal so Google returns the `hd` claim (the request-side hint is never used).
