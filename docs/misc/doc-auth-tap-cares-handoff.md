---
title: Auth tap_cares Pass — Session Handoff
date: 2026-06-24
status: handoff
audience:
  - llm
  - developer
related_docs:
  - docs/misc/doc-auth-per-app-standards.md
related_specs:
  - tap_auth/specs/spec-tap-auth-v0.md
---

# Auth tap_cares Pass — Session Handoff

Handoff for the next session to complete the **tap_cares per-app auth pass** (the program-actor
binding work). The core auth tightening + the per-app actor model + the actor rename are **done and
committed** on `session/boot`; this pass closes the "every collector run broken in prod, green in
CI" class. Read this first, then the `tap_cares` section of `doc-auth-per-app-standards.md` (note its
**post-backout banner — do NOT reintroduce ledger machinery**) and `spec-tap-auth-v0.md`
(`req-tap-auth-actor-model` / `req-tap-auth-builtins` for the per-app internal-actor model).

## State — 5 commits on `session/boot`, NOT promoted

- `66ff0f2` stateless backstop + core hardening (ledger removed → `policy.can` re-check)
- `88dd555` authz-coverage lint (Rule A) — baseline at `tap/tests/_authz_coverage_baseline.txt`
- `5460d95` GRIFT sweep tombstone authorizes grid.delete + lint marker fix
- `ba4a294` per-app internal-actor model (spec/docs) + Codex reconciliation
- `21ad2b1` actor rename → `tap_cares.collector` / `tap_cares.scheduler`  ← the pass starts here

## THE design input (George, 2026-06-24): a generic `acting_as`, NOT a per-app helper

Build ONE generic context manager in **`tap_auth`**, parameterized by the actor — the no-request
analogue of `CallerContextMiddleware`. Do **not** write a cares-specific `collector_runtime_context()`.

```python
# tap_auth (alongside the middleware + get_builtin_actor); composes tap_grid's CallerContext
@contextlib.contextmanager
def acting_as(actor, *, batch_id=None):
    prior = get_caller_context()
    set_caller_context(CallerContext(user=actor, batch_id=batch_id))
    try:
        yield
    finally:
        set_caller_context(prior)
```

Every no-request subsystem inherits it by supplying its **resolved actor** (not a builtin_key, so it
stays fully generic): cares `with acting_as(get_builtin_actor(COLLECTOR)):`, boot
`with acting_as(get_builtin_actor(BOOTLOADER)):`, a future AI runner `with acting_as(delegated):`.
The request middleware is the request-scoped special case of this (same set/restore, sourced from
`request.user`) — optionally refactor it onto `acting_as` later.

## Remaining tasks (closes ~13 of the 15 tap_cares authz-coverage baseline rows)

1. **`acting_as`** in `tap_auth` (the generic helper above).
2. **Bind the cares no-request boundaries:**
   - `tasks.py` `run_collector` (rows 151/167/196/214/258/280) — wrap the task body in
     `with acting_as(get_builtin_actor(COLLECTOR)):` **once** at entry; downstream
     `_patch_node_internal` / `create_edge` / `submit_grift` inherit it.
   - `collectors/base.py` `submit_grift` (289) — drop the `actor=None` default; use the bound actor.
   - `scheduler.py` tick path (266/300/319/343) — route through the `tap_cares.scheduler` context
     (`acting_as(get_builtin_actor(SCHEDULER))` at the tick boundary, or extend `_scheduler_ctx`)
     instead of pass-through `caller_context=None`.
   - `services.py` (225/271) — thread the bound ctx through the enqueue/record paths.
   - `registry.py` (157/194) — **DEFER to the boot increment** (the "move collector upsert out of
     `ready()` under `tap_bootloader`" work). These 2 rows stay in the baseline after this pass.
   - Already correct, do NOT touch: `run_collection` (services.py:202 binds COLLECTOR), `_scheduler_ctx`
     (scheduler.py:64 self-heals SCHEDULER).
3. **Human-trigger gate** on `run_collection`: authorize the triggering human for
   `cares.run_collectors` **before** the COLLECTOR swap — two decisions, never collapsed. Every
   trigger surface (the administrivia collector panel POST, mgmt commands) routes through it.
4. **Production-realism test** (highest value): a fixture that clears the ambient actor
   (`set_caller_context(None)`, no pre-auth) and asserts a cares write-path **still succeeds** by
   binding its own COLLECTOR via `acting_as` — the test that would have caught the prod break. Plus a
   human-trigger denial test (no-cap → denied, no job created).
5. **Ratchet the baseline**: delete the now-gated rows from `tap/tests/_authz_coverage_baseline.txt`.
   The gate fails on **stale** entries too, so they MUST be removed as you close them (~15 → 2).

## Decisions locked (this session)

- Naming: `<full-app-label>.<component>` → `tap_cares.collector`, `tap_cares.scheduler`; `tap_boot.*`
  when the boot increment lands. `user_kind` stays `program` (ownership via namespace, not a new kind).
- `registry.py`'s 2 rows → boot increment, not now.
- Dev-DB rename: accept the re-sync; old `tap_collector`/`tap_scheduler` built-ins orphan. **Validate
  with `--create-db`** (fresh DB) — a reused DB carries the orphans and will fail `test_sync`'s keys
  assertion.

## Validation

- `scripts/dc exec -T web uv run pytest tap_cares/ tap_auth/ --create-db -q`
- The authz gate (`tap/tests/test_authz_coverage.py`) must stay green — delete baseline rows as you
  close them; do a final full-suite run before declaring done.

## After this pass

boot increment (registry upsert out of `ready()` + a boot binding via `acting_as`), then tap_web
(lint Rule B + the panel ORM→gryphon/batch conversion — separate/parallel session per George), then
tap_api. Promote the `session/boot` commits when George says.
