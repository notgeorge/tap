# AAR — AuthN/Z Sprint Close-Out

| | |
| --- | --- |
| **Date** | 2026-06-26 (week-long push) |
| **Severity** | None — successful sprint; foundation landed. Filed as a close-out + security-review handoff, not a went-sideways report. |
| **Status** | AuthN solid; AuthZ near-MVP with named, deliberately-deferred cleanup. **Flagged for third-party security review (see §5).** |
| **Author** | George (parting thoughts, §3) + Claude `session/boot` (commentary, §4–7) |
| **Critical-path authority** | `plan/road-rampart.md` (launch-ready step); this closes the pre-Hawaii authN+boot push. |

This is a close-out note to ourselves for when we pick authN/Z back up. It deviates
from the standard 8-section AAR format (this sprint largely succeeded) but keeps the
AAR charter: *how we worked*, what's solid, what's deferred, and where the dragons
are. The running-system behavior is covered by the specs; this is the meta-layer.

## 1. Goal vs. Outcome

**Goal:** stand up authN/Z far enough to get a real person logged into a TAP
instance and bounded by capabilities — the launch-gate item.

**Outcome:** met. AuthN is production-shaped (standalone local users + Google OIDC
via allauth, extensible to more providers, live-verified end-to-end against real
Google). AuthZ is near-MVP: the service-boundary capability model + the
human/program role-assignment model are real and enforced; what remains is a named
backlog of surfaces that don't yet route through clean gates, backstopped by the
authz-coverage scanner so no *new* anti-patterns land.

## 2. What landed (the foundation)

- **AuthN:** allauth + `google_oidc`, the default-deny login wall, the TAP security
  adapter (verified-email / `hd`-domain-via-returned-claim / `allowed_emails` /
  linking-disabled), `ExternalIdentity` (durable `(provider, sub)`), gated
  provisioning, DB-backed sessions + session invalidation (no Redis), local-auth
  disable. Live-verified.
- **This session specifically:** test-debt cleanup (gridkin oracle made
  registry-growth-robust; sigstore decompose; authz-ratchet bookkeeping); the
  OAuth-callback-unreachable → friendly 503 hardening (`req-tap-auth-google-oidc-9`);
  **`initial_grants` + the explicit `assignable_to` (human/program/both) role model
  + `tap_viewer`** (`req-tap-auth-roles-7/8/9`, `req-tap-auth-boot-8`); and the
  **json-files convention** integration (one audited `load_json_file` path; typed
  filenames).
- **Spec'd-but-deferred (waiting on demand):** the administrivia user-management
  surface (`spec-tap-auth-user-management-v0.md`), IdP-claim→role mapping, and the
  on-grid-users / grid-intent-actions split — all in the auth spec's Future Needs.

## 3. George's parting thoughts (preserved)

> **Parting thoughts on AuthN/Z**
>
> We've gotten the foundation built for both authN/Z with the authN system being
> solid for both standalone users and OIDC integration via allauth and the ability
> to add further providers as needed. That's awesome and just about exactly where it
> needs to be at this time (there's no need to email a forgotten-password link to
> non-IdP users — we haven't reached the point where our system needs to send email).
>
> The authZ system is in a near-MVP-ready state with an appropriate amount of
> embarrassing stuff that we need to deal with… eventually. Going back through the
> backlog of items that violate good authZ practices will be a task for another day
> when I've got dedicated headspace to think through how to refactor the tap_web
> access process and address the other awkward areas the scanner flagged. Until then
> we've got the scanner to backstop and avoid any new anti-patterns.
>
> Beyond cleanup there's the need to refine the authZ system to make it more robust:
> - **dimensionality** — using dimensions as a gating function on what actions
>   someone can take;
> - **ownership** — consider allowing modifications only to items the user created
>   (we don't necessarily need groups because we've already got a dimension /
>   namespace system);
> - **entity types** — further downgrade who can do what per entity so we can get to
>   super-specific roles generated on the fly for things like scoped AI actions (à la
>   Rick & Morty — "you pass the butter"-type permission sets);
> - **traversal / gryphon** — zany, but using the gryphon system to set boundaries
>   on what someone can access: dynamically define subgraphs users may operate on,
>   blast-radius-scoped access along a path through the system. Demand-driven, likely
>   by AI systems, enhanced every time we add gryphon features (e.g. path traversal).
>
> The dimensions (and traversal) systems will require modification at both the
> capabilities level and the grid-read system level — that's what lets us "hide"
> dimensions of data from users and opens the potential for future agreement systems
> by merging layers. The good news: we've got control of the surfaces where this can
> happen via our existing hunt for everywhere someone reads the grid, so we'll know
> where to inject those restrictions.
>
> The other bits are managing users via administrivia integrations and supporting
> IdP-based role mapping — both spec'd already, waiting for demand signals.
>
> Further out, managing users and representing them on the grid opens a world of
> collaboration (some of which comes up when building AI): seeing who else is on a
> page, yak-style discussions, etc. Making the transition from sub-grid to
> grid-representation of users + user-management actions needs its own dedicated
> think-through, but that lift is likely smaller than expected once based on patterns
> that have emerged — like collector management (and the work to stabilize/standardize
> how those routes are authZ'd).
>
> On the whole, good stopping place for a week-long push.
>
> **Third-party security review starts here.** This section should go through
> rigorous security review at our earliest convenience. It was a complicated bit of
> implementation and we made it through, but this was the first time we did a
> security-critical build-out — a fair amount of feeling it out as we go, and at
> least one point where handoffs / session clears produced wacky, disconcerting
> behavior. Codex pointing out repeated errors in the approach means the process
> wasn't fully baked up front; more emerged over time — not necessarily bad, but a
> place where there could still be dragons. This is where we focus fire for
> third-party assessments and for focused work with our own security tooling.

## 4. Claude's commentary — what I saw building it

**The scanner's sink inventory *is* the authZ-refinement map.** George's "we've got
control of the surfaces" is the load-bearing observation, and it's stronger than it
reads: the authz-coverage baseline (the ~54 ungated-sink worklist) is literally the
enumerated set of every grid read/write surface. The same inventory that backstops
anti-patterns today is the exact injection-point map for dimension-gating,
ownership-checks, and traversal-scoping tomorrow. Building the scanner bought two
things, not one — a guardrail *and* a refactor atlas. When the dimensions/ownership
work starts, that file is the checklist.

**The line-number baseline is itself a small anti-pattern.** It bit us three times
in one week: a gridkin-runner edit shifted two entries, and the json-files refactor
shifted `validate/service.py` 806→780. The `# TAP-AUTHZ-COV: <reason>` annotation
escape hatch is the better tool for provably-safe / test-harness sinks — I moved the
two gridkin-runner sinks to annotations and they left the fragile baseline for good.
Cleanup-day win: sweep the baseline for entries that are *actually* safe-by-context
(test harnesses, already-gated-by-an-unseen-caller) and convert them to annotations.
That shrinks the 54-list *and* removes the churn, separating "real authZ debt" from
"scanner can't see the gate."

**The dragons George felt are real, and they cluster at execution-context
boundaries.** The wacky handoff/session-clear behavior had a concrete shape worth
handing a reviewer:
- **Settings-import re-entrancy.** Code that runs *during* `tap.settings` import
  cannot reliably read `django.conf.settings` (the lazy object is mid-init). This
  produced a genuinely confusing failure that only triggered once a real boot profile
  was active (`_profile_path` reaching for `settings.BASE_DIR`, `_secrets_root` for
  `TAP_SECRETS_ROOT`). Fix was to use `__file__`-relative paths + `os.environ`
  fallback. **Reviewer prompt:** audit everything that executes at settings-time vs
  boot-time vs request-time; the boundaries are where the surprises lived.
- **allauth's defaults are not TAP-safe.** Two live bugs: allauth 65 stores
  openid_connect `extra_data` *wrapped* (`{userinfo, id_token}`) and only unwraps it
  for the uid — the adapter read top-level claims and silently denied verified users
  until `_pick_claims` merged them (signed `id_token` wins on `email_verified`/`hd`).
  And `is_open_for_signup=False` (local self-signup closed) leaked into the social
  path → "Sign Up Closed" for permitted Google logins. The adapter overrides *are*
  the security boundary; the framework underneath them is not.

**The new role boundary is a good edge — verify all three enforcement points.** The
human/program/both model enforces "a person can never be granted a program-actor
role" in three places (schema enum kept in sync with the loader by a guard test +
boot fail-loud + adapter runtime refusal), with a program-side complement
(`_ensure_program_actor` refuses human-only groups). That redundancy is deliberate
(cheap-now-expensive-later), but a reviewer should confirm each layer actually holds
and that the schema↔loader sync guard can't silently drift.

**Add-only grants are intentional but asymmetric.** `initial_grants` only ever adds
(a typo/de-listing can't silently revoke), which means de-provisioning is a *separate
explicit action*, not a config edit, and the map is **not** a source of truth for
*current* access. That's the right call for now, but it's a named gap: until the
administrivia control surface lands, revocation is manual (group removal + session
invalidation). A reviewer should confirm there's no silent-revoke path *and* that the
absence of config-driven revoke is acceptable for the deployment posture.

**The json-files refactor (landed today) is a security-posture asset for the review.**
The auth registries (`tap_auth.roles.json`, `tap_auth.capabilities.json`, the boot
profiles) now load through one audited `load_json_file` path instead of seven
copy-pasted load-validate blocks — exactly the "one hardened load path is cheaper to
harden than seven" edge. Good news for the reviewer: there's one place to add size
limits / redaction / schema-required enforcement, not a dozen.

## 5. Where to focus the security review

Per George's flag, authN/Z is the focus-fire zone. The brand-new
`specs/spec-security-posture-corpus.md` (landed this sprint) is the natural home for
the *output*: evaluate this surface against an explicit control ledger rather than a
generic scan. Concrete starting targets, in rough priority:

1. **Claim trust & the OIDC chokepoint** — `evaluate_access` + `_pick_claims`: is
   every access-relevant claim read from the *returned/signed* token, never a
   request-side hint? `hd`-domain, `email_verified`, `allowed_emails`, linking-disabled.
2. **The role-assignment boundary** — all three human/program enforcement points +
   the schema↔loader sync guard (§4).
3. **Execution-context boundaries** — settings-time vs boot-time vs request-time
   re-entrancy; the deploy-posture gate; secret resolution paths (§4).
4. **The login wall** — default-deny + exempt-prefix list: is any exemption
   (`/auth /api /admin /static`) broader than intended?
5. **Sessions** — DB-backed invalidation (global/per-user/per-session) completeness;
   the capability gate on `auth.manage_sessions`.
6. **The deferred authZ backlog** — the ~54-entry scanner baseline is the honest,
   named list of surfaces not yet behind clean gates; tap_web's access path is the
   biggest one. Not "hidden risk" — *named* risk, which is the posture we want.

## 6. Forward backlog (digest — full reasoning above + in the auth spec)

Already spec'd, demand-gated: **administrivia user-management surface**
(`spec-tap-auth-user-management-v0.md`), **IdP-claim→role mapping**, **on-grid users
/ grid-intent actions** (all in `spec-tap-auth-v0.md` Future Needs).

Named here, not yet spec'd (George's refinement directions — promote to spec Future
Needs when picked up): **dimension-gating** (dimensions as an authZ scope, requires
capabilities-level + grid-read-level changes to "hide" dimensions), **ownership-gating**
(modify-only-what-you-created, leveraging the dimension/namespace system over groups),
**entity-type-scoped roles** (on-the-fly narrow roles for scoped AI actions), and
**gryphon-traversal-scoped access** (dynamically-defined operable subgraphs;
blast-radius-scoped along a path — demand-driven, grows with gryphon features).

## 7. Lessons → durable rules

- **Security-critical build-out earns a dedicated review pass.** First time through,
  process emerged as we went; that's acceptable *if* it's followed by deliberate
  review. Don't let "it works and is tested" stand in for "it was reviewed."
- **Treat execution-context boundaries as a hazard class.** Settings-time /
  boot-time / request-time is where the confusing bugs lived; flag code that crosses
  them.
- **The anti-pattern scanner is also the refactor map.** Keep the authz-coverage
  baseline honest and lean (annotate provably-safe sinks); it's the checklist for the
  dimensions/ownership/traversal work, not just a guardrail.
- **Name the deferred risk, don't imply completeness.** The 54-entry baseline + this
  note are the named-risk record; that's the security posture we hold to.
- **Reinforces `ground-in-canon-before-building`.** The handoff weirdness is why we
  ground in specs + keystone + roadmap across session clears, not handoff docs.
