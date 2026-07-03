"""The bootloader orchestrator — fixed-phase standup (req-boot-phases).

`run_boot` is the single canonical standup path for both dev (`spawn-session.sh`,
req-boot-spawn-bridge) and customer deployments. It runs the v0 phase order
**auth → population**:

- **auth** — `tap_auth.sync_auth()` (capabilities → protected groups → built-in
  program actors, incl. `tap_bootloader`) then `ensure_initial_admin()`. The boot
  actor is resolved here, *after* `sync_auth` mints it (the v0 collapse of the
  fuller `bootstrap` pre-phase: nothing writes through the service layer before
  auth, so no earlier actor is needed — spec v0 Scope).
- **population** — bound `acting_as(tap_bootloader)`: pre-resolve every enabled
  step against in-memory registries (unknown plugin/collector/bundle aborts before
  ANY grid mutation, req-boot-population-4), *then* reconcile collector grid nodes,
  then apply the ordered `seed-plugin` / `fire-collector` steps.

Phases are plain functions so each becomes a registered section-handler body when
that framework lands (req-boot-sections) — an additive refactor, not a rewrite.
The deferred section/registry/two-layer-validate machinery is intentionally not
built here (spec v0 Scope).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from tap_auth.actors import BOOTLOADER, acting_as, get_builtin_actor
from tap_auth.sync import ensure_initial_admin, sync_auth
from tap_boot.profile import BootProfile, FireCollectorStep, PopulationStep, SeedPluginStep

logger = logging.getLogger(__name__)

# A no-op writer keeps run_boot usable from tests/handlers that don't want stdout.
Echo = Callable[[str], None]
_SILENT: Echo = lambda _msg: None  # noqa: E731

# Default per-collector await timeout when a fire-collector step does not set its
# own `timeout_seconds`. Deliberately short — snappy collectors should finish well
# inside it; a slow collector (a full cloud pull) declares a higher value on its
# step. The better long-term home is a per-collector default the step overrides
# (see backlog req-boot-collector-timeout); v0 uses this single fallback.
DEFAULT_COLLECTOR_TIMEOUT_SECONDS = 90.0


class BootError(Exception):
    """Raised when a phase cannot complete; the command maps it to a non-zero exit."""


def run_boot(profile: BootProfile | None, *, echo: Echo | None = None) -> None:
    """Stand the instance up: auth phase, then (if the profile has steps) population.

    `profile` is None for an auth-only standup (an intentional `--allow-empty`
    run, req-boot-profile-4). Raises `BootError` on any phase failure, after
    logging the offending section/step (req-boot-report).
    """
    say = echo or _SILENT
    profile_label = profile.profile_id if profile else "(none — auth only)"
    logger.info("[c13a] boot starting: profile=%s", profile_label)
    say(f"Boot starting (profile: {profile_label}).")

    _phase_auth(profile, say)

    if profile is None or not profile.has_population:
        logger.info("[f89d] boot: no population steps; auth-only standup complete")
        say("No population steps — auth-only standup complete.")
        return

    # The boot actor is resolved after sync_auth mints it and bound for every
    # population write (req-boot-phases-3: no boot write is User=None).
    bootloader = get_builtin_actor(BOOTLOADER)
    with acting_as(bootloader):
        _phase_population(profile, bootloader, say)

    logger.info("[9e9b] boot complete: profile=%s", profile_label)
    say("Boot complete.")


def check_profile(profile: BootProfile | None, *, echo: Echo | None = None) -> int:
    """Resolve-only preflight: validate every enabled step, mutate nothing.

    Runs the zero-grid-mutation pre-resolution `run_boot` does before the
    population phase (`_resolve_steps`) — every `seed-plugin` slug/bundle and
    every `fire-collector` key is checked against the in-memory registries — but
    stops there: no auth sync, no DB writes, no collector firing. This is the
    per-profile cold-boot smoke's engine: a shipped profile whose collector key
    has rotted (the module-path→slug drift class) or whose plugin/bundle is
    missing fails here, offline, without standing anything up.

    Returns the number of enabled population steps that resolved. Raises
    `BootError` on the first unresolvable step (same failure the real boot
    would hit at `_resolve_steps`, only sooner and side-effect-free).
    """
    say = echo or _SILENT
    profile_label = profile.profile_id if profile else "(none — auth only)"
    if profile is None or not profile.has_population:
        say(f"Profile '{profile_label}': no population steps to resolve (auth-only).")
        return 0
    plan = _resolve_steps(profile, say)
    say(f"Profile '{profile_label}': {len(plan)} population step(s) resolved cleanly.")
    return len(plan)


def _phase_auth(profile: BootProfile | None, say: Echo) -> None:
    """auth phase: hard-sync capabilities/groups/actors, ensure the admin, then
    (if the profile declares one) validate + apply the auth section."""
    logger.info("[0b5f] boot auth phase: sync_auth")
    say("Auth phase: syncing capabilities, protected groups, built-in actors ...")
    sync_auth()

    admin = ensure_initial_admin()
    if admin is not None:
        say(f"Auth phase: initial admin '{admin.get_username()}' ensured (joined tap_admin).")
    else:
        say("Auth phase: no DJANGO_SUPERUSER_USERNAME set; skipped initial-admin bootstrap.")

    if profile is not None and profile.has_auth:
        from django.conf import settings

        from tap_auth.boot import AuthBootError, apply_auth_boot_section

        logger.info("[b2d4] boot auth phase: applying auth section (providers, last-admin, deploy gate)")
        say("Auth phase: validating + applying auth section ...")
        try:
            apply_auth_boot_section(profile.auth or {}, deploy=not settings.DEBUG, echo=say)
        except AuthBootError as exc:
            raise BootError(f"auth section: {exc}") from exc


def _phase_population(profile: BootProfile, bootloader: object, say: Echo) -> None:
    """population phase: pre-resolve (no mutation), reconcile, apply ordered steps."""
    from tap_cares.registry import reconcile_collector_nodes

    # Pre-resolution happens FIRST, against in-memory registries only — so an
    # unknown plugin slug / collector key / bundle name aborts before ANY grid
    # mutation, including the collector-node reconcile below (req-boot-population-4).
    plan = _resolve_steps(profile, say)

    logger.info("[f193] boot population phase: reconciling collector nodes")
    say("Population phase: reconciling collector grid nodes ...")
    reconcile_collector_nodes()

    failures: list[str] = []
    for step in plan:
        ok = _apply_step(step, bootloader, say)
        if ok:
            continue
        label = _step_label(step)
        failures.append(label)
        if profile.on_failure == "abort":
            logger.error("[ac13] boot population aborting on failed step: %s", label)
            raise BootError(f"Population step failed: {label}; on_failure=abort — stopping.")

    if failures:
        raise BootError(f"Population completed with {len(failures)} failed step(s): {', '.join(failures)}.")

    logger.info("[cc13] boot population phase complete: %d step(s)", len(plan))


def _resolve_steps(profile: BootProfile, say: Echo) -> list[PopulationStep]:
    """Validate every enabled step against in-memory registries; fail loud on any miss.

    Resolves with ZERO grid mutation (collector keys are checked against the
    in-memory collector registry, not by reading/creating grid nodes), so a
    malformed profile aborts before the population phase touches the grid.
    """
    from tap_cares.exceptions import CollectorNotFoundError
    from tap_cares.registry import get_collector
    from tap_plugins.seeding import PluginNotFound, resolve_tap_plugin

    for step in profile.enabled_steps:
        if isinstance(step, SeedPluginStep):
            try:
                config = resolve_tap_plugin(step.plugin)
            except PluginNotFound as exc:
                raise BootError(f"seed-plugin: {exc} Aborting before any population step runs.") from exc
            if step.bundle is not None:
                declared = {b.name for b in (config.manifest.grift if config.manifest else [])}
                if step.bundle not in declared:
                    raise BootError(
                        f"seed-plugin '{step.plugin}': unknown bundle '{step.bundle}'. "
                        f"Declared bundles: {sorted(declared) or '(none)'}. "
                        "Aborting before any population step runs."
                    )
        elif isinstance(step, FireCollectorStep):
            try:
                get_collector(step.key)
            except CollectorNotFoundError as exc:
                raise BootError(
                    f"fire-collector: unknown collector key '{step.key}' — not registered. "
                    "Aborting before any population step runs."
                ) from exc
        else:  # pragma: no cover - schema guards the type set
            raise BootError(f"Unknown population step type: {step!r}")

    skipped = len(profile.steps) - len(profile.enabled_steps)
    plan = list(profile.enabled_steps)
    logger.info("[8e0f] boot population plan: %d step(s) (%d disabled, skipped)", len(plan), skipped)
    say(f"Population plan: {len(plan)} step(s) to apply ({skipped} disabled).")
    return plan


def _apply_step(step: object, bootloader: object, say: Echo) -> bool:
    if isinstance(step, SeedPluginStep):
        return _apply_seed_plugin(step, bootloader, say)
    if isinstance(step, FireCollectorStep):
        return _apply_fire_collector(step, say)
    return False  # pragma: no cover


def _apply_seed_plugin(step: SeedPluginStep, bootloader: object, say: Echo) -> bool:
    from tap_plugins.seeding import resolve_tap_plugin, seed_plugin

    say(f"  [seed-plugin] {step.plugin} ...")
    config = resolve_tap_plugin(step.plugin)  # validated in _resolve_steps; cheap in-memory lookup
    outcomes = seed_plugin(config, actor=bootloader, bundle_name=step.bundle)

    if not outcomes:
        # No bundles imported. A bad bundle name was already rejected in
        # pre-resolution, so this only happens for a plugin that declares no GRIFT
        # — report it honestly (it is a no-op, not "seeded data").
        logger.info("[5f47] seed-plugin %s: no GRIFT bundles to import", step.plugin)
        say(f"    OK — {step.plugin}: no GRIFT bundles to import (no-op).")
        return True

    failed = [o for o in outcomes if not o.ok]
    for o in outcomes:
        if o.ok:
            logger.info("[e79e] seeded %s/%s", o.slug, o.bundle_name)
        else:
            detail = o.read_error if o.read_error is not None else "import failed (see grift result)"
            logger.error("[916b] seed failed %s/%s: %s", o.slug, o.bundle_name, detail)
    if failed:
        say(f"    FAILED — {step.plugin}: {len(failed)} bundle(s) did not import.")
        return False
    say(f"    OK — {step.plugin}: {len(outcomes)} bundle(s) seeded.")
    return True


def _apply_fire_collector(step: FireCollectorStep, say: Echo) -> bool:
    from tap_cares.models import Collector
    from tap_cares.services import fire_collector_and_await

    # The Collector grid node exists now (reconcile ran after pre-resolution); the
    # key was validated against the registry in _resolve_steps.
    collector = Collector.objects.get(collector_registry=step.key)
    timeout = step.timeout_seconds if step.timeout_seconds is not None else DEFAULT_COLLECTOR_TIMEOUT_SECONDS

    say(f"  [fire-collector] {step.key} (run_mode={step.run_mode}, timeout={timeout:g}s) ...")
    ok, job = fire_collector_and_await(
        collector,
        run_mode=step.run_mode,
        manual_run_source="boot",
        timeout_seconds=timeout,
    )
    if ok:
        logger.info("[75b3] fired collector %s: %s", step.key, job.summary or "successful")
        say(f"    OK — {step.key}: {job.summary or 'successful'}")
        return True
    logger.error("[1324] collector failed %s: status=%s %s", step.key, job.status, job.summary or "")
    say(f"    FAILED — {step.key}: status={job.status} {job.summary or 'see CollectionJob'}")
    return False


def _step_label(step: object) -> str:
    if isinstance(step, SeedPluginStep):
        return f"seed-plugin:{step.plugin}"
    if isinstance(step, FireCollectorStep):
        return f"fire-collector:{step.key}"
    return repr(step)  # pragma: no cover
