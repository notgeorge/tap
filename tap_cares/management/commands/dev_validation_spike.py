"""Phase-0 spike for the development validation gate's load-bearing requirement.

Proves `req-dev-validation-real-backend` (specs/spec-dev-validation.md) is
buildable: a collector can be driven through the **real** DB-backed
`SteadyQueueBackend` — never the pytest `ImmediateBackend` substitute — with an
in-process synchronous drain, reaching a terminal `CollectionJob` state and a
positively-asserted grid mutation.

The drain is the real Steady Queue machinery, minus the supervisor/fork/
thread-pool/polling-loop that production uses to *drive* it:

  ScheduledExecution.dispatch_next_batch()   # promote scheduled -> ready
  ReadyExecution.objects.claim(queues, ...)  # real FOR UPDATE SKIP LOCKED
  ClaimedExecution.perform()                 # real deserialize + task.func

This is genuinely distinct from both forbidden options:
  - NOT ImmediateBackend: real Job/ReadyExecution rows, a real commit
    boundary (run_collection's transaction.on_commit must fire before the
    row is claimable), real Arguments deserialization + task dispatch.
  - NOT the deferred out-of-process real-worker tiers (task-backend
    backlog-2): no fork, no supervisor, no concurrency/thread-pool surface.

Usage (inside the compose image, real settings — NOT test settings):

    scripts/dc exec -T web sh -c 'cd /app && uv run python manage.py \
        dev_validation_spike --collector <registry_key> [--timeout 120] [--skip-drain]'

`--skip-drain` is the teeth check: with no consumer the job must stay READY
and the command must exit non-zero — proving the gate catches "the backend
did not actually deliver", which an ImmediateBackend gate would mask.

Phase-0 deliverable only; the Phase-1 cold-boot gate (task #27) is backlogged.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

_TERMINAL = {"SUCCESSFUL", "FAILED"}


class Command(BaseCommand):
    help = "Phase-0 spike: drive a collector through the real backend + in-process drain."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--collector",
            dest="collector",
            required=True,
            help="Collector registry key, e.g. plugins.fedramp_20x_ksi.collectors.ksi_catalog:ksi-catalog",
        )
        parser.add_argument(
            "--timeout",
            dest="timeout",
            type=int,
            default=120,
            help="Seconds to wait for the in-process drain to reach a terminal CollectionJob state.",
        )
        parser.add_argument(
            "--skip-drain",
            dest="skip_drain",
            action="store_true",
            default=False,
            help="Teeth check: enqueue but do NOT drain; assert the job stays READY and exit non-zero.",
        )

    def handle(self, *args, **options) -> None:
        from django.conf import settings

        backend = settings.TASKS["default"]["BACKEND"]
        if "ImmediateBackend" in backend:
            raise CommandError(
                f"Refusing to run under {backend}. This spike is meaningless without the real "
                f"DB-backed backend (req-dev-validation-real-backend-1). Run via manage.py "
                f"(tap.settings), not the pytest/test_settings path."
            )
        self.stdout.write(f"backend: {backend}")

        from tap_auth.actors import BOOTLOADER, acting_as, get_builtin_actor
        from tap_cares.models import CollectionJobStatus, Collector
        from tap_cares.services import run_collection

        key: str = options["collector"]
        timeout: int = options["timeout"]
        skip_drain: bool = options["skip_drain"]

        try:
            collector = Collector.objects.get(collector_registry=key)
        except Collector.DoesNotExist as exc:
            raise CommandError(
                f"No on-grid Collector for registry key {key!r}. Registered collectors are "
                f"created by plugin GRIFT import; run import_plugin_grift --all first."
            ) from exc

        self.stdout.write(f"collector: {collector.name} ({key})")

        # CLI dev spike has no request middleware to bind an actor; run_collection's
        # trigger gate (cares.run_collectors) requires a named one. Fire as
        # tap_bootloader (holds the cap); the run still executes as tap_cares.collector.
        with acting_as(get_builtin_actor(BOOTLOADER)):
            job = run_collection(
                collector,
                manual_run=True,
                manual_run_source="dev_validation_spike",
            )
        job_id = job.entity_id
        job.refresh_from_db()
        self.stdout.write(f"enqueued: CollectionJob {job_id} status={job.status}")

        if skip_drain:
            # Teeth check: no consumer ran, so the real backend must NOT have
            # advanced the job. A green here would mean the backend executed
            # inline (ImmediateBackend semantics) — exactly the blind spot the
            # gate exists to prevent.
            if job.status == CollectionJobStatus.READY.value:
                raise CommandError(
                    "TEETH CHECK PASSED (intentional non-zero exit): job stayed READY with no "
                    "drain — the real backend did not execute inline. A gate that ran under "
                    "ImmediateBackend would have shown this green. This is the failure class "
                    "req-dev-validation-real-backend exists to catch."
                )
            raise CommandError(
                f"TEETH CHECK FAILED: job advanced to {job.status} with no drain — the backend "
                f"is executing inline (ImmediateBackend-like). Gate fidelity is compromised."
            )

        from tap_cares.dev_validation import DrainTimeout, drain_ready_executions

        try:
            drained = drain_ready_executions(deadline=time.monotonic() + timeout)
        except DrainTimeout as exc:
            raise CommandError(f"GATE RED: {exc}") from exc
        self.stdout.write(f"drain: performed {drained} execution(s)")

        job.refresh_from_db()
        self.stdout.write(f"terminal: CollectionJob {job_id} status={job.status}")

        if job.status not in _TERMINAL:
            raise CommandError(
                f"GATE RED: job did not reach a terminal state within {timeout}s "
                f"(status={job.status}). Delivery hang or stuck job — a real failure class."
            )

        if job.status == CollectionJobStatus.FAILED.value:
            # A FAILED collector is itself a valuable spike outcome: the gate
            # surfaces the real collector bug instead of masking it.
            raise CommandError(
                f"GATE RED: collector ran through the real backend but FAILED.\n"
                f"  summary: {job.summary!r}\n"
                f"  self_test: {job.self_test}\n"
                f"  errors: {(job.results or {}).get('error')}"
            )

        # Grid-mutation signal is the CollectionJob --PRODUCED_BATCH--> Batch
        # edges with disposition="imported" (req-grid-edge-produced-batch).
        # The former Phase-0 drift (grift_batches JSON field, zero edges) is
        # closed: the CARES runtime now creates these edges at terminal state
        # and the field is gone.
        from tap_grid.batch import produced_batches

        imported = produced_batches(job.entity_id)["imported"]
        info_codes = [e.get("message_code") for e in (job.results or {}).get("info", [])]

        if imported:
            self.stdout.write(
                self.style.SUCCESS(
                    f"GATE GREEN: real backend enqueue -> commit -> in-process drain -> "
                    f"terminal SUCCESSFUL, {len(imported)} GRIFT batch(es) imported to the "
                    f"grid (PRODUCED_BATCH edges, disposition=imported). "
                    f"req-dev-validation-real-backend is buildable AND grid mutation "
                    f"is positively asserted."
                )
            )
            return

        # SUCCESSFUL with no import: a legitimate idempotent no-op (e.g.
        # DIFF_EMPTY on a re-run). The linchpin (real backend -> terminal) is
        # proven; grid mutation simply was not exercised this run. Honest
        # outcome, not a false GREEN — and not a failure.
        self.stdout.write(
            self.style.WARNING(
                f"MECHANISM PROVEN (no grid mutation this run): real backend enqueue -> "
                f"commit -> in-process drain -> terminal SUCCESSFUL, but the collector was "
                f"a no-op (no imported PRODUCED_BATCH edges; info={info_codes}). "
                f"req-dev-validation-real-backend is buildable; to also exercise a grid "
                f"mutation, run against a collector/state that imports (e.g. purge the "
                f"catalog entities first, then re-run)."
            )
        )
