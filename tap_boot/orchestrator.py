"""The bootloader orchestrator — fixed-phase standup (req-boot-phases).

`run_boot` is the single canonical standup path for both dev (`spawn-session.sh`,
req-boot-spawn-bridge) and customer deployments. It runs the v0 phase order
**auth → population**:

- **auth** — `tap_auth.sync_auth()` (capabilities → protected groups → built-in
  program actors, incl. `tap_bootloader`) then `ensure_initial_admin()`. The boot
  actor is resolved here, *after* `sync_auth` mints it (the v0 collapse of the
  fuller `bootstrap` pre-phase: nothing writes through the service layer before
  auth, so no earlier actor is needed — spec v0 Scope).
- **population** — bound `acting_as(tap_bootloader)`: reconcile collector grid
  nodes, pre-resolve every step (unknown plugin/collector key fails loud before
  any mutation), then apply the ordered `seed-plugin` / `fire-collector` steps.

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
from tap_boot.profile import BootProfile, FireCollectorStep, SeedPluginStep

logger = logging.getLogger(__name__)

# A no-op writer keeps run_boot usable from tests/handlers that don't want stdout.
Echo = Callable[[str], None]
_SILENT: Echo = lambda _msg: None  # noqa: E731


class BootError(Exception):
    """Raised when a phase cannot complete; the command maps it to a non-zero exit."""


def run_boot(
    profile: BootProfile | None,
    *,
    timeout_seconds: float = 600.0,
    echo: Echo | None = None,
) -> None:
    """Stand the instance up: auth phase, then (if the profile has steps) population.

    `profile` is None for an auth-only standup (no profile selected, the dev
    no-outbound default — req-boot-profile-4). Raises `BootError` on any phase
    failure, after logging the offending section/step (req-boot-report).
    """
    say = echo or _SILENT
    profile_label = profile.profile_id if profile else "(none — auth only)"
    logger.info("[c13a] boot starting: profile=%s", profile_label)
    say(f"Boot starting (profile: {profile_label}).")

    _phase_auth(say)

    if profile is None or not profile.has_population:
        logger.info("[f89d] boot: no population steps; auth-only standup complete")
        say("No population steps — auth-only standup complete.")
        return

    # The boot actor is resolved after sync_auth mints it and bound for every
    # population write (req-boot-phases-3: no boot write is User=None).
    bootloader = get_builtin_actor(BOOTLOADER)
    with acting_as(bootloader):
        _phase_population(profile, bootloader, timeout_seconds, say)

    logger.info("[9e9b] boot complete: profile=%s", profile_label)
    say("Boot complete.")


def _phase_auth(say: Echo) -> None:
    """auth phase: hard-sync capabilities/groups/actors, then ensure the admin."""
    logger.info("[0b5f] boot auth phase: sync_auth")
    say("Auth phase: syncing capabilities, protected groups, built-in actors ...")
    sync_auth()

    admin = ensure_initial_admin()
    if admin is not None:
        say(f"Auth phase: initial admin '{admin.get_username()}' ensured (joined tap_admin).")
    else:
        say("Auth phase: no DJANGO_SUPERUSER_USERNAME set; skipped initial-admin bootstrap.")


def _phase_population(
    profile: BootProfile,
    bootloader: object,
    timeout_seconds: float,
    say: Echo,
) -> None:
    """population phase: reconcile collector nodes, pre-resolve, apply ordered steps."""
    from tap_cares.registry import reconcile_collector_nodes

    logger.info("[f193] boot population phase: reconciling collector nodes")
    say("Population phase: reconciling collector grid nodes ...")
    reconcile_collector_nodes()

    # Pre-resolution: every enabled step's plugin/collector key is resolved before
    # ANY step mutates the grid, so an unknown key aborts cleanly (req-boot-population-4).
    plan = _resolve_steps(profile, say)

    failures: list[str] = []
    for step, resolved in plan:
        ok = _apply_step(step, resolved, bootloader, timeout_seconds, say)
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


def _resolve_steps(profile: BootProfile, say: Echo) -> list[tuple[object, object]]:
    """Resolve each enabled step to its target object; fail loud on an unknown key."""
    from tap_cares.models import Collector
    from tap_plugins.seeding import PluginNotFound, resolve_tap_plugin

    plan: list[tuple[object, object]] = []
    for step in profile.enabled_steps:
        if isinstance(step, SeedPluginStep):
            try:
                resolved: object = resolve_tap_plugin(step.plugin)
            except PluginNotFound as exc:
                raise BootError(f"seed-plugin: {exc} Aborting before any population step runs.") from exc
        elif isinstance(step, FireCollectorStep):
            try:
                resolved = Collector.objects.get(collector_registry=step.key)
            except Collector.DoesNotExist:
                raise BootError(
                    f"fire-collector: unknown collector key '{step.key}' — not registered. "
                    "Aborting before any population step runs."
                ) from None
        else:  # pragma: no cover - schema guards the type set
            raise BootError(f"Unknown population step type: {step!r}")
        plan.append((step, resolved))

    skipped = len(profile.steps) - len(profile.enabled_steps)
    logger.info("[8e0f] boot population plan: %d step(s) (%d disabled, skipped)", len(plan), skipped)
    say(f"Population plan: {len(plan)} step(s) to apply ({skipped} disabled).")
    return plan


def _apply_step(
    step: object,
    resolved: object,
    bootloader: object,
    timeout_seconds: float,
    say: Echo,
) -> bool:
    if isinstance(step, SeedPluginStep):
        return _apply_seed_plugin(step, resolved, bootloader, say)
    if isinstance(step, FireCollectorStep):
        return _apply_fire_collector(step, resolved, timeout_seconds, say)
    return False  # pragma: no cover


def _apply_seed_plugin(step: SeedPluginStep, config: object, bootloader: object, say: Echo) -> bool:
    from tap_plugins.seeding import seed_plugin

    say(f"  [seed-plugin] {step.plugin} ...")
    outcomes = seed_plugin(config, actor=bootloader, bundle_name=step.bundle)  # type: ignore[arg-type]
    failed = [o for o in outcomes if not o.ok]
    for o in outcomes:
        if o.ok:
            logger.info("[5f47] seeded %s/%s", o.slug, o.bundle_name)
        else:
            detail = o.read_error if o.read_error is not None else "import failed (see grift result)"
            logger.error("[e79e] seed failed %s/%s: %s", o.slug, o.bundle_name, detail)
    if failed:
        say(f"    FAILED — {step.plugin}: {len(failed)} bundle(s) did not import.")
        return False
    say(f"    OK — {step.plugin}: {len(outcomes)} bundle(s) seeded.")
    return True


def _apply_fire_collector(step: FireCollectorStep, collector: object, timeout_seconds: float, say: Echo) -> bool:
    from tap_cares.services import fire_collector_and_await

    say(f"  [fire-collector] {step.key} (run_mode={step.run_mode}) ...")
    ok, job = fire_collector_and_await(
        collector,  # type: ignore[arg-type]
        run_mode=step.run_mode,
        manual_run_source="boot",
        timeout_seconds=timeout_seconds,
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
