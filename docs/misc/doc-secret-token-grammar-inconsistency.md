# Issue: two secret loaders, two token grammars (`tap_plugins/source` degraded-secret)

**Status:** ✅ RESOLVED 2026-07-04 (flat-grammar fix). The token grammar was centralized to one
home (`tap.registry.SCOPED_TOKEN_PATTERN` + `validate_scoped_token`); the two copied `_TOKEN_PATTERN`s
in `tap_cares` now defer to it; `tap/runtime_secrets` enforces it on the pre-boot read path too; and
the outlier scope was realigned `tap_plugins/source` → `tap_plugins.source` (flat, `.` not `/`) in both
`SOURCE_SECRET_SCOPE` and the mounted `.secret.json`. The `W001` degraded-secret warning is gone. The
original write-up is retained below as the design record. Deferred preventive follow-on: enforcing
`scope` as a real least-privilege boundary (`req-tap-cares-secrets-future-access-control`); interim
detective control shipped alongside (a `CONCERN` tripwire when a plugin resolves `tap_plugins.source`).

**TL;DR:** The same `/run/tap-secrets/*.secret.json` files are read by *two* subsystems that
disagree on what a valid `scope`/`key` token is. The core pre-boot resolver accepts a `/`;
the Django-side `tap_cares` registry forbids it. So the plugin-source credential
(`tap_plugins/source:github-plugins-ro`) **works** for pulling plugins but throws a degraded
`tap_cares.W001` when the tap_cares registry tries to index it. The real defect is that the
token grammar was never given a single home.

## Symptom (reproduced on both stacks, 2026-07-03)

```
tap_cares.secrets.loader — skipping file with invalid token
  /run/tap-secrets/tap_plugins/github-plugins-ro.secret.json:
  Invalid secret registry token 'tap_plugins/source'. Must match ^[A-Za-z0-9][A-Za-z0-9_.\-]*$.
tap_cares.W001  Secret failed to load (degraded): tap_plugins/source:github-plugins-ro — …
```

The other three secrets in the same dir load clean (`auth:example-google`,
`aws_core:boto_collector`, `github_core:collector`) — every one uses a **flat, slash-free**
scope. `tap_plugins/source` is the lone `/` outlier. Confirmed identical on `session/plugins`
(plugin-clear) and `session/codex-security` — the secrets subsystem is byte-identical between
them, so this is not a stale-branch artifact and there is no fix on either side.

## The two readers

1. **Pre-boot install path — the one that actually pulls plugins.**
   `tap/plugin_source_auth.py` → `tap.runtime_secrets.resolve_secret_envelope`. `runtime_secrets`
   validates envelope *shape* (scope/key are strings, required fields present) and resolves a
   file by **plain scope/key string match** (`find_secret_file`:
   `doc["scope"] == scope and doc["key"] == key`). It applies **no charset/token-format rule**,
   so `tap_plugins/source` resolves fine. This is why the PAT has worked for hours.

2. **`tap_cares` Django-side secret registry — the one that warns.**
   `tap_cares/secrets/loader.py` indexes discovered secrets into a `tap.registry.ScopedRegistry`
   via `_validate_secret_token` (`tap_cares/secrets/registry.py:30`), which runs
   `_TOKEN_PATTERN = ^[A-Za-z0-9][A-Za-z0-9_.\-]*$` — **no `/`** → the file is skipped and the
   secret goes degraded. This registry is *not* in the plugin-install path; it backs
   collector-secret lookup and the health/`W001` surface.

Same directory, two grammars, guaranteed to drift.

## Corrected impact

Earlier characterization ("the credential can never resolve") was **backwards**. The credential
resolves perfectly for its real consumer (pre-boot git install). What is degraded is only the
**`tap_cares` registry's *view*** of it: anything relying on `secret_registry` to see
`tap_plugins/source:github-plugins-ro` (health reporting, collector-secret lookup) won't find it.
Plugin pulling is unaffected. It is a WARNING, not a boot/promote blocker.

## Root cause

The token grammar is **duplicated and mis-homed**:

- `tap/runtime_secrets.py` (the centralized core secret-file layer) — **no** charset rule.
- `tap_cares/registry.py:43` — `_TOKEN_PATTERN` for *collector* tokens.
- `tap_cares/secrets/registry.py:30` — a **byte-identical copy** for *secret* tokens (its own
  docstring says it "mirrors the collector registry's validator").

So the shared core says "`/` is fine" and a hand-copied pattern one layer up says "`/` is
illegal." There is no single source of truth for "what is a valid secret token."

## Reasonable upstream fix

Give the grammar one home in the **centralized core** both consumers already import, and have
everything defer to it:

1. Define the canonical secret scope/key grammar **once in `tap/runtime_secrets.py`**
   (`SECRET_TOKEN_PATTERN` + a `validate_secret_token()` helper).
2. Point the `tap_cares` secret registry's `_validate_secret_token` at it; **delete the copy**.
   (Optionally unify the collector-token copy too — the fully-centralized version parks the
   default token validator on `tap.registry.ScopedRegistry` so every scoped registry shares it.)
3. Enforce it in `runtime_secrets`' envelope parse so a malformed scope fails **loud and
   identically** on every read path, instead of one path silently diverging.

### The grammar decision: keep it flat

Every secret that works today uses a flat slug scope; `tap_plugins/source` is the only `/`
user, and it doesn't even honor its own "dir mirrors the scope" story (the file lives in
`tap_plugins/`, not `tap_plugins/source/`). So:

- **Keep the grammar flat** (no `/`) and realign the outlier:
  `SOURCE_SECRET_SCOPE = "tap_plugins/source"` → `"tap_plugins.source"` (the `.` is already
  legal in the pattern). This matches the established convention instead of inventing a
  hierarchy for one secret.
- Allowing `/` (real hierarchical scopes) is the larger change — it reshapes the registry's
  scope model and the on-disk layout convention to accommodate one scope that isn't using the
  hierarchy consistently. Not warranted.

### Ordering catch (must sequence, or it breaks the working install)

Enforcing the grammar in `runtime_secrets` makes the pre-boot resolver start rejecting `/` too —
which would break the install that currently works. So:

1. **First:** `SOURCE_SECRET_SCOPE` → `tap_plugins.source`, and update the mounted dev
   `.secret.json`'s declared `scope` (and, if the layout mirrors scope, its path). This file
   lives at `/run/tap-secrets`, **not in git** — an ops/dev-env touch.
2. **Then:** centralize + enforce the grammar in `tap/`, deleting the duplicated patterns.

Landing the grammar first *without* enforcement (accepting today's inputs), then realigning the
scope, then tightening, keeps every step green.

## Suggested split

- **`tap/` centralization** (canonical grammar in `runtime_secrets`, collapse the
  `_TOKEN_PATTERN` copies) — core security-adjacent work; a cheap foundational edge (one
  grammar, enforced on every path, can't silently diverge again).
- **`SOURCE_SECRET_SCOPE` value + the mounted `.secret.json`** — plugin-refactor / ops domain
  (Codex / George).

## Pointers

- `tap/runtime_secrets.py` — `find_secret_file`, `resolve_secret_envelope` (string-match, no grammar).
- `tap/plugin_source_auth.py:50` — `SOURCE_SECRET_SCOPE = "tap_plugins/source"`.
- `tap_cares/secrets/registry.py:30` — the rejecting `_TOKEN_PATTERN` copy.
- `tap_cares/registry.py:43` — the collector-token copy (unify candidate).
- `tap_cares/secrets/loader.py`, `tap_cares/checks.py` — the loader + `W001` system check.
